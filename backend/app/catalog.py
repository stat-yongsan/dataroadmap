"""플레이북 원문 → 작업 카탈로그(원문 §5). 원문은 읽기만 한다.

  python -m app.catalog build   → catalog/projects.json · index.json · cards/<ID>.md 생성 + 점검 보고

원문에서 기계적으로 뽑은 필드(source)만 여기서 만든다. 실행기·사전조건 같은 구현 메타는 contracts.py 에 따로 둔다.
"""
import hashlib
import json
import re
import sys

from . import settings

FIELD_KEYS = {
    "입력 예제": "input_example",
    "변환·출력 계약": "transformation_output_contract",
    "성공 기준": "success_criteria",
    "실패·경계 실험": "failure_boundary_experiment",
}
W_KEYS = {"입력": "input", "연결": "link_text", "계약": "contract", "정답": "expected", "실패 실험": "failure_experiment"}
AREA_RE = re.compile(r"^### ([A-Q])\. (.+?) — (\d+)개\s*$")
CARD_RE = re.compile(r"^#### ([A-Q]\d{2}) · (.+?)\s*$")
TABLE_RE = re.compile(r"^\| ([A-Q]\d{2}) \| (.+?) \| (\S+) \|$")
ENV_RE = re.compile(r"^\*\*환경: (\S+) — (.+?)\*\*$")
BULLET_RE = re.compile(r"^- \*\*(.+?):\*\* ?(.*)$")          # 카드: - **입력 예제:** …
W_BULLET_RE = re.compile(r"^- (입력|연결|계약|정답|실패 실험): ?(.*)$")   # W: - 입력: … (굵은 글씨 없음)
W_RE = re.compile(r"^### (W\d{2})\. (.+?)\s*$")


def parse(text: str) -> dict:
    lines = text.splitlines()
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    areas, projects, workflows, table_titles = [], [], [], {}
    cur_area = cur = None
    in_map = in_w = False

    def close(end):
        nonlocal cur
        if cur is not None:
            while end > cur["source_start_line"] and not lines[end - 1].strip():
                end -= 1
            cur["source_end_line"] = end
            cur = None

    for i, line in enumerate(lines, start=1):
        if line.startswith("## "):
            close(i - 1)
            in_map = line.startswith("## 7.")
            in_w = line.startswith("## 8.")
            continue
        if in_map and (m := AREA_RE.match(line)):
            close(i - 1)
            cur_area = {"id": m[1], "name": m[2], "declared_count": int(m[3]), "question": ""}
            areas.append(cur_area)
            continue
        if in_map and cur_area and not cur_area["question"] and line.strip() and not line.startswith(("|", "#")):
            cur_area["question"] = line.strip()
        if in_map and (m := TABLE_RE.match(line)):
            table_titles[m[1]] = (m[2], m[3])
            continue
        if in_map and (m := CARD_RE.match(line)):
            close(i - 1)
            cur = {"project_id": m[1], "area_id": m[1][0], "title": m[2], "environment": None,
                   "environment_label": None, **{v: None for v in FIELD_KEYS.values()},
                   "source_heading": line, "source_start_line": i, "source_end_line": None, "source_sha256": sha}
            projects.append(cur)
            continue
        if in_w and (m := W_RE.match(line)):
            close(i - 1)
            cur = {"workflow_id": m[1], "title": m[2], **{v: None for v in W_KEYS.values()},
                   "mentioned_projects": [], "source_heading": line, "source_start_line": i,
                   "source_end_line": None, "source_sha256": sha}
            workflows.append(cur)
            continue
        if cur is None:
            continue
        if "project_id" in cur and (m := ENV_RE.match(line)):
            cur["environment"], cur["environment_label"] = m[1], m[2]
        elif m := (BULLET_RE.match(line) if "project_id" in cur else W_BULLET_RE.match(line)):
            keys = FIELD_KEYS if "project_id" in cur else W_KEYS
            if m[1] in keys:
                cur[keys[m[1]]] = m[2]
                if m[1] == "연결":
                    # 화살표 전체를 단일 파일 전달 체인으로 해석하지 않는다(원문 §5) — 언급된 번호만 순서대로 둔다.
                    seen = dict.fromkeys(re.findall(r"(?<![A-Za-z0-9])[A-Q]\d{2}(?!\d)", m[2]))   # 「N03으로」처럼 조사가 붙어도 잡는다
                    cur["mentioned_projects"] = list(seen)
    close(len(lines))
    return {"sha256": sha, "lines": len(lines), "areas": areas, "projects": projects,
            "workflows": workflows, "table_titles": table_titles}


