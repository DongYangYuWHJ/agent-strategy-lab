"""A pinned, small LiveCodeBench stdio subset, not a leaderboard implementation."""
import base64
import io
import json
from pathlib import Path
import pickle
import urllib.request
import zlib
from .domain import digest, save_json

DATASET = "livecodebench/code_generation_lite"
REVISION = "0fe84c3912ea0c4d4a78037083943e8f0c4dd505"
FILENAME = "test6.jsonl"
SELECTION = ("abc387_b", "abc387_a", "abc387_c", "abc389_d", "abc387_f", "abc388_f")
ROOT = Path(__file__).resolve().parents[2]


class RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        raise ValueError("Dataset pickle globals are forbidden")


def decode_cases(value):
    try:
        cases = json.loads(value)
    except json.JSONDecodeError:
        compressed = base64.b64decode(value, validate=True)
        decoder = zlib.decompressobj()
        data = decoder.decompress(compressed, 20_000_000)
        if decoder.unconsumed_tail or not decoder.eof:
            raise ValueError("Dataset compressed test payload exceeds limit or is incomplete")
        # Upstream stores a pickled JSON string. Never permit arbitrary classes/code.
        text = RestrictedUnpickler(io.BytesIO(data)).load()
        if not isinstance(text, str):
            raise ValueError("Expected a pickled JSON string")
        cases = json.loads(text)
    if not isinstance(cases, list) or not cases:
        raise ValueError("Nonempty test cases are required")
    for case in cases:
        if (not isinstance(case, dict) or case.get("testtype") != "stdin"
                or not isinstance(case.get("input"), str) or not isinstance(case.get("output"), str)):
            raise ValueError("This subset adapter supports stdio string cases only")
    return cases


def fetch_rows():
    url = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{FILENAME}"
    selected, transferred = {}, 0
    with urllib.request.urlopen(url, timeout=60) as response:
        while True:
            line = response.readline(16_000_001)
            if not line:
                break
            transferred += len(line)
            if len(line) > 16_000_000 or transferred > 32_000_000:
                raise ValueError("Subset download exceeded its bounded streaming budget")
            row = json.loads(line)
            if row.get("question_id") in SELECTION:
                selected[row["question_id"]] = row
            if len(selected) == len(SELECTION):
                break
    if set(selected) != set(SELECTION):
        raise ValueError("Pinned source did not contain all selected task IDs")
    return selected, transferred


def check_script(cases):
    # The trusted host owns expected outputs; only inputs reach the submission worker.
    return ("from check_client import check_stdio_cases\nimport os\nfrom pathlib import Path\nimport json\n\n"
            + "cases = json.loads(" + repr(json.dumps(cases, ensure_ascii=False)) + ")\n"
            + "check_stdio_cases(Path(os.environ['LAB_WORKSPACE']) / 'solution.py', cases)\n")


