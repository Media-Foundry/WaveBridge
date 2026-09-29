import copy
from pathlib import Path
import shutil
import unittest
from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.parameter_entry import check_guarded_argument
from wavebridge.verification.power_ceiling import check_guarded_shift


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class GuardedArgumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        collected = collect(Path(__file__).parent / "fixtures/guarded_argument.cpp",
                            shutil.which("clang++"), ["-std=c++17"], "good", full_translation_unit=True)
        if collected["status"] != "collected": raise AssertionError(collected)
        cls.root = collected["ast_roots"][0]

    def select(self, name, callee_name="dispatch"):
        function = next(n for n in _walk(self.root) if n.get("kind") == "FunctionDecl" and n.get("name") == name)
        callee = next(n for n in _walk(self.root) if n.get("kind") == "FunctionDecl" and n.get("name") == callee_name)
        variable = next(n for n in _walk(function) if n.get("kind") == "VarDecl" and n.get("name") == "value")
        guard = next(n for n in _walk(function) if n.get("kind") == "IfStmt")
        call = next(n for n in _walk(function) if n.get("kind") == "CallExpr" and
                    any(c.get("referencedDecl", {}).get("id") == callee["id"] for c in _walk(n)))
        return function["id"], variable["id"], guard["id"], call["id"], callee["id"]

    def power_ids(self):
        function = next(n for n in _walk(self.root) if n.get("kind") == "FunctionDecl" and n.get("name") == "power_dispatch")
        variables = {n.get("name"): n["id"] for n in _walk(function) if n.get("kind") == "VarDecl"}
        return variables["exponent"], variables["power"]

    def test_guard_to_power_composition_has_no_external_numeric_domain(self):
        result = check_guarded_shift(self.root, *self.select("guarded_power", "power_dispatch"), 0, *self.power_ids())
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["entry_values"], [65, 128])
        self.assertEqual(result["result_values"], [128])
        self.assertFalse(result["numeric_input_domain_supplied"])
        self.assertTrue(result["guarded_call_domain_derived"])
        self.assertFalse(result["runtime_input_binding_verified"])
        self.assertFalse(result["other_call_sites_checked"])
        self.assertEqual(len(result["per_entry_value_checks"]), 2)

    def test_guard_does_not_override_invalid_helper_domain_or_wrong_initialization(self):
        result = check_guarded_shift(self.root, *self.select("unsafe_guarded_power", "power_dispatch"), 0, *self.power_ids())
        self.assertEqual(result["guard_check"]["status"], "checked")
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["guarded_call_domain_derived"])
        exponent, power = self.power_ids()
        result = check_guarded_shift(self.root, *self.select("guarded_power", "power_dispatch"), 0, power, exponent)
        self.assertEqual(result["status"], "unknown")

    def test_discrete_domain_survives_unrelated_opaque_predicates(self):
        for position in (0, 1):
            result = check_guarded_argument(self.root, *self.select("good"), position)
            self.assertEqual(result["status"], "checked", result)
            self.assertEqual(result["argument_values"], [65, 128])
            self.assertFalse(result["call_reachability_proved"])
            self.assertFalse(result["other_argument_effects_checked"])
            self.assertFalse(result["deployable"])

    def test_escape_extra_conjunct_mutation_bypass_and_wrong_argument(self):
        for name in ("extra_conjunct", "escaped", "aliased", "bypass", "mutable_local", "wrong_argument"):
            result = check_guarded_argument(self.root, *self.select(name), 0)
            self.assertEqual(result["status"], "unknown", (name, result))
        self.assertEqual(check_guarded_argument(self.root, *self.select("wrong_argument"), 1)["status"], "checked")

    def test_budget_conflicts_wrong_positions_and_immutability(self):
        root = copy.deepcopy(self.root)
        selection = self.select("good")
        check_guarded_argument(root, *selection, 0)
        self.assertEqual(root, self.root)
        for kwargs in ({"max_ast_nodes": 1}, {"int_bits": 7}):
            self.assertEqual(check_guarded_argument(root, *selection, 0, **kwargs)["status"], "unknown")
        for position in (True, -1, 2):
            self.assertEqual(check_guarded_argument(root, *selection, position)["status"], "unknown")
        root["inner"].append(copy.deepcopy(next(n for n in _walk(root) if n.get("id") == selection[1])))
        self.assertEqual(check_guarded_argument(root, *selection, 0)["status"], "unknown")
