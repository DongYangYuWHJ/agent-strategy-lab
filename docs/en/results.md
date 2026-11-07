# Experiment results

[Home](../../README.md) · [Architecture](architecture.md) · [Experiment plan](experiment-plan.md)

The current comparisons use four Python development tasks. Each task begins from the same starting source for its comparison. A full pass requires every final acceptance case to pass. A valid grade can be a pass or a failure. Infrastructure and budget stops without a final grade are tracked separately.

| Task | Final cases |
|---|---:|
| ItsDangerous token migration | 57 |
| ItsDangerous integrated signing and migration | 177 |
| Cachetools atomic update | 34 |
| Cachetools integrated resize and rollback | 79 |

These are project-authored tasks on pinned library snapshots. The four tasks come from two library families and were used during development of the harness and workflows. Repeats describe variation on these tasks. They do not add independent tasks or establish a general model ranking.

## Plan 16 · Self-review and independent review

Both groups used Sol for planning and Luna for implementation and revision. The review turn used Luna in the self-review group and Sol in the independent-review group. Both used the planned-self-test workflow and the same external acceptance checks.

| Task | Luna self-review | Independent Sol review |
|---|---:|---:|
| Token migration | 2/3 | 3/3 |
| Integrated signing and migration | 3/3 | 3/3 |
| Atomic update | 3/3 | 3/3 |
| Integrated resize and rollback | 3/3 | 3/3 |
| **Full passes** | **11/12** | **12/12** |
| **Estimated cost of graded runs** | **$1.357112** | **$3.869028** |

Independent review added one full pass. The self-review failure scored 53/57 and missed the cross-format migration cases. The independent-review group cost about 2.85 times as much. Including all attempts, Plan 16 recorded **$5.521828** in known estimated cost and **$0.136961** in unknown-usage reserves. [Original decision record](../decisions/016-planned-self-tests-and-review.md)

### Sol single-agent comparison with the same self-test workflow

The follow-up ran Sol alone once per task. The handoff column uses the first preassigned repeat for each Plan 16 task. Both columns use the same four task prompts, self-test tools, and acceptance suite. They were run in separate batches.

| Task | Sol alone | Sol plans, Luna implements and self-reviews |
|---|---:|---:|
| Token migration | $0.472188 | $0.115031 |
| Integrated signing and migration | $0.760009 | $0.134882 |
| Atomic update | $0.415017 | $0.089364 |
| Integrated resize and rollback | $0.829150 | $0.107412 |
| **Full passes** | **4/4** | **4/4** |
| **Estimated total** | **$2.476365** | **$0.446689** |

The handoff cost about **82% less** in this four-run comparison. The Sol baseline has one observation per task, while the complete handoff series passed 11/12. The result establishes an observed cost difference on these runs. A repeated Sol baseline on fresh tasks would clarify how often the workflows achieve the same quality.

For historical context, Plan 13 recorded **6/12 at $0.182398** for Luna alone and **9/12 at $2.177165** for Sol alone on the same tasks. Those runs used an earlier workflow and toolset. Changes in the self-test tools, prompts, and model assignment all contribute to the difference between those historical baselines and Plan 16. [Historical comparison](../decisions/013-task-discrimination-and-calibration.md)

## Plan 17 · Strict versus flexible permissions

Both groups used the same Sol/Luna/Sol model assignment and four-turn schedule. The flexible workflow allowed the active Planner and Reviewer to modify permitted source and self-tests, and used instructions that described their broader responsibilities.

| Group | Full passes | Estimated cost of graded runs |
|---|---:|---:|
| Strict | 11/12 | $3.961096 |
| Flexible | 11/12 | $5.088489 |

Flexible permissions cost **28.5% more** in this comparison. Both groups missed the cross-format cases once, on different repeats of token migration. The observed full-pass rates were equal. The sample gives no clear evidence of a quality difference, and the comparison measures the combined change in permissions and instructions. The known estimate across all attempts was **$9.325152**, including the strict run stopped by the budget guard before final acceptance. [Original decision record](../decisions/017-role-flexibility-and-permissions.md)

## How costs and evidence are reported

Costs use reported API usage and the rates saved with each run. The tables label whether costs cover graded runs or all attempts. A reserve for unknown usage is separate from known estimated cost. A partial attempt may consume API calls even when it has no acceptance grade.

The repository includes experiment configs, task manifests, and original decision records. Machine-generated reports and raw traces live under Git-ignored `artifacts/`. The tables here preserve aggregate evidence for readers who only have a clone.
