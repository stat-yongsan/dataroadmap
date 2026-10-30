"""앱 설정 한 곳 — 경로 · 한도(원문 §6) · 탐색 기본값(원문 §9) · 버전.

비밀값은 환경변수로만 읽는다. .env 는 D:\\devOps\\.env(규칙서의 비밀값 한 곳) 또는 data-roadmap\\.env 에서
필요한 이름만 읽어 os.environ 에 없을 때만 채운다. 값은 어디에도 출력하지 않는다.
"""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # data-roadmap/
DATA = Path(os.environ.get("JEV_ROADMAP_DATA", ROOT / "data"))
CATALOG_DIR = ROOT / "catalog"
EXAMPLES_DIR = ROOT / "examples"
DOCS_DIR = ROOT / "docs"
FRONTEND_DIST = ROOT / "frontend" / "dist"

_ENV_NAMES = ("TYPESAFE_API_KEY", "JEV_MODEL", "JEV_API_URL", "PLAYBOOK_PATH", "ANTHROPIC_API_KEY",
              "OPENAI_API_KEY", "OPENAI_DECISIONS_MODEL", "OPENAI_DECISIONS_URL", "ROADMAP_HOSTED", "ROADMAP_ADMIN_PASSWORD", "ROADMAP_CODEX_ENABLED", "CODEX_BIN", "ROADMAP_CODEX_MODEL", "ROADMAP_KOREAN_FONT")
for _env in (ROOT.parent / ".env", ROOT / ".env"):
    if _env.is_file():
        for _line in _env.read_text(encoding="utf-8", errors="replace").splitlines():
            _k, _, _v = _line.partition("=")
            if _k.strip() in _ENV_NAMES and _v.strip():
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

PLAYBOOK = Path(os.environ.get("PLAYBOOK_PATH", r"D:\elec5_test\Excel_Automation_Playbook_KO.md"))
LEGACY_CATALOG = PLAYBOOK.parent / "Excel_Automation_Labs_KO" / "project_catalog.json"
# 명세(원문 §1)에 적힌 기준 해시. 다르면 오류가 아니라 새 원본 기준으로 새 카탈로그 버전을 만든다.
SPEC_PLAYBOOK_SHA256 = "fcfdc11d6d5f5f471f7751ac07e36667faf7771031536c2d31c50367595e3de5"

LIMITS = {
    "upload_bytes": 20 * 1024 * 1024,        # 20 MiB
    "max_rows": 100_000,                     # 읽기 대상 행 — 넘으면 자르지 않고 거절
    "xlsx_unzipped_bytes": 200 * 1024 * 1024,
}
SEARCH = {
    "beam_width": 3,
    "branch_candidates": 3,
    "max_depth": 6,
    "max_nodes": 120,
    "max_live_calls_per_plan": 10,
    "request_timeout_seconds": 30,
}
VERSIONS = {"policy": "policy.v1", "question": "questions.v1", "handler": "handlers.v1"}

JEV_API_URL = os.environ.get("JEV_API_URL", "https://api.typesafe.ai/v1/systemone")
JEV_MODEL = os.environ.get("JEV_MODEL", "jev-latest")
OPENAI_DECISIONS_URL = os.environ.get("OPENAI_DECISIONS_URL", "https://api.openai.com/v1/decisions")
OPENAI_DECISIONS_MODEL = os.environ.get("OPENAI_DECISIONS_MODEL", "gpt-6-luna")
HOSTED = os.environ.get("ROADMAP_HOSTED") == "1"
ADMIN_PASSWORD = os.environ.get("ROADMAP_ADMIN_PASSWORD", "")
CODEX_BIN = os.environ.get("CODEX_BIN") or shutil.which("codex") or "codex"
CODEX_MODEL = os.environ.get("ROADMAP_CODEX_MODEL", "gpt-6.1-sol")
KOREAN_FONT = os.environ.get("ROADMAP_KOREAN_FONT", "Malgun Gothic")


def codex_available() -> bool:
    return os.environ.get("ROADMAP_CODEX_ENABLED") == "1" and bool(shutil.which(CODEX_BIN))


def anthropic_key() -> str:
    """결정 속도 비교(/race)의 Opus 5.5 호출용. 값은 밖으로 내보내지 않는다."""
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()


def openai_key() -> str:
    """OpenAI Decisions API 키. 값은 밖으로 내보내지 않는다(Codex CLI 환경에도 넘기지 않음)."""
    return os.environ.get("OPENAI_API_KEY", "").strip()


def live_key() -> str:
    """키 값 자체는 이 함수 밖으로 내보내지 않는다(있다/없다만 화면에 보인다)."""
    return os.environ.get("TYPESAFE_API_KEY", "").strip()
