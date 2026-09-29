import copy
from pathlib import Path
import shutil
import unittest
from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.field_snapshot import check


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class FieldSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        collected = collect(Path(__file__).parent / "fixtures/field_snapshot.cpp", shutil.which("clang++"),
                            ["-std=c++17"], "good", full_translation_unit=True)
        if collected["status"] != "collected": raise AssertionError(collected)
        cls.root = collected["ast_roots"][0]
        cls.ids = {n["name"]: n["id"] for n in _walk(cls.root) if n.get("kind") == "FunctionDecl"}

    def test_snapshot_relation_does_not_establish_api_domain(self):
        result = check(self.root, self.ids["good"])
        self.assertEqual(result["status"], "checked", result)
        self.assertIsNone(result["field_numeric_domain"])
        for key in ("prefix_effects_checked", "field_value_initialized", "API_success_verified",
                    "function_reachability_proved", "source_program_checked", "deployable"):
            self.assertFalse(result[key])
        self.assertEqual(len(result["unchecked_prefix_statement_ids"]), 2)

    def test_changed_suffix_or_unsupported_effects_are_unknown(self):
        for name in ("wrong_counter", "wrong_return", "intervening_call", "volatile_field", "changed_value"):
            result = check(self.root, self.ids[name])
            self.assertEqual(result["status"], "unknown", (name, result))

    def test_identity_budget_and_source_immutability(self):
        root = copy.deepcopy(self.root)
        check(root, self.ids["good"])
        self.assertEqual(root, self.root)
        self.assertEqual(check(root, self.ids["good"], max_ast_nodes=1)["status"], "unknown")
        observed = next(n for n in _walk(root) if n.get("kind") == "VarDecl" and n.get("name") == "observed")
        root["inner"].append(copy.deepcopy(observed))
        self.assertEqual(check(root, self.ids["good"])["status"], "unknown")
