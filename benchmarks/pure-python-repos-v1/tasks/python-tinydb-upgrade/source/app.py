"""Read-only lab adapter. Business behavior must be implemented in tinydb itself."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from copy import deepcopy
import tempfile
from tinydb import TinyDB, Query
from tinydb.table import Document
from tinydb.storages import MemoryStorage, JSONStorage
from tinydb.middlewares import CachingMiddleware


def view(value):
    if isinstance(value, Document):
        return {"id": value.doc_id, "data": dict(value)}
    if isinstance(value, list):
        return [view(v) for v in value]
    return value


def query(spec):
    if "and" in spec:
        a, b = spec["and"]
        return query(a) & query(b)
    if "or" in spec:
        a, b = spec["or"]
        return query(a) | query(b)
    if "not" in spec:
        return ~query(spec["not"])
    q = Query()
    for key in spec.get("path", []):
        q = q[key]
    op, value = spec["op"], spec.get("value")
    if op == "eq":
        return q == value
    if op == "ge":
        return q >= value
    if op == "exists":
        return q.exists()
    if op == "fragment":
        return q.fragment(value)
    if op == "one_of":
        return q.one_of(value)
    if op == "noop":
        return q.noop()
    if op == "lower_eq":
        return q.map(str.lower) == value
    raise ValueError("Unknown query operator")


def run(request):
    request = deepcopy(request)
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
        path = str(Path(directory) / "data.json")
        backend = request.get("backend", "memory")

        def open_db():
            if backend == "memory":
                return TinyDB(storage=MemoryStorage)
            if backend == "cached":
                return TinyDB(path, storage=CachingMiddleware(JSONStorage))
            return TinyDB(path)

        db = open_db()
        results = []
        try:
            for step in request["steps"]:
                table = db.table(step.get("table", "_default"))
                op = step["op"]
                try:
                    if op == "insert":
                        result = table.insert(step["data"])
                    elif op == "insert_doc":
                        result = table.insert(Document(step["data"], doc_id=step["id"]))
                    elif op == "bulk":
                        docs = [Document(x["data"], doc_id=x["id"]) if "id" in x else x["data"] for x in step["documents"]]
                        result = table.insert_multiple(iter(docs))
                    elif op == "upsert_doc":
                        result = table.upsert(Document(step["data"], doc_id=step["id"]))
                    elif op == "upsert_query":
                        result = table.upsert(step["data"], query(step["query"]))
                    elif op == "get_many":
                        result = table.get(doc_ids=step["ids"])
                    elif op == "get":
                        result = table.get(doc_id=step["id"])
                    elif op == "all":
                        result = table.all()
                    elif op == "search":
                        result = table.search(query(step["query"]))
                    elif op == "dynamic_map":
                        state = [step["first"]]
                        q = Query()[step["field"]].map(lambda x: x + state[0]) >= step["threshold"]
                        first = table.search(q)
                        state[0] = step["second"]
                        result = [first, table.search(q)]
                    elif op == "update":
                        result = table.update(step["data"], query(step["query"]))
                    elif op == "remove":
                        result = table.remove(query(step["query"]))
                    elif op == "reopen":
                        db.close()
                        db = open_db()
                        result = True
                    else:
                        raise ValueError("Unknown operation")
                    results.append(view(result))
                except Exception as exc:
                    results.append({"error": type(exc).__name__})
        finally:
            db.close()
    return {"results": results}
