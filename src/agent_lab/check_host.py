"""Trusted check-script host. Never import a submission into this process."""
import json
from pathlib import Path
import runpy
import sys
import traceback


def main():
    script, receipt, nonce = sys.argv[1:]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    outcome, code = "passed", 0
    try:
        runpy.run_path(script, run_name="__main__")
    except AssertionError:
        outcome, code = "failed", 1
        traceback.print_exc()
    except BaseException:
        outcome, code = "environment_error", 2
        traceback.print_exc()
    # A normal exit code alone is insufficient. Early exits cannot reach here.
    Path(receipt).write_text(json.dumps({"nonce": nonce, "completed": True, "outcome": outcome}), encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
