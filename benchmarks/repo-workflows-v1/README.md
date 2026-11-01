# Repository workflows v1

Six original, offline Python mini-repository tasks: two local repairs, two cross-file changes, and two diagnosis tasks. These are development tasks with unmeasured difficulty, not sourced from upstream issues. No network access, third-party dependencies, or real sleeps are needed.

Each task contains a `source/` project with README, public tests and an `app.run(request)` entry point. Only manifest-listed business modules may be edited. Operator-owned validators and reference/mutant controls live outside `source/` and must not be exposed through agent tools.

The suite has 18 public scenarios and 139 final scenarios (including public regressions), plus complete cursor traversal checks. These validate observable behavior and regressions, not a required implementation style. Auditing accepted the six reference patches and rejected starters, partial fixes, early exits, and a disabled-cache implementation: 25 controls, 50 public/final check executions.

Generation: `scripts/build_repo_tasks.py` (refuses to overwrite an existing suite). Audit: `scripts/audit_repo_tasks.py --output <new-directory>`. Metadata and case counts are in `manifest.json`.

See [任务集与运行说明](../../docs/repo-tasks.md) and [实验配置](../../configs/workflow-repo-single.json). A first 12-cell model comparison was recorded on 2026-10-31: Sol 6 formal acceptances; DeepSeek 4, plus a transport interruption and a validation timing anomaly (hidden checks passed on the latter). No failed cell was replayed. Four clean pairs passed for both models; quality discrimination remains unproven. Full details and incomplete-cost caveats are in the linked task documentation.
