"""Batch planning for frozen task × architecture × conversation experiments."""
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path
import random
from .domain import Limits, Task, digest, money, now, read_json, safe_id, save_json
from .experiments import discover_task_paths
from .opencode_bridge import SUPPORTED_VERSION
from .opencode_workflow import run_workflow, workflow_role_prompts
from .providers import make_provider
from .reporting import collect_results, write_report
from .runner import task_fingerprint
from .workflows import Workflow
from .workspace import inventory


def load_workflow_experiment(path, catalog, model_filter=None):
    raw = read_json(path)
    if raw.get("schema_version") != 1 or raw.get("backend") != "opencode":
        raise ValueError("Workflow experiments require backend=opencode and schema_version=1")
    workflow = Workflow.load(path.resolve().parent / raw["workflow"])
    tasks = [Task.load(p) for p in discover_task_paths(path.resolve().parent, raw)]
    if len({t.id for t in tasks}) != len(tasks):
        raise ValueError("Duplicate task IDs")
    architectures = []
    for item in raw["architectures"]:
        if set(item) != {"id", "strategy", "models"}:
            raise ValueError("Architecture requires id, strategy, models")
        safe_id(item["id"])
        expected = {"single_agent": 1, "planner_worker": 2}.get(item["strategy"])
        if expected is None or len(item["models"]) != expected:
            raise ValueError("Invalid workflow architecture")
        models = [catalog[mid] for mid in item["models"]]
        if any(m.provider == "mock" for m in models):
            raise ValueError("OpenCode workflows require real provider configurations")
        if model_filter is None or any(mid in model_filter for mid in item["models"]):
            architectures.append((item, models))
    if len({a["id"] for a, _ in architectures}) != len(architectures) or not architectures:
        raise ValueError("No architectures selected or duplicate IDs")
    if model_filter and not set(model_filter) <= {m for a, _ in architectures for m in a["models"]}:
        raise ValueError("Requested model not in workflow experiment")
    repeats, seed = raw.get("repeats", 1), raw.get("seed", 42)
    if type(repeats) is not int or not 1 <= repeats <= 100 or type(seed) is not int:
        raise ValueError("Invalid repeats or seed")
    return tasks, architectures, workflow, Limits(**raw.get("limits", {})), repeats, seed, money(raw["batch_budget_usd"])


def run_workflow_batch(path, catalog, output, model_filter=None, resume=False):
    tasks, architectures, workflow, limits, repeats, seed, budget = load_workflow_experiment(path, catalog, model_filter)
    counters = {}
    for _, models in architectures:
        for model in models:
            counters[model.id] = make_provider(model, "", "", [], tasks[0]).token_counting_info()
    plan = [{"cell": f"{t.id}:{a['id']}:{r}", "task": t.id, "architecture": a["id"], "repeat": r}
            for r in range(repeats) for t in tasks for a, _ in architectures]
    random.Random(seed).shuffle(plan)
    identity = {"schema_version": 1, "backend": "opencode", "opencode_version": SUPPORTED_VERSION,
                "framework_fingerprint": digest(inventory(Path(__file__).parent)), "workflow": asdict(workflow),
                "token_counting": counters,
                "task_fingerprints": {t.id: task_fingerprint(t) for t in tasks},
                "architectures": [{**a, "catalog": [asdict(m) for m in models]} for a, models in architectures],
                "role_prompts": {a["id"]: workflow_role_prompts(a["strategy"]) for a, _ in architectures},
                "limits": asdict(limits), "seed": seed, "plan": plan, "batch_budget_usd": str(budget)}
    output = output.resolve()
    if resume:
        manifest = read_json(output / "batch.json")
        if manifest.get("fingerprint") != digest(identity):
            raise ValueError("Cannot resume: workflow, source, architecture, or configuration changed")
        results = collect_results(output)
        if manifest.get("inflight") or any(r["status"] == "interrupted" for r in results):
            raise ValueError("Inspect interrupted workflow; it will not be replayed automatically")
        if any(not (output / "runs" / rid / "result.json").is_file() for rid in manifest["completed"].values()):
            raise ValueError("Completed workflow result missing")
    else:
        if output.exists():
            raise ValueError("Output directory already exists; use a new directory or --resume")
        output.mkdir(parents=True)
        manifest = {"schema_version": 1, "fingerprint": digest(identity), "configuration": identity,
                    "completed": {}, "inflight": {}, "started_at": now(), "status": "running"}
    task_map = {t.id: t for t in tasks}
    arch_map = {a["id"]: (a, models) for a, models in architectures}
    manifest["status"] = "running"
    save_json(output / "batch.json", manifest)
    try:
        for cell in plan:
            if cell["cell"] in manifest["completed"]:
                continue
            existing = collect_results(output)
            if any(not r["accounting"]["usage_complete"] for r in existing):
                manifest["status"] = "usage_unknown"
                break
            spent = sum((money(r["accounting"]["estimated_cost_usd"]) for r in existing), Decimal(0))
            if spent >= budget:
                manifest["status"] = "batch_budget_limit"
                break
            task = task_map[cell["task"]]
            if task_fingerprint(task) != identity["task_fingerprints"][task.id]:
                raise ValueError("Task changed during workflow batch")
            arch, models = arch_map[cell["architecture"]]
            if workflow_role_prompts(arch["strategy"]) != identity["role_prompts"][arch["id"]]:
                raise ValueError("Role instructions changed during workflow batch")
            effective = replace(limits, max_cost_usd=str(min(money(limits.max_cost_usd), budget - spent)))
            manifest["inflight"] = {cell["cell"]: cell}
            save_json(output / "batch.json", manifest)
            result = run_workflow(task, models, effective, output / "runs", workflow, arch["strategy"],
                                  role_prompts=identity["role_prompts"][arch["id"]])
            manifest["completed"][cell["cell"]] = result["run_id"]
            manifest["inflight"] = {}
            save_json(output / "batch.json", manifest)
            print(f"{task.id} / {arch['id']}: {result['status']} ({result['stop_reason']}); turns {result['turns_completed']}/{result['turns_expected']}", flush=True)
            if result["status"] in {"error", "cancelled"} or not result["accounting"]["usage_complete"] or result["stop_reason"] == "input_count_error":
                manifest["status"] = result["stop_reason"]
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
        save_json(output / "batch.json", manifest)
        write_report(output)
    return manifest
