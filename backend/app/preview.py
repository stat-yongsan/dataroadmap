"""경로 결과 미리보기(D17 · Q8 가): 계획의 경로 하나를 현재 데이터 버전의 메모리 복사본에서 그 순서대로 실제 실행기로 돌려 본다.

「실행은 깊이 1 노드만」의 미리보기 전용 예외라서 지키는 것:
- DB · data/runs 에 아무것도 남기지 않는다(record_step · profile_of 를 부르지 않는다). 원본과 기존 버전은 읽기만 한다.
- 단계마다 게이트 6조건을 다시 판정하고, 게이트 실패 · 실행기 없음 · 실행 실패에서 「여기서 멈춤」.
- 문구는 「미리보기 통과 / 미리보기 실패 / 여기서 멈춤」 — 「검증 완료 · 실제 실행」을 쓰지 않는다.
- 그래프 · projected state · Jev payload · 내보내기에 섞지 않는다. 경로는 계획 ID + 끝 노드 ID 로만 찾는다.
- 실제 흐름은 단계마다 다시 판단하므로, 이 결과는 「앱이 갈 길」이 아니라 「이 순서대로 돌리면」이다.
"""
import base64
import copy
import html
import json
import tempfile
from pathlib import Path

from . import catalog, contracts, engine, exports, planning, profiling, store
from . import handlers as H

BADGE = {"passed": "미리보기 통과", "failed": "미리보기 실패", "stopped": "여기서 멈춤", "skipped": "미실행(앞에서 멈춤)"}
GATE_KO = {"input_contract_matches": "입력 계약 일치", "required_parameters_resolved": "필요한 인자 있음", "preconditions_pass": "사전조건 통과",
           "handler_implemented": "실행기 구현됨", "runtime_capabilities_available": "실행 환경 지원", "requested_operation_allowed": "허용된 작업"}


class PreviewError(Exception):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


def run(plan_id: str, leaf: str) -> dict:
    pl = store.one("SELECT * FROM plans WHERE plan_id=?", plan_id)
    if not pl:
        raise PreviewError("없는 계획", 404)
    path = next((p for p in pl["config"].get("paths", []) if p["leaf"] == leaf), None)
    if not path:
        raise PreviewError("이 계획의 경로 비교 표에 없는 경로입니다", 404)
    _, _, root = planning.load_graph(plan_id)
    state = copy.deepcopy(root["state"])
    rules = state["business_rules"]
    titles = catalog.load()["by_id"]
    out = {"plan_id": plan_id, "leaf": leaf, "path": path, "base_version_id": pl["base_version_id"], "provider": pl["provider"],
           "goal": state["goal"], "steps": [], "stopped": None, "result": None,
           "others": [{"rank": q["rank"], "steps": q["steps"], "leaf": q["leaf"], "complete": q["complete"]} for q in pl["config"].get("paths", [])[:10]]}
    v = store.one("SELECT * FROM dataset_versions WHERE version_id=?", pl["base_version_id"])
    if not v:
        out["stopped"] = "표를 아직 읽지 않은 상태(표 범위 미확정)라 미리보기를 할 수 없습니다"
        return out
    table = store.load_table(v)                       # 읽기만 — 바뀐 표는 아래 mem 에만 둔다
    mem, detail_vid = {}, v["version_id"]

    def load(vid):
        return mem[vid] if vid in mem else engine._load_version(vid)

    with tempfile.TemporaryDirectory(prefix="jr_preview_") as tmp:   # N02 · N05 파일은 임시 폴더에 쓰고 읽은 뒤 지운다
        for n, pid in enumerate(path["steps"], start=1):
            rec = {"n": n, "project_id": pid, "title": titles.get(pid, {}).get("title", pid)}
            out["steps"].append(rec)
            cand = planning.candidates(state).get(pid)
            why = None
            if not cand:
                why = ["이 상태에서는 후보가 아님 — 앞 단계 결과로 조건이 바뀌었거나 이미 한 일"]
            elif not cand["gate"]["executable"]:
                g = cand["gate"]
                why = g["reasons"] or [f"{GATE_KO[k]} 아님" for k in GATE_KO if g.get(k) is not True]
            elif pid not in contracts.IMPL:
                why = ["실행기 없음(명세만)"]
            if why:
                rec.update(status="stopped", reasons=why)
                out["stopped"] = f"{n}단계 {pid} 에서 멈춤 — " + " · ".join(why)
                break
            d = Path(tmp) / f"{n:02d}_{pid}"
            d.mkdir()
            try:
                inputs, _, call = engine.step_call(pid, state, table, detail_vid, load, lambda: profiling.profile_table(table, rules))
                res = call(d)
            except H.HandlerError as e:
                inputs, res = {}, H.StepResult(e.status, checks=e.checks, issues=[str(e)])
            except engine.EngineError as e:
                inputs, res = {}, H.StepResult("failed", issues=[str(e)])
            ok = res.status == "succeeded"
            failed_check = any(c["status"] == "failed" for c in res.checks)
            rec.update(status="failed" if not ok or failed_check else "passed", run_status=res.status, checks=res.checks,
                       issues=res.issues, metrics=res.metrics)
            state["completed_steps"].append({"project_id": pid, "status": res.status, "state": "preview",
                                             "check_status": "failed" if failed_check else ("passed" if res.checks else None)})
            state["checks"] += [{"project_id": pid, "name": c["name"], "status": c["status"]} for c in res.checks]
            if ok and res.new_table:
                detail_vid = f"미리보기-{n}"
                mem[detail_vid], table = res.new_table, res.new_table
                rec["table"] = _head(res.new_table)
                state["dataset_version_id"] = detail_vid
                state["facts"]["columns"], state["facts"]["key_dup_groups"] = engine.column_facts(profiling.profile_table(table, rules))
            if ok and res.aggregate:
                aid = f"미리보기-{n}-집계"
                mem[aid] = res.aggregate
                rec["aggregate"] = res.aggregate
                # 게이트는 실제 실행과 같게 판정한다(메모리 안에서는 실제로 계산된 표) — 화면 문구는 미리보기로만 쓴다
                state["artifacts"].append({"kind": inputs.get("agg_kind_out"), "state": "observed", "version_id": aid})
            if ok and pid in ("N02", "N05"):
                for o in res.outputs:
                    f = d / o["path"]
                    if f.suffix == ".png":
                        rec["chart"] = "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode()
                    elif f.suffix == ".html":
                        rec["html"] = f.read_text(encoding="utf-8")
                state["artifacts"].append({"kind": "chart" if pid == "N02" else "html", "state": "observed", "version_id": None})
            if not ok:
                out["stopped"] = f"{n}단계 {pid} 실행 결과 {res.status} — " + " · ".join(res.issues or ["검사 실패"])
                break
    for pid in path["steps"][len(out["steps"]):]:
        out["steps"].append({"project_id": pid, "title": titles.get(pid, {}).get("title", pid), "status": "skipped"})
    kind = planning.GOALS[state["goal"]["key"]]["artifact"]
    art = next((a for a in reversed(state["artifacts"]) if a["kind"] == kind and a.get("version_id")), None)
    if art:
        out["result"] = {"kind": kind, "table": load(art["version_id"]), "from": "미리보기" if art["version_id"] in mem else "이미 실제로 실행한 결과"}
    return out


