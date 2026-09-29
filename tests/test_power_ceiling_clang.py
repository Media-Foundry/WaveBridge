import copy
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.power_ceiling import check


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class PowerCeilingClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/power_ceiling.cpp", shutil.which("clang++"),
                         ["-std=c++17"], "renamed", full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]
        cls.ids = {n["name"]: n["id"] for n in _walk(cls.root) if n.get("kind") == "FunctionDecl"}

    def test_renamed_and_postfix_real_sources(self):
        for name in ("renamed", "postfix"):
            result = check(self.root, self.ids[name], 65, 128)
            self.assertEqual(result["status"], "checked", result)
            self.assertEqual(result["result_interval"], {"lower": 7, "upper": 7})
            self.assertFalse(result["input_domain_established_at_call"])
            self.assertFalse(result["source_program_checked"])
            self.assertFalse(result["deployable"])

    def test_semantic_changes_and_static_storage_are_unknown(self):
        for name in ("wrong_equal", "wrong_write", "persistent"):
            result = check(self.root, self.ids[name], 1, 1024)
            self.assertEqual(result["status"], "unknown", result)

    def test_finite_domain_matches_enumerated_recurrence(self):
        for upper in range(1, 65):
            result = check(self.root, self.ids["renamed"], 1, upper)
            counter = 0
            while (1 << counter) < upper:
                counter += 1
            self.assertEqual(result["result_interval"], {"lower": 0, "upper": counter})

    def test_missing_and_unsafe_domain_is_not_assumed(self):
        for lower, upper in ((0, 1), (-1, 5), (1, 1 << 31), (4, 3), (True, 10)):
            result = check(self.root, self.ids["renamed"], lower, upper)
            self.assertEqual(result["status"], "unknown", result)
        result = check(self.root, self.ids["renamed"], 1, 1 << 30)
        self.assertEqual(result["result_interval"], {"lower": 0, "upper": 30})

    def test_identity_conflict_wrong_reference_and_immutability(self):
        before = copy.deepcopy(self.root)
        check(self.root, self.ids["renamed"], 1, 10)
        self.assertEqual(before, self.root)
        for mutation in ("duplicate", "reference"):
            root = copy.deepcopy(self.root)
            function = next(n for n in _walk(root) if n.get("id") == self.ids["renamed"])
            if mutation == "duplicate":
                root["inner"].append(copy.deepcopy(function))
            else:
                reference = next(n for n in _walk(function) if n.get("kind") == "DeclRefExpr")
                reference["referencedDecl"]["id"] = "wrong"
            self.assertEqual(check(root, self.ids["renamed"], 1, 10)["status"], "unknown")

    def test_budget_and_small_integer_boundaries(self):
        for budget in (0, True, 1, 10_000_001):
            self.assertEqual(check(self.root, self.ids["renamed"], 1, 10,
                                   max_ast_nodes=budget)["status"], "unknown")
        for bits in range(2, 9):
            maximum = 1 << (bits - 2)
            result = check(self.root, self.ids["renamed"], 1, maximum, int_bits=bits)
            self.assertEqual(result["result_interval"], {"lower": 0, "upper": bits - 2})
            self.assertEqual(check(self.root, self.ids["renamed"], 1, maximum + 1,
                                   int_bits=bits)["status"], "unknown")
