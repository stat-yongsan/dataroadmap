import json
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
from backend import access, race  # noqa: E402


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

    def test_comparison_uses_same_question_and_reports_failures(self):
        state = {"goal": "sum", "row_count": 1000, "columns": ["부서", "금액"]}
        seen = []
        def codex(payload):
            seen.append(payload)
            return {"choice": "C", "model": "gpt-6.1-sol"}
        def jev(payload, key):
            seen.append(payload)
            self.assertEqual(key, "fake-key")
            raise ValueError("simulated failure")
        with patch.object(race, "jev_key", return_value="fake-key"), patch.object(race.shutil, "which", return_value="codex"), patch.object(race, "codex_call", side_effect=codex), patch.object(race, "jev_call", side_effect=jev):
            result = race.compare(state)
        self.assertEqual(seen[0], seen[1])
        self.assertEqual(result["gpt"]["choice"], "C")
        self.assertEqual(result["jev"]["status"], "failed")
        self.assertNotIn("fake-key", json.dumps(result))

    def test_comparison_without_key_never_starts_codex(self):
        with patch.object(race, "jev_key", return_value=""), patch.object(race, "codex_call") as codex:
            with self.assertRaises(ValueError):
                race.compare({"goal": "sum"})
            codex.assert_not_called()

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
        response = io.BytesIO(json.dumps({"model": "jev-test", "answers": {"next_step": {"choice": "C", "probabilities": probs}}}).encode())
        with patch.object(race, "urlopen", return_value=response) as call:
            self.assertEqual(race.jev_call(payload, "fake-key")["choice"], "C")
            sent = json.loads(call.call_args.args[0].data)
            self.assertEqual(sent["state"], payload["state"])
            self.assertEqual(sent["questions"], payload["questions"])

    def test_http_flow_and_comparison_requires_consent_and_same_origin(self):
        client = TestClient(app)
        fields = {"goal": "sum", "group_col": "부서", "value_col": "금액"}
        def post(path, data, headers=None):
            return client.post(path, data=data, files={"file": ("sample.csv", self.sample, "text/csv")}, headers=headers or {})
        self.assertEqual(client.get("/api/sample").status_code, 200)
        self.assertEqual(post("/api/profile", {}).json()["row_count"], 1000)
        self.assertEqual(post("/api/plan", fields).json()["status"], "not_run")
        self.assertEqual(post("/api/run", fields).json()["total"], "148982900")
        with patch.object(race, "availability", return_value={"codex_installed": True, "jev_key_present": True}), patch.object(race, "compare", return_value={"gpt": {"status": "ok"}, "jev": {"status": "ok"}}) as comparison:
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
        with patch.object(race, "availability", return_value={"codex_installed": True, "jev_key_present": True}), patch.object(race, "compare", return_value={"gpt": {}, "jev": {}}) as comparison:
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
            with patch.dict(os.environ, env, clear=True), patch.object(race, "availability", return_value={"codex_installed": True, "jev_key_present": True}), patch.object(race, "compare", return_value={"gpt": {}, "jev": {}}) as comparison:
                self.assertEqual(send("wrong").status_code, 403)
                self.assertEqual(comparison.call_count, 0)
                self.assertEqual(send("test-password").status_code, 200)
                self.assertEqual(send("test-password").status_code, 429)
                self.assertEqual(comparison.call_count, 1)


if __name__ == "__main__":
    unittest.main()
