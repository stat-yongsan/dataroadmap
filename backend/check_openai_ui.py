"""OpenAI Decisions 화면 흐름(T15) — 가짜 Decisions 서버 + 가짜 키로 실제 화면을 조작한다. 실제 OpenAI 호출은 없다.

  py -3 check_openai_ui.py          앱을 임시 데이터 · 포트 8769 로 직접 띄우고 끝나면 끈다

이것은 「돌려 봤다」이지 「사람이 확인했다」가 아니다. 결과는 docs/check-openai-ui-report.json.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from fake_decisions import FAKE_KEY, FAKE_MODEL, FakeDecisions

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent
PORT = 8769
BASE = f"http://127.0.0.1:{PORT}"
MAKE = "활용 로드맵 만들기"
RES = []


def check(name, cond, detail=""):
    RES.append({"name": name, "ok": bool(cond), "detail": str(detail)[:300]})
    print(("  ✔ " if cond else "  ✘ ") + name + (f" — {detail}" if not cond and detail else ""))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.load(r)


def plan_id(page):
    return re.search(r"/roadmaps/([\w-]+)", page.url)[1]


def flow(page):
    page.goto(BASE + "/")
    page.get_by_role("button", name="불러오기").first.click()
    page.get_by_text("3. 목적과 업무 규칙").wait_for()
    pick = page.locator("select:has(option[value=openai])")
    make = page.get_by_role("button", name=MAKE)
    check("키가 있어도 기본은 모의 판단 · OpenAI 는 고르는 선택지", pick.input_value() == "mock" and not pick.locator("option[value=openai]").evaluate("o => o.disabled"), pick.input_value())
    check("상단에 OpenAI 연결 준비 · 모델 표시", "OpenAI 연결 준비 · gpt-6-luna" in page.locator(".band .live").inner_text())
    pick.select_option("openai")
    sec = page.locator("section.card", has_text="3. 목적과 업무 규칙")
    check("OpenAI 선택: 동의 전 잠김 · 잠긴 이유 안내 · 전송 목적지 표시", make.is_disabled() and "보낼 필드 먼저 보기」를 눌러야 켜집니다" in sec.inner_text() and "OpenAI Decisions API로 보냅니다" in sec.inner_text() and "TypeSafe로 보냅니다" not in sec.inner_text())
    page.get_by_role("button", name="보낼 필드 먼저 보기(호출 안 함)").click()
    consent = page.locator("label", has_text="보내는 데 동의합니다")
    consent.wait_for()
    check("필드 보기는 외부 호출 없음 · 아직 잠김 · 다음 할 일 안내", not FakeDecisions.hits and make.is_disabled() and "동의에 체크하면 켜집니다" in sec.inner_text(), FakeDecisions.hits)
    check("동의 문구의 목적지 = OpenAI Decisions API", "외부(OpenAI Decisions API)로 보내는 데 동의합니다" in consent.inner_text())
    consent.locator("input[type=checkbox]").check()
    check("동의하면 풀림 · 안내 사라짐", not make.is_disabled() and "켜집니다" not in sec.inner_text())
    make.click()
    page.wait_for_url(re.compile(r"/roadmaps/"))
    expect(page.locator(".react-flow__node").first).to_be_visible()
    calls = FakeDecisions.hits.get("ok", 0)
    band = page.locator(".band").inner_text()
    main = page.locator("main").inner_text()
    check("로드맵: 분기 그래프 · 띠에 OpenAI 공급자와 돌려받은 모델 · 호출 수", page.locator(".react-flow__node").count() >= 3 and f"LIVE 판단(OpenAI Decisions API · {FAKE_MODEL})" in band
          and re.search(r"호출 \d+/10회", main) and 1 <= calls <= 10, (band, calls))
    check("로드맵 본문: 실제 분포 표시 · TypeSafe 표기 없음 · confidence 표시", "OpenAI Decisions API 가 돌려준 분포입니다" in main and "TypeSafe" not in main and "0.61" in main, main[:300])

    before = plan_id(page)
    plan = get(f"/api/plans/{before}")
    node = next(n for n in plan["nodes"] if n["depth"] == 1 and n["status"] == "ready" and n["project_id"])
    page.locator(".react-flow__node", has_text=node["project_id"]).first.click()
    page.get_by_role("button", name=re.compile(rf"{node['project_id']} 실행")).click()
    page.wait_for_url(lambda u: "/roadmaps/" in u and before not in u)
    page.locator(".react-flow__node").first.wait_for()
    after = get(f"/api/plans/{plan_id(page)}")
    check("실행 뒤 새 계획도 OpenAI 유지 · 띠 그대로", after["plan"]["provider"] == "openai" and "OpenAI Decisions API" in page.locator(".band").inner_text(), after["plan"]["provider"])

    page.goto(BASE + "/")
    page.get_by_text("샘플 데이터 고르기").wait_for()
    check("시작 화면으로 돌아오면 다시 모의 판단 띠", page.locator(".band").inner_text().startswith("모의 판단"))
    health = json.dumps(get("/api/health"), ensure_ascii=False)
    check("health 는 키 유무만 알려 주고 값은 없음", '"openai_key_present": true' in health and FAKE_KEY not in health and FAKE_KEY not in page.content())


def main():
    fake = ThreadingHTTPServer(("127.0.0.1", 0), FakeDecisions)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    env = dict(os.environ, JEV_ROADMAP_DATA=tempfile.mkdtemp(prefix="jev-openai-ui-"), OPENAI_API_KEY=FAKE_KEY,
               OPENAI_DECISIONS_URL=f"http://127.0.0.1:{fake.server_address[1]}/ok", TYPESAFE_API_KEY="", ANTHROPIC_API_KEY="",
               ROADMAP_CODEX_ENABLED="", ROADMAP_HOSTED="", PYTHONIOENCODING="utf-8")
    srv = subprocess.Popen([str(BACKEND / ".venv/Scripts/python.exe"), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"], cwd=BACKEND, env=env)
    try:
        for _ in range(80):
            try:
                get("/api/health")
                break
            except OSError:
                time.sleep(0.5)
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": 1440, "height": 950})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            flow(page)
            check("화면 스크립트 오류 없음", not errors, errors[:2])
            b.close()
    finally:
        srv.terminate()
        srv.wait(timeout=15)
        fake.shutdown()
    ok = all(r["ok"] for r in RES)
    report = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "passed": sum(r["ok"] for r in RES), "total": len(RES), "all_passed": ok,
              "note": "가짜 서버 · 가짜 키. 실제 OpenAI 응답 · 판단 품질 검증이 아니다.", "results": RES}
    (ROOT / "docs" / "check-openai-ui-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{report['passed']}/{report['total']} 통과 — {'전부 통과' if ok else '실패 있음'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
