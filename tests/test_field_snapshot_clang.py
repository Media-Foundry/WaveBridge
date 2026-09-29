import copy
from pathlib import Path
import shutil
import unittest
from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.field_snapshot import check, check_query_object


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

    def test_guarded_query_address_matches_snapshot_object(self):
        for name, position in (("guarded_snapshot", 0), ("reordered_snapshot", 1)):
            result = check_query_object(self.root, self.ids[name])
            self.assertEqual(result["status"], "checked", result)
            self.assertEqual(result["argument_position"], position)
            self.assertTrue(result["same_object_declaration"])
            self.assertEqual(result["object_declaration_id"], result["snapshot_check"]["object_declaration_id"])
            self.assertEqual(result["query_result_check"]["status"], "checked")
            for key in ("query_output_effects_verified", "field_value_initialized", "API_success_verified",
                        "call_normal_return_proved", "dynamic_lifetime_verified", "source_program_checked", "deployable"):
                self.assertFalse(result[key])
            self.assertEqual(result["query_argument_direction"], "unverified")
            self.assertIsNone(result["field_numeric_domain"])

    def test_query_object_mismatch_or_unsupported_role_is_unknown(self):
        for name in ("wrong_query_object", "query_not_adjacent", "query_pointer_alias", "ambiguous_query_role",
                     "result_discarded", "good", "changed_value"):
            result = check_query_object(self.root, self.ids[name])
            self.assertEqual(result["status"], "unknown", (name, result))

    def test_composition_identity_budget_and_input_immutability(self):
        root = copy.deepcopy(self.root)
        check_query_object(root, self.ids["guarded_snapshot"])
        self.assertEqual(root, self.root)
        self.assertEqual(check_query_object(root, self.ids["guarded_snapshot"], max_ast_nodes=1)["status"], "unknown")
        declaration = next(n for n in _walk(root) if n.get("kind") == "FunctionDecl" and n.get("name") == "property_query")
        root["inner"].append(copy.deepcopy(declaration))
        self.assertEqual(check_query_object(root, self.ids["guarded_snapshot"])["status"], "unknown")
