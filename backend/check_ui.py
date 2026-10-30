"""브라우저 확인(A8 · A10) — Playwright 로 실제 화면을 조작한다. 서버가 127.0.0.1:8765(또는 JEV_BASE)에 떠 있어야 한다.

  py -3 check_ui.py [캡처 폴더]

이것은 「돌려 봤다」이지 「사람이 확인했다」가 아니다. 결과는 docs/check-ui-report.json.
"""
import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("JEV_BASE", "http://127.0.0.1:8765")  # 다른 포트로 띄운 시험 서버면 JEV_BASE
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "data" / "ui-shots"
SHOTS.mkdir(parents=True, exist_ok=True)
RES = []


def check(name, cond, detail=""):
    RES.append({"name": name, "ok": bool(cond), "detail": str(detail)[:300]})
    print(("  ✔ " if cond else "  ✘ ") + name + (f" — {detail}" if not cond and detail else ""))


def plan_id(page):
    return re.search(r"/roadmaps/([\w-]+)", page.url)[1]


def click_node(page, text):
    page.locator(".react-flow__node", has_text=text).first.click()


def run_and_wait(page, pid_text):
    """노드 패널의 실행 버튼 → 새 계획 주소로 바뀔 때까지 기다린다(이전 화면 글자에 속지 않게)."""
    before = plan_id(page)
    page.get_by_role("button", name=re.compile(rf"{pid_text} 실행")).click()
    page.wait_for_url(lambda u: "/roadmaps/" in u and before not in u)
    page.locator(".react-flow__node").first.wait_for()
    return plan_id(page)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 950})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        print("[A8 시작 화면 → 예제 A → 로드맵]")
        page.goto(BASE + "/")
        check("모든 화면 상단에 「모의 판단」 띠", page.locator(".band").inner_text().startswith("모의 판단"))
        live_txt = page.locator(".band .live").inner_text()
        check("띠에 LIVE 키 상태 표시(키 있음 · 모델 / 키 없음 — 꺼짐)", "키 있음 · 모델" in live_txt or "키 없음 — 꺼짐" in live_txt or "연결 준비 · " in live_txt, live_txt)
        page.locator("section.card", has_text="샘플 데이터").locator("button", has_text="불러오기").first.click()
        expect(page.get_by_text("열 측정값")).to_be_visible()
        check("업로드(샘플) 후 열 측정값 표 · measured 표시", page.get_by_text("measured").count() > 0)
        page.screenshot(path=str(SHOTS / "1-home.png"), full_page=True)
        sel = page.locator("select:has(option[value=live])")
        key_on = page.request.get(BASE + "/api/health").json()["live_key_present"]  # 띠는 Codex · OpenAI 를 먼저 보여 줘서 Jev 키 유무를 알 수 없다
        check("판단 선택: 기본 MOCK · LIVE 는 키가 있을 때만 고를 수 있음(D11)",
              sel.input_value() == "mock" and sel.locator("option[value=live]").evaluate("o => o.disabled") != key_on)  # is_disabled() 는 option 에 늘 거짓이라 DOM 값을 본다
        if key_on:  # LIVE 를 고르면 동의 전에는 만들기 버튼이 잠긴다 — 호출은 하지 않고 MOCK 으로 되돌린다
            sel.select_option("live")
            locked = page.get_by_role("button", name="활용 로드맵 만들기").is_disabled()
            sel.select_option("mock")
            check("LIVE 선택 시 외부 전송 동의 전엔 만들기 잠김", locked)
        page.get_by_role("button", name="활용 로드맵 만들기").click()
        page.wait_for_url(re.compile(r"/roadmaps/"))
        expect(page.locator(".react-flow__node").first).to_be_visible()
        n_nodes = page.locator(".react-flow__node").count()
        check("로드맵 화면에 분기 그래프(노드 여러 개)", n_nodes >= 5, n_nodes)
        check("줌 · 전체 보기 컨트롤", page.locator(".react-flow__controls-zoomin").count() == 1 and page.locator(".react-flow__controls-fitview").count() == 1)
        # G17~G19 전체 화면: 그래프 칸만 화면을 채우고 · 보이는 노드가 모두 화면 안 · 같은 단추로 나옴
        page.get_by_role("button", name="⛶ 전체 화면").click()
        page.wait_for_function("document.fullscreenElement && document.fullscreenElement.querySelector('.react-flow')")
        page.wait_for_timeout(500)
        fs = page.evaluate("""() => { const el = document.fullscreenElement, b = el.getBoundingClientRect()
          const ns = [...el.querySelectorAll('.react-flow__node')].map(n => n.getBoundingClientRect())
          return { fill: b.width === innerWidth && b.height === innerHeight, nodes: ns.length, inside: ns.every(r => r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight), aside: !!el.querySelector('aside') } }""")
        page.screenshot(path=str(SHOTS / "2b-fullscreen.png"))
        page.get_by_role("button", name="전체 화면 끝(Esc)").click()
        page.wait_for_function("!document.fullscreenElement")
        check("G17~G19 그래프 전체 화면: 화면 꽉 · 보이는 노드 모두 화면 안 · 설명 칸 없음 · 단추로 나옴", fs["fill"] and fs["inside"] and fs["nodes"] >= 5 and not fs["aside"], fs)
        page.screenshot(path=str(SHOTS / "2-roadmap.png"), full_page=True)
        click_node(page, "C03 · 문자 숫자")
        expect(page.get_by_text("실행 조건(코드가 판정)")).to_be_visible()
        panel = page.locator("aside").inner_text()
        check("노드 상세: 카드 ID · 제목 · 게이트 · 근거 규칙 · 입출력 계약", all(s in panel for s in ("C03 · 문자 숫자·백분율 해석", "실행기 구현됨", "R-SUM-NEEDS-NUMERIC", "입력 · 출력 계약")), panel[:200])
        check("confidence 는 「정답률 아님」과 함께 · MOCK 은 없음 표시", "없음(모의 판단)" in panel and "정답률 아님" in panel)
        note = page.get_by_test_id("star-note")
        check("Q7 깊이 1 노드: ★ 경로와 견준 경로 추천 점수 · 「성공확률이 아닙니다」", note.count() == 1 and "경로 추천 점수" in note.inner_text() and "성공확률이 아닙니다" in note.inner_text(), note.count() and note.inner_text())
        page.screenshot(path=str(SHOTS / "3-node-panel.png"), full_page=True)
        with page.context.expect_page() as newp:
            page.get_by_role("link", name="미리보기 ↗").first.click()
        pv = newp.value
        pv.wait_for_load_state("load")
        txt = pv.locator("body").inner_text()
        check("D17 경로 비교 1순위 「미리보기 ↗」: 새 탭 · 모의 판단 띠 · 기록 안 됨 안내 · 목표 결과 표(교과 2,000)",
              "모의 판단(MOCK)" in txt and "남지 않았습니다" in txt and "목표 결과 표" in txt and "2,000" in txt and "검증 완료" not in txt, txt[:300])
        pv.screenshot(path=str(SHOTS / "3b-path-preview.png"), full_page=True)
        pv.close()
        run_and_wait(page, "C03")
        check("실행 후 새 계획 버전으로 이동 · 실행 이력 노드(실제 실행)", page.locator(".react-flow__node", has_text="실제 실행").count() >= 2)
        click_node(page, "I01 · 그룹별")
        run_and_wait(page, "I01")
        check("I01 실행 뒤 현재 상태에 결과(agg_sum)", "결과: agg_sum" in page.locator("section.card.small").first.inner_text())
        # 경로 비교
        boxes = page.get_by_label("비교")
        if boxes.count() >= 2:
            boxes.nth(0).check()
            boxes.nth(1).check()
        check("경로 비교: 두 경로를 나란히", page.get_by_text(re.compile(r"경로 #\d+")).count() >= 2)
        click_node(page, "N02 · 보고서용")
        pid = run_and_wait(page, "N02")
        # 내보내기
        with page.expect_download() as dl:
            page.get_by_role("link", name="roadmap.json").click()
        data = json.loads(Path(dl.value.path()).read_text(encoding="utf-8"))
        check("roadmap.json 내려받기 · projected 표시 보존 · MOCK 표기", data["mode"].startswith("MOCK") and any(n["status"] == "projected" for n in data["nodes"]))
        rh = page.request.get(f"{BASE}/api/plans/{pid}/export/roadmap.html").text()
        check("roadmap.html 은 앱 없이 열리는 정적 결과(트리 + 표 대체 보기)", "노드 표(대체 보기)" in rh and "<script" not in rh)
        page.screenshot(path=str(SHOTS / "4-after-runs.png"), full_page=True)
        page.get_by_role("link", name="실행 기록 · 결과 파일").click()
        expect(page.get_by_text("단계 실행")).to_be_visible()
        check("실행 기록: A03 · C03 · I01 · N02 가 검증 완료", page.locator("tbody tr", has_text="검증 완료").count() >= 4)
        check("차트 이미지가 화면에 보임", page.locator("img[alt='N02 차트']").count() == 1)
        page.screenshot(path=str(SHOTS / "5-run.png"), full_page=True)
        with page.expect_download() as dl:
            page.get_by_role("link", name="run_manifest.json 내려받기").click()
        man = json.loads(Path(dl.value.path()).read_text(encoding="utf-8"))
        check("run_manifest.json: 단계 · 산출물 · 버전 · CSV 이스케이프 정책", len(man["step_runs"]) >= 4 and man["artifacts"] and man["csv_escape_policy"])
        # N05 필터 화면(예제 A 결과로): 교과만 → 합계 2000, 새로고침 후에도 같음
        rid = re.search(r"/runs/([\w-]+)", page.url)[1]
        page.goto(BASE + f"/roadmaps/{pid}")
        page.locator(".react-flow__node").first.wait_for()
        ready_n05 = page.locator(".react-flow__node").filter(has_text="N05").filter(has_text="실행 가능")
        if ready_n05.count() == 0:
            # 지금 할 수 있는 상위 3개 가지 밖이면 「후보 더 보기」로 붙인다(화면의 버튼)
            click_node(page, "현재 상태(측정)")
            page.locator("aside tr", has_text="N05").get_by_role("button", name="가지 추가").click()
            ready_n05.first.wait_for()
            check("후보 더 보기로 N05 가지를 붙임(실행 가능)", ready_n05.count() >= 1)
        ready_n05.first.click()
        newest = run_and_wait(page, "N05")
        man = page.request.get(f"{BASE}/api/runs/{rid}").json()
        view = next(a for a in man["artifacts"] if a["name"] == "view.html")
        v = b.new_page()
        v.goto(f"{BASE}/api/artifacts/{view['artifact_id']}")
        check("N05 전체 합계 2,500", v.locator("#t").inner_text() == "2,500")
        v.select_option("#f", "교과")
        ok1 = v.locator("#t").inner_text() == "2,000"
        v.reload()
        check("N05 교과만 고르면 2,000 · 새로고침 뒤에도 같은 필터", ok1 and v.locator("#t").inner_text() == "2,000" and v.locator("#f").input_value() == "교과")
        v.close()
        print("[파일 올리기 — CP949 CSV · 구조 불명확 XLSX]")
        up = b.new_page(viewport={"width": 1280, "height": 900})
        cp = SHOTS / "cp949_upload.csv"
        cp.write_bytes("번호,부서,금액\n1,교과,1000\n2,비교과,2000\n".encode("cp949"))
        up.goto(BASE + "/")
        up.set_input_files("input[type=file]", str(cp))
        up.get_by_role("button", name="올리기").click()
        expect(up.get_by_text("추정")).to_be_visible()
        check("CP949 CSV: 인코딩을 확정하지 않고 「추정」 + 선택지", up.get_by_role("button", name="이 인코딩으로 다시 읽기").count() == 1)
        up.locator("select").filter(has_text="인코딩 고르기").select_option("cp949")
        up.get_by_role("button", name="이 인코딩으로 다시 읽기").click()
        expect(up.locator("table").filter(has_text="자료형 후보")).to_be_visible()
        check("고른 인코딩으로 다시 읽으면 한글 열 이름(부서 · 금액)", up.locator("table").filter(has_text="자료형 후보").get_by_text("부서").count() >= 1)
        up.goto(BASE + "/")
        up.set_input_files("input[type=file]", str(Path(__file__).resolve().parents[1] / "examples" / "example_c_unclear.xlsx"))
        up.get_by_role("button", name="올리기").click()
        expect(up.get_by_text("미확정")).to_be_visible()
        check("구조 불명확 XLSX: 표 범위 미확정 · 같은 머리글 후보를 임의로 고르지 않음", up.get_by_text("임의로 고르지 않음").count() >= 1)
        up.get_by_label("머리글 행").fill("3")
        up.get_by_role("button", name="이 범위로 읽기(A02)").click()
        expect(up.locator("table").filter(has_text="자료형 후보")).to_be_visible()
        check("머리글 행을 지정하면 A02 로 읽혀 열 측정값이 나옴(거래번호 · 부서 · 금액 3행)", up.locator("table").filter(has_text="자료형 후보").get_by_text("거래번호").count() == 1 and up.get_by_text("읽은 행 3").count() == 1)
        up.screenshot(path=str(SHOTS / "9-upload-xlsx.png"), full_page=True)
        up.close()
        print("[카탈로그 · devplan]")
        page.goto(BASE + "/catalog")
        expect(page.get_by_text("작업 카탈로그")).to_be_visible()
        check("카탈로그: 153개 카드 목록", page.get_by_text("153개").count() >= 1 and page.locator("aside").count() == 1)
        page.get_by_placeholder("번호 · 제목 검색").fill("E04")
        page.locator("tbody tr", has_text="E04").first.click()
        expect(page.get_by_text("구현 메타")).to_be_visible()
        expect(page.locator("aside")).to_contain_text("데이터를 지우지 않는다")
        check("카드 상세: E04 는 계획 카드(정책 전에는 지우지 않음)", "계획 카드" in page.locator("aside").inner_text())
        check("W01~W20 표에 언급 카드 · 정답이 보임", "A01 · A03" in page.locator("section.card", has_text="조합 프로젝트").inner_text())
        page.screenshot(path=str(SHOTS / "6-catalog.png"), full_page=True)
        page.goto(BASE + "/devplan")
        check("/devplan: 같은 JSON 생성물 + 모의 판단 띠", "모의 판단(MOCK) 앱의 개발계획" in page.content() and "devplan — 데이터 활용 로드맵" in page.content())
        print("[A10 /learn 통계 실습 — 강의 원고의 손계산 값]")
        page.goto(BASE + "/learn")
        expect(page.get_by_text("강의 20단위")).to_be_visible()
        t = lambda k: page.get_by_test_id(k).inner_text()
        check("평균 7 · 분산 49", t("mean-b") == "7" and t("var-b") == "49", (t("mean-b"), t("var-b")))
        check("β=0.01 → 6.51 · β=0.05 → 4.55", t("u-b-0.01") == "6.51" and t("u-b-0.05") == "4.55", (t("u-b-0.01"), t("u-b-0.05")))
        check("같아지는 β = 1/49 = 0.02041", t("beta-star") == "0.02041", t("beta-star"))
        check("Score 1.1(0.1·0.7·0.2)", t("score-value") == "1.1", t("score-value"))
        check("Brier 0.16 · 0.1961", t("brier-0.8") == "0.16" and t("brier-0.99") == "0.1961", (t("brier-0.8"), t("brier-0.99")))
        check("기대손실 20(검토) · 2(자동처리 후보)", t("loss-0.8") == "20" and t("loss-0.98") == "2", (t("loss-0.8"), t("loss-0.98")))
        check("강의 20단위 목차", page.locator("ol li").count() >= 20)
        page.get_by_role("button", name="1. 예제 A 불러와 판단").click()
        page.get_by_role("button", name=re.compile(r"2\. 1순위 작업 C03 실행")).click()
        page.get_by_role("button", name=re.compile(r"2\. 1순위 작업 I01 실행")).click()
        expect(page.get_by_text("파이썬 합산 결과")).to_be_visible()
        check("2단계 실습: C03 → I01 → 교과 2,000 · 비교과 500 · 총 2,500 · 정답 일치", "일치" in page.locator("section.card", has_text="파이썬 합산 결과").inner_text())
        page.screenshot(path=str(SHOTS / "7-learn.png"), full_page=True)
        print("[T11 발표용 강의자료 — /learn 링크 · 파일로 열기]")
        with page.context.expect_page() as newp:
            page.get_by_role("link", name=re.compile("발표용 슬라이드 열기")).click()
        lec = newp.value
        lec.on("pageerror", lambda e: errors.append("lecture: " + str(e)))
        lec.wait_for_load_state("load")
        n_sl = lec.locator("section.slide").count()
        check("/learn 링크 → /lecture/ 강의자료가 새 탭으로 열림", "/lecture/" in lec.url and n_sl >= 30, (lec.url, n_sl))
        check("페이지 표시 = 1 / 슬라이드 수", lec.locator("#pageIndicator").inner_text() == f"1 / {n_sl}", lec.locator("#pageIndicator").inner_text())
        imgs = lec.evaluate("[...document.images].map(i => [i.getAttribute('src'), i.complete && i.naturalWidth > 0])")
        check("앱 캡처 이미지 모두 로드", imgs and all(ok for _, ok in imgs), imgs)
        lec.keyboard.press("End")
        check("End → 마지막 장", lec.locator("#pageIndicator").inner_text() == f"{n_sl} / {n_sl}")
        lec.keyboard.press("Home")
        idx = lec.evaluate("[...document.querySelectorAll('section.slide')].findIndex(s => s.querySelector('.quiz'))")
        for _ in range(idx):
            lec.keyboard.press("ArrowRight")
        before = lec.locator("#pageIndicator").inner_text()
        # 단계 공개(data-step)가 있는 장은 → 를 여러 번 눌러야 넘어간다 — 퀴즈 장에 도착했는지로 확인
        while not lec.locator("section.slide.active .quiz").count():
            lec.keyboard.press("ArrowRight")
        q = lec.locator("section.slide.active .quiz")
        hidden = not q.locator(".quiz-reveal").is_visible()
        page_before = lec.locator("#pageIndicator").inner_text()
        q.locator(".quiz-option[data-correct=false]").first.click()
        check("퀴즈: 처음엔 정답 숨김 → 고르면 정답 · 해설 · 선택지 잠금, 장은 그대로",
              hidden and q.locator(".quiz-reveal").is_visible() and q.locator(".quiz-option.is-correct").count() == 1
              and q.locator(".quiz-option:disabled").count() == q.locator(".quiz-option").count()
              and lec.locator("#pageIndicator").inner_text() == page_before, (before, page_before))
        mocks = lec.evaluate("[...document.querySelectorAll('section.slide')].filter(s => s.querySelector('img.shot')).map(s => !!s.querySelector('.mock-tag'))")
        check("앱 캡처가 있는 장마다 「모의 판단(MOCK)」 표시", mocks and all(mocks), mocks)
        lec.close()
        lec_file = Path(__file__).resolve().parents[1] / "lecture" / "index.html"
        f = b.new_page(viewport={"width": 1280, "height": 800})
        f.on("pageerror", lambda e: errors.append("lecture file: " + str(e)))
        f.goto(lec_file.as_uri())
        imgs = f.evaluate("[...document.images].map(i => i.complete && i.naturalWidth > 0)")
        check("앱 없이 파일로 열어도 동작(이미지 포함)", f.locator("section.slide.active").count() == 1 and imgs and all(imgs))
        # 15분 핵심판(D15) — 같은 엔진 · 같은 캡처, 계산 실습 없음
        f.goto(lec_file.with_name("15min.html").as_uri())
        n15 = f.locator("section.slide").count()
        imgs = f.evaluate("[...document.images].map(i => i.complete && i.naturalWidth > 0)")
        mocks = f.evaluate("[...document.querySelectorAll('section.slide')].filter(s => s.querySelector('img.shot')).map(s => !!s.querySelector('.mock-tag'))")
        check("15분 핵심판: 파일로 열림 · 20장 이하 · 퀴즈 1개 이상 · 캡처마다 모의 판단 · 이미지 로드",
              n15 <= 20 and f.locator(".quiz").count() >= 1 and f.locator("#pageIndicator").inner_text() == f"1 / {n15}"
              and imgs and all(imgs) and mocks and all(mocks), (n15, imgs, mocks))
        f.close()
        print("[모바일 390px]")
        m = b.new_page(viewport={"width": 390, "height": 844})
        for path in ("/", "/catalog", "/learn", f"/roadmaps/{newest}", "/lecture/", "/lecture/15min.html"):
            m.goto(BASE + path)
            m.wait_for_timeout(600)
            sw, cw = m.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
            check(f"390px {path}: 가로 넘침 없음", sw <= cw, (sw, cw))
        m.screenshot(path=str(SHOTS / "8-mobile-roadmap.png"), full_page=True)
        check("화면 스크립트 오류 없음", not errors, errors[:3])
        b.close()
    ok = all(r["ok"] for r in RES)
    out = Path(__file__).resolve().parents[1] / "docs" / "check-ui-report.json"
    out.write_text(json.dumps({"passed": sum(r["ok"] for r in RES), "total": len(RES), "all_passed": ok, "shots": str(SHOTS),
                               "note": "Playwright 로 돌려 본 결과(사람이 눈으로 확인한 것은 아님)", "results": RES}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{sum(r['ok'] for r in RES)}/{len(RES)} 통과")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
