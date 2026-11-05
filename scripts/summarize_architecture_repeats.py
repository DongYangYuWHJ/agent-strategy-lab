"""Combine predeclared architecture replications with their first trial; read-only."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
from statistics import median
from summarize_architecture_comparison import summarize as extract


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def totals(items):
    return {"recorded": len(items), "accepted": sum(row["accepted"] for row in items),
            "acceptance_failed": sum(row["category"] == "acceptance_failed" for row in items),
            "incomplete_or_environment": sum(row["category"] == "incomplete_or_environment" for row in items),
            "known_cost_usd": str(sum((Decimal(row["accounting"]["estimated_cost_usd"]) for row in items), Decimal(0))),
            "unknown_cost_reserve_usd": str(sum((Decimal(row["accounting"].get("unknown_cost_reserve_usd", "0")) for row in items), Decimal(0))),
            "unknown_calls": sum(row["accounting"].get("unknown_calls", 0) for row in items),
            "plan_cost_usd": str(sum((Decimal(row["plan_cost_usd"]) for row in items), Decimal(0))),
            "later_cost_usd": str(sum((Decimal(row["later_cost_usd"]) for row in items), Decimal(0))),
            "calls": sum(row["accounting"]["calls"] for row in items),
            "total_tokens": sum(row["accounting"]["total_tokens"] for row in items),
            "duration_seconds": str(sum((Decimal(str(row["duration_seconds"])) for row in items), Decimal(0))),
            "usage_complete": all(row["accounting"]["usage_complete"] for row in items)}


def summarize(directory, prereg_path):
    registration = read(prereg_path)
    batch = read(directory / "batch.json")
    if batch["status"] == "running" or batch["inflight"]:
        raise ValueError("Batch still running; do not declare partial results complete")
    base_dir = Path(registration["baseline_batch"]).resolve()
    baseline = read(base_dir / "architecture-comparison.json")
    config, first_config = batch["configuration"], read(base_dir / "batch.json")["configuration"]
    for key in ("workflow", "task_fingerprints", "framework_fingerprint", "limits", "role_prompts", "agent_ids", "permission_policy", "opencode_version", "architectures"):
        if config[key] != first_config[key]:
            raise ValueError("Frozen setting changed: " + key)
    if config["task_fingerprints"] != registration["task_fingerprints"] or len(config["plan"]) != 24:
        raise ValueError("Replication differs from preregistration")
    rows = [{**row, "overall_trial": 1, "origin": "first-trial", "batch": str(base_dir)} for row in baseline["rows"]]
    new_rows = [{**row, "overall_trial": registration["local_repeat_to_overall_trial"][str(row["repeat"])],
                 "origin": "replication", "batch": str(directory.resolve())} for row in extract(directory, rows_only=True)]
    rows.extend(new_rows)
    lookup = {(row["task"], row["architecture"], row["overall_trial"]): row for row in rows}
    if len(lookup) != len(rows):
        raise ValueError("Duplicate trial; never select or overwrite results")
    complete = batch["status"] == "completed" and len(new_rows) == 24
    if complete and len(rows) != 36:
        raise ValueError("Expected 36 observations including first trial")
    tasks = list(config["task_fingerprints"])
    architectures = [item["id"] for item in config["architectures"]]
    combined = {name: totals([row for row in rows if row["architecture"] == name]) for name in architectures}
    fresh = {name: totals([row for row in new_rows if row["architecture"] == name]) for name in architectures}
    pairs, rounds = [], []
    for task in tasks:
        for name in architectures:
            items = sorted([row for row in rows if row["task"] == task and row["architecture"] == name], key=lambda row: row["overall_trial"])
            known = [row for row in items if row["accounting"]["usage_complete"] and row["category"] != "incomplete_or_environment"]
            prices = [Decimal(row["accounting"]["estimated_cost_usd"]) for row in known]
            pairs.append({"task": task, "architecture": name, **totals(items),
                          "cost_range": {"min": str(min(prices)), "median": str(median(prices)), "max": str(max(prices))} if prices else None,
                          "trial_results": [{"trial": row["overall_trial"], "category": row["category"], "accepted": row["accepted"],
                                             "score": [row["scenarios_passed"], row["scenarios_graded"]],
                                             "known_cost_usd": row["accounting"]["estimated_cost_usd"]} for row in items]})
    for trial in (1, 2, 3):
        by_arch = {name: totals([row for row in rows if row["architecture"] == name and row["overall_trial"] == trial]) for name in architectures}
        sol, handoff = by_arch["sol-solo"], by_arch["sol-handoff-luna"]
        all_pairs = all((task, name, trial) in lookup for task in tasks for name in architectures)
        same_scores = all_pairs and all(lookup[task, "sol-solo", trial]["scenarios_passed"] == lookup[task, "sol-handoff-luna", trial]["scenarios_passed"]
                                       and lookup[task, "sol-solo", trial]["scenarios_graded"] == lookup[task, "sol-handoff-luna", trial]["scenarios_graded"]
                                       and lookup[task, "sol-solo", trial]["final_evidence"].get("completion_verified")
                                       and lookup[task, "sol-handoff-luna", trial]["final_evidence"].get("completion_verified") for task in tasks)
        rounds.append({"trial": trial, "architecture_totals": by_arch, "all_task_scores_match_sol_handoff": bool(same_scores),
                       "handoff_cost_reduction_fraction_vs_sol": str(1 - Decimal(handoff["known_cost_usd"]) / Decimal(sol["known_cost_usd"]))
                       if Decimal(sol["known_cost_usd"]) and sol["usage_complete"] and handoff["usage_complete"] else None})
    summary = {"schema_version": 1, "status": batch["status"], "complete": complete,
               "new_planned": 24, "new_recorded": len(new_rows), "combined_recorded": len(rows),
               "all_planned_attempts_recorded": len(new_rows) == 24,
               "new_valid_final_grades": sum(row["category"] != "incomplete_or_environment" for row in new_rows),
               "combined_valid_final_grades": sum(row["category"] != "incomplete_or_environment" for row in rows),
               "all_usage_complete": all(row["accounting"]["usage_complete"] for row in rows),
               "new_known_cost_usd": str(sum((Decimal(row["accounting"]["estimated_cost_usd"]) for row in new_rows), Decimal(0))),
               "combined_known_cost_usd": str(sum((Decimal(row["accounting"]["estimated_cost_usd"]) for row in rows), Decimal(0))),
               "unknown_cost_reserve_usd": str(sum((Decimal(row["accounting"].get("unknown_cost_reserve_usd", "0")) for row in rows), Decimal(0))),
               "unknown_calls": sum(row["accounting"].get("unknown_calls", 0) for row in rows),
               "combined_architecture_totals": combined, "new_architecture_totals": fresh,
               "pairs": pairs, "rounds": rounds, "rows": rows,
               "preregistration": str(prereg_path.resolve()), "baseline_batch": str(base_dir),
               "limitations": ["Three trials per task/architecture, four correlated development tasks, not a stable or global ranking.",
                               "First trial is in a prior batch; new repetitions are shuffled in one batch, not chronological round blocks.",
                               "Role prompts and model allocation jointly define the architecture; not a model-only ablation.",
                               "All cost totals include failed attempts; lower cost with worse task quality is not equal-quality savings.",
                               "Frozen API rates and actual caches, not account invoices; time variation includes provider and local overhead."]}
    lines = ["# Sol／Luna 架构重复验证", "", f"状态 {batch['status']}；新增 {len(new_rows)}/24 项，含首轮共 {len(rows)}/36 项。", "",
             f"新增有效最终验收 {summary['new_valid_final_grades']} 项；含首轮有效验收 {summary['combined_valid_final_grades']} 项。异常缺失不记为模型验收失败。", "",
             "原首轮为第1次，本批 repeat=0/1 为第2/3次；编号预先分配，随机执行顺序不按轮次递增。各次从原始源码和新会话开始，失败保留，不调参或追加最好一次。", ""]
    for title, group in [("含首轮三次", combined), ("仅本次新增两次", fresh)]:
        lines += ["## " + title, "", "| 结构 | 全通过／有效验收 | 验收失败 | 未完成／环境 | API | 累计 Token | 规划 USD | 后续 USD | 总已知估算 USD | 秒 |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for name, total in group.items():
            valid = total["accepted"] + total["acceptance_failed"]
            lines.append(f"| {name} | {total['accepted']}/{valid} | {total['acceptance_failed']} | {total['incomplete_or_environment']} | {total['calls']} | {total['total_tokens']} | {total['plan_cost_usd']} | {total['later_cost_usd']} | {total['known_cost_usd']} | {total['duration_seconds']} |")
        lines += [""]
    lines += ["## 每题三次", "", "| 任务 | 结构 | 第1次 | 第2次 | 第3次 | 全通过／有效验收 | 费用最小／中位／最大 USD |", "|---|---|---|---|---|---:|---|"]
    for pair in pairs:
        cells = []
        for trial in (1, 2, 3):
            row = lookup.get((pair["task"], pair["architecture"], trial))
            cells.append("未运行" if row is None else f"{row['scenarios_passed']}/{row['scenarios_graded']}" if row["groups"] else row["stop_reason"])
        span = pair["cost_range"]
        price = "未记录完整用量" if span is None else f"{span['min']} / {span['median']} / {span['max']}"
        lines.append(f"| {pair['task']} | {pair['architecture']} | {' | '.join(cells)} | {pair['accepted']}/{pair['accepted'] + pair['acceptance_failed']} | {price} |")
    lines += ["", "## 分轮次的费用与质量", "", "| 预分配轮次 | Sol 全通过 | Luna 全通过 | 交接全通过 | Sol与交接逐题分数一致 | 交接费用相对Sol下降比例 |", "|---|---:|---:|---:|---|---:|"]
    for item in rounds:
        t = item["architecture_totals"]
        reduction = item["handoff_cost_reduction_fraction_vs_sol"]
        pct = "用量不完整" if reduction is None else f"{Decimal(reduction) * 100:.1f}%"
        lines.append(f"| {item['trial']} | {t['sol-solo']['accepted']}/{t['sol-solo']['recorded']} | {t['luna-solo']['accepted']}/{t['luna-solo']['recorded']} | {t['sol-handoff-luna']['accepted']}/{t['sol-handoff-luna']['recorded']} | {item['all_task_scores_match_sol_handoff']} | {pct} |")
    lines += ["", f"本次新增已知估算 ${summary['new_known_cost_usd']}；含首轮共 ${summary['combined_known_cost_usd']}；用量{'完整' if summary['all_usage_complete'] else '有未知部分，不能当作完整费用'}。", "",
              "费用下降比例本身不证明相同质量：逐题质量未保持时，只能作为成本与交付情况的取舍。相同总通过数也可能来自不同任务，必须结合每题记录。", "",
              f"未知用量请求 {summary['unknown_calls']} 条，保留费用预留 ${summary['unknown_cost_reserve_usd']}，不记为零，也不作为实际账单。未完成项不算验收失败，不纳入完整运行的费用范围；总已知费用保留其中已发生部分。", "",
              "交接组实际模型、同会话选择、规划禁写和子会话证据见 architecture-repeat-comparison.json 的逐项数据与 runs/ 原始文件。费用包含失败；重复并未添加已知失败点或隐藏反馈，也没有让 Sol 在交接后回到会话。", "",
              "样本为四个相关开发任务，每格三次，不能据此宣称统计显著、全局最优或普遍省钱。首轮和新增批次的时段、缓存与服务延迟不同；历史 DeepSeek 及其他单体批次未混入本报告分母。汇总只读取保存记录，不调用模型或重新执行隐藏验收。"]
    (directory / "architecture-repeat-comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (directory / "architecture-repeat-comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("complete", "new_recorded", "combined_recorded", "new_known_cost_usd", "combined_architecture_totals", "new_architecture_totals")}, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--preregistration", type=Path, required=True)
    args = parser.parse_args()
    summarize(args.directory.resolve(), args.preregistration.resolve())
