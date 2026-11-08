"""Read-only interface for exercising document edits and serialization."""
from pathlib import Path
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tomlkit


def run(request):
    document = tomlkit.parse(request["text"])
    for path, value in request["updates"]:
        table = document
        for key in path[:-1]:
            table = table[key]
        table[path[-1]] = value
    rendered = tomlkit.dumps(document)
    result = {"document": tomllib.loads(rendered)}
    if request.get("inspect_text"):
        result["text"] = rendered
    return result



def run_many(requests):
    # Each run constructs independent library instances; the trusted host grades results.
    results = []
    for request in requests:
        try:
            results.append({"ok": True, "value": run(request)})
        except Exception as exc:
            results.append({"ok": False, "error": type(exc).__name__, "message": str(exc)[:500]})
    return results
