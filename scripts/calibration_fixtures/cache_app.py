"""Read-only cache adapter; no reference eviction or update logic lives here."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import cachetools


def run(request):
    now = [0]
    kind = request.get("kind", "LRUCache")
    size = len if request.get("weighted") else None
    kw = {"getsizeof": size}
    if kind == "TTLCache":
        kw.update(ttl=request.get("ttl", 10), timer=lambda: now[0])
    cache = getattr(cachetools, kind)(request.get("maxsize", 3), **kw)
    results = []

    def pairs(step):
        for pair in step["pairs"]:
            yield pair
        if step.get("fail_iterator"):
            raise RuntimeError("broken stream")

    for step in request["steps"]:
        try:
            op = step["op"]
            if op == "put":
                cache[step["key"]] = step["value"]
                result = None
            elif op == "get":
                result = cache[step["key"]]
            elif op == "resize":
                result = [list(pair) for pair in cache.resize(step["size"])]
            elif op == "atomic":
                result = cache.update_atomic(pairs(step))
            elif op == "popitem":
                result = list(cache.popitem())
            elif op == "pop":
                result = cache.pop(step["key"])
            elif op == "advance":
                now[0] += step["seconds"]
                result = now[0]
            elif op == "state":
                result = {"items": sorted([[key, cachetools.Cache.__getitem__(cache, key)] for key in cache]),
                          "maxsize": cache.maxsize, "currsize": cache.currsize}
            elif op == "memo":
                calls = []
                @cachetools.cached(cache, key=lambda key: key)
                def lookup(key):
                    calls.append(key)
                    return step["value"]
                result = [lookup(step["key"]), lookup(step["key"]), len(calls)]
            else:
                raise ValueError("Unknown operation")
            results.append(result)
        except Exception as exc:
            results.append({"error": type(exc).__name__})
    return {"results": results}
