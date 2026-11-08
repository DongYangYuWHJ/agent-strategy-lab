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

## Architecture results at a glance

The sequence in each workflow is **plan → implement → review → revise**. A single agent handles all four turns. The tables keep separate batches separate, even when their model assignments match.

### Current workflow with agent-written self-tests

| Experiment | Models by turn | Condition | Full passes | Estimated cost of graded runs |
|---|---|---|---:|---:|
| Plan 16 follow-up | Sol → Sol → Sol → Sol | Single agent, one run per task | 4/4 (100%) | $2.476 |
| Plan 16 planner comparison | Luna → Luna → Luna → Luna | Planner-to-executor handoff with Luna in both roles | 8/12 (66.7%) | $0.585 |
| Plan 16 DeepSeek follow-up | DeepSeek → DeepSeek → DeepSeek → DeepSeek | DeepSeek Flash low in both handoff roles, one run per task | 4/4 (100%) | $0.613 |
| Plan 16 | Sol → Luna → Luna → Luna | Planner handoff, Luna self-review | 11/12 (91.7%) | $1.357 |
| Plan 16 | Sol → Luna → Sol → Luna | Independent Sol review | 12/12 (100%) | $3.869 |
| Plan 17 | Sol → Luna → Sol → Luna | Strict permissions | 11/12 (91.7%) | $3.961 |
| Plan 17 | Sol → Luna → Sol → Luna | Flexible permissions and corresponding instructions | 11/12 (91.7%) | $5.088 |

### Earlier four-task comparisons

These results predate the current self-test workflow. The Plan 13 repeated architecture series already includes its first run per task. The two Plan 14 comparisons are separate batches.

| Experiment | Workflow | Full passes / valid grades | Known estimated cost |
|---|---|---:|---:|
| Plan 13 repeated architecture comparison | Sol single agent | 9/12 (75.0%) | $2.177 |
| Plan 13 repeated architecture comparison | Luna single agent | 6/12 (50.0%) | $0.182 |
| Plan 13 repeated architecture comparison | Sol plans, Luna implements and self-reviews | 5/12 (41.7%) | $0.915 |
| Plan 14 initial review comparison | Sol single agent | 4/4 (100%) | $0.974 |
| Plan 14 initial review comparison | Luna single agent | 1/4 (25.0%) | $0.064 |
| Plan 14 initial review comparison | Sol plans, Luna implements and self-reviews | 3/4 (75.0%) | $0.293 |
| Plan 14 initial review comparison | Sol plans and reviews, Luna implements and revises | 4/4 (100%) | $0.671 |
| Plan 14 planner comparison | Sol plans and reviews, Luna implements and revises | 3/4 (75.0%) | $0.694 |
| Plan 14 planner comparison | Luna plans, implements and revises, Sol reviews | 2/4 (50.0%) | $0.508 |

Plan 13's handoff cost includes an interrupted attempt and has a separate $0.065782 unknown-usage reserve. Plan 14 costs refer to the graded comparison batches. The planner comparison also had earlier stopped attempts recorded separately. [Plan 13](../decisions/013-task-discrimination-and-calibration.md) · [Plan 14](../decisions/014-planner-executor-reviewer.md)

### Earlier algorithm-task pilots

The pilots used different tasks and limits. The table gives planned positions as well as valid grades so a configuration that stopped before grading is visible.

| Experiment | Workflow | Full passes / valid grades | Planned positions |
|---|---|---:|---:|
| Plan 11 · parent and subagent | DeepSeek single agent | 1/1 | 3 |
| Plan 11 · parent and subagent | Sol single agent | 3/3 | 3 |
| Plan 11 · parent and subagent | Sol parent, DeepSeek executor | 2/2 | 3 |
| Plan 11 · parent and subagent | DeepSeek parent, Sol executor | 1/1 | 3 |
| Plan 11 · parent and subagent | DeepSeek parent and executor | 1/1 | 3 |
| Plan 11 · parent and subagent | Sol parent and executor | 3/3 | 3 |
| Plan 12 · same-session handoff | DeepSeek single agent | 1/1 | 3 |
| Plan 12 · same-session handoff | Sol single agent | 3/3 | 3 |
| Plan 12 · same-session handoff | Sol plans, DeepSeek takes over | 3/3 | 3 |
| Plan 12 · DeepSeek follow-up | DeepSeek low single agent | 2/2 | 2 |
| Plan 12 · DeepSeek follow-up | DeepSeek max plans, DeepSeek low takes over | 2/2 | 2 |

