"""Compare frozen single-agent batches without model calls or new grading."""
import argparse
from decimal import Decimal
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def compare(inputs, output):
    if output.exists():
        raise ValueError("Preserve existing evidence; use a new output directory")
    batches = [read(path / "batch.json") for path in inputs]
    summaries = [read(path / "comparison.json") for path in inputs]
    base = batches[0]["configuration"]
    rows, totals, seen = [], {}, set()
    for directory, batch, summary in zip(inputs, batches, summaries):
        if batch["status"] != "completed" or batch["inflight"]:
            raise ValueError("Only completed batches may enter this comparison")
        config = batch["configuration"]
        for key in ("workflow", "task_fingerprints", "framework_fingerprint", "limits", "permission_policy", "opencode_version"):
            if config[key] != base[key]:
                raise ValueError("Incompatible frozen setting: " + key)
        for key in ("role_prompts", "agent_ids"):
            normalize = lambda value: {json.dumps(item, sort_keys=True) for item in value.values()}
            if normalize(config[key]) != normalize(base[key]):
                raise ValueError("Incompatible frozen setting: " + key)
        if any(architecture["strategy"] != "single_agent" for architecture in config["architectures"]):
            raise ValueError("This report is for single-agent baselines")
        if summary["recorded"] != summary["planned"] or not summary["all_usage_complete"]:
            raise ValueError("Comparison requires all planned records and complete usage")
        for row in summary["rows"]:
            identity = row["task"], row["model"]
            if identity in seen:
                raise ValueError("Duplicate model/task result; do not select the best trial")
            seen.add(identity)
            if row["turns_completed"] != 4 or not row["final_evidence"].get("completion_verified"):
                raise ValueError("Baseline run did not finish all four turns and trusted final grading")
            rows.append({**row, "batch": str(directory.resolve())})
        if set(totals) & set(summary["model_totals"]):
            raise ValueError("Repeated model needs an explicit repeat-analysis protocol")
        totals.update(summary["model_totals"])
    models = list(totals)
    tasks = sorted(base["task_fingerprints"])
    lookup = {(row["task"], row["model"]): row for row in rows}
    if any((task, model) not in lookup for task in tasks for model in models):
        raise ValueError("Missing paired baseline cell")
    score = lambda row: f"{row['scenarios_passed']}/{row['scenarios_graded']}"
    comparison = {"schema_version": 1, "inputs": [str(path.resolve()) for path in inputs],
                  "task_count": len(tasks), "model_count": len(models), "records": len(rows),
                  "same_workflow_tasks_framework_limits_and_permissions": True,
                  "batch_budgets_usd": [batch["configuration"]["batch_budget_usd"] for batch in batches],
                  "all_usage_complete": True, "model_totals": totals, "rows": rows,
                  "known_estimated_cost_usd": str(sum((Decimal(total["estimated_cost_usd"]) for total in totals.values()), Decimal(0))),
                  "limitations": ["One independent trial per model/task, not stable success probabilities.",
                                  "Nine tasks contain overlapping focused/integrated contracts from three libraries.",
                                  "Models ran in separate chronological batches, not fully interleaved.",
                                  "Batch dollar caps differ; report resource stops separately if any.",
                                  "Frozen standard prices include DeepSeek peak estimates; not account invoices.",
                                  "No architecture trials, key-task repeats, or independent holdout are included."]}
    lines = ["# 三模型单体工程任务基线", "",
             "任务、四轮提示、工具、权限、运行器及本地额度策略的冻结配置一致；每模型每题一次，不调参或付费重跑。", "",
             "| 模型 | 全通过 | 最终验收失败 | 未完成／环境 | 调用 | 累计 Token | 估算 USD | 秒 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for model, total in totals.items():
        lines.append(f"| {model} | {total['accepted']}/{total['attempted']} | {total['acceptance_failed']} | {total['incomplete_or_environment']} | {total['calls']} | {total['total_tokens']} | {total['estimated_cost_usd']} | {total['duration_seconds']} |")
    lines += ["", "| 任务 | " + " | ".join(models) + " |", "|---|" + "---:|" * len(models)]
    for task in tasks:
        lines.append("| " + task + " | " + " | ".join(score(lookup[task, model]) for model in models) + " |")
    different = [task for task in tasks if len({lookup[task, model]["accepted"] for model in models}) > 1]
    lines += ["", f"本轮有 {len(different)} 道任务出现最终全通过状态差异；不能按独立项目或独立缺陷计数。", "",
              "## 解释边界", "",
              "这是当前模型配置的首轮数据，不是显著性检验或稳定排名。专项和组合需求重叠，不能将组合题当作未见过的独立评估集。高级模型通过率较高时，只支持继续做重复与架构对照，不直接证明高级规划者能让便宜执行者达到相同质量。", "",
              "比较了两个先后批次：廉价模型批次费用上限 $2，Sol 批次 $5；若都未触发费用停止，仍须保留这项配置差异。模型推理档位、真实缓存命中和执行顺序不同，不能把全部成本差异只归于单价。", "",
              "费用包含失败运行。低价失败不能当作等质量省钱；估算使用各批冻结费率，DeepSeek 为峰值估算，不是实际账单。", "",
              "后续先固定关键题、独立重复到每模型累计三次，再决定冻结任务上的单体与规划后交接对照。独立留出集仍未建立。", "",
              "## 原始证据", ""]
    for directory in inputs:
        lines.append(f"- {directory.resolve()}：comparison.json、batch.json，以及 runs/ 中的结果、调用、四轮快照和独立验收日志。")
    output.mkdir(parents=True)
    (output / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(rows), "task_count": len(tasks), "model_totals": totals,
                     "known_estimated_cost_usd": comparison["known_estimated_cost_usd"]}, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    compare([path.resolve() for path in args.input], args.output.resolve())
