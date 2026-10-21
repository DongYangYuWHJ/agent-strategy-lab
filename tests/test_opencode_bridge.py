import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab import opencode_bridge as bridge


class OpenCodeBridgeTests(unittest.TestCase):
    def test_environment_injects_only_selected_keys_without_changing_parent(self):
        values = {"OPENAI_API_KEY": "old-open", "DEEPSEEK_API_KEY": "old-deep",
                  "ANTHROPIC_API_KEY": "unused-claude", "PATH": "keep-path"}
        with patch.dict(os.environ, values, clear=True), \
                patch.object(bridge, "resolve_credential", return_value=("selected-secret", "local_file")):
            child = bridge.environment(("openai",))
            self.assertEqual(child["OPENAI_API_KEY"], "selected-secret")
            self.assertNotIn("DEEPSEEK_API_KEY", child)
            self.assertNotIn("ANTHROPIC_API_KEY", child)
            self.assertEqual(child["PATH"], "keep-path")
            self.assertEqual(dict(os.environ), values)

    def test_missing_credentials_stop_launch_before_interactive_child(self):
        with patch.object(bridge, "check_version"), \
                patch.object(bridge, "resolve_credential", return_value=("", "missing")), \
                patch.object(bridge.subprocess, "call") as start:
            with self.assertRaisesRegex(ValueError, "Configure the openai API key"):
                bridge.launch()
        start.assert_not_called()

    def test_redaction_removes_credentials_and_ephemeral_server_password(self):
        text = "failure secret-one\nserver password ephemeral-value\nother output"
        cleaned = bridge.redact(text, {"OPENAI_API_KEY": "secret-one"})
        self.assertNotIn("secret-one", cleaned)
        self.assertNotIn("ephemeral-value", cleaned)
        self.assertIn("other output", cleaned)

    def test_version_mismatch_prevents_interactive_launch(self):
        with patch.object(bridge, "invoke", return_value=(0, "opencode v9.9.9\n", "")), \
                patch.object(bridge.subprocess, "call") as start:
            with self.assertRaisesRegex(ValueError, "requires OpenCode 2.0.32"):
                bridge.launch()
        start.assert_not_called()

    def test_launch_inherits_terminal_without_initial_paid_prompt(self):
        with patch.object(bridge, "check_version"), \
                patch.object(bridge, "executable", return_value="opencode.exe"), \
                patch.object(bridge, "environment", return_value={"OPENAI_API_KEY": "secret"}), \
                patch.object(bridge.subprocess, "call", return_value=7) as start:
            self.assertEqual(bridge.launch(), 7)
        self.assertEqual(start.call_args.args[0], ["opencode.exe", "--standalone"])
        self.assertNotIn("capture_output", start.call_args.kwargs)

    def test_builtin_agents_do_not_satisfy_project_role_check(self):
        with self.assertRaisesRegex(ValueError, "lab-coordinator"):
            bridge.validate_agents([{"id": "build", "mode": "primary"}])

    def test_role_override_is_detected(self):
        agents = [
            {"id": "lab-coordinator", "mode": "primary", "model": {"providerID": "openai", "id": "gpt-6.1-sol"}},
            {"id": "lab-worker", "mode": "subagent", "model": {"providerID": "deepseek", "id": "deepseek-flash"}},
            {"id": "lab-solo", "mode": "primary", "model": {"providerID": "openai", "id": "gpt-6.1-sol"}},
        ]
        self.assertEqual(len(bridge.validate_agents(agents)), 3)
        agents[1]["model"]["id"] = "other-model"
        with self.assertRaisesRegex(ValueError, "lab-worker"):
            bridge.validate_agents(agents)


if __name__ == "__main__":
    unittest.main()