Plan 11 had seven stops before final acceptance. The first Plan 12 pilot had one output truncation and one workspace setup failure, both in the DeepSeek single-agent group. Use the planned-position column when assessing how often a workflow delivered a full pass. [Plan 11](../decisions/011-planner-executor.md) · [Plan 12](../decisions/012-planner-handoff-and-routing.md)

Plan 15 tested revision alone from saved implementation snapshots. Sol passed 21/24 and Luna passed 19/24. Both repaired 12/15 initially failing inputs. Sol's revision introduced new failures in 0/24 attempts and Luna's in 4/24. These are revision outcomes with shared saved inputs and feedback. [Plan 15](../decisions/015-revision-model-comparison.md)

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

### Planner choice with Luna implementation and self-review

The Luna-planner follow-up kept the same task inputs, four prompts, role handoff, tools, and acceptance checks as the existing Sol-planner group. It ran in a separate batch with three repeats per task.

| Task | Luna planner | Sol planner |
|---|---:|---:|
| Token migration | 1/3 | 2/3 |
| Integrated signing and migration | 1/3 | 3/3 |
| Atomic update | 3/3 | 3/3 |
| Integrated resize and rollback | 3/3 | 3/3 |
| **Full passes** | **8/12** | **11/12** |
| **Estimated total** | **$0.585025** | **$1.357112** |
| **Planning phase estimate** | **$0.048877** | **$0.849841** |

Sol planning added three full passes for about $0.772 in additional estimated cost. The gains came from the two ItsDangerous tasks. All 12 Luna-planner runs passed their final self-tests, including the four that failed external acceptance. [Plan 16 planner follow-up](../decisions/016-planned-self-tests-and-review.md)

### DeepSeek planning, implementation, and self-review

DeepSeek Flash low handled both roles in the same Plan 16 handoff workflow and passed all four tasks, including both ItsDangerous tasks. All four final self-test results were current and passed. The batch recorded 162 generation calls and $0.613214 in estimated cost, with complete usage.

| Four-task comparison | Full passes | Estimated cost |
|---|---:|---:|
| Luna in both roles, first preassigned repeat per task | 2/4 | $0.187208 |
| DeepSeek in both roles, one run per task | 4/4 | $0.613214 |
| Sol planning with Luna implementation and self-review, first preassigned repeat per task | 4/4 | $0.446689 |

The DeepSeek run matched the Sol-to-Luna pass count at about 37% higher estimated cost. The groups ran in separate batches. The DeepSeek result covers one repeat per task. [Plan 16 DeepSeek follow-up](../decisions/016-planned-self-tests-and-review.md)

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

## Plan 19 · Review routing pilot

All arms started with Luna planning, implementation, self-review, and initial revision. Escalation added Sol review and another Luna revision. Each arm ran once on three development tasks outside the offline routing analysis.

| Arm | Full passes / valid grades | Escalations | Estimated cost |
|---|---:|---:|---:|
| Deliver after Luna self-review | 3/3 | 0/3 | $0.147479 |
| Escalate by rule | 3/3 | 3/3 | $1.078738 |
| Always escalate | 3/3 | 3/3 | $1.055128 |

The batch cost $2.281344 with complete usage. The rule escalated every task, and every baseline run passed. The pilot measures escalation behavior and cost. It offers no observed acceptance failures in the baseline to measure missed escalations or reviewer rescue.

All three rule-triggered runs had passing public checks and self-tests. One escalation arose solely from a test reference field containing several valid references where the parser expected one. The other two also had explicit coverage gaps. A retrospective normalization check would reduce escalations from three to two on these saved inputs. The acceptance outcomes for that changed policy remain unmeasured. [Plan 19](../decisions/019-task-and-review-routers.md)

## How costs and evidence are reported

Costs use reported API usage and the rates saved with each run. The tables label whether costs cover graded runs or all attempts. A reserve for unknown usage is separate from known estimated cost. A partial attempt may consume API calls even when it has no acceptance grade.

The repository includes experiment configs, task manifests, and original decision records. Machine-generated reports and raw traces live under Git-ignored `artifacts/`. The tables here preserve aggregate evidence for readers who only have a clone.
