"""Publish only the fixed synthetic 1000-row example, using the actual application engine.

Public GET serves an immutable verified snapshot; it never accepts uploads or starts model calls.
Run `python -m app.demo codex` as an operator to record actual Codex decisions before publication.
"""
import hashlib
import json
import sys

from . import catalog, engine, planning, settings, store

FILENAME = "example_a_money_text_1000.csv"
EXPECTED = 148_982_900


def snapshot_path():
    return settings.DATA / "public-demo.json"


def generate(provider="mock"):
    if provider not in ("mock", "codex"):   # 공개 예제 화면은 이 둘만 표시한다 — 다른 공급자가 「모의」로 보이면 안 된다
        raise ValueError(f"공개 예제에 쓰지 않는 판단 공급자입니다: {provider}")
    catalog.load()
    raw = (settings.EXAMPLES_DIR / FILENAME).read_bytes()
    ds = engine.create_dataset(raw, FILENAME, source="public-synthetic-demo")
    rules = {"grain": "거래 1건", "key": ["거래번호"], "value_unit": "원"}
    gid = engine.create_goal(ds, "sum_by_group", {"group_col": "부서", "value_col": "금액"}, rules)
    pid = engine.plan(ds, gid, provider)
    trace = []
    for _ in range(16):
        roots = store.many("SELECT * FROM plan_nodes WHERE plan_id=? AND depth=0", pid)
        dc = store.one("SELECT * FROM decision_calls WHERE call_id=?", roots[0]["decision_call_id"])
        if dc["status"] != "ok":
            raise RuntimeError(dc.get("error") or "Demo decision failed")
        answer = dc["answers"]["answers"]["next_step"]
        chosen = answer["choice"]
        trace.append({"choice": chosen, "reason": answer.get("reason") or "명시한 모의 판단 규칙으로 선택",
                      "provider": dc["provider"], "model": dc["model_returned"], "latency_ms": dc["latency_ms"]})
        if chosen == "done":
            break
        if chosen in ("needs_info", "unsupported"):
            raise RuntimeError(f"Fixed example stopped: {chosen}")
        node = store.one("SELECT node_id FROM plan_nodes WHERE plan_id=? AND depth=1 AND project_id=?", pid, chosen)
        if node is None:
            nid = planning.expand(pid, roots[0]["node_id"], chosen)
        else:
            nid = node["node_id"]
        result = engine.execute(pid, nid)
        if result["step_run"]["status"] != "succeeded":
            raise RuntimeError(f"Demo execution failed: {chosen}")
        pid = result["plan_id"]
    else:
        raise RuntimeError("Demo did not finish within 16 steps")
    agg = store.one("SELECT * FROM dataset_versions WHERE dataset_id=? AND role='aggregate' AND agg_kind='agg_sum' ORDER BY rowid DESC LIMIT 1", ds)
    if not agg:
        raise RuntimeError("No sum artifact")
    table = store.load_table(agg)
    total = sum(row[table["columns"].index("sum_금액")] for row in table["rows"])
    if total != EXPECTED or len(table["rows"]) != 10:
        raise RuntimeError("Independent example answer mismatch; snapshot was not published")
    steps = store.many("SELECT project_id, status, checks_json, metrics_json, output_versions_json FROM step_runs WHERE run_id=? ORDER BY rowid", engine.run_of(ds))
    stages = []
    for step in steps:
        vid = (step.get("output_versions") or {}).get("aggregate") or (step.get("output_versions") or {}).get("detail")
        sample = None
        if vid:
            version = store.one("SELECT * FROM dataset_versions WHERE version_id=?", vid)
            t = store.load_table(version)
            sample = {"columns": t["columns"], "rows": t["rows"][:10]}
        stages.append({"id": step["project_id"], "title": catalog.load()["by_id"][step["project_id"]]["title"],
                       "status": step["status"], "checks": step.get("checks") or [], "preview": sample})
    source = engine.dataset(ds)
    if source["source"] != "public-synthetic-demo" or source["sha256"] != hashlib.sha256(raw).hexdigest():
        raise RuntimeError("Only the fixed synthetic source can be published")
    data = {"format": "public-demo.v1", "title": "1,000건 지출 자료 → 부서별 합계", "generated_at": store.now(),
            "provider": provider, "model": next((t["model"] for t in trace if t["model"]), None),
            "source": {"file": FILENAME, "rows": 1000, "groups": 10, "sha256": source["sha256"], "synthetic": True},
            "total": total, "expected_total": EXPECTED, "verified": total == EXPECTED, "result": {"columns": table["columns"], "rows": table["rows"]},
            "stages": stages, "decisions": trace,
            "note": "실제로 실행한 고정 가상 예제의 기록입니다. 공개 화면 조작은 새 모델 호출이나 파일 업로드를 하지 않습니다."}
    path = snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return data


def read():
    path = snapshot_path()
    if not path.exists():
        return generate("mock")
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    d = generate(sys.argv[1] if len(sys.argv) > 1 else "mock")
    print(json.dumps({"provider": d["provider"], "model": d["model"], "total": d["total"], "verified": d["verified"], "steps": len(d["stages"])}, ensure_ascii=False))
