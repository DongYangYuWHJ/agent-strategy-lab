from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.domain import Model, Pricing, Task, Limits, read_json
from agent_lab.opencode_workflow import opencode_config, OpenCodeSession, run_workflow
from agent_lab.opencode_permissions import (ROLE_AGENT_IDS, PermissionConfigurationError,
    audit_registered_agents, role_ids, permission_probes)
from agent_lab.workflows import Workflow


def registered(config):
    agents = []
    for name, item in config["agents"].items():
        provider, model = item["model"].split("/", 1)
        agents.append({"id": name, **item, "model": {"providerID": provider, "id": model},
            "permissions": [{"action": "edit", "resource": "*", "effect": "allow"}, *item["permissions"],
                            {"action": "browser", "resource": "*", "effect": "deny"}]})
    # Legacy roles may stay registered but must never be selected or delegated to.
    agents.append({"id": "lab-worker", "permissions": [{"action": "edit", "resource": "*", "effect": "allow"}]})
    return agents


@contextmanager
def fake_server(*args):
    yield "http://fixture", "fixture"


class PermissionTests(unittest.TestCase):
    def setUp(self):
        self.model = Model("test-deep", "deepseek", "fixture", Pricing("1", "2"), max_output_tokens=256, reasoning_effort="low")
        self.config = opencode_config([self.model, self.model], "http://127.0.0.1:1/fixture", Limits(), "planner_worker")
        self.expected = {"roles": role_ids("planner_worker"), "agents": self.config["agents"]}

    def test_old_allow_before_role_reset_is_overridden(self):
        result = audit_registered_agents(registered(self.config), self.expected)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(item["deny_boundary_index"] == 1 for item in result))

    def test_native_and_broad_grants_after_reset_are_rejected(self):
        for action, resource, effect in [("edit", "*", "allow"), ("shell", "*", "ask"),
                ("*", "*", "allow"), ("lab_worker_*", "*", "allow"),
                ("subagent", "lab-worker", "allow")]:
            with self.subTest(action=action):
                agents = registered(self.config)
                agents[1]["permissions"].append({"action": action, "resource": resource, "effect": effect})
                with self.assertRaises(PermissionConfigurationError):
                    audit_registered_agents(agents, self.expected)

    def test_overridden_worker_model_or_instructions_fail_audit(self):
        for field, value in [("model", {"providerID": "other", "id": "other"}),
                             ("system", "overridden"), ("mode", "primary")]:
            agents = registered(self.config)
            agents[1][field] = value
            with self.assertRaises(PermissionConfigurationError):
                audit_registered_agents(agents, self.expected)

    def test_missing_role_or_deny_boundary_is_rejected(self):
        with self.assertRaises(PermissionConfigurationError):
            audit_registered_agents(registered(self.config)[:1], self.expected)
        agents = registered(self.config)
        agents[1]["permissions"] = [r for r in agents[1]["permissions"] if r["action"] != "*"]
        with self.assertRaises(PermissionConfigurationError):
            audit_registered_agents(agents, self.expected)

    def test_namespace_and_delegation_target_are_consistent(self):
        planner = self.config["agents"][ROLE_AGENT_IDS["planner"]]
        worker = self.config["agents"][ROLE_AGENT_IDS["worker"]]
        self.assertIn(ROLE_AGENT_IDS["worker"], planner["system"])
        self.assertIn(ROLE_AGENT_IDS["worker"], worker["system"])
        self.assertNotIn("{{EXECUTOR_AGENT_ID}}", planner["system"])
        self.assertIn({"action": "subagent", "resource": ROLE_AGENT_IDS["worker"], "effect": "allow"}, planner["permissions"])
        self.assertFalse(any(p["action"] == "subagent" for p in worker["permissions"]))
        self.assertFalse(any(p["action"] == "lab_planner_write_file" for p in planner["permissions"]))
        self.assertTrue(any(p["action"] == "lab_worker_write_file" for p in worker["permissions"]))

    def test_preflight_permission_error_stops_before_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            api_calls = []
            def unsafe_api(url, path, password, *args, **kwargs):
                api_calls.append(path)
                self.assertTrue(path.startswith("/api/agent?"))
                config = read_json(next((root / "runs").glob("*/opencode-config.json")))
                agents = registered(config)
                agents[0]["permissions"].append({"action": "edit", "resource": "*", "effect": "allow"})
                return {"data": agents}
            with patch("agent_lab.providers.require_credential", return_value="fixture"), \
                 patch("agent_lab.opencode_workflow.isolated_server", fake_server), \
                 patch("agent_lab.opencode_workflow.request", side_effect=unsafe_api), \
                 patch("agent_lab.workflow_gateway.forward_stream", side_effect=AssertionError("must not generate")):
                result = run_workflow(Task.load(ROOT / "tickets/clamp-boundaries/task.json"), [self.model], Limits(), root / "runs",
                                      Workflow.load(ROOT / "configs/workflows/daily-review.json"))
            self.assertEqual(result["stop_reason"], "permission_configuration_error")
            self.assertEqual(result["accounting"]["calls"], 0)
            self.assertEqual(result["turns_completed"], 0)
            self.assertFalse(read_json(Path(result["artifact_dir"]) / "permission-audit.json")["passed"])
            self.assertFalse(any(path.endswith("/prompt") for path in api_calls))

    def test_authoritative_permission_mismatch_stops_before_prompt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def api(url, path, password, payload=None, *args, **kwargs):
                config = read_json(next((root / "runs").glob("*/opencode-config.json")))
                if path.startswith("/api/agent?"):
                    return {"data": registered(config)}
                if path == "/api/session":
                    return {"data": {"id": "s"}}
                if path.endswith("/permission"):
                    # Registered rules appear safe but OpenCode reports edit allowed.
                    return {"data": {"effect": "allow"}}
                raise AssertionError("No prompt or generation allowed")
            with patch("agent_lab.providers.require_credential", return_value="fixture"), \
                 patch("agent_lab.opencode_workflow.isolated_server", fake_server), \
                 patch("agent_lab.opencode_workflow.request", side_effect=api), \
                 patch("agent_lab.workflow_gateway.forward_stream", side_effect=AssertionError("must not generate")):
                result = run_workflow(Task.load(ROOT / "tickets/clamp-boundaries/task.json"), [self.model], Limits(), root / "runs",
                                      Workflow.load(ROOT / "configs/workflows/daily-review.json"))
            self.assertEqual(result["stop_reason"], "permission_configuration_error")
            audit = read_json(Path(result["artifact_dir"]) / "permission-audit.json")
            self.assertFalse(audit["passed"])
            self.assertEqual(audit["probes"][0]["observed"], "allow")
            self.assertEqual(result["accounting"]["calls"], 0)


if __name__ == "__main__":
    unittest.main()
