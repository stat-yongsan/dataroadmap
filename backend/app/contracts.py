"""구현 메타데이터(원문 §5) — 원문에서 뽑은 카드 필드와 분리한다. metadata_origin = implementation_design.

카드 본문에 적히지 않은 의존관계를 원문 사실처럼 쓰지 않는다. 여기 적힌 조건 · 효과는 이 앱의 설계다.
"""

from . import settings

IMPL = {
    "A02": {"handler_id": "a02_read_range", "input_contract": "XLSX 파일 + 시트 + 머리글 행 또는 범위",
            "output_contract": "상세 표(원본 값 그대로 · 행별 원본 셀 위치)", "required_parameters": ["sheet", "header_row 또는 range"],
            "preconditions": ["파일이 XLSX", "시트가 있고 범위에 데이터 행이 있음"], "effects": ["표 범위 확정", "상세 표 v0"],
            "capability_requirements": ["python", "openpyxl"], "side_effect_class": "new_version"},
    "A03": {"handler_id": "a03_read_text", "input_contract": "CSV/TSV 바이트 + 인코딩 · 구분자 · 따옴표 규칙",
            "output_contract": "상세 표(모든 칸 문자열 — 앞자리 0 보존)", "required_parameters": ["encoding(자동 판별 또는 지정)"],
            "preconditions": ["인코딩이 확정됨", "따옴표가 닫힘 · 행마다 칸 수 같음"], "effects": ["상세 표 v0"],
            "capability_requirements": ["python"], "side_effect_class": "new_version"},
    "C01": {"handler_id": "c01_rename", "input_contract": "상세 표 + 별칭 사전", "output_contract": "열 이름을 바꾼 새 버전",
            "required_parameters": ["aliases"], "preconditions": ["별칭 충돌 없음"], "effects": ["열 이름 표준화"],
            "capability_requirements": ["python"], "side_effect_class": "new_version"},
    "C03": {"handler_id": "c03_parse", "input_contract": "상세 표 + 값 열 + 구문 규칙(쉼표 · 괄호 음수 · % · 원 접미사)",
            "output_contract": "값 열이 숫자(null 구분)인 새 버전 — 해석 불가 값이 있으면 새 버전 없이 검토 필요",
            "required_parameters": ["value_col"], "preconditions": ["값 열이 있음"], "effects": ["값 열 numeric (C03 통과 시)"],
            "capability_requirements": ["python"], "side_effect_class": "new_version"},
    "C05": {"handler_id": "c05_identifiers", "input_contract": "상세 표 + 식별자 열", "output_contract": "check(문자열 유지 · 자릿수 · 손상 의심)",
            "required_parameters": ["식별자 열(자동: 키 · 대상 열)"], "preconditions": ["식별자 열이 있음"], "effects": ["식별자 보존 확인"],
            "capability_requirements": ["python"], "side_effect_class": "read_only_check"},
    "D01": {"handler_id": "d01_schema", "input_contract": "상세 표 + 목표가 요구하는 열 규격", "output_contract": "check(missing_column · type_mismatch · 선택 열 경고)",
            "required_parameters": ["목표 인자(열 이름)"], "preconditions": ["표 확정"], "effects": ["필수 열 확인"],
            "capability_requirements": ["python"], "side_effect_class": "read_only_check"},
    "D03": {"handler_id": "d03_duplicates", "input_contract": "상세 표 + 업무 키", "output_contract": "check(중복 그룹 · 모든 원본 행 · 완전 중복/값 다름 구분) — 삭제하지 않음",
            "required_parameters": ["key"], "preconditions": ["키 열이 있음"], "effects": ["키 중복 점검 결과"],
            "capability_requirements": ["python"], "side_effect_class": "read_only_check"},
    "I01": {"handler_id": "i01_aggregate", "input_contract": "상세 표 + 그룹 열 + 축약 통계(건수 · 합계 · 평균)",
            "output_contract": "그룹 1행 집계표 + check(행 보존 · 합계 불변식 · 빈 그룹 구분)", "required_parameters": ["group_col"],
            "preconditions": ["합계·평균이면 값 열이 숫자", "업무 키 중복 없음(측정)"], "effects": ["그룹별 집계표"],
            "capability_requirements": ["python"], "side_effect_class": "new_version"},
    "I02": {"handler_id": "i02_distinct", "input_contract": "상세 표 + 대상 키 열(+그룹)", "output_contract": "대상 수 표 + check(행 수와 구분 · 빈 키 제외)",
            "required_parameters": ["entity_col"], "preconditions": ["대상 열이 숫자로 손상되지 않음"], "effects": ["고유 대상 수"],
            "capability_requirements": ["python"], "side_effect_class": "new_version"},
    "H01": {"handler_id": "h01_ratio", "input_contract": "그룹 × 상태 건수표 + 분자 정의(성공 상태) + 분모 정의(그룹 전체) + 0분모 정책",
            "output_contract": "그룹별 비율 + 전체(합친 분자/분모) · 0분모 null", "required_parameters": ["status_col", "success_values"],
            "preconditions": ["그룹 × 상태 건수표가 있음"], "effects": ["비율표"],
            "capability_requirements": ["python"], "side_effect_class": "new_version"},
    "N02": {"handler_id": "n02_chart", "input_contract": "집계표(목표 결과)", "output_contract": "PNG 막대차트 + check(표시값 · 0 기준 축 · 한글 글꼴 · 라벨 잘림)",
            "required_parameters": ["단위"], "preconditions": ["목표 결과 표가 있음"], "effects": ["차트 파일"],
            "capability_requirements": ["python", "matplotlib", f"font:{settings.KOREAN_FONT}"], "side_effect_class": "artifact_only"},
    "N05": {"handler_id": "n05_html", "input_contract": "집계표(목표 결과)", "output_contract": "표 · 합계 · 필터가 있는 로컬 HTML(데이터는 글자로만 표시)",
            "required_parameters": [], "preconditions": ["목표 결과 표가 있음"], "effects": ["HTML 결과 화면"],
            "capability_requirements": ["python"], "side_effect_class": "artifact_only"},
}

