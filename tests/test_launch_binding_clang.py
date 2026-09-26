"""Fresh real CUDA AST binding; mutated ASTs below test evidence tampering only."""
import copy
from pathlib import Path
import shutil
import unittest

from wavebridge.analysis.launch_facts import inspect
from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.launch_binding import check


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class LaunchBindingClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/lambda_launch.cu", shutil.which("clang++"),
                         ["-std=c++17", "--cuda-host-only", "-nocudainc", "-nocudalib"],
                         "target", full_translation_unit=True, dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]
        cls.kernel = report["function_locations"][0]["id"]
        cls.site = inspect(cls.root, cls.kernel)["sites"][0]
        cls.selection = {"schema_version": "launch-selection/v1", "ast_root_sha256": _hash(cls.root),
                         "kernel_declaration_id": cls.kernel, "launch_id": cls.site["launch_id"],
                         "configuration_declaration_id": cls.site["configuration_declaration_id"],
                         "configuration_expression_ids": [n["id"] for n in cls.site["configuration_arguments"]]}

    def test_real_lambda_duplicate_launch_has_exact_four_slots(self):
        result = check(self.root, self.selection)
        self.assertEqual("checked", result["status"], result)
        self.assertGreater(result["launch_ast_occurrences"], 1)
        self.assertGreaterEqual(result["configuration_declaration_occurrences"], 1)
        self.assertEqual(self.selection["configuration_expression_ids"],
                         [n["expression_id"] for n in result["configuration_slots"]])
        self.assertEqual(self.site["parameter_bindings"], result["parameter_bindings"])
        for key in ("configuration_values", "source_object_preservation", "host_reachability",
                    "launch_API_semantics"):
            self.assertEqual("not_established", result[key])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_wrong_selection_and_swapped_slots_do_not_bind(self):
        changes = {"ast_root_sha256": "stale", "kernel_declaration_id": "other",
                   "launch_id": "other", "configuration_declaration_id": "other",
                   "configuration_expression_ids": self.selection["configuration_expression_ids"][::-1]}
        for key, value in changes.items():
            with self.subTest(key=key):
                result = check(self.root, {**self.selection, key: value})
                self.assertEqual("unknown", result["status"], result)

    def test_missing_repeated_or_boolean_slot_ids_are_unknown(self):
        for slots in ([], [True] * 4, [""] * 4, [self.selection["configuration_expression_ids"][0]] * 4):
            self.assertEqual("unknown", check(self.root, {**self.selection,
                                                         "configuration_expression_ids": slots})["status"])

    def mutate(self, action):
        root = copy.deepcopy(self.root)
        action(root)
        return check(root, {**self.selection, "ast_root_sha256": _hash(root)})

    def test_conflicting_launch_and_slot_occurrences_are_unknown(self):
        for selected_id in (self.site["launch_id"], *self.selection["configuration_expression_ids"]):
            def change(root):
                node = next(n for n in _walk(root) if n.get("id") == selected_id)
                altered = copy.deepcopy(node)
                altered["valueCategory"] = "tampered"
                root["inner"].append(altered)
            with self.subTest(identifier=selected_id):
                self.assertEqual("unknown", self.mutate(change)["status"])

    def test_conflicting_kernel_or_parameter_declaration_is_unknown(self):
        parameter = self.site["parameter_bindings"][0]["parameter_declaration_id"]
        for selected_id in (self.kernel, parameter):
            def change(root):
                node = next(n for n in _walk(root) if n.get("id") == selected_id)
                altered = copy.deepcopy(node)
                altered["type"] = {"qualType": "long"}
                root["inner"].append(altered)
            self.assertEqual("unknown", self.mutate(change)["status"])

    def test_variadic_or_non_kernel_definition_is_unknown(self):
        def variadic(root):
            next(n for n in _walk(root) if n.get("id") == self.kernel)["variadic"] = True
        def nonglobal(root):
            node = next(n for n in _walk(root) if n.get("id") == self.kernel)
            node["inner"] = [n for n in node["inner"] if n.get("kind") != "CUDAGlobalAttr"]
        for mutation in (variadic, nonglobal):
            self.assertEqual("unknown", self.mutate(mutation)["status"])

    def test_callee_hidden_child_or_type_change_is_unknown(self):
        for field, value in (("inner", [{"kind": "IntegerLiteral", "value": "0"}]),
                             ("type", {"qualType": "void ()"})):
            def change(root):
                for node in _walk(root):
                    if (node.get("kind") == "DeclRefExpr" and
                            node.get("referencedDecl", {}).get("id") == self.kernel):
                        node[field] = copy.deepcopy(value)
            self.assertEqual("unknown", self.mutate(change)["status"])

    def test_resource_and_input_boundaries_are_unknown(self):
        self.assertEqual("ast_node_budget_exceeded", check(self.root, self.selection, max_ast_nodes=1)["reason"])
        self.assertEqual("invalid_ast_node_budget", check(self.root, self.selection, max_ast_nodes=True)["reason"])
        self.assertEqual("unknown", check({}, self.selection)["status"])
        self.assertEqual("unknown", check(self.root, {})["status"])


if __name__ == "__main__":
    unittest.main()
