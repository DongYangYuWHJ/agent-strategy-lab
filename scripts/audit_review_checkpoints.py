"""Post-hoc local checkpoint grading. Never call models or modify original runs."""
import argparse
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from agent_lab.domain import Task, now, read_json, save_json
from agent_lab.evaluation import Checks
from agent_lab.runner import task_fingerprint
from agent_lab.workspace import Workspace, file_hash, inventory

STAGES = ('01-implement', '02-review', '03-revise')


def parse_grade(path):
    log = path.read_text(encoding='utf-8')
    groups = [json.loads(line.removeprefix('LAB_GROUP_RESULTS '))
              for line in log.splitlines() if line.startswith('LAB_GROUP_RESULTS ')]
    if len(groups) != 1:
        return None
    groups = groups[0]
    passed = sum(g['passed'] for g in groups.values())
    total = sum(g['total'] for g in groups.values())
    failures = {int(number): group for number, group in re.findall(
        r'(?:^|AssertionError:\s*)case\s+(\d+)\s+\[([^\]]+)\]', log, re.MULTILINE)}
    if len(failures) != total - passed:
        raise ValueError(f'Incomplete scenario failure list: {path}')
    return {'passed': passed, 'total': total, 'groups': groups,
            'failed_scenarios': [{'case': n, 'group': failures[n]} for n in sorted(failures)]}


