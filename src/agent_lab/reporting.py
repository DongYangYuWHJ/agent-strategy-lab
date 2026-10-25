from collections import Counter
from decimal import Decimal
from pathlib import Path
from .domain import read_json, save_json


def incomplete_result(directory):
    """Recover only accounting, never replay an interrupted billable request."""
    config = read_json(directory / "config.json")
    events = []
    if (directory / "events.jsonl").exists():
        for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                import json
                events.append(json.loads(line))
            except ValueError:
                # A terminated process may leave a partial final line.
                break
    starts = {item["call"]: item for item in events if item["type"] == "request_started"}
    completed = {item["call"]: item for item in events if item["type"] == "request_completed"}
    outstanding = set(starts) - set(completed)
    known = sum((Decimal(item["estimated_cost_usd"]) for item in completed.values()), Decimal(0))
    reserve = sum((Decimal(starts[index]["estimated_reserve_usd"]) for index in outstanding), Decimal(0))
    tokens = sum(item["usage"]["input_tokens"] + item["usage"]["output_tokens"] for item in completed.values())
    result = {"run_id": directory.name, "task_id": config["task"]["id"], "model_id": "--".join(m["id"] for m in config.get("models", [config["model"]])),
            "strategy": config["strategy"]["name"], "execution_kind": config["execution_kind"],
            "status": "interrupted", "stop_reason": "incomplete_run", "accepted": False,
            "duration_seconds": 0, "repairs": 0, "artifact_dir": str(directory),
            "accounting": {"estimated_cost_usd": str(known), "unknown_cost_reserve_usd": str(reserve),
                           "total_tokens": tokens, "calls": len(starts), "usage_complete": not outstanding}}
    if config.get("workflow"):
        result.update(backend=config["backend"], workflow_id=config["workflow"]["id"], turns=[],
                      turns_completed=sum(e["type"] == "turn_completed" for e in events),
                      turns_expected=len(config["workflow"]["turns"]))
    return result


def collect_results(root: Path):
    # Inspect only the selected run/batch, never unrelated result files.
    if (root / "result.json").is_file():
        return [read_json(root / "result.json")]
    if (root / "config.json").is_file():
        return [incomplete_result(root)]
    run_root = root / "runs" if (root / "batch.json").is_file() else root
    results = []
    if run_root.exists():
        for directory in sorted(run_root.iterdir()):
            if not directory.is_dir() or not (directory / "config.json").is_file():
                continue
            results.append(read_json(directory / "result.json") if (directory / "result.json").is_file() else incomplete_result(directory))
    return results


def summarize(results):
    grouped = {}
    for result in results:
        key = (result["execution_kind"], result["strategy"], result["model_id"], result.get("backend", "native"), result.get("workflow_id", ""))
        grouped.setdefault(key, []).append(result)
    rows = []
    for (kind, strategy, model, backend, workflow), group in sorted(grouped.items()):
        cost = sum((Decimal(item["accounting"]["estimated_cost_usd"]) for item in group), Decimal(0))
        reserves = sum((Decimal(item["accounting"]["unknown_cost_reserve_usd"]) for item in group), Decimal(0))
        success = sum(item["accepted"] for item in group)
        complete = all(item["accounting"]["usage_complete"] for item in group)
        rows.append({"execution_kind": kind, "strategy": strategy, "model_id": model, "backend": backend, "workflow_id": workflow,
                     "runs": len(group), "successes": success, "success_rate": success / len(group),
                     "known_estimated_cost_usd": str(cost), "unknown_cost_reserve_usd": str(reserves),
                     "unit_accepted_cost_usd": str(cost / success) if success and complete else None,
                     "usage_complete": complete,
                     "total_tokens": sum(item["accounting"]["total_tokens"] for item in group),
                     "total_seconds": round(sum(item["duration_seconds"] for item in group), 6),
                     "stop_reasons": dict(Counter(item["stop_reason"] for item in group))})
    return rows


def write_report(root: Path):
    results = collect_results(root)
    rows = summarize(results)
    report = {"schema_version": 1, "cost_basis": "reported usage x frozen configured rates; not provider invoice",
              "groups": rows, "runs": results}
    save_json(root / "report.json", report)
    lines = ["# AI 架构实验报告", "", "费用依据：供应商报告用量 × 本批次保存的价格表；不是供应商账单。",
             "模拟与真实实验分组展示。模拟用量来自固定回放，不能用于模型能力排名。", "",
             "| 类型 | 策略 | 模型 | 成功 / 运行 | 总 Token | 已知估算费用 USD | 每次合格交付费用 USD |",
             "|---|---|---|---:|---:|---:|---:|"]
    for row in rows:
        unit = row["unit_accepted_cost_usd"]
        display = f"{Decimal(unit):.6f}" if unit is not None else ("费用不完整" if not row["usage_complete"] else "无合格交付")
        strategy_label = row['strategy'] + (f" / {row['backend']} / {row['workflow_id']}" if row['workflow_id'] else "")
        lines.append(f"| {'模拟' if row['execution_kind'] == 'simulated' else '真实'} | {strategy_label} | {row['model_id']} | "
                     f"{row['successes']} / {row['runs']} | {row['total_tokens']} | "
                     f"{Decimal(row['known_estimated_cost_usd']):.6f} | {display} |")
    lines += ["", "失败尝试的费用包含在单位合格交付成本中；缺失用量时不计算该排名指标。",
              "未知费用预留用于暂停后续调用，不能当作已知账单或确定的最高费用。", "", "## 每次运行", "",
              "| 任务 | 模型 | 结果 | 停止原因 | 修复轮数 | 用量完整 | 记录目录 |",
              "|---|---|---|---|---:|---|---|"]
    for item in results:
        lines.append(f"| {item['task_id']} | {item['model_id']} | {item['status']} | {item['stop_reason']} | "
                     f"{item['repairs']} | {'是' if item['accounting']['usage_complete'] else '否'} | {item['run_id']} |")
    lines.append("")
    workflows = [item for item in results if item.get("workflow_id")]
    if workflows:
        lines += ["## 用户交互轮次", "", "每轮可以包含多次模型与工具调用；轮次完成不代表任务验收通过。", "",
                  "| 任务 | 工作流 | 已完成轮次 | 最终验收 |", "|---|---|---:|---|"]
        for item in workflows:
            lines.append(f"| {item['task_id']} | {item['workflow_id']} | {item['turns_completed']} / {item['turns_expected']} | {item['stop_reason']} |")
        lines.append("")
        for item in workflows:
            lines.append(f"\n运行 `{item['run_id']}`：\n")
            for turn in item.get("turns", []):
                lines.append(f"\n- {turn['id']}: {turn['status']}；模型调用 {turn.get('calls', '未完成')}；记录 `runs/{item['run_id']}/turns/{turn['index']:02d}-{turn['id']}/`。")
        lines.append("")
    (root / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return report
