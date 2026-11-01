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

cases = json.loads('[{"request": {"notes": [{"id": "a", "text": "first"}], "operations": [{"op": "list"}]}, "expected": {"results": [[{"id": "a", "text": "first", "deleted": false}]]}}, {"request": {"notes": [{"id": "a", "text": "first"}], "operations": [{"op": "delete", "id": "a"}, {"op": "list"}]}, "expected": {"results": [{"ok": true}, []]}}, {"request": {"notes": [{"id": "a", "text": "first"}], "operations": [{"op": "delete", "id": "a"}, {"op": "restore", "id": "a"}, {"op": "get", "id": "a"}]}, "expected": {"results": [{"ok": true}, {"ok": true}, {"id": "a", "text": "first", "deleted": false}]}}, {"request": {"notes": [{"id": "a", "text": "first"}], "operations": [{"op": "delete", "id": "a"}, {"op": "get", "id": "a"}, {"op": "get", "id": "a", "include_deleted": true}]}, "expected": {"results": [{"ok": true}, {"error": "not_found"}, {"id": "a", "text": "first", "deleted": true}]}}, {"request": {"notes": [{"id": "a", "text": "first"}], "operations": [{"op": "delete", "id": "a"}, {"op": "delete", "id": "a"}, {"op": "create", "id": "a", "text": "replacement"}]}, "expected": {"results": [{"ok": true}, {"ok": true}, {"error": "conflict"}]}}, {"request": {"notes": [{"id": "a", "text": "first"}], "operations": [{"op": "delete", "id": "a"}, {"op": "update", "id": "a", "text": "bad"}, {"op": "restore", "id": "a"}, {"op": "get", "id": "a"}]}, "expected": {"results": [{"ok": true}, {"error": "not_found"}, {"ok": true}, {"id": "a", "text": "first", "deleted": false}]}}, {"request": {"notes": [], "operations": [{"op": "get", "id": "x"}, {"op": "delete", "id": "x"}, {"op": "restore", "id": "x"}, {"op": "update", "id": "x", "text": "bad"}]}, "expected": {"results": [{"error": "not_found"}, {"error": "not_found"}, {"error": "not_found"}, {"error": "not_found"}]}}, {"request": {"notes": [{"id": "b", "text": "B", "deleted": true}, {"id": "a", "text": "A", "deleted": false}], "operations": [{"op": "list"}, {"op": "list", "include_deleted": true}, {"op": "restore", "id": "b"}, {"op": "list"}]}, "expected": {"results": [[{"id": "a", "text": "A", "deleted": false}], [{"id": "b", "text": "B", "deleted": true}, {"id": "a", "text": "A", "deleted": false}], {"ok": true}, [{"id": "b", "text": "B", "deleted": false}, {"id": "a", "text": "A", "deleted": false}]]}}, {"request": {"notes": [], "operations": [{"op": "create", "id": "x", "text": "old"}, {"op": "update", "id": "x", "text": "new"}, {"op": "create", "id": "x", "text": "dup"}, {"op": "restore", "id": "x"}]}, "expected": {"results": [{"id": "x", "text": "old", "deleted": false}, {"id": "x", "text": "new", "deleted": false}, {"error": "conflict"}, {"ok": true}]}}, {"request": {"notes": [{"id": "a", "text": "A", "deleted": false}, {"id": "b", "text": "B", "deleted": false}, {"id": "c", "text": "C", "deleted": false}], "operations": [{"op": "delete", "id": "b"}, {"op": "create", "id": "d", "text": "D"}, {"op": "list"}, {"op": "list", "include_deleted": true}]}, "expected": {"results": [{"ok": true}, {"id": "d", "text": "D", "deleted": false}, [{"id": "a", "text": "A", "deleted": false}, {"id": "c", "text": "C", "deleted": false}, {"id": "d", "text": "D", "deleted": false}], [{"id": "a", "text": "A", "deleted": false}, {"id": "b", "text": "B", "deleted": true}, {"id": "c", "text": "C", "deleted": false}, {"id": "d", "text": "D", "deleted": false}]]}}, {"request": {}, "expected": {"results": []}}, {"request": {"notes": [{"id": "note-0", "text": "\\u6b63\\u6587-0", "deleted": false}], "operations": [{"op": "update", "id": "note-0", "text": "\\u6b63\\u6587-0!"}, {"op": "delete", "id": "note-0"}, {"op": "restore", "id": "note-0"}, {"op": "list"}]}, "expected": {"results": [{"id": "note-0", "text": "\\u6b63\\u6587-0!", "deleted": false}, {"ok": true}, {"ok": true}, [{"id": "note-0", "text": "\\u6b63\\u6587-0!", "deleted": false}]]}}, {"request": {"notes": [{"id": "note-1", "text": "\\u6b63\\u6587-1", "deleted": false}], "operations": [{"op": "update", "id": "note-1", "text": "\\u6b63\\u6587-1!"}, {"op": "delete", "id": "note-1"}, {"op": "restore", "id": "note-1"}, {"op": "list"}]}, "expected": {"results": [{"id": "note-1", "text": "\\u6b63\\u6587-1!", "deleted": false}, {"ok": true}, {"ok": true}, [{"id": "note-1", "text": "\\u6b63\\u6587-1!", "deleted": false}]]}}, {"request": {"notes": [{"id": "note-2", "text": "\\u6b63\\u6587-2", "deleted": false}], "operations": [{"op": "update", "id": "note-2", "text": "\\u6b63\\u6587-2!"}, {"op": "delete", "id": "note-2"}, {"op": "restore", "id": "note-2"}, {"op": "list"}]}, "expected": {"results": [{"id": "note-2", "text": "\\u6b63\\u6587-2!", "deleted": false}, {"ok": true}, {"ok": true}, [{"id": "note-2", "text": "\\u6b63\\u6587-2!", "deleted": false}]]}}, {"request": {"notes": [{"id": "note-3", "text": "\\u6b63\\u6587-3", "deleted": false}], "operations": [{"op": "update", "id": "note-3", "text": "\\u6b63\\u6587-3!"}, {"op": "delete", "id": "note-3"}, {"op": "restore", "id": "note-3"}, {"op": "list"}]}, "expected": {"results": [{"id": "note-3", "text": "\\u6b63\\u6587-3!", "deleted": false}, {"ok": true}, {"ok": true}, [{"id": "note-3", "text": "\\u6b63\\u6587-3!", "deleted": false}]]}}, {"request": {"notes": [{"id": "note-4", "text": "\\u6b63\\u6587-4", "deleted": false}], "operations": [{"op": "update", "id": "note-4", "text": "\\u6b63\\u6587-4!"}, {"op": "delete", "id": "note-4"}, {"op": "restore", "id": "note-4"}, {"op": "list"}]}, "expected": {"results": [{"id": "note-4", "text": "\\u6b63\\u6587-4!", "deleted": false}, {"ok": true}, {"ok": true}, [{"id": "note-4", "text": "\\u6b63\\u6587-4!", "deleted": false}]]}}]')
submission = load_submission(Path(os.environ['LAB_WORKSPACE']) / 'app.py')
for index, item in enumerate(cases, 1):
    request = deepcopy(item['request'])
    before = json.dumps(request, sort_keys=True)
    actual = submission.run(request)
    assert json.dumps(request, sort_keys=True) == before, f'Input mutated at case {index}'
    expected = item['expected']
    assert equivalent(actual, expected), f'Wrong result at case {index}: expected {expected!r}, got {actual!r}'
print(f'Executed {len(cases)} repository cases successfully')
