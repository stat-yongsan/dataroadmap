"""FastAPI — 127.0.0.1 한 포트에서 API 와 빌드된 화면을 함께 내보낸다(P8).

  .venv\\Scripts\\python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
"""
import json
import re
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse

from . import catalog, contracts, decisions, engine, examples, exports, planning, preview, profiling, race, settings, store
from . import hosting



@asynccontextmanager
async def lifespan(_app):
    if settings.HOSTED and not settings.ADMIN_PASSWORD:
        raise RuntimeError("ROADMAP_ADMIN_PASSWORD is required in hosted mode")
    catalog.load()
    examples.build()
    store.db()
    if settings.HOSTED:
        from . import demo
        demo.read()
    yield


app = FastAPI(title="데이터 활용 로드맵", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)
app.middleware("http")(hosting.access)


def _err(e: engine.EngineError):
    return HTTPException(status_code=e.code, detail=str(e))


# ---------------- 기본 정보 ----------------
@app.get("/api/health")
def health(request: Request):
    admin = hosting.is_admin(request)
    if settings.HOSTED and not admin:
        return {"hosted": True, "admin": False, "mode": "public-example", "codex_ready": False}
    return {"hosted": settings.HOSTED, "admin": admin, "codex_ready": settings.codex_available(), "codex_model": settings.CODEX_MODEL,
            "mode": "MOCK", "live_key_present": bool(settings.live_key()), "catalog_version": catalog.load()["catalog_version"],
            "versions": settings.VERSIONS, "capabilities": engine.capabilities(), "limits": settings.LIMITS, "search": settings.SEARCH,
            "jev_model_default": settings.JEV_MODEL, "anthropic_key_present": bool(settings.anthropic_key()),
            "openai_key_present": bool(settings.openai_key()), "openai_model": settings.OPENAI_DECISIONS_MODEL}


@app.get("/api/demo")
def public_demo():
    from . import demo
    return demo.read()


@app.get("/api/catalog")
def catalog_index():
    c = catalog.load()
    return {"catalog_version": c["catalog_version"], "source": c["source"], "areas": c["areas"], "verify": c["verify"],
            "projects": [{k: p[k] for k in ("project_id", "area_id", "title", "environment")} | {"implementation_status": contracts.status_of(p["project_id"])}
                         for p in c["projects"]],
            "workflows": c["workflows"]}


@app.get("/api/catalog/{pid}")
def catalog_card(pid: str):
    c = catalog.load()
    p = c["by_id"].get(pid) or next((w for w in c["workflows"] if w["workflow_id"] == pid), None)
    if not p:
        raise HTTPException(404, "없는 카드")
    f = settings.CATALOG_DIR / "cards" / f"{pid}.md"
    return {"source": p, "card_md": f.read_text(encoding="utf-8") if f.exists() else "", "impl": contracts.meta(pid) if "project_id" in p else None}


@app.get("/api/goals")
def goals():
    return {k: {"label": v["label"], "required": v["required"]} for k, v in planning.GOALS.items()}


@app.get("/api/policy")
def policy():
    return {"version": settings.VERSIONS["policy"], "rules": planning.POLICY_RULES, "control": decisions.CONTROL, "score_levels": decisions.SCORE_LEVELS}


# ---------------- 데이터셋 ----------------
@app.get("/api/examples")
def list_examples():
    return [{"key": k, "title": v["title"], "desc": v["desc"], "file": v["file"], "goal_key": v["goal_key"], "params": v["params"],
             "rules": v["rules"], "expected": v["expected"]} for k, v in examples.EXAMPLES.items()]


@app.post("/api/examples/{key}")
def load_example(key: str):
    ex = examples.EXAMPLES.get(key)
    if not ex:
        raise HTTPException(404, "없는 예제")
    try:
        ds = engine.create_dataset((settings.EXAMPLES_DIR / ex["file"]).read_bytes(), ex["file"], f"example:{key}")
    except engine.EngineError as e:
        raise _err(e)
    return {"dataset_id": ds, "suggested": {"goal_key": ex["goal_key"], "params": ex["params"], "rules": ex["rules"]}}


