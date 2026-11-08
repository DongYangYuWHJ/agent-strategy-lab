import json
import unittest

from app import run

CASES = json.loads('[{"group": "promoted-table", "request": {"text": "a.b = 1\\n", "updates": [[["a", "c"], {}], [["z"], 2]]}, "expected": {"document": {"a": {"b": 1, "c": {}}, "z": 2}}}, {"group": "regular-table", "request": {"text": "[a]\\nb = 1\\n", "updates": [[["z"], 2]]}, "expected": {"document": {"a": {"b": 1}, "z": 2}}}]')


class PublicScenarios(unittest.TestCase):
    def test_contract(self):
        for item in CASES:
            with self.subTest(group=item["group"]):
                self.assertEqual(run(item["request"]), item["expected"])
