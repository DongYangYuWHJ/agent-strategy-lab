import json
import unittest

from app import run

CASES = json.loads('[{"group": "mixed-errors", "request": {"groups": {"all": [{}, "not a valid requirement!!!"]}, "target": "all", "method": "resolve"}, "expected": {"errors": ["InvalidDependencyGroupObject", "InvalidRequirement"]}}, {"group": "valid-order", "request": {"groups": {"all": ["alpha", {"include-group": "more"}, "alpha"], "more": ["beta>=1"]}, "target": "all", "method": "resolve"}, "expected": {"items": ["alpha", "beta>=1", "alpha"]}}]')


class PublicScenarios(unittest.TestCase):
    def test_contract(self):
        for item in CASES:
            with self.subTest(group=item["group"]):
                self.assertEqual(run(item["request"]), item["expected"])