def audit(batch_dir, output):
    if output.exists() or output.is_relative_to(batch_dir) or batch_dir.is_relative_to(output):
        raise ValueError('Use a new output directory separate from original evidence')
    batch = read_json(batch_dir / 'batch.json')
    original_report = read_json(batch_dir / 'review-comparison.json')
    if batch['status'] != 'completed' or batch['inflight'] or len(original_report['rows']) != 8:
        raise ValueError('Expected the completed eight-cell planner comparison')
    runtime_names = ('check_host.py', 'check_client.py', 'submission_worker.py')
    inputs = []
    for row in original_report['rows']:
        run = batch_dir / Path(row['result_path']).parent
        config = read_json(run / 'config.json')
        task = Task.load(ROOT / 'benchmarks/python-calibration-v1/tasks' / row['task'] / 'task.json')
        if task_fingerprint(task) != config['task_fingerprint']:
            raise ValueError('Task source or validator differs from the frozen run')
        for kind in ('public', 'final'):
            if file_hash(getattr(task, kind + '_check')) != file_hash(run / 'checks' / (kind + '.py')):
                raise ValueError('Saved grader differs from task grader')
        for name in runtime_names:
            if file_hash(ROOT / 'src/agent_lab' / name) != file_hash(run / 'checks/runtime' / name):
                raise ValueError('Saved grading runtime differs; do not silently migrate it')
        snapshots = {stage: inventory(run / 'turns' / stage / 'workspace') for stage in STAGES}
        if snapshots[STAGES[0]] != snapshots[STAGES[1]]:
            raise ValueError('Reviewer changed code; inspect before interpreting checkpoint scores')
        final_source = inventory(run / 'workspace')
        final_source.pop('opencode.jsonc', None)
        if snapshots[STAGES[2]] != final_source:
            raise ValueError('Saved final checkpoint differs from delivered source')
        inputs.append((row, run, task, snapshots))
    output.mkdir(parents=True)
    record = {'schema_version': 1, 'status': 'running', 'created_at': now(),
              'analysis_kind': 'posthoc_existing_code_only', 'original_batch': str(batch_dir),
              'original_final_results_already_known': True, 'generation_requests': 0,
              'feedback_to_agents': False, 'snapshot_positions': 24,
              'checkpoint_timeout_seconds': 120,
              'timeout_policy': 'Environment/missing evidence, never a model-quality failure; no automatic retry.',
              'protocol': ['Grade three independent copies per run with the frozen final checker and matching runtime.',
                           'Compare full group scores and failed scenario IDs; identical review source must grade identically.',
                           'Final checkpoint must reproduce the originally recorded groups and failures.',
                           'Preserve every audit log/receipt; never overwrite original run evidence or send feedback to models.'],
              'rows': []}
    save_json(output / 'audit.json', record)
    protected = {batch_dir / 'batch.json': file_hash(batch_dir / 'batch.json'),
                 batch_dir / 'review-comparison.json': file_hash(batch_dir / 'review-comparison.json')}
    for row, run, task, snapshots in inputs:
        protected[run / 'result.json'] = file_hash(run / 'result.json')
        original_grade = parse_grade(run / 'checks' / row['final_evidence']['log'])
        checkpoints = {}
        for stage in STAGES:
            directory = output / 'runs' / run.name / stage
            directory.mkdir(parents=True)
            offline_task = replace(task, source_dir=run / 'turns' / stage / 'workspace',
                                   public_check=run / 'checks/public.py', final_check=run / 'checks/final.py')
            workspace = Workspace(offline_task, directory)
            checks = Checks(offline_task, directory, workspace, 120)
            evidence = checks.run('final', 120)
            grade = parse_grade(directory / 'checks' / evidence['log']) if evidence['ok'] and evidence['completion_verified'] else None
            item = {'stage': stage, 'evidence': evidence, 'grade': grade,
                    'original_snapshot': str((run / 'turns' / stage / 'workspace').resolve()),
                    'audit_directory': str(directory.resolve())}
            save_json(directory / 'checkpoint.json', item)
            checkpoints[stage] = item
            print(json.dumps({'task': row['task'], 'architecture': row['architecture'], 'stage': stage,
                              'score': [grade['passed'], grade['total']] if grade else None,
                              'status': evidence['status']}, ensure_ascii=True), flush=True)
        before, reviewed, after = [checkpoints[s]['grade'] for s in STAGES]
        complete = all(g is not None for g in (before, reviewed, after))
        deterministic_review = complete and before == reviewed
        reproduced = after is not None and after == original_grade
        outcome = 'unresolved_evidence'
        fixed, introduced = [], []
        if complete:
            before_ok, after_ok = before['passed'] == before['total'], after['passed'] == after['total']
            outcome = ('pass_to_pass' if before_ok and after_ok else 'fail_to_pass' if after_ok else
                       'pass_to_fail' if before_ok else 'fail_to_fail')
            old_failures = {s['case']: s['group'] for s in before['failed_scenarios']}
            new_failures = {s['case']: s['group'] for s in after['failed_scenarios']}
            fixed = [{'case': n, 'group': old_failures[n]} for n in sorted(old_failures.keys() - new_failures.keys())]
            introduced = [{'case': n, 'group': new_failures[n]} for n in sorted(new_failures.keys() - old_failures.keys())]
        result = {'task': row['task'], 'architecture': row['architecture'], 'original_run': str(run.resolve()),
                  'checkpoints': checkpoints, 'readonly_review_same_source': True,
                  'readonly_review_same_grade': deterministic_review, 'original_final_reproduced': reproduced,
                  'evidence_complete': complete, 'transition': outcome,
                  'fixed_scenarios': fixed, 'introduced_scenarios': introduced,
                  'review': row['review'], 'executor_final_public_reply': row['executor_final_public_reply']}
        record['rows'].append(result)
        save_json(output / 'audit.json', record)
    for _, run, _, snapshots in inputs:
        if any(inventory(run / 'turns' / s / 'workspace') != snapshots[s] for s in STAGES):
            raise ValueError('Original snapshot changed during audit')
    if any(file_hash(path) != checksum for path, checksum in protected.items()):
        raise ValueError('Original run/report changed during audit')
    record['original_evidence_unchanged'] = True
    record['audit_consistent'] = all(r['evidence_complete'] and r['readonly_review_same_grade']
                                     and r['original_final_reproduced'] for r in record['rows'])
    record['status'] = 'completed' if record['audit_consistent'] else 'completed_with_inconsistencies'
    record['updated_at'] = now()
    record['architecture_transitions'] = {name: dict(Counter(r['transition'] for r in record['rows'] if r['architecture'] == name))
                                          for name in sorted({r['architecture'] for r in record['rows']})}
    save_json(output / 'audit.json', record)
    lines = ['# Plan 14：既有代码快照事后验收', '',
             '本地验收24份独立副本，0次模型调用；未向任何Agent回传结果，未修改原始实验记录。分析前已知最终成绩，不是独立留出评估。', '',
             f"状态：{record['status']}；原最终成绩与只读审查前后结果一致：{record['audit_consistent']}。", '',
             '| 任务 | 规划者 | 实施后 | 审查后 | 修正后 | 变化 | 修复场景数 | 新增失败场景数 |',
             '|---|---|---:|---:|---:|---|---:|---:|']
    labels = {'pass_to_pass': '通过→通过', 'fail_to_pass': '失败→通过',
              'pass_to_fail': '通过→失败', 'fail_to_fail': '失败→失败', 'unresolved_evidence': '证据不足'}
    for r in record['rows']:
        scores = [f"{g['passed']}/{g['total']}" if (g := r['checkpoints'][s]['grade']) else '未取得有效验收' for s in STAGES]
        planner = 'Sol' if r['architecture'] == 'sol-luna-sol-review' else 'Luna'
        lines.append(f"| {r['task']} | {planner} | {' | '.join(scores)} | {labels[r['transition']]} | {len(r['fixed_scenarios'])} | {len(r['introduced_scenarios'])} |")
    lines += ['', '审查阶段只读，其分数用于核对一致性，不作为Reviewer独立解题成绩。失败场景按同一验收器中的固定编号比较，不将场景数量当独立任务样本。', '',
              '修正前后发生变化可定位到Executor改动阶段，但不能仅据此证明Reviewer是必要原因；额外修正轮也可能产生自发修改。审查建议是否正确，仍需结合具体意见与代码差异。', '',
              '最终快照重新验收只用于复现和诊断，不替换原报告，不增加模型重复次数。超时或缺少完成凭证归为证据不足，不能当模型答错。', '',
              '各阶段完整日志、完成凭证与源码副本在runs目录；逐场景修复／新增失败、原始审查与Executor答复见audit.json。']
    (output / 'audit.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'status': record['status'], 'audit_consistent': record['audit_consistent'],
                      'transitions': record['architecture_transitions'], 'generation_requests': 0}, ensure_ascii=True))
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit(args.batch.resolve(), args.output.resolve())