# 계획에만 보이는 카드 — 실행 버튼 비활성, 부족한 조건을 보여 준다(원문 §8.1 · §11)
PLANNED = {
    "B01": {"why_not": "실행기 미구현 — 머리글 후보가 여럿이면 임의로 고르지 않고 범위 지정을 요구한다", "input_contract": "시트 + 필수 열 집합", "output_contract": "머리글 행 + 선택 근거"},
    "D02": {"why_not": "실행기 미구현", "input_contract": "상세 표 + 필수 필드", "output_contract": "행별 누락 오류표"},
    "E04": {"why_not": "기본 실행기에서 뺌 — 중복 해소 정책 · 감사 로그가 정해지기 전에는 데이터를 지우지 않는다(원문 §11)",
            "input_contract": "상세 표 + 키 + 해소 정책(예: 최신 수정행)", "output_contract": "남긴 행 · 제거한 행 · 선택 근거"},
    "I03": {"why_not": "실행기 미구현 — 지금은 I01(그룹 × 상태 건수)로 H01 의 분자 · 분모를 만든다(원문 §12 예제 D)",
            "input_contract": "상세 표 + 조건", "output_contract": "조건부 건수 · 금액"},
    "C04": {"why_not": "실행기 미구현", "input_contract": "날짜 문자열 + 허용 형식 + Asia/Seoul", "output_contract": "ISO 날짜 · 시각"},
    "J01": {"why_not": "실행기 미구현", "input_contract": "날짜가 표준화된 표", "output_contract": "월 단위 재집계(흐름은 합 · 잔액은 마지막 관측)"},
    "J03": {"why_not": "실행기 미구현", "input_contract": "기간별 집계", "output_contract": "전기 대비 차이 · 증감률"},
}


def status_of(pid: str) -> str:
    return "implemented" if pid in IMPL else "planned" if pid in PLANNED else "spec_only"


def meta(pid: str) -> dict:
    if pid in IMPL:
        return {**IMPL[pid], "project_id": pid, "implementation_status": "implemented", "handler_version": "handlers.v1",
                "metadata_origin": "implementation_design"}
    if pid in PLANNED:
        return {**PLANNED[pid], "project_id": pid, "implementation_status": "planned", "handler_id": None,
                "metadata_origin": "implementation_design"}
    return {"project_id": pid, "implementation_status": "spec_only", "handler_id": None, "input_contract": None,
            "output_contract": None, "preconditions": [], "effects": [], "required_parameters": [],
            "metadata_origin": "implementation_design", "why_not": "명세 있음 · 실행기 미구현"}
