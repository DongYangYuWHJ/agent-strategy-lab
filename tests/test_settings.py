from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab import settings
from agent_lab.cli import main
from agent_lab.domain import Limits, Task, load_models, save_json
from agent_lab.providers import AnthropicProvider, DeepSeekProvider, OpenAIProvider
from agent_lab.reporting import write_report
from agent_lab.runner import run_task
from test_providers import provider


class CredentialTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "settings.local.json"
        # Preserve platform variables needed by checks without preserving credentials.
        environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "LANG") if key in os.environ}
        for patcher in (patch.dict(os.environ, environment, clear=True),
                        patch.object(settings, "LOCAL_SETTINGS", self.path)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def keys(self, **values):
        save_json(self.path, {"schema_version": 1,
                              "providers": {name: {"api_key": value} for name, value in values.items()}})

    def test_environment_overrides_file_without_mutating_environment(self):
        self.keys(openai="file-secret", deepseek="deep-secret")
        os.environ["OPENAI_API_KEY"] = "env-secret"
        before = dict(os.environ)
        self.assertEqual(settings.resolve_credential("openai"), ("env-secret", "environment"))
        self.assertEqual(settings.resolve_credential("deepseek"), ("deep-secret", "local_file"))
        self.assertEqual(dict(os.environ), before)

    def test_blank_environment_uses_file_and_unused_keys_remain_missing(self):
        self.keys(openai="local-secret", anthropic="")
        os.environ["OPENAI_API_KEY"] = "   "
        self.assertEqual(settings.resolve_credential("openai"), ("local-secret", "local_file"))
        self.assertEqual(settings.resolve_credential("anthropic"), ("", "missing"))
        self.assertEqual(settings.resolve_credential("deepseek"), ("", "missing"))

    def test_all_three_providers_use_credentials_only_in_headers(self):
        self.keys(openai="open-secret", deepseek="deep-secret", anthropic="claude-secret")
        for cls, kind, secret in [(OpenAIProvider, "openai", "open-secret"),
                                  (DeepSeekProvider, "deepseek", "deep-secret"),
                                  (AnthropicProvider, "anthropic", "claude-secret")]:
            with self.subTest(provider=kind):
                client = provider(cls, kind)
                client.preflight()
                payload = client.prepare()
                with patch("agent_lab.providers.request_json", return_value={}) as request:
                    client.send(payload, 1)
                headers = request.call_args.args[2]
                self.assertIn(secret, " ".join(headers.values()))
                self.assertNotIn(secret, json.dumps(payload))
                self.assertNotIn(settings.KEY_NAMES[kind], os.environ)

    def test_missing_key_fails_before_run_records_or_requests(self):
        model = load_models(ROOT / "configs" / "models.json")["gpt-6-luna"]
        task = Task.load(ROOT / "tickets" / "clamp-boundaries" / "task.json")
        with patch("agent_lab.providers.request_json") as request:
            with self.assertRaisesRegex(ValueError, "settings.local.json"):
                run_task(task, model, Limits(), self.root / "runs")
        request.assert_not_called()
        self.assertFalse((self.root / "runs").exists())

    def test_status_and_parse_errors_never_print_secret_contents(self):
        secret = "never-display-this-key"
        self.keys(openai=secret)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["check-settings"]), 0)
        self.assertIn("已配置", output.getvalue())
        self.assertNotIn(secret, output.getvalue())
        self.path.write_text('{"' + secret + '\n', encoding="utf-8")
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(main(["check-settings"]), 2)
        self.assertNotIn(secret, error.getvalue())
        self.assertIn("valid UTF-8 JSON", error.getvalue())

    def test_invalid_configuration_or_header_values_are_rejected_without_echo(self):
        secret = "do-not-echo"
        for value in (None, {"schema_version": True, "providers": {}},
                      {"schema_version": 1, "providers": {secret: {"api_key": secret}}},
                      {"schema_version": 1, "providers": {"openai": {"api_key": 123}}},
                      {"schema_version": 1, "providers": {"openai": {"api_key": secret + "\nInjected: value"}}}):
            with self.subTest(value=value):
                save_json(self.path, value)
                with self.assertRaises(ValueError) as failure:
                    settings.resolve_credential("openai")
                self.assertNotIn(secret, str(failure.exception))
        self.path.write_bytes(b" " * 16385)
        with self.assertRaisesRegex(ValueError, "size limit"):
            settings.resolve_credential("openai")
        os.environ["OPENAI_API_KEY"] = secret + "\nInjected: value"
        with self.assertRaisesRegex(ValueError, "invalid characters"):
            settings.resolve_credential("openai")

    def test_offline_live_protocol_run_and_report_exclude_local_credentials(self):
        secret = "sentinel-private-openai-key"
        self.keys(openai=secret)
        model = load_models(ROOT / "configs" / "models.json")["gpt-6-luna"]
        task = Task.load(ROOT / "tickets" / "clamp-boundaries" / "task.json")
        raw = {"id": "offline", "model": model.model,
               "output": [{"type": "function_call", "call_id": "submit", "name": "submit",
                           "arguments": json.dumps({"summary": "Unmodified submission"})}],
               "usage": {"input_tokens": 100, "output_tokens": 20}}
        with patch("agent_lab.providers.request_json", side_effect=[{"input_tokens": 100}, raw]) as request:
            result = run_task(task, model, Limits(max_repairs=0), self.root / "runs")
        self.assertEqual(request.call_count, 2)
        self.assertTrue(request.call_args_list[0].args[0].endswith("/responses/input_tokens"))
        self.assertEqual(result["stop_reason"], "repair_limit")
        self.assertTrue(result["accounting"]["usage_complete"])
        write_report(self.root / "runs")
        for file in (self.root / "runs").rglob("*"):
            if file.is_file():
                self.assertNotIn(secret.encode(), file.read_bytes(), str(file))


if __name__ == "__main__":
    unittest.main()
