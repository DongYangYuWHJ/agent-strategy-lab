"""Read-only review architecture comparison; no model calls or regrading."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
from summarize_architecture_comparison import summarize as extract
from summarize_architecture_repeats import totals


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def public_reply(path):
    if not path.exists():
        return None
    messages = [m for m in read(path).get('data', [])
                if m.get('type') == 'assistant' and m.get('time', {}).get('completed')]
    if not messages:
        return None
    latest = max(messages, key=lambda m: m.get('time', {}).get('created', 0))
    return '\n'.join(p['text'] for p in latest.get('content', [])
                     if p.get('type') == 'text' and isinstance(p.get('text'), str))


def summarize(directory, preregistration):
    batch = read(directory / 'batch.json')
    if batch['status'] == 'running' or batch['inflight']:
        raise ValueError('Wait for the batch; do not overwrite incomplete reports')
    frozen = read(preregistration)
    config = batch['configuration']
    for key in ('architectures', 'workflow', 'role_prompts', 'limits', 'framework_fingerprint', 'task_fingerprints'):
        assert config[key] == frozen[key], key
    planned = frozen['planned_cells']
    assert len(config['plan']) == planned
    architectures = {a['id']: a for a in config['architectures']}
    phases = [t['id'] for t in config['workflow']['turns']]
    assert phases == ['plan', 'implement', 'review', 'revise']
    rows = extract(directory, rows_only=True)
    assert len({(r['task'], r['architecture'], r['repeat']) for r in rows}) == len(rows)
    for row in rows:
        run = directory / Path(row['result_path']).parent
        architecture = architectures[row['architecture']]
        events = [json.loads(line) for line in (run / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
        valid = row['category'] != 'incomplete_or_environment'
        if valid:
            assert row['turns_completed'] == 4 and row['final_evidence'].get('completion_verified')
        assert read(run / 'permission-audit.json')['passed'] or not valid
        task = read(run / 'task.json')
        issues = []
        for index in (0, 2):
            current = run / 'turns' / f'{index:02d}-{phases[index]}' / 'workspace'
            previous = run / 'baseline' if index == 0 else run / 'turns/01-implement/workspace'
            if not current.exists():
                continue
            for name in task['editable_files']:
                if (previous / name).read_bytes() != (current / name).read_bytes():
                    issues.append(f'{phases[index]} changed {name}')
        assert not issues, issues
        writes = [e for e in events if e['type'] == 'tool' and e.get('tool') in {'write_file', 'edit_file'}
                  and e['result'].get('ok')]
        assert all(e['turn'] in {'implement', 'revise'} for e in writes)
        phase_data = {}
        schedule = ([('planner', 0), ('worker', 1), ('reviewer', 2), ('worker', 1)]
                    if row['strategy'] == 'planner_executor_reviewer' else
                    [('planner', 0), ('worker', 1), ('worker', 1), ('worker', 1)]
                    if row['strategy'] == 'planner_handoff' else [('solo', 0)] * 4)
        for phase, (role, model_index) in zip(phases, schedule):
            started = [e for e in events if e['type'] == 'request_started' and e['turn'] == phase]
            charged = [e for e in events if e['type'] == 'request_completed' and e['turn'] == phase]
            assert all(e['model_id'] == architecture['models'][model_index] for e in started)
            if role != 'solo':
                assert all(e['primary_role'] == role for e in started)
            phase_data[phase] = {'role': role, 'model': architecture['models'][model_index],
                'calls': len(started), 'unmatched_requests': len(started) - len(charged),
                'known_cost_usd': str(sum((Decimal(e['estimated_cost_usd']) for e in charged), Decimal(0)))}
        assert sum(Decimal(p['known_cost_usd']) for p in phase_data.values()) == Decimal(row['accounting']['estimated_cost_usd'])
        if row['strategy'] in {'planner_handoff', 'planner_executor_reviewer'}:
            selections = row['verified_selections']
            if valid:
                assert len(selections) == 4 and all(s['passed'] for s in selections)
            if selections:
                assert len({s['session_id'] for s in selections}) == 1
                for selection, (role, model_index) in zip(selections, schedule):
                    if selection['passed']:
                        assert selection['role'] == role
                        assert selection['after']['model']['id'] == architecture['models'][model_index]
                        assert selection['after']['agent'] == selection['expected_agent']
            assert all(e['role'] == 'worker' for e in writes)
        assert row['child_sessions'] == [] or not valid
        row['phase_accounting'] = phase_data
        row['readonly_snapshots_verified'] = not issues
        row['review'] = read(run / 'review.json') if (run / 'review.json').exists() else None
        row['executor_final_public_reply'] = public_reply(run / 'turns/03-revise/messages.json')
        changed = []
        before, after = run / 'turns/01-implement/workspace', run / 'turns/03-revise/workspace'
        if before.exists() and after.exists():
            changed = [name for name in task['editable_files'] if (before / name).read_bytes() != (after / name).read_bytes()]
        row['files_changed_after_review'] = changed
        if valid and row['strategy'] == 'planner_executor_reviewer':
            assert row['review'] and row['review']['text'].strip()
    grouped = {name: totals([r for r in rows if r['architecture'] == name]) for name in architectures}
    phase_totals = {name: {phase: {
        'known_cost_usd': str(sum((Decimal(r['phase_accounting'][phase]['known_cost_usd'])
                                 for r in rows if r['architecture'] == name), Decimal(0))),
        'calls': sum(r['phase_accounting'][phase]['calls'] for r in rows if r['architecture'] == name)}
                          for phase in phases} for name in architectures}
    known = sum((Decimal(t['known_cost_usd']) for t in grouped.values()), Decimal(0))
    reserve = sum((Decimal(t['unknown_cost_reserve_usd']) for t in grouped.values()), Decimal(0))
    summary = {'schema_version': 1, 'status': batch['status'], 'planned': planned, 'recorded': len(rows),
               'complete': batch['status'] == 'completed' and len(rows) == planned,
               'valid_final_grades': sum(r['category'] != 'incomplete_or_environment' for r in rows),
               'all_usage_complete': all(r['accounting']['usage_complete'] for r in rows),
               'known_cost_usd': str(known), 'unknown_cost_reserve_usd': str(reserve),
               'budget_usd': config['batch_budget_usd'], 'architecture_totals': grouped,
               'phase_totals': phase_totals, 'rows': rows,
               'preregistration': str(preregistration.resolve()),
               'limitations': ['One run per architecture/task; four correlated development tasks.',
                               'New workflow prompts shared by all four groups; historical batches not pooled.',
                               'Review text and code changes are observations, not proof of causal repair.',
                               'Costs include failed attempts; unknown usage remains separate; not invoices.',
                               'Final hidden feedback never returned to models; no automatic paid retries.']}
    lines = ['# Plan 14：审查架构正式对照', '',
             f"状态 {batch['status']}，记录 {len(rows)}/{planned} 项，有效最终验收 {summary['valid_final_grades']} 项。每题×每架构一次，没有调参或自动重跑。", '',
             '| 结构 | 全通过／有效验收 | 环境／未完成 | API | Token | 估算 USD | 未知预留 USD | 累计秒 |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name, t in grouped.items():
        lines.append(f"| {name} | {t['accepted']}/{t['accepted'] + t['acceptance_failed']} | {t['incomplete_or_environment']} | {t['calls']} | {t['total_tokens']} | {t['known_cost_usd']} | {t['unknown_cost_reserve_usd']} | {t['duration_seconds']} |")
    lines += ['', '| 任务 | ' + ' | '.join(architectures) + ' |', '|---|' + '---|' * len(architectures)]
    for task in config['task_fingerprints']:
        values = []
        for name in architectures:
            row = next((r for r in rows if r['task'] == task and r['architecture'] == name), None)
            values.append('未运行' if row is None else
                          f"{row['scenarios_passed']}/{row['scenarios_graded']}；${row['accounting']['estimated_cost_usd']}" if row['groups'] else row['stop_reason'])
        lines.append('| ' + task + ' | ' + ' | '.join(values) + ' |')
    lines += ['', '## 分阶段费用与调用', '', '| 结构 | 规划 USD／调用 | 实施 USD／调用 | 审查 USD／调用 | 修正交付 USD／调用 |', '|---|---:|---:|---:|---:|']
    for name, phases_data in phase_totals.items():
        lines.append('| ' + name + ' | ' + ' | '.join(f"{p['known_cost_usd']} / {p['calls']}" for p in phases_data.values()) + ' |')
    lines += ['', '## 新架构审查与修正记录', '']
    for row in rows:
        if row['strategy'] != 'planner_executor_reviewer':
            continue
        run = Path(row['result_path']).parent
        review_path = (run / 'review.json').as_posix()
        changes = ', '.join(row['files_changed_after_review']) or ('无修改' if row['turns_completed'] == 4 else '尚未完成')
        lines += [f"- {row['task']}：{row['category']}；审查后改变的文件：{changes}；[可见审查]({review_path})。"]
    lines += ['', f'已知合计 ${known}，未知预留 ${reserve}，本批预算 ${config["batch_budget_usd"]}。失败和中断的已知费用均保留，未知预留不是实际账单。', '',
              '所有组共用四轮提示、任务、各模型档位、工具与最终验收。各组实际模型分配见逐项JSON和冻结配置：三角色模型列表依次为Planner、Executor、Reviewer，最后修正仍由Executor负责；单体全程同一模型。规划及审查阶段只读。', '',
              '审查意见只读自可见回复，不提取reasoning。代码是否改变与最终是否通过分别记录；没有重新给实施快照执行隐藏评分，不能仅凭最终成功声称Reviewer修好了某个错误。', '',
              '四个相关开发任务、每格一次，只能作为探索；不与历史批次或小任务报告混合分母。需结合冻结的角色指令与模型分配解释差异；若两组仅Planner模型不同，也仍有生成路径和缓存波动。完整角色／模型选择、源码快照与费用分解保存在同目录JSON及runs原始记录。']
    (directory / 'review-comparison.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (directory / 'review-comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('complete', 'recorded', 'valid_final_grades', 'known_cost_usd', 'unknown_cost_reserve_usd', 'architecture_totals')}, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--preregistration', type=Path, required=True)
    args = parser.parse_args()
    summarize(args.directory.resolve(), args.preregistration.resolve())
