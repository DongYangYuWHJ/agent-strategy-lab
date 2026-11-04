"""Combine predeclared repeat trials with first-round evidence; never generate or regrade."""
import argparse
from collections import defaultdict
from decimal import Decimal
from datetime import datetime
import json
from pathlib import Path
from statistics import median


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def money_stats(rows):
    complete = [row for row in rows if row["accounting"]["usage_complete"] and row["category"] != "incomplete_or_environment"]
    values = [Decimal(row["accounting"]["estimated_cost_usd"]) for row in complete]
    times = [Decimal(str(row["duration_seconds"])) for row in complete]
    return {"sum_usd": str(sum(values, Decimal(0))), "min_usd": str(min(values)),
            "median_usd": str(median(values)), "max_usd": str(max(values)),
            "min_seconds": str(min(times)), "median_seconds": str(median(times)), "max_seconds": str(max(times)),
            "usage_complete": all(row["accounting"]["usage_complete"] for row in rows),
            "excluded_incomplete_rows": len(rows) - len(complete)}


def summarize(directory, baseline_path, prereg_path, recovery_path=None):
    batch = read(directory / "batch.json")
    recovery = read(recovery_path) if recovery_path else None
    if recovery is None and (batch["status"] == "running" or batch["inflight"]):
        raise ValueError("Wait for the running batch; do not grade or declare partial data complete")
    if recovery is not None:
        if recovery["status"] != "completed_pending_only" or Path(recovery["original_batch"]).resolve() != directory:
            raise ValueError("Recovery is unfinished or references a different original batch")
    prereg, baseline = read(prereg_path), read(baseline_path)
    tasks, models = prereg["tasks"], prereg["models"]
    config = batch["configuration"]
    if set(config["task_fingerprints"]) != set(tasks):
        raise ValueError("Task selection differs from preregistration")
    if config["task_fingerprints"] != prereg["task_fingerprints"] or len(config["plan"]) != prereg["new_cells"]:
        raise ValueError("Frozen tasks or sample count changed")
    rows = [{**row, "overall_trial": 1, "trial_origin": "first-round"}
            for row in baseline["rows"] if row["task"] in tasks]
    if len(rows) != len(tasks) * len(models):
        raise ValueError("First-round paired observations missing")
    plan = {cell["cell"]: cell for cell in config["plan"]}
    architecture_models = {item["id"]: item["models"][0] for item in config["architectures"]}
    completed_paths = {cell_id: directory / "runs" / run_id / "result.json"
                       for cell_id, run_id in batch["completed"].items()}
    if recovery is not None:
        for cell_id, item in recovery["completed"].items():
            if cell_id in completed_paths or cell_id in batch["inflight"]:
                raise ValueError("Recovery must not replay completed or interrupted cells")
            completed_paths[cell_id] = Path(item["output"]) / "runs" / item["run_id"] / "result.json"
    for cell_id, path in completed_paths.items():
        cell = plan[cell_id]
        result = read(path)
        if result["task_id"] != cell["task"] or result["model_id"] != architecture_models[cell["architecture"]]:
            raise ValueError("Result identity differs from planned cell")
        final = result.get("final_evidence") or {}
        groups, failures = {}, []
        if final.get("log"):
            text = (path.parent / "checks" / final["log"]).read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("LAB_GROUP_RESULTS "):
                    groups = json.loads(line.removeprefix("LAB_GROUP_RESULTS "))
                if line.startswith("AssertionError:") or line.startswith("case "):
                    failures.append(line)
        category = ("accepted" if result["accepted"] else "acceptance_failed"
                    if final.get("ok") and final.get("completion_verified") and not final.get("passed")
                    else "incomplete_or_environment")
        rows.append({"task": result["task_id"], "model": result["model_id"],
                     "overall_trial": prereg["local_repeat_to_overall_trial"][str(cell["repeat"])],
                     "trial_origin": "predeclared-repeat", "batch": str(path.parents[2].resolve()),
                     "result_path": str(path.resolve()), "accepted": result["accepted"],
                     "category": category, "stop_reason": result["stop_reason"], "groups": groups,
                     "scenarios_passed": sum(group["passed"] for group in groups.values()),
                     "scenarios_graded": sum(group["total"] for group in groups.values()),
                     "turns_completed": result["turns_completed"], "final_evidence": final,
                     "accounting": result["accounting"], "duration_seconds": result["duration_seconds"],
                     "failure_details": failures})
    if recovery is not None:
        stopped = recovery["interrupted"]
        cell = plan[stopped["cell"]]
        run_dir = Path(stopped["run_dir"])
        state = read(run_dir / "state.json")
        observed = (datetime.fromisoformat(stopped["observed_last_event_at"]) - datetime.fromisoformat(state["started_at"])).total_seconds()
        rows.append({"task": cell["task"], "model": architecture_models[cell["architecture"]],
                     "overall_trial": prereg["local_repeat_to_overall_trial"][str(cell["repeat"])],
                     "trial_origin": "predeclared-repeat", "batch": str(directory), "result_path": None,
                     "accepted": False, "category": "incomplete_or_environment",
                     "stop_reason": "process_interrupted_response_unknown", "groups": {},
                     "scenarios_passed": 0, "scenarios_graded": 0, "turns_completed": stopped["turns_completed"],
                     "final_evidence": {}, "duration_seconds": round(observed, 6), "duration_observed_only": True,
                     "accounting": {"calls": stopped["known_completed_calls"] + stopped["unknown_calls"],
                                    "total_tokens": stopped["total_tokens"], "usage": stopped["usage"],
                                    "estimated_cost_usd": stopped["known_cost_usd"],
                                    "unknown_cost_reserve_usd": stopped["unknown_reserve_usd"],
                                    "unknown_calls": stopped["unknown_calls"], "usage_complete": False},
                     "failure_details": ["No final grade. Lost process after an outbound request; not replayed."]})
    lookup = {(row["task"], row["model"], row["overall_trial"]): row for row in rows}
    if len(lookup) != len(rows):
        raise ValueError("Duplicate trial; never replace a failed observation")
    complete = recovery is None and batch["status"] == "completed" and len(batch["completed"]) == prereg["new_cells"]
    if complete and len(rows) != len(tasks) * len(models) * 3:
        raise ValueError("Expected exactly three trials per pair")
    pairs, totals = [], {}
    for task in tasks:
        for model in models:
            items = sorted([row for row in rows if row["task"] == task and row["model"] == model],
                           key=lambda row: row["overall_trial"])
            pairs.append({"task": task, "model": model, "recorded": len(items),
                          "accepted": sum(row["accepted"] for row in items),
                          "acceptance_failed": sum(row["category"] == "acceptance_failed" for row in items),
                          "incomplete_or_environment": sum(row["category"] == "incomplete_or_environment" for row in items),
                          "trials": [{"trial": row["overall_trial"], "accepted": row["accepted"],
                                      "score": [row["scenarios_passed"], row["scenarios_graded"]],
                                      "category": row["category"], "stop_reason": row["stop_reason"]} for row in items],
                          "cost_and_time": money_stats(items)})
    for model in models:
        items = [row for row in rows if row["model"] == model]
        totals[model] = {"recorded": len(items), "planned": len(tasks) * 3,
                         "accepted": sum(row["accepted"] for row in items),
                         "acceptance_failed": sum(row["category"] == "acceptance_failed" for row in items),
                         "incomplete_or_environment": sum(row["category"] == "incomplete_or_environment" for row in items),
                         "estimated_cost_usd": str(sum((Decimal(row["accounting"]["estimated_cost_usd"]) for row in items), Decimal(0))),
                         "duration_seconds": str(sum((Decimal(str(row["duration_seconds"])) for row in items), Decimal(0))),
                         "usage_complete": all(row["accounting"]["usage_complete"] for row in items)}
    new_rows = [row for row in rows if row["trial_origin"] == "predeclared-repeat"]
    new_totals = {}
    for model in models:
        items = [row for row in new_rows if row["model"] == model]
        new_totals[model] = {"recorded": len(items), "planned": len(tasks) * 2,
                             "accepted": sum(row["accepted"] for row in items),
                             "acceptance_failed": sum(row["category"] == "acceptance_failed" for row in items),
                             "incomplete_or_environment": sum(row["category"] == "incomplete_or_environment" for row in items),
                             "estimated_cost_usd": str(sum((Decimal(row["accounting"]["estimated_cost_usd"]) for row in items), Decimal(0))),
                             "usage_complete": all(row["accounting"]["usage_complete"] for row in items)}
    effective_status = "recovered_with_interruption" if recovery is not None else batch["status"]
    summary = {"schema_version": 1, "batch_status": effective_status, "complete": complete,
               "new_planned": prereg["new_cells"], "new_recorded": len(new_rows),
               "combined_recorded": len(rows), "combined_planned": len(tasks) * len(models) * 3,
               "new_final_graded": sum(bool(row["final_evidence"].get("completion_verified")) for row in new_rows),
               "combined_final_graded": sum(bool(row["final_evidence"].get("completion_verified")) for row in rows),
               "recovery": str(recovery_path.resolve()) if recovery_path else None,
               "unknown_cost_reserve_usd": str(sum((Decimal(row["accounting"].get("unknown_cost_reserve_usd", "0")) for row in rows), Decimal(0))),
               "new_known_estimated_cost_usd": str(sum((Decimal(row["accounting"]["estimated_cost_usd"]) for row in new_rows), Decimal(0))),
               "combined_known_estimated_cost_usd": str(sum((Decimal(row["accounting"]["estimated_cost_usd"]) for row in rows), Decimal(0))),
               "all_usage_complete": all(row["accounting"]["usage_complete"] for row in rows),
               "model_totals": totals, "new_model_totals": new_totals, "pairs": pairs, "rows": rows,
               "preregistration": str(prereg_path.resolve()), "baseline": str(baseline_path.resolve()),
               "limitations": ["Four development tasks selected because first-round failures occurred; not an unbiased overall benchmark.",
                               "Two project families with overlapping focused/integrated requirements; cases are correlated.",
                               "Three trials per model/task cannot establish a stable ranking or significance.",
                               "First-round trials were in chronological batches; new repeats interleave models in one frozen shuffled batch.",
                               "Trial numbers 2/3 are preallocated labels, not chronological execution order.",
                               "Frozen cost estimates include failed runs and DeepSeek peak prices; not account invoices."]}
    lines = ["# 四个关键任务：三模型独立重复", "",
             f"状态 {effective_status}；新增 {len(new_rows)}/{prereg['new_cells']} 项记录，其中 {summary['new_final_graded']} 项有最终验收；连同首轮共 {len(rows)} 项记录、{summary['combined_final_graded']} 项最终验收。", "",
             "首轮（含失败）为第1次；本批局部 repeat=0/1 为总体第2/3次。编号预先分配，随机执行顺序不一定按编号递增。没有按结果调参、替换失败或追加最好一次。", "",
             "| 模型 | 全通过／有效验收 | 最终验收失败 | 未完成／环境 | 含首轮已知估算 USD | 已记录秒 |",
             "|---|---:|---:|---:|---:|---:|"]
    for model, total in totals.items():
        lines.append(f"| {model} | {total['accepted']}/{total['accepted'] + total['acceptance_failed']} | {total['acceptance_failed']} | {total['incomplete_or_environment']} | {total['estimated_cost_usd']} | {total['duration_seconds']} |")
    lines += ["", "## 仅本次新增的独立验证", "",
              "选题使用了首轮失败信息，所以首轮是发现数据；下表单独展示冻结选题后的新增两次，避免将选题样本与验证样本混成唯一结论。上表仍完整保留三次结果，未删除首轮失败。", "",
              "| 模型 | 新增全通过／有效验收 | 验收失败 | 未完成／环境 | 新增已知估算 USD |",
              "|---|---:|---:|---:|---:|"]
    for model, total in new_totals.items():
        lines.append(f"| {model} | {total['accepted']}/{total['accepted'] + total['acceptance_failed']} | {total['acceptance_failed']} | {total['incomplete_or_environment']} | {total['estimated_cost_usd']} |")
    lines += ["", "## 各题三次记录", "",
              "| 任务 | 模型 | 第1次 | 第2次 | 第3次 | 全通过／有效验收 | 完整记录费用最小／中位／最大 USD |",
              "|---|---|---:|---:|---:|---:|---|"]
    for pair in pairs:
        cells = []
        for trial in (1, 2, 3):
            row = lookup.get((pair["task"], pair["model"], trial))
            cells.append("未运行" if row is None else f"{row['scenarios_passed']}/{row['scenarios_graded']}" if row["groups"] else row["stop_reason"])
        stats = pair["cost_and_time"]
        lines.append(f"| {pair['task']} | {pair['model']} | {' | '.join(cells)} | {pair['accepted']}/{pair['accepted'] + pair['acceptance_failed']} | {stats['min_usd']} / {stats['median_usd']} / {stats['max_usd']} |")
    lines += ["", f"本次新增已知估算 ${summary['new_known_estimated_cost_usd']}；含四题首轮合计 ${summary['combined_known_estimated_cost_usd']}，{'用量完整' if summary['all_usage_complete'] else '包含未知用量，不能视为完整费用'}。", "",
              "五个未重复的任务仍各一次；本报告是四题挑战子集，不能将36项分母和原九题通过率混用。专项与组合需求相关，不是四个独立项目或独立缺陷。", "",
              "费用包含失败。小样本只描述本次重复性，不做显著性或稳定排名结论；不同模型的档位与缓存、先前批次顺序也不同。冻结费率是估算，DeepSeek 使用峰值费率，不是实际账单。", "",
              "## 未全通过的新运行", ""]
    for row in new_rows:
        if row["accepted"]:
            continue
        failed = {name: group for name, group in row["groups"].items() if group["passed"] < group["total"]}
        lines += [f"- {row['task']} / {row['model']} / 第{row['overall_trial']}次：{row['category']}，{row['stop_reason']}；失败组 {json.dumps(failed, ensure_ascii=False)}。"]
    lines += ["", "原始调用、四轮源码快照和独立验收日志保留。该汇总只读取已有记录，没有重新执行隐藏验收，也没有调用模型。"]
    if recovery is not None:
        lines += ["", f"原进程在第18项中断，17项完整记录保留；仅继续6项从未开始的任务。中断项没有重跑、没有追加隐藏评分，保留1条未知请求，费用预留 ${summary['unknown_cost_reserve_usd']}。全部继续部分与已知费用、未知预留共享原整批 $5 上限。", "",
                  "有一项质量结果缺失，不能声称每对都有三次有效验收。中断不算模型质量失败；该项只有截至最后日志的时间和已知费用，已从费用／时间范围统计中排除。原 batch.json 未被伪改为完成，恢复记录单独保存；继续部分保持剩余任务原顺序，但时间与单格批次划分已变化。恢复前后的缓存和负载条件不同，费用与耗时变化不能全部归因于模型输出波动。"]
    (directory / "repeat-comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (directory / "repeat-comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("complete", "new_recorded", "combined_recorded", "new_known_estimated_cost_usd", "model_totals", "new_model_totals")}, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--recovery", type=Path)
    args = parser.parse_args()
    summarize(args.directory.resolve(), args.baseline.resolve(), args.preregistration.resolve(), args.recovery.resolve() if args.recovery else None)
