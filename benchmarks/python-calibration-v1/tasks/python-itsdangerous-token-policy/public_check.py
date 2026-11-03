from collections import defaultdict
from copy import deepcopy
import json
import os
from pathlib import Path
from check_client import load_submission

cases = json.loads('[{"request": {"mode": "claims", "payload": {"user": 7}}, "expected": {"value": {"user": 7}}, "group": "claims"}, {"request": {"mode": "claims", "payload": {"user": 7}, "check_at": 121}, "expected": {"error": "SignatureExpired"}, "group": "expiry"}, {"request": {"mode": "regression", "payload": [1, null]}, "expected": {"value": [1, null]}, "group": "regression"}]')
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
