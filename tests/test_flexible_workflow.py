from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from agent_lab.accounting import StopRun
from agent_lab.domain import Task, Model, Pricing, Limits, read_json
from agent_lab.opencode_workflow import run_workflow, opencode_config
from agent_lab.opencode_permissions import permission_probes, ROLE_AGENT_IDS
from agent_lab.workflows import Workflow, effective_workflow, primary_schedule


@contextmanager
def server(*args):
    yield 'http://fixture', 'fixture'


class FlexibleSession:
    def __init__(self, url, password, workspace, directory, models, strategy, gateway):
        self.g = gateway

    def select_primary(self, role, model, turn_dir):
        self.role = role

    def run_turn(self, text, turn_dir):
        task = Task.load(ROOT / 'tickets/clamp-boundaries/task.json')
        action = next(a for batch in read_json(task.manifest_path.parent / 'replay.json') for a in batch if a['name'] == 'write_file')
        for call in (action, {'name': 'write_test', 'arguments': {'name': 'test_role.py',
                            'content': 'import unittest\n# Written by ' + self.role}}):
            result = self.g.mcp(self.role, {'id': 1, 'method': 'tools/call', 'params': call})
            assert not result['isError'], result
        denied = self.g.mcp(self.role, {'id': 2, 'method': 'tools/call', 'params': {
            'name': 'write_file', 'arguments': {'path': '../checks/final.py', 'content': 'bad'}}})
        assert denied['isError']
        other = 'worker' if self.role != 'worker' else 'planner'
        with unittest.TestCase().assertRaises(StopRun):
            self.g.mcp(other, {'id': 3, 'method': 'tools/call', 'params': action})
        return {'data': [{'type': 'assistant', 'time': {'created': 1, 'completed': 2},
                          'content': [{'type': 'text', 'text': 'Verified role edits and boundaries.'}]}]}

    def close(self):
        pass


class FlexibleTests(unittest.TestCase):
    def test_all_roles_can_edit_but_cannot_escape_or_impersonate(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts/test-temp') as tmp:
            model = Model('plan', 'deepseek', 'fixture', Pricing('1', '2'), reasoning_effort='low')
            models = [model, replace(model, id='execute'), replace(model, id='review')]
            with patch('agent_lab.providers.require_credential', return_value='fixture'), \
                 patch('agent_lab.opencode_workflow.isolated_server', server):
                result = run_workflow(Task.load(ROOT / 'tickets/clamp-boundaries/task.json'), models, Limits(),
                    Path(tmp), Workflow.load(ROOT / 'configs/workflows/plan-execute-review-self-tests.json'),
                    'planner_executor_reviewer_flexible', session_factory=FlexibleSession)
            self.assertTrue(result['accepted'], result)
            self.assertTrue(all(t['allow_write'] for t in result['turns']))
            root = Path(result['artifact_dir'])
            self.assertTrue((root / 'review.json').exists())
            for turn in ('00-plan', '02-review'):
                self.assertTrue((root / 'turns' / turn / 'self-tests/test_role.py').exists())

    def test_strict_and_flexible_rules_remain_distinct(self):
        workflow = Workflow.load(ROOT / 'configs/workflows/plan-execute-review-self-tests.json')
        strict = primary_schedule('planner_executor_reviewer', workflow)
        flexible = effective_workflow('planner_executor_reviewer_flexible', workflow)
        self.assertEqual(strict, primary_schedule('planner_executor_reviewer_flexible', flexible))
        self.assertEqual([t.allow_write for t in workflow.turns], [False, True, False, True])
        for role in ('planner', 'reviewer'):
            probes = permission_probes(role, 'planner_executor_reviewer_flexible')
            for tool in ('write_file', 'write_test', 'run_self_tests'):
                matching = [p['expected'] for p in probes if p['action'] == f'lab_{role}_{tool}']
                self.assertEqual(matching, ['allow'])
            self.assertTrue(any(p['action'] == 'shell' and p['expected'] == 'deny' for p in probes))


if __name__ == '__main__':
    unittest.main()
