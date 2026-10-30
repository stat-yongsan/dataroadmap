"""실행기 12개(원문 §11): A02 A03 C01 C03 C05 D01 D03 I01 I02 H01 N02 N05.

각 실행기는 카드의 입력·출력·성공·실패 실험을 따른다. 입력 표를 고치지 않고, 바뀐 데이터는 새 표로 돌려준다
(엔진이 새 dataset_version 으로 저장). 검증은 표를 바꾸지 않고 check 로 따로 돌려준다(원문 §2).
status = succeeded | failed | blocked | needs_review | skipped (플레이북 step_result.v1)
"""
import csv
import html
import json
import re
import warnings
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import profiling, settings

VERSION = "handlers.v1"
FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r")
CSV_ESCAPE_POLICY = "문자열 칸이 = + - @ 탭 CR 로 시작하면 앞에 ' 를 붙인다(스프레드시트 수식 주입 방지). 숫자 칸은 그대로."


class HandlerError(Exception):
    def __init__(self, message, status="failed", checks=None):
        super().__init__(message)
        self.status, self.checks = status, checks or []


@dataclass
class StepResult:
    status: str
    new_table: dict | None = None          # 상세 표가 바뀌면 새 버전
    aggregate: dict | None = None          # 다른 grain 의 결과 표(집계 · 비율)
    checks: list = field(default_factory=list)
    outputs: list = field(default_factory=list)   # 사용자에게 보이는 파일 [{name, kind, path}]
    metrics: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    provenance: dict = field(default_factory=dict)


def _idx(table, col):
    if col not in table["columns"]:
        raise HandlerError(f"열 '{col}' 이(가) 없습니다", status="failed")
    return table["columns"].index(col)


def _check(name, status, **detail):
    return {"name": name, "status": status, "detail": detail}


def write_csv_safe(path: Path, columns, rows):
    def esc(v):
        if v is None:
            return ""
        if isinstance(v, str) and v.startswith(FORMULA_PREFIX):
            return "'" + v
        return v
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([esc(c) for c in columns])
        w.writerows([[esc(v) for v in r] for r in rows])


def _table_out(run_dir: Path, name, table, kind="table"):
    p = run_dir / f"{name}.csv"
    write_csv_safe(p, table["columns"], table["rows"])
    (run_dir / f"{name}.schema.json").write_text(json.dumps(table.get("schema", {}), ensure_ascii=False, indent=1), encoding="utf-8")
    return {"name": name, "kind": kind, "path": p.name, "grain": table.get("schema", {}).get("grain")}


def _schema(table, **over):
    s = dict(table.get("schema") or {})
    s["types"] = dict(s.get("types") or {})
    s.update(over)
    return s


# ---------------- A03 CSV·TSV 인코딩 읽기 ----------------
def a03_read_text(raw: bytes, filename: str, encoding=None, delimiter=None, grain=None) -> StepResult:
    det = profiling.detect_encoding(raw)
    enc = encoding or (det["encoding"] if det["status"] == "confirmed" else None)
    if not enc:
        raise HandlerError(f"인코딩을 확정할 수 없습니다({det['reason']}). 선택지: {det['choices']}", status="needs_review")
    try:
        text = raw.decode(enc)
    except (UnicodeDecodeError, LookupError) as e:
        raise HandlerError(f"지정한 인코딩 {enc} 로 해석할 수 없습니다: {e}") from e
    delim = delimiter or profiling.detect_delimiter(filename, text)
    try:
        rows = profiling.csv_rows(text, delim)
    except profiling.InspectError as e:
        raise HandlerError(str(e)) from e
    if not rows:
        raise HandlerError("빈 파일입니다 — 빈 표로 성공 처리하지 않습니다")
    header, data = [h.strip() for h in rows[0]], rows[1:]
    dup = sorted({h for h in header if header.count(h) > 1})
    if dup or any(not h for h in header):
        raise HandlerError(f"머리글이 비었거나 중복입니다: {dup or '빈 머리글'}")
    bad = [i + 2 for i, r in enumerate(data) if len(r) != len(header)]
    if bad:
        raise HandlerError(f"칸 수가 머리글({len(header)})과 다른 행: {bad[:10]} — 조용히 채우지 않습니다")
    table = {"columns": header, "rows": data,
             "schema": {"grain": grain, "types": {h: "string" for h in header},
                        "source": {"encoding": enc, "encoding_status": "confirmed" if encoding else det["status"], "delimiter": delim}}}
    return StepResult("succeeded", new_table=table, metrics={"rows": len(data), "columns": len(header)},
                      checks=[_check("text_table_parsed", "passed", encoding=enc, delimiter=repr(delim), rows=len(data))])