def verify(cat: dict, legacy: list | None) -> dict:
    """A1 점검 — 영역 17 · 카드 153 · W01~W20 · ID 중복·누락 · 제목 일치."""
    issues = []
    ids = [p["project_id"] for p in cat["projects"]]
    dup = sorted({x for x in ids if ids.count(x) > 1})
    if dup:
        issues.append(f"중복 ID: {dup}")
    for a in cat["areas"]:
        mine = [x for x in ids if x[0] == a["id"]]
        want = [f"{a['id']}{n:02d}" for n in range(1, a["declared_count"] + 1)]
        if mine != want:
            issues.append(f"{a['id']} 영역: 선언 {a['declared_count']}개와 카드 번호 불일치 {sorted(set(want) ^ set(mine))}")
    for p in cat["projects"]:
        t = cat["table_titles"].get(p["project_id"])
        if not t or t[0] != p["title"] or t[1] != p["environment"]:
            issues.append(f"{p['project_id']}: 영역 표와 카드 제목·환경 불일치")
        missing = [k for k in FIELD_KEYS.values() if not p[k]] + ([] if p["environment"] else ["environment"])
        if missing:
            issues.append(f"{p['project_id']}: 원문 필드 없음 {missing}")
    wids = [w["workflow_id"] for w in cat["workflows"]]
    for w in cat["workflows"]:
        missing = [k for k in ("input", "link_text", "contract", "expected", "failure_experiment") if not w[k]]
        if missing or not w["mentioned_projects"]:
            issues.append(f"{w['workflow_id']}: 원문 필드 없음 {missing or ['mentioned_projects']}")
    if wids != [f"W{n:02d}" for n in range(1, 21)]:
        issues.append(f"W01~W20 불일치: {wids}")
    legacy_diff = None
    if legacy is not None:
        lt = {x["id"]: x["title"] for x in legacy}
        legacy_diff = sorted(k for k in set(lt) | set(ids) if lt.get(k) != next((p["title"] for p in cat["projects"] if p["project_id"] == k), None))
        if legacy_diff:
            issues.append(f"기존 project_catalog.json 과 제목 다름: {legacy_diff}")
    return {
        "areas": len(cat["areas"]), "projects": len(ids), "workflows": len(wids),
        "per_area": {a["id"]: len([x for x in ids if x[0] == a["id"]]) for a in cat["areas"]},
        "matches_spec_hash": cat["sha256"] == settings.SPEC_PLAYBOOK_SHA256,
        "legacy_compared": legacy is not None, "legacy_title_mismatch": legacy_diff,
        "ok": not issues and len(cat["areas"]) == 17 and len(ids) == 153, "issues": issues,
    }


def build(playbook=settings.PLAYBOOK, out=settings.CATALOG_DIR) -> dict:
    text = playbook.read_text(encoding="utf-8")
    cat = parse(text)
    legacy = None
    if settings.LEGACY_CATALOG.is_file():
        legacy = json.loads(settings.LEGACY_CATALOG.read_text(encoding="utf-8"))["projects"]
    report = verify(cat, legacy)
    version = "playbook-" + cat["sha256"][:12]
    (out / "cards").mkdir(parents=True, exist_ok=True)
    lines = text.splitlines()
    for p in cat["projects"] + cat["workflows"]:
        pid = p.get("project_id") or p["workflow_id"]
        body = "\n".join(lines[p["source_start_line"] - 1:p["source_end_line"]])
        (out / "cards" / f"{pid}.md").write_text(
            f"<!-- 원문 {playbook.name} {p['source_start_line']}~{p['source_end_line']}행 · sha256 {cat['sha256']} · 생성물 -->\n{body}\n",
            encoding="utf-8")
    source = {"path": str(playbook), "sha256": cat["sha256"], "lines": cat["lines"],
              "spec_sha256": settings.SPEC_PLAYBOOK_SHA256}
    doc = {"catalog_version": version, "source": source, "areas": cat["areas"],
           "projects": cat["projects"], "workflows": cat["workflows"], "verify": report}
    (out / "projects.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    index = {"catalog_version": version, "source": source, "counts": report["per_area"],
             "projects": [{k: p[k] for k in ("project_id", "area_id", "title", "environment")} for p in cat["projects"]],
             "workflows": [{"workflow_id": w["workflow_id"], "title": w["title"]} for w in cat["workflows"]]}
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


_cache: dict = {}


def load() -> dict:
    """생성된 카탈로그를 읽는다(없으면 만든다). 원문 해시가 바뀌었으면 새 버전으로 다시 만든다."""
    f = settings.CATALOG_DIR / "projects.json"
    if not _cache:
        doc = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else build()
        if settings.PLAYBOOK.is_file():
            now = hashlib.sha256(settings.PLAYBOOK.read_bytes()).hexdigest()
            if now != doc["source"]["sha256"]:
                doc = build()
        _cache.update(doc)
        _cache["by_id"] = {p["project_id"]: p for p in doc["projects"]}
    return _cache


if __name__ == "__main__":
    if sys.argv[1:] == ["build"]:
        d = build()
        print(json.dumps({"catalog_version": d["catalog_version"], **d["verify"]}, ensure_ascii=False, indent=1))
        sys.exit(0 if d["verify"]["ok"] else 1)
    print(__doc__)
