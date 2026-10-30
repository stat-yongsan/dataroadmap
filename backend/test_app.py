import json
import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.app import app, execute, make_plan, parse_csv, profile  # noqa: E402
from backend import race  # noqa: E402


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

    def test_comparison_uses_same_question_and_reports_failures(self):
        state = {"goal": "sum", "row_count": 1000, "columns": ["부서", "금액"]}
        seen = []
        def codex(payload):
            seen.append(payload)
            return {"choice": "C03", "model": "gpt-6.1-sol"}
        def jev(payload, key):
            seen.append(payload)
            self.assertEqual(key, "fake-key")
            raise ValueError("simulated failure")
        with patch.object(race, "jev_key", return_value="fake-key"), patch.object(race.shutil, "which", return_value="codex"), patch.object(race, "codex_call", side_effect=codex), patch.object(race, "jev_call", side_effect=jev):
            result = race.compare(state)
        self.assertEqual(seen[0], seen[1])
        self.assertEqual(result["gpt"]["choice"], "C03")
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
            Path(args[args.index("--output-last-message") + 1]).write_text('{"choice":"C03"}', encoding="utf-8")
            self.assertEqual(args[args.index("-m") + 1], "gpt-6.1-sol")
            self.assertIn("--sandbox", args)
            self.assertIn("--disable", args)
            self.assertNotIn("TYPESAFE_API_KEY", kwargs["env"])
            return types.SimpleNamespace(returncode=0, stdout=b'{"type":"turn.completed"}\n', stderr=b"")
        with patch.object(race.shutil, "which", return_value="codex"), patch.object(race.subprocess, "run", side_effect=fake_run):
            self.assertEqual(race.codex_call(payload)["choice"], "C03")
        response = io.BytesIO(json.dumps({"model": "jev-test", "answers": {"next_step": {"choice": "C03"}}}).encode())
        with patch.object(race, "urlopen", return_value=response) as call:
            self.assertEqual(race.jev_call(payload, "fake-key")["choice"], "C03")
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
        with patch.object(race, "compare", return_value={"gpt": {"status": "ok"}, "jev": {"status": "ok"}}) as comparison:
            self.assertEqual(post("/api/race", fields).status_code, 403)
            self.assertEqual(post("/api/race", {**fields, "consent": "true"}, {"x-data-roadmap": "1", "origin": "https://evil.example"}).status_code, 403)
            self.assertEqual(post("/api/race", fields, {"x-data-roadmap": "1"}).status_code, 400)
            self.assertFalse(comparison.called)
            self.assertEqual(post("/api/race", {**fields, "consent": "true"}, {"x-data-roadmap": "1"}).status_code, 200)
            state = comparison.call_args.args[0]
            self.assertEqual(state["row_count"], 1000)
            self.assertNotIn("rows", state)
            self.assertNotIn("98,300", json.dumps(state))


if __name__ == "__main__":
    unittest.main()
