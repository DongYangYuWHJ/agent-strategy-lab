# Agent Architecture Lab

[中文历史说明](README.zh-CN.md)

Agent Architecture Lab is a Python harness for comparing coding-agent workflows under a common set of tasks, tools, and acceptance checks. It runs single-agent baselines and fixed-role OpenCode workflows, then reports final acceptance, API usage, estimated cost, and reasons for stopping.

The current experiments ask when planning and review justify their cost. The harness supports single-agent runs, planner-to-executor handoffs, independent review, and workflows in which several roles can edit and run tests.

## Quick start

Use Python 3.11 or newer. The commands below run from the repository root.

```powershell
python lab.py validate
python lab.py demo
```

The demo uses fixed model replies, requires no API credentials, and makes no paid calls. It writes a Markdown report and a JSON report under `artifacts/`. Use it to check the workflow and reporting on a fresh checkout.

For live OpenCode experiments, use the repository's supported OpenCode version, **2.0.32**, and install the optional token-counting dependencies when the selected catalog requires them.

```powershell
python -m pip install -e ".[token-counting]"
Copy-Item settings.example.json settings.local.json
```

Set the relevant provider key in `settings.local.json`, or use the corresponding environment variable. Then validate and run a one-task smoke experiment.

```powershell
python lab.py check-settings
python lab.py validate --experiment configs/workflow-single.json
python lab.py batch --experiment configs/workflow-single.json --output artifacts/workflow-smoke-01
```

The last command makes paid DeepSeek API calls and uses a **$0.20** batch budget. Choose a fresh output directory for a new batch. Windows users can also use `run-lab.cmd` in place of `python lab.py`. See the [experiment guide](docs/en/running-experiments.md) for setup, configuration, and how to read the reports.

## Selected results

These comparisons used four related Python development tasks involving ItsDangerous and Cachetools. A pass means that the delivered code passed all independent acceptance cases for its run.

| Comparison | Full passes | Estimated cost of runs with a valid final grade |
|---|---:|---:|
| Sol alone with self-tests, one run per task | 4/4 | $2.476 |
| Sol plans, Luna implements and self-reviews, first run per task | 4/4 | $0.447 |
| Sol plans, Luna implements and self-reviews, three runs per task | 11/12 | $1.357 |
| Luna plans, implements and self-reviews with a role handoff, three runs per task | 8/12 | $0.585 |
| Sol plans and independently reviews, Luna implements and revises | 12/12 | $3.869 |
| Strict role permissions | 11/12 | $3.961 |
| Flexible role permissions | 11/12 | $5.088 |

The four-task Sol-to-Luna handoff cost about **82% less** than the separately run Sol baseline, with both passing all four tasks. With three repeats, independent Sol review added one full pass at about **2.85 times** the cost of Luna self-review. Flexible permissions cost **28.5% more** than strict permissions with the same number of full passes.

The sample is small and drawn from development tasks. The [architecture results overview](docs/en/results.md#architecture-results-at-a-glance) lists current and earlier workflows with their denominators, costs, and batch conditions.

## Documentation

- [Run and configure experiments](docs/en/running-experiments.md)
- [Understand the architecture and execution boundaries](docs/en/architecture.md)
- [Read the results and limitations](docs/en/results.md)
- [Follow the experiment decisions and next questions](docs/en/experiment-plan.md)
- [Browse the original Chinese decision records](docs/experiment-decisions.md)

Experiment configs, task definitions, and source code are in the repository. Raw run artifacts are local and ignored by Git. The English results page includes the key numbers needed to read the comparisons from a fresh clone.