@app.post("/api/datasets")
async def upload(file: UploadFile = File(...), encoding: str = Form("")):
    raw = await file.read(settings.LIMITS["upload_bytes"] + 1)
    try:
        ds = engine.create_dataset(raw, file.filename or "upload.csv")
        if encoding:
            engine.ingest(ds, {"encoding": encoding})
    except engine.EngineError as e:
        raise _err(e)
    return {"dataset_id": ds}


@app.get("/api/datasets/{ds}")
def get_dataset(ds: str, key: str = ""):
    try:
        d = engine.dataset(ds)
    except engine.EngineError as e:
        raise _err(e)
    v = engine.current_detail(ds)
    rules = {"key": [k for k in key.split(",") if k]} if key else {}
    prof = engine.profile_of(v, rules)["profile"] if v else None
    preview = None
    if v:
        t = store.load_table(v)
        preview = {"columns": t["columns"], "rows": t["rows"][:20], "note": f"미리보기 {min(20, len(t['rows']))}행 — 판정은 전체 {len(t['rows'])}행 측정값(프로필)으로 한다"}
    steps = store.many("SELECT step_run_id, project_id, status, issues_json, checks_json, started_at FROM step_runs WHERE run_id=? ORDER BY rowid", engine.run_of(ds))
    return {"dataset": {k: d[k] for k in ("dataset_id", "display_name", "kind", "sha256", "size", "source", "created_at")},
            "inspect": d["inspect"], "detail_version": v and {k: v[k] for k in ("version_id", "parent_version_id", "grain", "created_at")},
            "profile": prof, "preview": preview, "suggested_goals": profiling.suggest_goals(prof) if prof else [],
            "run_id": engine.run_of(ds), "steps": steps}


@app.post("/api/datasets/{ds}/ingest")
def ingest(ds: str, params: dict = Body(default={})):
    allowed = {k: params[k] for k in ("encoding", "delimiter", "sheet", "header_row", "range", "last_row") if params.get(k) not in (None, "")}
    if "range" in allowed and not re.fullmatch(r"[A-Za-z]{1,3}\d{1,7}:[A-Za-z]{1,3}\d{1,7}", str(allowed["range"])):
        raise HTTPException(400, "범위는 B3:D6 같은 형식이어야 합니다")
    if "header_row" in allowed:
        allowed["header_row"] = int(allowed["header_row"])
    try:
        return engine.ingest(ds, allowed)
    except engine.EngineError as e:
        raise _err(e)


@app.post("/api/datasets/{ds}/goals")
def create_goal(ds: str, body: dict = Body(...)):
    """preview_only = LIVE 전 「보낼 필드」 먼저 보기(D11): 목표만 만들고 판단은 부르지 않는다.
    그 뒤 goal_id 를 넘기면 같은 목표로 계획을 만든다 — 첫 호출의 state 는 미리 본 것과 같은 함수(state_payload)로 만든다."""
    try:
        gid = body.get("goal_id")
        if gid:
            g = store.one("SELECT dataset_id FROM goals WHERE goal_id=?", gid)
            if not g or g["dataset_id"] != ds:
                raise HTTPException(404, "없는 목표")
        else:
            gid = engine.create_goal(ds, body.get("goal_key"), body.get("params") or {}, body.get("rules") or {}, body.get("description") or "")
        if body.get("preview_only"):
            state = engine.observed_state(ds, gid)
            return {"goal_id": gid, "live_payload": planning.state_payload(state, planning.candidates(state))}
        pid = engine.plan(ds, gid, body.get("provider") or "mock", req_id=body.get("req_id"))
    except engine.EngineError as e:
        raise _err(e)
    return {"goal_id": gid, "plan_id": pid}


@app.post("/api/plan-requests/{req_id}/cancel")
def cancel_plan(req_id: str):
    planning.cancel(req_id)
    return {"cancelled": req_id}


