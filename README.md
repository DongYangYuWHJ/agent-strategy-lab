# Agent Architecture Lab

[中文说明](README.zh-CN.md)

Agent Architecture Lab is a Python harness for comparing coding-agent workflows under a common set of tasks, tools, and acceptance checks. It runs single-agent baselines and fixed-role OpenCode workflows, then reports final acceptance, API usage, estimated cost, and reasons for stopping.

The experiments ask when planning and review justify their cost. The harness supports single-agent runs, planner-to-executor handoffs, independent review, and task routing before planning.

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

**Main result.** On four paired repository tasks, Sol handled the planning turn, then Luna implemented, self-reviewed, and revised in the same session. Both this workflow and Sol alone passed all four tasks. The handoff cost **$0.447 versus $2.476**, about **82% less**. Planning cost was nearly the same. The savings came from moving implementation, review, and revision to Luna. [Four-task comparison](docs/en/results.md#sol-single-agent-comparison-with-the-same-self-test-workflow)

The following comparisons used four related Python repository tasks involving ItsDangerous and Cachetools. A pass means that the delivered code passed every independent acceptance case for its run.

| Comparison | Full passes | Estimated cost of runs with a valid final grade |
|---|---:|---:|
| Sol alone with self-tests, one run per task | 4/4 | $2.476 |
| Sol plans, Luna implements and self-reviews, first run per task | 4/4 | $0.447 |
| Sol plans, Luna implements and self-reviews, three runs per task | 11/12 | $1.357 |
| Luna plans, implements and self-reviews with a role handoff, three runs per task | 8/12 | $0.585 |
| Sol plans and independently reviews, Luna implements and revises | 12/12 | $3.869 |
| Strict role permissions | 11/12 | $3.961 |
| Flexible role permissions | 11/12 | $5.088 |

With three repeats, independent Sol review added one full pass at about **2.85 times** the cost of Luna self-review. Flexible permissions cost **28.5% more** than strict permissions with the same number of full passes.

**Task routing.** On a separate 14-task comparison, a two-tier router chose between Luna alone and the Sol-to-Luna handoff. It cost **$0.597 versus $0.799** for using the handoff on every task, about **25% less**, with **13/14 versus 14/14** passes. Fixed Luna alone cost **$0.316** and matched the router's pass or fail outcome on every task. [Fourteen-task comparison](docs/en/results.md#plan-20--two-tier-task-routing)

These comparisons use small, fixed task sets. The [results overview](docs/en/results.md#architecture-results-at-a-glance) gives denominators, costs, and batch conditions.

## Documentation

- [Run and configure experiments](docs/en/running-experiments.md)
- [Understand the architecture and execution boundaries](docs/en/architecture.md)
- [Read the results and limitations](docs/en/results.md)
- [Follow the experiment decisions and next questions](docs/en/experiment-plan.md)
- [Browse the original Chinese decision records](docs/experiment-decisions.md)

Experiment configs, task definitions, and source code are in the repository. Raw run artifacts are local and ignored by Git. The English results page includes the key numbers needed to read the comparisons from a fresh clone.
