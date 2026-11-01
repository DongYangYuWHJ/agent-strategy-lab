import base64
import json
import unittest
from copy import deepcopy
from app import run

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

CASES = json.loads('[{"request": {"responses": [{"status": 503}, {"status": 200, "body": "ok"}], "max_attempts": 3, "base_delay": 1}, "expected": {"status": 200, "body": "ok", "attempts": 2, "delays": [1]}}, {"request": {"responses": [{"status": 404}], "max_attempts": 3, "base_delay": 1}, "expected": {"status": 404, "body": null, "attempts": 1, "delays": []}}, {"request": {"responses": [{"status": 500}], "max_attempts": 1, "base_delay": 2}, "expected": {"status": 500, "body": null, "attempts": 1, "delays": []}}]')
class SmokeTests(unittest.TestCase):
    def test_public_contract(self):
        for index, item in enumerate(CASES, 1):
            with self.subTest(case=index):
                request = deepcopy(item['request'])
                before = json.dumps(request, sort_keys=True)
                actual = run(request)
                self.assertEqual(json.dumps(request, sort_keys=True), before)
                expected = item['expected']
                self.assertTrue(equivalent(actual, expected), (actual, expected))
if __name__ == '__main__':
    unittest.main()
