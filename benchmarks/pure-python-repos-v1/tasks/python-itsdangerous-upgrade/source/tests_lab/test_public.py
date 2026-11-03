import unittest
from app import run
import json
CASES = json.loads('[{"request": {"mode": "rotate", "keys": ["retired", "current"], "payload": {"user": "alice"}, "serializer": "url"}, "expected": {"legacy_values": [{"user": "alice"}, {"user": "alice"}], "current": {"user": "alice"}, "newest_accepts": true, "old_accepts": [false], "wrong_salt_rejected": true, "tamper_rejected": true}}, {"request": {"mode": "rotate", "keys": ["one-key"], "payload": [1, "two"], "serializer": "plain"}, "expected": {"legacy_values": [[1, "two"]], "current": [1, "two"], "newest_accepts": true, "old_accepts": [], "wrong_salt_rejected": true, "tamper_rejected": true}}, {"request": {"mode": "timed", "keys": ["retired", "current"], "signed_at": 1700000000, "now": 1700000010, "max_age": 20, "serializer": "url_timed", "payload": {"id": 1}}, "expected": {"value": {"id": 1}, "timestamp_utc": true, "timestamp_seconds": 1700000000}}, {"request": {"mode": "timed", "keys": ["one-key"], "signed_at": 1700000000, "now": 1700000021, "max_age": 20, "serializer": "timed", "payload": {"id": 1}}, "expected": {"error": "SignatureExpired", "timestamp_utc": true}}]')

class Smoke(unittest.TestCase):
    def test_public_scenarios(self):
        for item in CASES:
            with self.subTest(request=item['request']):
                self.assertEqual(run(item['request']), item['expected'])
