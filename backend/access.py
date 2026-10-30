"""Hosted comparison access and persistent, atomic attempt limit."""
import hmac
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import HTTPException


def hosted() -> bool:
    return os.environ.get("DATA_ROADMAP_HOSTED") == "1"


def reserve(password: str | None) -> None:
    if not hosted():
        return
    expected = os.environ.get("DATA_ROADMAP_REVIEW_PASSWORD", "")
    if not expected or not hmac.compare_digest(password or "", expected):
        raise HTTPException(403, "심사위원 접근 암호를 확인해 주세요.")
    path = os.environ.get("DATA_ROADMAP_QUOTA_DB", "")
    if not path:
        raise HTTPException(503, "비교 한도가 설정되지 않았습니다.")
    try:
        limit = int(os.environ.get("DATA_ROADMAP_COMPARE_LIMIT", "5"))
        if limit < 1:
            raise ValueError("invalid limit")
        with closing(sqlite3.connect(Path(path), timeout=10, isolation_level=None)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY)")
            db.execute("BEGIN IMMEDIATE")
            used = db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            if used >= limit:
                db.rollback()
                raise HTTPException(429, "비교 사용 한도에 도달했습니다.")
            db.execute("INSERT INTO attempts DEFAULT VALUES")
            db.commit()
    except (ValueError, sqlite3.Error, OSError) as exc:
        raise HTTPException(503, "비교 한도를 확인할 수 없습니다.") from exc
