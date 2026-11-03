def export_snapshot(self):
    from copy import deepcopy
    data = self.storage.read() or {}
    return {"version": 1, "tables": {
        name: [{"id": int(key), "data": deepcopy(value)}
               for key, value in sorted(rows.items(), key=lambda pair: int(pair[0]))]
        for name, rows in sorted(data.items())}}


def restore_snapshot(self, snapshot, mode="replace", dry_run=False):
    from copy import deepcopy
    if mode not in ("replace", "merge", "reject") or type(dry_run) is not bool:
        raise ValueError("Invalid restore options")
    if (not isinstance(snapshot, dict) or set(snapshot) != {"version", "tables"}
            or type(snapshot["version"]) is not int or snapshot["version"] != 1
            or not isinstance(snapshot["tables"], dict)):
        raise ValueError("Invalid snapshot")
    incoming = {}
    for name, rows in snapshot["tables"].items():
        if not isinstance(name, str) or not name or not isinstance(rows, list):
            raise ValueError("Invalid table")
        table = incoming[name] = {}
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {"id", "data"}
                    or type(row["id"]) is not int or row["id"] <= 0
                    or not isinstance(row["data"], dict) or str(row["id"]) in table):
                raise ValueError("Invalid document")
            table[str(row["id"])] = deepcopy(row["data"])
    result = {} if mode == "replace" else deepcopy(self.storage.read() or {})
    for name, rows in incoming.items():
        target = result.setdefault(name, {})
        for key, value in rows.items():
            if mode == "reject" and key in target:
                raise ValueError("Document conflict")
            target[key] = value
    summary = {"tables": len(result), "documents": sum(len(rows) for rows in result.values())}
    if not dry_run:
        self.storage.write(deepcopy(result))
        for table in self._tables.values():
            table.clear_cache()
            table._next_id = None
    return summary
