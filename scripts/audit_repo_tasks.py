"""Audit repository task fixtures with the real isolated checker; never call models."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.domain import Task, read_json, save_json
from agent_lab.evaluation import Checks
from agent_lab.runner import task_fingerprint
from agent_lab.workspace import Workspace


def control_patches(folder, task):
    reference = {p.relative_to(folder / "operator/reference").as_posix(): p.read_text(encoding="utf-8")
                 for p in (folder / "operator/reference").rglob("*.py")}
    if set(reference) != set(task.editable_files):
        raise ValueError("Reference patch must match the declared editable files")
    controls = [("starter", {}, False, False), ("reference", reference, True, True)]
    for path in sorted((folder / "operator/mutants").glob("*.json")):
        mutant = read_json(path)
        if not set(mutant) <= set(task.editable_files):
            raise ValueError("Mutant cannot modify trusted or immutable files")
        controls.append((path.stem, {**reference, **mutant}, True, False))
    controls.append(("early-exit", {**reference, task.editable_files[0]: "import os\nos._exit(0)\n"}, False, False))
    return controls


def audit(output, suite=None):
    suite = (suite or ROOT / "benchmarks/repo-workflows-v1").resolve()
    if output.exists():
        raise ValueError("Use a new audit directory; existing evidence is preserved")
    output.mkdir(parents=True)
    manifest = read_json(suite / "manifest.json")
    rows = []
    for entry in manifest["tasks"]:
        task = Task.load(suite / entry["manifest"])
        before = task_fingerprint(task)
        for name, patch, expected_public, expected_final in control_patches(task.manifest_path.parent, task):
            directory = output / task.id / name
            directory.mkdir(parents=True)
            workspace = Workspace(task, directory)
            for path, text in patch.items():
                workspace.write_file(path, text)
            checks = Checks(task, directory, workspace, 120)
            public = checks.run("public", 120)
            final = checks.run("final", 120)
            matched = (public["ok"] and final["ok"] and public["passed"] == expected_public
                       and final["passed"] == expected_final)
            row = {"task": task.id, "control": name, "expected_public": expected_public, "expected_final": expected_final,
                   "matched": matched, "public": public, "final": final, "task_fingerprint": before}
            rows.append(row)
            save_json(directory / "audit-result.json", row)
            print(task.id, name, "PASS" if matched else "MISMATCH", flush=True)
        if task_fingerprint(task) != before:
            raise ValueError("Audit changed the frozen task source or checks")
    result = {"schema_version": 1, "suite": manifest["id"], "supplier_generation_requests": 0,
              "tasks": len(manifest["tasks"]), "controls": len(rows), "passed": all(r["matched"] for r in rows), "results": rows}
    save_json(output / "audit.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.output.resolve())
    print("AUDIT", "PASS" if result["passed"] else "FAIL", result["controls"], "controls", flush=True)
    raise SystemExit(0 if result["passed"] else 1)
