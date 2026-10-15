"""Real Clang regression for symbolic lane-family prefix dependencies."""
import copy
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.lane_uniformity import check_prefix


CLANG = shutil.which("clang++")


@unittest.skipUnless(CLANG, "requires clang++")
class LaneUniformityClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/lane_uniformity.cu", CLANG,
                         ["-std=c++17", "-x", "c++", "-fms-extensions"], "good",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]
        cls.functions = {node.get("name"): node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")}

    def selection(self, name, declaration="local_batches"):
        function = self.functions[name]
        variables = [node for node in _walk(function)
                     if node.get("kind") == "VarDecl" and node.get("name")]
        selected = next(node for node in variables if node["name"] == declaration)
        body = next(node for node in function.get("inner", []) if node.get("kind") == "CompoundStmt")
        target = next(statement for statement in body.get("inner", [])
                      if statement.get("kind") == "DeclStmt" and
                      any(node.get("kind") == "VarDecl" and node.get("name") == "stop"
                          for node in statement.get("inner", [])))
        return function, selected, target

    def protocol(self, function, *, include_x=False, uint_axis=False):
        suffix = "_uint" if uint_axis else ""
        leaves = [
            {"declaration_id": self.functions["group_size_leaf" + suffix]["id"],
             "return_type": {"qualType": "unsigned long"}, "arguments": [1],
             "semantics": "workgroup_size"},
            {"declaration_id": self.functions["group_id_leaf" + suffix]["id"],
             "return_type": {"qualType": "unsigned long"}, "arguments": [0],
             "semantics": "workgroup_id"},
            {"declaration_id": self.functions["local_id_leaf" + suffix]["id"],
             "return_type": {"qualType": "unsigned long"}, "arguments": [1],
             "semantics": "workgroup_local_id"},
        ]
        if include_x:
            leaves.append({"declaration_id": self.functions["local_id_leaf"]["id"],
                           "return_type": {"qualType": "unsigned long"}, "arguments": [0],
                           "semantics": "workgroup_local_id"})
        return {"schema_version": "lane-family-api-assumptions/v1",
                "ast_root_sha256": _hash(self.root), "function_id": function["id"],
                "family": "same_invocation_same_workgroup_fixed_local_yz_vary_local_x",
                "scalar_arguments_common_assumed": True,
                "coordinate_calls_stable_and_no_memory_write_assumed": True,
                "property_receivers_valid_and_static_semantics_assumed": True,
                "same_target_integer_semantics_assumed": True, "leaves": leaves,
                "evidence_reference": "synthetic-test-only API lane-family premise"}

    def run_case(self, name="good", declaration="local_batches", *, protocol=None,
                 root=None, max_ast_nodes=1_000_000):
        function, selected, target = self.selection(name, declaration)
        return check_prefix(self.root if root is None else root, function["id"], target["id"], selected["id"],
                            self.protocol(function) if protocol is None else protocol,
                            max_ast_nodes=max_ast_nodes)

    def test_common_prefix_and_value_alias_are_checked(self):
        before = copy.deepcopy(self.root)
        for name, declaration in (("good", "local_batches"), ("value_alias", "alias"),
                                  ("common_write", "local_batches"),
                                  ("post_write", "local_batches"), ("post_loop", "local_batches"),
                                  ("target_writes", "local_batches")):
            with self.subTest(name=name):
                result = self.run_case(name, declaration)
                self.assertEqual(result["status"], "checked", result)
                for flag in ("source_program_checked", "deployable", "integer_definedness_checked",
                             "api_semantics_verified", "count_common_across_lanes_checked"):
                    self.assertFalse(result[flag])
                self.assertEqual(result["input_sha256"]["root"], _hash(self.root))
        self.assertEqual(before, self.root)

        function, _, _ = self.selection("uint_axis_good")
        uint_axis = self.run_case("uint_axis_good", protocol=self.protocol(function, uint_axis=True))
        self.assertEqual(uint_axis["status"], "checked", uint_axis)
        self.assertTrue(uint_axis["common_value_at_target_checked"])
        consumed = {entry["declaration_id"] for entry in uint_axis["dependency_origins"].values()
                    if entry.get("basis") != "external_invocation_argument_semantics"}
        self.assertEqual(consumed, {leaf["declaration_id"] for leaf in self.protocol(function, uint_axis=True)["leaves"]})

    def test_local_x_dependency_and_varying_branch_remain_unknown(self):
        for name in ("varying_value", "varying_if", "varying_if_two_constants"):
            function, _, _ = self.selection(name)
            result = self.run_case(name, protocol=self.protocol(function, include_x=True))
            self.assertEqual(result["status"], "unknown", result)
            self.assertTrue(result.get("variable_dependencies"))

        function, _, _ = self.selection("varying_if_unrelated")
        unrelated = self.run_case("varying_if_unrelated", protocol=self.protocol(function, include_x=True))
        self.assertEqual(unrelated["status"], "checked", unrelated)
        self.assertTrue(any(origin.get("varying") for origin in unrelated["dependency_origins"].values()))
        self.assertFalse(any(unrelated["dependency_origins"][token]["varying"]
                             for token in unrelated["selected_dependencies"]))

    def test_ms_property_static_getter_chain_is_supported_but_exact(self):
        good = self.run_case("property_good")
        self.assertEqual(good["status"], "checked", good)
        self.assertTrue(good["common_value_at_target_checked"])
        self.assertGreaterEqual(len(good["getter_checks"]), 4)
        self.assertTrue(any(any(token.startswith("api:") for token in check["dependencies"])
                            for check in good["getter_checks"]))
        for name in ("property_wrong_receiver", "property_unknown_wrapper"):
            with self.subTest(name=name):
                result = self.run_case(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["common_value_at_target_checked"])

    def test_unsupported_storage_escape_calls_and_control_fail_closed(self):
        for name in ("reference_alias", "static_local", "tls_local", "address_escape",
                     "unknown_call", "goto_after"):
            with self.subTest(name=name):
                result = self.run_case(name)
                self.assertEqual(result["status"], "unknown", result)

    def test_protocol_is_exact_and_all_leaves_are_consumed(self):
        function, _, _ = self.selection("good")
        base = self.protocol(function)
        variants = []
        for key, value in (("ast_root_sha256", "0" * 64), ("function_id", self.functions["post_write"]["id"]),
                           ("scalar_arguments_common_assumed", 1),
                           ("coordinate_calls_stable_and_no_memory_write_assumed", False)):
            changed = copy.deepcopy(base); changed[key] = value; variants.append(changed)
        extra = copy.deepcopy(base); extra["extra"] = True; variants.append(extra)
        unused = copy.deepcopy(base)
        unused["leaves"].append({"declaration_id": self.functions["local_id_leaf"]["id"],
                                 "return_type": {"qualType": "unsigned long"}, "arguments": [2],
                                 "semantics": "workgroup_local_id"})
        variants.append(unused)
        wrong_axis = copy.deepcopy(base); wrong_axis["leaves"][2]["arguments"] = [0]; variants.append(wrong_axis)
        for protocol in variants:
            with self.subTest(protocol=protocol):
                self.assertEqual(self.run_case(protocol=protocol)["status"], "unknown")

    def test_identity_budget_and_selection_fail_closed(self):
        self.assertEqual(self.run_case(max_ast_nodes=1)["status"], "unknown")
        duplicate = copy.deepcopy(self.root)
        function, selected, _ = self.selection("good")
        duplicate["inner"].append(copy.deepcopy(next(node for node in _walk(duplicate)
                                                        if node.get("id") == selected["id"])))
        protocol = self.protocol(function)
        protocol["ast_root_sha256"] = _hash(duplicate)
        conflicted = self.run_case(root=duplicate, protocol=protocol)
        self.assertEqual(conflicted["status"], "unknown")
        self.assertIn("identity_not_unique", conflicted["reason"])
        function, selected, target = self.selection("good")
        self.assertEqual(check_prefix(self.root, self.functions["post_write"]["id"], target["id"], selected["id"],
                                      self.protocol(function))["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