def _head(t, n=10):
    return {"columns": t["columns"], "rows": t["rows"][:n], "total": len(t["rows"])}


def _table(t, limit=50):
    e = html.escape
    head = "".join(f"<th>{e(str(c))}</th>" for c in t["columns"])
    body = "".join("<tr>" + "".join(f"<td>{e('' if x is None else (f'{x:,}' if isinstance(x, int) and not isinstance(x, bool) else str(x)))}</td>" for x in r) + "</tr>"
                   for r in t["rows"][:limit])
    more = f"<p class='dim'>앞 {limit}행만 — 전체 {len(t['rows']):,}행</p>" if len(t["rows"]) > limit else ""
    return f"<div class='tw'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>{more}"


def render(r: dict) -> str:
    e = html.escape
    p = r["path"]
    mock = r["provider"] == "mock"
    steps = []
    for s in r["steps"]:
        st = s["status"]
        body = ""
        if s.get("reasons"):
            body += f"<p class='bad'>멈춘 이유: {e(' · '.join(s['reasons']))}</p>"
        for c in s.get("checks") or []:
            body += (f"<div class='ck'>{'✔' if c['status'] == 'passed' else '✘'} {e(c['name'])} "
                     f"<code>{e(json.dumps(c.get('detail'), ensure_ascii=False, default=str)[:220])}</code></div>")
        if s.get("issues"):
            body += f"<p class='bad'>{e(' / '.join(s['issues']))}</p>"
        if s.get("table"):
            t = s["table"]
            body += f"<details><summary>바뀐 상세 표 — 앞 {len(t['rows'])}행 / 전체 {t['total']:,}행</summary>{_table(t)}</details>"
        if s.get("aggregate"):
            body += f"<details><summary>이 단계가 만든 집계표 — {len(s['aggregate']['rows']):,}행(아래 목표 결과 표와 같을 수 있음)</summary>{_table(s['aggregate'])}</details>"
        if s.get("chart"):
            body += f"<img alt='{e(s['project_id'])} 차트(미리보기)' src='{s['chart']}'>"
        if s.get("html"):
            body += f"<iframe title='N05 결과 화면(미리보기)' sandbox='allow-scripts' srcdoc='{e(s['html'], quote=True)}'></iframe>"
        steps.append(f"<li class='st st-{st}'><b>{e(s['project_id'])} · {e(s['title'])}</b> <span class='b b-{st}'>{BADGE[st]}</span>{body}</li>")
    res = r["result"]
    if r["stopped"]:
        summary = f"<p class='bad'><b>{e(r['stopped'])}</b> — 이 순서로는 목표 결과까지 가지 못합니다.</p>"
    elif res:
        summary = "<p class='good'><b>목표 결과 표까지 닿음(미리보기)</b> — 모든 단계가 미리보기에서 통과했습니다.</p>"
    else:
        summary = f"<p>끝: {e(exports.STATUS_KO.get(p['ends_with'], p['ends_with']) or '—')}</p>"
    if res:
        summary += (f"<h2>목표 결과 표 <small>({e(res['from'])} · 기준 버전 {e(r['base_version_id'])} · 기록 안 됨)</small></h2>" + _table(res["table"]))
        t = res["table"]
        for i, c in enumerate(t["columns"]):
            vals = [row[i] for row in t["rows"] if str(row[0]) != "전체"]
            if str(c).startswith(("sum_", "count")) and vals and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in vals):
                summary += f"<p><b>{e(str(c))} 전체 = {sum(vals):,}</b> <small>(위 {len(vals)}개 그룹을 더한 값 · 미리보기 측정)</small></p>"
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>경로 결과 미리보기</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--dim:#666;--line:#ddd;--warn:#fff3cd;--ok:#0a7a45;--bad:#b42318;--note:#eef3ff}}
@media(prefers-color-scheme:dark){{:root{{--bg:#16181c;--fg:#e8e8e8;--dim:#9aa0a6;--line:#333;--warn:#3a3000;--ok:#4cc38a;--bad:#ff8a80;--note:#1d2433}}}}
body{{font-family:"Malgun Gothic",system-ui,sans-serif;margin:0;padding:16px;background:var(--bg);color:var(--fg);line-height:1.55;overflow-wrap:anywhere;max-width:1100px}}
.band{{background:var(--warn);padding:.5rem .8rem;border-radius:6px;font-weight:700}} .note{{background:var(--note);padding:.6rem .8rem;border-radius:6px}}
table{{border-collapse:collapse;font-size:.9rem}} th,td{{border:1px solid var(--line);padding:.3rem .5rem;text-align:left}} .tw{{overflow-x:auto;margin:.4rem 0}}
.dim,small{{color:var(--dim)}} .bad{{color:var(--bad)}} .good{{color:var(--ok)}} code{{font-size:.8rem;color:var(--dim)}}
ol{{padding-left:1.3rem}} .st{{margin:.6rem 0;padding:.5rem .7rem;border:1px solid var(--line);border-radius:8px}} .st-skipped{{opacity:.6;border-style:dashed}}
.b{{font-size:.8rem;border:1px dashed var(--line);border-radius:8px;padding:0 .4rem}} .b-passed{{color:var(--ok)}} .b-failed,.b-stopped{{color:var(--bad)}}
img{{max-width:100%;height:auto;margin:.4rem 0}} iframe{{width:100%;height:420px;border:1px solid var(--line);border-radius:6px;background:#fff}} .ck{{font-size:.9rem}}
</style></head><body>
<p class="band">{'모의 판단(MOCK) — 경로를 고른 판단은 로컬 규칙이며 실제 Jev 판단이 아닙니다' if mock else 'LIVE(OpenAI Codex) 판단으로 만든 경로 — 1=선택, 0=대안(확률 아님)' if r['provider'] == 'codex' else 'LIVE(OpenAI Decisions API) 판단으로 만든 경로' if r['provider'] == 'openai' else 'LIVE(TypeSafe Jev) 판단으로 만든 경로'}</p>
<h1>경로 결과 미리보기 — {e(r['goal']['label'])}</h1>
<p class="note"><b>미리보기</b> — 현재 데이터 버전 <code>{e(r['base_version_id'])}</code> 의 복사본에서 이 순서대로 실행기를 돌려 본 결과입니다.
실행 이력 · 데이터 버전 · 재계획에 남지 않았습니다(원본은 읽기만 함). 앱에서 한 단계씩 실행하면 단계마다 다시 판단하므로 다른 길로 갈 수 있습니다.
숫자는 모두 「미리보기 측정(기록 안 됨)」입니다.</p>
<p>경로 #{p.get('rank', '?')} <b>{e(' → '.join(p['steps']) or '(바로 멈춤)')}</b> · 경로 추천 점수 {p['score']:.3f} <small>({'선택 지시자 집계 — 성공확률 아님' if r['provider'] == 'codex' else '각 단계 선택지 확률의 기하평균 — 성공확률 아님'})</small> · 계획 <code>{e(r['plan_id'])}</code></p>
<h2>단계</h2><ol>{''.join(steps) or '<li>실행할 단계가 없는 경로입니다</li>'}</ol>
{summary}
<h2>다른 경로 미리보기</h2><ul>{''.join(f"<li>{'<b>' if o['leaf'] == r['leaf'] else ''}<a href='/api/plans/{e(r['plan_id'])}/paths/{e(o['leaf'])}/preview'>#{o['rank']} {e(' → '.join(o['steps']) or '(바로 멈춤)')}</a>{'</b> ← 지금' if o['leaf'] == r['leaf'] else ''} <small>{'목표까지 닿는 경로' if o['complete'] else '부분 경로'}</small></li>" for o in r['others'])}</ul>
</body></html>"""