# ---------------- 계획 ----------------
def _plan_lineage(plan_id):
    chain, cur = [], store.one("SELECT plan_id, parent_plan_id, created_at FROM plans WHERE plan_id=?", plan_id)
    while cur:
        chain.append(cur)
        cur = store.one("SELECT plan_id, parent_plan_id, created_at FROM plans WHERE plan_id=?", cur["parent_plan_id"]) if cur["parent_plan_id"] else None
    child = store.one("SELECT plan_id FROM plans WHERE parent_plan_id=? ORDER BY rowid DESC LIMIT 1", plan_id)
    return list(reversed(chain)), child and child["plan_id"]


@app.get("/api/plans/{plan_id}")
def get_plan(plan_id: str):
    pl = store.one("SELECT * FROM plans WHERE plan_id=?", plan_id)
    if not pl:
        raise HTTPException(404, "없는 계획")
    g = store.one("SELECT * FROM goals WHERE goal_id=?", pl["goal_id"])
    nodes, edges, root = planning.load_graph(plan_id)
    cat = catalog.load()["by_id"]
    decisions_by_call = {d["call_id"]: d for d in store.many("SELECT call_id, provider, model_returned, probabilities_json, confidence, answers_json, status, error, latency_ms FROM decision_calls WHERE plan_id=?", plan_id)}
    out_nodes = []
    for n in nodes.values():
        st = n["state"] or {}
        out_nodes.append({"node_id": n["node_id"], "parent": n["parent_node_id"], "depth": n["depth"], "project_id": n["project_id"],
                          "control_action": n["control_action"], "title": cat.get(n["project_id"], {}).get("title") if n["project_id"] else None,
                          "state_kind": n["state_kind"], "status": n["display_status"], "suggested": bool(n["suggested"]),
                          "terminal_reason": n["terminal_reason"], "gate": n["gate"], "decision_call_id": n["decision_call_id"],
                          "implementation_status": contracts.status_of(n["project_id"]) if n["project_id"] else None,
                          "conditions": st.get("conditions", []) if n["state_kind"] == "projected" else [],
                          "artifacts": [a["kind"] for a in st.get("artifacts", [])]})
    lineage, newer = _plan_lineage(plan_id)
    rd = decisions_by_call.get(root["decision_call_id"]) if root["decision_call_id"] else None
    state = root["state"]
    try:
        cands = planning.candidates(state)
        preview = planning.state_payload(state, cands)
    except Exception:  # noqa: BLE001 — 미리보기 실패는 계획 화면을 막지 않는다
        preview = None
    hist = [{"step_run_id": s["step_run_id"], "project_id": s["project_id"], "status": s["status"],
             "title": cat.get(s["project_id"], {}).get("title"), "checks": s.get("checks"), "issues": s.get("issues"), "metrics": s.get("metrics")}
            for s in engine.steps_on_lineage(pl["dataset_id"])]
    return {"plan": {k: pl[k] for k in ("plan_id", "dataset_id", "goal_id", "run_id", "base_version_id", "parent_plan_id", "provider",
                                        "versions", "status", "stop_reasons", "calls_used", "usage", "created_at")},
            "config": {k: v for k, v in pl["config"].items() if k not in ("paths", "root_candidates")},
            "goal": {"goal_key": g["goal_key"], "label": planning.GOALS[g["goal_key"]]["label"], "params": g["params"], "rules": g["rules"]},
            "root_state": {k: state.get(k) for k in ("dataset_version_id", "grain", "unresolved_requirements", "artifacts", "completed_steps", "checks")}
            | {"columns": state["facts"]["columns"], "table_confirmed": state["facts"]["table_confirmed"], "key_dup_groups": state["facts"].get("key_dup_groups")},
            "nodes": out_nodes, "edges": [{"from": e["from"], "to": e["to"], "option": e["option"], "p": e["p"], "rank": e["rank"], "kind": e["kind"]} for e in edges],
            "paths": pl["config"].get("paths", []), "root_decision": rd, "decisions": decisions_by_call,
            "history": hist, "lineage": lineage, "newer_plan": newer, "live_preview": preview,
            "notes": exports.notes(pl["provider"])}


