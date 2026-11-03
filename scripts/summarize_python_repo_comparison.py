"""Summarize a completed repository batch without model calls or retries."""
import argparse
from collections import defaultdict
from decimal import Decimal
import json
from pathlib import Path


def summarize(directory):
    batch = json.loads((directory / "batch.json").read_text(encoding="utf-8"))
    if batch["status"] == "running" or batch["inflight"]:
        raise ValueError("Batch is still running; do not present partial results as complete")
    rows = []
    for result_path in sorted((directory / "runs").glob("*/result.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        events = [json.loads(line) for line in (result_path.parent / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        underlying = [e["reason"] for e in events if e["type"] == "gateway_stopped"]
        tools = [e for e in events if e["type"] == "tool"]
        row = {"task": result["task_id"], "model": result["model_id"], "accepted": result["accepted"],
               "status": result["status"], "stop_reason": result["stop_reason"], "gateway_stop_reasons": underlying,
               "turns_completed": result["turns_completed"], "duration_seconds": result["duration_seconds"],
               "accounting": result["accounting"], "final_evidence": result["final_evidence"],
               "write_operations": sum(e["tool"] in {"write_file", "edit_file"} and e["result"].get("ok") is True for e in tools),
               "public_check_operations": sum(e["tool"] == "run_checks" for e in tools),
               "peak_estimated_input_tokens": max((e["estimated_input_tokens"] for e in events if e["type"] == "request_started"), default=0),
               "written_files": sorted({e["arguments"]["path"] for e in tools if e["tool"] in {"write_file", "edit_file"} and e["result"].get("ok") is True}),
               "result_path": result_path.relative_to(directory).as_posix()}
        rows.append(row)
    known = sum((Decimal(r["accounting"]["estimated_cost_usd"]) for r in rows), Decimal(0))
    all_known = all(r["accounting"]["usage_complete"] for r in rows)
    configuration = batch["configuration"]
    policies = {model["id"]: {"max_output_tokens": model.get("max_output_tokens"),
                              "enforce_total_token_limit": model.get("enforce_total_token_limit", True)}
                for architecture in configuration["architectures"] for model in architecture["catalog"]}
    summary = {"batch_status": batch["status"], "planned": len(batch["configuration"]["plan"]),
               "recorded": len(rows), "known_estimated_cost_usd": str(known), "all_usage_complete": all_known,
               "rows": rows, "limits": configuration["limits"], "model_policies": policies,
               "batch_budget_usd": configuration["batch_budget_usd"],
               "limitations": ["Two curated historical upgrade contracts, not original issues or official benchmark.",
                               "One run per model/task; limits and tool set differ from earlier miniature tasks.",
                               "A resource stop is not a completed failing implementation. Partial costs are not cost-to-solution."]}
    (directory / "comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Pure Python 仓库任务：Luna / DeepSeek", "", "固定四轮对话，每格一次，保留停止结果，不自动调参或重跑。", "",
             "| 任务 | 模型 | 结果／限制 | 完成轮数 | API | Token | 估算费用 USD | 秒 |", "|---|---|---|---:|---:|---:|---:|---:|"]
    groups = defaultdict(list)
    for row in rows:
        groups[row["model"]].append(row)
        reason = "通过" if row["accepted"] else (row["gateway_stop_reasons"][-1] if row["gateway_stop_reasons"] else row["stop_reason"])
        a = row["accounting"]
        lines.append(f"| {row['task']} | {row['model']} | {reason} | {row['turns_completed']}/4 | {a['calls']} | {a['total_tokens']} | {a['estimated_cost_usd']} | {row['duration_seconds']} |")
    totals = {}
    for mid, results in groups.items():
        totals[mid] = {"attempted": len(results), "accepted": sum(r["accepted"] for r in results),
                       "estimated_cost_usd": str(sum((Decimal(r["accounting"]["estimated_cost_usd"]) for r in results), Decimal(0))),
                       "calls": sum(r["accounting"]["calls"] for r in results),
                       "total_tokens": sum(r["accounting"]["total_tokens"] for r in results),
                       "duration_seconds": str(sum((Decimal(str(r["duration_seconds"])) for r in results), Decimal(0)))}
    summary["model_totals"] = totals
    (directory / "comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines += ["", "| 模型 | 完成 | 生成调用 | 估算费用 USD | 总耗时秒 |", "|---|---:|---:|---:|---:|"]
    for mid, total in totals.items():
        lines.append(f"| {mid} | {total['accepted']}/{total['attempted']} | {total['calls']} | {total['estimated_cost_usd']} | {total['duration_seconds']} |")
    def cap(value):
        return "不设本地上限" if value is None else str(value)
    limit_text = "; ".join(f"{name}={cap(configuration['limits'].get(name))}" for name in
                           ("max_calls", "max_tool_steps", "max_total_tokens", "max_estimated_input_tokens", "max_seconds"))
    policy_text = "; ".join(f"{mid}: 单次输出={cap(p['max_output_tokens'])}，累计 Token 门限={'启用' if p['enforce_total_token_limit'] else '关闭'}" for mid, p in policies.items())
    lines += ["", f"共保存 {len(rows)}/{summary['planned']} 项，已知估算费用 ${known}；用量{'完整' if all_known else '含未知部分'}。", "",
              "Token 为各次调用累计使用量，不是单次上下文长度。下一次放行还会预留输入与服务输出额度，因此资源预留可能在实际用量达到配置值前停止请求。", "",
              f"本批冻结限制：{limit_text}。整批费用：{cap(configuration['batch_budget_usd'])} USD。", "",
              f"模型策略：{policy_text}。服务端限制与 OpenCode 引擎自身边界另计。", "",
              "费用按批次冻结的模型 catalog 估算。DeepSeek 使用峰值价格，未按时段折算；这些数值不是账户实际账单。", "",
              "## 解释边界", "", "每题采用真实上游源码，升级需求及 30／35 个最终场景由本实验整理；不是官方上游完整测试。源码及参考版本固定，参考实现和隐藏测试不进入 Agent 工作区。", "",
              "触发限额、会话错误和验收不通过分开记录。opencode_session_error 如同时有 gateway_stop_reasons，以后者说明本地网关拒绝的具体原因，原始停止原因仍保留。未完成记录的支出不能当作成功完成该任务的费用，不能据此排列模型能力或省钱程度。", "",
              "逐项 result.json、events.jsonl、调用记录和逐轮源码快照均保留在 runs/。未对中途停止的版本额外执行隐藏验收。"]
    (directory / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    summarize(parser.parse_args().directory.resolve())
