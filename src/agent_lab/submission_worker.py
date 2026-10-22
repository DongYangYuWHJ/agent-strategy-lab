"""Execute one submission request. Expected answers stay in the trusted host.

Process separation is an integrity boundary, NOT an OS security sandbox.
"""
import contextlib
import io
import json
from pathlib import Path
import sys


class LimitedOutput(io.StringIO):
    def write(self, value):
        if self.tell() + len(value) > 262144:
            raise RuntimeError("Submission output limit exceeded")
        return super().write(value)


def main():
    request = json.load(sys.stdin)
    source = Path(request["source"])
    captured, diagnostic = LimitedOutput(), LimitedOutput()
    try:
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(diagnostic):
            namespace = {"__name__": "submission", "__file__": str(source)}
            sys.argv = [str(source)]
            exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), namespace)
            parts = request["function"].split(".")
            target = namespace[parts[0]]
            if len(parts) == 2:
                target = getattr(target(), parts[1])
            args = request["args"]
            value = target(*args)
        response = {"status": "returned", "value": value, "args_after": args}
        encoded = json.dumps(response, ensure_ascii=True, allow_nan=False)
        if len(encoded.encode("utf-8")) > 1048576:
            raise RuntimeError("Submission result limit exceeded")
    except BaseException as exc:
        encoded = json.dumps({"status": "exception", "exception": type(exc).__name__, "message": str(exc)[:400]})
    print(encoded, flush=True)


if __name__ == "__main__":
    main()
