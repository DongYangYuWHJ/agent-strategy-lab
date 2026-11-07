"""Freeze and summarize PE versus PER with the same planned-self-test tools."""
import argparse
from dataclasses import asdict
from pathlib import Path
from decimal import Decimal
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from agent_lab.domain import now, read_json, save_json, digest, load_models
from agent_lab.workspace import inventory, file_hash
from agent_lab.workflow_experiments import load_workflow_experiment
from agent_lab.opencode_workflow import workflow_role_prompts
from agent_lab.runner import task_fingerprint
from agent_lab.workflows import primary_schedule, effective_workflow
from summarize_architecture_comparison import summarize as extract
from summarize_architecture_repeats import totals

CONFIG = ROOT / 'configs/workflow-python-self-test-architecture-comparison.json'


def freeze(path, experiment=CONFIG):
    if path.exists():
        raise ValueError('Do not overwrite a preregistration')
    raw = read_json(experiment)
    tasks, architectures, workflow, limits, repeats, seed, budget = load_workflow_experiment(
        experiment, load_models(experiment.parent / raw['catalog']))
    flexible = any(a['strategy'].endswith('_flexible') for a, _ in architectures)
    record = {'created_at': now(), 'planned_cells': len(tasks) * len(architectures) * repeats - len(raw.get('skip_cells', [])),
        'repeats': repeats, 'seed': seed, 'batch_budget_usd': str(budget),
        'experiment': str(experiment), 'experiment_sha256': file_hash(experiment),
        'workflow': asdict(workflow), 'limits': asdict(limits),
        'task_fingerprints': {t.id: task_fingerprint(t) for t in tasks},
        'framework_fingerprint': digest(inventory(ROOT / 'src/agent_lab')),
        'architectures': [{**a, 'catalog': [asdict(m) for m in models]} for a, models in architectures],
        'role_prompts': {a['id']: workflow_role_prompts(a['strategy']) for a, _ in architectures},
        'comparison': 'Same four prompts and tools: P/W/W/W vs P/W/R/W. Sol Planner, Luna Executor; Sol independent Reviewer in PER only.',
        'endpoints': ['final hidden pass rate', 'all-attempt costs/calls/time', 'self-test creation and execution',
                      'last self-test source/test version freshness', 'phase-level costs'],
        'stop_policy': 'No automatic paid retry, adaptive prompts, parameter changes or hidden feedback. Preserve all stops and unknown usage.',
        'local_validation': {'unit_tests_passed': 177, 'new_self_test_cases_passed': 5,
                             'native_opencode_fixture_protocols': ['planner_handoff', 'planner_executor_reviewer']},
        'limitations': 'Four correlated development tasks, three repeats per cell. No causal comparison to historical no-self-test batches.'}
    if flexible:
        record.update(architecture_workflows={a['id']: asdict(effective_workflow(a['strategy'], workflow)) for a, _ in architectures},
                      comparison='Strict vs flexible responsibilities and write permissions; same Sol/Luna/Sol model schedule.', plan_number=17)
    save_json(path, record)
    print(f'Frozen {record["planned_cells"]} planned cells, budget ${budget}')


