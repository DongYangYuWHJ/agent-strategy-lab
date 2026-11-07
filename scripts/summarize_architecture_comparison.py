"""Read same-batch architecture costs, grades and handoff evidence; no generation."""
import argparse
from collections import defaultdict
from decimal import Decimal
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(directory, *, rows_only=False):
    batch = read(directory / "batch.json")
    if batch["status"] == "running" or batch["inflight"]:
        raise ValueError("Batch is still running; preserve it and wait")
    config = batch["configuration"]
    cells = {item["cell"]: item for item in config["plan"]}
    architectures = {item["id"]: item for item in config["architectures"]}
    rows = []
    for cell_id, run_id in batch["completed"].items():
        cell = cells[cell_id]
        run_dir = directory / "runs" / run_id
        result = read(run_dir / "result.json")
        events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        final = result.get("final_evidence") or {}
        groups = {}
        if final.get("log"):
            for line in (run_dir / "checks" / final["log"]).read_text(encoding="utf-8").splitlines():
                if line.startswith("LAB_GROUP_RESULTS "):
                    groups = json.loads(line.removeprefix("LAB_GROUP_RESULTS "))
        category = ("accepted" if result["accepted"] else "acceptance_failed"
                    if final.get("ok") and final.get("completion_verified") and not final.get("passed")
                    else "incomplete_or_environment")
        charges = [event for event in events if event["type"] == "request_completed"]
        plan_cost = sum((Decimal(event["estimated_cost_usd"]) for event in charges if event["turn"] == "plan"), Decimal(0))
        later_cost = sum((Decimal(event["estimated_cost_usd"]) for event in charges if event["turn"] != "plan"), Decimal(0))
        if plan_cost + later_cost != Decimal(result["accounting"]["estimated_cost_usd"]):
            raise ValueError("Phase charges do not equal ledger total")
        actual = defaultdict(set)
        for event in events:
            if event["type"] == "request_started":
                actual[event["turn"]].add(event["model_id"])
        writes = [event for event in events if event["type"] == "tool"
                  and event.get("tool") in {"write_file", "edit_file"} and event["result"].get("ok") is True]
        plan_writes = [event for event in writes if event["turn"] == "plan"]
        if plan_writes and architectures[cell['architecture']]['strategy'] != 'planner_executor_reviewer_flexible':
            raise ValueError("Planning phase wrote source code")
        architecture = architectures[cell["architecture"]]
        handoff = architecture["strategy"] == "planner_handoff"
        selections = [read(path) for path in sorted((run_dir / "turns").glob("*/selection.json"))]
        children_path = run_dir / "child-sessions.json"
        children = read(children_path).get("data", []) if children_path.exists() else None
        if handoff:
            for turn, model_ids in actual.items():
                expected = architecture["models"][0 if turn == "plan" else 1]
                if model_ids != {expected}:
                    raise ValueError("Actual phase model differs from handoff assignment")
            if selections and not all(item["passed"] for item in selections):
                raise ValueError("Primary role/model selection verification failed")
        if children:
            raise ValueError("Unexpected child session in solo/handoff comparison")
        rows.append({"cell": cell_id, "task": result["task_id"], "architecture": cell["architecture"],
                     "repeat": cell["repeat"],
                     "strategy": architecture["strategy"], "accepted": result["accepted"], "category": category,
                     "status": result["status"], "stop_reason": result["stop_reason"],
                     "gateway_stop_reasons": [event["reason"] for event in events if event["type"] == "gateway_stopped"],
                     "turns_completed": result["turns_completed"], "turns": result["turns"],
                     "final_evidence": final, "groups": groups,
                     "scenarios_passed": sum(group["passed"] for group in groups.values()),
                     "scenarios_graded": sum(group["total"] for group in groups.values()),
                     "accounting": result["accounting"], "duration_seconds": result["duration_seconds"],
                     "plan_cost_usd": str(plan_cost), "later_cost_usd": str(later_cost),
                     "plan_calls": sum(event["turn"] == "plan" for event in charges),
                     "later_calls": sum(event["turn"] != "plan" for event in charges),
                     "actual_models_by_turn": {turn: sorted(ids) for turn, ids in actual.items()},
                     "successful_writes_by_turn": {turn: sum(event["turn"] == turn for event in writes)
                                                   for turn in actual},
                     "verified_selections": selections, "child_sessions": children,
                     "result_path": str((run_dir / "result.json").relative_to(directory))})
    if rows_only:
        return rows
    totals = {}
    for architecture in architectures:
        items = [row for row in rows if row["architecture"] == architecture]
        totals[architecture] = {"recorded": len(items), "planned": sum(cell["architecture"] == architecture for cell in cells.values()),
                                "accepted": sum(row["accepted"] for row in items),
                                "acceptance_failed": sum(row["category"] == "acceptance_failed" for row in items),
                                "incomplete_or_environment": sum(row["category"] == "incomplete_or_environment" for row in items),
                                "known_cost_usd": str(sum((Decimal(row["accounting"]["estimated_cost_usd"]) for row in items), Decimal(0))),
                                "plan_cost_usd": str(sum((Decimal(row["plan_cost_usd"]) for row in items), Decimal(0))),
                                "later_cost_usd": str(sum((Decimal(row["later_cost_usd"]) for row in items), Decimal(0))),
                                "calls": sum(row["accounting"]["calls"] for row in items),
                                "total_tokens": sum(row["accounting"]["total_tokens"] for row in items),
                                "duration_seconds": str(sum((Decimal(str(row["duration_seconds"])) for row in items), Decimal(0))),
                                "usage_complete": all(row["accounting"]["usage_complete"] for row in items)}
    tasks = list(config["task_fingerprints"])
    lookup = {(row["task"], row["architecture"]): row for row in rows}
    comparisons = []
    for task in tasks:
        sol, luna, handoff = [lookup.get((task, key)) for key in ("sol-solo", "luna-solo", "sol-handoff-luna")]
        if sol is None or luna is None or handoff is None:
            continue
        comparisons.append({"task": task, "luna_accepted": luna["accepted"], "sol_accepted": sol["accepted"],
                            "handoff_accepted": handoff["accepted"],
                            "handoff_minus_sol_cost_usd": str(Decimal(handoff["accounting"]["estimated_cost_usd"]) - Decimal(sol["accounting"]["estimated_cost_usd"])),
                            "both_sol_and_handoff_accepted": sol["accepted"] and handoff["accepted"],
                            "handoff_improves_binary_acceptance_over_luna": handoff["accepted"] and not luna["accepted"]})
    matched_tasks = [item["task"] for item in comparisons if item["both_sol_and_handoff_accepted"]]
    matched_sol = sum((Decimal(lookup[task, "sol-solo"]["accounting"]["estimated_cost_usd"]) for task in matched_tasks), Decimal(0))
    matched_handoff = sum((Decimal(lookup[task, "sol-handoff-luna"]["accounting"]["estimated_cost_usd"]) for task in matched_tasks), Decimal(0))
    summary = {"schema_version": 1, "batch_status": batch["status"], "planned": len(cells), "recorded": len(rows),
               "complete": batch["status"] == "completed" and len(rows) == len(cells),
               "known_estimated_cost_usd": str(sum((Decimal(row["accounting"]["estimated_cost_usd"]) for row in rows), Decimal(0))),
               "all_usage_complete": all(row["accounting"]["usage_complete"] for row in rows),
               "architecture_totals": totals, "paired_task_comparisons": comparisons, "rows": rows,
               "both_sol_and_handoff_successful_tasks": {"tasks": matched_tasks, "sol_cost_usd": str(matched_sol),
                                                        "handoff_cost_usd": str(matched_handoff),
                                                        "handoff_cost_reduction_fraction": str((matched_sol - matched_handoff) / matched_sol) if matched_sol else None},
               "limitations": ["One run per architecture/task; no stable architecture ranking or significance claim.",
                               "Four development tasks selected after solo screening, with overlapping requirements in two projects.",
                               "Architecture change includes generic role instructions and one planning-stage handoff, not a pure model-only ablation.",
                               "Prices are frozen API estimates including failed runs, not account invoices.",
                               "Do not call cheaper incomplete/failing results equal-quality savings."]}
    lines = ["# Sol／Luna：单体与规划后交接的同批对照", "",
             f"状态 {batch['status']}；保存 {len(rows)}/{len(cells)} 项，每格一次，不调参或自动重跑。", "",
             "| 结构 | 全通过 | 验收失败 | 未完成／环境 | API | 规划阶段 USD | 后续阶段 USD | 总估算 USD | 秒 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, total in totals.items():
        lines.append(f"| {name} | {total['accepted']}/{total['recorded']} | {total['acceptance_failed']} | {total['incomplete_or_environment']} | {total['calls']} | {total['plan_cost_usd']} | {total['later_cost_usd']} | {total['known_cost_usd']} | {total['duration_seconds']} |")
    lines += ["", "| 任务 | Sol 单体 | Luna 单体 | Sol→Luna |", "|---|---|---|---|"]
    for task in tasks:
        values = []
        for name in ("sol-solo", "luna-solo", "sol-handoff-luna"):
            row = lookup.get((task, name))
            if row is None:
                values.append("未运行")
            else:
                grade = f"{row['scenarios_passed']}/{row['scenarios_graded']}" if row["groups"] else row["stop_reason"]
                values.append(f"{grade}；${row['accounting']['estimated_cost_usd']}")
        lines.append(f"| {task} | {' | '.join(values)} |")
    lines += ["", f"已知合计 ${summary['known_estimated_cost_usd']}；用量{'完整' if summary['all_usage_complete'] else '存在未知部分，费用不完整'}。", "",
              f"另列两组都完整通过的 {len(matched_tasks)} 个同题配对：Sol 合计 ${matched_sol}，交接合计 ${matched_handoff}。这是已通过子集的描述，主表仍包含所有失败费用，不能用这个子集代替全任务结果。", "",
              "## 交接与权限证据", ""]
    for row in rows:
        if row["strategy"] == "planner_handoff":
            lines.append(f"- {row['task']}：完成 {row['turns_completed']}/4 轮，已核对 {len(row['verified_selections'])} 次角色／模型选择；子会话 {'未能导出' if row['child_sessions'] is None else len(row['child_sessions'])}；实际模型分轮为 {json.dumps(row['actual_models_by_turn'], ensure_ascii=False)}。")
    lines += ["", "## 解释边界", "",
              "同批固定四题、模型档位、工具、四轮用户提示与最终验收；交接组第一轮 Sol 只规划、后三轮 Luna 接管，不委派、不重新召回 Planner。所有规划阶段均禁止写入。一次规划阶段可以有多次 API 调用。", "",
              "角色系统提示也是架构的一部分；该实验不是只换模型而其他上下文完全相同的消融。历史 DeepSeek 与三次单体结果保留作参照，不混入本批对照的分母。", "",
              "先评价交接是否比 Luna 完成更多要求，再看是否达到 Sol 的质量且费用较低。若质量未达到，不能把低价叫作等质量节省；单次同分也不能证明稳定收益。接口／权限／额度停止和完整验收失败分别统计。", "",
              "四题是按开发阶段失败选择的挑战子集，两个项目中的专项与组合有重叠，不是独立留出集。所有费用含失败尝试，按冻结标准费率估算，不是实际账户账单。", "",
              "原始 result.json、events.jsonl、逐轮源码、selection.json、permission-audit.json 与 child-sessions.json 保留。汇总只读既有证据，不重新执行隐藏验收，不调用模型。"]
    (directory / "architecture-comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (directory / "architecture-comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("batch_status", "planned", "recorded", "known_estimated_cost_usd", "all_usage_complete", "architecture_totals")}, ensure_ascii=True))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    summarize(parser.parse_args().directory.resolve())
