"""Sequential, reproducible batches with a shared cumulative budget."""
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path
import glob
import random
from .domain import Limits, Task, digest, money, now, read_json, save_json
from .providers import make_provider
from .reporting import collect_results, write_report
from .runner import SYSTEM, run_task, task_fingerprint
from .tools import TOOLS
from .workspace import inventory
from . import __version__


def discover_task_paths(root, configuration):
    """Combine explicit manifests and sorted globs, deduplicating by real path."""
    explicit = configuration.get("tasks", [])
    patterns = configuration.get("task_globs", [])
    for name, values in (("tasks", explicit), ("task_globs", patterns)):
        if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"{name} must be an array of nonempty path strings")
    candidates = [(root / value).resolve() for value in explicit]
    for pattern in patterns:
        matches = [Path(value).resolve() for value in glob.glob(str(root / pattern), recursive=True)]
        if not matches:
            raise ValueError(f"Task pattern matched no files: {pattern}")
        candidates.extend(sorted(matches, key=lambda value: (value.as_posix().casefold(), value.as_posix())))
    selected = []
    seen = set()
    for path in candidates:
        if not path.is_file():
            raise ValueError(f"Task manifest is missing or not a file: {path}")
        if path not in seen:
            selected.append(path)
            seen.add(path)
    if not selected:
        raise ValueError("No tasks selected: configure tasks or task_globs")
    return selected


def load_experiment(path, catalog, model_filter=None):
    raw = read_json(path)
    if raw.get("schema_version") != 1 or raw.get("strategy") != "single_agent":
        raise ValueError("v1 experiments require schema_version=1 and strategy=single_agent")
    root = path.resolve().parent
    tasks = [Task.load(value) for value in discover_task_paths(root, raw)]
    ids = raw["models"]
    if model_filter is not None:
        if not set(model_filter) <= set(ids):
            raise ValueError("Requested model is not in this experiment")
        ids = [name for name in ids if name in model_filter]
    if len(set(ids)) != len(ids) or len({task.id for task in tasks}) != len(tasks):
        raise ValueError("Duplicate task or model IDs")
    models = [catalog[name] for name in ids]
    repeats = raw.get("repeats", 1)
    seed = raw.get("seed", 42)
    if not tasks or not models or type(repeats) is not int or not 1 <= repeats <= 100 or type(seed) is not int:
        raise ValueError("Invalid experiment tasks/models/repeats/seed")
    kinds = {model.provider == "mock" for model in models}
    if len(kinds) != 1:
        raise ValueError("Use separate batches for simulated and live experiments")
    return tasks, models, Limits(**raw.get("limits", {})), repeats, seed, money(raw["batch_budget_usd"])


def run_batch(path, catalog, output, model_filter=None, resume=False):
    if read_json(path).get("backend") == "opencode":
        from .workflow_experiments import run_workflow_batch
        return run_workflow_batch(path, catalog, output, model_filter, resume)
    tasks, models, limits, repeats, seed, batch_budget = load_experiment(path, catalog, model_filter)
    token_counters = {}
    for task in tasks:
        for model in models:
            provider = make_provider(model, SYSTEM, "preflight", TOOLS, task)
            token_counters[model.id] = provider.token_counting_info()
    plan = [{"cell": f"{task.id}:{model.id}:{repeat}", "task": task.id, "model": model.id, "repeat": repeat}
            for repeat in range(repeats) for task in tasks for model in models]
    random.Random(seed).shuffle(plan)
    identity = {"schema_version": 1, "framework_version": __version__,
                "framework_fingerprint": digest(inventory(Path(__file__).parent)),
                "task_fingerprints": {task.id: task_fingerprint(task) for task in tasks},
                "task_manifests": {task.id: str(task.manifest_path) for task in tasks},
                "models": [asdict(model) for model in models], "limits": asdict(limits),
                "token_counting": token_counters,
                "batch_budget_usd": str(batch_budget), "strategy": "single_agent", "plan": plan,
                "system_prompt": SYSTEM, "tools": TOOLS, "seed": seed}
    output = output.resolve()
    manifest_path = output / "batch.json"
    if resume:
        if not manifest_path.exists():
            raise ValueError("Cannot resume: batch.json is missing")
        manifest = read_json(manifest_path)
        if manifest["fingerprint"] != digest(identity):
            raise ValueError("Cannot resume: tasks, models, checks, framework, or configuration changed")
        for run_id in manifest["completed"].values():
            if Path(run_id).name != run_id or not (output / "runs" / run_id / "result.json").is_file():
                raise ValueError("Cannot resume: completed result is missing; restore the record before continuing")
        if any(item["status"] == "interrupted" for item in collect_results(output)):
            write_report(output)
            raise ValueError("Incomplete run detected. Inspect its request/usage records; it will not be silently replayed")
        # If killed between result.json and the batch checkpoint, recover the cell mapping.
        for cell, info in manifest.get("inflight", {}).items():
            matches = [item for item in collect_results(output) if item["run_id"] not in manifest["completed"].values()
                       and item["task_id"] == info["task"] and item["model_id"] == info["model"]]
            if len(matches) == 1:
                manifest["completed"][cell] = matches[0]["run_id"]
            elif matches:
                raise ValueError("Ambiguous interrupted batch checkpoint")
        manifest["inflight"] = {}
    else:
        if output.exists():
            raise ValueError("Output directory already exists; use a new directory or --resume")
        output.mkdir(parents=True)
        manifest = {"schema_version": 1, "fingerprint": digest(identity), "configuration": identity,
                    "started_at": now(), "completed": {}, "inflight": {}, "status": "running"}
    save_json(manifest_path, manifest)
    task_map = {task.id: task for task in tasks}
    model_map = {model.id: model for model in models}
    manifest["status"] = "running"
    try:
        for cell in plan:
            if cell["cell"] in manifest["completed"]:
                continue
            existing = collect_results(output)
            if any(not item["accounting"]["usage_complete"] for item in existing):
                manifest["status"] = "usage_unknown"
                break
            spent = sum((money(item["accounting"]["estimated_cost_usd"]) for item in existing), Decimal(0))
            remaining_budget = batch_budget - spent
            if remaining_budget <= 0:
                manifest["status"] = "batch_budget_limit"
                break
            task = task_map[cell["task"]]
            if task_fingerprint(task) != identity["task_fingerprints"][task.id]:
                raise ValueError("Task source or checks changed during batch")
            effective = replace(limits, max_cost_usd=str(min(money(limits.max_cost_usd), remaining_budget)))
            manifest["inflight"] = {cell["cell"]: cell}
            save_json(manifest_path, manifest)
            result = run_task(task, model_map[cell["model"]], effective, output / "runs")
            manifest["completed"][cell["cell"]] = result["run_id"]
            manifest["inflight"] = {}
            save_json(manifest_path, manifest)
            print(f"{task.id} / {cell['model']} [{cell['repeat'] + 1}]: {result['status']} ({result['stop_reason']})", flush=True)
            if result["status"] == "cancelled":
                manifest["status"] = "cancelled"
                break
            if result["stop_reason"] == "input_count_error":
                manifest["status"] = "input_count_error"
                break
            if not result["accounting"]["usage_complete"]:
                manifest["status"] = "usage_unknown"
                break
        else:
            manifest["status"] = "completed"
    except KeyboardInterrupt:
        manifest["status"] = "cancelled"
    except Exception:
        manifest["status"] = "error"
        raise
    finally:
        manifest["updated_at"] = now()
        save_json(manifest_path, manifest)
        write_report(output)
    return manifest
