"""Jev 발표의 통계 기초 실습. Python 표준 라이브러리만 사용합니다.

실행: python jev_stats_demo.py
실제 Jev 호출이나 모델 학습을 하지 않습니다. 모든 확률은 교육용 가정입니다.
"""

from math import isclose, log2


def moments(outcomes):
    """outcomes: [(결과값, 확률), ...]. 분포의 기댓값과 분산."""
    if not outcomes or not isclose(sum(p for _, p in outcomes), 1.0):
        raise ValueError("확률 합은 1이어야 합니다.")
    if any(p < 0 or p > 1 for _, p in outcomes):
        raise ValueError("확률은 0~1이어야 합니다.")
    mean = sum(value * p for value, p in outcomes)
    variance = sum(p * (value - mean) ** 2 for value, p in outcomes)
    return mean, variance


def main():
    print("[교육용 가정값] 이 프로그램은 Jev를 호출하지 않습니다.\n")
    # 결과값의 단위는 임의의 효용 점수입니다. Choice 확률과 혼동하지 않습니다.
    actions = {"안정형 A": [(6, 1.0)], "변동형 B": [(0, 0.5), (14, 0.5)]}
    for beta in (0.0, 0.01, 0.05):
        utilities = {}
        for name, outcomes in actions.items():
            mean, variance = moments(outcomes)
            utilities[name] = mean - beta * variance
            print(f"β={beta:.2f} {name}: 평균={mean:.2f}, 분산={variance:.2f}, "
                  f"효용={utilities[name]:.2f}")
        print("선택:", max(utilities, key=utilities.get), "\n")
    print(f"두 선택이 같아지는 β = 1/49 = {1 / 49:.5f}\n")

    # 같은 Score 평균이어도 분포는 다를 수 있습니다.
    score_distributions = {
        "중간 수준에 집중": [(0, 0.0), (1, 1.0), (2, 0.0)],
        "낮음·높음 사이에서 불확실": [(0, 0.5), (1, 0.0), (2, 0.5)],
    }
    for name, distribution in score_distributions.items():
        mean, variance = moments(distribution)
        entropy = -sum(p * log2(p) for _, p in distribution if p > 0)
        print(f"{name}: Score={mean:.1f}, 수준 번호의 분산={variance:.1f}, "
              f"엔트로피={entropy:.1f} bit")
    print("엔트로피는 여기서 계산한 통계량이며 Jev confidence의 공식이 아닙니다.\n")

    # 80% 예측 10개 중 실제 yes가 8개인 아주 작은 설명용 예제입니다.
    labels = [1] * 8 + [0] * 2
    for predicted_p in (0.8, 0.99):
        brier = sum((predicted_p - y) ** 2 for y in labels) / len(labels)
        print(f"확률={predicted_p:.2f}, 관측 빈도=0.80, 이진 Brier={brier:.4f}")
    print("10건은 개념 설명용입니다. 실제 보정 성능을 입증하는 표본이 아닙니다.\n")

    # 자동처리는 맞으면 손실 0, 틀리면 손실 100. 검토 비용은 확정 5로 가정.
    error_cost, review_cost = 100, 5
    for p_correct in (0.8, 0.98):
        auto_loss = (1 - p_correct) * error_cost
        decision = "자동처리 후보" if auto_loss < review_cost else "검토"
        print(f"p_correct={p_correct:.2f}: 자동처리 기대손실={auto_loss:.1f}, "
              f"검토비용={review_cost}, 선택={decision}")
    print("p_correct는 해당 업무에서 검증된 정답확률이라는 가정입니다.")
    print("실제 실행에는 허용된 작업, 선행조건, 데이터 검증도 필요합니다.")


if __name__ == "__main__":
    main()
