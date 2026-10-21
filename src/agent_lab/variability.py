"""Offline within-task variation analysis, using only frozen batch data."""
from collections import Counter
from decimal import Decimal
from pathlib import Path
import statistics
from .accounting import usage_cost
from .domain import Pricing, Usage, read_json, save_json
from .reporting import collect_results


def distribution(values):
    if not values:
        return None
    samples = [Decimal(str(value)) for value in values]
    low, high = min(samples), max(samples)
    median, mean = statistics.median(samples), statistics.mean(samples)
    deviation = statistics.stdev(samples) if len(samples) > 1 else None
    return {"n": len(samples), "minimum": str(low), "median": str(median), "maximum": str(high),
            "mean": str(mean), "sample_stddev": str(deviation) if deviation is not None else None,
            "minimum_vs_median_pct": float((low / median - 1) * 100) if median else None,
            "maximum_vs_median_pct": float((high / median - 1) * 100) if median else None,
            "maximum_over_minimum": float(high / low) if low else None,
            "coefficient_of_variation_pct": float(deviation / mean * 100) if deviation is not None and mean else None}


def build_variance_report(manifest, results):
    configuration = manifest["configuration"]
    models = {model["id"]: model for model in configuration["models"]}
    planned = Counter((cell["task"], cell["model"]) for cell in configuration["plan"])
    cells = {run_id: cell for cell, run_id in manifest["completed"].items()}
    by_cell = {cell["cell"]: cell for cell in configuration["plan"]}
    rows = []
    for result in sorted(results, key=lambda value: value.get("started_at", "")):
        model = models[result["model_id"]]
        rates = Pricing(**model["pricing"])
        account = result["accounting"]
        complete = account["usage_complete"]
        usage = Usage(**account["usage"]) if complete and "usage" in account else None
        if usage is not None and usage_cost(usage, rates) != Decimal(account["estimated_cost_usd"]):
            raise ValueError("Recorded cost differs from usage and frozen rates")
        cell = by_cell.get(cells.get(result["run_id"], ""))
        rows.append({"run_id": result["run_id"], "task_id": result["task_id"], "model_id": result["model_id"],
                     "execution_kind": result["execution_kind"], "strategy": result["strategy"],
                     "repeat": cell["repeat"] + 1 if cell else None,
                     "started_at": result.get("started_at"), "accepted": result["accepted"],
                     "status": result["status"], "stop_reason": result["stop_reason"],
                     "calls": account["calls"], "tool_steps": account.get("tool_steps"),
                     "repairs": result["repairs"], "seconds": result["duration_seconds"],
                     "total_tokens": account["total_tokens"], "usage": account.get("usage"),
                     "cache_read_fraction": usage.cached_input_tokens / usage.input_tokens if usage and usage.input_tokens else None,
                     "cache_write_fraction": usage.cache_write_tokens / usage.input_tokens if usage and usage.input_tokens else None,
                     "known_estimated_cost_usd": account["estimated_cost_usd"],
                     "unknown_cost_reserve_usd": account["unknown_cost_reserve_usd"], "usage_complete": complete,
                     "all_input_uncached_reference_usd": str(usage_cost(Usage(usage.input_tokens, usage.output_tokens), rates)) if usage else None,
                     "artifact_dir": result["artifact_dir"]})
    groups = []
    for task, model_id in sorted(planned):
        group = [row for row in rows if row["task_id"] == task and row["model_id"] == model_id]
        complete = bool(group) and all(row["usage_complete"] for row in group)
        groups.append({"task_id": task, "model_id": model_id, "planned_runs": planned[(task, model_id)],
                       "observed_runs": len(group), "successes": sum(row["accepted"] for row in group),
                       "usage_complete": complete, "sample_complete": len(group) == planned[(task, model_id)],
                       "cost_usd": distribution([row["known_estimated_cost_usd"] for row in group]) if complete else None,
                       "uncached_reference_usd": distribution([row["all_input_uncached_reference_usd"] for row in group]) if complete and all(row["all_input_uncached_reference_usd"] is not None for row in group) else None,
                       "tokens": distribution([row["total_tokens"] for row in group]),
                       "calls": distribution([row["calls"] for row in group]),
                       "seconds": distribution([row["seconds"] for row in group]),
                       "stop_reasons": dict(Counter(row["stop_reason"] for row in group))})
    return {"schema_version": 1, "batch_status": manifest["status"], "batch_fingerprint": manifest["fingerprint"],
            "planned_runs": len(configuration["plan"]), "observed_runs": len(rows),
            "known_estimated_cost_usd": str(sum((Decimal(row["known_estimated_cost_usd"]) for row in rows), Decimal(0))),
            "unknown_cost_reserve_usd": str(sum((Decimal(row["unknown_cost_reserve_usd"]) for row in rows), Decimal(0))),
            "cost_basis": "Reported usage x frozen prices; DeepSeek uses peak rates; not an invoice",
            "method": "Fresh source and conversation per run; seeded shuffled order; cache behavior not controlled; failures included",
            "reference_note": "All input, including cache reads/writes, repriced at the uncached input rate; counterfactual, not an extra API run or bill",
            "limitation": "Small samples describe observed variation only; no population range or reliable tail quantiles; shared supplier cache means runs need not be independent",
            "groups": groups, "runs_in_order": rows}


