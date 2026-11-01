from copy import deepcopy
import base64
import json
import os
from pathlib import Path
from check_client import load_submission

def equivalent(actual, expected):
    if type(expected) is dict:
        return type(actual) is dict and actual.keys() == expected.keys() and all(equivalent(actual[k], v) for k, v in expected.items())
    if type(expected) is list:
        return type(actual) is list and len(actual) == len(expected) and all(equivalent(a, e) for a, e in zip(actual, expected))
    if type(expected) is bool:
        return type(actual) is bool and actual == expected
    if type(expected) in (int, float):
        return type(actual) in (int, float) and actual == expected
    return type(actual) is type(expected) and actual == expected

def normalize_cursor(value):
    if type(value) is not dict or value.get("next_cursor") is None:
        return value
    try:
        token = value["next_cursor"]
        assert type(token) is str
        payload = json.loads(base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True))
        assert type(payload) is dict and set(payload) == {"v", "ts", "id"}
        assert type(payload["v"]) is int and payload["v"] == 1
        assert type(payload["ts"]) is int and type(payload["id"]) is int and payload["id"] >= 1
        return {**value, "next_cursor": payload}
    except Exception as exc:
        raise AssertionError("Invalid output cursor") from exc

cases = json.loads('[{"request": {"notes": [{"id": "a", "text": "first"}], "operations": [{"op": "list"}]}, "expected": {"results": [[{"id": "a", "text": "first", "deleted": false}]]}}, {"request": {"notes": [{"id": "a", "text": "first"}], "operations": [{"op": "delete", "id": "a"}, {"op": "list"}]}, "expected": {"results": [{"ok": true}, []]}}, {"request": {"notes": [{"id": "a", "text": "first"}], "operations": [{"op": "delete", "id": "a"}, {"op": "restore", "id": "a"}, {"op": "get", "id": "a"}]}, "expected": {"results": [{"ok": true}, {"ok": true}, {"id": "a", "text": "first", "deleted": false}]}}]')
submission = load_submission(Path(os.environ['LAB_WORKSPACE']) / 'app.py')
for index, item in enumerate(cases, 1):
    request = deepcopy(item['request'])
    before = json.dumps(request, sort_keys=True)
    actual = submission.run(request)
    assert json.dumps(request, sort_keys=True) == before, f'Input mutated at case {index}'
    expected = item['expected']
    assert equivalent(actual, expected), f'Wrong result at case {index}: expected {expected!r}, got {actual!r}'
print(f'Executed {len(cases)} repository cases successfully')
