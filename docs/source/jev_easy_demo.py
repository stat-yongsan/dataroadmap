"""Jev로 다음 엑셀 작업을 고르고, Python이 실행한 결과를 다시 판단합니다.

Python 3.10+ / 외부 패키지 없음
  python jev_easy_demo.py                 # 명시적인 고정 MOCK, 무료·오프라인
  python jev_easy_demo.py --live          # 실제 API 2회, 키·연결·이용 조건 필요

공식 규격 확인일: 2026-09-26 / https://docs.typesafe.ai/api
원본 파일이나 개인정보는 읽지 않습니다. 아래의 가상 3행만 전송합니다.
MOCK 확률과 confidence는 설명용 고정 fixture이며 실제 모델 결과가 아닙니다.
"""

import argparse
import getpass
import json
import math
import os
import re
from collections import defaultdict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


QUESTIONS = {
    "next_step": {
        "type": "choice",
        "instructions": (
            "주어진 goal을 위해 현재 rows에 적용할 바로 다음 작업 하나를 고르세요. "
            "금액이 통화 문자를 포함하는 문자열이면 C03을 먼저 고릅니다. "
            "금액이 숫자로 정리되었고 부서별 집계표가 아직 없으면 I01을 고릅니다. "
            "완성한 부서별 집계표가 있을 때 N02를 고릅니다. "
            "입력이 부족하거나 어느 작업도 맞지 않으면 needs_info를 고릅니다."
        ),
        "criteria": {
            "C03": "문자 금액을 명시된 원화 구문 규칙에 따라 숫자로 바꾸기",
            "I01": "숫자형 금액을 부서별로 합산하기",
            "N02": "이미 계산한 부서별 합계로 차트 만들기",
            "needs_info": "목표나 입력이 부족하여 다음 작업을 정할 수 없음",
        },
    },
    "readiness": {
        "type": "score",
        "instructions": "현재 rows는 부서별 금액 합계를 계산할 준비가 어느 수준입니까?",
        "criteria": [
            "부서 또는 금액 열이 없어서 집계를 시작할 수 없음",
            "필요한 열은 있지만 문자 금액을 숫자로 바꿔야 함",
            "필요한 열이 있으며 모든 금액이 숫자여서 집계 가능",
        ],
    },
    "goal_clear": {
        "type": "noul",
        "instructions": "goal에 집계할 값과 그룹 기준이 모두 명시되어 있습니까?",
    },
}


