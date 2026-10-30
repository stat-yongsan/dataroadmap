"""내보내기(원문 §17): roadmap.json · roadmap.html(앱 없이 열림 · 표 대체 보기) · run_manifest.json.

실행하지 않은 노드는 projected 표시를 그대로 둔다. API 키 · 원본 셀 값은 넣지 않는다.
"""
import html

from . import catalog, handlers, planning, settings, store

STATUS_KO = {"observed": "현재 상태(측정)", "ready": "실행 가능", "running": "실행 중", "succeeded": "검증 완료",
             "needs_info": "정보 필요", "needs_review": "검토 필요", "unsupported": "현재 환경에서 지원 안 됨",
             "failed": "실패", "projected": "아직 실행하지 않은 계획", "done": "목표 도달(계획)"}
NOTES = ["경로 추천 점수 = 이 앱이 정한 Choice 확률의 기하평균. 실제 성공확률 · 최적성 · 보정된 확률이 아니다.",
         "confidence = 판단 확신 지표(정답률 아님). MOCK 판단에는 confidence 가 없다.",
         "MOCK = 명시한 로컬 규칙(policy.v1)이며 실제 Jev 판단이 아니다."]


def mode(provider):
    return {"mock": "MOCK(모의 판단)", "typesafe": "LIVE(TypeSafe Jev)", "codex": "LIVE(OpenAI Codex)",
            "openai": "LIVE(OpenAI Decisions API)"}.get(provider, f"LIVE({provider})")


def notes(provider):
    if provider == "codex":
        return ["Codex 선택 표시: 1=선택, 0=미선택 대안. 확률·성공률·confidence가 아닙니다.",
                "현재 측정 상태에서 한 단계만 판단하고, Python 실행·검증 뒤 다시 판단합니다.",
                "경로 점수는 기존 저장 형식의 선택 지시자 집계이며 성공확률이 아닙니다."]
    return NOTES


def _label(n):
    if n["control_action"]:
        return n["control_action"]
    if n["depth"] == 0:
        return "현재 상태"
    t = catalog.load()["by_id"].get(n["project_id"], {}).get("title", "")
    return f"{n['project_id']} · {t}"


def roadmap(plan_id) -> dict:
    pl = store.one("SELECT * FROM plans WHERE plan_id=?", plan_id)
    if not pl:
        raise KeyError(plan_id)
    g = store.one("SELECT * FROM goals WHERE goal_id=?", pl["goal_id"])
    nodes, edges, root = planning.load_graph(plan_id)
    return {
        "format": "roadmap.v1", "plan_id": plan_id, "parent_plan_id": pl["parent_plan_id"], "created_at": pl["created_at"],
        "mode": mode(pl["provider"]), "value_semantics": "selection_indicator" if pl["provider"] == "codex" else "choice_distribution",
        "goal": {"key": g["goal_key"], "label": planning.GOALS[g["goal_key"]]["label"], "params": g["params"], "description": g["description"]},
        "state_version": pl["base_version_id"], "versions": pl["versions"], "config": {k: v for k, v in pl["config"].items() if k not in ("paths", "root_candidates")},
        "stop_reasons": pl["stop_reasons"], "calls_used": pl["calls_used"], "usage": pl["usage"],
        "nodes": [{"node_id": n["node_id"], "parent": n["parent_node_id"], "depth": n["depth"], "label": _label(n),
                   "project_id": n["project_id"], "control_action": n["control_action"], "state_kind": n["state_kind"],
                   "status": n["display_status"], "status_ko": STATUS_KO.get(n["display_status"], n["display_status"]),
                   "suggested": bool(n["suggested"]), "gate": n["gate"], "terminal_reason": n["terminal_reason"],
                   "conditions": (n["state"] or {}).get("conditions", []) if not n["control_action"] else []} for n in nodes.values()],
        "edges": [{"from": e["from"], "to": e["to"], "option": e["option"], "prob_raw": e["p"], "prob_search": max(e["p"], 1e-12),
                   "rank": e["rank"], "kind": e["kind"]} for e in edges],
        "paths": pl["config"].get("paths", []),
        "notes": notes(pl["provider"]),
    }


