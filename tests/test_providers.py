import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent_lab.domain import Model, Pricing, ToolCall
from agent_lab.providers import AnthropicProvider, DeepSeekProvider, OpenAIProvider
from agent_lab.tools import TOOLS


def provider(cls, kind):
    return cls(Model("test", kind, "test-model", Pricing("1", "2"),
                     reasoning_effort="low" if kind == "deepseek" else "medium"), "system", "task", TOOLS)


class ProviderProtocolTests(unittest.TestCase):
    def test_large_encrypted_state_uses_reported_output_allowance_not_ciphertext_bytes(self):
        client = provider(OpenAIProvider, "openai")
        raw = {"status": "completed", "usage": {"input_tokens": 100, "output_tokens": 2300},
               "output": [{"type": "reasoning", "encrypted_content": "x" * 200000, "summary": []},
                          {"type": "function_call", "call_id": "a", "name": "list_files", "arguments": "{}"}]}
        reply = client.accept(raw)
        client.add_results([(reply.calls[0], {"ok": True})])
        request = client.prepare()
        self.assertGreater(len(json.dumps(request).encode()), 200000)
        self.assertEqual(request["input"][1]["encrypted_content"], "x" * 200000)
        estimate = client.estimate_input_tokens(request)
        self.assertGreater(estimate, 2300 + 2048)
        self.assertLess(estimate, 12000)
        # A second response contributes its complete output allowance as well.
        client.accept({"usage": {"output_tokens": 1500}, "output": [
            {"type": "reasoning", "encrypted_content": "y" * 100000, "summary": []}]})
        self.assertGreaterEqual(client.estimate_input_tokens(client.prepare()), estimate + 1500)
        # Ordinary source/tool text is still counted and bounded.
        client.add_user("z" * 70000)
        self.assertGreater(client.estimate_input_tokens(client.prepare()), 70000)

    def test_truncated_tool_calls_are_never_accepted(self):
        examples = [
            (OpenAIProvider, "openai", {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"},
             "output": [{"type": "function_call", "call_id": "c", "name": "submit", "arguments": "{partial"}]}),
            (DeepSeekProvider, "deepseek", {"choices": [{"finish_reason": "length", "message": {
                "tool_calls": [{"id": "c", "function": {"name": "submit", "arguments": "{partial"}}]}}]}),
            (AnthropicProvider, "anthropic", {"stop_reason": "max_tokens", "content": [
                {"type": "tool_use", "id": "c", "name": "submit", "input": {"summary": "partial"}}]})]
        for cls, kind, raw in examples:
            with self.subTest(provider=kind):
                client = provider(cls, kind)
                reply = client.accept(raw)
                self.assertEqual(reply.incomplete_reason, "length" if kind == "deepseek" else "max_output_tokens")
                self.assertEqual(reply.calls, [])
                self.assertEqual(len(client.messages), 1)

    def test_openai_preserves_reasoning_and_tool_call_ids(self):
        client = provider(OpenAIProvider, "openai")
        raw = {"output": [{"type": "reasoning", "id": "rs", "encrypted_content": "encrypted", "summary": []},
                          {"type": "function_call", "id": "fc", "call_id": "call-a", "name": "list_files", "arguments": "{}"}]}
        reply = client.accept(raw)
        client.add_results([(reply.calls[0], {"ok": True, "files": []})])
        request = client.prepare()
        self.assertEqual(request["input"][1], raw["output"][0])
        self.assertEqual(request["input"][-1]["call_id"], "call-a")
        self.assertFalse(request["store"])
        self.assertIn("reasoning.encrypted_content", request["include"])

    def test_openai_usage_cache_and_reasoning_are_subsets(self):
        client = provider(OpenAIProvider, "openai")
        usage = client.usage({"usage": {"input_tokens": 100, "output_tokens": 30,
                                      "input_tokens_details": {"cached_tokens": 80},
                                      "output_tokens_details": {"reasoning_tokens": 20}}})
        self.assertEqual(usage.total, 130)
        self.assertEqual(usage.cached_input_tokens, 80)

    def test_deepseek_preserves_thinking_message(self):
        client = provider(DeepSeekProvider, "deepseek")
        message = {"role": "assistant", "content": None, "reasoning_content": "original reasoning",
                   "tool_calls": [{"id": "c", "type": "function", "function": {"name": "list_files", "arguments": "{}"}}]}
        reply = client.accept({"choices": [{"message": message}]})
        client.add_results([(reply.calls[0], {"ok": True})])
        self.assertEqual(client.prepare()["messages"][-2]["reasoning_content"], "original reasoning")
        self.assertEqual(client.prepare()["messages"][-1]["tool_call_id"], "c")
        self.assertEqual(client.prepare()["reasoning_effort"], "low")

    def test_deepseek_cache_usage(self):
        usage = provider(DeepSeekProvider, "deepseek").usage(
            {"usage": {"prompt_tokens": 100, "completion_tokens": 30,
                       "prompt_cache_hit_tokens": 70, "completion_tokens_details": {"reasoning_tokens": 20}}})
        self.assertEqual(usage.total, 130)
        self.assertEqual(usage.cached_input_tokens, 70)

    def test_anthropic_adds_exclusive_cache_counters_once(self):
        usage = provider(AnthropicProvider, "anthropic").usage(
            {"usage": {"input_tokens": 10, "cache_read_input_tokens": 20,
                       "cache_creation_input_tokens": 30, "output_tokens": 40}})
        self.assertEqual(usage.input_tokens, 60)
        self.assertEqual(usage.total, 100)

    def test_anthropic_thinking_signature_and_grouped_tool_results(self):
        client = provider(AnthropicProvider, "anthropic")
        content = [{"type": "thinking", "thinking": "reasoning", "signature": "sig"},
                   {"type": "tool_use", "id": "a", "name": "list_files", "input": {}},
                   {"type": "tool_use", "id": "b", "name": "search", "input": {"query": "def"}}]
        reply = client.accept({"content": content})
        client.add_results([(call, {"ok": True}) for call in reply.calls])
        self.assertEqual(client.prepare()["messages"][-2]["content"], content)
        self.assertEqual([item["tool_use_id"] for item in client.prepare()["messages"][-1]["content"]], ["a", "b"])

    def test_missing_usage_is_not_zero_usage(self):
        for cls, kind in [(OpenAIProvider, "openai"), (DeepSeekProvider, "deepseek"), (AnthropicProvider, "anthropic")]:
            with self.subTest(kind=kind), self.assertRaises(KeyError):
                provider(cls, kind).usage({})

    def test_bad_tool_arguments_do_not_execute_as_valid_arguments(self):
        client = provider(OpenAIProvider, "openai")
        reply = client.accept({"output": [{"type": "function_call", "call_id": "c", "name": "write_file", "arguments": "{oops"}]})
        self.assertIn("_invalid_arguments", reply.calls[0].arguments)


if __name__ == "__main__":
    unittest.main()
