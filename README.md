# Data Roadmap

An initial prototype of a new Data Roadmap built from scratch with Codex. It uses a catalogue of 17 work areas and 153 tasks organized with Astra, and helps a user turn a synthetic CSV or Excel file and an analysis goal into an inspectable plan and a verified result.

[한국어 실습 워크숍](workshop/codex-data-roadmap.md) · [Codex Skill](skills/data-roadmap/SKILL.md)

This is a **new Codex-built prototype**. An earlier prototype of the project was built with Claude Code; the earlier work remains in the repository history. The catalogue index and synthetic sample are reused as data; the application code in this version was newly written with Codex.

The prototype is available at [dataroadmap.axmaster.cloud](https://dataroadmap.axmaster.cloud/). The optional live model comparison is restricted to reviewers with an access password and a limited total number of comparisons; the local version can also be run using the instructions below.

## What it does

1. Reads UTF-8 CSV or the first sheet of an XLSX file, shows its columns and first five rows, and identifies numeric columns. XLSX formulas must first be saved as values; files are limited to 2 MB.
2. Offers two implemented goals: group totals and group counts. The user selects the group and, for totals, the numeric column.
3. Shows the fixed procedure and measured data checks before execution. Running it checks the grouped total against the original total or row count and charts the actual result.
4. Displays Astra's catalogue as 17 areas and 153 cards. Only a few cards have measurable checks; other cards are marked unassessed, not zero. The catalogue is broader than the two executable goals.

Files stay in the app. The fixed procedure and calculations use deterministic code and do not call an AI model. Measured check percentages are not AI recommendations or success probabilities. Use synthetic data only. Unsupported goals, malformed rows, missing group values and unparseable numbers stop execution with an explanation.

The separate **GPT-6.1 Sol vs Jev** comparison sends the same measured summary and 17-area choice to Codex CLI and TypeSafe Jev after explicit in-app consent. It sends column names, row count and measured checks, not file rows. Codex supplies a choice and model-generated explanation; Jev supplies its own choice and distribution. Jev's probabilities are not success rates or Codex scores. Neither model's choice is automatically executed. Install Codex CLI and sign in with the intended account; put `TYPESAFE_API_KEY` in an untracked `.env` next to the app (or its parent) and restart. To use an existing `.env` elsewhere without copying the key, set `DATA_ROADMAP_ENV_FILE` to that file's path before starting. Each comparison calls both providers once. Timings include Codex CLI startup and do not measure accuracy. On one real synthetic-data test both selected I (aggregation); this is not evidence of general reliability.

## Run on Windows

Prerequisites: Python 3.13, Node.js 22 and npm.

```powershell
git clone https://github.com/stat-yongsan/dataroadmap.git
cd dataroadmap
.\run.bat
```

The first run installs dependencies and builds the interface. Open `http://127.0.0.1:8765`, select **가상 예제 시작하기**, choose a goal, create the plan and run it. The bundled synthetic sample has 1,000 transactions across 10 groups and a total of 148,982,900. Stop the app with Ctrl+C.

## Tests

After the first run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest -v test_app
```

The tests check the catalogue counts, the sample's known total and row count, and rejection of malformed data. They do not establish model quality.
