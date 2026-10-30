"""Enumerate supported workflows and run a selected workflow on in-memory data."""
from itertools import permutations

PAGE_SIZE = 20
NAMES = {"A02": "엑셀 첫 시트 읽기", "A03": "CSV 읽기", "C03": "숫자 해석",
         "D01": "필수 열 확인", "D02": "그룹 결측 확인", "I01": "그룹별 집계", "N02": "결과 시각화"}


def paths(goal: str, source: str) -> list[dict]:
    if goal not in ("sum", "count") or source not in ("csv", "xlsx"):
        raise ValueError("지원하는 목표와 파일 형식을 선택해 주세요.")
    first = "A02" if source == "xlsx" else "A03"
    optional = ("D01", "D02")
    before = []
    for mask in range(4):
        selected = [p for i, p in enumerate(optional) if mask & (1 << i)]
        if goal == "sum":
            selected.append("C03")
        before.extend(permutations(selected))
    out = []
    for check_order in before:
        for chart in (False, True):
            steps = [first, *check_order, "I01", *(["N02"] if chart else [])]
            out.append({"id": "-".join(steps), "steps": steps, "names": [NAMES[p] for p in steps],
                        "chart": chart, "score": None})
    return sorted(out, key=lambda p: (len(p["steps"]), p["id"]))


def list_paths(goal: str, source: str, page: int = 1) -> dict:
    if page < 1:
        raise ValueError("페이지는 1 이상이어야 합니다.")
    all_paths = paths(goal, source)
    start = (page - 1) * PAGE_SIZE
    return {"paths": all_paths[start:start + PAGE_SIZE], "total": len(all_paths), "page": page,
            "page_size": PAGE_SIZE, "scope": "현재 구현된 읽기·검사·숫자 해석·집계·차트 작업만 탐색했습니다.",
            "score_note": "작업 수 순서로 정렬했습니다. 모델 경로 점수는 계산하지 않았습니다."}


def preview(raw: bytes, goal: str, group: str, value: str, source: str, path_id: str) -> dict:
    from backend.app import _is_amount, execute, make_plan, parse_csv

    candidate = next((p for p in paths(goal, source) if p["id"] == path_id), None)
    if candidate is None:
        raise ValueError("현재 데이터와 목표에서 허용된 경로가 아닙니다.")
    plan = make_plan(raw, goal, group, value, source)
    columns, rows = parse_csv(raw)
    results, aggregate, stopped = [], None, None
    for pid in candidate["steps"]:
        status, detail = "passed", ""
        if pid in ("A02", "A03"):
            detail = f"{len(rows):,}행 · {len(columns):,}열 읽음"
        elif pid == "D01":
            detail = "선택한 필수 열이 존재합니다."
        elif pid == "D02":
            count = sum(not row[group].strip() for row in rows)
            detail = f"그룹 값이 빈 행 {count:,}건"
            status = "passed" if count == 0 else "stopped"
        elif pid == "C03":
            bad = sum(not _is_amount(row[value]) for row in rows)
            detail = f"숫자로 해석하지 못한 값 {bad:,}건"
            status = "passed" if bad == 0 else "stopped"
        elif pid == "I01":
            try:
                aggregate = execute(raw, goal, group, value, source)
                status = "passed" if aggregate["verified"] else "stopped"
                detail = aggregate["check"] if aggregate["verified"] else "원본과 집계가 일치하지 않습니다."
            except ValueError as exc:
                status, detail = "stopped", str(exc)
        elif pid == "N02":
            status = "passed" if aggregate else "stopped"
            detail = "실제 집계값으로 결과 차트를 표시합니다." if aggregate else "먼저 집계 결과가 필요합니다."
        results.append({"id": pid, "name": NAMES[pid], "status": status, "detail": detail})
        if status != "passed":
            stopped = f"{pid}: {detail}"
            break
    return {"path": candidate, "steps": results, "stopped": stopped, "result": aggregate,
            "note": "입력 데이터 사본을 메모리에서 처리했으며 원본과 실행 이력을 변경하지 않았습니다.",
            "executable": plan["executable"]}
