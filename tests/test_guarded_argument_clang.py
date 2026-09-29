import copy
from pathlib import Path
import shutil
import unittest
from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.parameter_entry import check_guarded_argument


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class GuardedArgumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        collected = collect(Path(__file__).parent / "fixtures/guarded_argument.cpp",
                            shutil.which("clang++"), ["-std=c++17"], "good", full_translation_unit=True)
        if collected["status"] != "collected": raise AssertionError(collected)
        cls.root = collected["ast_roots"][0]

    def select(self, name):
        function = next(n for n in _walk(self.root) if n.get("kind") == "FunctionDecl" and n.get("name") == name)
        callee = next(n for n in _walk(self.root) if n.get("kind") == "FunctionDecl" and n.get("name") == "dispatch")
        variable = next(n for n in _walk(function) if n.get("kind") == "VarDecl" and n.get("name") == "value")
        guard = next(n for n in _walk(function) if n.get("kind") == "IfStmt")
        call = next(n for n in _walk(function) if n.get("kind") == "CallExpr" and
                    any(c.get("referencedDecl", {}).get("id") == callee["id"] for c in _walk(n)))
        return function["id"], variable["id"], guard["id"], call["id"], callee["id"]

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
