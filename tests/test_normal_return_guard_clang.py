import copy
from pathlib import Path
import shutil
import unittest
from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.normal_return_guard import check, check_call


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class NormalReturnGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/normal_return_guard.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "good", full_translation_unit=True)
        if report["status"] != "collected": raise AssertionError(report)
        cls.root = report["ast_roots"][0]
        cls.ids = {n["name"]: n["id"] for n in _walk(cls.root) if n.get("kind") == "FunctionDecl"}
        cls.calls = {n["name"]: next(c for c in n["inner"] if c.get("kind") == "CompoundStmt")["inner"][0]["id"]
                     for n in _walk(cls.root) if n.get("kind") == "FunctionDecl" and n.get("name", "").startswith("call_")}

    def test_only_converted_comparison_is_established(self):
        result = check(self.root, self.ids["good"])
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(len(result["unchecked_prefix_call_ids"]), 1)
        for key in ("API_success_verified", "enum_equality_established", "runtime_linkage_verified",
                    "source_program_checked", "deployable"):
            self.assertFalse(result[key])

    def test_unsupported_control_or_missing_noreturn(self):
        for name in ("returns", "early_return", "wrong_test", "changed_status", "has_else",
                     "hidden_return", "indirect", "after_terminal"):
            self.assertEqual(check(self.root, self.ids[name])["status"], "unknown", name)

    def test_identity_budget_and_immutability(self):
        root = copy.deepcopy(self.root)
        check(root, self.ids["good"])
        self.assertEqual(root, self.root)
        self.assertEqual(check(root, self.ids["good"], max_ast_nodes=1)["status"], "unknown")
        selected = next(n for n in _walk(root) if n.get("id") == self.ids["stop"])
        root["inner"].append(copy.deepcopy(selected))
        self.assertEqual(check(root, self.ids["good"])["status"], "unknown")

    def test_fresh_query_result_composition(self):
        result = check_call(self.root, self.calls["call_good"])
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["query_result_preserved_to_parameter"])
        self.assertEqual(result["query_declaration_id"], self.ids["query"])
        self.assertEqual(result["wrapper_check"]["status"], "checked")
        self.assertEqual(len(result["query_arguments"]), 1)
        for key in ("API_success_verified", "enum_equality_established", "call_normal_return_proved",
                    "query_output_effects_verified", "runtime_linkage_verified", "source_program_checked", "deployable"):
            self.assertFalse(result[key])
        other = check_call(self.root, self.calls["call_other"])
        self.assertEqual(other["status"], "checked", other)
        self.assertEqual(other["query_declaration_id"], self.ids["other_query"])
        self.assertNotEqual(result["input_sha256"]["selection"], other["input_sha256"]["selection"])

    def test_changed_query_result_or_unsupported_call_is_unknown(self):
        for name in ("call_constant", "call_discarded", "call_converted", "call_conditional",
                     "call_indirect", "call_unguarded"):
            result = check_call(self.root, self.calls[name])
            self.assertEqual(result["status"], "unknown", (name, result))
            self.assertFalse(result["query_result_preserved_to_parameter"])

    def test_call_identity_budget_and_immutability(self):
        root = copy.deepcopy(self.root)
        check_call(root, self.calls["call_good"])
        self.assertEqual(root, self.root)
        self.assertEqual(check_call(root, self.calls["call_good"], max_ast_nodes=1)["status"], "unknown")
        declaration = next(n for n in _walk(root) if n.get("id") == self.ids["query"])
        root["inner"].append(copy.deepcopy(declaration))
        self.assertEqual(check_call(root, self.calls["call_good"])["status"], "unknown")
