"""Read a single authorized recovery alongside the preserved original attempts."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
from summarize_architecture_comparison import summarize as extract
from summarize_architecture_repeats import totals


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def summarize(directory):
    record = read(directory / 'recovery.json')
    original = Path(record['original_batch'])
    previous = read(original / 'architecture-repeat-comparison.json')
    batch_dir = Path(record['output'])
    batch = read(batch_dir / 'batch.json')
    assert batch['status'] != 'running' and not batch['inflight']
    assert len(batch['completed']) == 1
    old_config = read(original / 'batch.json')['configuration']
    config = batch['configuration']
    for key in ('workflow', 'framework_fingerprint', 'limits', 'permission_policy', 'opencode_version'):
        assert config[key] == old_config[key], key
    aid = 'sol-handoff-luna'
    assert config['architectures'] == [next(a for a in old_config['architectures'] if a['id'] == aid)]
    for key in ('role_prompts', 'agent_ids'):
        assert config[key] == {aid: old_config[key][aid]}, key
    assert config['task_fingerprints'] == {'python-cachetools-atomic-update': old_config['task_fingerprints']['python-cachetools-atomic-update']}
    recovered = extract(batch_dir, rows_only=True)[0]
    recovered = {**recovered, 'actual_recovery_cell': recovered['cell'],
                 'cell': record['original_cell'], 'repeat': 1, 'overall_trial': record['overall_trial'],
                 'origin': 'user-authorized-interruption-replacement', 'batch': str(batch_dir)}
    old = next(r for r in previous['rows'] if r['cell'] == record['original_cell'] and r['origin'] == 'replication')
    assert old['category'] == 'incomplete_or_environment' and not old['final_evidence']
    assert recovered['task'] == old['task'] and recovered['architecture'] == old['architecture']
    rows = [recovered if r is old else r for r in previous['rows']]
    assert len(rows) == len({(r['task'], r['architecture'], r['overall_trial']) for r in rows}) == 36
    attempts = previous['rows'] + [recovered]
    assert len(attempts) == 37
    selections = 0
    for row in attempts:
        folder = Path(row['batch']) / Path(row['result_path']).parent
        task = read(folder / 'task.json')
        for name in task['editable_files']:
            assert (folder / 'baseline' / name).read_bytes() == (folder / 'turns/00-plan/workspace' / name).read_bytes()
        assert row['child_sessions'] == []
        if row['category'] != 'incomplete_or_environment':
            assert row['turns_completed'] == 4 and row['final_evidence'].get('completion_verified') and row['final_evidence'].get('ok')
        if row['strategy'] == 'planner_handoff':
            choices = row['verified_selections']
            assert len(choices) == (4 if row['category'] != 'incomplete_or_environment' else len(row['turns']))
            assert [c['role'] for c in choices] == ['planner', 'worker', 'worker', 'worker'][:len(choices)]
            assert len({c['session_id'] for c in choices}) == 1
            for i, choice in enumerate(choices):
                model = 'gpt-6.1-sol' if i == 0 else 'gpt-6-luna'
                assert choice['passed'] and choice['after']['model']['id'] == model
                assert choice['after']['agent'] == choice['expected_agent']
            selections += len(choices)
            events = [json.loads(line) for line in (folder / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
            for event in events:
                if event['type'] == 'request_started':
                    assert event['model_id'] == ('gpt-6.1-sol' if event['turn'] == 'plan' else 'gpt-6-luna')
                if event['type'] == 'tool' and event.get('tool') in {'write_file', 'edit_file'} and event['result'].get('ok'):
                    assert event['turn'] != 'plan' and event['role'] == 'worker'
    archs = ['sol-solo', 'luna-solo', 'sol-handoff-luna']
    combined = {a: totals([r for r in rows if r['architecture'] == a]) for a in archs}
    fresh = {a: totals([r for r in rows if r['architecture'] == a and r['overall_trial'] != 1]) for a in archs}
    all_costs = {a: totals([r for r in attempts if r['architecture'] == a]) for a in archs}
    new_cost = Decimal(recovered['accounting']['estimated_cost_usd'])
    repeat_known = Decimal(record['previous_known_cost_usd']) + new_cost
    reserve = Decimal(record['previous_unknown_reserve_usd']) + Decimal(recovered['accounting'].get('unknown_cost_reserve_usd', '0'))
    assert repeat_known + reserve <= Decimal(record['global_budget_usd'])
    valid = sum(r['category'] != 'incomplete_or_environment' for r in rows)
    summary = {'schema_version': 1, 'quality_complete': valid == 36, 'quality_slots': 36,
               'valid_final_grades': valid, 'attempts_including_interruption': 37,
               'original_interrupted_attempt': old, 'replacement': recovered,
               'combined_quality_totals': combined, 'new_quality_totals': fresh,
               'all_attempt_accounting': all_costs, 'repeat_known_cost_usd': str(repeat_known),
               'recovery_known_cost_usd': str(new_cost), 'unknown_cost_reserve_usd': str(reserve),
               'combined_known_cost_usd': str(sum((Decimal(t['known_cost_usd']) for t in all_costs.values()), Decimal(0))),
               'all_usage_complete': all(r['accounting']['usage_complete'] for r in attempts),
               'handoff_verified_selections_all_attempts': selections,
               'configuration_and_role_evidence_verified': True, 'global_budget_usd': record['global_budget_usd'],
               'rows': rows, 'original_report': str(original / 'architecture-repeat-comparison.json'),
               'limitations': ['Four correlated development tasks; three valid trials do not establish a global ranking.',
                               'Replacement follows a user-reported network interruption in a later time window.',
                               'Old interrupted attempt remains in cost totals and audit trail, not an extra quality observation.',
                               'Unknown cost reserve is not measured spending; estimates are not account invoices.']}
    lines = ['# 架构重复实验：网络中断后补跑', '',
             f'固定质量位置36项，已取得{valid}项有效最终验收。原中断记录保留；补跑仅替代其缺失质量位置，不增加独立重复次数。共37次尝试记录。', '',
             '| 结构 | 含首轮全通过／有效验收 | 仅新增全通过／有效验收 | 全部尝试已知估算 USD | 未知预留 USD |',
             '|---|---:|---:|---:|---:|']
    for a in archs:
        t, f, c = combined[a], fresh[a], all_costs[a]
        lines.append(f"| {a} | {t['accepted']}/{t['accepted'] + t['acceptance_failed']} | {f['accepted']}/{f['accepted'] + f['acceptance_failed']} | {c['known_cost_usd']} | {c['unknown_cost_reserve_usd']} |")
    lines += ['', '| 任务 | Sol 单体全通过 | Luna 单体全通过 | Sol→Luna 全通过 |', '|---|---:|---:|---:|']
    for task in old_config['task_fingerprints']:
        values = []
        for a in archs:
            items = [r for r in rows if r['task'] == task and r['architecture'] == a]
            values.append(f"{sum(r['accepted'] for r in items)}/{sum(r['category'] != 'incomplete_or_environment' for r in items)}")
        lines.append(f"| {task} | {' | '.join(values)} |")
    lines += ['', f"补跑结果：{recovered['category']}，{recovered['scenarios_passed']}/{recovered['scenarios_graded']}，已知估算 ${new_cost}。", '',
              f'原重复批次加本次补跑已知 ${repeat_known}，未知预留 ${reserve}，仍共用原 ${record["global_budget_usd"]} 预算。含架构首轮已知 ${summary["combined_known_cost_usd"]}。', '',
              '全费用包含失败及旧中断的已知部分；未知预留仍保留，不能称费用完整。中断不算模型解题失败；补跑使用原始源码、新会话、相同模型档位／角色／任务／工作流，不接收先前隐藏反馈。', '',
              '首轮交接的质量收益没有稳定复现，不能将较低费用称为保持质量的省钱。样本小、任务相关且没有独立留出评估，结论仅适用于本组配置和任务。', '',
              f'全部尝试中交接角色选择已验证{selections}次；规划可编辑源码未变、实施写入属于worker、子会话为空。原始报告不覆盖，完整逐项记录见同目录JSON。']
    (directory / 'architecture-recovery-comparison.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (directory / 'architecture-recovery-comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('quality_complete', 'valid_final_grades', 'recovery_known_cost_usd', 'repeat_known_cost_usd', 'unknown_cost_reserve_usd', 'combined_quality_totals')}, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    summarize(parser.parse_args().directory.resolve())
