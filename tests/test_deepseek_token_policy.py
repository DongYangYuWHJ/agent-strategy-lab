"""Removing DeepSeek Token gates must retain money, calls, and accounting."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.accounting import Ledger, StopRun
from agent_lab.domain import Limits, Model, Pricing, Usage
from agent_lab.opencode_workflow import opencode_config
from agent_lab.providers import DeepSeekProvider
from agent_lab.telemetry import Recorder
from agent_lab.workflow_gateway import Gateway


def uncapped(**kwargs):
    return Model("test-deep", "deepseek", "deepseek-flash", Pricing("0.30", "1.20"),
                 max_output_tokens=None, reasoning_effort="low", enforce_total_token_limit=False, **kwargs)


class DeepSeekTokenPolicyTests(unittest.TestCase):
    def test_null_output_omits_native_request_cap_and_preserves_effort(self):
        for effort, reserve in [("none", 8192), ("low", 65536), ("high", 65536), ("max", 131072)]:
            with self.subTest(effort=effort):
                model = replace(uncapped(), reasoning_effort=effort)
                p = DeepSeekProvider(model, "system", "task", [])
                self.assertNotIn("max_tokens", p.prepare())
                self.assertEqual(p.prepare()["reasoning_effort"], effort)
                self.assertEqual(model.output_reserve_tokens, reserve)

    def test_other_providers_cannot_disable_token_policy(self):
        for provider in ["openai", "anthropic", "mock"]:
            with self.subTest(provider=provider), self.assertRaises(ValueError):
                replace(uncapped(), provider=provider)
        with self.assertRaises(ValueError):
            replace(uncapped(), enforce_total_token_limit="false")

    def test_uncapped_usage_is_counted_but_does_not_consume_mixed_model_token_budget(self):
        model = uncapped()
        limited = Model("sol", "openai", "fixture", Pricing("0", "0"), max_output_tokens=256)
        ledger = Ledger(Limits(max_total_tokens=1000, max_cost_usd="1"))
        ledger.reserve(model, 100, 100)
        ledger.record(model, Usage(100000, 1000), "deep", model.model)
        ledger.check_observed_limits()
        self.assertEqual(ledger.summary()["total_tokens"], 101000)
        self.assertEqual(ledger.summary()["token_budget_tokens"], 0)
        self.assertGreater(ledger.summary()["usage"]["input_tokens"], 0)
        ledger.reserve(limited, 100, 100)
        ledger.record(limited, Usage(700, 100), "sol", limited.model)
        self.assertEqual(ledger.summary()["token_budget_tokens"], 800)
        with self.assertRaisesRegex(StopRun, "token_limit"):
            ledger.reserve(limited, 100, 100)

    def test_uncapped_calls_still_obey_money_calls_and_observed_fees(self):
        model = uncapped()
        ledger = Ledger(Limits(max_total_tokens=1, max_calls=1, max_cost_usd="1"))
        reservation = ledger.reserve(model, 100, 100)
        self.assertGreaterEqual(reservation, Decimal(65536) * Decimal("1.20") / 1000000)
        with self.assertRaisesRegex(StopRun, "call_limit"):
            ledger.reserve(model, 100, 100)
        with self.assertRaisesRegex(StopRun, "budget_limit"):
            Ledger(Limits(max_cost_usd="0.001")).reserve(model, 100, 100)
        ledger = Ledger(Limits(max_cost_usd="0.01"))
        ledger.record(model, Usage(100000, 1000), "r", model.model)
        with self.assertRaisesRegex(StopRun, "budget_limit"):
            ledger.check_observed_limits()
        ledger.mark_unknown(reservation)
        self.assertFalse(ledger.summary()["usage_complete"])

    def test_gateway_strips_all_adapter_output_caps_and_accounts_large_response(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = uncapped()
            with patch("agent_lab.providers.require_credential", return_value="fixture"):
                g = Gateway(Mock(), [model], Limits(max_total_tokens=1000), root, Recorder(root), Mock(), Mock())
            g.closed = False
            raw = {"id": "fixture", "model": model.model, "usage": {"prompt_tokens": 100, "completion_tokens": 20000},
                   "choices": [{"finish_reason": "stop"}]}
            def response(provider, payload, timeout):
                for key in ("max_tokens", "max_output_tokens", "max_completion_tokens"):
                    self.assertNotIn(key, payload)
                self.assertEqual(payload["thinking"], {"type": "enabled"})
                self.assertEqual(payload["reasoning_effort"], "low")
                return b"fixture", raw
            with patch("agent_lab.workflow_gateway.forward_stream", side_effect=response):
                g.generation(model.id, "chat/completions", {"model": model.model, "messages": [],
                    "max_tokens": 16384, "max_completion_tokens": 16384, "max_output_tokens": 16384})
            self.assertEqual(g.ledger.tokens, 20100)
            self.assertGreater(g.ledger.cost, 0)
            self.assertEqual(g.ledger.token_budget_tokens, 0)
            g.started -= g.limits.max_seconds + 1
            with patch("agent_lab.workflow_gateway.forward_stream") as upstream:
                with self.assertRaisesRegex(StopRun, "time_limit"):
                    g.generation(model.id, "chat/completions", {"model": model.model, "messages": []})
                upstream.assert_not_called()

    def test_provider_length_stop_is_not_reported_as_a_local_cap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = uncapped()
            with patch("agent_lab.providers.require_credential", return_value="fixture"):
                g = Gateway(Mock(), [model], Limits(), root, Recorder(root), Mock(), Mock())
            g.closed = False
            raw = {"id": "fixture", "usage": {"prompt_tokens": 100, "completion_tokens": 65536},
                   "choices": [{"finish_reason": "length"}]}
            with patch("agent_lab.workflow_gateway.forward_stream", return_value=(b"fixture", raw)):
                with self.assertRaisesRegex(StopRun, "provider_length_limit"):
                    g.generation(model.id, "chat/completions", {"model": model.model, "messages": []})
            self.assertEqual(g.ledger.calls, 1)
            self.assertTrue(g.ledger.summary()["usage_complete"])

    def test_opencode_metadata_does_not_reintroduce_16384_cap(self):
        config = opencode_config([uncapped()], "http://fixture", Limits(), "single_agent")
        metadata = config["providers"]["lab-test-deep"]["models"]["test-deep"]["limit"]
        self.assertEqual(metadata["output"], 65536)
        self.assertEqual(metadata["context"], 1048576)


if __name__ == "__main__":
    unittest.main()
