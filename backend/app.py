"""Data Roadmap: a small, local CSV planning prototype."""
from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from backend import race

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 100_000
app = FastAPI(title="Data Roadmap prototype")


def parse_csv(raw: bytes) -> tuple[list[str], list[dict[str, str]]]:
    if len(raw) > MAX_BYTES:
        raise ValueError("파일은 2MB 이하만 사용할 수 있습니다.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("UTF-8 CSV 파일을 선택해 주세요.") from exc
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        columns = next(reader, None)
        if not columns or any(not x.strip() for x in columns):
            raise ValueError("비어 있지 않은 열 이름이 필요합니다.")
        columns = [x.strip() for x in columns]
        if len(columns) != len(set(columns)):
            raise ValueError("열 이름이 중복됩니다.")
        rows = []
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            if len(row) != len(columns):
                raise ValueError(f"{reader.line_num}행의 열 개수가 머리글과 다릅니다.")
            rows.append(dict(zip(columns, row)))
            if len(rows) > MAX_ROWS:
                raise ValueError("10만 행을 초과하는 파일은 사용할 수 없습니다.")
    except csv.Error as exc:
        raise ValueError("CSV 형식을 읽을 수 없습니다.") from exc
    if not rows:
        raise ValueError("데이터 행이 없습니다.")
    return columns, rows


def amount(value: str) -> Decimal:
    text = value.strip().removesuffix("원").strip()
    if not re.fullmatch(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", text):
        raise ValueError("금액은 숫자와 천 단위 쉼표, 선택적인 원 단위만 지원합니다.")
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("금액을 숫자로 읽을 수 없습니다.") from exc


def profile(raw: bytes) -> dict:
    columns, rows = parse_csv(raw)
    numeric = []
    for col in columns:
        try:
            for row in rows:
                amount(row[col])
        except ValueError:
            continue
        numeric.append(col)
    return {"columns": columns, "row_count": len(rows), "numeric_columns": numeric,
            "preview": [[row[col] for col in columns] for row in rows[:5]]}


def make_plan(raw: bytes, goal: str, group_col: str, value_col: str = "") -> dict:
    columns, rows = parse_csv(raw)
    if goal not in ("sum", "count"):
        raise ValueError("지원하는 목표를 선택해 주세요.")
    if group_col not in columns:
        raise ValueError("데이터에 있는 그룹 열을 선택해 주세요.")
    if any(not row[group_col].strip() for row in rows):
        raise ValueError("그룹 값이 비어 있는 행이 있어 먼저 확인해야 합니다.")
    if goal == "sum":
        if value_col not in columns or value_col == group_col:
            raise ValueError("그룹 열과 다른 금액 열을 선택해 주세요.")
        for row in rows:
            amount(row[value_col])
    steps = (["CSV 읽기", "그룹 값 확인", "금액 해석", "그룹별 합계", "원본 합계와 대조"] if goal == "sum"
             else ["CSV 읽기", "그룹 값 확인", "그룹별 건수", "원본 행 수와 대조"])
    return {"goal": goal, "group_col": group_col, "value_col": value_col if goal == "sum" else None,
            "row_count": len(rows), "steps": steps, "status": "not_run"}


def execute(raw: bytes, goal: str, group_col: str, value_col: str = "") -> dict:
    plan = make_plan(raw, goal, group_col, value_col)
    _, rows = parse_csv(raw)
    if goal == "sum":
        totals: dict[str, Decimal] = {}
        for row in rows:
            key = row[group_col].strip()
            totals[key] = totals.get(key, Decimal(0)) + amount(row[value_col])
        expected = sum((amount(row[value_col]) for row in rows), Decimal(0))
        actual = sum(totals.values(), Decimal(0))
        result = [{"group": k, "value": format(v, "f")} for k, v in sorted(totals.items())]
        total = format(actual, "f")
        verified = actual == expected
        check = "그룹 합계와 원본 금액 합계 일치"
    else:
        totals = Counter(row[group_col].strip() for row in rows)
        actual = sum(totals.values())
        result = [{"group": k, "value": str(v)} for k, v in sorted(totals.items())]
        total = str(actual)
        verified = actual == len(rows)
        check = "그룹별 건수와 원본 행 수 일치"
    return {"plan": plan, "rows": result, "total": total, "verified": verified, "check": check}


async def read_file(file: UploadFile) -> bytes:
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "CSV 파일만 지원합니다.")
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(400, "파일은 2MB 이하만 사용할 수 있습니다.")
    return raw


@app.get("/api/catalog")
def get_catalog():
    catalog = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))
    return {"areas": catalog["counts"], "area_names": catalog["area_names"], "projects": catalog["projects"]}


@app.get("/api/sample")
def get_sample():
    return FileResponse(ROOT / "data" / "sample.csv", media_type="text/csv", filename="sample.csv")


@app.post("/api/profile")
async def get_profile(file: UploadFile = File(...)):
    try:
        return profile(await read_file(file))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/plan")
async def get_plan(file: UploadFile = File(...), goal: str = Form(...), group_col: str = Form(...), value_col: str = Form("")):
    try:
        return make_plan(await read_file(file), goal, group_col, value_col)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/run")
async def run_plan(file: UploadFile = File(...), goal: str = Form(...), group_col: str = Form(...), value_col: str = Form("")):
    try:
        return execute(await read_file(file), goal, group_col, value_col)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/race/availability")
def race_availability():
    return race.availability()


@app.post("/api/race")
async def race_models(request: Request, file: UploadFile = File(...), goal: str = Form(...), group_col: str = Form(...),
                      value_col: str = Form(""), consent: bool = Form(False)):
    origin = request.headers.get("origin")
    if request.headers.get("x-data-roadmap") != "1" or request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "이 앱에서 보낸 요청만 허용합니다.")
    if origin and (urlsplit(origin).netloc != request.url.netloc or urlsplit(origin).scheme != request.url.scheme):
        raise HTTPException(403, "다른 사이트에서 보낸 요청은 허용하지 않습니다.")
    if not consent:
        raise HTTPException(400, "두 공급자에게 보낼 필드를 확인하고 동의해 주세요.")
    try:
        raw = await read_file(file)
        p = profile(raw)
        make_plan(raw, goal, group_col, value_col)
        state = {"goal": goal, "group_col": group_col, "value_col": value_col if goal == "sum" else None,
                 "row_count": p["row_count"], "columns": p["columns"], "numeric_columns": p["numeric_columns"]}
        return await run_in_threadpool(race.compare, state)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


dist = ROOT / "frontend" / "dist"
if (dist / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")


@app.get("/")
def index():
    if not (dist / "index.html").is_file():
        raise HTTPException(503, "먼저 frontend에서 npm ci와 npm run build를 실행해 주세요.")
    return FileResponse(dist / "index.html")
