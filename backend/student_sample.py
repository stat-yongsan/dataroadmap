"""Deterministic fictional student records for the app's built-in demonstration."""
from __future__ import annotations

import csv
import io
import random

HEADERS = (
    "학생ID", "학과", "학년", "입학연도", "재학상태", "거주형태", "통학시간_분", "학업지원참여",
    "지원_성적구간", "성적구간", "출석구간", "주당학습시간", "출석률", "중간고사", "기말고사",
    "과제제출률", "평점", "이번학기학점", "누적취득학점", "등록금_원", "장학금_원", "실납부액_원",
    "대출금_원", "월생활비_원", "주당근로시간", "하루수면시간", "상담횟수", "멘토링횟수",
    "비교과참여횟수", "진로준비상태",
)
DEPARTMENTS = ("컴퓨터공학과", "경영학과", "간호학과", "기계공학과", "디자인학과", "통계학과", "사회복지학과", "생명과학과", "경제학과", "교육학과")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def student_csv() -> bytes:
    """Return 1,000 synthetic rows; visible differences are intentionally designed, not causal."""
    rng = random.Random(20261031)
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(HEADERS)
    for i in range(1000):
        dept = i % len(DEPARTMENTS)
        year = 1 + (i // 20) % 4
        supported = (i // 10) % 2 == 0
        support = "참여" if supported else "미참여"
        score = round(_clamp(rng.gauss(87 if supported else 61, 9), 35, 100), 1)
        midterm = round(_clamp(score + rng.gauss(-1, 4), 30, 100), 1)
        final = round(_clamp(score + rng.gauss(1, 4), 30, 100), 1)
        attendance = round(_clamp(rng.gauss(93 if supported else 76, 7), 40, 100), 1)
        assignment = round(_clamp(rng.gauss(94 if supported else 72, 8), 35, 100), 1)
        observed_score = (midterm + final) / 2
        grade = "우수" if observed_score >= 80 else "보통" if observed_score >= 65 else "주의"
        attendance_band = "양호" if attendance >= 90 else "보통" if attendance >= 75 else "주의"
        tuition = 2_900_000 + dept * 170_000 + year * 25_000
        scholarship = min(tuition, (1_500_000 if supported else 300_000) + (250_000 if grade == "우수" else 0) + (dept % 3) * 50_000)
        net_tuition = tuition - scholarship
        debt = min(net_tuition, rng.choice((0, 0, 250_000, 600_000, 1_000_000)))
        gpa = round(_clamp((midterm * 0.25 + final * 0.35 + assignment * 0.25 + attendance * 0.15) * 4.5 / 100, 0, 4.5), 2)
        semester_credits = rng.choice((12, 15, 18, 21))
        cumulative_credits = min(140, (year - 1) * 30 + semester_credits + rng.choice((0, 3, 6)))
        row = (
            f"S{i + 1:04d}", DEPARTMENTS[dept], year, 2027 - year, "재학", rng.choice(("기숙사", "자취", "가족동거")),
            rng.randrange(10, 111, 5), support, f"{support}·{grade}", grade, attendance_band,
            round(_clamp(rng.gauss(18 if supported else 9, 4), 1, 35), 1), attendance, midterm, final, assignment, gpa,
            semester_credits, cumulative_credits, tuition, scholarship, net_tuition, debt, rng.randrange(450_000, 1_050_001, 50_000),
            rng.randrange(0, 31, 2), round(rng.uniform(5.5, 8.5), 1), rng.randrange(0, 5),
            rng.randrange(2, 9) if supported else 0, rng.randrange(0, 9),
            rng.choice(("탐색", "준비", "지원중")) if year >= 3 else rng.choice(("탐색", "준비")),
        )
        writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")
