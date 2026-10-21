from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent_lab.variability import build_variance_report, distribution


def sample(number, tokens, *, accepted=True, complete=True, task="t", cached=0):
    cost = Decimal(tokens - cached) + Decimal(cached) / 2
    return {"run_id": f"r{number}", "task_id": task, "model_id": "m", "strategy": "single_agent",
            "execution_kind": "simulated", "started_at": f"2026-10-12T00:00:{number:02d}Z",
            "accepted": accepted, "status": "succeeded" if accepted else "failed", "stop_reason": "test",
            "repairs": 0, "duration_seconds": 1, "artifact_dir": "unused",
            "accounting": {"calls": 1, "tool_steps": 1, "total_tokens": tokens,
                           "usage": {"input_tokens": tokens, "output_tokens": 0, "cached_input_tokens": cached},
                           "estimated_cost_usd": str(cost), "unknown_cost_reserve_usd": "0" if complete else "5",
                           "usage_complete": complete}}


def batch(results):
    plan = [{"cell": result["run_id"], "task": result["task_id"], "model": "m", "repeat": index}
            for index, result in enumerate(results)]
    return {"status": "completed", "fingerprint": "fixed", "completed": {result["run_id"]: result["run_id"] for result in results},
            "configuration": {"plan": plan, "models": [{"id": "m", "pricing": {"input": "1000000", "output": "0", "cached_input": "500000"}}]}}


class VariabilityTests(unittest.TestCase):
    def test_median_relative_range_and_sample_standard_deviation(self):
        stats = distribution([1, 2, 3])
        self.assertEqual(stats["median"], "2")
        self.assertEqual(stats["sample_stddev"], "1")
        self.assertEqual(stats["minimum_vs_median_pct"], -50)
        self.assertEqual(stats["maximum_vs_median_pct"], 50)
        self.assertEqual(stats["coefficient_of_variation_pct"], 50)
        self.assertEqual(stats["maximum_over_minimum"], 3)

    def test_no_samples_single_sample_and_zero_cost_do_not_invent_statistics(self):
        self.assertIsNone(distribution([]))
        self.assertIsNone(distribution([1])["sample_stddev"])
        self.assertIsNone(distribution([0, 0])["coefficient_of_variation_pct"])
        self.assertIsNone(distribution([0, 0])["minimum_vs_median_pct"])
        self.assertIsNone(distribution([0, 1])["maximum_over_minimum"])

    def test_failed_attempt_costs_are_included_and_grouping_is_within_task(self):
        results = [sample(1, 1), sample(2, 3, accepted=False), sample(3, 9, task="other")]
        report = build_variance_report(batch(results), results)
        group = next(group for group in report["groups"] if group["task_id"] == "t")
        self.assertEqual(group["successes"], 1)
        self.assertEqual(group["observed_runs"], 2)
        self.assertEqual(group["cost_usd"]["median"], "2")
        self.assertEqual(report["known_estimated_cost_usd"], "13")
        self.assertEqual(len(report["groups"]), 2)

    def test_unknown_usage_suppresses_cost_statistics_without_hiding_known_spend(self):
        results = [sample(1, 1), sample(2, 2, complete=False)]
        report = build_variance_report(batch(results), results)
        self.assertIsNone(report["groups"][0]["cost_usd"])
        self.assertIsNone(report["groups"][0]["uncached_reference_usd"])
        self.assertEqual(report["known_estimated_cost_usd"], "3")
        self.assertEqual(report["unknown_cost_reserve_usd"], "5")

    def test_repricing_uses_frozen_rates_and_order_not_result_directory_order(self):
        results = [sample(2, 10, cached=8), sample(1, 10, cached=0)]
        report = build_variance_report(batch(results), results)
        self.assertEqual([row["run_id"] for row in report["runs_in_order"]], ["r1", "r2"])
        self.assertEqual(report["groups"][0]["cost_usd"]["minimum"], "6")
        self.assertEqual(report["groups"][0]["uncached_reference_usd"]["minimum"], "10")
        self.assertEqual(report["groups"][0]["uncached_reference_usd"]["maximum"], "10")
        self.assertEqual(report["runs_in_order"][1]["cache_read_fraction"], 0.8)

    def test_partial_batch_and_inconsistent_cost_are_explicit(self):
        results = [sample(1, 1), sample(2, 2)]
        manifest = batch(results)
        partial = build_variance_report(manifest, results[:1])
        self.assertFalse(partial["groups"][0]["sample_complete"])
        self.assertEqual(partial["groups"][0]["planned_runs"], 2)
        results[0]["accounting"]["estimated_cost_usd"] = "999"
        with self.assertRaisesRegex(ValueError, "frozen rates"):
            build_variance_report(manifest, results)


if __name__ == "__main__":
    unittest.main()
