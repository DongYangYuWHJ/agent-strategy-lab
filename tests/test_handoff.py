"""Handoff controls: same-session selection, phase gates, and shared accounting."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.accounting import StopRun
from agent_lab.domain import Limits, Model, Pricing, Task, read_json
from agent_lab.opencode_permissions import ROLE_AGENT_IDS, audit_registered_agents, role_ids
from agent_lab.opencode_workflow import OpenCodeSession, model_ref, opencode_config, run_workflow
from agent_lab.workflows import Workflow


@contextmanager
def fake_server(*args):
    yield "http://fixture", "fixture"


class HandoffSession:
    selections = []
    fail_plan = False
    fail_switch = False

    def __init__(self, url, password, workspace, directory, models, strategy, gateway):
        self.gateway = gateway

    def select_primary(self, role, model, turn_dir):
        if role == "worker" and self.fail_switch:
            raise StopRun("agent_switch_error")
        self.selections.append(role)
        self.model = model

    def run_turn(self, text, turn_dir):
        g = self.gateway
        g.generation(self.model.id, "chat/completions", {"model": self.model.model,
                     "messages": [{"role": "user", "content": text}]})
        if g.turn == "plan" and self.fail_plan:
            raise StopRun("needs_user_input")
        if g.turn == "implement":
            task = Task.load(ROOT / "tickets/clamp-boundaries/task.json")
            action = next(a for batch in read_json(task.manifest_path.parent / "replay.json")
                          for a in batch if a["name"] == "write_file")
            result = g.mcp("worker", {"id": 1, "method": "tools/call", "params": action})
            assert not result["isError"]

    def close(self):
        pass


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = Model("planner", "deepseek", "fixture", Pricing("1", "2"), max_output_tokens=256, reasoning_effort="low")
        self.worker = replace(self.model, id="executor")
        self.workflow = Workflow.load(ROOT / "configs/workflows/daily-review.json")
        HandoffSession.selections = []
        HandoffSession.fail_plan = HandoffSession.fail_switch = False

    def run_fixture(self, limits=None):
        def response(client, payload, timeout):
            return b"fixture", {"id": "fixture", "model": "fixture", "usage": {"prompt_tokens": 100, "completion_tokens": 30},
                                "choices": [{"finish_reason": "stop"}]}
        with patch("agent_lab.providers.require_credential", return_value="fixture"), \
             patch("agent_lab.workflow_gateway.forward_stream", side_effect=response), \
             patch("agent_lab.opencode_workflow.isolated_server", fake_server):
            return run_workflow(Task.load(ROOT / "tickets/clamp-boundaries/task.json"), [self.model, self.worker],
                limits or Limits(), self.root, self.workflow, "planner_handoff", session_factory=HandoffSession)

    def test_handoff_has_two_primaries_and_no_delegation_grant(self):
        config = opencode_config([self.model, self.worker], "http://fixture", Limits(), "planner_handoff")
        agents = []
        for name, item in config["agents"].items():
            self.assertEqual(item["mode"], "primary")
            self.assertFalse(any(p["action"] == "subagent" and p["effect"] == "allow" for p in item["permissions"]))
            provider, model = item["model"].split("/", 1)
            agents.append({"id": name, **item, "model": {"providerID": provider, "id": model}})
        expected = {"roles": role_ids("planner_handoff"), "agents": config["agents"], "strategy": "planner_handoff"}
        self.assertEqual(len(audit_registered_agents(agents, expected)), 2)
        agents[0]["permissions"].append({"action": "subagent", "resource": ROLE_AGENT_IDS["worker"], "effect": "allow"})
        with self.assertRaises(ValueError):
            audit_registered_agents(agents, expected)

    def test_turn_ownership_and_cumulative_snapshots(self):
        result = self.run_fixture()
        self.assertTrue(result["accepted"])
        self.assertEqual(HandoffSession.selections, ["planner", "worker", "worker", "worker"])
        self.assertEqual([t["model_id"] for t in result["turns"]], ["planner", "executor", "executor", "executor"])
        self.assertEqual([t["accounting_cumulative"]["total_tokens"] for t in result["turns"]], [130, 260, 390, 520])
        events = [json.loads(line) for line in (Path(result["artifact_dir"]) / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([e["primary_role"] for e in events if e["type"] == "request_started"], HandoffSession.selections)

    def test_budget_does_not_reset_at_handoff(self):
        result = self.run_fixture(Limits(max_calls=2))
        self.assertEqual(result["stop_reason"], "call_limit")
        self.assertEqual(result["accounting"]["calls"], 2)
        self.assertEqual(result["turns_completed"], 2)
        self.assertIsNone(result["final_evidence"])

    def test_writable_first_turn_is_rejected_without_generation(self):
        workflow = replace(self.workflow, turns=(replace(self.workflow.turns[0], allow_write=True), *self.workflow.turns[1:]))
        with patch("agent_lab.workflow_gateway.forward_stream") as upstream:
            with self.assertRaisesRegex(ValueError, "read-only first plan"):
                run_workflow(Task.load(ROOT / "tickets/clamp-boundaries/task.json"), [self.model, self.worker],
                             Limits(), self.root, workflow, "planner_handoff")
            upstream.assert_not_called()

    def test_failed_plan_or_switch_does_not_generate_next_turn(self):
        for flag, calls, turns, reason in [("fail_plan", 1, 0, "needs_user_input"),
                                            ("fail_switch", 1, 1, "agent_switch_error")]:
            with self.subTest(flag=flag):
                HandoffSession.fail_plan = HandoffSession.fail_switch = False
                setattr(HandoffSession, flag, True)
                result = self.run_fixture()
                self.assertEqual(result["stop_reason"], reason)
                self.assertEqual(result["accounting"]["calls"], calls)
                self.assertEqual(result["turns_completed"], turns)
                self.assertIsNone(result["final_evidence"])

    def test_inactive_role_and_wrong_model_are_blocked_before_upstream(self):
        # Reuse the runner's real gateway through a capturing session.
        class CapturingSession(HandoffSession):
            def select_primary(inner, role, model, turn_dir):
                super().select_primary(role, model, turn_dir)
                g = inner.gateway
                g.closed = False
                try:
                    wrong = "executor" if role == "planner" else "planner"
                    with self.assertRaisesRegex(StopRun, "unexpected_model"):
                        g.generation(wrong, "chat/completions", {"model": "fixture"})
                    with self.assertRaisesRegex(StopRun, "inactive_agent"):
                        g.mcp("worker" if role == "planner" else "planner", {"id": 1, "method": "tools/call"})
                finally:
                    g.closed = True
        with patch("agent_lab.providers.require_credential", return_value="fixture"), \
             patch("agent_lab.opencode_workflow.isolated_server", fake_server), \
             patch("agent_lab.workflow_gateway.forward_stream", return_value=(b"", {"usage": {"prompt_tokens": 1, "completion_tokens": 1}, "choices": [{"finish_reason": "stop"}]})) as upstream:
            result = run_workflow(Task.load(ROOT / "tickets/clamp-boundaries/task.json"), [self.model, self.worker],
                Limits(), self.root, self.workflow, "planner_handoff", session_factory=CapturingSession)
        self.assertTrue(result["accepted"])
        self.assertEqual(upstream.call_count, 4)

    def test_busy_or_mismatched_selection_fails_closed(self):
        for mode in ("busy", "wrong_agent", "wrong_model", "ok"):
            with self.subTest(mode=mode):
                s = OpenCodeSession.__new__(OpenCodeSession)
                s.id, s.url, s.password = "same-session", "http://fixture", "fixture"
                s.gateway = Mock(turn="implement")
                state = {"id": s.id, "agent": ROLE_AGENT_IDS["planner"], "model": model_ref(self.model)}
                state["model"]["variant"] = "default"
                def call(suffix, payload=None):
                    if suffix == "/inbox":
                        return {"data": []}
                    if suffix == "/agent" and mode != "wrong_agent":
                        state["agent"] = payload["agent"]
                    if suffix == "/model" and mode != "wrong_model":
                        state["model"] = payload["model"]
                    return {"data": dict(state)}
                s.call = Mock(side_effect=call)
                directory = self.root / mode
                directory.mkdir()
                with patch("agent_lab.opencode_workflow.request", return_value={"data": {s.id: {}} if mode == "busy" else {}}):
                    if mode == "ok":
                        s.select_primary("worker", self.worker, directory)
                    else:
                        with self.assertRaisesRegex(StopRun, "agent_switch_error"):
                            s.select_primary("worker", self.worker, directory)
                evidence = read_json(directory / "selection.json")
                self.assertEqual(evidence["passed"], mode == "ok")
                self.assertFalse(any(c.args[0] == "/prompt" for c in s.call.call_args_list))


if __name__ == "__main__":
    unittest.main()