@app.get("/api/plans/{plan_id}/nodes/{node_id}")
def node_detail(plan_id: str, node_id: str):
    n = store.one("SELECT * FROM plan_nodes WHERE node_id=? AND plan_id=?", node_id, plan_id)
    if not n:
        raise HTTPException(404, "없는 노드")
    parent = store.one("SELECT * FROM plan_nodes WHERE node_id=?", n["parent_node_id"]) if n["parent_node_id"] else None
    dc = store.one("SELECT * FROM decision_calls WHERE call_id=?", parent["decision_call_id"]) if parent and parent["decision_call_id"] else None
    own = store.one("SELECT * FROM decision_calls WHERE call_id=?", n["decision_call_id"]) if n["decision_call_id"] else None
    pid = n["project_id"]
    card = catalog.load()["by_id"].get(pid) if pid else None
    rule = None
    if dc and dc.get("answers") and dc["answers"].get("policy_rules"):
        rid = dc["answers"]["policy_rules"].get(n["option"])
        rule = {"rule_id": rid, "text": planning.POLICY_RULES.get(rid)}
    st = n.get("state") or {}
    return {"node": {k: n[k] for k in ("node_id", "depth", "project_id", "control_action", "state_kind", "display_status", "terminal_reason", "suggested")},
            "gate": n.get("gate"), "card": card, "impl": contracts.meta(pid) if pid else None,
            "control_text": decisions.CONTROL.get(n["control_action"]) if n["control_action"] else None,
            "selection": {"probabilities": dc.get("probabilities") if dc else None, "chosen_option": n["option"],
                          "confidence": dc.get("confidence") if dc else None, "provider": dc.get("provider") if dc else None,
                          "model": dc.get("model_returned") if dc else None, "rule": rule,
                          "areas": {k: v for k, v in ((dc.get("answers") or {}).get("answers") or {}).items() if k.startswith("area_")} if dc else {},
                          "score": ((dc.get("answers") or {}).get("answers") or {}).get(f"contrib_{pid}") if dc and pid else None},
            "own_decision": own and {"probabilities": own.get("probabilities"), "status": own["status"], "error": own["error"]},
            "state": {"kind": n["state_kind"], "conditions": st.get("conditions", []), "artifacts": st.get("artifacts", []),
                      "completed_steps": st.get("completed_steps", []), "checks": st.get("checks", []),
                      "facts": {"table_confirmed": st.get("facts", {}).get("table_confirmed"), "key_dup_groups": st.get("facts", {}).get("key_dup_groups")}}}


@app.post("/api/plans/{plan_id}/nodes/{node_id}/run")
def run_node(plan_id: str, node_id: str, body: dict = Body(default={})):
    try:
        return engine.execute(plan_id, node_id, force_new=bool(body.get("force_new")))
    except engine.EngineError as e:
        raise _err(e)


@app.post("/api/plans/{plan_id}/nodes/{node_id}/expand")
def expand(plan_id: str, node_id: str, body: dict = Body(...)):
    try:
        return {"node_id": planning.expand(plan_id, node_id, body.get("option"))}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/plans/{plan_id}/replan")
def replan(plan_id: str, body: dict = Body(default={})):
    pl = store.one("SELECT * FROM plans WHERE plan_id=?", plan_id)
    if not pl:
        raise HTTPException(404, "없는 계획")
    try:
        return {"plan_id": engine.plan(pl["dataset_id"], pl["goal_id"], body.get("provider") or engine.provider_request(pl["provider"]),
                                       parent_plan_id=plan_id, req_id=body.get("req_id"))}
    except engine.EngineError as e:
        raise _err(e)