def import_subset(output=None, records=None):
    output = Path(output or ROOT / "benchmarks" / "livecodebench").resolve()
    if output.exists():
        raise ValueError("Subset output already exists; choose a new directory instead of changing a frozen suite")
    if records:
        selected = {row["question_id"]: row for row in records}
        transferred = 0
    else:
        selected, transferred = fetch_rows()
    if set(selected) != set(SELECTION):
        raise ValueError("Exactly the pinned selection is required")
    prepared = []
    for question_id in SELECTION:
        row = selected[question_id]
        public = decode_cases(row["public_test_cases"])
        private = decode_cases(row["private_test_cases"])
        if row["difficulty"] not in {"easy", "medium", "hard"}:
            raise ValueError("Unrecognized source difficulty")
        prepared.append((row, public, private))
    output.mkdir(parents=True)
    entries = []
    for row, public, private in prepared:
        question_id = row["question_id"]
        task_id = "lcb-" + question_id.replace("_", "-")
        directory = output / "tasks" / task_id
        source = directory / "source"
        source.mkdir(parents=True)
        (source / "solution.py").write_text("# Read standard input and print the answer.\nraise NotImplementedError('Implement this task')\n", encoding="utf-8")
        description = (f"LiveCodeBench / {row['difficulty']} / {row['question_title']}\n\n"
                       + row["question_content"]
                       + "\n\nImplement solution.py as a Python standard-input/output program. Use the standard library only. "
                       "Each test starts a fresh process. Do not read test files or modify the evaluator.")
        save_json(directory / "task.json", {"schema_version": 1, "id": task_id, "description": description,
                  "acceptance": ["Match the specified input/output behavior for all public and held-out cases.",
                                 "Read stdin and write stdout; no external dependencies or files are required."],
                  "source_dir": "source", "editable_files": ["solution.py"],
                  "public_check": "public_check.py", "final_check": "final_check.py"})
        for kind, cases in (("public", public), ("final", private)):
            (directory / f"{kind}_check.py").write_text(check_script(cases), encoding="utf-8")
        entry = {"task_id": task_id, "question_id": question_id, "title": row["question_title"],
                 "difficulty": row["difficulty"], "platform": row["platform"], "contest_date": row["contest_date"],
                 "manifest": f"tasks/{task_id}/task.json", "public_cases": len(public), "private_cases": len(private),
                 "record_sha256": digest(row)}
        save_json(directory / "provenance.json", {"dataset": DATASET, "revision": REVISION, "source_file": FILENAME, **entry})
        save_json(output / "upstream" / f"{question_id}.json", row)
        entries.append(entry)
    manifest = {"schema_version": 1, "dataset": DATASET, "revision": REVISION,
                "source_file": FILENAME, "source_url": f"https://huggingface.co/datasets/{DATASET}",
                "selection": "Fixed infrastructure sample: two easy, two medium, two hard; not a representative ranking set.",
                "evaluation": "local stdio subset adapter, separate trusted comparison, fresh process per case; not official leaderboard scores",
                "transferred_record_bytes": transferred, "tasks": entries}
    save_json(output / "manifest.json", manifest)
    return manifest


def audit_subset(output):
    """Offline positive and negative controls; never creates a model/provider."""
    from .domain import Task
    from .evaluation import Checks
    from .runner import task_fingerprint
    from .workspace import Workspace, file_hash
    suite = ROOT / "benchmarks" / "livecodebench"
    manifest = json.loads((suite / "manifest.json").read_text(encoding="utf-8"))
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for entry in manifest["tasks"]:
        task = Task.load(suite / entry["manifest"])
        row = json.loads((suite / "upstream" / (entry["question_id"] + ".json")).read_text(encoding="utf-8"))
        if digest(row) != entry["record_sha256"]:
            raise ValueError("Frozen upstream record changed")
        control = suite / "operator_controls" / (entry["question_id"] + ".py")
        sources = {"positive": control.read_text(encoding="utf-8"),
                   "starter": (task.source_dir / "solution.py").read_text(encoding="utf-8"),
                   "sample_only": "print(" + repr(json.loads(row["public_test_cases"])[0]["output"]) + ")\n",
                   "early_exit": "import os\nos._exit(0)\n"}
        checks_result = {}
        for label, source in sources.items():
            directory = output / task.id / label
            directory.mkdir(parents=True)
            workspace = Workspace(task, directory)
            workspace.write_file("solution.py", source)
            checks = Checks(task, directory, workspace, 300)
            evidence = {kind: checks.run(kind, 300) for kind in ("public", "final")}
            checks_result[label] = evidence
        passed = all(evidence["passed"] and evidence["completion_verified"]
                     for evidence in checks_result["positive"].values())
        passed = passed and all(not evidence["passed"] and evidence["completion_verified"]
                                for label, pair in checks_result.items() if label != "positive" for evidence in pair.values())
        results.append({"task_id": task.id, "difficulty": entry["difficulty"], "passed": passed,
                        "task_fingerprint": task_fingerprint(task), "control_sha256": file_hash(control),
                        "evidence": checks_result})
        print(task.id + ": " + ("audit passed" if passed else "AUDIT FAILED"), flush=True)
        save_json(output / "audit.json", {"schema_version": 1, "kind": "offline_evaluator_controls",
                  "dataset_revision": REVISION, "all_passed": all(row["passed"] for row in results),
                  "complete": len(results) == len(manifest["tasks"]), "tasks": results})
    return all(row["passed"] for row in results)