def roadmap_html(plan_id) -> str:
    r = roadmap(plan_id)
    e = html.escape
    selection_label = "선택 표시(1=선택, 0=대안)" if r["value_semantics"] == "selection_indicator" else "선택지 확률"
    by_parent = {}
    for n in r["nodes"]:
        by_parent.setdefault(n["parent"], []).append(n)
    probs = {(x["from"], x["to"]): x["prob_raw"] for x in r["edges"]}

    def tree(pid, depth=0):
        kids = by_parent.get(pid, [])
        if not kids or depth > 8:
            return ""
        items = []
        for n in kids:
            p = probs.get((pid, n["node_id"]))
            cond = f"<br><small>조건: {e(' · '.join(n['conditions']))}</small>" if n["conditions"] and n["state_kind"] == "projected" else ""
            items.append(f"<li><b>{e(n['label'])}</b> <span class='s s-{e(n['status'])}'>{e(n['status_ko'])}</span>"
                         f"{' <span class=sug>추천됨</span>' if n['suggested'] else ''}{f' <small>{selection_label} {p:.3f}</small>' if p is not None else ''}{cond}"
                         f"{tree(n['node_id'], depth + 1)}</li>")
        return "<ul>" + "".join(items) + "</ul>"

    root = next(n for n in r["nodes"] if n["depth"] == 0)
    rows = "".join(f"<tr><td>{p['rank']}</td><td>{'완료 경로' if p['complete'] else '부분 경로'}</td><td>{e(' → '.join(p['steps']) or '(없음)')}</td>"
                   f"<td>{p['score']:.3f}</td><td>{'예' if p['all_implemented'] else '아니오'}</td><td>{e(', '.join(p['result_kinds']))}</td>"
                   f"<td>{e(' · '.join(p['conditions']))}</td><td>{e(p['ends_with'])}</td></tr>" for p in r["paths"][:15])
    nrows = "".join(f"<tr><td>{n['depth']}</td><td>{e(n['label'])}</td><td>{e(n['status_ko'])}</td><td>{e(n['state_kind'])}</td>"
                    f"<td>{e(n['terminal_reason'] or '')}</td></tr>" for n in sorted(r["nodes"], key=lambda x: x["depth"]))
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>활용 로드맵 — {e(r['goal']['label'])}</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--dim:#666;--line:#ddd;--warn:#fff3cd}}
@media(prefers-color-scheme:dark){{:root{{--bg:#16181c;--fg:#e8e8e8;--dim:#9aa0a6;--line:#333;--warn:#3a3000}}}}
body{{font-family:"Malgun Gothic",system-ui,sans-serif;margin:0;padding:16px;background:var(--bg);color:var(--fg);line-height:1.55;overflow-wrap:anywhere}}
.band{{background:var(--warn);padding:.5rem .8rem;border-radius:6px;font-weight:700}} table{{border-collapse:collapse;width:100%;font-size:.9rem}}
th,td{{border:1px solid var(--line);padding:.35rem .5rem;text-align:left;vertical-align:top}} small,.dim{{color:var(--dim)}}
ul{{padding-left:1.2rem}} .s{{font-size:.8rem;border:1px solid var(--line);border-radius:8px;padding:0 .35rem}} .sug{{font-size:.8rem;color:#0a7}}
.s-ready{{color:#07a}} .s-projected{{border-style:dashed}} .s-unsupported,.s-needs_review{{color:#b44}}
</style></head><body>
<p class="band">{e(r['mode'])} — {'실제 Jev 판단이 아닙니다' if r['mode'].startswith('MOCK') else '외부 판단 결과'}</p>
<h1>활용 로드맵 — {e(r['goal']['label'])}</h1>
<p class="dim">계획 {e(r['plan_id'])} · 상태 버전 {e(r['state_version'])} · {e(r['created_at'])} · 카탈로그 {e(str(r['versions'].get('catalog')))} · 정책 {e(str(r['versions'].get('policy')))}</p>
<ul class="dim">{''.join(f'<li>{e(x)}</li>' for x in r['notes'])}</ul>
<h2>분기 그래프(트리 보기)</h2><ul><li><b>현재 상태(측정)</b>{tree(root['node_id'])}</li></ul>
<h2>경로 비교</h2><table><thead><tr><th>순위</th><th>종류</th><th>작업 순서</th><th>경로 추천 점수</th><th>모두 실행기 있음</th><th>결과</th><th>필요한 조건</th><th>끝</th></tr></thead><tbody>{rows}</tbody></table>
<h2>노드 표(대체 보기)</h2><table><thead><tr><th>깊이</th><th>노드</th><th>상태</th><th>종류</th><th>멈춘 이유</th></tr></thead><tbody>{nrows}</tbody></table>
<p class="dim">멈춘 이유: {e(' · '.join(r['stop_reasons']) or '없음')} · 판단 호출(LIVE) {r['calls_used']}회</p>
</body></html>"""


def run_manifest(run_id) -> dict:
    run = store.one("SELECT * FROM runs WHERE run_id=?", run_id)
    if not run:
        raise KeyError(run_id)
    ds = store.one("SELECT dataset_id, display_name, kind, sha256, size, source, created_at FROM datasets WHERE dataset_id=?", run["dataset_id"])
    steps = store.many("SELECT * FROM step_runs WHERE run_id=? ORDER BY rowid", run_id)
    arts = store.many("SELECT a.artifact_id, a.step_run_id, a.name, a.kind, a.grain, a.sha256, a.created_at FROM artifacts a "
                      "JOIN step_runs s ON a.step_run_id=s.step_run_id WHERE s.run_id=? ORDER BY a.rowid", run_id)
    plans = store.many("SELECT plan_id, provider, calls_used, usage_json, created_at, parent_plan_id FROM plans WHERE run_id=? ORDER BY rowid", run_id)
    return {
        "format": "run_manifest.v1", "run": run, "dataset": ds,
        "versions": store.many("SELECT version_id, parent_version_id, role, agg_kind, grain, created_by_step_run, created_at FROM dataset_versions WHERE dataset_id=? ORDER BY rowid", run["dataset_id"]),
        "step_runs": [{k: s.get(k) for k in ("step_run_id", "project_id", "handler_version", "config_hash", "idempotency_key", "input_versions",
                                             "output_versions", "checks", "execution_mode", "status", "metrics", "issues", "started_at", "ended_at")} for s in steps],
        "artifacts": arts,
        "decisions": {"plans": plans, "live_calls": sum(p["calls_used"] or 0 for p in plans),
                      "tokens": {k: sum((p.get("usage") or {}).get(k, 0) for p in plans) for k in ("input_tokens", "output_tokens")},
                      "cost": "요금표 확인 전이라 원화 비용은 표시하지 않음(호출 수 · 토큰만)"},
        "csv_escape_policy": handlers.CSV_ESCAPE_POLICY,
        "app_versions": {**settings.VERSIONS, "catalog": catalog.load()["catalog_version"]},
        "mode": "판단 " + (" + ".join(sorted({mode(p["provider"]) for p in plans})) or "MOCK")
                + " · 실행 로컬(execution_mode=local)",
    }
