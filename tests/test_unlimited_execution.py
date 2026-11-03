"""No paid requests: unlimited execution retains accounting and isolation."""
from dataclasses import asdict
from decimal import Decimal
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.accounting import Ledger, usage_cost
from agent_lab.domain import Limits, Task, Usage, bounded_timeout, load_models, read_json
from agent_lab.experiments import run_batch
from agent_lab.opencode_workflow import opencode_config
from agent_lab.telemetry import Recorder
from agent_lab.workflow_gateway import Gateway


def limits():
    return Limits(**read_json(ROOT / "configs/workflow-python-repo-comparison.json")["limits"])


def catalog():
    return load_models(ROOT / "configs/models-python-repo-unlimited.json")


class UnlimitedExecutionTests(unittest.TestCase):
    def test_null_policy_is_distinct_from_service_capabilities(self):
        configured = asdict(limits())
        self.assertEqual(configured.pop("token_count_margin"), 256)
        self.assertTrue(all(v is None for v in configured.values()))
        self.assertEqual(set(catalog()), {"gpt-6-luna", "deepseek-flash"})
        for model in catalog().values():
            self.assertIsNone(model.max_output_tokens)
            self.assertFalse(model.enforce_total_token_limit)
            self.assertGreater(model.output_reserve_tokens, 32768)
        with self.assertRaises(ValueError):
            Limits(token_count_margin=None)
        with self.assertRaises(ValueError):
            Limits(max_calls=False)
        self.assertEqual(Limits().max_calls, 12)

    def test_many_large_calls_keep_counting(self):
        ledger, model = Ledger(limits()), catalog()["gpt-6-luna"]
        for i in range(110):
            ledger.reserve(model, 4000000, 800000)
            ledger.record(model, Usage(800000, 130000, 100000), str(i), model.model)
            ledger.tool_step()
            ledger.check_observed_limits()
        self.assertEqual(ledger.calls, 110)
        self.assertEqual(ledger.tool_steps, 110)
        self.assertEqual(ledger.tokens, 110 * 930000)
        self.assertGreater(ledger.cost, Decimal("2"))
        self.assertTrue(ledger.summary()["usage_complete"])
        ledger.mark_unknown(Decimal("1"))
        self.assertFalse(ledger.summary()["usage_complete"])

    def test_full_request_long_context_pricing_boundary(self):
        model = catalog()["gpt-6-luna"]
        at = usage_cost(Usage(272000, 1000, 100000, 1000), model.pricing)
        over = usage_cost(Usage(272001, 1000, 100000, 1000), model.pricing)
        self.assertEqual(at, (Decimal(171000) * Decimal("0.10") + 100000 * Decimal("0.01") + 1000 * Decimal("0.125") + 1000 * Decimal("0.50")) / 1000000)
        self.assertEqual(over, (Decimal(171001) * Decimal("0.20") + 100000 * Decimal("0.02") + 1000 * Decimal("0.25") + 1000 * Decimal("0.75")) / 1000000)

    def test_no_infinity_reaches_timeout_apis(self):
        self.assertIsNone(bounded_timeout(None, math.inf))
        self.assertEqual(bounded_timeout(None, 3, math.inf), 3)
        self.assertEqual(bounded_timeout(8, 3), 3)

    def test_opencode_omits_local_input_and_step_limits(self):
        for model in catalog().values():
            config = opencode_config([model], "http://localhost/fixture", limits(), "single_agent")
            self.assertTrue(all("steps" not in a for a in config["agents"].values()))
            provider = config["providers"]["lab-" + model.id]
            self.assertNotIn("input", provider["models"][model.id]["limit"])
            self.assertEqual(provider["models"][model.id]["limit"]["context"], model.context_window)
            self.assertIs(provider["settings"]["timeout"], False)
            self.assertIs(provider["settings"]["headerTimeout"], False)
            self.assertIs(provider["settings"]["chunkTimeout"], False)
            self.assertNotIn("execution", config["mcp"]["servers"]["lab_solo"]["timeout"])

    def test_gateway_strips_sdk_caps_for_both_models(self):
        for model in catalog().values():
            with self.subTest(model=model.id), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                with patch("agent_lab.providers.require_credential", return_value="fixture"):
                    gateway = Gateway(Task.load(ROOT / "tickets/clamp-boundaries/task.json"), [model], limits(), directory, Recorder(directory), None, None)
                gateway.closed = False
                gateway.started -= 100000
                self.assertTrue(math.isinf(gateway.remaining()))
                gateway.clients[model.id].count_input_tokens = Mock(return_value=300000)
                def reply(client, payload, timeout):
                    self.assertFalse({"max_tokens", "max_output_tokens", "max_completion_tokens"} & payload.keys())
                    self.assertIsNone(timeout)
                    if model.provider == "openai":
                        raw = {"id": "fake", "model": model.model, "status": "completed", "usage": {"input_tokens": 300000, "output_tokens": 20000}, "output": []}
                    else:
                        raw = {"id": "fake", "model": model.model, "choices": [{"finish_reason": "stop"}], "usage": {"prompt_tokens": 300000, "completion_tokens": 20000, "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 300000}}
                    return b"fixture", raw
                payload = {"model": model.model, "messages": [], "input": [], "max_tokens": 1, "max_output_tokens": 1, "max_completion_tokens": 1}
                with patch("agent_lab.workflow_gateway.forward_stream", side_effect=reply):
                    gateway.generation(model.id, "responses" if model.provider == "openai" else "chat/completions", payload)
                self.assertEqual(gateway.ledger.tokens, 320000)
                self.assertEqual(gateway.ledger.calls, 1)
                self.assertTrue(gateway.ledger.summary()["usage_complete"])

    def test_null_native_batch_budget_runs_finite_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            experiment = {"schema_version": 1, "strategy": "single_agent", "models": ["mock-pass"],
                          "tasks": [str(ROOT / "tickets/clamp-boundaries/task.json")], "repeats": 1,
                          "batch_budget_usd": None, "limits": read_json(ROOT / "configs/workflow-python-repo-comparison.json")["limits"]}
            path = root / "experiment.json"
            path.write_text(json.dumps(experiment), encoding="utf-8")
            result = run_batch(path, load_models(ROOT / "configs/mock_models.json"), root / "result")
            self.assertEqual(result["status"], "completed")
            self.assertIsNone(result["configuration"]["batch_budget_usd"])


if __name__ == "__main__":
    unittest.main()
