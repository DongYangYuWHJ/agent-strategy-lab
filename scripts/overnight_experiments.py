"""One authorized pass for Plan16 continuation then Plan17; no automatic retries."""
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
from agent_lab.domain import read_json, save_json, now
from agent_lab.workflow_experiments import load_workflow_experiment
from agent_lab.domain import load_models
from self_test_architecture_experiment import freeze, summarize
from summarize_architecture_repeats import totals

BASE = ROOT / 'artifacts/overnight-plan16-plan17-20261106-01'
OLD = ROOT / 'artifacts/plan16-self-tests-architecture-live-20261106-01'


def prepare():
    if BASE.exists():
        raise ValueError('Do not overwrite overnight evidence')
    old = read_json(OLD / 'batch.json')
    old_report = read_json(OLD / 'self-test-comparison.json')
    raw = read_json(ROOT / 'configs/workflow-python-self-test-architecture-comparison.json')
    raw['workflow'] = str(ROOT / 'configs' / raw['workflow'])
    raw['catalog'] = str(ROOT / 'configs' / raw['catalog'])
    raw['task_globs'] = [str((ROOT / 'configs' / p).resolve()) for p in raw['task_globs']]
    completed = [r['cell'] for r in old_report['rows'] if r['category'] != 'incomplete_or_environment']
    assert len(completed) == 2 and old['status'] != 'running' and not old['inflight']
    known, reserve = Decimal(old_report['known_cost_usd']), Decimal(old_report['unknown_cost_reserve_usd'])
    raw['skip_cells'] = completed
    raw['batch_budget_usd'] = str(Decimal('5') - known - reserve)
    BASE.mkdir(parents=True)
    config16 = BASE / 'plan16-continuation.json'
    save_json(config16, raw)
    tasks, architectures, workflow, limits, repeats, seed, budget = load_workflow_experiment(config16, load_models(Path(raw['catalog'])))
    assert old['configuration']['workflow'] == json.loads(json.dumps(asdict(workflow)))
    assert old['configuration']['limits'] == asdict(limits)
    arch_values = [{**a, 'catalog': [asdict(m) for m in models]} for a, models in architectures]
    assert old['configuration']['architectures'] == arch_values
    prereg16 = BASE / 'plan16-preregistration.json'
    freeze(prereg16, config16)
    assert read_json(prereg16)['role_prompts'] == old['configuration']['role_prompts']
    assert read_json(prereg16)['task_fingerprints'] == old['configuration']['task_fingerprints']
    prereg17 = BASE / 'plan17-preregistration.json'
    config17 = ROOT / 'configs/workflow-python-flexible-team-comparison.json'
    freeze(prereg17, config17)
    record = {'created_at': now(), 'status': 'prepared', 'prior_batch': str(OLD),
        'prior_known_cost_usd': str(known), 'prior_unknown_reserve_usd': str(reserve),
        'reused_cells': completed, 'authorized_interrupted_cell_replacement': True,
        'framework_change': 'Adds separately gated flexible strategy and explicit skip_cells; strict task/model/prompts/limits verified identical. Original frozen batch is not resumed in place.',
        'stop_policy': 'One batch attempt each. No automatic retry or parameter adaptation. Plan17 runs independently even if Plan16 has an infrastructure/budget stop; cancellation aborts both.',
        'jobs': [
            {'plan': 16, 'experiment': str(config16), 'preregistration': str(prereg16),
             'output': str(BASE / 'plan16-live'), 'planned_new_cells': 22, 'budget_usd': str(budget)},
            {'plan': 17, 'experiment': str(config17), 'preregistration': str(prereg17),
             'output': str(BASE / 'plan17-live'), 'planned_new_cells': 24, 'budget_usd': '5.00'}]}
    save_json(BASE / 'queue.json', record)
    print(json.dumps(record, ensure_ascii=True), flush=True)


