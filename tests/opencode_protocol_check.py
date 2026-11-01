"""Explicit local OpenCode integration check. All model replies are fixtures.

Not discovered by the normal suite; no external generation is performed.
"""
from pathlib import Path
from dataclasses import replace
import argparse
import json
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.domain import Limits, Task, load_models, save_json, digest
from agent_lab.opencode_workflow import run_workflow, opencode_config
from agent_lab.opencode_permissions import ROLE_AGENT_IDS
from agent_lab.reporting import write_report
from agent_lab.workflows import Workflow


parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
parser.add_argument("--strategy", choices=("single_agent", "planner_worker", "planner_handoff"), default="single_agent")
parser.add_argument("--distinct-model", action="store_true", help="Use a separate fixture model ID for the handoff Executor")
parser.add_argument("--inject-edit-grant", action="store_true")
args = parser.parse_args()
output = args.output.resolve()
if output.exists():
    raise SystemExit("Use a new output directory")
model = load_models(ROOT / "configs/models.json")["deepseek-flash"]
task = Task.load(ROOT / "benchmarks/livecodebench-v2/tasks/lcb-abc387-a/task.json")
workflow = Workflow.load(ROOT / "configs/workflows/daily-review.json")
call_index = 0
observed_tools = {}


def fake_upstream(provider, payload, timeout):
    global call_index
    call_index += 1
    if provider.model.max_output_tokens is None:
        assert not {"max_tokens", "max_completion_tokens", "max_output_tokens"}.intersection(payload), "Adapter reintroduced a local output cap"
    all_text = json.dumps(payload["messages"], ensure_ascii=False)
    tools = payload.get("tools", [])
    names = {t["function"]["name"] for t in tools}
    role = "planner" if any(n.startswith("lab_planner_") for n in names) else "worker" if any(n.startswith("lab_worker_") for n in names) else "solo"
    if args.strategy == "planner_handoff":
        assert "subagent" not in names
        if role == "worker":
            assert "PLANNING_CONTEXT_FIXTURE" in all_text, "Planning history was lost during handoff"
    observed_tools[role] = sorted(names)
    assert not names.intersection({"patch", "write", "edit", "read", "glob", "grep", "shell", "execute", "question"}), "Native tool leaked"
    assert not any(n.startswith("lab_") and not n.startswith("lab_" + role + "_") for n in names), "Cross-role tool leaked"
    function = next((n for n in names if n.endswith("write_file")), None)
    written = any(m.get("role") == "tool" and '"bytes"' in str(m.get("content", "")) for m in payload["messages"])
    should_write = (role == "worker" or "核实后按你认为合适的方案实施" in all_text) and function and not written
    delegated = any(m.get("role") == "tool" and "<subagent " in str(m.get("content", "")) for m in payload["messages"])
    should_delegate = role == "planner" and "核实后按你认为合适的方案实施" in all_text and not delegated
    action = None
    if should_delegate:
        assert "subagent" in names
        action = {"name": "subagent", "arguments": {"agent": ROLE_AGENT_IDS["worker"], "description": "Protocol fixture implementation",
            "prompt": "Implement solution.py: read two integers A B, print (A+B)**2. Current turn permits edits, solution.py is the only editable file. Return actual evidence. No further delegation."}}
    elif should_write:
        action = {"name": function, "arguments": {"path": "solution.py", "content": "import sys\na,b=map(int,sys.stdin.read().split())\nprint((a+b)**2)\n"}}
    message = {"role": "assistant", "content": None if action else "已核对当前轮要求。" + (" PLANNING_CONTEXT_FIXTURE" if role == "planner" else "")}
    message["reasoning_content"] = "Fixture reasoning retained across tool calls."
    if action:
        message["tool_calls"] = [{"id": f"call-{call_index}", "type": "function", "function": {
            "name": action["name"], "arguments": json.dumps(action["arguments"])}}]
    usage = {"prompt_tokens": provider.count_input_tokens(payload, 10), "completion_tokens": 50}
    raw = {"id": f"fixture-{call_index}", "model": model.model, "usage": usage,
           "choices": [{"finish_reason": "tool_calls" if action else "stop", "message": message}],
           "_lab_tool_calls": int(bool(action))}
    delta = dict(message)
    if action:
        delta["tool_calls"] = [{"index": i, **c} for i, c in enumerate(delta["tool_calls"])]
    chunks = [
        {"id": raw["id"], "object": "chat.completion.chunk", "created": 1, "model": model.model,
         "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
        {"id": raw["id"], "object": "chat.completion.chunk", "created": 1, "model": model.model,
         "choices": [{"index": 0, "delta": {}, "finish_reason": raw["choices"][0]["finish_reason"]}], "usage": usage}]
    body = ("".join("data: " + json.dumps(c, ensure_ascii=False) + "\n\n" for c in chunks) + "data: [DONE]\n\n").encode()
    return body, raw


def generated_config(*values, **kwargs):
    config = opencode_config(*values, **kwargs)
    if args.inject_edit_grant:
        target = ROLE_AGENT_IDS["solo"] if args.strategy == "single_agent" else ROLE_AGENT_IDS["worker"]
        config["agents"][target]["permissions"].append({"action": "edit", "resource": "*", "effect": "allow"})
    return config


legacy_hash = digest((ROOT / "opencode.jsonc").read_text(encoding="utf-8"))
with patch("agent_lab.providers.require_credential", return_value="protocol-fixture"), \
     patch("agent_lab.workflow_gateway.forward_stream", side_effect=fake_upstream), \
     patch("agent_lab.opencode_workflow.opencode_config", side_effect=generated_config):
    models = [model] if args.strategy == "single_agent" else [model, model]
    if args.distinct_model:
        assert args.strategy == "planner_handoff"
        models[1] = replace(model, id="fixture-executor")
    result = run_workflow(task, models, Limits(max_calls=20, max_tool_steps=40, max_seconds=180, check_timeout_seconds=30), output, workflow, args.strategy)
result["execution_kind"] = "simulated"
directory = Path(result["artifact_dir"])
config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
config["execution_kind"] = "simulated"
config["protocol_fixture"] = True
save_json(directory / "config.json", config)
result["config_fingerprint"] = digest(config)
save_json(directory / "result.json", result)
assert digest((ROOT / "opencode.jsonc").read_text(encoding="utf-8")) == legacy_hash
registered = json.loads((directory / "registered-agents.json").read_text(encoding="utf-8"))
legacy = next((a for a in registered if a.get("id") == "lab-worker"), None)
assert legacy and any(p.get("action") == "edit" and p.get("effect") == "allow" for p in legacy.get("permissions", [])), "Legacy config was not loaded"
save_json(directory / "fixture-assertions.json", {"legacy_config_present": True, "legacy_config_unchanged": True,
          "observed_tools_by_role": observed_tools, "fixture_generation_requests": call_index,
          "injected_edit_grant": args.inject_edit_grant})
write_report(output)
print(json.dumps({k: result[k] for k in ["status", "stop_reason", "turns_completed", "turns_expected", "artifact_dir"]}))
if args.inject_edit_grant:
    passed = result["stop_reason"] == "permission_configuration_error" and call_index == 0 and result["accounting"]["calls"] == 0
else:
    passed = result["accepted"] and result["turns_completed"] == 4
    if passed and args.strategy == "planner_worker":
        children = json.loads((directory / "child-sessions.json").read_text(encoding="utf-8"))["data"]
        assert children and all(c["agent"] == ROLE_AGENT_IDS["worker"] for c in children)
        assert set(observed_tools) == {"planner", "worker"}
    if passed and args.strategy == "planner_handoff":
        children = json.loads((directory / "child-sessions.json").read_text(encoding="utf-8"))["data"]
        assert not children, "Handoff must not create child sessions"
        selections = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((directory / "turns").glob("*/selection.json"))]
        assert len(selections) == 4 and all(s["passed"] for s in selections)
        assert len({s["session_id"] for s in selections}) == 1
        assert [s["role"] for s in selections] == ["planner", "worker", "worker", "worker"]
        events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        generations = [e for e in events if e["type"] == "request_started"]
        assert all(e["primary_role"] == ("planner" if e["turn"] == "plan" else "worker") for e in generations)
        assert all(e["model_id"] == models[0 if e["turn"] == "plan" else 1].id for e in generations)
        assert (directory / "turns/00-plan/workspace/solution.py").read_bytes() == (task.source_dir / "solution.py").read_bytes()
        assert set(observed_tools) == {"planner", "worker"}
raise SystemExit(0 if passed else 1)
