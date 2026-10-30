"""강의자료용 앱 캡처(D14 · D16) — 1000행 예제(examples/example_a_money_text_1000.csv)를 올려 ★ 추천을 따라가며
Playwright 로 lecture/img/ 에 저장한다(C05 → D03 → D01 → C03 → I01 → N02).

  backend\\.venv\\Scripts\\python ..\\lecture\\capture.py [주소]   (기본 http://127.0.0.1:8765)

화면 맨 위 「모의 판단」 띠가 들어가도록 늘 창 맨 위부터 찍는다(원문 §10 · R16.1 — MOCK 을 Jev 성능처럼 보이지 않게).
서버는 따로 켜 둔다. 캡처용이면 JEV_ROADMAP_DATA 를 임시 폴더로 두고 다른 포트로 켜면 쓰던 자료와 섞이지 않는다.
"""
import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8765"
OUT = Path(__file__).resolve().parent / "img"
OUT.mkdir(exist_ok=True)
VIEW = {"width": 1280, "height": 720}


def shot(page, name):
    page.evaluate("window.scrollTo(0, 0)")
    assert page.locator(".band").inner_text().startswith("모의 판단"), "모의 판단 띠가 없다"
    page.screenshot(path=str(OUT / f"{name}.png"))
    print("  saved", name)


def plan_id(page):
    return re.search(r"/roadmaps/([\w-]+)", page.url)[1]


def run(page, pid_text):
    before = plan_id(page)
    page.get_by_role("button", name=re.compile(rf"{pid_text} 실행")).click()
    page.wait_for_url(lambda u: "/roadmaps/" in u and before not in u)
    page.locator(".react-flow__node").first.wait_for()


CSV = Path(__file__).resolve().parents[1] / "examples" / "example_a_money_text_1000.csv"


def node(page, text):
    """계획 노드만 누른다(실행 이력 노드 h:… 는 뺀다)."""
    page.locator(".react-flow__node:not([data-id^='h:'])", has_text=text).first.click()
    expect(page.get_by_text("실행 조건(코드가 판정)")).to_be_visible()


with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport=VIEW, device_scale_factor=2)  # 발표 화면에서 글자가 뭉개지지 않게
    page.goto(BASE + "/")
    page.locator("input[type=file]").set_input_files(str(CSV))
    page.get_by_role("button", name="올리기").click()
    expect(page.get_by_text("열 측정값")).to_be_visible()
    page.locator("section.card", has_text="목적과 업무 규칙").get_by_role("button", name="그룹별 합계").click()
    page.get_by_label("한 행의 의미(grain)").fill("거래 1건")
    page.get_by_label("값 단위").fill("원")
    page.locator("label", has_text="거래번호").locator("input[type=checkbox]").check()
    # 발표 화면에 「열 측정값 · 업무 규칙」이 보이게 이미 쓴 샘플 · 올리기 줄만 잠시 접는다(값은 그대로)
    page.evaluate("[...document.querySelectorAll('section.card')].find(s => s.textContent.includes('샘플 데이터 고르기')).parentElement.style.display = 'none'")
    shot(page, "home")
    page.evaluate("[...document.querySelectorAll('section.card')].find(s => s.textContent.includes('샘플 데이터 고르기')).parentElement.style.display = ''")
    page.get_by_role("button", name="활용 로드맵 만들기").click()
    page.wait_for_url(re.compile(r"/roadmaps/"))
    page.locator(".react-flow__node").first.wait_for()
    page.wait_for_timeout(600)
    shot(page, "roadmap")
    node(page, "C05 · ")
    shot(page, "star")
    node(page, "C03 · 문자 숫자")
    shot(page, "node")
    for pid in ("C05", "D03", "D01", "C03", "I01"):   # 매번 ★ 추천 노드를 실행 → 새 상태에서 다시 판단
        node(page, f"{pid} · ")
        assert page.locator("aside .sug").count(), f"{pid} 가 ★ 추천이 아니다 — 흐름이 바뀌었다"
        run(page, pid)
    page.wait_for_timeout(600)
    shot(page, "after-runs")
    node(page, "N02 · 보고서용")
    run(page, "N02")
    page.get_by_role("link", name="실행 기록 · 결과 파일").click()
    expect(page.locator("img[alt='N02 차트']")).to_be_visible()
    page.wait_for_timeout(400)
    shot(page, "run")
    b.close()
