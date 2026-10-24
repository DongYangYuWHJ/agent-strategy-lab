from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.domain import Limits, Model, Pricing, Task, read_json
from agent_lab.providers import AnthropicProvider, DeepSeekProvider, OpenAIProvider, ProviderError
from agent_lab.runner import run_task, SYSTEM
from agent_lab.token_counting import TokenCountError, deepseek_counter
from agent_lab.tools import TOOLS


def client_for(kind, model_name="test-model"):
    cls = {"openai": OpenAIProvider, "anthropic": AnthropicProvider, "deepseek": DeepSeekProvider}[kind]
    model = Model("counted-" + kind, kind, model_name, Pricing("0.1", "0.5"),
                  max_output_tokens=16384, reasoning_effort="low", token_counting="model")
    client = cls(model, SYSTEM, "Count this task", TOOLS)
    client._api_key = "test-only"
    return client


class TokenCountingTests(unittest.TestCase):
    def test_deepseek_counts_tools_reasoning_and_results_without_mutating_request(self):
        client = client_for("deepseek", "deepseek-flash")
        first = client.count_input_tokens(client.prepare(), 30)
        reply = client.accept({"choices": [{"finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None, "reasoning_content": "Consider the constraints. " * 100,
            "tool_calls": [{"id": "a", "function": {"name": "write_file", "arguments":
                json.dumps({"path": "solution.py", "content": "print('hello')"})}}]}}]})
        client.add_results([(reply.calls[0], {"ok": True})])
        payload = client.prepare()
        before = deepcopy(payload)
        count = client.count_input_tokens(payload, 30)
        self.assertGreater(count, first)
        self.assertEqual(payload, before)
        self.assertLess(count + 256, client.estimate_input_tokens(payload))
        self.assertEqual(client.token_counting_info()["method"], "deepseek_v41_local")

    def test_deepseek_counter_does_not_silently_use_another_model_tokenizer(self):
        with self.assertRaises(TokenCountError):
            client_for("deepseek", "deepseek-v4-pro").count_input_tokens(
                client_for("deepseek", "deepseek-v4-pro").prepare(), 30)

    def test_deepseek_counter_rejects_unsupported_multimodal_inputs(self):
        client = client_for("deepseek", "deepseek-flash")
        payload = client.prepare()
        payload["messages"][-1]["content"] = [{"type": "image_url", "image_url": {"url": "https://example.com"}}]
        with self.assertRaises(TokenCountError):
            client.count_input_tokens(payload, 30)

    def test_openai_counts_the_same_model_tools_and_encrypted_history(self):
        client = client_for("openai")
        client.accept({"usage": {"output_tokens": 100}, "output": [
            {"type": "reasoning", "encrypted_content": "opaque-state", "summary": []}]})
        payload = client.prepare()
        with patch("agent_lab.providers.request_json", return_value={"input_tokens": 1500}) as request:
            self.assertEqual(client.count_input_tokens(payload, 17), 1500)
        url, counted, _, timeout = request.call_args.args
        self.assertTrue(url.endswith("/responses/input_tokens"))
        self.assertEqual(counted["model"], payload["model"])
        self.assertEqual(counted["input"], payload["input"])
        self.assertEqual(counted["tools"], payload["tools"])
        self.assertEqual(timeout, 17)
        self.assertNotIn("max_output_tokens", counted)

    def test_claude_counter_keeps_thinking_and_tool_schema(self):
        client = client_for("anthropic")
        client.accept({"content": [{"type": "thinking", "thinking": "state", "signature": "sig"}]})
        payload = client.prepare()
        with patch("agent_lab.providers.request_json", return_value={"input_tokens": 700}) as request:
            self.assertEqual(client.count_input_tokens(payload, 30), 700)
        url, counted, _, _ = request.call_args.args
        self.assertTrue(url.endswith("/messages/count_tokens"))
        for key in ("model", "system", "messages", "tools", "thinking"):
            self.assertEqual(counted[key], payload[key])
        self.assertNotIn("max_tokens", counted)

    def test_counter_failure_or_invalid_count_is_not_zero_or_a_generation_retry(self):
        for kind in ("openai", "anthropic"):
            client = client_for(kind)
            for raw in ({}, {"input_tokens": -1}, {"input_tokens": True}, {"input_tokens": "100"}):
                with self.subTest(provider=kind, response=raw):
                    with patch("agent_lab.providers.request_json", return_value=raw) as request:
                        with self.assertRaises(TokenCountError):
                            client.count_input_tokens(client.prepare(), 30)
                    self.assertEqual(request.call_count, 1)
            with patch("agent_lab.providers.request_json", side_effect=ProviderError("timeout")):
                with self.assertRaises(TokenCountError):
                    client.count_input_tokens(client.prepare(), 30)

    def test_invalid_configuration_rejected(self):
        with self.assertRaises(ValueError):
            replace(client_for("openai").model, token_counting="unknown")
        for values in ({"token_count_margin": 0}, {"token_count_margin": True}, {"token_count_timeout_seconds": -1}):
            with self.assertRaises(ValueError):
                Limits(**values)


class CountedRunTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.task = Task.load(ROOT / "tickets/clamp-boundaries/task.json")
        self.client = client_for("openai")

    def run_client(self, **limits):
        with patch("agent_lab.runner.make_provider", return_value=self.client):
            return run_task(self.task, self.client.model, Limits(**limits), self.root / "runs")

    def test_model_count_is_used_for_admission_but_not_added_to_real_usage(self):
        raw = {"usage": {"input_tokens": 900, "output_tokens": 100}, "output": [
            {"type": "function_call", "call_id": "a", "name": "submit", "arguments": '{"summary":"done"}'}]}
        with patch.object(self.client, "count_input_tokens", return_value=1000) as count, \
             patch.object(self.client, "send", return_value=raw):
            result = self.run_client(max_repairs=0, token_count_margin=256)
        self.assertEqual(count.call_count, 1)
        self.assertEqual(result["accounting"]["calls"], 1)
        self.assertEqual(result["accounting"]["total_tokens"], 1000)
        self.assertTrue(result["accounting"]["usage_complete"])
        events = [json.loads(line) for line in (Path(result["artifact_dir"]) / "events.jsonl").read_text().splitlines()]
        comparison = next(event for event in events if event["type"] == "input_count_comparison")
        self.assertEqual(comparison["reserved_input_tokens"], 1256)
        self.assertEqual(comparison["reported_input_tokens"], 900)
        self.assertEqual(read_json(Path(result["artifact_dir"]) / "config.json")["token_counting"]["method"], "openai_count_api")

    def test_failed_count_never_sends_generation_or_claims_unknown_generation_spend(self):
        with patch.object(self.client, "count_input_tokens", side_effect=TokenCountError("count failed")), \
             patch.object(self.client, "send", side_effect=AssertionError("must not generate")):
            result = self.run_client()
        self.assertEqual(result["stop_reason"], "input_count_error")
        self.assertEqual(result["accounting"]["calls"], 0)
        self.assertTrue(result["accounting"]["usage_complete"])
        self.assertEqual(result["accounting"]["unknown_calls"], 0)

    def test_wire_limit_applies_before_remote_counting(self):
        with patch.object(self.client, "count_input_tokens", side_effect=AssertionError("must not count")), \
             patch.object(self.client, "send", side_effect=AssertionError("must not generate")):
            result = self.run_client(max_request_bytes=1)
        self.assertEqual(result["stop_reason"], "request_size_limit")

    def test_counted_input_and_margin_still_obey_cumulative_token_limit(self):
        with patch.object(self.client, "count_input_tokens", return_value=1000), \
             patch.object(self.client, "send", side_effect=AssertionError("must not generate")):
            result = self.run_client(max_total_tokens=17000)
        self.assertEqual(result["stop_reason"], "token_limit")
        self.assertEqual(result["accounting"]["calls"], 0)


if __name__ == "__main__":
    unittest.main()
