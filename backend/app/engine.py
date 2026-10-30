"""엔진(원문 §8.4): 업로드 → 읽기(A02/A03) → observed 상태 → 계획 → 실행 → 결과 검증 → 새 버전 → 다시 계획.

원본은 불변. 실행마다 새 dataset_version 을 만들고, 실패 · 검토 필요면 성공 버전을 갱신하지 않는다(원문 §7).
실행할 수 있는 것은 등록된 실행기와 스키마를 통과한 설정뿐이다 — 셀 안의 문장 · 모델 출력은 명령이 아니다(원문 §15).
"""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from . import contracts, decisions, handlers as H, planning, profiling, settings, store

TEXT_EXT = {".csv": "csv", ".tsv": "csv", ".txt": "csv"}


class EngineError(Exception):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


@lru_cache(maxsize=1)
def capabilities() -> tuple:
    caps = ["python", "openpyxl"]
    try:
        import matplotlib  # noqa: F401
        from matplotlib import font_manager
        caps.append("matplotlib")
        font_manager.findfont(font_manager.FontProperties(family=settings.KOREAN_FONT), fallback_to_default=False)
        caps.append(f"font:{settings.KOREAN_FONT}")
    except (ImportError, ValueError):
        pass
    caps.append("excel_com:미확인(사용 안 함)")   # Windows Excel 기능을 실행했다고 표시하지 않는다(원문 §2)
    return tuple(caps)


def _h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ---------------- 데이터셋 · 읽기 ----------------
def create_dataset(raw: bytes, display_name: str, source: str = "upload") -> str:
    if len(raw) > settings.LIMITS["upload_bytes"]:
        raise EngineError(f"파일이 {len(raw):,} 바이트로 업로드 한도 {settings.LIMITS['upload_bytes']:,} 바이트(20 MiB)를 넘습니다 — 자르지 않고 거절합니다", 413)
    ext = Path(display_name).suffix.lower()
    if ext in (".xlsm", ".xlsb", ".xls"):
        raise EngineError(f"{ext} 는 받지 않습니다 — 매크로 파일은 실행하지 않고, 구형 형식 변환(A04)은 Excel 엔진이 필요해 BLOCKED 입니다", 415)
    kind = "xlsx" if ext == ".xlsx" else TEXT_EXT.get(ext)
    if not kind:
        raise EngineError("CSV · TSV · XLSX 만 받습니다", 415)
    ds = store.new_id("ds")
    folder = settings.DATA / "uploads" / ds
    folder.mkdir(parents=True, exist_ok=True)
    original = folder / f"original{ext}"       # 경로는 ID 로만 만든다 — 업로드 파일명을 경로에 쓰지 않는다
    original.write_bytes(raw)
    try:
        info = profiling.inspect_xlsx(original) if kind == "xlsx" else profiling.inspect_csv(raw, display_name)
    except profiling.InspectError as e:
        raise EngineError(str(e), 422) from e
    run_id = store.new_id("run")
    store.insert("datasets", dataset_id=ds, display_name=display_name, kind=kind, sha256=profiling.sha256_bytes(raw), size=len(raw),
                 source=source, original_path=str(original.relative_to(settings.DATA)), inspect_json=info, created_at=store.now())
    store.insert("runs", run_id=run_id, dataset_id=ds, status="open", created_at=store.now())
    if info["table"]["status"] == "confirmed":
        ingest(ds, {})
    return ds


def dataset(ds: str) -> dict:
    d = store.one("SELECT * FROM datasets WHERE dataset_id=?", ds)
    if not d:
        raise EngineError("데이터셋이 없습니다", 404)
    return d


def run_of(ds: str) -> str:
    return store.one("SELECT run_id FROM runs WHERE dataset_id=? ORDER BY created_at LIMIT 1", ds)["run_id"]


def current_detail(ds: str):
    return store.one("SELECT * FROM dataset_versions WHERE dataset_id=? AND role='detail' ORDER BY rowid DESC LIMIT 1", ds)


def ingest(ds: str, params: dict) -> dict:
    """A03(텍스트) 또는 A02(XLSX) 실행기로 원본을 상세 표 v0 으로 읽는다. 표 범위를 사용자가 정하면 A02 를 그 범위로 돌린다."""
    d = dataset(ds)
    raw_path = settings.DATA / d["original_path"]
    pid = "A02" if d["kind"] == "xlsx" else "A03"
    cfg = {k: params.get(k) for k in (("sheet", "header_row", "range", "last_row") if pid == "A02" else ("encoding", "delimiter")) if params.get(k)}

    def call(run_dir):
        if pid == "A03":
            return H.a03_read_text(raw_path.read_bytes(), d["display_name"], cfg.get("encoding"), cfg.get("delimiter"))
        return H.a02_read_range(raw_path, cfg.get("sheet") or d["inspect"]["table"].get("sheet"), cfg.get("header_row"),
                                cfg.get("range"), cfg.get("last_row"))
    return record_step(ds, pid, cfg, {"detail": None, "original_sha256": d["sha256"]}, call)


