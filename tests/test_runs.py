from dataclasses import replace
import io
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.domain import Limits, Model, Pricing, Task, load_models, read_json, save_json
from agent_lab.experiments import run_batch
from agent_lab.providers import AnthropicProvider, DeepSeekProvider, OpenAIProvider, MockProvider, ProviderError
from agent_lab.runner import SYSTEM
from agent_lab.tools import TOOLS
from agent_lab.reporting import collect_results, write_report
from agent_lab.runner import run_task
from agent_lab.workspace import Workspace, file_hash
from agent_lab.token_counting import TokenCountError


class RunTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.task = Task.load(ROOT / "tickets" / "clamp-boundaries" / "task.json")
        self.models = load_models(ROOT / "configs" / "mock_models.json")

    def run_model(self, behavior="pass", **limits):
        model = replace(self.models["mock-pass"], mock_behavior=behavior)
        return run_task(self.task, model, Limits(**limits), self.root / "runs")

    def test_success_is_verified_and_original_source_unchanged(self):
        source = self.task.source_dir / "bounds.py"
        original = file_hash(source)
        result = self.run_model()
        self.assertTrue(result["accepted"])
        self.assertTrue(result["final_evidence"]["passed"])
        self.assertEqual(file_hash(source), original)
        artifact = Path(result["artifact_dir"])
        self.assertIn("+    if lower > upper:", (artifact / "changes.patch").read_text())
        self.assertEqual(len(list((artifact / "calls").glob("*-response.json"))), 3)
        self.assertEqual(result["execution_kind"], "simulated")

    def test_all_three_fixtures_work(self):
        for task_path in sorted((ROOT / "tickets").glob("*/task.json")):
            with self.subTest(task=task_path.parent.name):
                result = run_task(Task.load(task_path), self.models["mock-pass"], Limits(), self.root / "runs")
                self.assertTrue(result["accepted"])

    def test_repeated_false_completion_stops(self):
        result = self.run_model("stuck")
        self.assertEqual(result["stop_reason"], "no_progress")
        self.assertEqual(result["accounting"]["calls"], 2)
        self.assertGreater(float(result["accounting"]["estimated_cost_usd"]), 0)

    def test_zero_repairs_stops_on_first_failed_submission(self):
        result = self.run_model("stuck", max_repairs=0)
        self.assertEqual(result["stop_reason"], "repair_limit")
        self.assertEqual(result["accounting"]["calls"], 1)

    def test_call_limit_stops_before_another_request(self):
        result = self.run_model(max_calls=1)
        self.assertEqual(result["stop_reason"], "call_limit")
        self.assertEqual(result["accounting"]["calls"], 1)
        self.assertTrue(result["accounting"]["usage_complete"])

    def test_budget_limit_sends_no_request(self):
        with patch.object(MockProvider, "send", side_effect=AssertionError("must not call")):
            result = self.run_model(max_cost_usd="0.000001")
        self.assertEqual(result["stop_reason"], "budget_limit")
        self.assertEqual(result["accounting"]["calls"], 0)

    def test_request_size_limit_sends_no_request(self):
        result = self.run_model(max_request_bytes=1)
        self.assertEqual(result["stop_reason"], "request_size_limit")
        self.assertEqual(result["accounting"]["calls"], 0)

    def test_truncated_response_records_usage_without_tools_checks_repairs_or_retry(self):
        examples = [
            (OpenAIProvider, "openai", {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"},
                "usage": {"input_tokens": 100, "output_tokens": 2048}, "output": []}),
            (DeepSeekProvider, "deepseek", {"choices": [{"finish_reason": "length", "message": {"content": ""}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 2048}}),
            (AnthropicProvider, "anthropic", {"stop_reason": "max_tokens", "content": [],
                "usage": {"input_tokens": 100, "output_tokens": 2048}})]
        for cls, kind, raw in examples:
            with self.subTest(provider=kind):
                model = Model("test-" + kind, kind, "test-model", Pricing("1", "2"),
                              max_output_tokens=16384, reasoning_effort="low")
                client = cls(model, SYSTEM, "task", TOOLS)
                with patch("agent_lab.runner.make_provider", return_value=client), \
                     patch.object(client, "send", return_value=raw) as send, \
                     patch("agent_lab.runner.Checks.run", side_effect=AssertionError("must not verify")):
                    result = run_task(self.task, model, Limits(), self.root / "truncation")
                self.assertEqual(result["stop_reason"], "generation_length_limit" if kind == "deepseek" else "output_token_limit")
                self.assertEqual(result["repairs"], 0)
                self.assertEqual(result["accounting"]["tool_steps"], 0)
                self.assertEqual(result["accounting"]["total_tokens"], 2148)
                self.assertTrue(result["accounting"]["usage_complete"])
                self.assertGreater(float(result["accounting"]["estimated_cost_usd"]), 0)
                self.assertEqual(send.call_count, 1)
                self.assertIsNone(result["final_evidence"])

    def test_deepseek_length_at_configured_output_cap_is_output_token_limit(self):
        model = Model("test-deepseek", "deepseek", "test-model", Pricing("1", "2"),
                      max_output_tokens=16384, reasoning_effort="low")
        client = DeepSeekProvider(model, SYSTEM, "task", TOOLS)
        raw = {"choices": [{"finish_reason": "length", "message": {"content": ""}}],
               "usage": {"prompt_tokens": 100, "completion_tokens": 16384}}
        with patch("agent_lab.runner.make_provider", return_value=client), patch.object(client, "send", return_value=raw):
            result = run_task(self.task, model, Limits(), self.root / "deepseek-output-cap")
        self.assertEqual(result["stop_reason"], "output_token_limit")
        self.assertEqual(result["accounting"]["calls"], 1)
        self.assertEqual(result["repairs"], 0)

    def test_openai_large_encrypted_continuation_reaches_verified_delivery_offline(self):
        model = Model("test-openai", "openai", "test-model", Pricing("0.1", "0.5"), max_output_tokens=16384)
        client = OpenAIProvider(model, SYSTEM, "task", TOOLS)
        replay = read_json(self.task.manifest_path.parent / "replay.json")
        requests = []

        def fake_send(payload, timeout):
            import copy
            requests.append(copy.deepcopy(payload))
            index = len(requests) - 1
            output = [{"type": "function_call", "call_id": f"c-{index}-{i}",
                       "name": action["name"], "arguments": action["arguments"]}
                      for i, action in enumerate(replay[index])]
            if index == 0:
                output.insert(0, {"type": "reasoning", "encrypted_content": "x" * 200000, "summary": []})
            return {"status": "completed", "usage": {"input_tokens": 1000, "output_tokens": 1000}, "output": output}

        with patch("agent_lab.runner.make_provider", return_value=client), patch.object(client, "send", fake_send):
            result = run_task(self.task, model, Limits(), self.root / "continuation")
        self.assertTrue(result["accepted"], result["stop_reason"])
        self.assertEqual(len(requests), 3)
        self.assertEqual(requests[1]["input"][1]["encrypted_content"], "x" * 200000)
        self.assertTrue(result["final_evidence"]["passed"])
        self.assertTrue(result["accounting"]["usage_complete"])

    def test_missing_usage_stops_without_executing_response_tools(self):
        result = self.run_model("missing_usage")
        self.assertEqual(result["stop_reason"], "usage_unknown")
        self.assertFalse(result["accounting"]["usage_complete"])
        self.assertEqual(result["accounting"]["tool_steps"], 0)

    def test_transport_failure_preserves_unknown_spend(self):
        for request_timeout, task_seconds in [(300, 900), (37, 900), (300, 120)]:
            with self.subTest(request_timeout=request_timeout, task_seconds=task_seconds):
                with patch.object(MockProvider, "send", side_effect=ProviderError("timeout")) as send:
                    result = self.run_model(request_timeout_seconds=request_timeout, max_seconds=task_seconds)
                timeout = send.call_args.args[1]
                if request_timeout < task_seconds:
                    self.assertEqual(timeout, request_timeout)
                else:
                    self.assertGreater(timeout, 0)
                    self.assertLessEqual(timeout, task_seconds)
                self.assertEqual(result["stop_reason"], "provider_error")
                self.assertFalse(result["accounting"]["usage_complete"])
                self.assertGreater(float(result["accounting"]["unknown_cost_reserve_usd"]), 0)
                saved = read_json(Path(result["artifact_dir"]) / "config.json")
                self.assertEqual(saved["limits"]["request_timeout_seconds"], request_timeout)

    def test_invalid_paths_cannot_read_private_checks_and_tool_cap_stops(self):
        result = self.run_model("invalid", max_tool_steps=2)
        self.assertEqual(result["stop_reason"], "tool_limit")
        events = (Path(result["artifact_dir"]) / "events.jsonl").read_text()
        self.assertIn("Expected a relative path", events)

    def test_public_passing_patch_can_fail_final_acceptance(self):
        original_send = MockProvider.send
        def public_only(client, payload, timeout):
            response = original_send(client, payload, timeout)
            for call in response["reply"]["calls"]:
                if call["name"] == "write_file":
                    call["arguments"]["content"] = "def clamp(value, lower, upper):\n    return max(lower, min(value, upper))\n"
            return response
        with patch.object(MockProvider, "send", public_only):
            result = self.run_model()
        self.assertEqual(result["stop_reason"], "acceptance_failed")
        self.assertFalse(result["accepted"])
        delivery = read_json(Path(result["artifact_dir"]) / "delivery.json")
        self.assertTrue(delivery["public"]["passed"])
        self.assertFalse(delivery["final"]["passed"])
        # Hidden expected answers are not returned into a fourth model call.
        self.assertEqual(result["accounting"]["calls"], 3)

    def test_child_checks_do_not_inherit_api_credentials(self):
        copy = self.root / "ticket"
        shutil.copytree(self.task.manifest_path.parent, copy)
        final = copy / "final_check.py"
        final.write_text(final.read_text() + "\nassert 'OPENAI_API_KEY' not in os.environ\nassert 'ANTHROPIC_API_KEY' not in os.environ\n")
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-secret", "ANTHROPIC_API_KEY": "other-secret"}):
            result = run_task(Task.load(copy / "task.json"), self.models["mock-pass"], Limits(), self.root / "runs")
        self.assertTrue(result["accepted"])

    def test_workspace_disallows_escape_absolute_paths_and_noneditable_files(self):
        run_dir = self.root / "workspace-test"
        run_dir.mkdir()
        workspace = Workspace(self.task, run_dir)
        for name in ("../final_check.py", "C:/private.txt", "/private.txt", ".env", "unknown.py"):
            with self.subTest(path=name), self.assertRaises(ValueError):
                workspace.read_file(name)

    def test_interrupted_record_is_reconstructed_without_zeroing_cost(self):
        result = self.run_model()
        directory = Path(result["artifact_dir"])
        (directory / "result.json").unlink()
        recovered = collect_results(directory)[0]
        self.assertEqual(recovered["status"], "interrupted")
        self.assertEqual(recovered["accounting"]["estimated_cost_usd"], result["accounting"]["estimated_cost_usd"])
        report = write_report(directory)
        self.assertEqual(report["groups"][0]["successes"], 0)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.models = load_models(ROOT / "configs" / "mock_models.json")
        self.config = self.root / "experiment.json"
        save_json(self.config, {"schema_version": 1, "strategy": "single_agent", "models": ["mock-pass"],
                               "tasks": [str(ROOT / "tickets" / "clamp-boundaries" / "task.json")],
                               "repeats": 2, "batch_budget_usd": "1", "seed": 42})

    def run_batch(self, **kwargs):
        with redirect_stdout(io.StringIO()):
            return run_batch(self.config, self.models, self.root / "batch", **kwargs)

    def test_completed_batch_resume_does_not_rerun(self):
        self.run_batch()
        before = [item["run_id"] for item in collect_results(self.root / "batch")]
        with patch.object(MockProvider, "send", side_effect=AssertionError("must not rerun")):
            self.run_batch(resume=True)
        self.assertEqual(before, [item["run_id"] for item in collect_results(self.root / "batch")])

    def test_count_service_failure_stops_batch_without_generation_or_retry(self):
        model = replace(self.models["mock-pass"], provider="openai", model="test-model", token_counting="model")
        self.models["mock-pass"] = model
        client = OpenAIProvider(model, SYSTEM, "task", TOOLS)
        with patch("agent_lab.experiments.make_provider", return_value=client), \
             patch("agent_lab.runner.make_provider", return_value=client), \
             patch.object(client, "count_input_tokens", side_effect=TokenCountError("offline error")) as count, \
             patch.object(client, "send", side_effect=AssertionError("must not generate")):
            manifest = self.run_batch()
        self.assertEqual(manifest["status"], "input_count_error")
        self.assertEqual(count.call_count, 1)
        results = collect_results(self.root / "batch")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["accounting"]["calls"], 0)

    def test_resume_rejects_changed_configuration(self):
        self.run_batch()
        raw = read_json(self.config)
        raw["seed"] = 43
        save_json(self.config, raw)
        with self.assertRaisesRegex(ValueError, "configuration changed"):
            self.run_batch(resume=True)

    def test_batch_unknown_usage_halts_future_runs(self):
        self.models["mock-pass"] = replace(self.models["mock-pass"], mock_behavior="missing_usage")
        manifest = self.run_batch()
        self.assertEqual(manifest["status"], "usage_unknown")
        self.assertEqual(len(collect_results(self.root / "batch")), 1)

    def test_batch_resume_rejects_incomplete_run(self):
        self.run_batch()
        first = collect_results(self.root / "batch")[0]
        (Path(first["artifact_dir"]) / "result.json").unlink()
        with self.assertRaisesRegex(ValueError, "completed result is missing"):
            self.run_batch(resume=True)

    def test_resume_reconciles_result_saved_before_batch_checkpoint(self):
        self.run_batch()
        manifest_path = self.root / "batch" / "batch.json"
        manifest = read_json(manifest_path)
        cell_id, run_id = next(iter(manifest["completed"].items()))
        manifest["completed"].pop(cell_id)
        cell = next(item for item in manifest["configuration"]["plan"] if item["cell"] == cell_id)
        manifest["inflight"] = {cell_id: cell}
        save_json(manifest_path, manifest)
        with patch.object(MockProvider, "send", side_effect=AssertionError("must not replay")):
            restored = self.run_batch(resume=True)
        self.assertEqual(restored["completed"][cell_id], run_id)

    def test_unknown_usage_in_last_cell_is_not_marked_batch_completed(self):
        raw = read_json(self.config)
        raw["repeats"] = 1
        save_json(self.config, raw)
        self.models["mock-pass"] = replace(self.models["mock-pass"], mock_behavior="missing_usage")
        self.assertEqual(self.run_batch()["status"], "usage_unknown")

    def test_new_incomplete_run_is_not_replayed_on_resume(self):
        self.run_batch()
        manifest_path = self.root / "batch" / "batch.json"
        manifest = read_json(manifest_path)
        cell_id, run_id = next(iter(manifest["completed"].items()))
        manifest["completed"].pop(cell_id)
        manifest["inflight"] = {cell_id: next(item for item in manifest["configuration"]["plan"] if item["cell"] == cell_id)}
        save_json(manifest_path, manifest)
        (self.root / "batch" / "runs" / run_id / "result.json").unlink()
        with self.assertRaisesRegex(ValueError, "Incomplete run"):
            self.run_batch(resume=True)

    def test_batch_cumulative_budget_cannot_be_reset_per_task(self):
        # The second run has insufficient remaining reservation even though
        # it would fit a fresh per-task budget.
        raw = read_json(self.config)
        raw["batch_budget_usd"] = "0.014"
        raw["limits"] = {"max_repairs": 0}
        save_json(self.config, raw)
        self.models["mock-pass"] = replace(self.models["mock-pass"], mock_behavior="stuck")
        original_send = MockProvider.send
        def measured_cost(client, payload, timeout):
            response = original_send(client, payload, timeout)
            response["usage"] = {"input_tokens": 8000, "output_tokens": 500}
            return response
        with patch.object(MockProvider, "send", measured_cost):
            self.run_batch()
        results = collect_results(self.root / "batch")
        self.assertLessEqual(sum(float(item["accounting"]["estimated_cost_usd"]) for item in results), 0.014)
        self.assertEqual(sorted(item["stop_reason"] for item in results), ["budget_limit", "repair_limit"])
        self.assertEqual(sum(item["accounting"]["calls"] for item in results), 1)


if __name__ == "__main__":
    unittest.main()
