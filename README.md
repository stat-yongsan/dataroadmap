# Data Roadmap

An initial prototype of a new Data Roadmap built from scratch with Codex. It uses a catalogue of 17 work areas and 153 tasks organized with Astra, and helps a user turn a synthetic CSV and an analysis goal into an inspectable plan and a verified result.

[한국어 실습 워크숍](workshop/codex-data-roadmap.md) · [Codex Skill](skills/data-roadmap/SKILL.md)

This is a **new Codex-built prototype**. An earlier prototype of the project was built with Claude Code; the earlier work remains in the repository history. The catalogue index and synthetic sample are reused as data; the application code in this version was newly written with Codex.

## What it does

1. Reads a UTF-8 CSV, shows its columns and first five rows, and identifies numeric columns.
2. Offers two implemented goals: group totals and group counts. The user selects the group and, for totals, the numeric column.
3. Shows a plan before running it. Running the plan processes the data and checks the grouped total against the original total or row count.
4. Displays Astra's catalogue as 17 areas and 153 cards. The catalogue is broader than the two goals implemented in this prototype.

CSV files stay in the local app. The plans and calculations use deterministic code and do not call an AI model. Use synthetic data only. Unsupported goals, malformed rows, missing group values and unparseable numbers stop with an explanation.

The separate **GPT-6.1 Sol vs Jev** comparison sends the same question and measured summary to Codex CLI and TypeSafe Jev after explicit in-app consent. It sends column names and row count, not CSV rows. Install Codex CLI and sign in with the intended account; put `TYPESAFE_API_KEY` in an untracked `.env` next to the app (or its parent) and restart. To use an existing `.env` elsewhere without copying the key, set `DATA_ROADMAP_ENV_FILE` to that file's path before starting. Both providers are called once per comparison. Timings include Codex CLI startup, and the comparison does not measure decision accuracy or execute either model's choice. The integration has been checked with simulated responses; real provider calls have not yet been verified for this version.

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
