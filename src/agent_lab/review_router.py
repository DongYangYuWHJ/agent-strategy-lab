"""Deterministic review escalation from visible checks and requirement evidence."""
import json


def signals(events):
    """Use the last check of each type and writes that occurred after it."""
    last_checks = {}
    last_source_write = last_test_write = -1
    for event in events:
        if event["type"] != "tool":
            continue
        tool = event["tool"]
        result = event["result"]
        sequence = event["sequence"]
        if tool in ("run_checks", "run_self_tests"):
            last_checks[tool] = event
        elif result.get("ok") and tool in ("write_file", "edit_file"):
            last_source_write = sequence
        elif result.get("ok") and tool == "write_test":
            last_test_write = sequence

    outcome = {}
    for name, tool, last_write in (
        ("public", "run_checks", last_source_write),
        ("self_test", "run_self_tests", max(last_source_write, last_test_write)),
    ):
        check = last_checks.get(tool)
        if check is None:
            outcome[name] = "missing"
        elif check["sequence"] < last_write:
            outcome[name] = "stale"
        elif check["result"].get("passed") is not True:
            outcome[name] = "failed_or_incomplete"
        elif name == "public" and check["result"].get("completion_verified") is not True:
            outcome[name] = "failed_or_incomplete"
        else:
            outcome[name] = "passed"
    return outcome


def decide_review(mode, events, reply, requirements, test_files):
    checks = signals(events)
    reasons = [f"{name}:{status}" for name, status in checks.items() if status != "passed"]
    prefix = "ROUTER_EVIDENCE "
    lines = reply.strip().splitlines()
    try:
        evidence = json.loads(lines[-1][len(prefix):]) if lines and lines[-1].startswith(prefix) else None
    except ValueError:
        evidence = None
    if not isinstance(evidence, dict) or set(evidence) != {str(i) for i in range(1, requirements + 1)}:
        reasons.append("missing_or_invalid_requirement_evidence")
    else:
        for requirement, item in evidence.items():
            if (not isinstance(item, dict)
                    or not all(isinstance(item.get(k), str) and item[k].strip()
                               for k in ("scenario", "assertion", "test", "status"))
                    or item["status"] != "verified"
                    or (item["test"] != "public" and item["test"] not in test_files)):
                reasons.append(f"requirement_gap:{requirement}")
    return {"mode": mode, "escalated": mode == "always" or (mode == "rules" and bool(reasons)),
            "reasons": reasons, "checks": checks, "requirement_evidence": evidence}


