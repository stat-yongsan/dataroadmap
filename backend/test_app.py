import json
import csv
from collections import Counter
import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from openpyxl import Workbook
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.app import app, execute, make_plan, parse_csv, profile  # noqa: E402
from backend import access, race, roadmaps  # noqa: E402


class DataRoadmapTests(unittest.TestCase):
    def setUp(self):
        self.sample = (ROOT / "data" / "sample.csv").read_bytes()

    def test_catalogue_and_sample(self):
        catalog = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(len(catalog["counts"]), 17)
        self.assertEqual(len(catalog["area_names"]), 17)
        self.assertEqual(len(catalog["projects"]), 153)
        data = profile(self.sample)
        self.assertEqual(data["row_count"], 1000)
        self.assertIn("금액", data["numeric_columns"])

    def test_default_student_example_and_previous_example(self):
        client = TestClient(app)
        response = client.get("/api/sample")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        raw = response.content
        self.assertEqual(raw, client.get("/api/sample").content)
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        self.assertEqual((len(rows), len(rows[0])), (1000, 30))
        self.assertEqual(len({r["학생ID"] for r in rows}), 1000)
        self.assertEqual(len({r["학과"] for r in rows}), 10)
        self.assertEqual(Counter(r["학업지원참여"] for r in rows), {"참여": 500, "미참여": 500})
        self.assertTrue(all(int(r["등록금_원"]) == int(r["장학금_원"]) + int(r["실납부액_원"]) for r in rows))
        self.assertTrue(all(int(r["대출금_원"]) <= int(r["실납부액_원"]) for r in rows))
        for row in rows:
            score = (float(row["중간고사"]) + float(row["기말고사"])) / 2
            self.assertEqual(row["성적구간"], "우수" if score >= 80 else "보통" if score >= 65 else "주의")
        counts = Counter(r["지원_성적구간"] for r in rows)
        self.assertGreater(counts["참여·우수"], counts["미참여·우수"] * 5)
        result = execute(raw, "count", "지원_성적구간")
        self.assertTrue(result["verified"])
        self.assertEqual(result["total"], "1000")
        self.assertEqual(execute(raw, "sum", "학과", "장학금_원")["total"], str(sum(int(r["장학금_원"]) for r in rows)))
        self.assertEqual(client.get("/api/sample/transactions").content, self.sample)

    def test_sum_is_verified_against_known_expected(self):
        plan = make_plan(self.sample, "sum", "부서", "금액")
        self.assertEqual(plan["status"], "not_run")
        result = execute(self.sample, "sum", "부서", "금액")
        self.assertEqual(result["total"], "148982900")
        self.assertEqual(len(result["rows"]), 10)
        self.assertTrue(result["verified"])

    def test_count_and_original_bytes(self):
        before = self.sample[:]
        result = execute(self.sample, "count", "부서")
        self.assertEqual(result["total"], "1000")
        self.assertTrue(result["verified"])
        self.assertEqual(self.sample, before)

    def test_incomplete_or_invalid_data_stops(self):
        for raw in (b"a,a\n1,2\n", b"a,b\n1\n", b"a,b\nx,\n"):
            with self.assertRaises(ValueError):
                if raw.endswith(b"x,\n"):
                    execute(raw, "sum", "a", "b")
                else:
                    parse_csv(raw)
        with self.assertRaises(ValueError):
            execute(b"group,value\na,nope\n", "sum", "group", "value")
        with self.assertRaises(ValueError):
            execute(b"group,value\n,10\n", "count", "group")
        with self.assertRaises(ValueError):
            make_plan(self.sample, "sum", "missing", "금액")

    def test_assessment_uses_observed_values_and_blocks_incomplete_data(self):
        raw = b'group,value\na,10\nb,bad\n,30\n'
        plan = make_plan(raw, "sum", "group", "value")
        self.assertEqual(plan["assessments"]["D02"]["score"], 66.7)
        self.assertEqual(plan["assessments"]["C03"]["score"], 66.7)
        self.assertEqual(plan["assessments"]["I01"]["score"], 33.3)
        self.assertIn("2/3", plan["assessments"]["C03"]["basis"])
        self.assertFalse(plan["executable"])
        self.assertNotIn("Q01", plan["assessments"])
        with self.assertRaises(ValueError):
            execute(raw, "sum", "group", "value")

    def test_xlsx_first_sheet_values_and_formula_rejection(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["group", "value"])
        ws.append(["a", 10])
        ws.append(["b", 20])
        wb.create_sheet("ignored").append(["unrelated"])
        buf = io.BytesIO()
        wb.save(buf)
        client = TestClient(app)
        file = {"file": ("sample.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        fields = {"goal": "sum", "group_col": "group", "value_col": "value"}
        plan = client.post("/api/plan", files=file, data=fields)
        self.assertEqual(plan.status_code, 200)
        self.assertIn("A02", plan.json()["assessments"])
        result = client.post("/api/run", files=file, data=fields)
        self.assertEqual(result.json()["total"], "30")
        ws["B2"] = "=1+1"
        buf = io.BytesIO()
        wb.save(buf)
        rejected = client.post("/api/profile", files={"file": ("sample.xlsx", buf.getvalue(), "application/octet-stream")})
        self.assertEqual(rejected.status_code, 400)

    def test_paths_and_copy_preview_are_real_and_bounded(self):
        client = TestClient(app)
        fields = {"goal": "sum", "group_col": "부서", "value_col": "금액"}
        file = {"file": ("sample.csv", self.sample, "text/csv")}
        first = client.post("/api/paths", data=fields, files=file).json()
        second = client.post("/api/paths", data={**fields, "page": "2"}, files=file).json()
        all_paths = first["paths"] + second["paths"]
        self.assertEqual(first["total"], 22)
        self.assertEqual(len(first["paths"]), 20)
        self.assertEqual(len(set(p["id"] for p in all_paths)), 22)
        selected = next(p for p in all_paths if p["steps"] == ["A03", "C03", "I01", "N02"])
        result = client.post("/api/preview", data={**fields, "path_id": selected["id"]}, files=file)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["result"]["total"], "148982900")
        self.assertEqual([s["id"] for s in result.json()["steps"]], selected["steps"])
        self.assertIsNone(result.json()["stopped"])
        self.assertEqual(client.post("/api/preview", data={**fields, "path_id": "A03-Q01-I01"}, files=file).status_code, 400)

    def test_copy_preview_stops_on_invalid_input(self):
        raw = b'group,value\na,10\nb,bad\n'
        selected = next(p for p in roadmaps.paths("sum", "csv") if p["steps"] == ["A03", "C03", "I01"])
        result = roadmaps.preview(raw, "sum", "group", "value", "csv", selected["id"])
        self.assertIn("C03", result["stopped"])
        self.assertIsNone(result["result"])
        self.assertEqual(raw, b'group,value\na,10\nb,bad\n')

    def test_comparison_uses_same_question_and_reports_failures(self):
        state = {"goal": "sum", "row_count": 1000, "columns": ["부서", "금액"]}
        seen = []
        def openai(payload, key):
            seen.append(payload)
            self.assertEqual(key, "fake-openai-key")
            return {"choice": "C", "model": "gpt-6-luna"}
        def jev(payload, key):
            seen.append(payload)
            self.assertEqual(key, "fake-key")
            raise ValueError("simulated failure")
        with patch.object(race, "jev_key", return_value="fake-key"), patch.object(race, "openai_key", return_value="fake-openai-key"), patch.object(race, "decisions_call", side_effect=openai), patch.object(race, "jev_call", side_effect=jev):
            result = race.compare(state)
        self.assertEqual(seen[0], seen[1])
        self.assertEqual(result["gpt"]["choice"], "C")
        self.assertEqual(result["jev"]["status"], "failed")
        self.assertNotIn("fake-key", json.dumps(result))

    def test_comparison_without_key_never_starts_provider(self):
        with patch.object(race, "jev_key", return_value=""), patch.object(race, "decisions_call") as openai:
            with self.assertRaises(ValueError):
                race.compare({"goal": "sum"})
            openai.assert_not_called()
        with patch.object(race, "jev_key", return_value="fake-key"), patch.object(race, "openai_key", return_value=""), patch.object(race, "jev_call") as jev:
            with self.assertRaises(ValueError):
                race.compare({"goal": "sum"})
            jev.assert_not_called()

    def test_existing_env_file_can_be_reused_without_exposing_key(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ".env"
            path.write_text("TYPESAFE_API_KEY=fake-local-key\n", encoding="utf-8")
            with patch.dict(os.environ, {"DATA_ROADMAP_ENV_FILE": str(path)}, clear=True):
                self.assertEqual(race.jev_key(), "fake-local-key")
            with patch.dict(os.environ, {"DATA_ROADMAP_ENV_FILE": str(path), "TYPESAFE_API_KEY": ""}, clear=True):
                self.assertEqual(race.jev_key(), "")

    def test_codex_cli_and_jev_receive_question_and_validate_choice(self):
        payload = race.question({"goal": "sum", "row_count": 3})
        def fake_run(args, **kwargs):
            Path(args[args.index("--output-last-message") + 1]).write_text('{"choice":"C","reason":"numeric text"}', encoding="utf-8")
            self.assertEqual(args[args.index("-m") + 1], "gpt-6.1-sol")
            self.assertIn("--sandbox", args)
            self.assertIn("--disable", args)
            self.assertNotIn("TYPESAFE_API_KEY", kwargs["env"])
            return types.SimpleNamespace(returncode=0, stdout=b'{"type":"turn.completed"}\n', stderr=b"")
        with patch.object(race.shutil, "which", return_value="codex"), patch.object(race.subprocess, "run", side_effect=fake_run):
            self.assertEqual(race.codex_call(payload)["choice"], "C")
        probs = {key: float(key == "C") for key in race.CHOICES}
        response = io.BytesIO(json.dumps({"model": "jev-1.13.0", "answers": {"next_step": {"choice": "C", "probabilities": probs}}}).encode())
        with patch.object(race, "urlopen", return_value=response) as call:
            self.assertEqual(race.jev_call(payload, "fake-key")["choice"], "C")
            sent = json.loads(call.call_args.args[0].data)
            self.assertEqual(sent["state"], payload["state"])
            self.assertEqual(sent["questions"], payload["questions"])
            self.assertEqual(sent["model"], "jev-1.13.0")

    def test_openai_decisions_request_and_response(self):
        payload = race.question({"goal": "sum", "row_count": 3})
        probabilities = [{"value": k, "probability": float(k == "I")} for k in race.CHOICES]
        response = io.BytesIO(json.dumps({"model": "gpt-6-luna", "answers": [{"name": "next_step", "type": "choice", "choice": "I", "probabilities": probabilities}]}).encode())
        with patch.object(race, "urlopen", return_value=response) as call:
            result = race.decisions_call(payload, "fake-openai-key")
            sent = json.loads(call.call_args.args[0].data)
            self.assertEqual(sent["model"], "gpt-6-luna")
            self.assertEqual(sent["input"][0]["content"][0]["data"], payload["state"])
            self.assertEqual({x["value"]: x["description"] for x in sent["questions"][0]["choices"]}, race.CHOICES)
            self.assertEqual(result["probabilities"]["I"], 1)
            self.assertTrue(result["probabilities_complete"])

    def test_jev_version_mismatch_rejected(self):
        response = io.BytesIO(json.dumps({"model": "jev-1.14.0", "answers": {}}).encode())
        with patch.object(race, "urlopen", return_value=response):
            with self.assertRaises(ValueError):
                race.jev_call(race.question({}), "fake-key")

    def test_openai_invalid_duplicate_probabilities_rejected(self):
        answer = {"model": "gpt-6-luna", "answers": [{"name": "next_step", "type": "choice", "choice": "I", "probabilities": [{"value": "I", "probability": 0.5}, {"value": "I", "probability": 0.5}]}]}
        with patch.object(race, "urlopen", return_value=io.BytesIO(json.dumps(answer).encode())):
            with self.assertRaises(ValueError):
                race.decisions_call(race.question({}), "fake-key")

    def test_http_flow_and_comparison_requires_consent_and_same_origin(self):
        client = TestClient(app)
        fields = {"goal": "sum", "group_col": "부서", "value_col": "금액"}
        def post(path, data, headers=None):
            return client.post(path, data=data, files={"file": ("sample.csv", self.sample, "text/csv")}, headers=headers or {})
        self.assertEqual(client.get("/api/sample").status_code, 200)
        self.assertEqual(post("/api/profile", {}).json()["row_count"], 1000)
        self.assertEqual(post("/api/plan", fields).json()["status"], "not_run")
        self.assertEqual(post("/api/run", fields).json()["total"], "148982900")
        with patch.object(race, "availability", return_value={"codex_installed": True, "jev_key_present": True, "openai_key_present": True}), patch.object(race, "compare", return_value={"gpt": {"status": "ok"}, "jev": {"status": "ok"}}) as comparison:
            self.assertEqual(post("/api/race", fields).status_code, 403)
            self.assertEqual(post("/api/race", {**fields, "consent": "true"}, {"x-data-roadmap": "1", "origin": "https://evil.example"}).status_code, 403)
            self.assertEqual(post("/api/race", fields, {"x-data-roadmap": "1"}).status_code, 400)
            self.assertFalse(comparison.called)
            self.assertEqual(post("/api/race", {**fields, "consent": "true"}, {"x-data-roadmap": "1"}).status_code, 200)
            state = comparison.call_args.args[0]
            self.assertEqual(state["row_count"], 1000)
            self.assertNotIn("rows", state)
            self.assertNotIn("98,300", json.dumps(state))

    def test_incomplete_data_may_be_sent_for_area_choice_but_not_executed(self):
        client = TestClient(app)
        raw = b'group,value\na,10\nb,bad\n'
        fields = {"goal": "sum", "group_col": "group", "value_col": "value", "consent": "true"}
        file = {"file": ("sample.csv", raw, "text/csv")}
        self.assertEqual(client.post("/api/run", data=fields, files=file).status_code, 400)
        with patch.object(race, "availability", return_value={"codex_installed": True, "jev_key_present": True, "openai_key_present": True}), patch.object(race, "compare", return_value={"gpt": {}, "jev": {}}) as comparison:
            response = client.post("/api/race", data=fields, files=file, headers={"x-data-roadmap": "1"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(comparison.call_args.args[0]["measured_checks"]["C03"]["score"], 50.0)

    def test_hosted_review_access_and_persistent_limit(self):
        from fastapi import HTTPException
        with tempfile.TemporaryDirectory() as temp:
            env = {"DATA_ROADMAP_HOSTED": "1", "DATA_ROADMAP_REVIEW_PASSWORD": "test-review-password",
                   "DATA_ROADMAP_QUOTA_DB": str(Path(temp) / "quota.db"), "DATA_ROADMAP_COMPARE_LIMIT": "2"}
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaises(HTTPException) as wrong:
                    access.reserve("wrong")
                self.assertEqual(wrong.exception.status_code, 403)
                access.reserve("test-review-password")
                access.reserve("test-review-password")
                with self.assertRaises(HTTPException) as capped:
                    access.reserve("test-review-password")
                self.assertEqual(capped.exception.status_code, 429)

    def test_hosted_http_denies_unknown_and_enforces_limit(self):
        client = TestClient(app)
        fields = {"goal": "count", "group_col": "부서", "consent": "true"}
        def send(password):
            return client.post("/api/race", data=fields, files={"file": ("sample.csv", self.sample, "text/csv")},
                               headers={"x-data-roadmap": "1", "x-review-password": password})
        with tempfile.TemporaryDirectory() as temp:
            env = {"DATA_ROADMAP_HOSTED": "1", "DATA_ROADMAP_REVIEW_PASSWORD": "test-password",
                   "DATA_ROADMAP_QUOTA_DB": str(Path(temp) / "quota.db"), "DATA_ROADMAP_COMPARE_LIMIT": "1"}
            with patch.dict(os.environ, env, clear=True), patch.object(race, "availability", return_value={"codex_installed": True, "jev_key_present": True, "openai_key_present": True}), patch.object(race, "compare", return_value={"gpt": {}, "jev": {}}) as comparison:
                self.assertEqual(send("wrong").status_code, 403)
                self.assertEqual(comparison.call_count, 0)
                self.assertEqual(send("test-password").status_code, 200)
                self.assertEqual(send("test-password").status_code, 429)
                self.assertEqual(comparison.call_count, 1)


if __name__ == "__main__":
    unittest.main()