def summarize(directory, preregistration):
    frozen = read_json(preregistration)
    batch = read_json(directory / 'batch.json')
    if batch['status'] == 'running' or batch['inflight']:
        raise ValueError('Wait for the batch to stop')
    config = batch['configuration']
    for key in ('workflow', 'limits', 'task_fingerprints', 'framework_fingerprint', 'architectures', 'role_prompts'):
        assert config[key] == json.loads(json.dumps(frozen[key])), key
    if 'architecture_workflows' in frozen:
        assert config['architecture_workflows'] == frozen['architecture_workflows']
    rows = extract(directory, rows_only=True)
    architectures = {a['id']: a for a in config['architectures']}
    for row in rows:
        run = directory / Path(row['result_path']).parent
        events = [json.loads(line) for line in (run / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
        architecture = architectures[row['architecture']]
        from agent_lab.workflows import Workflow, Turn
        specific = config.get('architecture_workflows', {}).get(row['architecture'], config['workflow'])
        workflow = Workflow(specific['id'], tuple(Turn(**t) for t in specific['turns']))
        schedule = dict(zip([t.id for t in workflow.turns], primary_schedule(architecture['strategy'], workflow)))
        starts = [e for e in events if e['type'] == 'request_started']
        assert all(e['primary_role'] == schedule[e['turn']][0] and
                   e['model_id'] == architecture['models'][schedule[e['turn']][1]] for e in starts)
        tools = [e for e in events if e['type'] == 'tool']
        flexible = architecture['strategy'].endswith('_flexible')
        successful_writes = [e for e in tools if e['tool'] in ('write_test', 'write_file', 'edit_file') and e['result'].get('ok')]
        if not flexible:
            assert all(e['role'] == 'worker' and e['turn'] in ('implement', 'revise') for e in successful_writes)
        row['cross_role_writes'] = {role: sum(e['role'] == role for e in successful_writes) for role in ('planner', 'worker', 'reviewer')}
        test_files = sorted((run / 'self-tests/source').glob('test_*.py'))
        test_runs = sorted((run / 'self-tests').glob('*-result.json'))
        latest = read_json(test_runs[-1]) if test_runs else None
        source = {name: file_hash(run / 'workspace' / name) for name in read_json(run / 'task.json')['editable_files']}
        tests = {p.name: file_hash(p) for p in test_files}
        fresh = bool(latest and latest['test_hashes'] == tests and
                     all(latest['source_hashes'].get(n) == checksum for n, checksum in source.items()))
        row['self_tests'] = {'files': len(test_files), 'runs': len(test_runs), 'latest_matches_final': fresh,
                             'latest_passed': latest.get('passed') if latest else None,
                             'latest_tests_run': latest.get('tests_run') if latest else 0,
                             'worker_writes': sum(e['tool'] == 'write_test' and e['result'].get('ok', False) for e in tools),
                             'reviewer_runs': sum(e['tool'] == 'run_self_tests' and e['role'] == 'reviewer' for e in tools)}
        row['phase_costs'] = {phase: str(sum((Decimal(e['estimated_cost_usd']) for e in events
            if e['type'] == 'request_completed' and e['turn'] == phase), Decimal(0))) for phase in schedule}
        if row['category'] != 'incomplete_or_environment':
            assert read_json(run / 'permission-audit.json')['passed']
            assert not read_json(run / 'child-sessions.json')['data']
            for index in (0, 2):
                if workflow.turns[index].allow_write:
                    continue
                turn = config['workflow']['turns'][index]['id']
                previous = run / 'baseline' if index == 0 else run / 'turns/01-implement/workspace'
                current = run / 'turns' / f'{index:02d}-{turn}' / 'workspace'
                assert all(file_hash(previous / name) == file_hash(current / name) for name in source)
                old_tests = {} if index == 0 else {p.name: file_hash(p) for p in (run / 'turns/01-implement/self-tests').glob('*.py')}
                now_tests = {p.name: file_hash(p) for p in (run / 'turns' / f'{index:02d}-{turn}' / 'self-tests').glob('*.py')}
                assert old_tests == now_tests
    grouped = {a: {**totals([r for r in rows if r['architecture'] == a]),
        'with_tests': sum(r['self_tests']['files'] > 0 for r in rows if r['architecture'] == a),
        'fresh_self_test_passes': sum(r['self_tests']['latest_matches_final'] and bool(r['self_tests']['latest_passed']) for r in rows if r['architecture'] == a)}
        for a in architectures}
    result = {'status': batch['status'], 'planned': frozen['planned_cells'], 'recorded': len(rows),
              'architecture_totals': grouped, 'rows': rows,
              'known_cost_usd': str(sum((Decimal(t['known_cost_usd']) for t in grouped.values()), Decimal(0))),
              'unknown_cost_reserve_usd': str(sum((Decimal(t['unknown_cost_reserve_usd']) for t in grouped.values()), Decimal(0)))}
    save_json(directory / 'self-test-comparison.json', result)
    lines = [('# Plan 17：严格分工与灵活分工对照' if frozen.get('plan_number') == 17 else '# Plan 16：自测职责下 PE 与 PER 对照'), '',
             f"状态 {batch['status']}；记录{len(rows)}/{frozen['planned_cells']}次。每题每结构预定{frozen['repeats']}次，全部尝试保留。", '',
             '| 结构 | 全通过/有效验收 | 未完成 | 有自测 | 最终版本自测通过 | 费用 USD | 未知预留 USD |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for a, t in grouped.items():
        lines.append(f'| {a} | {t["accepted"]}/{t["accepted"] + t["acceptance_failed"]} | {t["incomplete_or_environment"]} | {t["with_tests"]} | {t["fresh_self_test_passes"]} | {t["known_cost_usd"]} | {t["unknown_cost_reserve_usd"]} |')
    lines += ['', '| 任务 | 结构 | 重复 | 最终场景 | 费用 USD | 自测文件/执行次数 | 最终版本自测通过 |', '|---|---|---:|---:|---:|---:|---|']
    for r in sorted(rows, key=lambda r: (r['task'], r['architecture'], r['repeat'])):
        t = r['self_tests']
        score = f'{r["scenarios_passed"]}/{r["scenarios_graded"]}' if r['groups'] else r['stop_reason']
        lines.append(f'| {r["task"]} | {r["architecture"]} | {r["repeat"] + 1} | {score} | {r["accounting"]["estimated_cost_usd"]} | {t["files"]}/{t["runs"]} | {t["latest_matches_final"] and bool(t["latest_passed"])} |')
    description = ('固定Sol/Luna/Sol及四轮调度，对照严格职责与灵活职责/权限。测试过程证据不替代隐藏验收；提示词和权限同时改变，不单独归因于权限。'
                   if frozen.get('plan_number') == 17 else '两组共享四轮提示与自测能力；PE的只读检查由Luna自己完成，PER由Sol Reviewer完成。测试只提供过程证据，最终成绩仍来自隐藏验收。不是对历史旧提示词的单变量比较。')
    lines += ['', description, '',
              f'全部尝试已知费用${result["known_cost_usd"]}，未知预留${result["unknown_cost_reserve_usd"]}。']
    (directory / 'self-test-comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('freeze', 'summarize'))
    parser.add_argument('--preregistration', type=Path, required=True)
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--experiment', type=Path, default=CONFIG)
    args = parser.parse_args()
    if args.action == 'freeze':
        freeze(args.preregistration.resolve(), args.experiment.resolve())
    else:
        summarize(args.directory.resolve(), args.preregistration.resolve())
