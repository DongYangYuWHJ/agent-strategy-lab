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

CASES = json.loads('[{"request": {"records": [{"id": 2, "created_at": 1, "payload": "second"}, {"id": 1, "created_at": 1, "payload": "first"}, {"id": 3, "created_at": 2, "payload": "third"}], "limit": 2}, "expected": {"items": [{"id": 1, "created_at": 1, "payload": "first"}, {"id": 2, "created_at": 1, "payload": "second"}], "next_cursor": "eyJ2IjoxLCJ0cyI6MSwiaWQiOjJ9"}}, {"request": {"records": [{"id": 2, "created_at": 1, "payload": "second"}, {"id": 1, "created_at": 1, "payload": "first"}, {"id": 3, "created_at": 2, "payload": "third"}], "limit": 2, "cursor": "eyJ2IjoxLCJ0cyI6MSwiaWQiOjF9"}, "expected": {"items": [{"id": 2, "created_at": 1, "payload": "second"}, {"id": 3, "created_at": 2, "payload": "third"}], "next_cursor": null}}, {"request": {"records": [], "limit": 2}, "expected": {"items": [], "next_cursor": null}}]')
class SmokeTests(unittest.TestCase):
    def test_public_contract(self):
        for index, item in enumerate(CASES, 1):
            with self.subTest(case=index):
                request = deepcopy(item['request'])
                before = json.dumps(request, sort_keys=True)
                actual = run(request)
                self.assertEqual(json.dumps(request, sort_keys=True), before)
                actual, expected = normalize_cursor(actual), normalize_cursor(item['expected'])
                self.assertTrue(equivalent(actual, expected), (actual, expected))
if __name__ == '__main__':
    unittest.main()
