import json
import unittest
from app import run
CASES = json.loads('[{"request": {"steps": [{"op": "transaction", "steps": [{"op": "insert", "data": {"n": 1}, "table": "_default"}, {"op": "insert", "data": {"n": 2}, "table": "other"}], "catch": false}, {"op": "writes"}], "backend": "memory"}, "expected": {"results": [[1, 1], 1], "state": {"_default": [{"id": 1, "data": {"n": 1}}], "other": [{"id": 1, "data": {"n": 2}}]}}, "group": "commit"}, {"request": {"steps": [{"op": "insert", "data": {"n": 1}, "table": "_default"}, {"op": "transaction", "steps": [{"op": "insert", "data": {"n": 2}, "table": "_default"}, {"op": "fail"}], "catch": true}, {"op": "all"}], "backend": "memory"}, "expected": {"results": [1, {"error": "RuntimeError"}, [{"id": 1, "data": {"n": 1}}]], "state": {"_default": [{"id": 1, "data": {"n": 1}}]}}, "group": "rollback"}, {"request": {"steps": [{"op": "insert", "data": {"n": 1}, "table": "_default"}, {"op": "update", "ids": [1], "data": {"n": 3}}, {"op": "all"}], "backend": "memory"}, "expected": {"results": [1, [1], [{"id": 1, "data": {"n": 3}}]], "state": {"_default": [{"id": 1, "data": {"n": 3}}]}}, "group": "regression"}]')

class PublicScenarios(unittest.TestCase):
    def test_contract(self):
        for item in CASES:
            with self.subTest(group=item['group']):
                self.assertEqual(run(item['request']), item['expected'])
