"""Role isolation and failure handling for read-only review followed by revision."""
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from agent_lab.accounting import StopRun
from agent_lab.domain import Limits, Model, Pricing, Task, read_json
from agent_lab.opencode_permissions import ROLE_AGENT_IDS, audit_registered_agents, role_ids
from agent_lab.opencode_workflow import opencode_config, review_reply, run_workflow
from agent_lab.workflow_experiments import load_workflow_experiment
from agent_lab.workflows import Workflow


@contextmanager
def fixture_server(*args):
    yield 'http://fixture', 'fixture'


class ReviewSession:
    selections = []
    tamper = False
    empty_review = False

    def __init__(self, url, password, workspace, directory, models, strategy, gateway):
        self.gateway, self.workspace, self.directory = gateway, workspace, directory
        self.review_seen = False

    def select_primary(self, role, model, turn_dir):
        self.selections.append((role, model.id))
        self.role, self.model = role, model

    def run_turn(self, text, turn_dir):
        g = self.gateway
        g.generation(self.model.id, 'chat/completions', {'model': self.model.model,
                     'messages': [{'role': 'user', 'content': text}]})
        if g.turn == 'review':
            before = self.workspace.resolve('bounds.py').read_bytes()
            # A malicious direct MCP request must fail even if allow_write is set incorrectly.
            g.allow_write = True
            denied = g.mcp('reviewer', {'id': 1, 'method': 'tools/call', 'params': {
                'name': 'write_file', 'arguments': {'path': 'bounds.py', 'content': 'forbidden'}}})
            assert denied['isError'] and self.workspace.resolve('bounds.py').read_bytes() == before
            try:
                g.mcp('worker', {'id': 2, 'method': 'tools/call', 'params': {
                    'name': 'write_file', 'arguments': {'path': 'bounds.py', 'content': 'forbidden'}}})
            except StopRun as exc:
                assert exc.reason == 'inactive_agent'
            else:
                raise AssertionError('Reviewer used an Executor endpoint')
            g.allow_write = False
            if self.tamper:
                self.workspace.resolve('bounds.py').write_text('bypass', encoding='utf-8')
            self.review_seen = True
            messages = {'data': [{'type': 'assistant', 'time': {'created': 3, 'completed': 4},
                'content': [{'type': 'text', 'text': '' if self.empty_review else 'REVIEW: fix the boundary handling.'},
                            {'type': 'reasoning', 'text': 'NOT_PUBLIC'}]}]}
            (turn_dir / 'messages.json').write_text(json.dumps(messages), encoding='utf-8')
            return messages
        if g.turn == 'revise':
            assert self.review_seen and 'REVIEW: fix' in read_json(self.directory / 'review.json')['text']
            task = Task.load(ROOT / 'tickets/clamp-boundaries/task.json')
            action = next(a for batch in read_json(task.manifest_path.parent / 'replay.json')
                          for a in batch if a['name'] == 'write_file')
            assert not g.mcp('worker', {'id': 3, 'method': 'tools/call', 'params': action})['isError']

    def close(self):
        pass


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        m = Model('plan', 'deepseek', 'fixture', Pricing('1', '2'), max_output_tokens=256, reasoning_effort='low')
        self.models = [m, replace(m, id='execute'), replace(m, id='review')]
        self.workflow = Workflow.load(ROOT / 'configs/workflows/plan-execute-review.json')
        ReviewSession.selections = []
        ReviewSession.tamper = ReviewSession.empty_review = False

    def run_fixture(self, limits=None, workflow=None):
        with patch('agent_lab.providers.require_credential', return_value='fixture'), \
             patch('agent_lab.opencode_workflow.isolated_server', fixture_server), \
             patch('agent_lab.workflow_gateway.forward_stream', return_value=(b'fixture', {
                 'id': 'fixture', 'model': 'fixture', 'usage': {'prompt_tokens': 100, 'completion_tokens': 30},
                 'choices': [{'finish_reason': 'stop'}]})):
            return run_workflow(Task.load(ROOT / 'tickets/clamp-boundaries/task.json'), self.models,
                                limits or Limits(), self.root, workflow or self.workflow,
                                'planner_executor_reviewer', session_factory=ReviewSession)

    def test_review_then_executor_revision_and_shared_accounting(self):
        result = self.run_fixture()
        self.assertTrue(result['accepted'])
        self.assertEqual(ReviewSession.selections, [('planner', 'plan'), ('worker', 'execute'),
                                                   ('reviewer', 'review'), ('worker', 'execute')])
        self.assertEqual([t['accounting_cumulative']['calls'] for t in result['turns']], [1, 2, 3, 4])
        self.assertEqual(result['accounting']['estimated_cost_usd'], '0.00064')
        directory = Path(result['artifact_dir'])
        self.assertEqual(read_json(directory / 'review.json')['text'], 'REVIEW: fix the boundary handling.')
        self.assertEqual((directory / 'turns/01-implement/workspace/bounds.py').read_bytes(),
                         (directory / 'turns/02-review/workspace/bounds.py').read_bytes())
        self.assertNotEqual((directory / 'turns/02-review/workspace/bounds.py').read_bytes(),
                            (directory / 'turns/03-revise/workspace/bounds.py').read_bytes())

    def test_budget_is_shared_through_review_and_no_revision_after_stop(self):
        result = self.run_fixture(Limits(max_calls=3))
        self.assertEqual(result['stop_reason'], 'call_limit')
        self.assertEqual(result['turns_completed'], 3)
        self.assertIsNone(result['final_evidence'])

    def test_readonly_bypass_and_missing_review_stop_before_revision(self):
        for flag, reason in [('tamper', 'read_only_violation'), ('empty_review', 'missing_review')]:
            with self.subTest(flag=flag):
                ReviewSession.tamper = ReviewSession.empty_review = False
                setattr(ReviewSession, flag, True)
                result = self.run_fixture()
                self.assertEqual(result['stop_reason'], reason)
                self.assertEqual(result['turns_completed'], 2)
                self.assertIsNone(result['final_evidence'])

    def test_writable_review_is_rejected_before_creating_run(self):
        turns = list(self.workflow.turns)
        turns[2] = replace(turns[2], allow_write=True)
        with self.assertRaisesRegex(ValueError, 'review'):
            self.run_fixture(workflow=replace(self.workflow, turns=tuple(turns)))
        self.assertFalse(list(self.root.iterdir()))

    def test_reviewer_audit_rejects_native_or_mcp_write_grants(self):
        config = opencode_config([self.models[0], self.models[1], self.models[0]], 'http://fixture',
                                 Limits(), 'planner_executor_reviewer')
        self.assertEqual(len(config['providers']), 2)
        agents = []
        for name, item in config['agents'].items():
            provider, model = item['model'].split('/', 1)
            agents.append({'id': name, **item, 'model': {'providerID': provider, 'id': model}})
            self.assertEqual(item['mode'], 'primary')
        expected = {'roles': role_ids('planner_executor_reviewer'), 'agents': config['agents'],
                    'strategy': 'planner_executor_reviewer'}
        self.assertEqual(len(audit_registered_agents(agents, expected)), 3)
        reviewer = next(a for a in agents if a['id'] == ROLE_AGENT_IDS['reviewer'])
        for action in ('edit', 'shell', 'lab_reviewer_write_file', 'lab_worker_edit_file', 'subagent'):
            with self.subTest(action=action):
                reviewer['permissions'].append({'action': action, 'resource': '*', 'effect': 'allow'})
                with self.assertRaises(ValueError):
                    audit_registered_agents(agents, expected)
                reviewer['permissions'].pop()

    def test_review_text_does_not_use_old_assistant_or_reasoning(self):
        messages = {'data': [
            {'type': 'assistant', 'time': {'created': 1, 'completed': 2}, 'content': [{'type': 'text', 'text': 'OLD'}]},
            {'type': 'assistant', 'time': {'created': 3, 'completed': 4}, 'content': [{'type': 'reasoning', 'text': 'SECRET'}]}]}
        with self.assertRaisesRegex(StopRun, 'missing_review'):
            review_reply(messages)

    def test_bad_architecture_workflow_rejected_at_config_load(self):
        config = {'schema_version': 1, 'backend': 'opencode',
                  'workflow': str(ROOT / 'configs/workflows/daily-review.json'),
                  'tasks': [str(ROOT / 'tickets/clamp-boundaries/task.json')],
                  'architectures': [{'id': 'review', 'strategy': 'planner_executor_reviewer',
                                    'models': [m.id for m in self.models]}], 'batch_budget_usd': '5'}
        path = self.root / 'bad.json'; path.write_text(json.dumps(config), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'review'):
            load_workflow_experiment(path, {m.id: m for m in self.models})


if __name__ == '__main__':
    unittest.main()
