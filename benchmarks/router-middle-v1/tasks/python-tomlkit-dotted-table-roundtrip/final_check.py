from collections import defaultdict
from copy import deepcopy
import json
import os
from pathlib import Path
from check_client import load_submission

cases = json.loads('[{"group": "promoted-table", "request": {"text": "a.b = 1\\n", "updates": [[["a", "c"], {}], [["z"], 2]]}, "expected": {"document": {"a": {"b": 1, "c": {}}, "z": 2}}}, {"group": "regular-table", "request": {"text": "[a]\\nb = 1\\n", "updates": [[["z"], 2]]}, "expected": {"document": {"a": {"b": 1}, "z": 2}}}, {"group": "deep-promotion", "request": {"text": "build.worker.threads = 2\\n", "updates": [[["build", "worker", "limits"], {"seconds": 5}], [["enabled"], true], [["label"], "local"]]}, "expected": {"document": {"build": {"worker": {"threads": 2, "limits": {"seconds": 5}}}, "enabled": true, "label": "local"}}}, {"group": "multiple-tables", "request": {"text": "name = \\"dev\\"\\na.b = 1\\n\\n[existing]\\nx = 5\\n", "updates": [[["a", "new"], {"flag": true}], [["count"], 7], [["ready"], false]]}, "expected": {"document": {"name": "dev", "a": {"b": 1, "new": {"flag": true}}, "existing": {"x": 5}, "count": 7, "ready": false}}}, {"group": "inline-order", "request": {"text": "# keep this\\nservice.port = 9000 # default\\n", "updates": [[["active"], true]], "inspect_text": true}, "expected": {"document": {"service": {"port": 9000}, "active": true}, "text": "# keep this\\nservice.port = 9000 # default\\nactive = true\\n"}}, {"group": "inline-deep-order", "request": {"text": "service.http.port = 8080\\n", "updates": [[["active"], false]], "inspect_text": true}, "expected": {"document": {"service": {"http": {"port": 8080}}, "active": false}, "text": "service.http.port = 8080\\nactive = false\\n"}}]')
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
