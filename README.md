# Data Roadmap | 데이터 활용 로드맵

Turn a spreadsheet into a visible, verifiable sequence of data operations. The application measures the data, asks Codex to choose among allowed actions, runs a registered Python operation, and uses the observed result to plan the next step.

**[Try the public example](https://dataroadmap.axmaster.cloud/)** · [한국어 실습 워크숍](workshop/codex-data-roadmap.md) · [Codex Skill](skills/data-roadmap/SKILL.md) · [한국어 상세 안내](README_KO.md) · [Development record](docs/t15-process-log.md)

## Try it in your browser

1. Open the public example and select a numbered stage to see its checks and output.
2. Compare the final table and decision record. The synthetic dataset contains 1,000 transactions across 10 departments; its independently checked total is **148,982,900 KRW**.
3. Expand “만든 방법과 공개 예제의 범위” to read how the example was produced.

The public example shows a stored run: clicking a stage does not call a model. Uploading a file and creating a new Codex plan on the hosted site require administrator access.

## How it works

1. **Inspect:** Python reads CSV or XLSX and measures columns, types, missing values and duplicate keys.
2. **Choose:** The application filters candidates by implemented operations and preconditions. Codex selects the next action from those candidates.
3. **Execute and verify:** A registered Python handler executes the selected action. The app checks the result and preserves the original dataset and versioned outputs.
4. **Replan:** The next choice uses the observed result. The graph distinguishes completed work from unexecuted projections.

Codex's 1/0 selection indicators are not probabilities or success rates. The app can surface missing-information or unsupported-operation choices instead of inventing a result. The catalogue describes 153 cards; 12 handlers are implemented.

## Run locally on Windows

Prerequisites: Python 3.13 (`py -3`), Node.js 22 and npm. Open a terminal in the folder where you want the project and run:

```powershell
git clone https://github.com/stat-yongsan/dataroadmap.git
cd dataroadmap
.\run.bat
```

The first run installs dependencies and builds the frontend, then opens `http://127.0.0.1:8765`. Stop the server with Ctrl+C. The local app supports a mock decision mode without a model API key. Use the included synthetic examples for the first run.

For an existing Windows environment after installation, the backend checks can be run with:

```powershell
cd backend
.\.venv\Scripts\python.exe -X utf8 check.py
```

The checks cover application behaviour and simulated provider responses; they do not prove model decision quality.

## Project and evidence

The initial prototype was built with Claude Code. Codex implemented the Codex decision integration, the hosted public example and administrator access separation. The OpenAI Decisions API adapter was implemented with Claude Code and tested with a simulated server; a real OpenAI Decisions API call has not yet been verified. See the development records for details.

The public demo uses synthetic data. Uploaded datasets and local execution results are stored outside version control. The app is intended for use with synthetic examples; do not assume it is ready for sensitive or production data.
