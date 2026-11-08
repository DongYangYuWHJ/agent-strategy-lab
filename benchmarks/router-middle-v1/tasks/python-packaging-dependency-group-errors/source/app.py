"""Read-only interface that records dependency resolution results and error types."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from packaging.dependency_groups import DependencyGroupInclude, DependencyGroupResolver
from packaging.errors import ExceptionGroup


def error_types(error):
    if isinstance(error, ExceptionGroup):
        return [name for member in error.exceptions for name in error_types(member)]
    return [type(error).__name__]


def run(request):
    try:
        resolver = DependencyGroupResolver(request["groups"])
        if request.get("method") == "lookup":
            items = resolver.lookup(request["target"])
        else:
            items = resolver.resolve(request["target"])
    except ExceptionGroup as error:
        return {"errors": sorted(error_types(error))}
    except Exception as error:
        return {"unwrapped_error": type(error).__name__}
    return {"items": [
        {"include-group": item.include_group} if isinstance(item, DependencyGroupInclude) else str(item)
        for item in items
    ]}



def run_many(requests):
    # Each run constructs independent library instances; the trusted host grades results.
    results = []
    for request in requests:
        try:
            results.append({"ok": True, "value": run(request)})
        except Exception as exc:
            results.append({"ok": False, "error": type(exc).__name__, "message": str(exc)[:500]})
    return results
