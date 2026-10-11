from contextlib import redirect_stdout
import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.domain import load_models, read_json, save_json
from agent_lab.experiments import discover_task_paths, load_experiment, run_batch
from agent_lab.providers import MockProvider
from agent_lab.reporting import collect_results


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config_dir = self.root / "configs"
        self.config_dir.mkdir()
        self.config = self.config_dir / "experiment.json"
        self.catalog = load_models(ROOT / "configs" / "mock_models.json")
        self.add_task("zeta")
        self.add_task("alpha")
        save_json(self.config, {"schema_version": 1, "strategy": "single_agent", "models": ["mock-pass"],
                               "task_globs": ["../tickets/*/task.json"], "repeats": 1,
                               "batch_budget_usd": "1", "seed": 42})

    def add_task(self, name, task_id=None):
        target = self.root / "tickets" / name
        shutil.copytree(ROOT / "tickets" / "clamp-boundaries", target)
        raw = read_json(target / "task.json")
        raw["id"] = task_id or "task-" + Path(name).name
        save_json(target / "task.json", raw)
        return target / "task.json"

    def test_scans_relative_to_config_in_stable_order(self):
        tasks = load_experiment(self.config, self.catalog)[0]
        self.assertEqual([task.id for task in tasks], ["task-alpha", "task-zeta"])

    def test_new_task_is_discovered_without_configuration_changes(self):
        before = self.config.read_bytes()
        self.add_task("beta")
        tasks = load_experiment(self.config, self.catalog)[0]
        self.assertEqual([task.id for task in tasks], ["task-alpha", "task-beta", "task-zeta"])
        self.assertEqual(self.config.read_bytes(), before)

    def test_explicit_and_overlapping_patterns_deduplicate_paths(self):
        paths = discover_task_paths(self.config_dir, {
            "tasks": ["../tickets/zeta/task.json"],
            "task_globs": ["../tickets/*/task.json", "../tickets/alpha/task.json"]})
        self.assertEqual([path.parent.name for path in paths], ["zeta", "alpha"])

    def test_recursive_scan_finds_nested_tasks(self):
        self.add_task("category/nested")
        paths = discover_task_paths(self.config_dir, {"task_globs": ["../tickets/**/task.json"]})
        self.assertEqual(len(paths), 3)
        self.assertTrue(any(path.parent.name == "nested" for path in paths))

    def test_no_matches_errors_instead_of_silently_running_empty_batch(self):
        with self.assertRaisesRegex(ValueError, "matched no files"):
            discover_task_paths(self.config_dir, {"task_globs": ["../missing/*/task.json"]})

    def test_list_fields_must_be_arrays(self):
        for raw in ({"tasks": "task.json"}, {"task_globs": "*.json"}, {"tasks": [1]}, {"task_globs": [""]}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                discover_task_paths(self.config_dir, raw)

    def test_duplicate_ids_are_rejected(self):
        self.add_task("duplicate", "task-alpha")
        with self.assertRaisesRegex(ValueError, "Duplicate task"):
            load_experiment(self.config, self.catalog)

    def test_invalid_discovered_task_errors_before_model_calls(self):
        invalid = self.root / "tickets" / "broken" / "task.json"
        save_json(invalid, {"schema_version": 999})
        with patch.object(MockProvider, "send", side_effect=AssertionError("must not call")):
            with self.assertRaisesRegex(ValueError, "Unsupported task schema"):
                run_batch(self.config, self.catalog, self.root / "batch")
        self.assertFalse((self.root / "batch").exists())

    def test_discovered_list_drives_runs_and_new_tasks_do_not_change_old_batch(self):
        with redirect_stdout(io.StringIO()):
            manifest = run_batch(self.config, self.catalog, self.root / "batch")
        self.assertEqual(len(collect_results(self.root / "batch")), 2)
        self.assertEqual(set(manifest["configuration"]["task_manifests"]), {"task-alpha", "task-zeta"})
        self.add_task("beta")
        with self.assertRaisesRegex(ValueError, "configuration changed"):
            run_batch(self.config, self.catalog, self.root / "batch", resume=True)
        self.assertEqual(len(collect_results(self.root / "batch")), 2)


if __name__ == "__main__":
    unittest.main()
