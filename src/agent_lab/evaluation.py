"""Operator-owned checks: public feedback versus final held-out acceptance."""
import os
from pathlib import Path
import subprocess
import sys
import time
import shutil
import json
import secrets
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
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.runtime_hashes = {}
        for name in ("check_host.py", "check_client.py", "submission_worker.py"):
            target = self.runtime / name
            shutil.copyfile(Path(__file__).parent / name, target)
            self.runtime_hashes[target] = file_hash(target)
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
        if any(file_hash(path) != checksum for path, checksum in self.runtime_hashes.items()):
            raise ValueError("Trusted check runtime changed")
        self.counter += 1
        log_path = self.root / f"{self.counter:03d}-{kind}.log"
        # Credentials are deliberately absent from child processes.
        environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "LANG") if key in os.environ}
        environment["LAB_WORKSPACE"] = str(self.workspace.root.resolve())
        timeout = max(0.01, min(self.timeout, remaining))
        environment["LAB_CHECK_DEADLINE"] = str(time.monotonic() + timeout)
        environment["LAB_SUBMISSION_WORKER"] = str((self.runtime / "submission_worker.py").resolve())
        nonce = secrets.token_hex(24)
        receipt_path = self.root / f"{self.counter:03d}-{kind}.receipt.json"
        started = time.monotonic()
        with log_path.open("wb") as output:
            try:
                result = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", str((self.runtime / "check_host.py").resolve()),
                                         str(script.resolve()), str(receipt_path.resolve()), nonce],
                                        cwd=self.workspace.root, env=environment, stdin=subprocess.DEVNULL,
                                        stdout=output, stderr=subprocess.STDOUT,
                                        timeout=timeout, check=False,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                code = result.returncode
                status = "completed"
            except subprocess.TimeoutExpired:
                code, status = None, "timed_out"
        self.workspace.verify_immutable()
        if file_hash(script) != self.hashes[kind]:
            raise ValueError("Trusted validator changed during execution")
        if any(file_hash(path) != checksum for path, checksum in self.runtime_hashes.items()):
            raise ValueError("Trusted check runtime changed during execution")
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            receipt = {}
        completed = (isinstance(receipt, dict) and receipt.get("nonce") == nonce
                     and receipt.get("completed") is True
                     and receipt.get("outcome") == {0: "passed", 1: "failed", 2: "environment_error"}.get(code))
        if status == "completed" and not completed:
            status = "incomplete"
        with log_path.open("rb") as output:
            text = output.read(4001).decode("utf-8", errors="replace")
        return {"ok": code in (0, 1) and status == "completed", "passed": code == 0 and completed and status == "completed",
                "completion_verified": completed,
                "exit_code": code, "status": status, "output": text[:4000],
                "output_truncated": log_path.stat().st_size > 4000,
                "duration_seconds": round(time.monotonic() - started, 6),
                "log": log_path.name, "validator_sha256": self.hashes[kind]}
