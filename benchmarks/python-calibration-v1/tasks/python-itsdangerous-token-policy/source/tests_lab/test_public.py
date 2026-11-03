import json
import unittest
from app import run
CASES = json.loads('[{"request": {"mode": "claims", "payload": {"user": 7}}, "expected": {"value": {"user": 7}}, "group": "claims"}, {"request": {"mode": "claims", "payload": {"user": 7}, "check_at": 121}, "expected": {"error": "SignatureExpired"}, "group": "expiry"}, {"request": {"mode": "regression", "payload": [1, null]}, "expected": {"value": [1, null]}, "group": "regression"}]')

class PublicScenarios(unittest.TestCase):
    def test_contract(self):
        for item in CASES:
            with self.subTest(group=item['group']):
                self.assertEqual(run(item['request']), item['expected'])
