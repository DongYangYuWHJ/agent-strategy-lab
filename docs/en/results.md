# Experiment results

[Home](../../README.md) · [Architecture](architecture.md) · [Experiment plan](experiment-plan.md)

## Summary

This project asks when a coding-agent workflow can lower estimated API cost while maintaining task acceptance. The main result comes from four paired repository tasks. Sol alone and a workflow with Sol planning followed by Luna implementation, self-review, and revision both passed **4/4**. The handoff cost **$0.447 versus $2.476**, about **82% less**. Costs for the planning turn were similar, and the later turns accounted for the savings. [Paired handoff results](#sol-single-agent-comparison-with-the-same-self-test-workflow)

The benefit depended on the workflow. In an early pilot, keeping Sol involved as the parent while also assigning a Sol executor cost **1.82 times** as much as Sol alone. An early handoff also delivered fewer complete passes than Sol alone across repeats. The later workflow explicitly planned tests, let the executor write and run them, and checked the final code with an independent acceptance suite. [Early delegation](../decisions/011-planner-executor.md) · [Early handoff](../decisions/013-task-discrimination-and-calibration.md) · [Later workflow](../decisions/016-planned-self-tests-and-review.md)

The task router is a separate extension. On 14 tasks, it lowered the cost of a fixed Sol-to-Luna handoff by **25.3%**, with **13/14 versus 14/14** passes. Fixed Luna alone matched the router's pass or fail outcome on every task and cost less. The comparison used a different task mix and baseline from the four-task handoff experiment. [Task-routing results](#plan-20--two-tier-task-routing)

## Evaluation setup

Each task begins from the same starting source within a comparison. A full pass requires every independent final acceptance case to pass. A valid grade can be a pass or a failure. Infrastructure and budget stops without a final grade are tracked separately. The planning, review, and role-permission comparisons used four repository tasks.

| Task | Final cases |
|---|---:|
| ItsDangerous token migration | 57 |
| ItsDangerous integrated signing and migration | 177 |
| Cachetools atomic update | 34 |
| Cachetools integrated resize and rollback | 79 |

These are project-authored tasks on pinned library snapshots from two library families. Repeated runs measure variation on those tasks. The routing comparison adds algorithm tasks and other repository tasks. Later runs evaluated fixed workflow configurations, with some tasks reused across comparisons.

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

The handoff cost about **82% less** in this four-pair comparison. Planning cost $0.270786 for Sol alone and $0.276100 for the handoff. The three remaining turns cost $2.205579 with Sol and $0.170590 with Luna. The handoff used 139 model calls versus 134 for Sol alone. The Sol baseline has one observation per task, while the complete handoff series passed 11/12. The observed cost difference and equal pass count apply to the four paired runs.

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

## Plan 20 · Two-tier task routing

Luna selected either Luna alone or the Sol-to-Luna handoff before planning. The two fixed groups used one architecture for every task. All three groups used the same 14 tasks, four-turn workflow, and independent acceptance checks. The router and fixed handoff groups combined 12 matching saved runs with 16 new runs. Fixed Luna combined three matching saved runs with 11 new runs. Each task has one valid grade per group.

| Difficulty | Fixed Luna passes | Fixed Luna USD | Fixed handoff passes | Fixed handoff USD | Router passes | Router USD |
|---|---:|---:|---:|---:|---:|---:|
| Easy | 8/8 | 0.091475 | 8/8 | 0.250835 | 8/8 | 0.084913 |
| Medium | 4/4 | 0.136945 | 4/4 | 0.319817 | 4/4 | 0.301457 |
| Hard | 1/2 | 0.087093 | 2/2 | 0.228349 | 1/2 | 0.210449 |
| **Total** | **13/14** | **0.315513** | **14/14** | **0.799001** | **13/14** | **0.596818** |

The router chose Luna alone for all eight easy tasks and one medium task. Compared with fixed handoff, the easy tier cost **66.1% less** and accounted for about **82% of the observed savings**. On the integrated ItsDangerous task, the router and fixed Luna both passed 173/177 cases and missed the same four cross-format cases. Fixed handoff passed 177/177 using the same architecture the router selected. The estimated routing cost of $0.001804 is included in the totals.

Fixed Luna and the router passed exactly the same 13 tasks. The router cost about **89% more** than fixed Luna while its cumulative runtime was **8 minutes 23 seconds shorter**. This comparison shows no improvement in full-task acceptance over fixed Luna on this set. The groups were collected across batches and have one observation per task and group, so the observed runtime difference can also reflect cache and service timing. [Plan 20](../decisions/020-structure-router-comparison.md) · [Configuration](../../configs/workflow-structure-router-two-tier-mixed.json)

### Results by task

Each cell gives final acceptance and estimated cost. “Handoff” means Sol planning followed by Luna implementation, self-review, and revision.

| Difficulty | Task | Router choice | Fixed Luna | Fixed handoff | Router |
|---|---|---|---:|---:|---:|
| Easy | Happy New Year 2025 | Luna | Pass / $0.00904 | Pass / $0.01914 | Pass / $0.00638 |
| Easy | 9x9 Sum | Luna | Pass / $0.00608 | Pass / $0.02042 | Pass / $0.00542 |
| Easy | Geometric Sequence | Luna | Pass / $0.00836 | Pass / $0.02445 | Pass / $0.00683 |
| Easy | Seek Grid | Luna | Pass / $0.00598 | Pass / $0.02709 | Pass / $0.00845 |
| Easy | Pagination boundaries | Luna | Pass / $0.01511 | Pass / $0.03464 | Pass / $0.01051 |
| Easy | HTTP retry policy | Luna | Pass / $0.01454 | Pass / $0.04064 | Pass / $0.01492 |
| Easy | Timeout configuration | Luna | Pass / $0.02028 | Pass / $0.04288 | Pass / $0.01906 |
| Easy | Soft delete and restore | Luna | Pass / $0.01207 | Pass / $0.04157 | Pass / $0.01334 |
| Medium | Gravity | Luna | Pass / $0.01812 | Pass / $0.04083 | Pass / $0.01782 |
| Medium | TOMLKit round trip | Handoff | Pass / $0.03002 | Pass / $0.09316 | Pass / $0.10484 |
| Medium | Packaging dependency-group errors | Handoff | Pass / $0.02311 | Pass / $0.05220 | Pass / $0.05789 |
| Medium | TinyDB snapshot restore | Handoff | Pass / $0.06569 | Pass / $0.13364 | Pass / $0.12090 |
| Hard | Cachetools atomic update | Handoff | Pass / $0.04278 | Pass / $0.11676 | Pass / $0.08998 |
| Hard | ItsDangerous signing and migration | Handoff | Fail / $0.04431 | Pass / $0.11159 | Fail / $0.12047 |

### Keyword rule versus model routing

A retrospective replay used a fixed keyword rule. It read the task description and acceptance text, selected the handoff on explicit mentions of migration, permissions, atomicity, or rollback, and selected Luna alone otherwise. The two policies used the same archived fixed-run outcome whenever they chose the same architecture. The model policy also included its measured routing fee.

| Policy | Luna choices | Handoff choices | Replay passes | Estimated USD |
|---|---:|---:|---:|---:|
| Keyword rule | 12 | 2 | 14/14 | 0.456769 |
| LLM Router | 9 | 5 | 14/14 | 0.618737 |

The rule cost **26.2% less** in replay. The three different choices were TOMLKit, Packaging, and TinyDB, where the rule chose Luna and both fixed architectures passed. Both policies made the same choice on the two hard tasks. These are replay estimates from one archived run per task and fixed architecture. The rule was defined after the earlier experiments, and the independent live router run still scored 13/14. [Plan 20 replay notes](../decisions/020-structure-router-comparison.md#简单规则与-llm-router-离线对照)

The keyword rule remains an offline cost baseline. Routing open-ended developer requests calls for interpreting the user's intent and constraints in context. For example, “no migration is needed” triggers the keyword rule, while “data saved by older versions must still load” can require migration work without using the trigger word. This is a design choice for everyday use. The replay did not test paraphrases or establish a pass-rate advantage for LLM routing. [Design decision](../decisions/020-structure-router-comparison.md#简单规则与-llm-router-离线对照)

## How costs and evidence are reported

Costs use reported API usage and the rates saved with each run. The tables label whether costs cover graded runs or all attempts. A reserve for unknown usage is separate from known estimated cost. A partial attempt may consume API calls even when it has no acceptance grade.

The repository includes experiment configs, task manifests, and original decision records. Machine-generated reports and raw traces live under Git-ignored `artifacts/`. The tables here preserve evidence for readers who only have a clone.