@app.get("/api/plans/{plan_id}/export/roadmap.json")
def export_json(plan_id: str):
    try:
        data = exports.roadmap(plan_id)
    except KeyError:
        raise HTTPException(404, "없는 계획")
    return Response(json.dumps(data, ensure_ascii=False, indent=1, default=str), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="roadmap_{plan_id}.json"'})


@app.get("/api/plans/{plan_id}/export/roadmap.html")
def export_html(plan_id: str, download: int = 0):
    try:
        doc = exports.roadmap_html(plan_id)
    except KeyError:
        raise HTTPException(404, "없는 계획")
    headers = {"Content-Disposition": f'attachment; filename="roadmap_{plan_id}.html"'} if download else {}
    return HTMLResponse(doc, headers=headers)


# ---------------- 실행 기록 · 산출물 ----------------
@app.get("/api/plans/{plan_id}/paths/{leaf}/preview")
def path_preview(plan_id: str, leaf: str):
    """경로 결과 미리보기(D17) — 메모리에서만 돌리고 아무것도 저장하지 않는다. 계획 ID + 끝 노드 ID 로만 찾는다."""
    try:
        doc = preview.render(preview.run(plan_id, leaf))
    except preview.PreviewError as e:
        raise HTTPException(e.code, str(e))
    csp = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'"
    return HTMLResponse(doc, headers={"Content-Security-Policy": csp})


# ---------------- 결정 속도 비교(/race, D20) — 계획 · 경로에는 쓰지 않는다 ----------------
def _race_err(e: race.RaceError):
    return HTTPException(status_code=e.code, detail=str(e))


@app.get("/api/race/{plan_id}")
def race_info(plan_id: str):
    try:
        payload, q = race.race_input(plan_id)
    except race.RaceError as e:
        raise _race_err(e)
    return {"plan_id": plan_id, "payload": payload, "questions": q, "opus_model": race.OPUS_MODEL, "efforts": race.EFFORTS,
            "max_per_batch": race.MAX_PER_BATCH, "jev_model": settings.JEV_MODEL,
            "keys": {"jev": bool(settings.live_key()), "opus": bool(settings.anthropic_key())}, **race.summary(plan_id)}


@app.post("/api/race/{plan_id}/jev")
def race_jev(plan_id: str, body: dict = Body(default={})):
    try:
        return race.run_jev(plan_id, body.get("batch_id"))
    except race.RaceError as e:
        raise _race_err(e)


@app.post("/api/race/{plan_id}/opus")
def race_opus(plan_id: str, body: dict = Body(default={})):
    try:
        gen = race.stream_opus(plan_id, body.get("batch_id"), body.get("effort") or "low")
    except race.RaceError as e:
        raise _race_err(e)
    return StreamingResponse(gen, media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    try:
        m = exports.run_manifest(run_id)
    except KeyError:
        raise HTTPException(404, "없는 실행")
    cat = catalog.load()["by_id"]
    for s in m["step_runs"]:
        s["title"] = cat.get(s["project_id"], {}).get("title")
    return m


@app.get("/api/runs/{run_id}/manifest")
def get_manifest(run_id: str):
    try:
        m = exports.run_manifest(run_id)
    except KeyError:
        raise HTTPException(404, "없는 실행")
    return Response(json.dumps(m, ensure_ascii=False, indent=1, default=str), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="run_manifest_{run_id}.json"'})


@app.get("/api/versions/{version_id}")
def get_version(version_id: str, limit: int = 200):
    v = store.one("SELECT * FROM dataset_versions WHERE version_id=?", version_id)   # ID 로만 찾는다
    if not v:
        raise HTTPException(404, "없는 버전")
    t = store.load_table(v)
    n = max(1, min(limit, 1000))
    return {"version": {k: v[k] for k in ("version_id", "dataset_id", "parent_version_id", "role", "agg_kind", "grain", "created_at")},
            "schema": t["schema"], "columns": t["columns"], "rows": t["rows"][:n], "total_rows": len(t["rows"]), "shown": min(n, len(t["rows"]))}


MEDIA = {".csv": "text/csv; charset=utf-8", ".json": "application/json", ".png": "image/png", ".html": "text/html; charset=utf-8"}


@app.get("/api/artifacts/{artifact_id}")
def artifact(artifact_id: str, download: int = 0):
    a = store.one("SELECT * FROM artifacts WHERE artifact_id=?", artifact_id)   # ID 로만 찾는다
    if not a:
        raise HTTPException(404, "없는 산출물")
    p = (settings.DATA / a["path"]).resolve()
    if settings.DATA.resolve() not in p.parents or not p.is_file():
        raise HTTPException(404, "파일 없음")
    headers = {"Content-Security-Policy": "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'"}
    if download or p.suffix != ".html":
        headers["Content-Disposition"] = f'{"attachment" if download else "inline"}; filename="{a["name"]}"'
    return FileResponse(p, media_type=MEDIA.get(p.suffix, "application/octet-stream"), headers=headers)


# ---------------- /learn ----------------
@app.get("/api/learn/outline")
def learn_outline():
    f = settings.DOCS_DIR / "source" / "Jev_60min_Lecture_KO.md"
    text = f.read_text(encoding="utf-8")
    units = []
    for m in re.finditer(r"^## (\d+)\. (.+?) / (\d{2}–\d{2}분)\s*$", text, re.M):
        body = text[m.end():text.find("\n## ", m.end()) if text.find("\n## ", m.end()) > 0 else len(text)]
        screen = re.search(r"\*\*화면 문장\*\*: (.+)", body)
        units.append({"no": int(m[1]), "title": m[2], "time": m[3], "screen": screen[1].strip() if screen else None})
    return {"source": "docs/source/Jev_60min_Lecture_KO.md", "units": units}


# ---------------- /devplan (D13) ----------------
BANNER = ('<div style="position:sticky;top:0;z-index:9;background:#fff3cd;color:#3a3000;padding:.45rem .8rem;font:700 14px \'Malgun Gothic\',system-ui;'
          'border-bottom:1px solid #e0c060">모의 판단(MOCK) 앱의 개발계획 — 이 페이지는 data-roadmap/docs/devplan.json 에서 생성된 것 · <a href="/">앱으로</a></div>')


@app.get("/devplan", response_class=HTMLResponse)
def devplan():
    h, j = settings.DOCS_DIR / "devplan.html", settings.DOCS_DIR / "devplan.json"
    doc = h.read_text(encoding="utf-8")
    warn = ""
    if j.stat().st_mtime > h.stat().st_mtime + 1:
        warn = ('<div style="background:#b44;color:#fff;padding:.45rem .8rem;font:700 14px system-ui">생성물 낡음 — devplan.json 이 더 새것입니다. '
                '<code>node tools/devplan.js data-roadmap/docs</code> 로 다시 만드세요</div>')
    return doc.replace("<body>", "<body>" + BANNER + warn, 1)


# ---------------- /lecture (D14) ----------------
# 발표용 강의자료는 data-roadmap/lecture/ 에 따로 둔 파일(더블클릭으로도 열림). 앱은 /learn 링크용으로 그 파일을 그대로 보여 줄 뿐이다.
LECTURE_DIR = settings.ROOT / "lecture"


@app.get("/lecture")
def lecture_slash():
    return RedirectResponse("/lecture/")


@app.get("/lecture/{path:path}")
def lecture(path: str):
    f = (LECTURE_DIR / (path or "index.html")).resolve()
    if LECTURE_DIR.resolve() not in f.parents or f.suffix not in (".html", ".png") or not f.is_file():
        raise HTTPException(404, "강의자료 파일 없음")
    return FileResponse(f)


@app.get("/requirements-source.md", response_class=PlainTextResponse)
def requirements_source():
    return (settings.DOCS_DIR / "requirements-source.md").read_text(encoding="utf-8")


# ---------------- 화면(SPA) ----------------
@app.get("/{path:path}")
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "없는 API")
    f = (settings.FRONTEND_DIST / path).resolve()
    if path and settings.FRONTEND_DIST.resolve() in f.parents and f.is_file():
        return FileResponse(f)
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        return HTMLResponse("<p>화면이 아직 빌드되지 않았습니다 — run.bat 을 실행하거나 frontend 에서 npm run build</p>", status_code=503)
    return FileResponse(index)


@app.exception_handler(engine.EngineError)
def engine_error(_, e: engine.EngineError):
    return JSONResponse({"detail": str(e)}, status_code=e.code)
