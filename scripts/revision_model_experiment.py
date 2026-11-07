"""Freeze revision-only task packs; summarize every attempt without selecting winners."""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from agent_lab.domain import Task, load_models, now, read_json, save_json
from agent_lab.runner import task_fingerprint
from agent_lab.workspace import file_hash, inventory
from agent_lab.workflow_experiments import load_workflow_experiment
from audit_review_checkpoints import parse_grade

AUDIT = ROOT / 'artifacts/plan14-checkpoint-audit-20261105-01/audit.json'


def prepare(output):
    output = output.resolve()
    if output.exists():
        raise ValueError('Use a new pack directory')
    audit = read_json(AUDIT)
    assert audit['audit_consistent'] and len(audit['rows']) == 8
    rows = []
    for index, row in enumerate(audit['rows']):
        run = Path(row['original_run'])
        original = Task.load(ROOT / 'benchmarks/python-calibration-v1/tasks' / row['task'] / 'task.json')
        assert task_fingerprint(original) == read_json(run / 'config.json')['task_fingerprint']
        snapshot = run / 'turns/01-implement/workspace'
        assert inventory(snapshot) == inventory(run / 'turns/02-review/workspace')
        review = read_json(run / 'review.json')['text']
        assert review.strip()
        task_id = f'revision-{index + 1:02d}-{row["task"].removeprefix("python-")}'
        directory = output / 'tasks' / task_id
        directory.mkdir(parents=True)
        shutil.copytree(snapshot, directory / 'source')
        assert inventory(snapshot) == inventory(directory / 'source')
        for kind in ('public', 'final'):
            saved = run / 'checks' / f'{kind}.py'
            assert file_hash(saved) == file_hash(getattr(original, kind + '_check'))
            shutil.copyfile(saved, directory / f'{kind}.py')
        contract = original.public_contract()
        contract.update(id=task_id, source_dir='source', public_check='public.py', final_check='final.py')
        contract['description'] += ('\n\n当前工作区是一份已有实现。以下是此前只读审查者的原始意见；'
                                   '请独立核实，不应为了符合意见而无依据地修改。\n\n' + review)
        save_json(directory / 'task.json', contract)
        loaded = Task.load(directory / 'task.json')
        rows.append({'task': task_id, 'original_task': row['task'], 'original_architecture': row['architecture'],
                     'original_run': str(run), 'original_review_sha256': file_hash(run / 'review.json'),
                     'source_inventory': inventory(snapshot), 'task_fingerprint': task_fingerprint(loaded),
                     'baseline_grade': row['checkpoints']['01-implement']['grade']})
    original_workflow = read_json(ROOT / 'configs/workflows/plan-execute-review.json')
    save_json(output / 'workflow.json', {'schema_version': 1, 'id': 'frozen-review-revision-v1',
                                       'turns': [original_workflow['turns'][3]]})
    config = read_json(ROOT / 'configs/workflow-python-review-planner-comparison.json')
    config.update(workflow='workflow.json', architectures=[
        {'id': 'luna-revision', 'strategy': 'single_agent', 'models': ['gpt-6-luna']},
        {'id': 'sol-revision', 'strategy': 'single_agent', 'models': ['gpt-6.1-sol']}],
        repeats=3, seed=42, batch_budget_usd='5.00',
        catalog=str(ROOT / 'configs/models-python-calibration-repeat.json'),
        tasks=[f'tasks/{r["task"]}/task.json' for r in rows])
    config.pop('task_globs')
    save_json(output / 'experiment.json', config)
    tasks, architectures, workflow, limits, repeats, seed, budget = load_workflow_experiment(
        output / 'experiment.json', load_models(Path(config['catalog'])))
    assert len(tasks) * len(architectures) * repeats == 48
    save_json(output / 'preregistration.json', {
        'created_at': now(), 'status': 'frozen_before_generation', 'audit_sha256': file_hash(AUDIT),
        'design': 'paired_revision_model_ablation', 'rows': rows, 'planned_attempts': 48,
        'batch_budget_usd': str(budget), 'repeats': repeats, 'seed': seed,
        'context': 'Fresh independent session per attempt; original requirements, implementation, saved Sol review only. No original conversation or planner output.',
        'roles': 'Single non-delegating revision Executor; no new Planner or Reviewer generation.',
        'feedback': 'Public checks only during revision. Baseline grades and hidden failures remain operator-only.',
        'endpoints': ['full pass rate', 'fail-to-pass / initially failing inputs',
                      'pass-to-fail / initially passing inputs', 'fixed and introduced scenario IDs',
                      'all-attempt cost and time; unknown usage separately'],
        'stop_policy': 'No automatic retry or parameter adaptation. Stop on infrastructure/unknown-usage errors or budget exhaustion.',
        'limitations': 'Eight selected development snapshots from two libraries, not eight independent projects. Fresh context differs from historical full workflows; only revision-stage cost measured.',
        'experiment_sha256': file_hash(output / 'experiment.json'),
        'workflow_sha256': file_hash(output / 'workflow.json')})
    print(f'Prepared {len(tasks)} identical-input packs / 48 attempts; budget ${budget}', flush=True)