# ---------------- A02 엑셀 범위를 표로 읽기 ----------------
def a02_read_range(path, sheet=None, header_row=None, cell_range=None, last_row=None, grain=None) -> StepResult:
    import openpyxl
    from openpyxl.utils.cell import range_boundaries, get_column_letter

    wb_v = openpyxl.load_workbook(path, data_only=True)    # 저장된 계산값
    wb_f = openpyxl.load_workbook(path, data_only=False)   # 수식 여부
    name = sheet or wb_v.worksheets[0].title
    if name not in wb_v.sheetnames:
        raise HandlerError(f"시트 '{name}' 를 찾지 못했습니다(시트: {wb_v.sheetnames}) — 빈 표로 성공 처리하지 않습니다")
    ws, wf = wb_v[name], wb_f[name]
    if cell_range:
        try:
            c1, r1, c2, r2 = range_boundaries(cell_range)
        except ValueError as e:
            raise HandlerError(f"범위 '{cell_range}' 를 해석하지 못했습니다") from e
    else:
        r1 = int(header_row or 1)
        hdr = [c.value for c in ws[r1]]
        filled = [i for i, v in enumerate(hdr, start=1) if v not in (None, "")]
        if not filled:
            raise HandlerError(f"{r1}행에 머리글이 없습니다 — 대상을 찾지 못했습니다")
        c1, c2 = filled[0], filled[-1]
        r2 = int(last_row) if last_row else ws.max_row
    header = [profiling._cell_text(ws.cell(r1, c).value) for c in range(c1, c2 + 1)]
    if not all(header):
        raise HandlerError(f"머리글 칸이 비어 있습니다: {header}")
    rows, cells, uncached = [], [], {}
    for r in range(r1 + 1, r2 + 1):
        vals = []
        for j, c in enumerate(range(c1, c2 + 1)):
            v = ws.cell(r, c).value
            if wf.cell(r, c).data_type == "f" and v is None:
                uncached[header[j]] = uncached.get(header[j], 0) + 1   # 수식 있음 · 재계산 안 됨 — 빈칸이나 0 으로 세지 않는다
            if hasattr(v, "isoformat"):
                v = v.isoformat()[:10] if getattr(v, "hour", 0) == 0 and getattr(v, "minute", 0) == 0 else v.isoformat()
            vals.append(v)
        if all(v in (None, "") for v in vals) and not cell_range:
            break
        rows.append(vals)
        cells.append(f"{get_column_letter(c1)}{r}")
    if not rows:
        raise HandlerError(f"'{name}' 의 지정 범위에 데이터 행이 없습니다 — 대상을 찾지 못했습니다")
    types = {h: ("number_cells" if any(isinstance(r[i], (int, float)) for r in rows) else "string") for i, h in enumerate(header)}
    rng = f"{get_column_letter(c1)}{r1}:{get_column_letter(c2)}{r1 + len(rows)}"
    table = {"columns": header, "rows": rows,
             "schema": {"grain": grain, "types": types, "source": {"sheet": name, "range": rng, "header_row": r1}}}
    issues = [f"수식 칸 {n}개({h})는 저장된 계산값이 없어 값 없음으로 둠 — 재계산 안 됨" for h, n in uncached.items()]
    return StepResult("succeeded", new_table=table, metrics={"rows": len(rows), "columns": len(header), "range": rng},
                      checks=[_check("excel_range_read", "passed", sheet=name, range=rng, rows=len(rows))],
                      issues=issues, provenance={"first_cell_of_row": cells, "formula_uncached": uncached})


