"""Exercise selection, dispatch, and accounting without a live provider."""
from contextlib import contextmanager
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.domain import Limits, Model, Pricing, Task, read_json
from agent_lab.opencode_workflow import run_workflow, workflow_role_prompts
from agent_lab.workflows import Workflow


@contextmanager
def fixture_server(*args):
    yield "http://fixture", "fixture"


class SoloSession:
    def __init__(self, url, password, workspace, directory, models, strategy, gateway):
        assert strategy == "single_agent"
        assert [model.id for model in models] == ["luna"]
        self.gateway = gateway

    def run_turn(self, text, turn_dir):
        if self.gateway.turn == "implement":
            replay = read_json(ROOT / "tickets/clamp-boundaries/replay.json")
            action = next(a for batch in replay for a in batch if a["name"] == "write_file")
            reply = self.gateway.mcp("solo", {"id": 1, "method": "tools/call", "params": action})
            assert not reply["isError"]

    def close(self):
        pass


class StructureRouterTests(unittest.TestCase):
    def test_choice_dispatch_and_cost_survive_invalid_choice(self):
        task = Task.load(ROOT / "tickets/clamp-boundaries/task.json")
        workflow = Workflow.load(ROOT / "configs/workflows/plan-execute-review-self-tests.json")
        luna = Model("luna", "openai", "fixture", Pricing("1", "2"), max_output_tokens=1024)
        baseline = {"strategy": "planner_handoff"}
        candidates = {"solo": ({"strategy": "single_agent"}, [luna]),
                      "fixed": (baseline, [luna, luna])}
        prompts = {key: workflow_role_prompts(value[0]["strategy"]) for key, value in candidates.items()}
        for choice in ("solo", "unregistered"):
            with self.subTest(choice=choice), tempfile.TemporaryDirectory() as tmp:
                response = {"id": "fixture", "model": "fixture", "status": "completed",
                    "usage": {"input_tokens": 100, "output_tokens": 30},
                    "output": [{"type": "message", "role": "assistant", "content": [
                        {"type": "output_text", "text": json.dumps(
                            {"architecture": choice, "reason": "Local change", "risk": "Bounds"})}]}]}
                with patch("agent_lab.providers.require_credential", return_value="fixture"), \
                     patch("agent_lab.opencode_workflow.isolated_server", side_effect=fixture_server) as server, \
                     patch("agent_lab.workflow_gateway.forward_stream", return_value=(b"fixture", response)) as calls:
                    result = run_workflow(task, [luna, luna], Limits(), Path(tmp), workflow,
                        "planner_handoff", session_factory=SoloSession,
                        structure_routing=(luna, {"solo": "One agent", "fixed": "Handoff"}, candidates, prompts))
                self.assertEqual(calls.call_count, 1)
                self.assertEqual(result["accounting"]["estimated_cost_usd"], "0.00016")
                if choice == "solo":
                    self.assertTrue(result["accepted"])
                    self.assertEqual(result["turns_completed"], 4)
                    decision = read_json(Path(result["artifact_dir"]) / "structure-routing.json")
                    self.assertEqual(decision["architecture"], "solo")
                else:
                    self.assertEqual(result["stop_reason"], "invalid_structure_route")
                    self.assertEqual(result["turns_completed"], 0)
                    server.assert_not_called()
