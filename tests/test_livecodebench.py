import base64
import json
from pathlib import Path
import pickle
import sys
import tempfile
import unittest
import zlib
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.domain import Task
from agent_lab.evaluation import Checks
from agent_lab.livecodebench import decode_cases
from agent_lab.workspace import Workspace
from agent_lab.check_client import stdio_equal


class LiveCodeBenchTests(unittest.TestCase):
    def test_upstream_json_and_compressed_pickle_string_formats(self):
        cases = [{"input": "1", "output": "2", "testtype": "stdin"}]
        text = json.dumps(cases)
        compressed = base64.b64encode(zlib.compress(pickle.dumps(text))).decode()
        self.assertEqual(decode_cases(text), cases)
        self.assertEqual(decode_cases(compressed), cases)

    def test_pickle_globals_are_rejected_without_execution(self):
        malicious = base64.b64encode(zlib.compress(pickle.dumps(eval))).decode()
        with self.assertRaisesRegex(ValueError, "globals are forbidden"):
            decode_cases(malicious)

    def test_empty_or_unsupported_cases_are_rejected(self):
        for cases in ([], [{"input": "1", "output": "2", "testtype": "functional"}]):
            with self.assertRaises(ValueError):
                decode_cases(json.dumps(cases))

    def test_comparator_preserves_line_structure_and_large_integer_precision(self):
        self.assertTrue(stdio_equal(" 1  2.0\n", "1 2"))
        self.assertFalse(stdio_equal("1\n2", "1 2"))
        self.assertFalse(stdio_equal("50000000000000000", "50000000000000001"))
        self.assertFalse(stdio_equal("nan", "1"))
        self.assertFalse(stdio_equal("", "1"))

    def test_frozen_suite_has_balanced_levels_and_loadable_separate_checks(self):
        root = ROOT / "benchmarks" / "livecodebench"
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(Counter(row["difficulty"] for row in manifest["tasks"]), {"easy": 2, "medium": 2, "hard": 2})
        for row in manifest["tasks"]:
            task = Task.load(root / row["manifest"])
            self.assertEqual(row["private_cases"], 40)
            self.assertFalse(task.final_check.is_relative_to(task.source_dir))
            self.assertNotIn("private_test_cases", task.description)

    def test_real_easy_task_accepts_correct_code_and_rejects_sample_only_code(self):
        task = Task.load(ROOT / "benchmarks/livecodebench/tasks/lcb-abc387-a/task.json")
        for source, expected in [("a,b=map(int,input().split())\nprint((a+b)**2)\n", True),
                                 ("import sys\na,b=map(int,input().split())\nprint((a+b)**2)\nsys.exit(0)\n", True),
                                 ("import sys\na,b=map(int,sys.stdin.buffer.read().split())\nprint('debug',file=sys.stderr)\nsys.stdout.buffer.write(str((a+b)**2).encode())\n", True),
                                 ("print(2025)\n", False), ("import os\nos._exit(0)\n", False)]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                workspace = Workspace(task, directory)
                workspace.write_file("solution.py", source)
                result = Checks(task, directory, workspace, 30).run("final", 30)
                self.assertEqual(result["passed"], expected)


if __name__ == "__main__":
    unittest.main()
