# Data Roadmap

An initial prototype of a new Data Roadmap built from scratch with Codex. It uses a catalogue of 17 work areas and 153 tasks organized with Astra, and helps a user turn a synthetic CSV or Excel file and an analysis goal into an inspectable plan and a verified result.

[한국어 실습 워크숍](workshop/codex-data-roadmap.md) · [Codex Skill](skills/data-roadmap/SKILL.md)

This is a **new Codex-built prototype**. An earlier prototype of the project was built with Claude Code; the earlier work remains in the repository history. The catalogue index and synthetic sample are reused as data; the application code in this version was newly written with Codex.

The prototype is available at [dataroadmap.axmaster.cloud](https://dataroadmap.axmaster.cloud/). The optional live model comparison is restricted to reviewers with an access password and a limited total number of comparisons; the local version can also be run using the instructions below.

## What it does

1. Reads UTF-8 CSV or the first sheet of an XLSX file, shows its columns and first five rows, and identifies numeric columns. XLSX formulas must first be saved as values; files are limited to 2 MB.
2. Offers two implemented goals: group totals and group counts. The user selects the group and, for totals, the numeric column.
3. Displays all 17 areas and marks which have supported steps for the selected goal. It enumerates supported task sequences (20 per page), shows measured data checks and verifies a selected sequence by actually running it on an in-memory copy. This is a limited search over implemented steps, not all combinations of 153 tasks. The result checks grouped totals against the original total or row count; routes including the chart step show the actual result visually.
4. Displays Astra's catalogue as 17 areas and 153 cards. Only a few cards have measurable checks; other cards are marked unassessed, not zero. The catalogue is broader than the two executable goals.

Files stay in the app. The planned sequences and calculations use deterministic code and do not call an AI model. Measured check percentages are not AI recommendations or success probabilities. Use synthetic data only. Unsupported goals, malformed rows, missing group values and unparseable numbers stop execution with an explanation.

The separate **GPT-6 Luna (OpenAI Decisions API) vs Jev 1.13.0** comparison sends the same measured summary and 17-area choice to the two APIs after explicit in-app consent. It sends column names, row count and measured checks, not file rows. Neither model's choice is automatically executed, and model probabilities are not success rates. Put `OPENAI_API_KEY` and `TYPESAFE_API_KEY` in an untracked `.env` next to the app (or its parent) and restart. To use an existing `.env` elsewhere without copying the keys, set `DATA_ROADMAP_ENV_FILE` to that file's path before starting. Each comparison calls each provider once; elapsed time includes network and response processing. This version has been tested with simulated API responses, not a live Decisions API call.

## Run on Windows

Prerequisites: Python 3.13, Node.js 22 and npm.

```powershell
git clone https://github.com/stat-yongsan/dataroadmap.git
cd dataroadmap
.\run.bat
```

The first run installs dependencies and builds the interface. Open `http://127.0.0.1:8765`, select **가상 예제 시작하기**, choose a goal, create the plan and select a path's **결과 미리보기** to check its result. The bundled synthetic sample has 1,000 transactions across 10 groups and a total of 148,982,900. Stop the app with Ctrl+C.

## Tests

After the first run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest -v test_app
```

The tests check the catalogue counts, the sample's known total and row count, and rejection of malformed data. They do not establish model quality.
