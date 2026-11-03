"""Prepare operator-only SWE-bench Pro materials, never execute upstream code."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "benchmarks/swebench-pro-v2-selection/selection.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use an already downloaded archive")
    args = parser.parse_args()
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    output = ROOT / "artifacts/swebench-pro-v2-intake"
    output.mkdir(parents=True, exist_ok=True)
    archive = args.archive or output / "upstream.zip"
    if not archive.exists():
        url = "https://codeload.github.com/scaleapi/SWE-bench_Pro-os/zip/" + selection["revision"]
        with urllib.request.urlopen(url, timeout=120) as response:
            archive.write_bytes(response.read())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != selection["archive_sha256"]:
        raise ValueError("Archive checksum differs from frozen selection")
    checksums = {}
    with zipfile.ZipFile(archive) as source:
        prefix = source.namelist()[0].split("/")[0] + "/"
        for task in selection["tasks"]:
            upstream = prefix + "v2/tasks/" + task["id"] + "/"
            names = [n for n in source.namelist() if n.startswith(upstream) and not n.endswith("/")]
            required = {"instruction.md", "task.toml", "environment/Dockerfile", "solution/gold_patch.diff", "tests/test.sh", "tests/config.json"}
            relatives = {n[len(upstream):] for n in names}
            if not required <= relatives:
                raise ValueError(f"Incomplete task: {task['id']}")
            for name in names:
                relative = name[len(upstream):]
                data = source.read(name)
                if relative == "instruction.md" and hashlib.sha256(data).hexdigest() != task["instruction_sha256"]:
                    raise ValueError("Instruction checksum mismatch")
                # The WHOLE destination is operator-only, including the instruction preview.
                target = output / "operator" / task["id"] / relative
                if not target.resolve().is_relative_to((output / "operator").resolve()):
                    raise ValueError("Unsafe archive path")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                checksums[target.relative_to(output).as_posix()] = hashlib.sha256(data).hexdigest()
        for relative in ["v2/README.md", "v2/GATE.md", "v2/SHA256SUMS", "LICENSE"]:
            data = source.read(prefix + relative)
            target = output / "provenance" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    receipt = {"revision": selection["revision"], "archive_sha256": digest,
               "task_count": len(selection["tasks"]), "files": checksums,
               "status": "materials_prepared_not_executed",
               "warning": "Operator materials include solutions and hidden tests. Never mount this directory in an agent workspace. Repository source/dependencies live in upstream container images, not this archive."}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(selection['tasks'])} tasks / {len(checksums)} files: {output}")


if __name__ == "__main__":
    main()
