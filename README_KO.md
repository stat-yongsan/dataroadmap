# 데이터 활용 로드맵

CSV · XLSX 를 올리면 **코드가 먼저 재고**, **Codex가 다음 작업을 고르고**, **Python이 실행·검증한 뒤 바뀐 상태에서 다시 판단하는** 과정을 분기 그래프로 보여 줍니다. 기존 모의 판단과 Jev 연결도 로컬 호환용으로 유지합니다.

## 공개 사이트와 관리자(2026-10-31)

- 공개 예제: https://dataroadmap.axmaster.cloud — 실제 Codex(gpt-6.1-sol)와 Python으로 검증한 1,000행 가상 지출 자료. 단계 버튼으로 각 결과를 살펴봅니다. 공개 조작으로 모델을 새로 호출하거나 파일을 올리지 않습니다.
- 관리자: `/admin`. 비밀번호는 저장소 밖 `D:\devOps\.env`의 `ROADMAP_ADMIN_PASSWORD`에만 보관합니다. 값은 로그·문서·대화에 적지 않습니다. HTTPS 전용 서명 쿠키는 12시간 유효합니다.
- 관리자만 파일 업로드·새 계획·실제 Codex 호출·명세/카탈로그 원문을 사용할 수 있습니다. 업로드 파일은 VPS에서 처리하며 모델에는 열·자료형·건수·업무 규칙·허용 후보의 측정 요약만 전송합니다(직접 적은 그룹·성공 값은 포함, 예시 행은 제외).
- Codex는 허용 ID 하나와 이유, 영역 필요 여부, 기여도 수준을 반환합니다. 그래프의 1/0은 선택/대안 지시자이며 확률·성공률·confidence가 아닙니다. 한 계획은 현재 상태에서 1회 판단하고, 등록 실행기 수행·검증 후 새 계획을 만듭니다.
- Codex CLI는 기존 ChatGPT 로그인으로 실행합니다. 읽기 전용 빈 작업 폴더·사용자 설정/플러그인/도구 비활성화·비밀 환경변수 제거를 적용합니다. 모델이 만든 코드를 실행하지 않으며 실패를 모의 판단으로 바꾸지 않습니다.
- 배포: `py -3 -X utf8 tools/dataroadmap-deploy.py deploy` → 고정 예제 실호출 검증 `publish` → HTTPS·인증 검사 `verify`(저장소 루트에서). 자체 검사는 `data-roadmap\backend\.venv\Scripts\python.exe -X utf8 tools\dataroadmap-check.py`입니다.
- VPS 컨테이너는 127.0.0.1:8785로만 연결하며 기존 Traefik에서 HTTPS를 처리합니다. 앱 데이터와 Codex 로그인 캐시는 전용 볼륨에 보존합니다. Linux 차트는 나눔고딕, Windows는 맑은 고딕을 사용합니다.

- 개발계획(진행 · 검증 증거): 앱의 `/devplan` 또는 `docs/devplan.html`
- 명세(원문, 고치지 않음): `docs/requirements-source.md` · 받은 자료 원본: `docs/source/`
- 플레이북 원문(읽기만): `D:\elec5_test\Excel_Automation_Playbook_KO.md`

## Windows 에서 켜기

1. `run.bat` 을 더블클릭합니다.
   - 처음 한 번은 파이썬 가상환경(`backend\.venv`)과 화면 빌드(`frontend\dist`)를 만듭니다(인터넷으로 패키지를 받음, 무료).
   - 준비되면 브라우저로 <http://127.0.0.1:8765> 가 열립니다. 이 PC 에서만 열리고 밖에서는 접속할 수 없습니다.
2. 끄려면 검은 창에서 `Ctrl+C`.

수동으로 켜기(같은 동작):

