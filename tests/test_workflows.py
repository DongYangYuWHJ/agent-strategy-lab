from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.accounting import StopRun
from agent_lab.domain import Limits, Model, Pricing, Task, read_json, save_json
from agent_lab.opencode_workflow import run_workflow, opencode_config, completed_turn
from agent_lab.reporting import summarize
from agent_lab.workflow_experiments import load_workflow_experiment, run_workflow_batch
from agent_lab.workflow_gateway import Gateway, stream_result
from agent_lab.workflows import Workflow


@contextmanager
def fake_server(*args):
    yield "http://fixture", "fixture"


class ScriptedSession:
    fail_turn = None
    seen = []

    def __init__(self, url, password, workspace, directory, models, strategy, gateway):
        self.gateway, self.workspace = gateway, workspace

    def run_turn(self, text, turn_dir):
        g = self.gateway
        self.seen.append((g.turn, text))
        g.generation("test-deep", "chat/completions", {"model": "fixture", "messages": [{"role": "user", "content": text}]})
        if g.turn == self.fail_turn:
            raise StopRun("needs_user_input")
        if g.turn == "plan":
            reply = g.mcp("solo", {"id": 1, "method": "tools/call", "params": {
                "name": "write_file", "arguments": {"path": "bounds.py", "content": "wrong"}}})
            if not reply["isError"]:
                raise AssertionError("Planning writes must be denied")
        if g.turn == "implement":
            task = Task.load(ROOT / "tickets/clamp-boundaries/task.json")
            replay = read_json(task.manifest_path.parent / "replay.json")
            action = next(a for batch in replay for a in batch if a["name"] == "write_file")
            reply = g.mcp("solo", {"id": 2, "method": "tools/call", "params": action})
            if reply["isError"]:
                raise AssertionError(reply)
        save_json(turn_dir / "messages.json", {"fixture": True, "text": text})

    def close(self):
        pass


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workflow = Workflow.load(ROOT / "configs/workflows/daily-review.json")
        self.task = Task.load(ROOT / "tickets/clamp-boundaries/task.json")
        self.model = Model("test-deep", "deepseek", "fixture", Pricing("1", "2"), max_output_tokens=256, reasoning_effort="low")
        ScriptedSession.seen = []
        ScriptedSession.fail_turn = None

    def run_fixture(self, **kwargs):
        def response(client, payload, timeout):
            return b"fixture", {"id": "fixture", "model": "fixture", "usage": {"prompt_tokens": 100, "completion_tokens": 30},
                                "choices": [{"finish_reason": "stop"}]}
        with patch("agent_lab.providers.require_credential", return_value="fixture-key"), \
             patch("agent_lab.workflow_gateway.forward_stream", side_effect=response), \
             patch("agent_lab.opencode_workflow.isolated_server", fake_server):
            return run_workflow(self.task, [self.model], Limits(**kwargs), self.root / "runs", self.workflow,
                                session_factory=ScriptedSession)

    def test_four_turns_same_workspace_final_only_once(self):
        result = self.run_fixture()
        self.assertTrue(result["accepted"])
        self.assertEqual(result["turns_completed"], 4)
        self.assertEqual([t for t, _ in ScriptedSession.seen], [t.id for t in self.workflow.turns])
        self.assertEqual(result["accounting"]["calls"], 4)
        self.assertEqual(result["accounting"]["total_tokens"], 520)
        directory = Path(result["artifact_dir"])
        events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        final = [e for e in events if e["type"] == "verification" and e["kind"] == "final"]
        completed = [e for e in events if e["type"] == "turn_completed"]
        self.assertEqual(len(final), 1)
        self.assertGreater(final[0]["sequence"], completed[-1]["sequence"])
        self.assertTrue((directory / "turns/00-plan/workspace/bounds.py").read_text().find("NotImplementedError") >= 0
                        or (directory / "turns/00-plan/workspace/bounds.py").read_text() == (self.task.source_dir / "bounds.py").read_text())
        self.assertNotIn("fixture-key", "".join(p.read_text(errors="replace") for p in directory.rglob("*.json")))

    def test_global_call_limit_does_not_reset_on_turn_change(self):
        result = self.run_fixture(max_calls=2)
        self.assertEqual(result["stop_reason"], "call_limit")
        self.assertEqual(result["turns_completed"], 2)
        self.assertEqual(result["accounting"]["calls"], 2)
        self.assertIsNone(result["final_evidence"])

    def test_budget_blocks_before_first_upstream_generation(self):
        result = self.run_fixture(max_cost_usd="0.000001")
        self.assertEqual(result["stop_reason"], "budget_limit")
        self.assertEqual(result["accounting"]["calls"], 0)

    def test_clarification_stops_without_advancing_or_grading(self):
        ScriptedSession.fail_turn = "requirements-review"
        result = self.run_fixture()
        self.assertEqual(result["stop_reason"], "needs_user_input")
        self.assertEqual(result["turns_completed"], 2)
        self.assertEqual(len(ScriptedSession.seen), 3)
        self.assertIsNone(result["final_evidence"])

    def test_generation_failure_closes_gate_no_retry(self):
        with patch("agent_lab.providers.require_credential", return_value="fixture"), \
             patch("agent_lab.workflow_gateway.forward_stream", side_effect=TimeoutError) as forward, \
             patch("agent_lab.opencode_workflow.isolated_server", fake_server):
            result = run_workflow(self.task, [self.model], Limits(), self.root / "runs", self.workflow,
                                  session_factory=ScriptedSession)
        self.assertEqual(result["stop_reason"], "usage_unknown")
        self.assertFalse(result["accounting"]["usage_complete"])
        self.assertEqual(forward.call_count, 1)

    def test_unknown_and_truncated_response_never_advance(self):
        for usage, reason in [(None, "usage_unknown"), ({"prompt_tokens": 1, "completion_tokens": 256}, "output_token_limit")]:
            with self.subTest(reason=reason), patch("agent_lab.providers.require_credential", return_value="fixture"), \
                 patch("agent_lab.workflow_gateway.forward_stream", return_value=(b"", {"usage": usage, "choices": [{"finish_reason": "length"}]})), \
                 patch("agent_lab.opencode_workflow.isolated_server", fake_server):
                result = run_workflow(self.task, [self.model], Limits(), self.root / reason, self.workflow, session_factory=ScriptedSession)
                self.assertEqual(result["stop_reason"], reason)
                self.assertEqual(result["turns_completed"], 0)

    def test_invalid_workflow_rejected(self):
        raw = {"schema_version": 1, "id": "bad", "turns": [{"id": "t", "prompt": "hi", "allow_write": "false"}]}
        p = self.root / "bad.json"; save_json(p, raw)
        with self.assertRaises(ValueError):
            Workflow.load(p)

    def test_completion_uses_current_main_idle_not_tool_error_wording(self):
        admitted = {"data": {"time": {"created": 10}}}
        self.assertFalse(completed_turn({"data": [{"type": "idle", "outcome": "succeeded", "time": {"created": 9}}]}, admitted))
        rows = [{"type": "idle", "outcome": "succeeded", "time": {"created": 12}},
                {"type": "assistant", "time": {"created": 11, "completed": 12}, "content": [{"error": "recoverable tool error"}]}]
        self.assertTrue(completed_turn({"data": rows}, admitted))
        rows[0]["outcome"] = "failed"
        with self.assertRaises(StopRun):
            completed_turn({"data": rows}, admitted)

    def test_generated_config_routes_all_models_through_gate(self):
        other = replace(self.model, id="test-other")
        config = opencode_config([self.model, other], "http://127.0.0.1:1/local", Limits(), "planner_worker")
        self.assertEqual(set(config["providers"]), {"lab-test-deep", "lab-test-other"})
        self.assertEqual(config["default_agent"], "lab-planner")
        self.assertNotIn("lab_worker_*", str(config["agents"]["lab-planner"]["permissions"]))
        self.assertNotIn("api.deepseek.com", str(config))
        self.assertFalse(config["compaction"]["auto"])

    def test_native_and_workflow_reports_are_separate(self):
        result = self.run_fixture()
        native = {**result, "backend": "native", "workflow_id": ""}
        self.assertEqual(len(summarize([native, result])), 2)

    def test_native_stream_usage_parsers(self):
        deep = stream_result("deepseek", [{"id": "d", "choices": [{"finish_reason": "stop"}], "usage": {"prompt_tokens": 2, "completion_tokens": 3}}])
        self.assertEqual(deep["usage"]["completion_tokens"], 3)
        opened = stream_result("openai", [{"type": "response.completed", "response": {"usage": {"input_tokens": 2}}}])
        self.assertEqual(opened["usage"]["input_tokens"], 2)
        claude = stream_result("anthropic", [{"type": "message_start", "message": {"usage": {"input_tokens": 2, "output_tokens": 1}}},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 3}}, {"type": "message_stop"}])
        self.assertEqual(claude["usage"]["output_tokens"], 3)

    def test_batch_stops_on_unknown_usage_and_refuses_replay(self):
        config = read_json(ROOT / "configs/workflow-single.json")
        config["workflow"] = str(ROOT / "configs/workflows/daily-review.json")
        config["tasks"] = [str(ROOT / "tickets/clamp-boundaries/task.json")]
        config["architectures"][0]["models"] = [self.model.id]
        config["repeats"] = 2
        path = self.root / "experiment.json"; save_json(path, config)
        unknown = {"run_id": "unknown", "status": "stopped", "stop_reason": "usage_unknown", "turns_completed": 0, "turns_expected": 4,
                   "accounting": {"usage_complete": False}}
        with patch("agent_lab.providers.require_credential", return_value="fixture"), \
             patch("agent_lab.workflow_experiments.run_workflow", return_value=unknown) as runner, \
             patch("agent_lab.workflow_experiments.write_report"):
            result = run_workflow_batch(path, {self.model.id: self.model}, self.root / "batch")
        self.assertEqual(result["status"], "usage_unknown")
        self.assertEqual(runner.call_count, 1)


if __name__ == "__main__":
    unittest.main()