# ---------------- C01 열 이름 표준화 ----------------
def c01_rename(table, aliases: dict) -> StepResult:
    if not aliases:
        raise HandlerError("별칭 사전이 없습니다", status="needs_review")
    targets = {}
    for c in table["columns"]:
        t = aliases.get(c, c)
        targets.setdefault(t, []).append(c)
    conflict = {t: src for t, src in targets.items() if len(src) > 1}
    if conflict:
        raise HandlerError(f"여러 열이 같은 이름으로 바뀝니다: {conflict}", checks=[_check("alias_conflict", "failed", conflict=conflict)])
    cols = [aliases.get(c, c) for c in table["columns"]]
    s = _schema(table)
    s["types"] = {aliases.get(k, k): v for k, v in s["types"].items()}
    s["renamed"] = {c: aliases[c] for c in table["columns"] if c in aliases}
    return StepResult("succeeded", new_table={"columns": cols, "rows": table["rows"], "schema": s},
                      checks=[_check("columns_standardized", "passed", columns=cols, renamed=s["renamed"])])


# ---------------- C03 문자 숫자·백분율 해석 ----------------
NUM_RE = re.compile(r"^[+-]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")


def parse_number(v, rule: dict):
    """(값, 결과종류) — 결과종류 = number | null | error. 명시한 구문만 허용한다(범용 파서 아님)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v, "number"
    s = "" if v is None else str(v).strip()
    if s == "":
        return None, "null"                      # 빈칸은 0 이 아니라 null
    neg = False
    if rule.get("paren_negative", True) and s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1].strip()
    pct = False
    if rule.get("percent", True) and s.endswith("%"):
        pct, s = True, s[:-1].strip()
    for suf in rule.get("suffixes", ["원", "₩", "KRW"]):
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
    if not NUM_RE.match(s):
        return str(v), "error"                   # 「미상」 같은 값을 0 으로 바꾸지 않는다
    try:
        d = Decimal(s.replace(",", ""))
    except InvalidOperation:
        return str(v), "error"
    if neg:
        d = -d
    if pct:
        return float(d / 100), "number"          # 25% → 0.25 (25 로 저장하지 않는다)
    return (int(d) if d == d.to_integral_value() else float(d)), "number"


def c03_parse(table, column, rule=None) -> StepResult:
    rule = rule or {}
    i = _idx(table, column)
    out_rows, errors, counts = [], [], {"number": 0, "null": 0, "error": 0}
    for n, r in enumerate(table["rows"], start=2):
        val, kind = parse_number(r[i], rule)
        counts[kind] += 1
        if kind == "error":
            errors.append({"row": n, "value": r[i]})
        out_rows.append(r[:i] + [val] + r[i + 1:])
    chk = _check("numeric_parse", "passed" if not errors else "failed", column=column, counts=counts, errors=errors[:50])
    if errors:
        # 실패·검토 필요 시 성공한 데이터 버전을 갱신하지 않는다(원문 §7)
        return StepResult("needs_review", checks=[chk], metrics=counts,
                          issues=[f"{column}: 해석할 수 없는 값 {len(errors)}개 — 규칙을 정하거나 원본을 고쳐야 합니다"])
    nums = [r[i] for r in out_rows if r[i] is not None]
    s = _schema(table)
    s["types"][column] = "integer" if all(isinstance(x, int) for x in nums) else "decimal"
    s.setdefault("parse_rules", {})[column] = rule or {"desc": "기본 규칙(쉼표 · 괄호 음수 · % · 원 접미사)"}
    return StepResult("succeeded", new_table={"columns": table["columns"], "rows": out_rows, "schema": s},
                      checks=[chk], metrics=counts)


# ---------------- C05 식별자의 앞자리 0 보존 ----------------
def c05_identifiers(table, columns) -> StepResult:
    checks, bad = [], []
    for col in columns:
        i = _idx(table, col)
        vals = [r[i] for r in table["rows"]]
        numeric = [n for n, v in enumerate(vals, start=2) if isinstance(v, (int, float)) and not isinstance(v, bool)]
        strs = [v for v in vals if isinstance(v, str) and v.strip()]
        lengths = sorted({len(v.strip()) for v in strs})
        status = "failed" if numeric else "passed"
        if numeric:
            bad.append(col)
        checks.append(_check("identifier_preserved", status, column=col, numeric_cells_rows=numeric[:20],
                             leading_zero_values=sum(1 for v in strs if v.strip().isdigit() and v.strip().startswith("0") and len(v.strip()) > 1),
                             long_codes=[v for v in strs if v.strip().isdigit() and len(v.strip()) >= 16][:5],
                             lengths=lengths,
                             note=("이미 숫자로 저장된 칸 — 복구한 척하지 않는다. 원본을 다시 확인해야 한다" if numeric else "모든 값이 문자열로 유지됨")))
    if bad:
        return StepResult("needs_review", checks=checks, issues=[f"{c}: 숫자로 저장된 식별자 — 원본 재확인 요청" for c in bad])
    return StepResult("succeeded", checks=checks)


# ---------------- D01 스키마·자료형 검사 ----------------
def d01_schema(table, required: dict, optional=(), allow_extra=True, profile=None) -> StepResult:
    prof = {c["name"]: c for c in (profile or profiling.profile_table(table))["columns"]}
    errors, warns, notes = [], [], []
    for col, want in required.items():
        if col not in table["columns"]:
            errors.append({"code": "missing_column", "column": col, "expected": want})
            continue
        kind = prof[col]["kind"]
        ok = {"string": kind not in ("integer", "decimal") or not prof[col]["identifier"],
              "identifier": not prof[col]["identifier_damage_possible"],
              "number": kind in ("integer", "decimal"),
              "number_or_text": kind in ("integer", "decimal", "number_text", "integer_text", "percent_text", "mixed_numeric"),
              "decimal": kind in ("integer", "decimal"),
              "any": True}.get(want, True)
        if not ok:
            errors.append({"code": "type_mismatch", "column": col, "expected": want, "found": kind})
        elif want == "number_or_text" and kind not in ("integer", "decimal"):
            notes.append(f"{col}: 문자 숫자({kind}) — 합계 전에 C03 변환 필요")
    for col in optional:
        if col not in table["columns"]:
            warns.append({"code": "missing_optional_column", "column": col})   # 필수 열 누락과 구분
    extra = [c for c in table["columns"] if c not in required and c not in optional]
    if extra and not allow_extra:
        errors.append({"code": "unexpected_columns", "columns": extra})
    st = "failed" if errors else "passed"
    return StepResult("succeeded", checks=[_check("schema", st, errors=errors, warnings=warns, notes=notes, extra_columns=extra)],
                      metrics={"errors": len(errors), "warnings": len(warns)})


# ---------------- D03 중복 키 검출 ----------------
def d03_duplicates(table, key: list) -> StepResult:
    ix = [_idx(table, k) for k in key]
    groups = {}
    for n, r in enumerate(table["rows"], start=2):
        groups.setdefault(tuple(str(r[i]) for i in ix), []).append((n, r))
    dups = []
    for k, items in groups.items():
        if len(items) > 1:
            exact = len({json.dumps(r, ensure_ascii=False, default=str) for _, r in items}) == 1
            dups.append({"key": list(k), "rows": [{"row": n, "values": r} for n, r in items],
                         "kind": "완전히 같은 행" if exact else "같은 키 · 값이 다른 행"})
    # 검출만 한다. 삭제·해소는 E04(정책 필요)의 일이다.
    return StepResult("succeeded", checks=[_check("duplicate_keys", "passed" if not dups else "failed", key=key,
                                                  groups=len(dups), rows=sum(len(d["rows"]) for d in dups), duplicates=dups[:50])],
                      metrics={"groups": len(dups), "rows": sum(len(d["rows"]) for d in dups)})


# ---------------- I01 그룹별 기본 집계 ----------------
def i01_aggregate(table, group_by: list, measures: list, declared_groups: dict | None = None) -> StepResult:
    if not group_by:   # 그룹 없이 전체 1행 — 라벨 열 「구분」=전체
        table = {**table, "columns": table["columns"] + ["구분"], "rows": [r + ["전체"] for r in table["rows"]]}
        group_by = ["구분"]
    gi = [_idx(table, g) for g in group_by]
    ms = []
    for m in measures:
        if m["op"] in ("sum", "mean"):
            ci = _idx(table, m["col"])
            vals = [r[ci] for r in table["rows"]]
            nonnum = [v for v in vals if v is not None and not (isinstance(v, (int, float)) and not isinstance(v, bool))]
            if nonnum:
                raise HandlerError(f"'{m['col']}' 에 숫자가 아닌 값 {len(nonnum)}개({nonnum[:3]}) — C03 변환이 먼저입니다", status="blocked")
            if any(v is None for v in vals):
                raise HandlerError(f"'{m['col']}' 에 빈 값 {sum(v is None for v in vals)}개 — 빼고 합산할지 정책이 없습니다", status="needs_review")
            ms.append((m, ci))
        else:
            ms.append((m, None))
    sum_cols = {m["col"]: ci for m, ci in ms if ci is not None}   # 합계·평균이 같은 열을 써도 한 번만 더한다
    acc = {}
    for r in table["rows"]:
        k = tuple("" if r[i] is None else str(r[i]) for i in gi)
        a = acc.setdefault(k, {"count": 0, "sum": {}})
        a["count"] += 1
        for col, ci in sum_cols.items():
            a["sum"][col] = a["sum"].get(col, 0) + r[ci]
    empty_groups = []
    if declared_groups and len(group_by) >= 1 and group_by[0] in declared_groups:
        seen_first = {k[0] for k in acc}
        for g in declared_groups[group_by[0]]:
            if g not in seen_first:
                empty_groups.append(g)   # 관측 0 이 아니라 「행이 하나도 없는 선언된 그룹」
    cols = list(group_by) + ["observed"]
    for m, _ in ms:
        cols.append("count" if m["op"] == "count" else f"{m['op']}_{m['col']}")
    rows = []
    for k in sorted(acc):
        a = acc[k]
        row = list(k) + [True]
        for m, _ in ms:
            if m["op"] == "count":
                row.append(a["count"])
            elif m["op"] == "sum":
                row.append(a["sum"][m["col"]])
            else:
                row.append(a["sum"][m["col"]] / a["count"])
        rows.append(row)
    for g in empty_groups:
        rows.append([g] + [None] * (len(group_by) - 1) + [False] + [0 if m["op"] == "count" else None for m, _ in ms])
    checks = [_check("rows_preserved", "passed" if sum(a["count"] for a in acc.values()) == len(table["rows"]) else "failed",
                     input_rows=len(table["rows"]), aggregated_rows=sum(a["count"] for a in acc.values()))]
    for m, ci in ms:
        if m["op"] == "sum":
            total_in = sum(r[ci] for r in table["rows"])
            total_out = sum(a["sum"][m["col"]] for a in acc.values())
            checks.append(_check("sum_invariant", "passed" if total_in == total_out else "failed", column=m["col"], input_total=total_in, output_total=total_out))
    if empty_groups:
        checks.append(_check("empty_groups_marked", "passed", groups=empty_groups, note="선언된 그룹 중 행이 없는 그룹 — 관측값 0 과 구분(observed=false)"))
    grain = " × ".join(group_by) + " 1개"
    agg = {"columns": cols, "rows": rows, "schema": {"grain": grain, "group_by": group_by, "measures": measures,
                                                     "types": {c: "string" for c in group_by}}}
    return StepResult("succeeded", aggregate=agg, checks=checks, metrics={"groups": len(rows)})


# ---------------- I02 중복을 제외한 대상 수 ----------------
def i02_distinct(table, entity: list, group_by: list | None = None) -> StepResult:
    if not group_by:
        table = {**table, "columns": table["columns"] + ["구분"], "rows": [r + ["전체"] for r in table["rows"]]}
        group_by = ["구분"]
    ei = [_idx(table, e) for e in entity]
    gi = [_idx(table, g) for g in (group_by or [])]
    acc, blank = {}, 0
    for r in table["rows"]:
        k = tuple("" if r[i] is None else str(r[i]).strip() for i in ei)
        if any(x == "" for x in k):
            blank += 1                                 # 빈 키를 사람 1명으로 세지 않는다
            continue
        g = tuple(str(r[i]) for i in gi)
        a = acc.setdefault(g, {"rows": 0, "keys": set()})
        a["rows"] += 1
        a["keys"].add(k)
    cols = list(group_by or []) + ["valid_rows", "distinct_entities"]
    rows = [list(g) + [a["rows"], len(a["keys"])] for g, a in sorted(acc.items())]
    all_keys = set().union(*[a["keys"] for a in acc.values()]) if acc else set()
    unit = " + ".join(entity)
    agg = {"columns": cols, "rows": rows,
           "schema": {"grain": (" × ".join(group_by) + " 1개") if group_by else "전체 1행", "entity": entity,
                      "entity_unit": unit, "types": {c: "string" for c in (group_by or [])}}}
    chk = _check("distinct_vs_rows", "passed", entity_unit=unit, rows_total=len(table["rows"]),
                 rows_with_valid_key=sum(a["rows"] for a in acc.values()), blank_keys=blank, distinct=len(all_keys))
    return StepResult("succeeded", aggregate=agg, checks=[chk],
                      metrics={"distinct": len(all_keys), "rows": len(table["rows"]), "blank_keys": blank})


# ---------------- H01 분모가 분명한 비율 계산 ----------------
def ratio_rows(pairs):
    """pairs = [(group, numerator, denominator)] — None 은 누락. 0분모 · 누락은 null(0% 가 아님)."""
    out = []
    for g, num, den in pairs:
        if num is None or den is None:
            out.append([g, num, den, None, "누락 — 계산 안 함"])
        elif den == 0:
            out.append([g, num, den, None, "해당없음"])
        else:
            r = num / den
            out.append([g, num, den, r, f"{r * 100:.1f}%".replace(".0%", "%")])
    return out


def h01_ratio(agg_status, group_col, status_col, success_values: list) -> StepResult:
    gi, si, ci = _idx(agg_status, group_col), _idx(agg_status, status_col), _idx(agg_status, "count")
    oi = agg_status["columns"].index("observed") if "observed" in agg_status["columns"] else None
    groups = {}
    for r in agg_status["rows"]:
        g = r[gi]
        d = groups.setdefault(g, [0, 0])
        if oi is not None and r[oi] is False:
            continue                                   # 선언만 된 빈 그룹 → 분모 0
        d[1] += r[ci]
        if r[si] in success_values:
            d[0] += r[ci]
    rows = ratio_rows([(g, n, d) for g, (n, d) in sorted(groups.items())])
    tn = sum(n for _, (n, d) in groups.items())
    td = sum(d for _, (n, d) in groups.items())
    overall = tn / td if td else None
    ratios = [r[3] for r in rows if r[3] is not None]
    mean_of_ratios = sum(ratios) / len(ratios) if ratios else None
    rows.append(["전체", tn, td, overall, "해당없음" if overall is None else f"{overall * 100:.1f}%".replace(".0%", "%")])
    agg = {"columns": [group_col, "numerator", "denominator", "ratio", "display"], "rows": rows,
           "schema": {"grain": f"{group_col} 1개 + 전체 1행", "numerator": f"{status_col} ∈ {success_values} 건수",
                      "denominator": f"{group_col} 의 전체 행 수", "zero_denominator": "null(해당없음)",
                      "types": {group_col: "string", "ratio": "decimal"}}}
    chk = _check("overall_is_pooled_ratio", "passed", overall=overall, mean_of_group_ratios=mean_of_ratios,
                 note="전체 비율 = 전체 분자/전체 분모. 그룹 비율의 단순평균이 아니다")
    return StepResult("succeeded", aggregate=agg, checks=[chk], metrics={"overall": overall})


# ---------------- N02 보고서용 정적 차트 ----------------
def n02_chart(agg, label_col, value_col, run_dir: Path, unit="", title="", value_label="") -> StepResult:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    li, vi = _idx(agg, label_col), _idx(agg, value_col)
    try:
        font_path = font_manager.findfont(font_manager.FontProperties(family=settings.KOREAN_FONT), fallback_to_default=False)
    except ValueError as e:
        raise HandlerError(f"한글 글꼴({settings.KOREAN_FONT})을 찾지 못했습니다 — 차트를 만들지 않습니다", status="blocked") from e
    data = [(str(r[li]), r[vi]) for r in agg["rows"] if str(r[li]) != "전체"]
    labels = [d[0] for d in data]
    values = [d[1] for d in data]
    is_ratio = value_col == "ratio"
    heights = [(v * 100 if is_ratio else v) if v is not None else 0 for v in values]
    shown = [("해당없음" if v is None else (f"{v * 100:.1f}%".replace(".0%", "%") if is_ratio else f"{v:,}")) for v in values]
    plt.rcParams["font.family"] = settings.KOREAN_FONT
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(figsize=(6.4, 4), dpi=150)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        bars = ax.bar(labels, heights, color="#3b6fb6")
        texts = ax.bar_label(bars, labels=shown, padding=3)
        ax.set_ylim(bottom=0, top=max(heights + [1]) * 1.18)
        ax.set_ylabel(f"{value_label or value_col} ({'%' if is_ratio else unit})" if (unit or is_ratio) else (value_label or value_col))
        ax.set_title(title or f"{label_col}별 {value_label or value_col}")
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        fig.canvas.draw()
    glyph_warn = [str(w.message) for w in caught if "Glyph" in str(w.message) or "missing from" in str(w.message)]
    fb = fig.bbox
    parts = [ax.title, ax.yaxis.label, *ax.get_xticklabels(), *texts]
    cut = [t.get_text() for t in parts if t.get_text() and not (
        (e := t.get_window_extent()).x0 >= fb.x0 - 1 and e.x1 <= fb.x1 + 1 and e.y0 >= fb.y0 - 1 and e.y1 <= fb.y1 + 1)]
    read_back = [round(b.get_height(), 9) for b in bars]
    out = run_dir / "chart.png"
    fig.savefig(out)
    plt.close(fig)
    checks = [
        _check("bar_values_match", "passed" if read_back == [round(h, 9) for h in heights] else "failed", expected=heights, drawn=read_back,
               labels=shown),
        _check("axis_starts_at_zero", "passed" if ax.get_ylim()[0] == 0 else "failed"),
        _check("korean_font", "passed" if not glyph_warn else "failed", font=Path(font_path).name, warnings=glyph_warn),
        _check("labels_not_clipped", "passed" if not cut else "failed", clipped=cut),
        _check("single_unit", "passed", unit="%" if is_ratio else unit),
    ]
    st = "succeeded" if all(c["status"] == "passed" for c in checks) else "failed"
    return StepResult(st, checks=checks, outputs=[{"name": "chart.png", "kind": "chart", "path": out.name}],
                      metrics={"bars": len(bars)})


# ---------------- N05 HTML 결과 화면 ----------------
N05_TEMPLATE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--line:#ddd;--dim:#666}}@media(prefers-color-scheme:dark){{:root{{--bg:#16181c;--fg:#e8e8e8;--line:#333;--dim:#9aa0a6}}}}
body{{font-family:"Malgun Gothic",system-ui,sans-serif;margin:0;padding:16px;background:var(--bg);color:var(--fg)}}
table{{border-collapse:collapse;min-width:280px}}th,td{{border:1px solid var(--line);padding:.4rem .7rem;text-align:left}}td.n{{text-align:right}}
.meta{{color:var(--dim);font-size:.85rem}}</style></head><body>
<h1>{title}</h1><p class="meta">{meta}</p>
<label>{label_col}: <select id="f"><option value="">전체</option></select></label>
<table><thead><tr><th>{label_col}</th><th>{value_label}</th></tr></thead><tbody id="b"></tbody>
<tfoot><tr><th>합계</th><td class="n" id="t"></td></tr></tfoot></table>
<script type="application/json" id="data">{data}</script>
<script>
// 파일 내용은 데이터로만 다룬다: textContent 로 넣고 innerHTML 을 쓰지 않는다
const rows = JSON.parse(document.getElementById('data').textContent);
const f = document.getElementById('f'), b = document.getElementById('b'), t = document.getElementById('t');
for (const r of rows) {{ const o = document.createElement('option'); o.value = r.label; o.textContent = r.label; f.appendChild(o); }}
const fmt = (v) => v === null ? '해당없음' : Number(v).toLocaleString('ko-KR');
function draw() {{
  const sel = f.value; b.replaceChildren();
  const vis = rows.filter((r) => !sel || r.label === sel);
  for (const r of vis) {{ const tr = document.createElement('tr'); const a = document.createElement('td'); a.textContent = r.label;
    const c = document.createElement('td'); c.className = 'n'; c.textContent = fmt(r.value); tr.append(a, c); b.appendChild(tr); }}
  t.textContent = fmt(vis.reduce((s, r) => s + (r.value ?? 0), 0));
  location.hash = sel ? 'f=' + encodeURIComponent(sel) : '';
}}
f.addEventListener('change', draw);
const h = new URLSearchParams(location.hash.slice(1)).get('f'); if (h && rows.some((r) => r.label === h)) f.value = h;
draw();
</script></body></html>"""


def n05_html(agg, label_col, value_col, run_dir: Path, unit="", title="", value_label="") -> StepResult:
    li, vi = _idx(agg, label_col), _idx(agg, value_col)
    data = [{"label": str(r[li]), "value": r[vi]} for r in agg["rows"] if str(r[li]) != "전체"]
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    doc = N05_TEMPLATE.format(title=html.escape(title or f"{label_col}별 {value_label or value_col}"),
                              meta=html.escape(f"단위: {unit or '-'} · 필터를 바꾸면 표와 합계가 함께 바뀐다"),
                              label_col=html.escape(label_col), value_label=html.escape(value_label or value_col), data=blob)
    out = run_dir / "view.html"
    out.write_text(doc, encoding="utf-8")
    total = sum(d["value"] or 0 for d in data)
    raw_tag = any("<" in d["label"] for d in data)
    checks = [_check("total", "passed", total=total, groups=len(data)),
              _check("data_escaped", "passed" if "</script" not in blob.lower() else "failed",
                     note="데이터의 HTML 태그는 글자로 표시되고 실행되지 않는다", data_has_tags=raw_tag)]
    return StepResult("succeeded", checks=checks, outputs=[{"name": "view.html", "kind": "html", "path": out.name}],
                      metrics={"total": total})