def write_variance_report(root: Path):
    if not (root / "batch.json").is_file():
        raise ValueError("Cost variation analysis requires a batch directory with batch.json")
    report = build_variance_report(read_json(root / "batch.json"), collect_results(root))
    save_json(root / "variance.json", report)
    lines = ["# 单 Agent 费用浮动测试", "", "每次重置源码与对话，固定任务、工具、提示词、模型参数和价格；运行顺序按固定种子打乱。",
             "供应商缓存保持默认行为，不控制缓存冷暖；费用为用量乘以固定价格，DeepSeek 按峰时保守估算，不是实付账单。",
             "失败尝试包含在统计中。有未知费用时不计算该组费用波动。", "",
             "| 模型 / 任务 | 成功 / 已运行 / 计划 | 最低 USD | 中位 USD | 最高 USD | 相对中位数范围 | 最高 / 最低 | CV |",
             "|---|---:|---:|---:|---:|---|---:|---:|"]
    for group in report["groups"]:
        stats = group["cost_usd"]
        if stats:
            span = f"{stats['minimum_vs_median_pct']:+.1f}% ～ {stats['maximum_vs_median_pct']:+.1f}%" if stats["minimum_vs_median_pct"] is not None else "中位数为零"
            ratio = f"{stats['maximum_over_minimum']:.2f}×" if stats["maximum_over_minimum"] is not None else "最低为零"
            cv = f"{stats['coefficient_of_variation_pct']:.1f}%" if stats["coefficient_of_variation_pct"] is not None else "不足以计算"
            values = [f"{Decimal(stats[key]):.9f}" for key in ("minimum", "median", "maximum")]
        else:
            values, span, ratio, cv = ["费用不完整"] * 3, "—", "—", "—"
        lines.append(f"| {group['model_id']} / {group['task_id']} | {group['successes']} / {group['observed_runs']} / {group['planned_runs']} | {' | '.join(values)} | {span} | {ratio} | {cv} |")
    lines += ["", "CV = 样本标准差 ÷ 平均费用；相对中位数范围使用本次最低、最高值，不是置信区间。", "",
              f"已知合计估算费用：${report['known_estimated_cost_usd']}；未知费用预留：${report['unknown_cost_reserve_usd']}。", "",
              "## 排除缓存计价差异的参考", "", "按同次真实 Token 数，将全部输入按未缓存单价重算。这个反事实参考保持执行量不变，没有额外调用 API，不能视为实付费用。", "",
              "| 模型 / 任务 | 最低参考 USD | 中位参考 USD | 最高参考 USD | 相对中位数范围 |", "|---|---:|---:|---:|---|"]
    for group in report["groups"]:
        stats = group["uncached_reference_usd"]
        if stats:
            span = f"{stats['minimum_vs_median_pct']:+.1f}% ～ {stats['maximum_vs_median_pct']:+.1f}%" if stats["minimum_vs_median_pct"] is not None else "中位数为零"
            lines.append(f"| {group['model_id']} / {group['task_id']} | {Decimal(stats['minimum']):.9f} | {Decimal(stats['median']):.9f} | {Decimal(stats['maximum']):.9f} | {span} |")
    lines += ["", "## 按实际运行顺序的原始数值", "",
              "| 顺序 | 模型 | 重复编号 | 通过 | 调用 / 修复 | Token | 输入缓存读取比例 | 估算 USD | 未缓存参考 USD | 秒 |",
              "|---:|---|---:|---|---|---:|---:|---:|---:|---:|"]
    for index, row in enumerate(report["runs_in_order"], 1):
        cache = f"{row['cache_read_fraction']:.1%}" if row["cache_read_fraction"] is not None else "—"
        lines.append(f"| {index} | {row['model_id']} | {row['repeat']} | {'是' if row['accepted'] else '否'} | {row['calls']} / {row['repairs']} | {row['total_tokens']} | {cache} | {row['known_estimated_cost_usd']} | {row['all_input_uncached_reference_usd']} | {row['seconds']} |")
    lines += ["", "样本量较小，只描述该任务在此次配置与缓存环境下的观察结果，不能外推复杂任务，也不能估计稳定的 P90/P95 或总体波动范围。供应商缓存可能跨运行复用，重复运行不保证统计独立。", "",
              "完整数据：variance.json。原始请求、响应、工具、验收与补丁：runs/。", ""]
    (root / "variance.md").write_text("\n".join(lines), encoding="utf-8")
    return report
