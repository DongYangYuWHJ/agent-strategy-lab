import json
import unittest
from app import run
CASES = json.loads('[{"request": {"mode": "claims", "payload": {"user": 7}}, "expected": {"value": {"user": 7}}, "group": "claims"}, {"request": {"mode": "claims", "payload": {"user": 7}, "check_at": 121}, "expected": {"error": "SignatureExpired"}, "group": "expiry"}, {"request": {"mode": "regression", "payload": [1, null]}, "expected": {"value": [1, null]}, "group": "regression"}, {"request": {"mode": "migration", "origin": {"keys": ["old"], "salt": "old-salt", "digest": "sha1"}, "legacy": [{"keys": ["old"], "salt": "old-salt", "digest": "sha1"}], "payload": {"user": 7}}, "expected": {"value": {"user": 7}, "current_value": {"user": 7}, "source": 1, "old_accepts": false}, "group": "migration"}, {"request": {"mode": "migration", "origin": {"keys": ["old"], "salt": "old-salt", "digest": "sha1"}, "legacy": [{"keys": ["old"], "salt": "old-salt", "digest": "sha1"}], "payload": {"user": 7}, "kind": "plain"}, "expected": {"value": {"user": 7}, "current_value": {"user": 7}, "source": 1, "old_accepts": false}, "group": "serialization"}, {"request": {"mode": "regression", "payload": {"a": 1}}, "expected": {"value": {"a": 1}}, "group": "regression"}]')

class PublicScenarios(unittest.TestCase):
    def test_contract(self):
        for item in CASES:
            with self.subTest(group=item['group']):
                self.assertEqual(run(item['request']), item['expected'])
