import copy
from pathlib import Path
import shutil
import unittest
from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.normal_return_guard import check


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class NormalReturnGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/normal_return_guard.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "good", full_translation_unit=True)
        if report["status"] != "collected": raise AssertionError(report)
        cls.root = report["ast_roots"][0]
        cls.ids = {n["name"]: n["id"] for n in _walk(cls.root) if n.get("kind") == "FunctionDecl"}

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
