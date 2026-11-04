"""Continue never-started cells only; preserve the interrupted request and global budget."""
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.domain import Task, load_models, now, read_json, save_json
from agent_lab.experiments import run_batch
from agent_lab.runner import task_fingerprint
from agent_lab.workspace import inventory
from agent_lab.domain import digest


def main():
    original = ROOT / "artifacts/python-calibration-repeat-live-20261103-01"
    output = ROOT / "artifacts/python-calibration-repeat-recovery-20261103-01"
    if output.exists():
        raise ValueError("Recovery already exists; inspect it, never replay its requests")
    batch = read_json(original / "batch.json")
    if len(batch["completed"]) != 17 or len(batch["inflight"]) != 1:
        raise ValueError("Original state differs from the inspected interruption")
    pending = [cell for cell in batch["configuration"]["plan"]
               if cell["cell"] not in batch["completed"] and cell["cell"] not in batch["inflight"]]
    if len(pending) != 6:
        raise ValueError("Expected exactly six never-started cells")
    interrupted_cell = next(iter(batch["inflight"]))
    interrupted_dir = original / "runs/python-itsdangerous-integrated-gpt-6-luna-e28e8676eb8f"
    if (interrupted_dir / "result.json").exists():
        raise ValueError("Interrupted run now has a result; inspect before continuation")
    events = [json.loads(line) for line in (interrupted_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    charged = [event for event in events if event["type"] == "request_completed"]
    started = [event for event in events if event["type"] == "request_started"]
    if len(charged) != 9 or len(started) != 10:
        raise ValueError("Interrupted request accounting differs from inspected state")
    known = sum((Decimal(event["estimated_cost_usd"]) for event in charged), Decimal(0))
    reserve = Decimal(started[-1]["estimated_reserve_usd"])
    usage = {key: sum(event["usage"][key] for event in charged) for key in charged[0]["usage"]}
    previous_cost = sum((Decimal(read_json(original / "runs" / run_id / "result.json")["accounting"]["estimated_cost_usd"])
                         for run_id in batch["completed"].values()), Decimal(0))
    catalog_path = ROOT / "configs/models-python-calibration-repeat.json"
    catalog = load_models(catalog_path)
    base = read_json(ROOT / "configs/workflow-python-calibration-repeat.json")
    architecture = {item["id"]: item for item in base["architectures"]}
    if digest(inventory(ROOT / "src/agent_lab")) != batch["configuration"]["framework_fingerprint"]:
        raise ValueError("Framework changed since the frozen batch")
    expected_models = {model["id"]: model for item in batch["configuration"]["architectures"] for model in item["catalog"]}
    for model in catalog.values():
        if json.loads(json.dumps(asdict(model))) != expected_models[model.id]:
            raise ValueError("Model configuration changed")
    output.mkdir()
    record = {"schema_version": 1, "status": "prepared", "original_batch": str(original),
              "created_at": now(), "original_processes_verified_absent": True,
              "global_budget_usd": batch["configuration"]["batch_budget_usd"],
              "previous_completed_known_cost_usd": str(previous_cost),
              "interrupted": {"cell": interrupted_cell, "run_dir": str(interrupted_dir),
                              "status": "host_interrupted_not_replayed", "known_completed_calls": 9,
                              "unknown_calls": 1, "known_cost_usd": str(known), "unknown_reserve_usd": str(reserve),
                              "usage": usage, "total_tokens": usage["input_tokens"] + usage["output_tokens"],
                              "turns_completed": sum(read_json(path)["status"] == "completed"
                                                     for path in (interrupted_dir / "turns").glob("*/turn.json")),
                              "observed_last_event_at": events[-1]["timestamp"],
                              "hidden_grading_executed": False},
              "pending_original_cells": pending, "completed": {}, "parts": []}
    save_json(output / "recovery.json", record)
    global_limit = Decimal(record["global_budget_usd"])
    try:
        for index, cell in enumerate(pending, 1):
            continued_cost = sum((Decimal(read_json(Path(item["output"]) / "runs" / item["run_id"] / "result.json")["accounting"]["estimated_cost_usd"])
                                  for item in record["completed"].values()), Decimal(0))
            remaining = global_limit - previous_cost - known - reserve - continued_cost
            if remaining <= 0:
                record["status"] = "global_budget_limit"
                break
            task_path = ROOT / "benchmarks/python-calibration-v1/tasks" / cell["task"] / "task.json"
            if task_fingerprint(Task.load(task_path)) != batch["configuration"]["task_fingerprints"][cell["task"]]:
                raise ValueError("Task changed")
            config = {**base, "workflow": str((ROOT / "configs/workflows/daily-review.json").resolve()),
                      "catalog": str(catalog_path), "architectures": [architecture[cell["architecture"]]],
                      "tasks": [str(task_path)], "task_globs": [], "repeats": 1,
                      "batch_budget_usd": str(remaining)}
            config_path = output / f"part-{index:02d}.json"
            part_output = output / f"part-{index:02d}"
            save_json(config_path, config)
            part = {"original_cell": cell["cell"], "original_repeat": cell["repeat"],
                    "config": str(config_path), "output": str(part_output), "remaining_budget_usd": str(remaining),
                    "status": "running"}
            record["parts"].append(part)
            record["status"] = "running"
            save_json(output / "recovery.json", record)
            print(f"Continue {index}/6: {cell['cell']}; remaining global allowance {remaining}", flush=True)
            result = run_batch(config_path, catalog, part_output)
            part["status"] = result["status"]
            if len(result["completed"]) != 1:
                record["status"] = "stopped_in_part"
                break
            run_id = next(iter(result["completed"].values()))
            record["completed"][cell["cell"]] = {"output": str(part_output), "run_id": run_id,
                                                   "original_repeat": cell["repeat"]}
            run = read_json(part_output / "runs" / run_id / "result.json")
            if not run["accounting"]["usage_complete"] or result["status"] != "completed":
                record["status"] = "stopped_in_part"
                break
            save_json(output / "recovery.json", record)
        else:
            record["status"] = "completed_pending_only"
    finally:
        record["updated_at"] = now()
        save_json(output / "recovery.json", record)
    print(record["status"], flush=True)


if __name__ == "__main__":
    main()