def record_step(ds, pid, cfg, inputs, call, plan_id=None, node_id=None, force_new=False) -> dict:
    run_id = run_of(ds)
    idem = _h([ds, pid, inputs, cfg, H.VERSION])   # 같은 바이트의 다른 업로드와 섞이지 않게 데이터셋까지 넣는다
    prev = store.one("SELECT * FROM step_runs WHERE idempotency_key=? AND status='succeeded'", idem)
    if prev and not force_new:
        return {**prev, "reused": True}      # 같은 요청 반복 → 완료 결과 재사용(원본 · 이전 결과를 덮지 않음)
    sr = store.new_id("sr")
    run_dir = settings.DATA / "runs" / run_id / sr
    run_dir.mkdir(parents=True, exist_ok=True)
    started = store.now()
    try:
        res = call(run_dir)
    except H.HandlerError as e:
        res = H.StepResult(e.status, checks=e.checks, issues=[str(e)])
    if res.new_table and len(res.new_table["rows"]) > settings.LIMITS["max_rows"]:
        res = H.StepResult("failed", issues=[f"행 {len(res.new_table['rows']):,}개가 읽기 한도 {settings.LIMITS['max_rows']:,} 를 넘습니다 — 자르지 않고 거절"])
    outputs = {}
    ok = res.status == "succeeded"
    if ok and res.new_table:
        vid = store.new_id("v")
        res.new_table["schema"].setdefault("grain", None)
        store.insert("dataset_versions", version_id=vid, dataset_id=ds, parent_version_id=inputs.get("detail"), role="detail", agg_kind=None,
                     grain=res.new_table["schema"].get("grain"), table_path=store.save_table(vid, res.new_table),
                     schema_json=res.new_table["schema"], created_by_step_run=sr, created_at=store.now())
        outputs["detail"] = vid
        res.outputs.append(H._table_out(run_dir, "result", res.new_table))
    if ok and res.aggregate:
        vid = store.new_id("v")
        kind = inputs.get("agg_kind_out")
        store.insert("dataset_versions", version_id=vid, dataset_id=ds, parent_version_id=inputs.get("aggregate") or inputs.get("detail"),
                     role="aggregate", agg_kind=kind, grain=res.aggregate["schema"].get("grain"), table_path=store.save_table(vid, res.aggregate),
                     schema_json=res.aggregate["schema"], created_by_step_run=sr, created_at=store.now())
        outputs["aggregate"] = vid
        outputs["agg_kind"] = kind
        res.outputs.append(H._table_out(run_dir, "result", res.aggregate, kind="aggregate"))
    (run_dir / "check.json").write_text(json.dumps({"project_id": pid, "status": res.status, "checks": res.checks, "issues": res.issues},
                                                   ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    if res.provenance:
        (run_dir / "provenance.json").write_text(json.dumps(res.provenance, ensure_ascii=False, indent=1), encoding="utf-8")
    res.outputs.append({"name": "check.json", "kind": "check", "path": "check.json"})
    store.insert("step_runs", step_run_id=sr, run_id=run_id, project_id=pid, handler_version=H.VERSION, config_hash=_h(cfg), idempotency_key=idem,
                 input_versions_json=inputs, output_versions_json=outputs, checks_json=res.checks, execution_mode="local",
                 status=res.status, metrics_json=res.metrics, issues_json=res.issues, plan_id=plan_id, node_id=node_id,
                 started_at=started, ended_at=store.now())
    for c in res.checks:
        store.insert("checks", check_id=store.new_id("ck"), step_run_id=sr, project_id=pid, name=c["name"], status=c["status"],
                     detail_json=c.get("detail"), created_at=store.now())
    for o in res.outputs:
        p = run_dir / o["path"]
        store.insert("artifacts", artifact_id=store.new_id("af"), step_run_id=sr, name=o["name"], kind=o["kind"],
                     path=str(p.relative_to(settings.DATA)), grain=o.get("grain"),
                     sha256=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None, created_at=store.now())
    return store.one("SELECT * FROM step_runs WHERE step_run_id=?", sr)


# ---------------- observed 상태 ----------------
def lineage(ds) -> list:
    v = current_detail(ds)
    out = []
    while v:
        out.append(v["version_id"])
        v = store.one("SELECT * FROM dataset_versions WHERE version_id=?", v["parent_version_id"]) if v["parent_version_id"] else None
    return out


def steps_on_lineage(ds) -> list:
    lin = set(lineage(ds))
    out = []
    for s in store.many("SELECT * FROM step_runs WHERE run_id=? ORDER BY rowid", run_of(ds)):
        det = (s.get("input_versions") or {}).get("detail")
        made = (s.get("output_versions") or {}).get("detail")
        if (det in lin) or (det is None and made in lin):
            out.append(s)
    return out


def profile_of(version, rules) -> dict:
    rh = _h(rules.get("key") or [])
    got = store.one("SELECT * FROM profiles WHERE version_id=? AND rules_hash=?", version["version_id"], rh)
    if got:
        return got
    prof = profiling.profile_table(store.load_table(version), rules)
    pid = store.new_id("pf")
    store.insert("profiles", profile_id=pid, version_id=version["version_id"], rules_hash=rh, profile_json=prof, created_at=store.now())
    return store.one("SELECT * FROM profiles WHERE profile_id=?", pid)


def goal(goal_id) -> dict:
    g = store.one("SELECT * FROM goals WHERE goal_id=?", goal_id)
    if not g:
        raise EngineError("목적이 없습니다", 404)
    return g


def column_facts(profile) -> tuple:
    """프로필 → 게이트가 보는 열 사실 · 업무 키 중복 그룹 수(관측 상태와 미리보기가 같이 쓴다)."""
    cols = {c["name"]: {k: c[k] for k in ("kind", "identifier", "identifier_damage_possible", "numeric",
                                          "needs_parse", "empty", "null", "distinct", "leading_zero_values")} for c in profile["columns"]}
    dup = profile.get("declared_key_duplicates")
    return cols, (dup["groups"] if dup else None)


def observed_state(ds, goal_id) -> dict:
    d, g = dataset(ds), goal(goal_id)
    rules, params = g["rules"] or {}, g["params"] or {}
    v = current_detail(ds)
    facts = {"table_confirmed": v is not None, "file_kind": d["kind"], "columns": {}, "key_dup_groups": None,
             "table_reasons": [] if v else d["inspect"]["table"].get("reasons") or [d["inspect"]["table"].get("reason")]}
    profile_id = None
    if v:
        pr = profile_of(v, rules)
        profile_id = pr["profile_id"]
        facts["columns"], facts["key_dup_groups"] = column_facts(pr["profile"])
    completed, checks, arts = [], [], []
    for s in steps_on_lineage(ds):
        cks = s.get("checks") or []
        cstat = "failed" if any(c["status"] == "failed" for c in cks) else ("passed" if cks else None)
        completed.append({"project_id": s["project_id"], "status": s["status"], "state": "observed", "step_run_id": s["step_run_id"],
                          "check_status": cstat})
        for c in cks:
            checks.append({"project_id": s["project_id"], "name": c["name"], "status": c["status"], "step_run_id": s["step_run_id"]})
        if s["status"] == "succeeded":
            ov = s.get("output_versions") or {}
            kind = ov.get("agg_kind") or {"N02": "chart", "N05": "html"}.get(s["project_id"])
            if kind:
                arts.append({"kind": kind, "state": "observed", "version_id": ov.get("aggregate"), "step_run_id": s["step_run_id"]})
    state = {
        "state_id": store.new_id("st"), "state_kind": "observed",
        "dataset_version_id": v["version_id"] if v else f"{ds}:읽기 전",
        "goal": {"key": g["goal_key"], "label": planning.GOALS[g["goal_key"]]["label"], "params": params, "description": g["description"]},
        "grain": {"value": rules.get("grain"), "status": "confirmed" if rules.get("grain") else "unconfirmed"},
        "business_rules": rules, "profile_ref": profile_id, "facts": facts, "artifacts": arts, "checks": checks,
        "completed_steps": completed, "available_capabilities": list(capabilities()),
        "remaining_call_budget": settings.SEARCH["max_live_calls_per_plan"], "conditions": [],
    }
    state["unresolved_requirements"] = planning.unresolved(state)
    state["goal"]["status"] = "confirmed" if not any(u.startswith("목표 인자") for u in state["unresolved_requirements"]) else "unconfirmed"
    return state


# ---------------- 목적 · 계획 ----------------
def provider_for(kind: str):
    if kind == "codex":
        if not settings.codex_available():
            raise EngineError("Codex가 활성화되어 있지 않습니다 — 모의 판단으로 바꾸지 않습니다", 400)
        from .codex_provider import CodexProvider
        return CodexProvider()
    if kind == "openai":
        if not settings.openai_key():
            raise EngineError("OPENAI_API_KEY 가 없어 OpenAI 판단을 쓸 수 없습니다(MOCK 으로 바꾸지 않음). .env 에 키를 넣으면 켜집니다", 400)
        return decisions.OpenAIDecisionsProvider()
    if kind == "live":
        if not settings.live_key():
            raise EngineError("TYPESAFE_API_KEY 가 없어 LIVE 판단을 쓸 수 없습니다(MOCK 으로 바꾸지 않음). .env 에 키를 넣으면 켜집니다", 400)
        return decisions.TypeSafeJevProvider()
    if kind == "mock":
        return decisions.MockDecisionProvider()
    raise EngineError("알 수 없는 판단 공급자입니다", 400)


def provider_request(kind):
    return {"mock": "mock", "typesafe": "live", "codex": "codex"}.get(kind, kind)


def _clean(v, where):
    """바깥 입력 검증: JSON 값만 · UTF-8 로 저장할 수 있는 문자열만."""
    if isinstance(v, str):
        try:
            v.encode("utf-8")
        except UnicodeEncodeError:
            raise EngineError(f"{where}: 저장할 수 없는 문자가 있습니다(깨진 한글?)") from None
        return v
    if isinstance(v, dict):
        return {_clean(k, where): _clean(x, where) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x, where) for x in v]
    if v is None or isinstance(v, (int, float, bool)):
        return v
    raise EngineError(f"{where}: 허용하지 않는 값")


def create_goal(ds, goal_key, params, rules, description="") -> str:
    if goal_key not in planning.GOALS:
        raise EngineError(f"알 수 없는 목적: {goal_key}")
    params, rules, description = _clean(params or {}, "목표 인자"), _clean(rules or {}, "업무 규칙"), _clean(description or "", "설명")
    v = current_detail(ds)
    if v:
        cols = store.load_table(v)["columns"]
        bad = [f"{k}={x}" for k, x in params.items() if k.endswith("_col") and x and x not in cols]
        bad += [f"key={k}" for k in (rules.get("key") or []) if k not in cols]
        if bad:
            raise EngineError(f"표에 없는 열: {bad} (열: {cols})")
    if rules.get("key") is not None and not isinstance(rules["key"], list):
        raise EngineError("업무 키(key)는 열 이름 목록이어야 합니다")
    gid = store.new_id("goal")
    store.insert("goals", goal_id=gid, dataset_id=ds, goal_key=goal_key, description=description, params_json=params or {},
                 rules_json=rules or {}, status="active", created_at=store.now())
    return gid


def plan(ds, goal_id, provider_kind="mock", parent_plan_id=None, req_id=None) -> str:
    root = observed_state(ds, goal_id)
    return planning.build_plan(root, dataset_id=ds, goal_id=goal_id, run_id=run_of(ds), provider=provider_for(provider_kind),
                               parent_plan_id=parent_plan_id, req_id=req_id)


# ---------------- 실행 ----------------
def _latest_art(state, kind):
    for a in reversed(state["artifacts"]):
        if a["kind"] == kind:
            return a
    return None


def _source(state, load_version):
    """N02 · N05 가 그릴 목표 결과 표와 라벨 · 값 열 · 단위."""
    gk, p, r = state["goal"]["key"], state["goal"]["params"], state["business_rules"]
    kind = planning.GOALS[gk]["artifact"]
    a = _latest_art(state, kind)
    if not a:
        raise EngineError("목표 결과 표가 아직 없습니다")
    t = load_version(a["version_id"])
    label = p.get("group_col") if p.get("group_col") in t["columns"] else "구분"
    value, unit, vlabel = {"agg_sum": (f"sum_{p.get('value_col')}", r.get("value_unit") or "", "합계"),
                           "agg_count": ("count", "건", "건수"), "distinct": ("distinct_entities", "명", "대상 수"),
                           "rate": ("ratio", "%", "비율")}[kind]
    return a, t, label, value, unit, vlabel


def step_call(pid, state, table, detail_vid, load_version, profile_now):
    """실행기 호출 하나를 만든다 → (inputs, cfg, call(run_dir)). 실제 실행(execute)과 경로 미리보기(preview)가 같이 쓴다(D17 ⑥).
    load_version(vid) → 표, profile_now() → 지금 상세 표의 프로필. 저장은 부르는 쪽이 정한다."""
    g, p, r = state["goal"], state["goal"]["params"], state["business_rules"]
    inputs = {"detail": detail_vid}
    cfg = {"params": p, "rules": {k: r.get(k) for k in ("key", "amount_syntax", "declared_groups", "success_values", "aliases", "value_unit")}}
    if pid == "C01":
        call = lambda d: H.c01_rename(table, r["aliases"])
    elif pid == "C03":
        call = lambda d: H.c03_parse(table, p["value_col"], r.get("amount_syntax") or {})
    elif pid == "C05":
        ids = [c for c in dict.fromkeys([p.get("entity_col"), *(r.get("key") or [])]) if c and state["facts"]["columns"].get(c, {}).get("identifier")]
        call = lambda d: H.c05_identifiers(table, ids)
    elif pid == "D01":
        want = {"group_col": "string", "value_col": "number_or_text", "entity_col": "identifier", "status_col": "string", "date_col": "any"}
        req = {p[k]: t for k, t in want.items() if p.get(k)}
        for k in r.get("key") or []:
            req.setdefault(k, "string")
        prof = profile_now()
        call = lambda d: H.d01_schema(table, req, profile=prof)
    elif pid == "D03":
        call = lambda d: H.d03_duplicates(table, r["key"])
    elif pid == "I01":
        gk = g["key"]
        group = [p["group_col"]] if p.get("group_col") else []
        if gk == "rate_by_group":
            group, measures = [p["group_col"], p["status_col"]], [{"op": "count"}]
        elif gk == "sum_by_group":
            measures = [{"op": "count"}, {"op": "sum", "col": p["value_col"]}]
        else:
            measures = [{"op": "count"}]
        inputs["agg_kind_out"] = planning.I01_KIND[gk]
        call = lambda d: H.i01_aggregate(table, group, measures, r.get("declared_groups"))
    elif pid == "I02":
        inputs["agg_kind_out"] = "distinct"
        call = lambda d: H.i02_distinct(table, [p["entity_col"]], [p["group_col"]] if p.get("group_col") else None)
    elif pid == "H01":
        a = _latest_art(state, "agg_status")
        inputs["aggregate"], inputs["agg_kind_out"] = a["version_id"], "rate"
        agg = load_version(a["version_id"])
        call = lambda d: H.h01_ratio(agg, p["group_col"], p["status_col"], p["success_values"])
    elif pid in ("N02", "N05"):
        a, t, label, value, unit, vlabel = _source(state, load_version)
        inputs["aggregate"] = a["version_id"]
        title = f"{label}별 {vlabel}"
        fn = H.n02_chart if pid == "N02" else H.n05_html
        call = lambda d: fn(t, label, value, d, unit=unit, title=title, value_label=vlabel)
    else:
        raise EngineError(f"{pid} 실행기 연결 없음", 409)
    return inputs, cfg, call


def _load_version(vid):
    return store.load_table(store.one("SELECT * FROM dataset_versions WHERE version_id=?", vid))


def execute(plan_id, node_id, force_new=False) -> dict:
    pl = store.one("SELECT * FROM plans WHERE plan_id=?", plan_id)
    nd = store.one("SELECT * FROM plan_nodes WHERE node_id=? AND plan_id=?", node_id, plan_id)
    if not pl or not nd:
        raise EngineError("계획 또는 노드가 없습니다", 404)
    if nd["depth"] != 1 or nd["control_action"] or not nd["project_id"]:
        raise EngineError("지금 실행할 수 있는 것은 현재 상태 바로 다음의 작업 노드뿐입니다(아직 실행하지 않은 계획은 입력이 없음)", 409)
    ds, pid = pl["dataset_id"], nd["project_id"]
    state = observed_state(ds, pl["goal_id"])            # 실행 직전에 실제 상태로 게이트를 다시 판정한다
    cand = planning.candidates(state).get(pid)
    if not cand or not cand["gate"]["executable"]:
        why = cand["gate"]["reasons"] if cand else ["현재 상태에서 허용된 후보가 아님"]
        raise EngineError(f"{pid} 는 지금 실행할 수 없습니다: {why}", 409)
    if pid not in contracts.IMPL:
        raise EngineError(f"{pid} 는 실행기가 없습니다", 409)
    v = current_detail(ds)
    inputs, cfg, call = step_call(pid, state, store.load_table(v), v["version_id"], _load_version,
                                  lambda: profile_of(v, state["business_rules"])["profile"])
    sr = record_step(ds, pid, cfg, inputs, call, plan_id=plan_id, node_id=node_id, force_new=force_new)
    new_plan = plan(ds, pl["goal_id"], provider_request(pl["provider"]), parent_plan_id=plan_id)
    return {"step_run": sr, "plan_id": new_plan, "reused": bool(sr.get("reused"))}
