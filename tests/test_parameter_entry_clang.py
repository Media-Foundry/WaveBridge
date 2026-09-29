import copy
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.parameter_entry import check


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class ParameterEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        collected = collect(Path(__file__).parent / "fixtures/parameter_entry.cpp",
                            shutil.which("clang++"), ["-std=c++17"], "guarded",
                            full_translation_unit=True)
        if collected["status"] != "collected":
            raise AssertionError(collected)
        cls.root = collected["ast_roots"][0]

    def select(self, name):
        function = next(n for n in _walk(self.root) if n.get("kind") == "FunctionDecl" and n.get("name") == name)
        parameter = next(n for n in function["inner"] if n.get("kind") == "ParmVarDecl")
        target = next(n for n in _walk(function) if n.get("kind") == "DeclStmt" and
                      any(c.get("name") == "target" for c in n.get("inner", [])))
        return function["id"], parameter["id"], target["id"]

    def test_actual_conditions_exclude_opaque_branch(self):
        report = check(self.root, *self.select("guarded"), 65, 128)
        self.assertEqual(report["status"], "checked", report)
        self.assertTrue(report["parameter_preserved"])
        self.assertEqual(report["domain_values_exhaustively_checked"], 64)
        self.assertEqual(report["result_interval"], {"lower": 65, "upper": 128})
        for field in ("entry_domain_verified", "target_statement_evaluated", "source_program_checked", "deployable"):
            self.assertFalse(report[field])

    def test_reached_writes_aliases_calls_and_repeated_loops_are_unknown(self):
        for name in ("changed", "aliased", "called", "repeat", "branch_write"):
            report = check(self.root, *self.select(name), 65, 128)
            self.assertEqual(report["status"], "unknown", (name, report))
            self.assertFalse(report["parameter_preserved"])

    def test_domain_changes_reachability_and_no_writes_are_not_guessed(self):
        for lower, upper in ((0, 128), (65, 1025), (-1, 128)):
            self.assertEqual(check(self.root, *self.select("guarded"), lower, upper)["status"], "unknown")
        self.assertEqual(check(self.root, *self.select("branch_write"), 65, 100)["status"], "checked")

    def test_budget_invalid_domain_and_selection(self):
        selection = self.select("guarded")
        for kwargs in ({"max_steps": 1}, {"max_ast_nodes": 1}, {"int_bits": 7}):
            self.assertEqual(check(self.root, *selection, 65, 128, **kwargs)["status"], "unknown")
        for lower, upper in ((True, 128), (2, 1), (0, 4096)):
            self.assertEqual(check(self.root, *selection, lower, upper)["status"], "unknown")
        self.assertEqual(check(self.root, selection[0], selection[1], self.select("called")[2], 65, 128)["status"], "unknown")

    def test_duplicate_identity_and_input_immutability(self):
        root = copy.deepcopy(self.root)
        selection = self.select("guarded")
        check(root, *selection, 65, 128)
        self.assertEqual(root, self.root)
        root["inner"].append(copy.deepcopy(next(n for n in _walk(root) if n.get("id") == selection[1])))
        self.assertEqual(check(root, *selection, 65, 128)["status"], "unknown")
