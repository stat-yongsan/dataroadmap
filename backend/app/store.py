"""SQLite 저장소(원문 §14) — 엔티티 12개. 파일 산출물은 data/ 아래 ID 로만 찾는다(업로드 파일명으로 경로를 만들지 않는다)."""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from . import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets(dataset_id TEXT PRIMARY KEY, display_name TEXT, kind TEXT, sha256 TEXT, size INTEGER,
  source TEXT, original_path TEXT, inspect_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS dataset_versions(version_id TEXT PRIMARY KEY, dataset_id TEXT, parent_version_id TEXT, role TEXT,
  agg_kind TEXT, grain TEXT, table_path TEXT, schema_json TEXT, created_by_step_run TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS goals(goal_id TEXT PRIMARY KEY, dataset_id TEXT, goal_key TEXT, description TEXT, params_json TEXT,
  rules_json TEXT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS profiles(profile_id TEXT PRIMARY KEY, version_id TEXT, rules_hash TEXT, profile_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS plans(plan_id TEXT PRIMARY KEY, dataset_id TEXT, goal_id TEXT, run_id TEXT, base_version_id TEXT,
  parent_plan_id TEXT, provider TEXT, config_json TEXT, versions_json TEXT, status TEXT, stop_reasons_json TEXT,
  calls_used INTEGER, usage_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS plan_nodes(node_id TEXT PRIMARY KEY, plan_id TEXT, parent_node_id TEXT, depth INTEGER, state_kind TEXT,
  option TEXT, project_id TEXT, control_action TEXT, state_json TEXT, semantic_hash TEXT, gate_json TEXT, display_status TEXT,
  decision_call_id TEXT, path_score REAL, suggested INTEGER, terminal_reason TEXT, step_run_id TEXT);
CREATE TABLE IF NOT EXISTS plan_edges(edge_id TEXT PRIMARY KEY, plan_id TEXT, from_node TEXT, to_node TEXT, option TEXT,
  prob_raw REAL, prob_search REAL, rank INTEGER, decision_call_id TEXT, kind TEXT);
CREATE TABLE IF NOT EXISTS decision_calls(call_id TEXT PRIMARY KEY, plan_id TEXT, node_id TEXT, provider TEXT, model_requested TEXT,
  model_returned TEXT, state_hash TEXT, question_version TEXT, candidate_set_hash TEXT, catalog_version TEXT, policy_version TEXT,
  probabilities_json TEXT, confidence REAL, answers_json TEXT, usage_json TEXT, latency_ms INTEGER, attempts INTEGER,
  status TEXT, error TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, dataset_id TEXT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS step_runs(step_run_id TEXT PRIMARY KEY, run_id TEXT, project_id TEXT, handler_version TEXT, config_hash TEXT,
  idempotency_key TEXT, input_versions_json TEXT, output_versions_json TEXT, checks_json TEXT, execution_mode TEXT, status TEXT,
  metrics_json TEXT, issues_json TEXT, plan_id TEXT, node_id TEXT, started_at TEXT, ended_at TEXT);
CREATE TABLE IF NOT EXISTS artifacts(artifact_id TEXT PRIMARY KEY, step_run_id TEXT, name TEXT, kind TEXT, path TEXT, grain TEXT,
  sha256 TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS checks(check_id TEXT PRIMARY KEY, step_run_id TEXT, project_id TEXT, name TEXT, status TEXT,
  detail_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS race_runs(race_id TEXT PRIMARY KEY, batch_id TEXT, plan_id TEXT, who TEXT, model_requested TEXT,
  model_returned TEXT, effort TEXT, first_ms INTEGER, done_ms INTEGER, status TEXT, error TEXT, check_status TEXT, check_error TEXT,
  answer_json TEXT, usage_json TEXT, attempts INTEGER, created_at TEXT);
CREATE INDEX IF NOT EXISTS ix_nodes_plan ON plan_nodes(plan_id);
CREATE INDEX IF NOT EXISTS ix_edges_plan ON plan_edges(plan_id);
CREATE INDEX IF NOT EXISTS ix_steps_run ON step_runs(run_id);
"""

_lock = threading.RLock()
_conn = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def db() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            settings.DATA.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(settings.DATA / "app.sqlite", check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.executescript(SCHEMA)
        return _conn


def reset_for_tests(path):
    """점검 스크립트 전용 — 다른 data 폴더로 새 DB 를 연다."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
        settings.DATA = path


def insert(table: str, **row):
    row = {k: (json.dumps(v, ensure_ascii=False, default=str) if k.endswith("_json") else v) for k, v in row.items()}
    with _lock:
        db().execute(f"INSERT INTO {table}({','.join(row)}) VALUES({','.join('?' * len(row))})", list(row.values()))
        db().commit()


def update(table: str, key: str, key_val, **row):
    row = {k: (json.dumps(v, ensure_ascii=False, default=str) if k.endswith("_json") else v) for k, v in row.items()}
    with _lock:
        db().execute(f"UPDATE {table} SET {','.join(f'{k}=?' for k in row)} WHERE {key}=?", [*row.values(), key_val])
        db().commit()


def _dec(r):
    if r is None:
        return None
    d = dict(r)
    for k in list(d):
        if k.endswith("_json") and d[k] is not None:
            d[k[:-5]] = json.loads(d.pop(k))
    return d


def one(sql: str, *args):
    with _lock:
        return _dec(db().execute(sql, args).fetchone())


def many(sql: str, *args):
    with _lock:
        return [_dec(r) for r in db().execute(sql, args).fetchall()]


# ---- 표 파일 (null · 정수 · 문자열을 그대로 보존하려고 JSON 으로 둔다) ----
def save_table(version_id: str, table: dict) -> str:
    d = settings.DATA / "versions" / version_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / "table.json"
    p.write_text(json.dumps({"columns": table["columns"], "rows": table["rows"]}, ensure_ascii=False, default=str), encoding="utf-8")
    return str(p.relative_to(settings.DATA))


def load_table(version: dict) -> dict:
    t = json.loads((settings.DATA / version["table_path"]).read_text(encoding="utf-8"))
    t["schema"] = version.get("schema") or {}
    return t
