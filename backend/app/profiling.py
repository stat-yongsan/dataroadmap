"""업로드 파일 조사(원문 §6). 값을 고치지 않고 재기만 한다.

inspect_*  : 파일 수준(인코딩 · 구분자 · 시트 · 병합 · 숨김 · 수식 · 머리글 후보 · 표 범위 확정 여부)
profile_table : 읽어 들인 표의 열별 측정값(전체 조사 — 표본으로 전체를 판정하지 않는다)
"""
import csv
import hashlib
import io
import re
import time
import zipfile
from collections import Counter
from datetime import date, datetime

from . import settings

INT_RE = re.compile(r"^[+-]?\d+$")
NUM_TEXT_RE = re.compile(r"^\(?[+-]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?\)?\s*(원|₩|KRW)?$")
PERCENT_RE = re.compile(r"^[+-]?\d+(\.\d+)?%$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_LOOSE_RE = re.compile(r"^\d{4}[/.]\d{1,2}[/.]\d{1,2}$|^\d{1,2}/\d{1,2}/\d{4}$")
ID_NAME_RE = re.compile(r"(번호|학번|코드|아이디|id|_no|no\.?|key|키)$", re.I)
HEADER_SCAN_ROWS = 30  # 머리글 후보는 위에서부터 이 행 수만 본다 — 표본 기반이라고 결과에 적는다


class InspectError(Exception):
    """조사 불가(한도 초과 · 손상 · 해석 불가) — 조용히 넘어가지 않고 사용자에게 그대로 보인다."""


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ---------- CSV / TSV ----------
def detect_encoding(raw: bytes) -> dict:
    if raw.startswith(b"\xef\xbb\xbf"):
        return {"encoding": "utf-8-sig", "status": "confirmed", "reason": "UTF-8 BOM", "choices": []}
    try:
        raw.decode("utf-8")
        return {"encoding": "utf-8", "status": "confirmed", "reason": "UTF-8 로 오류 없이 해석됨", "choices": []}
    except UnicodeDecodeError:
        pass
    try:
        raw.decode("cp949")
        # CP949 는 많은 바이트열을 오류 없이 받아들인다 → 확정하지 않고 사용자에게 선택지를 준다(원문 §6)
        return {"encoding": "cp949", "status": "estimated", "reason": "UTF-8 로 해석 불가, CP949 로는 오류 없음(추정)",
                "choices": ["cp949", "euc-kr", "utf-16"]}
    except UnicodeDecodeError:
        return {"encoding": None, "status": "unknown", "reason": "UTF-8·CP949 모두 해석 불가 — 인코딩을 골라야 한다",
                "choices": ["utf-16", "euc-kr", "latin-1"]}


def detect_delimiter(filename: str, sample: str) -> str:
    if filename.lower().endswith(".tsv"):
        return "\t"
    if filename.lower().endswith(".csv"):
        return ","
    try:
        return csv.Sniffer().sniff(sample[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def inspect_csv(raw: bytes, filename: str) -> dict:
    enc = detect_encoding(raw)
    text = raw.decode(enc["encoding"]) if enc["encoding"] else ""
    return {"kind": "csv", "encoding": enc, "delimiter": detect_delimiter(filename, text),
            "table": {"status": "confirmed" if enc["encoding"] else "needs_info",
                      "reason": "텍스트 표는 첫 행을 머리글로 읽는다" if enc["encoding"] else enc["reason"]}}


# ---------- XLSX ----------
def _cell_text(v):
    return "" if v is None else str(v).strip()


def inspect_xlsx(path) -> dict:
    """시트 · 사용 범위 · 머리글 후보 · 병합 · 숨김 · 수식. 구조가 불명확하면 표 범위를 확정하지 않는다."""
    import openpyxl

    t0 = time.monotonic()
    try:
        with zipfile.ZipFile(path) as z:
            unzipped = sum(i.file_size for i in z.infolist())
            has_macro = any(i.filename.endswith("vbaProject.bin") for i in z.infolist())
    except zipfile.BadZipFile as e:
        raise InspectError(f"XLSX 가 아니거나 손상된 파일입니다: {e}") from e
    if unzipped > settings.LIMITS["xlsx_unzipped_bytes"]:
        raise InspectError(f"압축 해제 크기 {unzipped:,} 바이트가 한도 {settings.LIMITS['xlsx_unzipped_bytes']:,} 를 넘습니다(자르지 않고 거절).")
    wb = openpyxl.load_workbook(path, data_only=False)  # 병합 · 수식 확인용. 매크로 · 외부 링크는 실행하지 않는다
    sheets = []
    for ws in wb.worksheets:
        formulas = 0
        rows = []
        for r_idx, row in enumerate(ws.iter_rows(), start=1):
            if time.monotonic() - t0 > 30:
                raise InspectError("XLSX 조사가 30초를 넘어 멈췄습니다(처리 시간 한도).")
            vals = []
            for c in row:
                if c.data_type == "f":
                    formulas += 1
                vals.append(c.value)
            if r_idx <= HEADER_SCAN_ROWS:
                rows.append(vals)
        merged = [str(m) for m in ws.merged_cells.ranges]
        hidden_rows = sum(1 for d in ws.row_dimensions.values() if d.hidden)
        hidden_cols = sum(1 for d in ws.column_dimensions.values() if d.hidden)
        cands, titles = [], []
        for i, vals in enumerate(rows, start=1):
            texts = [_cell_text(v) for v in vals]
            filled = [t for t in texts if t]
            if len(filled) == 1 and len(texts) > 1:
                titles.append(i)
            elif len(filled) >= 2 and all(isinstance(v, str) for v in vals if _cell_text(v)) \
                    and not any(INT_RE.match(t) or NUM_TEXT_RE.match(t) for t in filled):
                nxt = rows[i] if i < len(rows) else []
                if any(_cell_text(v) for v in nxt):
                    cands.append({"row": i, "values": filled})
        same = [c["row"] for c in cands if sum(1 for d in cands if d["values"] == c["values"]) > 1]
        sheets.append({"name": ws.title, "state": ws.sheet_state, "dimension": ws.calculate_dimension(),
                       "max_row": ws.max_row, "max_column": ws.max_column, "merged": merged, "formulas": formulas,
                       "hidden_rows": hidden_rows, "hidden_columns": hidden_cols, "title_rows": titles,
                       "header_candidates": cands, "duplicate_header_rows": same,
                       "header_scan": {"method": f"위에서부터 {HEADER_SCAN_ROWS}행", "rows_scanned": len(rows), "sample_based": True}})
    data_sheets = [s for s in sheets if s["state"] == "visible" and s["max_row"] > 1]
    reasons = []
    if len(data_sheets) != 1:
        reasons.append(f"자료가 있는 보이는 시트가 {len(data_sheets)}개 — 어느 시트인지 지정 필요")
    s = data_sheets[0] if data_sheets else None
    if s:
        if s["merged"]:
            reasons.append(f"병합셀 {len(s['merged'])}개({', '.join(s['merged'][:3])})")
        if s["title_rows"]:
            reasons.append(f"제목행 후보 {s['title_rows']}")
        if s["duplicate_header_rows"]:
            reasons.append(f"동일한 머리글 후보 {s['duplicate_header_rows']} — 임의로 고르지 않음")
        elif len(s["header_candidates"]) != 1:
            reasons.append(f"머리글 후보 {len(s['header_candidates'])}개")
        elif s["header_candidates"][0]["row"] != 1:
            reasons.append(f"머리글 후보가 {s['header_candidates'][0]['row']}행 — 1행이 아님")
        if s["formulas"]:
            reasons.append(f"수식 {s['formulas']}칸 — openpyxl 은 계산하지 않음(저장된 값만 읽음)")
    table = {"status": "needs_info" if reasons else "confirmed", "reasons": reasons,
             "sheet": s["name"] if s else None, "header_row": 1 if not reasons else None,
             "reason": "단순 표(1행 머리글 · 병합 없음)" if not reasons else "표 범위 미확정 — 범위를 지정하거나 B01(미구현)이 필요"}
    return {"kind": "xlsx", "unzipped_bytes": unzipped, "has_macro": has_macro, "sheets": sheets, "table": table}


# ---------- 열 측정 ----------
def classify(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "text"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "decimal"
    if isinstance(v, (datetime, date)):
        return "date"
    s = str(v).strip()
    if s == "":
        return "empty"
    if INT_RE.match(s):
        return "int_text"
    if PERCENT_RE.match(s):
        return "percent_text"
    if NUM_TEXT_RE.match(s):
        return "number_text"
    if DATE_RE.match(s):
        return "date"
    if DATE_LOOSE_RE.match(s):
        return "date_nonstandard"
    return "text"


def column_kind(counts: Counter) -> str:
    real = {k: v for k, v in counts.items() if k not in ("null", "empty")}
    if not real:
        return "empty"
    if set(real) <= {"int"}:
        return "integer"
    if set(real) <= {"int", "decimal"}:
        return "decimal"
    if set(real) <= {"int_text"}:
        return "integer_text"
    if set(real) <= {"int_text", "number_text"}:
        return "number_text"
    if set(real) <= {"percent_text"}:
        return "percent_text"
    if set(real) <= {"date"}:
        return "date"
    if len(real) == 1:
        return next(iter(real))
    numericish = sum(v for k, v in real.items() if k in ("int", "decimal", "int_text", "number_text", "percent_text"))
    return "mixed_numeric" if numericish >= sum(real.values()) / 2 else "text"


def profile_table(table: dict, rules: dict | None = None, formula_uncached: dict | None = None) -> dict:
    """전체 행을 다 본다(measured). rules 의 key 가 있으면 중복 그룹을 잰다."""
    rules = rules or {}
    cols, rows = table["columns"], table["rows"]
    idx = {c: i for i, c in enumerate(cols)}
    out = []
    for c in cols:
        vals = [r[idx[c]] for r in rows]
        counts = Counter(classify(v) for v in vals)
        texts = [str(v).strip() for v in vals if isinstance(v, str) and str(v).strip()]
        leading_zero = sum(1 for t in texts if INT_RE.match(t) and len(t) > 1 and t.lstrip("+-").startswith("0"))
        long_digits = sum(1 for v in vals if isinstance(v, str) and INT_RE.match(v.strip()) and len(v.strip()) >= 16)
        numeric_cells = sum(1 for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool))
        nonempty = [v for v in vals if classify(v) not in ("null", "empty")]
        distinct = len({str(v) for v in nonempty})
        kind = column_kind(counts)
        is_id = bool(ID_NAME_RE.search(c)) or leading_zero > 0
        id_reason = []
        if ID_NAME_RE.search(c):
            id_reason.append("열 이름이 식별자 형태")
        if leading_zero:
            id_reason.append(f"앞자리 0 값 {leading_zero}개")
        damaged = is_id and numeric_cells > 0
        out.append({
            "name": c, "kind": kind, "type_counts": dict(counts),
            "null": counts.get("null", 0), "empty": counts.get("empty", 0),
            "zero": sum(1 for v in vals if (isinstance(v, (int, float)) and v == 0) or (isinstance(v, str) and v.strip() in ("0", "0원"))),
            "distinct": distinct, "all_unique": len(nonempty) == len(rows) and distinct == len(rows) and len(rows) > 1,
            "identifier": is_id, "identifier_reason": id_reason, "leading_zero_values": leading_zero,
            "long_digit_values": long_digits,
            "identifier_damage_possible": damaged,
            "identifier_damage_reason": "식별자 열에 숫자로 저장된 칸이 있음 — 앞자리 0·긴 숫자가 이미 손상됐을 수 있다(복구하지 않음)" if damaged else "",
            "formula_uncached": (formula_uncached or {}).get(c, 0),
            "numeric": kind in ("integer", "decimal"),
            "needs_parse": kind in ("number_text", "percent_text", "integer_text", "mixed_numeric") and not is_id,
        })
    key = [k for k in (rules.get("key") or []) if k in idx]
    dup = None
    if key:
        groups = Counter(tuple(str(r[idx[k]]) for k in key) for r in rows)
        bad = {g: n for g, n in groups.items() if n > 1}
        dup = {"key": key, "groups": len(bad), "rows": sum(bad.values()),
               "examples": [{"key": list(g), "count": n} for g, n in list(bad.items())[:5]]}
    return {
        "measured": True, "scope": "전체 조사", "rows_read": len(rows), "columns_read": len(cols),
        "columns": out,
        "key_candidates": [c["name"] for c in out if c["all_unique"]],
        "declared_key_duplicates": dup,
        "grain": {"value": rules.get("grain"), "status": "confirmed" if rules.get("grain") else "unconfirmed"},
        "units": {"value_unit": rules.get("value_unit"), "status": "confirmed" if rules.get("value_unit") else "unconfirmed"},
        "date_format": {"status": "confirmed" if rules.get("date_format") else "unconfirmed"},
    }


def suggest_goals(profile: dict) -> list[dict]:
    """데이터가 받쳐 주는 활용 목적 몇 개. 유일한 정답이라고 하지 않는다(원문 §15 · 강의 17절)."""
    cols = profile["columns"]
    n = profile["rows_read"] or 1
    group = [c["name"] for c in cols if c["kind"] == "text" and not c["identifier"] and 2 <= c["distinct"] <= max(20, n // 2)]
    value = [c["name"] for c in cols if (c["numeric"] or c["needs_parse"]) and not c["identifier"]]
    entity = [c["name"] for c in cols if c["identifier"] and not c["all_unique"]] or [c["name"] for c in cols if c["identifier"]]
    status = [c["name"] for c in cols if c["kind"] == "text" and not c["identifier"] and 2 <= c["distinct"] <= 5]
    dates = [c["name"] for c in cols if c["kind"] in ("date", "date_nonstandard")]
    out = []
    if group and value:
        out.append({"goal_key": "sum_by_group", "params": {"group_col": group[0], "value_col": value[0]}})
    if group:
        out.append({"goal_key": "count_by_group", "params": {"group_col": group[0]}})
    if entity:
        out.append({"goal_key": "distinct_entities", "params": {"entity_col": entity[0]}})
    if group and len(status) >= 2:
        st = next((s for s in status if s != group[0]), None)
        if st:
            out.append({"goal_key": "rate_by_group", "params": {"group_col": group[0], "status_col": st}})
    if dates:
        out.append({"goal_key": "monthly_trend", "params": {"date_col": dates[0], "value_col": value[0] if value else None}})
    return out


def csv_rows(text: str, delimiter: str) -> list[list[str]]:
    """따옴표 · 줄바꿈 규칙대로 읽는다. 닫히지 않은 따옴표 · 칸 수 불일치는 조용히 넘기지 않는다."""
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
    except csv.Error as e:
        raise InspectError(f"텍스트 표 해석 실패(따옴표 규칙): {e}") from e
    while rows and not any(x.strip() for x in rows[-1]):
        rows.pop()
    return rows
