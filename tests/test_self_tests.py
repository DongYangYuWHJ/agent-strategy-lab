"""Advisory self-tests run current code without granting source/acceptance writes."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from agent_lab.domain import Task, ToolCall
from agent_lab.workspace import Workspace
from agent_lab.self_tests import SelfTests
from agent_lab.workflow_gateway import Gateway, role_tool_definitions


class SelfTestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'artifacts/test-temp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = Workspace(Task.load(ROOT / 'tickets/clamp-boundaries/task.json'), self.root)
        self.tests = SelfTests(self.root, self.workspace)

    def write(self, text):
        return self.tests.execute(ToolCall('1', 'write_test', {'name': 'test_bounds.py', 'content': text}), 30)

    def test_current_source_and_advisory_failure_then_success(self):
        self.write('import unittest\nfrom bounds import clamp\nclass Bounds(unittest.TestCase):\n def test_clamp(self): self.assertEqual(clamp(5, 0, 3), 3)\n')
        self.workspace.write_file('bounds.py', 'def clamp(value, low, high): return value\n')
        before = self.tests.run(30)
        self.assertTrue(before['ok'])
        self.assertFalse(before['passed'])
        self.workspace.write_file('bounds.py', 'def clamp(value, low, high): return max(low, min(value, high))\n')
        after = self.tests.run(30)
        self.assertTrue(after['passed'], after)
        self.assertTrue(after['advisory_only'])
        self.assertNotEqual(before['source_hashes'], after['source_hashes'])
        self.assertEqual(before['test_hashes'], after['test_hashes'])

    def test_empty_and_early_exit_do_not_pass(self):
        self.assertFalse(self.tests.run(30)['passed'])
        self.write('raise SystemExit(0)\n')
        self.assertFalse(self.tests.run(30)['passed'])

    def test_external_reads_process_network_and_source_writes_blocked(self):
        secret = self.root / 'operator-only.txt'
        secret.write_text('never visible', encoding='utf-8')
        self.write('import unittest, pathlib, socket, subprocess, os\n'
            'class Guard(unittest.TestCase):\n'
            f' def test_read(self):\n  with self.assertRaises(PermissionError): pathlib.Path({str(secret)!r}).read_text()\n'
            ' def test_network(self):\n  with self.assertRaises(PermissionError): socket.socket()\n'
            ' def test_process(self):\n  with self.assertRaises(PermissionError): subprocess.run(["not-a-command"])\n'
            ' def test_write(self):\n  with self.assertRaises(PermissionError): pathlib.Path("bounds.py").write_text("bad")\n'
            ' def test_env(self): self.assertNotIn("OPENAI_API_KEY", os.environ)\n'
            ' def test_scratch(self): pathlib.Path("scratch/file.txt").write_text("allowed")\n')
        result = self.tests.run(30)
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['tests_run'], 6)

    def test_paths_and_role_gates(self):
        for name in ('../final.py', 'test_a/../test_b.py', 'final.py'):
            with self.assertRaises(ValueError):
                self.tests.path(name)
        self.assertNotIn('write_test', {t['name'] for t in role_tool_definitions('reviewer')})
        self.assertNotIn('run_self_tests', {t['name'] for t in role_tool_definitions('planner')})
        events = []
        gate = Gateway.__new__(Gateway)
        gate.guard = lambda: None
        import threading
        gate.lock = threading.RLock()
        gate.active_role, gate.turn, gate.allow_write = 'reviewer', 'review', True
        gate.recorder = SimpleNamespace(event=lambda *a, **k: events.append(k))
        gate.self_tests, gate.workspace, gate.remaining = self.tests, self.workspace, lambda: 30
        response = gate.mcp('reviewer', {'method': 'tools/call', 'params': {'name': 'write_test',
            'arguments': {'name': 'test_forbidden.py', 'content': 'bad'}}})
        self.assertTrue(response['isError'])
        self.assertFalse(self.tests.fingerprint())

    def test_timeout_does_not_pass(self):
        self.write('while True: pass\n')
        result = self.tests.run(0.2)
        self.assertEqual(result['status'], 'timed_out')
        self.assertFalse(result['passed'])


if __name__ == '__main__':
    unittest.main()
