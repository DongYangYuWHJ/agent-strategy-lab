# Experiment plan and decision history

[Home](../../README.md) · [Results](results.md) · [Running experiments](running-experiments.md)

Agent Architecture Lab studies how model assignment, review, and tool permissions affect coding-task delivery and API cost. A comparison fixes the task inputs, final checks, and model settings where practical, and records the prompt, tool, and permission differences that define the workflows.

## Current state

- **Planning, self-testing, and review.** Plan 16 completed the self-review versus independent-review comparison and a four-task Sol single-agent follow-up. The Sol-to-Luna handoff is the lower-cost observed configuration on the four-task follow-up. The independent-review group has the highest observed full-pass count in the repeated Plan 16 comparison. [Results](results.md)
- **Role flexibility.** Plan 17 completed the strict and flexible comparisons. Both groups passed 11/12. Flexible permissions increased estimated cost in this batch. [Results](results.md#plan-17--strict-versus-flexible-permissions)
- **Next question.** Test whether observable signs of unresolved risk can identify tasks that benefit from independent review. This review-routing experiment remains proposed.

## Proposed review-routing experiment

Use Luna self-review as the default and define escalation rules before running the comparison. Candidate signals include a remaining public or self-test failure, a final edit that has no fresh test result, and an explicit unresolved requirement. An escalated case would receive Sol review and another Luna revision. Every group would use the same independent final acceptance suite.

Compare self-review only, independent review on every task, and review on escalation. Record escalation frequency, full passes, newly introduced failures, known estimated costs, and interrupted attempts. Check false negatives using the offline grades, especially cases where the available checks pass while a hidden requirement fails. The runtime router would use evidence available during the run. Final acceptance outcomes would be reserved for analysis.

Use a fresh development set to check the rules, then assess the frozen policy on tasks that were not used to select those rules. Record the model assignments, time and spend limits, and planned repeats before launch.

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

When adding a decision, describe the question, experiment design, observed results, costs, and remaining uncertainty. Use the saved run configuration for exact execution settings. Keep interrupted attempts in the accounting and distinguish a proposed change from one that has been implemented or tested.