def aggregate16(output):
    old = read_json(OLD / 'self-test-comparison.json')
    new = read_json(output / 'self-test-comparison.json')
    reused = set(read_json(BASE / 'queue.json')['reused_cells'])
    old_rows = [{**r, 'origin_batch': str(OLD)} for r in old['rows'] if r['cell'] in reused]
    new_rows = [{**r, 'origin_batch': str(output)} for r in new['rows']]
    quality = old_rows + new_rows
    assert len({r['cell'] for r in quality}) == len(quality)
    attempts = [{**r, 'origin_batch': str(OLD)} for r in old['rows']] + new_rows
    grouped = {a: totals([r for r in attempts if r['architecture'] == a]) for a in new['architecture_totals']}
    result = {'planned_quality_cells': 24, 'quality_cells_recorded': len(quality),
        'valid_final_grades': sum(r['category'] != 'incomplete_or_environment' for r in quality),
        'new_batch_status': new['status'], 'architecture_totals_all_attempts': grouped,
        'quality_rows': quality, 'all_attempts': attempts,
        'known_cost_usd': str(Decimal(old['known_cost_usd']) + Decimal(new['known_cost_usd'])),
        'unknown_cost_reserve_usd': str(Decimal(old['unknown_cost_reserve_usd']) + Decimal(new['unknown_cost_reserve_usd']))}
    save_json(BASE / 'plan16-combined.json', result)
    lines = ['# Plan16：续跑及历史尝试合并', '',
        f"有效验收{result['valid_final_grades']}/24，续跑状态{new['status']}。原2个成功格仅复用，不重跑；原中断保留，替代运行有用户明确授权。", '',
        '| 结构 | 通过/有效验收 | 中断/未完成尝试 | 全部已知费用 USD | 未知预留 USD |', '|---|---:|---:|---:|---:|']
    for a, t in grouped.items():
        lines.append(f'| {a} | {t["accepted"]}/{t["accepted"] + t["acceptance_failed"]} | {t["incomplete_or_environment"]} | {t["known_cost_usd"]} | {t["unknown_cost_reserve_usd"]} |')
    lines += ['', '全部失败/中断费用保留，未知预留不是账单；不能将未完成算作解题失败。框架新增灵活模式，但严格组任务、模型、提示、限制与历史快照逐项核对相同。', '',
              f'全部已知${result["known_cost_usd"]}；未知预留${result["unknown_cost_reserve_usd"]}。']
    (BASE / 'plan16-combined.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def run():
    queue = read_json(BASE / 'queue.json')
    if queue['status'] != 'prepared':
        raise ValueError('This queue is never automatically replayed')
    queue.update(status='running', started_at=now())
    save_json(BASE / 'queue.json', queue)
    try:
        for job in queue['jobs']:
            job.update(status='running', started_at=now())
            save_json(BASE / 'queue.json', queue)
            print(f'START PLAN {job["plan"]}', flush=True)
            proc = subprocess.run([sys.executable, str(ROOT / 'lab.py'), 'batch', '--experiment', job['experiment'], '--output', job['output']], cwd=ROOT)
            job['process_exit_code'] = proc.returncode
            output = Path(job['output'])
            try:
                job['status'] = read_json(output / 'batch.json')['status']
                summarize(output, Path(job['preregistration']))
                if job['plan'] == 16:
                    aggregate16(output)
            except Exception as exc:
                job['report_error'] = type(exc).__name__ + ': ' + str(exc)[:500]
                job.setdefault('status', 'report_error')
            job['ended_at'] = now()
            save_json(BASE / 'queue.json', queue)
            print(f'END PLAN {job["plan"]}: {job["status"]}', flush=True)
            if job['status'] == 'cancelled' or proc.returncode in (130, -1073741510):
                queue['status'] = 'cancelled'
                break
        else:
            queue['status'] = 'finished'
    except KeyboardInterrupt:
        queue['status'] = 'cancelled'
        raise
    finally:
        queue['ended_at'] = now()
        save_json(BASE / 'queue.json', queue)


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in ('prepare', 'run'):
        raise SystemExit('Use prepare or run')
    prepare() if sys.argv[1] == 'prepare' else run()
