# Architecture

[Home](../../README.md) · [Running experiments](running-experiments.md) · [Results](results.md)

An experiment is a set of task, architecture, and repeat positions. Each run begins with a fresh copy of the task source and a new conversation. The runner records the task and configuration identity, executes the configured turns, and uses an independent final check to evaluate the delivered code.

## Execution and review

The native runner supports single-agent tool loops. The OpenCode backend runs fixed conversation workflows. In the current self-test comparison, the four turns are planning, implementation, review, and revision.

| Workflow | Planning | Implementation | Review | Revision |
|---|---|---|---|---|
| Sol single agent | Sol | Sol | Sol | Sol |
| Planner handoff with self-review | Sol | Luna | Luna | Luna |
| Planner, executor, and independent reviewer | Sol | Luna | Sol | Luna |

A handoff switches the primary agent and model in the same conversation. The independent reviewer in the strict comparison inspects code, checks assumptions against the original requirements, and can rerun public checks and self-tests. The executor handles edits and delivery. The flexible comparison uses the same role schedule and lets the active Planner and Reviewer also edit permitted task files and tests.

## Checks and accounting

Public checks give the agent operator-defined feedback during a run. Agent-written Python self-tests run in a disposable copy of the current task source. Their results are tied to the code and tests that ran. The external final check runs after the workflow and supplies the acceptance grade. Its hidden feedback stays outside the conversation.

The OpenCode runner verifies the effective role and tool permissions before generation. It exposes the task file allowlist and checks through its local tool gateway. These are application-level controls. Self-tests use process isolation and Python audit restrictions, so run the harness with host isolation appropriate to the code you evaluate.

A provider gateway records usage and applies the configured budget, token, call, and time rules. All roles in a run share one ledger. A failed or incomplete response can leave unknown usage and stop the batch. The saved event log preserves known charges and the unknown reserve.

| Source | Responsibility |
|---|---|
| [workflow_experiments.py](../../src/agent_lab/workflow_experiments.py) | Freeze and execute an OpenCode batch |
| [opencode_workflow.py](../../src/agent_lab/opencode_workflow.py) | Configure sessions, verify role selection, and advance turns |
| [workflow_gateway.py](../../src/agent_lab/workflow_gateway.py) and [opencode_permissions.py](../../src/agent_lab/opencode_permissions.py) | Gate requests, expose tools, and audit permissions |
| [self_tests.py](../../src/agent_lab/self_tests.py) and [evaluation.py](../../src/agent_lab/evaluation.py) | Run advisory self-tests and independent checks |
| [accounting.py](../../src/agent_lab/accounting.py) and [reporting.py](../../src/agent_lab/reporting.py) | Record estimated costs and summarize outcomes |