```powershell
cd D:\devOps\data-roadmap\backend
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

필요한 것: Python 3.13(`py -3`), Node 22 + npm(화면 빌드), 한글 글꼴 맑은 고딕(차트).

## 화면

| 주소 | 하는 일 |
|---|---|
| `/` | 샘플(예제 A~E) 고르기 또는 파일 올리기 → 열 측정값 · 표 범위 · 인코딩 확인 → 목적 · 업무 규칙(한 행의 의미 · 업무 키 · 단위) → 로드맵 만들기 |
| `/roadmaps/<계획>` | 분기 그래프(확대 · 축소 · 전체 보기 · 노드 선택 · 가지 접기 · 모든 가지 보기). 노드를 누르면 카드 · 실행 조건 6가지 · 선택 근거 규칙 · 확률 세부 · 입출력 계약. 「실행 가능」 노드만 실행 → 결과 검증 → 새 상태에서 다시 판단(새 계획 버전). 경로 비교 · 후보 더 보기 · 내려받기 |
| `/runs/<실행>` | 실제 단계 실행 · check · 결과 파일 · 데이터 버전 · 표 보기 |
| `/catalog` | 17개 영역 · 153개 카드 · W01~W20(원문 필드 + 구현 메타) |
| `/learn` | 60분 강의 목차 · 통계 실습(평균 · 분산 · β · Score · Brier · 기대손실) · 2단계 판단 실습 |
| `/devplan` | 개발계획(같은 JSON 에서 생성) |

화면 문구: 추천됨 · 실행 가능 · 실행 중 · 검증 완료 · 정보 필요 · 검토 필요 · 현재 환경에서 지원 안 됨 · 실패 · 아직 실행하지 않은 계획.
**경로 추천 점수**는 이 앱이 정한 Choice 확률의 기하평균이며 성공확률이 아닙니다. **confidence** 는 판단 확신 지표이며 정답률이 아닙니다(MOCK 에는 없음).

## 실행기 — 구현된 것과 명세만 있는 것

- **실행기 12개**: A02 엑셀 범위 읽기 · A03 CSV/TSV 인코딩 읽기 · C01 열 이름 표준화 · C03 문자 숫자·백분율 해석 · C05 식별자 앞자리 0 보존 · D01 스키마·자료형 검사 · D03 중복 키 검출 · I01 그룹별 기본 집계 · I02 중복을 제외한 대상 수 · H01 분모가 분명한 비율 · N02 정적 차트 · N05 HTML 결과 화면
- **계획 카드(실행 버튼 비활성, 부족한 조건 표시)**: B01 · D02 · E04(중복 해소 — 정책 · 감사 로그 전에는 데이터를 지우지 않음) · I03 · C04 · J01 · J03
- 나머지 134개는 **명세 있음 · 실행기 미구현** — 카탈로그에서 볼 수만 있습니다.

## MOCK / LIVE

- 기본은 **MOCK(모의 판단 · policy.v1)** 이고, 키가 있으면 계획을 만들 때 **LIVE(TypeSafe Jev)** 를 고를 수 있습니다.
- LIVE 켜는 순서:
  1. `D:\devOps\.env` 에 `TYPESAFE_API_KEY=…` 한 줄(대화창 · 코드에 키를 붙여넣지 않습니다). 모델을 바꾸려면 `JEV_MODEL=…`(없으면 `jev-latest`). 이름 목록은 `.env.example`.
  2. 앱을 껐다 켭니다(`run.bat`) — `.env` 는 켤 때 한 번 읽습니다. 상단 띠에 「LIVE 판단: 키 있음 · 모델 jev-latest」가 보이면 됩니다.
  3. 첫 화면 → 데이터 · 목적 → 「판단」에서 **LIVE — TypeSafe Jev** 선택 → 「보낼 필드 먼저 보기(호출 안 함)」 → 내용 확인 → 「동의」 체크 → 「활용 로드맵 만들기」.
  4. 로드맵 화면 위 띠가 「LIVE 판단(TypeSafe Jev · 돌려받은 모델명)」, 상태 칸에 「호출 n/10회」, confidence 숫자가 보입니다.
  - 호출 상한은 **계획당 10회**, 요청마다 30초. 단계를 실행할 때마다 같은 판단 방식으로 새 계획을 만들므로 그때마다 최대 10회가 더 듭니다.
  - LIVE 가 실패하면 MOCK 으로 바꾸지 않고 「판단 실패」로 보여 줍니다. 401 은 재시도하지 않고, 429 · 529 는 Retry-After 로 최대 2번 다시 시도합니다.
  - 보내는 것 = 측정 요약(열 이름 · 자료형 · 건수 · 빈칸 · 고유 수) · 업무 규칙 · 후보 작업 목록. 예시 행은 보내지 않습니다(셀 값은 직접 적은 그룹 목록 · 성공 값만).
- **LIVE 실호출은 아직 검증하지 않았습니다.** 화면 흐름과 어댑터는 가짜 서버(가짜 키)로만 시험했습니다.

## OpenAI Decisions API 판단

- `D:\devOps\.env` 에 `OPENAI_API_KEY=…` 한 줄을 넣고 앱을 껐다 켜면 「판단」에 **OpenAI Decisions API** 가 열립니다. 모델은 `gpt-6-luna`(`OPENAI_DECISIONS_MODEL` 로 바꿈) · 키는 stat.yongsan 계정 것만 씁니다.
- 키가 있어도 저절로 켜지지 않습니다. 고른 뒤 「보낼 필드 먼저 보기(호출 안 함)」 → 내용 확인 → 「동의」 체크를 해야 「활용 로드맵 만들기」가 켜집니다.
- Jev 처럼 실제 확률 분포와 confidence 를 돌려받아 분기 그래프를 만듭니다. 호출은 계획당 최대 10회이고, 단계를 실행할 때마다 같은 방식으로 새 계획을 만듭니다.
- 실패 · 거절(refusal)은 「판단 실패」로 남고 모의 판단으로 바꾸지 않습니다. 거절된 응답 원문은 기록에 남습니다.
- 시험은 가짜 서버로만 했습니다(`backend\check.py` · `py -3 backend\check_openai_ui.py`). **실제 OpenAI 호출과 판단 품질은 아직 검증하지 않았습니다.** 과정 기록 = `docs\t15-process-log.md`.

## 결정 속도 비교(Opus 5.5 vs Jev)

- 로드맵 화면 위 「Opus 5.5 vs Jev 결정 속도 비교 →」 → `/race/<계획>`. 왼쪽 Opus 5.5(`claude-opus-5-5`), 오른쪽 Jev.
- 필요한 것: `D:\devOps\.env` 의 `ANTHROPIC_API_KEY` 와 `TYPESAFE_API_KEY`(없는 쪽은 꺼짐). 패키지 `anthropic` 은 `backend\requirements.txt` 에 있음.
- 순서: Opus effort 고르기(기본 low — Opus 5.5 는 생각을 끌 수 없어 effort 로만 속도 조절) → 「두 곳으로 보내는 데 동의」 → 「1회 비교 시작」 또는 「5회 반복(중앙값)」.
- 두 쪽에 같은 질문 한 벌(그 계획을 만들 때의 상태에서 앱이 묻는 판단 질문)을 동시에 보냅니다. 스톱워치가 실시간으로 돌고, 서버가 잰 「첫 응답」 · 「결정 완료」 ms 가 남습니다. Jev 는 한 번에 답해 첫 응답 = 완료입니다.
- 결과는 비교 기록(race_runs)에만 남고 계획 · 경로에는 쓰지 않습니다. 한 번 누를 때 쪽마다 최대 5번 호출. 원화 비용은 표시하지 않습니다(호출 수 · 토큰만).
- Opus 의 확률은 모델이 글로 적은 값(보정 안 됨)이라 Jev 확률과 크기를 비교하지 않습니다. 정답 비교가 아니라 속도 비교입니다.

## 입력 바꾸기 · 다시 실행

- **다른 파일**: 첫 화면에서 CSV · XLSX 를 올립니다(20 MiB · 10만 행까지, 넘으면 잘라 읽지 않고 거절). 인코딩이 「추정」이면 골라서 다시 읽고, XLSX 표 범위가 불명확하면 시트 · 머리글 행 · 범위를 정해 읽습니다.
- **예제 값 바꾸기**: `examples\` 의 파일을 고치면 다음에 「불러오기」할 때 그 값으로 읽습니다. 정답 파일 `examples\expected\*.json` 은 실행 전에 정한 값이라, 입력을 바꾸면 정답 대조가 실패하는 것이 맞습니다(새 정답을 따로 정해야 함).
- **다시 실행**: 같은 입력 · 같은 규칙으로 같은 단계를 다시 요청하면 이전 완료 결과를 재사용합니다. 원본과 이전 결과는 덮어쓰지 않고, 실행마다 새 데이터 버전이 생깁니다.
- 목적을 바꾸면 계획을 따로 만듭니다(서로 다른 목적의 경로는 한 순위표에서 비교하지 않음).
- 앱 자료는 `data\` 폴더(올린 파일 · 버전 · 결과 · `app.sqlite`)에 쌓이고 git 에서 빠집니다.

## 검증

```powershell
cd D:\devOps\data-roadmap\backend
.venv\Scripts\python check.py      # 필수 검증(카드별 실행기 · 예제 A~E · 재계획 · 가짜 LIVE) → docs\check-report.json
py -3 check_ui.py                  # 서버를 켠 상태에서 브라우저 확인(Playwright) → docs\check-ui-report.json
```

- MOCK 예제가 통과한 것은 코드 기능 검증일 뿐, 실제 Jev 판단 품질의 증거가 아닙니다.
- `check_ui.py` 는 「돌려 봤다」입니다. 사람이 화면을 직접 써 보고 확인한 것과는 따로 적습니다.

## 폴더

```text
data-roadmap/
  backend/app/   settings · catalog(원문 → 카탈로그) · contracts(구현 메타) · profiling · handlers(실행기 12) ·
                 decisions(MOCK · TypeSafe · 응답 검증) · planning(후보 · 게이트 · beam) · engine · store(SQLite) · exports · main(API)
  backend/check.py · check_ui.py · requirements.txt(버전 고정)
  frontend/      React + TypeScript + Vite + @xyflow/react + @dagrejs/dagre (package-lock.json)
  catalog/       projects.json · index.json · cards/<ID>.md (생성물)
  examples/      예제 A~E 가상자료(시드 20260926) + expected/(실행 전 고정 정답)
  docs/          devplan.json(기준) → devplan.html · devplan.md(생성물) · requirements-source.md · source/
  data/          실행 자료(git 제외)
```

제한: Windows Excel 기능(COM · 실제 피벗 · 매크로)은 쓰지 않고, 실행했다고 표시하지도 않습니다. 공개 배포 · 외부 발송은 범위 밖입니다.
