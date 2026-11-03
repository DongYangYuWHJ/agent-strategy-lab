"""Trusted submission RPC client and LiveCodeBench subset comparators."""
import builtins
from decimal import Decimal, InvalidOperation
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


class SubmissionFailure(AssertionError):
    pass


def invoke(source, mode="call", **arguments):
    source = Path(source).resolve()
    workspace = Path(os.environ["LAB_WORKSPACE"]).resolve()
    if not source.is_relative_to(workspace) or not source.is_file():
        raise ValueError("Submission must be a file inside the workspace")
    submission_limit = os.environ.get("LAB_SUBMISSION_TIMEOUT_SECONDS", "6")
    bounds = [float(os.environ["LAB_CHECK_DEADLINE"]) - time.monotonic() - 0.25]
    if submission_limit != "none":
        bounds.append(float(submission_limit))
    finite = [value for value in bounds if math.isfinite(value)]
    timeout = min(finite) if finite else None
    if timeout is not None and timeout <= 0:
        raise SubmissionFailure("Check time budget exhausted")
    environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "LANG") if key in os.environ}
    request = {"source": str(source), "mode": mode, **arguments}
    command = [sys.executable, "-I", "-B", "-X", "utf8"]
    if mode == "stdin":
        # Real stdin/stdout preserve buffer APIs, fast I/O and normal sys.exit(0).
        # The trusted host compares the observed output; exit 0 never grades itself.
        command.append(str(source))
        payload = arguments["input"].encode("utf-8")
    elif mode == "call":
        command.append(os.environ["LAB_SUBMISSION_WORKER"])
        payload = json.dumps(request).encode("utf-8")
    else:
        raise ValueError("Unsupported submission mode")
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        try:
            result = subprocess.run(command, cwd=workspace, env=environment, input=payload,
                                    stdout=output, stderr=errors, timeout=timeout, check=False,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            raise SubmissionFailure("Submission timed out") from None
        output.seek(0)
        data = output.read(1048577)
    if result.returncode or len(data) > 1048576:
        raise SubmissionFailure("Submission crashed or produced an oversized result")
    if mode == "stdin":
        try:
            value = data.decode("utf-8")
        except UnicodeError:
            raise SubmissionFailure("Submission output is not UTF-8") from None
        return {"status": "returned", "value": value, "args_after": []}
    try:
        response = json.loads(data)
    except (ValueError, UnicodeError):
        raise SubmissionFailure("Submission exited without a complete result") from None
    if not isinstance(response, dict):
        raise SubmissionFailure("Malformed submission result")
    if response.get("status") == "exception":
        name = response.get("exception")
        # Catchable by operator tests, but uncaught submission errors remain task failures.
        if name in {"ValueError", "TypeError", "RuntimeError", "IndexError", "KeyError", "ZeroDivisionError", "AttributeError"}:
            error = type("Submission" + name, (getattr(builtins, name), SubmissionFailure), {})
            raise error(response.get("message", ""))
        raise SubmissionFailure("Submission raised " + str(name))
    if response.get("status") != "returned" or "value" not in response or not isinstance(response.get("args_after"), list):
        raise SubmissionFailure("Submission did not return a complete result")
    return response


class Submission:
    def __init__(self, source):
        self.source = source

    def __getattr__(self, name):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)?", name):
            raise AttributeError(name)
        def call(*args):
            response = invoke(self.source, function=name, args=args)
            for original, updated in zip(args, response["args_after"]):
                if isinstance(original, list) and isinstance(updated, list):
                    original[:] = updated
                elif isinstance(original, dict) and isinstance(updated, dict):
                    original.clear()
                    original.update(updated)
            return response["value"]
        return call


def load_submission(source):
    return Submission(source)


def stdio_equal(actual, expected):
    """Match upstream line stripping and exact Decimal token comparison; no float tolerance."""
    actual_lines = [line.strip() for line in actual.strip().split("\n")]
    expected_lines = [line.strip() for line in expected.strip().split("\n")]
    if len(actual_lines) != len(expected_lines):
        return False
    for left, right in zip(actual_lines, expected_lines):
        if left == right:
            continue
        try:
            left_numbers, right_numbers = [Decimal(x) for x in left.split()], [Decimal(x) for x in right.split()]
            if not left_numbers or any(not x.is_finite() for x in left_numbers + right_numbers) or left_numbers != right_numbers:
                return False
        except InvalidOperation:
            return False
    return True


def check_stdio_cases(source, cases):
    if not cases:
        raise ValueError("A check must contain at least one case")
    for index, case in enumerate(cases):
        result = invoke(source, mode="stdin", input=case["input"])
        if not isinstance(result["value"], str) or not stdio_equal(result["value"], case["output"]):
            # The host prints this for public checks; final logs never return to the agent.
            raise SubmissionFailure(f"Wrong answer at case {index + 1}")
    print(f"Executed {len(cases)} cases successfully")
