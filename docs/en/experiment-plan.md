# Experiment plan and decision history

[Home](../../README.md) · [Results](results.md) · [Running experiments](running-experiments.md)

Agent Architecture Lab studies how model assignment, review, and tool permissions affect coding-task delivery and API cost. A comparison fixes the task inputs, final checks, and model settings where practical, and records the prompt, tool, and permission differences that define the workflows.

## Current state

- **Planning and self-review.** In the paired Plan 16 follow-up, Sol alone and the Sol-to-Luna handoff both passed 4/4. The handoff cost about 82% less. Across three repeats, the handoff passed 11/12 with Luna self-review and 12/12 with independent Sol review. [Results](results.md#plan-16--self-review-and-independent-review)
- **Role flexibility.** Plan 17 completed the strict and flexible comparisons. Both groups passed 11/12. Flexible permissions increased estimated cost in this batch. [Results](results.md#plan-17--strict-versus-flexible-permissions)
- **Review routing.** Plan 18 replayed escalation signals on 12 self-review traces. In the live Plan 19 pilot, all baseline tasks passed and the rule escalated all three cases. This measured escalation behavior and cost. [Plan 18](../decisions/018-review-routing.md) · [Plan 19 results](results.md#plan-19--review-routing-pilot)
- **Task routing.** The two-tier router chose Luna alone or Sol planning followed by Luna implementation, self-review, and revision. On 14 tasks it cost 25.3% less than fixed Sol planning, with 13/14 versus 14/14 passes. Fixed Luna alone matched the router's task outcomes at a lower estimated cost. [Plan 20 results](results.md#plan-20--two-tier-task-routing)

## Evaluation scope

The later comparisons evaluated fixed workflows on named task sets. Some tasks appear in multiple comparisons. The report identifies the tasks, repeat counts, and saved runs used in each comparison, including the fixed Luna solo follow-up on the 14-task mix.

## Decision history

The English summaries below explain the purpose of each plan. Links point to the original Chinese records with implementation detail, earlier observations, and historical evidence.

| Plan | Decision |
|---|---|
| [001](../decisions/001-single-agent-baseline.md) | Establish a single-agent baseline with a reproducible task, tool, and grading loop. |
| [002](../decisions/002-adopt-opencode.md) | Use OpenCode for agent execution while retaining independent experiment control and grading. |
| [003](../decisions/003-independent-grading.md) | Verify checker completion so a premature exit cannot produce a successful grade. |
| [004](../decisions/004-output-budget-and-failure-types.md) | Separate model failures from output limits, budget stops, and runtime failures. |
| [005](../decisions/005-development-and-holdout.md) | Separate LiveCodeBench calibration, development, and holdout tasks. |
| [006](../decisions/006-quarantine-invalid-task.md) | Quarantine a task with a mismatch between its stated constraints and upstream validation. |
| [007](../decisions/007-output-token-budget-proposal.md) | Propose comparing output limits in controlled steps. |
| [008](../decisions/008-continuation-and-limit-fix.md) | Repair continuation and request-limit handling, then verify it in live runs. |
| [009](../decisions/009-single-agent-summary-and-parameter-failures.md) | Summarize the initial single-agent runs and distinguish parameter stops from acceptance failures. |
| [010](../decisions/010-conversation-workflow-evaluation.md) | Evaluate fixed follow-up turns that resemble everyday developer conversations. |
| [011](../decisions/011-planner-executor.md) | Compare planner/executor assignments and verify effective permissions before generation. |
| [012](../decisions/012-planner-handoff-and-routing.md) | Switch the primary agent after planning in the same conversation, and record routing as a future direction. |
| [013](../decisions/013-task-discrimination-and-calibration.md) | Calibrate repository tasks and repeat baseline and handoff comparisons on four development tasks. |
| [014](../decisions/014-planner-executor-reviewer.md) | Add independent review and inspect stage snapshots to distinguish original defects from revision regressions. |
| [015](../decisions/015-revision-model-comparison.md) | Compare Sol and Luna revising the same saved implementation with the same review feedback. |
| [016](../decisions/016-planned-self-tests-and-review.md) | Give the executor self-test tools, compare review assignments, and add the updated Sol single-agent baseline. |
| [017](../decisions/017-role-flexibility-and-permissions.md) | Compare strict and flexible role permissions under the same model assignment. |
| [018](../decisions/018-review-routing.md) | Replay escalation signals offline and identify gaps in the available test evidence before designing a live comparison. |
| [019](../decisions/019-task-and-review-routers.md) | Separate task routing before planning from review routing before delivery, and define the comparison for each. |
| [020](../decisions/020-structure-router-comparison.md) | Completed the 14-task comparison of two-tier task routing, fixed Sol planning, and fixed Luna alone. |

When adding a decision, describe the question, experiment design, observed results, costs, and remaining uncertainty. Use the saved run configuration for exact execution settings. Keep interrupted attempts in the accounting and distinguish a proposed change from one that has been implemented or tested.
