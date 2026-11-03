from copy import deepcopy
import json
import os
from pathlib import Path
from check_client import load_submission

cases = json.loads('[{"request": {"backend": "memory", "steps": [{"op": "insert_doc", "id": 10, "data": {"x": 1}}, {"op": "insert", "data": {"x": 2}}, {"op": "all"}]}, "expected": {"results": [10, 11, [{"id": 10, "data": {"x": 1}}, {"id": 11, "data": {"x": 2}}]]}}, {"request": {"backend": "memory", "steps": [{"op": "insert_doc", "id": 3, "data": {"x": 1}}, {"op": "upsert_doc", "id": 3, "data": {"y": 2}}, {"op": "get", "id": 3}]}, "expected": {"results": [3, [3], {"id": 3, "data": {"x": 1, "y": 2}}]}}, {"request": {"backend": "memory", "steps": [{"op": "insert", "data": {"name": "ALICE", "active": true}}, {"op": "search", "query": {"op": "lower_eq", "path": ["name"], "value": "alice"}}]}, "expected": {"results": [1, [{"id": 1, "data": {"name": "ALICE", "active": true}}]]}}, {"request": {"backend": "memory", "steps": [{"op": "insert", "data": {"x": 1}}, {"op": "search", "query": {"op": "fragment", "value": {"x": 1}}}, {"op": "get_many", "ids": [1]}]}, "expected": {"results": [1, [{"id": 1, "data": {"x": 1}}], [{"id": 1, "data": {"x": 1}}]]}}, {"request": {"backend": "cached", "steps": [{"op": "insert", "data": {"x": 9}}, {"op": "reopen"}, {"op": "all"}]}, "expected": {"results": [1, true, [{"id": 1, "data": {"x": 9}}]]}}]')
submission = load_submission(Path(os.environ["LAB_WORKSPACE"]) / "app.py")
failures = []
for index, item in enumerate(cases, 1):
    try:
        request = deepcopy(item["request"])
        actual = submission.run(request)
        assert actual == item["expected"], f"expected {item['expected']!r}, got {actual!r}"
    except Exception as exc:
        failures.append(f"case {index}: {str(exc)[:1200]}")
print(f"Passed {len(cases) - len(failures)}/{len(cases)} repository scenarios", flush=True)
assert not failures, "\n".join(failures)
