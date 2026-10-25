"""Explicit local OpenCode integration check. All model replies are fixtures.

Not discovered by the normal suite; no external generation is performed.
"""
from pathlib import Path
import json
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.domain import Limits, Task, load_models, save_json
from agent_lab.opencode_workflow import run_workflow
from agent_lab.reporting import write_report
from agent_lab.workflows import Workflow


output = Path(sys.argv[1]).resolve()
if output.exists():
    raise SystemExit("Use a new output directory")
model = load_models(ROOT / "configs/models.json")["deepseek-flash"]
task = Task.load(ROOT / "benchmarks/livecodebench-v2/tasks/lcb-abc387-a/task.json")
workflow = Workflow.load(ROOT / "configs/workflows/daily-review.json")
call_index = 0


def fake_upstream(provider, payload, timeout):
    global call_index
    call_index += 1
    all_text = json.dumps(payload["messages"], ensure_ascii=False)
    tools = payload.get("tools", [])
    function = next((t["function"]["name"] for t in tools if t["function"]["name"].endswith("write_file")), None)
    written = any(m.get("role") == "tool" and '"bytes"' in str(m.get("content", "")) for m in payload["messages"])
    should_write = "核实后按你认为合适的方案实施" in all_text and function and not written
    message = {"role": "assistant", "content": None if should_write else "已核对当前轮要求。"}
    message["reasoning_content"] = "Fixture reasoning retained across tool calls."
    if should_write:
        message["tool_calls"] = [{"id": "call-write", "type": "function", "function": {"name": function,
            "arguments": json.dumps({"path": "solution.py", "content": "import sys\na,b=map(int,sys.stdin.read().split())\nprint((a+b)**2)\n"})}}]
    usage = {"prompt_tokens": provider.count_input_tokens(payload, 10), "completion_tokens": 50}
    raw = {"id": f"fixture-{call_index}", "model": model.model, "usage": usage,
           "choices": [{"finish_reason": "tool_calls" if should_write else "stop", "message": message}],
           "_lab_tool_calls": int(should_write)}
    delta = dict(message)
    if should_write:
        delta["tool_calls"] = [{"index": i, **c} for i, c in enumerate(delta["tool_calls"])]
    chunks = [
        {"id": raw["id"], "object": "chat.completion.chunk", "created": 1, "model": model.model,
         "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
        {"id": raw["id"], "object": "chat.completion.chunk", "created": 1, "model": model.model,
         "choices": [{"index": 0, "delta": {}, "finish_reason": raw["choices"][0]["finish_reason"]}], "usage": usage}]
    body = ("".join("data: " + json.dumps(c, ensure_ascii=False) + "\n\n" for c in chunks) + "data: [DONE]\n\n").encode()
    return body, raw


with patch("agent_lab.providers.require_credential", return_value="protocol-fixture"), \
     patch("agent_lab.workflow_gateway.forward_stream", side_effect=fake_upstream):
    result = run_workflow(task, [model], Limits(max_calls=20, max_tool_steps=40, max_seconds=180, check_timeout_seconds=30), output, workflow)
result["execution_kind"] = "simulated"
directory = Path(result["artifact_dir"])
save_json(directory / "result.json", result)
config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
config["execution_kind"] = "simulated"
config["protocol_fixture"] = True
save_json(directory / "config.json", config)
write_report(output)
print(json.dumps({k: result[k] for k in ["status", "stop_reason", "turns_completed", "turns_expected", "artifact_dir"]}))
raise SystemExit(0 if result["accepted"] and result["turns_completed"] == 4 else 1)
