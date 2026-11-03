import json
import unittest
from app import run
CASES = json.loads('[{"request": {"steps": [{"op": "atomic", "pairs": [["a", 1], ["b", 2]]}, {"op": "state"}]}, "expected": {"results": [2, {"items": [["a", 1], ["b", 2]], "maxsize": 3, "currsize": 2}]}, "group": "commit"}, {"request": {"steps": [{"op": "put", "key": "a", "value": 1}, {"op": "atomic", "pairs": []}, {"op": "get", "key": "a"}]}, "expected": {"results": [null, 0, 1]}, "group": "empty"}, {"request": {"steps": [{"op": "put", "key": "a", "value": 1}, {"op": "memo", "key": "b", "value": 2}]}, "expected": {"results": [null, [2, 2, 1]]}, "group": "regression"}]')

class PublicScenarios(unittest.TestCase):
    def test_contract(self):
        for item in CASES:
            with self.subTest(group=item['group']):
                self.assertEqual(run(item['request']), item['expected'])
