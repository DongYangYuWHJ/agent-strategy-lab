"""Read completed calibration runs and trusted group receipts; never call models."""
import argparse
from collections import defaultdict
from decimal import Decimal
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(directory):
    batch = read(directory / "batch.json")
    if batch["status"] == "running" or batch["inflight"]:
        raise ValueError("Batch is still running; preserve partial data without declaring completion")
    suite = read(ROOT / "benchmarks/python-calibration-v1/manifest.json")
    task_metadata = {task["id"]: task for task in suite["tasks"]}
    rows = []
    for path in sorted((directory / "runs").glob("*/result.json")):
        result = read(path)
        events = [json.loads(line) for line in (path.parent / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        final = result.get("final_evidence") or {}
        groups, failure_details = {}, []
        if final.get("log"):
            log = (path.parent / "checks" / final["log"]).read_text(encoding="utf-8")
            for line in log.splitlines():
                if line.startswith("LAB_GROUP_RESULTS "):
                    groups = json.loads(line.removeprefix("LAB_GROUP_RESULTS "))
                if line.startswith("AssertionError:") or line.startswith("case "):
                    failure_details.append(line)
        if result["accepted"]:
            category = "accepted"
        elif final.get("completion_verified") and final.get("ok") and not final.get("passed"):
            category = "acceptance_failed"
        else:
            category = "incomplete_or_environment"
        metadata = task_metadata[result["task_id"]]
        public_checks = [e["result"] for e in events if e["type"] == "tool" and e.get("tool") == "run_checks"]
        rows.append({"task": result["task_id"], "family": metadata["family"], "scope": metadata["scope"],
                     "model": result["model_id"], "accepted": result["accepted"], "category": category,
                     "status": result["status"], "stop_reason": result["stop_reason"],
                     "gateway_stop_reasons": [e["reason"] for e in events if e["type"] == "gateway_stopped"],
                     "turns_completed": result["turns_completed"], "duration_seconds": result["duration_seconds"],
                     "accounting": result["accounting"], "final_evidence": final,
                     "groups": groups, "scenarios_passed": sum(g["passed"] for g in groups.values()),
                     "scenarios_graded": sum(g["total"] for g in groups.values()),
                     "failure_details": failure_details,
                     "write_operations": sum(e["type"] == "tool" and e.get("tool") in {"write_file", "edit_file"}
                                             and e["result"].get("ok") is True for e in events),
                     "public_check_operations": sum(e["type"] == "tool" and e.get("tool") == "run_checks" for e in events),
                     "public_functional_failures": sum(check.get("ok") and check.get("completion_verified")
                                                       and not check.get("passed") for check in public_checks),
                     "turns": result["turns"],
                     "result_path": path.relative_to(directory).as_posix()})
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["model"]].append(row)
    totals = {}
    for model, items in grouped.items():
        totals[model] = {"attempted": len(items), "accepted": sum(r["accepted"] for r in items),
                         "acceptance_failed": sum(r["category"] == "acceptance_failed" for r in items),
                         "incomplete_or_environment": sum(r["category"] == "incomplete_or_environment" for r in items),
                         "calls": sum(r["accounting"]["calls"] for r in items),
                         "total_tokens": sum(r["accounting"]["total_tokens"] for r in items),
                         "estimated_cost_usd": str(sum((Decimal(r["accounting"]["estimated_cost_usd"]) for r in items), Decimal(0))),
                         "usage_complete": all(r["accounting"]["usage_complete"] for r in items),
                         "duration_seconds": str(sum((Decimal(str(r["duration_seconds"])) for r in items), Decimal(0)))}
    summary = {"schema_version": 1, "batch_status": batch["status"],
               "planned": len(batch["configuration"]["plan"]), "recorded": len(rows),
               "known_estimated_cost_usd": str(sum((Decimal(r["accounting"]["estimated_cost_usd"]) for r in rows), Decimal(0))),
               "all_usage_complete": all(r["accounting"]["usage_complete"] for r in rows),
               "batch_budget_usd": batch["configuration"]["batch_budget_usd"],
               "model_totals": totals, "rows": rows, "suite_manifest": suite,
               "limitations": ["Lab-authored feature contracts in three real Python libraries, not official benchmark tasks.",
                               "One trial per model/task; nine tasks include three integrated tasks that reuse six focused contracts.",
                               "Repeated backend/serializer cases are not independent tasks; no significance claim.",
                               "Costs use frozen rates (DeepSeek peak estimate), not actual invoices.",
                               "Incomplete and environment results are not completed quality failures; no paid retries."]}
    (directory / "comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Python 工程候选任务：单体模型筛查", "",
             f"批次状态：{batch['status']}；保存 {len(rows)}/{summary['planned']} 项；每模型每题一次，不自动调参或重跑。", "",
             "| 任务 | 模型 | 结果 | 最终场景 | API | 累计 Token | 估算 USD | 秒 |",
             "|---|---|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        a = row["accounting"]
        outcome = {"accepted": "通过", "acceptance_failed": "最终验收失败",
                   "incomplete_or_environment": row["gateway_stop_reasons"][-1] if row["gateway_stop_reasons"] else row["stop_reason"]}[row["category"]]
        score = f"{row['scenarios_passed']}/{row['scenarios_graded']}" if row["groups"] else "未完成评分"
        lines.append(f"| {row['task']} | {row['model']} | {outcome} | {score} | {a['calls']} | {a['total_tokens']} | {a['estimated_cost_usd']} | {row['duration_seconds']} |")
    lines += ["", "| 模型 | 已运行 | 全通过 | 完整验收失败 | 未完成／环境 | 估算 USD | 总秒数 |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for model, total in totals.items():
        lines.append(f"| {model} | {total['attempted']} | {total['accepted']} | {total['acceptance_failed']} | {total['incomplete_or_environment']} | {total['estimated_cost_usd']} | {total['duration_seconds']} |")
    lines += ["", f"合计已知估算费用 ${summary['known_estimated_cost_usd']}；用量{'完整' if summary['all_usage_complete'] else '含未知部分，不能声称总费用完整'}。", "",
              "## 未全通过记录", ""]
    for row in rows:
        if row["accepted"]:
            continue
        lines += [f"### {row['task']} / {row['model']}", "",
                  f"类别：{row['category']}；原始停止原因：{row['stop_reason']}。"]
        for name, group in row["groups"].items():
            if group["passed"] != group["total"]:
                lines.append(f"- {name}: {group['passed']}/{group['total']}")
        if row["failure_details"]:
            lines += ["", "```text", *row["failure_details"], "```"]
        lines += [""]
    if all(row["accepted"] for row in rows) and rows:
        lines += ["本批已运行记录全部通过；本次仍未观察到最终质量差异。", ""]
    lines += ["## 解释边界", "",
              "这些是三个真实库上的人工功能合同，不是官方 benchmark。九项包括六个专项及三个复用需求的组合题，不能按九个独立项目计算，也不能把重复场景当作独立样本。", "",
              "本轮仅筛查两套廉价单体配置，每格一次。观察到差异也需要重复与 Sol 对照；若全部通过，则仅说明当前候选仍未显示质量区分度。", "",
              "模型允许在四轮内公开测试和修复，隐藏验收只在结束时执行。分组计数见 comparison.json 与独立验收日志；不将场景数量当作需求权重。", "",
              "费用按冻结模型费率估算，DeepSeek 使用峰值价格，不是实际账单。累计 Token 是多次请求相加，不是单次上下文长度；未完成运行的费用不能当作成功完成费用。", "",
              "原始结果、工具与调用轨迹、逐轮源码快照、验收回执全部保留；没有对停止的版本额外执行隐藏评分，没有重跑付费生成。"]
    (directory / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key not in {"rows", "suite_manifest", "limitations"}}, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    summarize(parser.parse_args().directory.resolve())
