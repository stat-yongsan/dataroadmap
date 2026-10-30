---
name: data-roadmap
description: Use a running local Data Roadmap app to inspect a synthetic spreadsheet, select an analysis goal, execute permitted steps, and review their checks and results. Use when a user asks Codex to help run or explain this app's data roadmap workflow.
---

# Data Roadmap

Help the user inspect a synthetic CSV/XLSX and understand how the app turns it into a verified result. The local app and its API are the authority for permitted actions and recorded results.

1. Confirm that the app is running at `http://127.0.0.1:8765` and that the user intends to use synthetic data. If it is not running, explain how to start `run.bat`; do not assume a different server or upload a real work file.
2. Use the app UI or its `/api/examples`, `/api/datasets`, `/api/datasets/{dataset_id}/goals`, and `/api/plans/{plan_id}` endpoints to inspect data, choose a supported goal and make a plan. Start with `mock` unless the user separately authorizes an external model call and understands the transmitted fields.
3. Examine the plan's root state and depth-one nodes. When the user wants a step run, use `/api/plans/{plan_id}/nodes/{node_id}/run` only for an executable depth-one node. Read the resulting run and newer plan before suggesting the next step. Stop on missing information, unsupported operations, errors or unclear results; ask for the missing decision rather than guessing.
4. Report the input, steps actually executed, checks, outputs and limitations. Label unexecuted alternatives as plans; do not call model confidence or Codex's selection indicator a success probability. For sample A, compare the result against `examples/expected/A.json`.

Never call handlers directly, execute code produced by a model, expose keys, or use the hosted administrator API as a substitute for the local app. The app checks preconditions and records versioned execution at its API boundary.
