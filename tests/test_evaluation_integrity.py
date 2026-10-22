from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.domain import Task
from agent_lab.evaluation import Checks
from agent_lab.workspace import Workspace


class EvaluationIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(ROOT / "tickets" / "clamp-boundaries", self.root / "ticket")

    def prepare(self, source, check=None, timeout=10):
        if check is not None:
            for kind in ("public", "final"):
                (self.root / "ticket" / (kind + "_check.py")).write_text(check, encoding="utf-8")
        task = Task.load(self.root / "ticket" / "task.json")
        directory = self.root / "run"
        directory.mkdir()
        workspace = Workspace(task, directory)
        workspace.write_file("bounds.py", source)
        return Checks(task, directory, workspace, timeout)

    def test_import_time_zero_exit_cannot_pass_public_or_final(self):
        checks = self.prepare("import os\nos._exit(0)\n")
        for kind in ("public", "final"):
            result = checks.run(kind, 10)
            self.assertFalse(result["passed"])
            self.assertTrue(result["completion_verified"])
            self.assertIn("without a complete result", result["output"])

    def test_function_time_zero_exit_and_fake_success_output_are_not_acceptance(self):
        checks = self.prepare("def clamp(*args):\n print('Final acceptance passed')\n import os\n os._exit(0)\n")
        self.assertFalse(checks.run("final", 10)["passed"])

    def test_submission_system_exit_is_a_task_failure(self):
        checks = self.prepare("raise SystemExit(0)\n")
        result = checks.run("public", 10)
        self.assertTrue(result["ok"])
        self.assertFalse(result["passed"])

    def test_trusted_check_early_exit_has_no_valid_completion_receipt(self):
        checks = self.prepare("", check="import os\nos._exit(0)\n")
        result = checks.run("public", 10)
        self.assertFalse(result["passed"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "incomplete")

    def test_wrong_answer_cannot_pass_by_printing_success(self):
        checks = self.prepare("def clamp(*args):\n print('Public checks passed')\n return 0\n")
        self.assertFalse(checks.run("public", 10)["passed"])

    def test_correct_code_passes_with_completion_evidence(self):
        checks = self.prepare("def clamp(value, lower, upper):\n if lower > upper: raise ValueError('bounds')\n return max(lower,min(value,upper))\n")
        result = checks.run("final", 10)
        self.assertTrue(result["passed"])
        self.assertTrue(result["completion_verified"])

    def test_mutated_arguments_are_visible_to_operator_checks(self):
        check = ("from check_client import load_submission\nfrom pathlib import Path\nimport os\n"
                 "m=load_submission(Path(os.environ['LAB_WORKSPACE'])/'bounds.py')\n"
                 "values=[1,2]\nm.clamp(values)\nassert values == [1,2]\n")
        checks = self.prepare("def clamp(values):\n values.clear()\n return 0\n", check)
        self.assertFalse(checks.run("final", 10)["passed"])

    def test_nonterminating_submission_is_not_accepted(self):
        checks = self.prepare("while True: pass\n", timeout=1)
        self.assertFalse(checks.run("final", 2)["passed"])

    def test_evaluator_runtime_integrity_is_checked(self):
        checks = self.prepare("pass\n")
        (checks.runtime / "submission_worker.py").write_text("pass\n")
        with self.assertRaisesRegex(ValueError, "runtime changed"):
            checks.run("final", 10)


if __name__ == "__main__":
    unittest.main()
