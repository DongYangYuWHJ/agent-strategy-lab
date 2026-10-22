from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent_lab.accounting import Ledger, StopRun, usage_cost
from agent_lab.domain import Limits, Model, Pricing, Usage
from agent_lab.reporting import summarize


def model():
    return Model("test", "mock", "fixture", Pricing("2", "10", "0.2", "2.5"), 512)


class AccountingTests(unittest.TestCase):
    def test_wire_bytes_are_independent_of_input_token_estimate(self):
        ledger = Ledger(Limits())
        ledger.reserve(model(), 200000, 5000)
        self.assertEqual(ledger.calls, 1)

    def test_transport_and_input_estimate_limits_stop_before_sending(self):
        for wire_bytes, estimate, reason in [(1048577, 5000, "request_size_limit"),
                                              (200000, 64001, "input_estimate_limit")]:
            with self.subTest(reason=reason):
                ledger = Ledger(Limits())
                with self.assertRaisesRegex(StopRun, reason):
                    ledger.reserve(model(), wire_bytes, estimate)
                self.assertEqual(ledger.calls, 0)

    def test_large_wire_request_still_obeys_token_and_money_budgets(self):
        for limits, reason in [(Limits(max_total_tokens=5500), "token_limit"),
                                (Limits(max_cost_usd="0.001"), "budget_limit")]:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(StopRun, reason):
                    Ledger(limits).reserve(model(), 200000, 5000)

    def test_input_and_transport_configuration_bounds_are_separate(self):
        Limits(max_request_bytes=1048576, max_estimated_input_tokens=64000)
        for kwargs in ({"max_request_bytes": 1048577}, {"max_estimated_input_tokens": 64001}):
            with self.assertRaises(ValueError):
                Limits(**kwargs)

    def test_cached_and_reasoning_tokens_not_double_counted(self):
        usage = Usage(1000, 200, 400, 100, 150)
        self.assertEqual(usage.total, 1200)
        self.assertEqual(usage_cost(usage, model().pricing), Decimal("0.00333"))

    def test_budget_reservation_blocks_before_a_call(self):
        ledger = Ledger(Limits(max_cost_usd="0.00001"))
        with self.assertRaisesRegex(StopRun, "budget_limit"):
            ledger.reserve(model(), 100)
        self.assertEqual(ledger.calls, 0)

    def test_call_cap_counts_attempts(self):
        ledger = Ledger(Limits(max_calls=1))
        ledger.reserve(model(), 100)
        with self.assertRaisesRegex(StopRun, "call_limit"):
            ledger.reserve(model(), 100)

    def test_token_reservation_includes_maximum_output(self):
        ledger = Ledger(Limits(max_total_tokens=2600))
        with self.assertRaisesRegex(StopRun, "token_limit"):
            ledger.reserve(model(), 100)

    def test_observed_over_budget_stops(self):
        ledger = Ledger(Limits(max_cost_usd="0.1"))
        ledger.record(model(), Usage(1000000, 1), "r", "m")
        with self.assertRaisesRegex(StopRun, "budget_limit"):
            ledger.check_observed_limits()

    def test_zero_price_does_not_make_unknown_usage_complete(self):
        ledger = Ledger(Limits())
        ledger.mark_unknown(Decimal(0))
        self.assertFalse(ledger.summary()["usage_complete"])

    def test_invalid_usage_rejected(self):
        for usage in [(10, 2, 11), (10, 2, 8, 3), (10, 2, 0, 0, 3), (-1, 1), (True, 1)]:
            with self.subTest(usage=usage), self.assertRaises(ValueError):
                Usage(*usage)

    def test_nonfinite_prices_rejected(self):
        for value in ("NaN", "Infinity", "-1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Pricing(value, "1")

    def test_failed_costs_included_and_unknown_costs_do_not_rank(self):
        def result(accepted, cost, complete=True):
            return {"execution_kind": "live", "strategy": "single_agent", "model_id": "m",
                    "accepted": accepted, "duration_seconds": 1, "stop_reason": "test",
                    "accounting": {"estimated_cost_usd": cost, "unknown_cost_reserve_usd": "0",
                                   "total_tokens": 10, "usage_complete": complete}}
        row = summarize([result(True, "1"), result(False, "2")])[0]
        self.assertEqual(row["unit_accepted_cost_usd"], "3")
        self.assertIsNone(summarize([result(False, "2")])[0]["unit_accepted_cost_usd"])
        self.assertIsNone(summarize([result(True, "1"), result(False, "2", False)])[0]["unit_accepted_cost_usd"])

    def test_simulated_and_live_results_never_aggregate_together(self):
        base = {"execution_kind": "live", "strategy": "single_agent", "model_id": "m",
                "accepted": True, "duration_seconds": 1, "stop_reason": "accepted",
                "accounting": {"estimated_cost_usd": "1", "unknown_cost_reserve_usd": "0",
                               "total_tokens": 10, "usage_complete": True}}
        self.assertEqual(len(summarize([base, {**base, "execution_kind": "simulated"}])), 2)


if __name__ == "__main__":
    unittest.main()
