"""Operator-owned checks: public feedback versus final held-out acceptance."""
import os
from pathlib import Path
import subprocess
import sys
import time
import shutil
from .workspace import file_hash


class Checks:
    def __init__(self, task, run_dir, workspace, timeout):
        self.root = run_dir / "checks"
        self.root.mkdir()
        self.workspace = workspace
        self.timeout = timeout
        self.counter = 0
        self.paths = {}
        self.hashes = {}
        for kind, original in (("public", task.public_check), ("final", task.final_check)):
            target = self.root / (kind + ".py")
            shutil.copyfile(original, target)
            self.paths[kind] = target
            self.hashes[kind] = file_hash(target)

    def run(self, kind, remaining):
        self.workspace.verify_immutable()
        script = self.paths[kind]
        if file_hash(script) != self.hashes[kind]:
            raise ValueError("Trusted validator changed")
        self.counter += 1
        log_path = self.root / f"{self.counter:03d}-{kind}.log"
        # Credentials are deliberately absent from child processes.
        environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "LANG") if key in os.environ}
        environment["LAB_WORKSPACE"] = str(self.workspace.root.resolve())
        started = time.monotonic()
        with log_path.open("wb") as output:
            try:
                result = subprocess.run([sys.executable, "-I", "-B", str(script.resolve())],
                                        cwd=self.workspace.root, env=environment, stdin=subprocess.DEVNULL,
                                        stdout=output, stderr=subprocess.STDOUT,
                                        timeout=max(0.01, min(self.timeout, remaining)), check=False)
                code = result.returncode
                status = "completed"
            except subprocess.TimeoutExpired:
                code, status = None, "timed_out"
        self.workspace.verify_immutable()
        if file_hash(script) != self.hashes[kind]:
            raise ValueError("Trusted validator changed during execution")
        with log_path.open("rb") as output:
            text = output.read(4001).decode("utf-8", errors="replace")
        return {"ok": code != 2 and status == "completed", "passed": code == 0,
                "exit_code": code, "status": status, "output": text[:4000],
                "output_truncated": log_path.stat().st_size > 4000,
                "duration_seconds": round(time.monotonic() - started, 6),
                "log": log_path.name, "validator_sha256": self.hashes[kind]}
