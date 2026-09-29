import copy
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.power_ceiling import check, check_initialized_shift


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

    def shift_ids(self, name):
        function = next(n for n in _walk(self.root) if n.get("id") == self.ids[name])
        declarations = {n.get("name"): n["id"] for n in _walk(function)
                        if n.get("kind") in {"VarDecl", "ParmVarDecl"}}
        return declarations["exponent"], declarations["power"], declarations["input"]

    def test_adjacent_initializers_bind_call_and_shift(self):
        result = check_initialized_shift(self.root, *self.shift_ids("adjacent"), 65, 128)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["result_interval"], {"lower": 128, "upper": 128})
        self.assertTrue(result["exponent_preserved_to_shift"])
        self.assertTrue(result["subsequent_shift_checked"])
        self.assertFalse(result["argument_domain_verified"])
        self.assertFalse(result["deployable"])

    def test_entry_domain_is_freshly_carried_to_direct_call_and_shift(self):
        for name in ("adjacent", "guarded_entry"):
            result = check_initialized_shift(self.root, *self.shift_ids(name), 65, 128,
                                             entry_function_id=self.ids[name])
            self.assertEqual(result["status"], "checked", result)
            self.assertTrue(result["argument_domain_derived_from_entry"])
            self.assertTrue(result["initializer_prefix_preserves_parameter"])
            self.assertEqual(result["checks"]["parameter_entry"]["status"], "checked")
            self.assertEqual(result["result_interval"], {"lower": 128, "upper": 128})
            self.assertFalse(result["entry_domain_verified"])
            self.assertFalse(result["argument_domain_verified"])
            self.assertFalse(result["deployable"])

    def test_entry_or_initializer_mutation_blocks_composition(self):
        for name in ("modified_entry", "changed_call", "intervening"):
            result = check_initialized_shift(self.root, *self.shift_ids(name), 65, 128,
                                             entry_function_id=self.ids[name])
            self.assertEqual(result["status"], "unknown", (name, result))
            self.assertFalse(result["argument_domain_derived_from_entry"])
        # An at-read assumption can still check the old path; it cannot establish
        # preservation of the different entry value in the new path.
        self.assertEqual(check_initialized_shift(self.root, *self.shift_ids("modified_entry"),
                                                 65, 128)["status"], "checked")

    def test_wrong_entry_owner_and_unsupported_domain_fail_closed(self):
        result = check_initialized_shift(self.root, *self.shift_ids("adjacent"), 65, 128,
                                         entry_function_id=self.ids["guarded_entry"])
        self.assertEqual(result["status"], "unknown", result)
        result = check_initialized_shift(self.root, *self.shift_ids("adjacent"), 1, 8192,
                                         entry_function_id=self.ids["adjacent"])
        self.assertEqual(result["status"], "unknown", result)

    def test_intervening_write_wrong_shift_and_static_are_unknown(self):
        for name in ("intervening", "changed_base", "shifted_other", "static_result"):
            result = check_initialized_shift(self.root, *self.shift_ids(name), 65, 128)
            self.assertEqual(result["status"], "unknown", (name, result))

    def test_shift_wrong_argument_and_missing_domain(self):
        exponent, power, argument = self.shift_ids("adjacent")
        other = self.shift_ids("changed_base")[2]
        self.assertEqual(check_initialized_shift(self.root, exponent, power, other, 65, 128)["status"], "unknown")
        self.assertEqual(check_initialized_shift(self.root, exponent, power, argument, 0, 128)["status"], "unknown")

    def test_shared_literal_occurrence_is_not_global_identity_relaxation(self):
        selected = self.shift_ids("adjacent")
        for conflict in (False, True):
            root = copy.deepcopy(self.root)
            power = next(n for n in _walk(root) if n.get("id") == selected[1])
            literal = next(n for n in _walk(power) if n.get("kind") == "IntegerLiteral")
            duplicate = copy.deepcopy(literal)
            if conflict:
                duplicate["value"] = "2"
            root["inner"].append(duplicate)
            result = check_initialized_shift(root, *selected, 65, 128)
            self.assertEqual(result["status"], "unknown" if conflict else "checked", result)
            if not conflict:
                self.assertEqual(result["base_literal_identity"]["occurrences"], 2)
        root = copy.deepcopy(self.root)
        declaration = next(n for n in _walk(root) if n.get("id") == selected[0])
        root["inner"].append(copy.deepcopy(declaration))
        self.assertEqual(check_initialized_shift(root, *selected, 65, 128)["status"], "unknown")

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
