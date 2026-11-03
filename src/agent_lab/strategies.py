"""Policies decide transitions; they never override shared limits."""
from dataclasses import dataclass
from enum import Enum


class Action(str, Enum):
    REPAIR = "repair"
    FINISH = "finish"
    STOP = "stop"
    REPLAN = "replan"  # Reserved extension; no planner calls in v1.


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str


class SingleAgent:
    name = "single_agent"
    version = 1

    def after_public_check(self, result, repairs, limits):
        if not result["ok"]:
            return Decision(Action.STOP, "check_timeout" if result["status"] == "timed_out" else "environment_error")
        if result["passed"]:
            return Decision(Action.FINISH, "public_checks_passed")
        if limits.max_repairs is not None and repairs >= limits.max_repairs:
            return Decision(Action.STOP, "repair_limit")
        return Decision(Action.REPAIR, "public_checks_failed")


def get_strategy(name):
    if name != SingleAgent.name:
        raise ValueError("v1 supports single_agent only; planner/worker and escalation are reserved extensions")
    return SingleAgent()
