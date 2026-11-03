from collections import defaultdict
from copy import deepcopy
import json
import os
from pathlib import Path
from check_client import load_submission

cases = json.loads('[{"request": {"steps": [{"op": "transaction", "steps": [{"op": "insert", "data": {"n": 1}, "table": "_default"}, {"op": "insert", "data": {"n": 2}, "table": "other"}], "catch": false}, {"op": "writes"}], "backend": "memory"}, "expected": {"results": [[1, 1], 1], "state": {"_default": [{"id": 1, "data": {"n": 1}}], "other": [{"id": 1, "data": {"n": 2}}]}}, "group": "commit"}, {"request": {"steps": [{"op": "insert", "data": {"n": 1}, "table": "_default"}, {"op": "transaction", "steps": [{"op": "insert", "data": {"n": 2}, "table": "_default"}, {"op": "fail"}], "catch": true}, {"op": "all"}], "backend": "memory"}, "expected": {"results": [1, {"error": "RuntimeError"}, [{"id": 1, "data": {"n": 1}}]], "state": {"_default": [{"id": 1, "data": {"n": 1}}]}}, "group": "rollback"}, {"request": {"steps": [{"op": "insert", "data": {"n": 1}, "table": "_default"}, {"op": "update", "ids": [1], "data": {"n": 3}}, {"op": "all"}], "backend": "memory"}, "expected": {"results": [1, [1], [{"id": 1, "data": {"n": 3}}]], "state": {"_default": [{"id": 1, "data": {"n": 3}}]}}, "group": "regression"}, {"request": {"steps": [{"op": "insert", "data": {"n": 1}, "table": "_default"}, {"op": "export"}], "backend": "memory"}, "expected": {"results": [1, {"version": 1, "tables": {"_default": [{"id": 1, "data": {"n": 1}}]}}], "state": {"_default": [{"id": 1, "data": {"n": 1}}]}}, "group": "export"}, {"request": {"steps": [{"op": "insert", "data": {"n": 1}, "table": "_default"}, {"op": "restore", "snapshot": {"version": 1, "tables": {"_default": [{"id": 5, "data": {"n": 5}}]}}}, {"op": "all"}], "backend": "memory"}, "expected": {"results": [1, {"tables": 1, "documents": 1}, [{"id": 5, "data": {"n": 5}}]], "state": {"_default": [{"id": 5, "data": {"n": 5}}]}}, "group": "replace"}, {"request": {"steps": [{"op": "insert", "data": {"n": 1}, "table": "_default"}, {"op": "restore", "snapshot": {"version": 1, "tables": {"_default": [{"id": 5, "data": {"n": 5}}]}}, "dry_run": true}], "backend": "memory"}, "expected": {"results": [1, {"tables": 1, "documents": 1}], "state": {"_default": [{"id": 1, "data": {"n": 1}}]}}, "group": "dry-run"}, {"request": {"steps": [{"op": "insert", "data": {"n": 2}, "table": "_default"}, {"op": "remove", "ids": [1]}, {"op": "insert", "data": {"n": 3}, "table": "_default"}], "backend": "memory"}, "expected": {"results": [1, [1], 2], "state": {"_default": [{"id": 2, "data": {"n": 3}}]}}, "group": "regression"}]')
submission = load_submission(Path(os.environ["LAB_WORKSPACE"]) / "app.py")
groups = defaultdict(lambda: {"passed": 0, "total": 0})
failures = []
outputs = submission.run_many([deepcopy(item["request"]) for item in cases])
assert isinstance(outputs, list) and len(outputs) == len(cases), "Incomplete batch result"
for index, item in enumerate(cases, 1):
    group = groups[item["group"]]
    group["total"] += 1
    try:
        response = outputs[index - 1]
        assert response.get("ok") is True, f"submission error: {response}"
        actual = response["value"]
        assert actual == item["expected"], f"expected {item['expected']!r}, got {actual!r}"
        group["passed"] += 1
    except Exception as exc:
        failures.append(f"case {index} [{item['group']}]: {str(exc)[:1000]}")
print("LAB_GROUP_RESULTS " + json.dumps(dict(groups), sort_keys=True), flush=True)
print(f"Passed {len(cases) - len(failures)}/{len(cases)} scenarios", flush=True)
assert not failures, "\n".join(failures)
