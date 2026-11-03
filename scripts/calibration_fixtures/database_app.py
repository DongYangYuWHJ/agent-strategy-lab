"""Read-only protocol adapter; all database behavior belongs in tinydb."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from copy import deepcopy
import tempfile
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage, JSONStorage
from tinydb.middlewares import CachingMiddleware


def run(request):
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
        backend = request.get("backend", "memory")
        path = str(Path(directory) / "db.json")
        handles, saved = {}, {}

        def open_db():
            raw = (MemoryStorage() if backend == "memory" else
                   CachingMiddleware(JSONStorage)(path) if backend == "cached" else JSONStorage(path))
            class Observed:
                writes = 0
                def read(self):
                    return raw.read()
                def write(self, data):
                    self.writes += 1
                    raw.write(data)
                def close(self):
                    raw.close()
            observed = Observed()
            return TinyDB(storage=lambda: observed), observed

        db, observed = open_db()

        def table(name):
            return handles.setdefault(name, db.table(name))

        def view(rows):
            return [{"id": row.doc_id, "data": dict(row)} for row in sorted(rows, key=lambda row: row.doc_id)]

        def execute(step):
            nonlocal db, observed
            name = step.get("table", "_default")
            op = step["op"]
            if op == "insert":
                return table(name).insert(deepcopy(step["data"]))
            if op == "all":
                return view(table(name).all())
            if op == "search":
                return view(table(name).search(Query()[step["field"]] == step["value"]))
            if op == "update":
                return table(name).update(deepcopy(step["data"]), doc_ids=step["ids"])
            if op == "remove":
                return table(name).remove(doc_ids=step["ids"])
            if op == "writes":
                return observed.writes
            if op == "backing":
                return deepcopy(observed.read() or {})
            if op == "fail":
                raise RuntimeError("requested abort")
            if op == "transaction":
                with db.transaction() as entered:
                    if entered is not db:
                        raise ValueError("transaction must yield database")
                    return [invoke(child) for child in step["steps"]]
            if op == "export":
                saved[step.get("name", "snapshot")] = db.export_snapshot()
                return deepcopy(saved[step.get("name", "snapshot")])
            if op == "restore":
                value = deepcopy(step.get("snapshot", saved.get(step.get("name", "snapshot"))))
                result = db.restore_snapshot(value, mode=step.get("mode", "replace"), dry_run=step.get("dry_run", False))
                if step.get("mutate_input"):
                    for rows in value["tables"].values():
                        for row in rows:
                            row["data"]["injected"] = True
                return result
            if op == "mutate_export":
                for rows in saved[step.get("name", "snapshot")]["tables"].values():
                    for row in rows:
                        row["data"]["injected"] = True
                return True
            if op == "reopen":
                if backend == "memory":
                    raise ValueError("reopen requires file backend")
                db.close()
                db, observed = open_db()
                handles.clear()
                return True
            raise ValueError("Unknown operation")

        def invoke(step):
            if not step.get("catch", False):
                return execute(step)
            try:
                return execute(step)
            except Exception as exc:
                return {"error": type(exc).__name__}

        try:
            results = [invoke(step) for step in request["steps"]]
            state = {name: view(db.table(name).all()) for name in sorted(db.tables())}
            return {"results": results, "state": state}
        finally:
            db.close()
