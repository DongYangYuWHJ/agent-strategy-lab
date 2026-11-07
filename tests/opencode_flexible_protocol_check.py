"""Real OpenCode / local fixture replies; Planner and Reviewer both edit source."""
from pathlib import Path
from dataclasses import replace
import json
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from agent_lab.domain import Task, load_models, Limits, read_json, save_json
from agent_lab.workflows import Workflow
from agent_lab.opencode_workflow import run_workflow

output = Path(sys.argv[1]).resolve()
if output.exists():
    raise ValueError('Use a fresh output')
task = Task.load(ROOT / 'tickets/clamp-boundaries/task.json')
action = next(a for batch in read_json(task.manifest_path.parent / 'replay.json') for a in batch if a['name'] == 'write_file')
base = load_models(ROOT / 'configs/models.json')['deepseek-flash']
models = [replace(base, id='fixture-plan'), replace(base, id='fixture-execute'), replace(base, id='fixture-review')]
count = 0


def respond(provider, payload, timeout):
    global count
    count += 1
    tools = [t['function']['name'] for t in payload['tools']]
    role = next(r for r in ('planner', 'worker', 'reviewer') if any(n.startswith('lab_' + r + '_') for n in tools))
    assert any(n.endswith('write_file') for n in tools) and any(n.endswith('run_self_tests') for n in tools)
    marker = 'FIXTURE_EDIT_' + role
    written = marker in json.dumps(payload['messages'])
    message = {'role': 'assistant', 'content': '角色已核对并完成。' if written else None}
    if not written:
        tool = next(n for n in tools if n.endswith('_write_file'))
        message['tool_calls'] = [{'id': f'fixture-{count}', 'type': 'function', 'function': {
            'name': tool, 'arguments': json.dumps({'path': 'bounds.py', 'content': '# ' + marker + '\n' + action['arguments']['content']})}}]
    response = {'id': str(count), 'model': provider.model.model, 'choices': [{'index': 0, 'message': message,
        'finish_reason': 'tool_calls' if not written else 'stop'}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 30}}
    delta = dict(message)
    if not written:
        delta['tool_calls'] = [{'index': i, **call} for i, call in enumerate(message['tool_calls'])]
    chunks = [{'id': str(count), 'object': 'chat.completion.chunk', 'created': 1, 'model': provider.model.model,
               'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
              {'id': str(count), 'object': 'chat.completion.chunk', 'created': 1, 'model': provider.model.model,
               'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop' if written else 'tool_calls'}],
               'usage': response['usage']}]
    body = (''.join('data: ' + json.dumps(c) + '\n\n' for c in chunks) + 'data: [DONE]\n\n').encode()
    return body, {**response, '_lab_tool_calls': int(not written)}


with patch('agent_lab.providers.require_credential', return_value='fixture'), \
     patch('agent_lab.workflow_gateway.forward_stream', respond):
    result = run_workflow(task, models, Limits(max_cost_usd='5'), output,
        Workflow.load(ROOT / 'configs/workflows/plan-execute-review-self-tests.json'), 'planner_executor_reviewer_flexible')
root = Path(result['artifact_dir'])
assert result['accepted'] and result['turns_completed'] == 4, result
assert read_json(root / 'permission-audit.json')['passed']
assert not read_json(root / 'child-sessions.json')['data']
events = [json.loads(line) for line in (root / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
writes = [e for e in events if e['type'] == 'tool' and e.get('tool') == 'write_file' and e['result'].get('ok')]
assert {'planner', 'worker', 'reviewer'} <= {e['role'] for e in writes}
save_json(output / 'verification.json', {'passed': True, 'paid_calls': 0, 'fixture_calls': count,
    'source_writes_by': sorted({e['role'] for e in writes}), 'native_shell_denied': True, 'run': root.name})
print(json.dumps({'passed': True, 'paid_calls': 0, 'fixture_calls': count}))