def mock_response(stage):
    chosen = "C03" if stage == 0 else "I01"
    probs = {"C03": 0.03, "I01": 0.03, "N02": 0.02, "needs_info": 0.02}
    probs[chosen] = 0.93
    level = 1 if stage == 0 else 2
    return {
        "model": "MOCK-FIXTURE-NOT-JEV",
        "answers": {
            "next_step": {"type": "choice", "choice": chosen,
                          "probabilities": probs, "confidence": 0.8},
            "readiness": {"type": "score", "score": float(level),
                          "probabilities": {str(i): float(i == level) for i in range(3)},
                          "legend": dict(enumerate(QUESTIONS["readiness"]["criteria"])),
                          "confidence": 1.0},
            "goal_clear": {"type": "noul", "noul": 1.0},
        },
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


def live_response(state, key):
    payload = {"model": os.environ.get("JEV_MODEL", "jev-latest"),
               "state": state, "questions": QUESTIONS}
    request = Request(
        "https://api.typesafe.ai/v1/systemone",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    # 첫 실습에서는 자동 재시도하지 않고 실패를 그대로 표시합니다.
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def validate_response(response):
    answers = response["answers"]
    for name in ("next_step", "readiness"):
        answer = answers[name]
        expected_type = "choice" if name == "next_step" else "score"
        if answer["type"] != expected_type:
            raise ValueError("응답 타입이 요청과 다릅니다.")
        probs = answer["probabilities"]
        expected_keys = set(QUESTIONS["next_step"]["criteria"]) if name == "next_step" else {"0", "1", "2"}
        if set(probs) != expected_keys:
            raise ValueError("응답 선택지가 요청 선택지와 다릅니다.")
        values = list(probs.values())
        if any(not math.isfinite(p) or not 0 <= p <= 1 for p in values):
            raise ValueError("유효하지 않은 확률입니다.")
        if not math.isclose(sum(values), 1, abs_tol=1e-3):
            raise ValueError("확률 합이 1이 아닙니다.")
        if not 0 <= answer["confidence"] <= 1:
            raise ValueError("confidence 범위를 확인하세요.")
    choice = answers["next_step"]
    if choice["choice"] not in choice["probabilities"]:
        raise ValueError("허용되지 않은 작업입니다.")
    if choice["probabilities"][choice["choice"]] < max(choice["probabilities"].values()) - 1e-3:
        raise ValueError("choice가 최대 확률 선택지가 아닙니다.")
    score = answers["readiness"]
    calculated_score = sum(int(level) * p for level, p in score["probabilities"].items())
    if not math.isclose(score["score"], calculated_score, abs_tol=0.02):
        raise ValueError("Score와 분포가 일치하지 않습니다.")
    if answers["goal_clear"]["type"] != "noul" or not 0 <= answers["goal_clear"]["noul"] <= 1:
        raise ValueError("Noul 응답을 확인하세요.")
    return answers


def parse_demo_won(value):
    """이 실습에서 정한 원화 정수 구문만 허용합니다. 범용 금액 파서가 아닙니다."""
    if not isinstance(value, str) or not re.fullmatch(r"(?:\d{1,3}(?:,\d{3})+|\d+)원", value):
        raise ValueError(f"가상자료의 금액 구문과 다릅니다: {value!r}")
    return int(value[:-1].replace(",", ""))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    key = ""
    if args.live:
        key = os.environ.get("TYPESAFE_API_KEY") or getpass.getpass("TypeSafe API 키(화면에 표시되지 않음): ")
        if not key.strip():
            raise ValueError("API 키가 없습니다. --live 없이 실행하면 MOCK 실습입니다.")
    print("[LIVE: 실제 Jev API]" if args.live else "[MOCK: 실제 Jev를 호출하지 않는 고정 예시]")
    rows = [
        {"department": "교과", "amount": "1,200원"},
        {"department": "교과", "amount": "800원"},
        {"department": "비교과", "amount": "500원"},
    ]
    history = []
    for stage, allowed_step in enumerate(("C03", "I01")):
        state = {"goal": "부서별 금액 합계를 구하고 싶다", "grain": "거래 1건",
                 "rows": rows, "history": history, "amount_unit": "KRW",
                 "amount_syntax": "원화 정수, 천단위 쉼표 허용, 마지막 글자 원"}
        response = live_response(state, key) if args.live else mock_response(stage)
        answers = validate_response(response)
        answer = answers["next_step"]
        chosen = answer["choice"]
        print(f"\n{stage + 1}단계 / 모델={response.get('model', 'unknown')}")
        print("Choice:", chosen, "/ 분포:", answer["probabilities"])
        print("confidence:", answer["confidence"], "(정답률과 동일하지 않음)")
        print("Score:", answers["readiness"]["score"], "/ Noul:", answers["goal_clear"]["noul"])
        # 0.80은 실습용 임계값이며 운영 성능을 보장하지 않습니다.
        if chosen != allowed_step or answer["probabilities"][chosen] < 0.80 or answers["goal_clear"]["noul"] < 0.80:
            print("needs_review: 교육용 허용 순서·확률 조건을 충족하지 않아 실행을 멈춥니다.")
            return
        if chosen == "C03":
            rows = [{**row, "amount": parse_demo_won(row["amount"])} for row in rows]
            print("Python 변환 결과:", rows)
        elif chosen == "I01":
            if not all(isinstance(row["amount"], int) for row in rows):
                raise ValueError("숫자 변환이 끝나지 않았습니다.")
            totals = defaultdict(int)
            for row in rows:
                totals[row["department"]] += row["amount"]
            print("Python 합산 결과:", dict(totals))
            assert dict(totals) == {"교과": 2000, "비교과": 500}, "가상자료 정답 불일치"
            print("정답 확인: 교과 2,000원, 비교과 500원, 총 2,500원")
        history.append({"project_id": chosen, "status": "succeeded"})
    print("\n학습: 모델은 작업을 선택하고, 코드는 계산하며, 다음 요청은 바뀐 상태를 봅니다.")


if __name__ == "__main__":
    try:
        main()
    except HTTPError as exc:
        raise SystemExit(f"API HTTP {exc.code}: 인증(401), 요청(422), 사용량(429), 일시 과부하(529)를 확인하세요. LIVE가 실패했으며 MOCK으로 대체하지 않았습니다.")
    except (URLError, TimeoutError) as exc:
        raise SystemExit(f"API 연결 또는 시간제한 오류: {type(exc).__name__}. LIVE 미완료.")
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"입력/응답 검증 실패: {exc}")