def summarize(pack, batch):
    protocol = read_json(pack / 'preregistration.json')
    manifest = read_json(batch / 'batch.json')
    if manifest['status'] == 'running' or manifest['inflight']:
        raise ValueError('Wait for the batch to stop before summarizing')
    assert file_hash(pack / 'experiment.json') == protocol['experiment_sha256']
    assert file_hash(pack / 'workflow.json') == protocol['workflow_sha256']
    inputs = {r['task']: r for r in protocol['rows']}
    rows, groups = [], defaultdict(list)
    for cell, run_id in manifest['completed'].items():
        task_id, architecture, repeat = cell.split(':')
        source = inputs[task_id]
        run = batch / 'runs' / run_id
        result = read_json(run / 'result.json')
        config = read_json(run / 'config.json')
        assert config['task_fingerprint'] == source['task_fingerprint']
        assert inventory(run / 'baseline') == {**source['source_inventory'],
                                               'opencode.jsonc': file_hash(run / 'baseline/opencode.jsonc')}
        evidence = result['final_evidence']
        grade = (parse_grade(run / 'checks' / evidence['log'])
                 if evidence and evidence['ok'] and evidence['completion_verified'] else None)
        baseline = source['baseline_grade']
        before_ok = baseline['passed'] == baseline['total']
        transition, fixed, introduced = 'unresolved_evidence', [], []
        if grade:
            after_ok = grade['passed'] == grade['total']
            transition = ('pass_to_pass' if before_ok and after_ok else 'fail_to_pass' if after_ok else
                          'pass_to_fail' if before_ok else 'fail_to_fail')
            old = {s['case'] for s in baseline['failed_scenarios']}
            new = {s['case'] for s in grade['failed_scenarios']}
            fixed, introduced = sorted(old - new), sorted(new - old)
        row = {'task': task_id, 'architecture': architecture, 'repeat': int(repeat),
               'run_id': run_id, 'status': result['status'], 'stop_reason': result['stop_reason'],
               'baseline_passed': before_ok, 'baseline_grade': baseline, 'grade': grade,
               'transition': transition, 'fixed_scenarios': fixed, 'introduced_scenarios': introduced,
               'accounting': result['accounting'], 'duration_seconds': result['duration_seconds']}
        rows.append(row)
        groups[architecture].append(row)
    totals = {}
    for architecture, subset in groups.items():
        totals[architecture] = {
            'attempts': len(subset), 'valid_grades': sum(r['grade'] is not None for r in subset),
            'full_passes': sum(r['transition'] in ('pass_to_pass', 'fail_to_pass') for r in subset),
            'attempts_with_new_failures': sum(bool(r['introduced_scenarios']) for r in subset),
            'transitions': dict(Counter(r['transition'] for r in subset)),
            'initially_passed_attempts': sum(r['baseline_passed'] for r in subset),
            'initially_failed_attempts': sum(not r['baseline_passed'] for r in subset),
            'known_cost_usd': str(sum((Decimal(r['accounting']['estimated_cost_usd']) for r in subset), Decimal(0))),
            'unknown_cost_reserve_usd': str(sum((Decimal(r['accounting'].get('unknown_cost_reserve_usd', '0')) for r in subset), Decimal(0))),
            'unknown_calls': sum(r['accounting'].get('unknown_calls', 0) for r in subset),
            'usage_complete': all(r['accounting']['usage_complete'] for r in subset),
            'calls': sum(r['accounting']['calls'] for r in subset),
            'total_tokens': sum(r['accounting']['total_tokens'] for r in subset),
            'duration_seconds': sum(r['duration_seconds'] for r in subset)}
    save_json(batch / 'revision-comparison.json', {'status': manifest['status'], 'planned_attempts': 48,
                                                 'totals': totals, 'rows': rows})
    lines = ['# 修正模型对照', '', '相同8份代码与Sol审查，各模型重复3次。费用仅含修正阶段，未含原规划、实施、审查费用。', '',
             '| 修正模型 | 有效验收/尝试 | 最终通过 | 失败→通过 | 通过→失败 | 通过→通过 | 失败→失败 | 任意新增失败的尝试 | 已知费用 USD |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for arch, t in totals.items():
        c = t['transitions']
        lines.append(f'| {arch} | {t["valid_grades"]}/{t["attempts"]} | {t["full_passes"]}/{t["valid_grades"]} | {c.get("fail_to_pass", 0)} | {c.get("pass_to_fail", 0)} | {c.get("pass_to_pass", 0)} | {c.get("fail_to_fail", 0)} | {t["attempts_with_new_failures"]} | {t["known_cost_usd"]} |')
    lines += ['', '| 输入 | 修正模型 | 重复 | 修正前 | 修正后 | 修复场景 | 新增失败 |', '|---|---|---:|---:|---:|---:|---:|']
    for r in sorted(rows, key=lambda r: (r['task'], r['architecture'], r['repeat'])):
        b, g = r['baseline_grade'], r['grade']
        score = f'{g["passed"]}/{g["total"]}' if g else '证据不足'
        lines.append(f'| {r["task"]} | {r["architecture"]} | {r["repeat"] + 1} | {b["passed"]}/{b["total"]} | {score} | {len(r["fixed_scenarios"])} | {len(r["introduced_scenarios"])} |')
    lines += ['', '选定开发任务上的诊断实验；同一输入的重复并不增加独立任务数量。保留所有尝试，不选择最佳答案。隐藏验收只在结束后用于统计，未回传Agent。']
    (batch / 'revision-comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(totals, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'summarize'])
    parser.add_argument('--pack', type=Path, required=True)
    parser.add_argument('--batch', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.pack)
    else:
        summarize(args.pack.resolve(), args.batch.resolve())
