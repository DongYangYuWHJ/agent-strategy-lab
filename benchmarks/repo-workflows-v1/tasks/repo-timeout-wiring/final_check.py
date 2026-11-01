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

cases = json.loads('[{"request": {}, "expected": {"target": "status", "timeout_ms": 1000, "timeout_seconds": 1.0, "headers": {"User-Agent": "lab-client/1"}}}, {"request": {"argv": ["--timeout-ms", "250", "--target", "health"], "config": {"timeout_ms": 99}}, "expected": {"target": "health", "timeout_ms": 250, "timeout_seconds": 0.25, "headers": {"User-Agent": "lab-client/1"}}}, {"request": {"argv": ["--timeout-ms", "0"]}, "expected": {"target": "status", "timeout_ms": 0, "timeout_seconds": null, "headers": {"User-Agent": "lab-client/1"}}}, {"request": {"config": {"timeout_ms": 400}}, "expected": {"target": "status", "timeout_ms": 400, "timeout_seconds": 0.4, "headers": {"User-Agent": "lab-client/1"}}}, {"request": {"env": {"APP_TIMEOUT_MS": "75"}, "config": {"timeout_ms": 900}}, "expected": {"target": "status", "timeout_ms": 75, "timeout_seconds": 0.075, "headers": {"User-Agent": "lab-client/1"}}}, {"request": {"argv": ["--timeout-ms", "10"], "env": {"APP_TIMEOUT_MS": "20"}, "config": {"timeout_ms": 30}}, "expected": {"target": "status", "timeout_ms": 10, "timeout_seconds": 0.01, "headers": {"User-Agent": "lab-client/1"}}}, {"request": {"env": {"APP_TIMEOUT_MS": "0"}}, "expected": {"target": "status", "timeout_ms": 0, "timeout_seconds": null, "headers": {"User-Agent": "lab-client/1"}}}, {"request": {"config": {"timeout_ms": " 1250 "}}, "expected": {"target": "status", "timeout_ms": 1250, "timeout_seconds": 1.25, "headers": {"User-Agent": "lab-client/1"}}}, {"request": {"argv": ["--target", "metrics"]}, "expected": {"target": "metrics", "timeout_ms": 1000, "timeout_seconds": 1.0, "headers": {"User-Agent": "lab-client/1"}}}, {"request": {"config": {"timeout_ms": -1}}, "expected": {"error": "invalid_timeout"}}, {"request": {"config": {"timeout_ms": true}}, "expected": {"error": "invalid_timeout"}}, {"request": {"config": {"timeout_ms": 2.5}}, "expected": {"error": "invalid_timeout"}}, {"request": {"config": {"timeout_ms": ""}}, "expected": {"error": "invalid_timeout"}}, {"request": {"config": {"timeout_ms": "2.5"}}, "expected": {"error": "invalid_timeout"}}, {"request": {"config": {"timeout_ms": "+3"}}, "expected": {"error": "invalid_timeout"}}, {"request": {"config": {"timeout_ms": "-2"}}, "expected": {"error": "invalid_timeout"}}, {"request": {"config": {"timeout_ms": null}}, "expected": {"error": "invalid_timeout"}}, {"request": {"env": {"APP_TIMEOUT_MS": ""}, "config": {"timeout_ms": 200}}, "expected": {"error": "invalid_timeout"}}, {"request": {"env": {"APP_TIMEOUT_MS": "-3"}, "config": {"timeout_ms": 200}}, "expected": {"error": "invalid_timeout"}}, {"request": {"env": {"APP_TIMEOUT_MS": "bad"}, "config": {"timeout_ms": 200}}, "expected": {"error": "invalid_timeout"}}, {"request": {"config": {"timeout_ms": 0}}, "expected": {"target": "status", "timeout_ms": 0, "timeout_seconds": null, "headers": {"User-Agent": "lab-client/1"}}}, {"request": {"argv": ["--timeout-ms", "10"], "env": {"APP_TIMEOUT_MS": "bad"}}, "expected": {"target": "status", "timeout_ms": 10, "timeout_seconds": 0.01, "headers": {"User-Agent": "lab-client/1"}}}, {"request": {"env": {"APP_TIMEOUT_MS": "20"}, "config": {"timeout_ms": null}}, "expected": {"target": "status", "timeout_ms": 20, "timeout_seconds": 0.02, "headers": {"User-Agent": "lab-client/1"}}}, {"request": {"argv": ["--timeout-ms", "-1"]}, "expected": {"error": "invalid_timeout"}}]')
submission = load_submission(Path(os.environ['LAB_WORKSPACE']) / 'app.py')
for index, item in enumerate(cases, 1):
    request = deepcopy(item['request'])
    before = json.dumps(request, sort_keys=True)
    actual = submission.run(request)
    assert json.dumps(request, sort_keys=True) == before, f'Input mutated at case {index}'
    expected = item['expected']
    assert equivalent(actual, expected), f'Wrong result at case {index}: expected {expected!r}, got {actual!r}'
print(f'Executed {len(cases)} repository cases successfully')
