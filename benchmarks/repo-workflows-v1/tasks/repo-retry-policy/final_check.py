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

cases = json.loads('[{"request": {"responses": [{"status": 503}, {"status": 200, "body": "ok"}], "max_attempts": 3, "base_delay": 1}, "expected": {"status": 200, "body": "ok", "attempts": 2, "delays": [1]}}, {"request": {"responses": [{"status": 404}], "max_attempts": 3, "base_delay": 1}, "expected": {"status": 404, "body": null, "attempts": 1, "delays": []}}, {"request": {"responses": [{"status": 500}], "max_attempts": 1, "base_delay": 2}, "expected": {"status": 500, "body": null, "attempts": 1, "delays": []}}, {"request": {"responses": [{"status": 429, "retry_after": 0}, {"status": 200}], "max_attempts": 3, "base_delay": 5}, "expected": {"status": 200, "body": null, "attempts": 2, "delays": [0]}}, {"request": {"responses": [{"status": 503, "retry_after": 2.5}, {"status": 200}], "max_attempts": 2, "base_delay": 1}, "expected": {"status": 200, "body": null, "attempts": 2, "delays": [2.5]}}, {"request": {"responses": [{"status": 502}, {"status": 503}, {"status": 204}], "max_attempts": 4, "base_delay": 0.5}, "expected": {"status": 204, "body": null, "attempts": 3, "delays": [0.5, 1]}}, {"request": {"responses": [{"status": 500}], "max_attempts": 3, "base_delay": 2}, "expected": {"status": 500, "body": null, "attempts": 3, "delays": [2, 4]}}, {"request": {"responses": [{"status": 200, "body": {"id": 9}}], "max_attempts": 4, "base_delay": 10}, "expected": {"status": 200, "body": {"id": 9}, "attempts": 1, "delays": []}}, {"request": {"responses": [{"status": 429, "retry_after": -2}, {"status": 200}], "max_attempts": 2, "base_delay": 3}, "expected": {"status": 200, "body": null, "attempts": 2, "delays": [3]}}, {"request": {"responses": [{"status": 503, "retry_after": "2"}, {"status": 200}], "max_attempts": 2, "base_delay": 3}, "expected": {"status": 200, "body": null, "attempts": 2, "delays": [3]}}, {"request": {"responses": [{"status": 503, "retry_after": true}, {"status": 200}], "max_attempts": 2, "base_delay": 3}, "expected": {"status": 200, "body": null, "attempts": 2, "delays": [3]}}, {"request": {"responses": [{"status": 400}], "max_attempts": 4, "base_delay": 1}, "expected": {"status": 400, "body": null, "attempts": 1, "delays": []}}, {"request": {"responses": [{"status": 401}], "max_attempts": 4, "base_delay": 1}, "expected": {"status": 401, "body": null, "attempts": 1, "delays": []}}, {"request": {"responses": [{"status": 403}], "max_attempts": 4, "base_delay": 1}, "expected": {"status": 403, "body": null, "attempts": 1, "delays": []}}, {"request": {"responses": [{"status": 408}], "max_attempts": 4, "base_delay": 1}, "expected": {"status": 408, "body": null, "attempts": 1, "delays": []}}, {"request": {"responses": [{"status": 418}], "max_attempts": 4, "base_delay": 1}, "expected": {"status": 418, "body": null, "attempts": 1, "delays": []}}, {"request": {"responses": [{"status": 501}], "max_attempts": 4, "base_delay": 1}, "expected": {"status": 501, "body": null, "attempts": 1, "delays": []}}, {"request": {"responses": [{"status": 505}], "max_attempts": 4, "base_delay": 1}, "expected": {"status": 505, "body": null, "attempts": 1, "delays": []}}, {"request": {"responses": [{"status": 302}], "max_attempts": 4, "base_delay": 1}, "expected": {"status": 302, "body": null, "attempts": 1, "delays": []}}, {"request": {"responses": [{"status": 200}], "max_attempts": 0}, "expected": {"error": "invalid_retry_options"}}, {"request": {"responses": [{"status": 200}], "max_attempts": -1}, "expected": {"error": "invalid_retry_options"}}, {"request": {"responses": [{"status": 200}], "max_attempts": true}, "expected": {"error": "invalid_retry_options"}}, {"request": {"responses": [{"status": 200}], "max_attempts": 1.5}, "expected": {"error": "invalid_retry_options"}}, {"request": {"responses": [{"status": 200}], "base_delay": -1}, "expected": {"error": "invalid_retry_options"}}, {"request": {"responses": [{"status": 200}], "base_delay": true}, "expected": {"error": "invalid_retry_options"}}, {"request": {"responses": [{"status": 200}], "base_delay": "1"}, "expected": {"error": "invalid_retry_options"}}, {"request": {"responses": [{"status": 200}], "base_delay": null}, "expected": {"error": "invalid_retry_options"}}, {"request": {"responses": [{"status": 500}, {"status": 200}], "max_attempts": 2, "base_delay": 0}, "expected": {"status": 200, "body": null, "attempts": 2, "delays": [0]}}, {"request": {"responses": [{"status": 503}, {"status": 200}]}, "expected": {"status": 200, "body": null, "attempts": 2, "delays": [1]}}, {"request": {"responses": [{"status": 500}]}, "expected": {"status": 500, "body": null, "attempts": 3, "delays": [1, 2]}}]')
submission = load_submission(Path(os.environ['LAB_WORKSPACE']) / 'app.py')
for index, item in enumerate(cases, 1):
    request = deepcopy(item['request'])
    before = json.dumps(request, sort_keys=True)
    actual = submission.run(request)
    assert json.dumps(request, sort_keys=True) == before, f'Input mutated at case {index}'
    expected = item['expected']
    assert equivalent(actual, expected), f'Wrong result at case {index}: expected {expected!r}, got {actual!r}'
print(f'Executed {len(cases)} repository cases successfully')
