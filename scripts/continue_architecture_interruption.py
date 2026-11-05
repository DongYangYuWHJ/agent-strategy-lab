"""One explicitly authorized replacement for the interrupted architecture trial."""
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from agent_lab.domain import Task, digest, load_models, now, read_json, save_json
from agent_lab.experiments import run_batch
from agent_lab.opencode_workflow import workflow_role_prompts
from agent_lab.runner import task_fingerprint
from agent_lab.workspace import inventory
from agent_lab.workflows import Workflow


def main(run):
    original = ROOT / 'artifacts/python-architecture-sol-luna-repeat-live-20261104-01'
    output = ROOT / 'artifacts/python-architecture-sol-luna-recovery-20261104-01'
    cell = 'python-cachetools-atomic-update:sol-handoff-luna:1'
    batch = read_json(original / 'batch.json')
    frozen = batch['configuration']
    assert batch['status'] == 'opencode_session_error' and not batch['inflight']
    assert len(batch['completed']) == 24
    old = read_json(original / 'runs' / batch['completed'][cell] / 'result.json')
    assert old['stop_reason'] == 'opencode_session_error' and old['turns_completed'] == 1
    assert old['final_evidence'] is None and old['accounting']['unknown_calls'] == 1
    assert digest(inventory(ROOT / 'src/agent_lab')) == frozen['framework_fingerprint']
    task = ROOT / 'benchmarks/python-calibration-v1/tasks/python-cachetools-atomic-update/task.json'
    assert task_fingerprint(Task.load(task)) == frozen['task_fingerprints']['python-cachetools-atomic-update']
    catalog_path = ROOT / 'configs/models-python-calibration-repeat.json'
    catalog = load_models(catalog_path)
    arch = next(a for a in frozen['architectures'] if a['id'] == 'sol-handoff-luna')
    assert json.loads(json.dumps([asdict(catalog[m]) for m in arch['models']])) == arch['catalog']
    assert workflow_role_prompts(arch['strategy']) == frozen['role_prompts'][arch['id']]
    workflow = ROOT / 'configs/workflows/daily-review.json'
    assert json.loads(json.dumps(asdict(Workflow.load(workflow)))) == frozen['workflow']
    results = [read_json(original / 'runs' / rid / 'result.json') for rid in batch['completed'].values()]
    known = sum((Decimal(r['accounting']['estimated_cost_usd']) for r in results), Decimal(0))
    reserve = sum((Decimal(r['accounting']['unknown_cost_reserve_usd']) for r in results), Decimal(0))
    remaining = Decimal(frozen['batch_budget_usd']) - known - reserve
    assert remaining > 0
    config = {**read_json(ROOT / 'configs/workflow-python-architecture-sol-luna-repeat.json'),
              'architectures': [{k: arch[k] for k in ('id', 'strategy', 'models')}],
              'tasks': [str(task)], 'task_globs': [], 'repeats': 1,
              'workflow': str(workflow), 'catalog': str(catalog_path), 'batch_budget_usd': str(remaining)}
    record_path = output / 'recovery.json'
    if not run:
        if output.exists():
            raise ValueError('Recovery already exists; inspect, do not replay')
        output.mkdir()
        save_json(output / 'experiment.json', config)
        save_json(record_path, {'schema_version': 1, 'status': 'prepared', 'created_at': now(),
            'original_batch': str(original), 'original_batch_fingerprint': batch['fingerprint'],
            'original_cell': cell, 'original_run_id': batch['completed'][cell],
            'overall_trial': 3, 'replacement_local_repeat': 0,
            'user_authorized_interruption_replacement': True,
            'fresh_session_from_original_source': True, 'experiment_parameters_changed': False,
            'previous_known_cost_usd': str(known), 'previous_unknown_reserve_usd': str(reserve),
            'global_budget_usd': frozen['batch_budget_usd'], 'remaining_budget_usd': str(remaining),
            'output': str(output / 'batch'), 'automatic_retries': 0})
        print(json.dumps({'status': 'prepared', 'only_cell': cell, 'remaining_budget_usd': str(remaining)}))
        return
    record = read_json(record_path)
    assert record['status'] == 'prepared' and not (output / 'batch').exists()
    assert read_json(output / 'experiment.json') == config
    record['status'] = 'running'
    save_json(record_path, record)
    try:
        result = run_batch(output / 'experiment.json', catalog, output / 'batch')
        record['status'] = result['status']
        record['completed'] = result['completed']
    finally:
        record['updated_at'] = now()
        save_json(record_path, record)
    print(json.dumps({'status': record['status'], 'completed': record.get('completed')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    main(parser.parse_args().run)
