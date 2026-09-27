"""Real-Clang coverage for exact scalar-parameter forwarding chains."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.scalar_forwarding import inspect_structure


CLANG = shutil.which("clang++")

SOURCE = r"""
float selected_external_leaf(float);
float other_external_leaf(float);
float global_value;

float renamed_middle(float renamed_value) {
  return selected_external_leaf(renamed_value);
}
static float renamed_outer(float another_name) noexcept {
  return renamed_middle(another_name);
}

float wrong_parameter(float first, float second) { return selected_external_leaf(second); }
float forwards_local(float value) { float local = value; return selected_external_leaf(local); }
float reads_global(float value) { return selected_external_leaf(global_value); }
float modifies_parameter(float value) { return selected_external_leaf(++value); }
float adds_value(float value) { return selected_external_leaf(value + 1.0f); }
float converts_value(float value) { return selected_external_leaf((float)(double)value); }
float writes_extra(float value) { global_value = value; return selected_external_leaf(value); }
float recursive_forward(float value) { return recursive_forward(value); }
float pointer_parameter(float* value) { return selected_external_leaf(*value); }
float reference_parameter(float& value) { return selected_external_leaf(value); }
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class ScalarForwardingClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-scalar-forwarding-")
        cls.source = Path(cls.temporary.name) / "scalar_forwarding.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "renamed_outer",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.declarations = [node for node in _walk(cls.root)
                            if node.get("kind") == "FunctionDecl" and node.get("name")]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def declaration(self, name, *, body=None):
        matches = []
        for node in self.declarations:
            if node.get("name") != name:
                continue
            has_body = any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                           for child in node.get("inner", []))
            if body is None or has_body is body:
                matches.append(node)
        self.assertEqual(len(matches), 1, (name, body, matches))
        return matches[0]

    def inspect(self, start, leaf="selected_external_leaf"):
        leaf_id = leaf if leaf == "missing-leaf-id" else self.declaration(leaf, body=False)["id"]
        return inspect_structure(self.root, self.declaration(start, body=True)["id"], leaf_id)

    def parameter_id(self, name, *, body):
        declaration = self.declaration(name, body=body)
        parameters = [child for child in declaration.get("inner", [])
                      if isinstance(child, dict) and child.get("kind") == "ParmVarDecl"]
        self.assertEqual(len(parameters), 1, name)
        return parameters[0]["id"]

    def test_renamed_two_layer_chain_binds_exact_parameter_flow(self):
        result = self.inspect("renamed_outer")
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["scope"], "exact_scalar_parameter_forwarding_chain")
        expected = [self.declaration("renamed_outer", body=True)["id"],
                    self.declaration("renamed_middle", body=True)["id"]]
        self.assertEqual(result["wrapper_declaration_ids"], expected)
        self.assertEqual(len(result["call_edges"]), 2)
        self.assertEqual(result["call_edges"][0]["source_parameter_id"],
                         self.parameter_id("renamed_outer", body=True))
        self.assertEqual(result["call_edges"][0]["target_parameter_id"],
                         self.parameter_id("renamed_middle", body=True))
        self.assertEqual(result["call_edges"][1]["source_parameter_id"],
                         self.parameter_id("renamed_middle", body=True))
        self.assertEqual(result["call_edges"][1]["target_parameter_id"],
                         self.parameter_id("selected_external_leaf", body=False))
        self.assertEqual(result["call_edges"][-1]["callee_id"],
                         self.declaration("selected_external_leaf", body=False)["id"])
        self.assertEqual(result["value_semantics"], "not_established")
        self.assertEqual(result["effect_semantics"], "not_established")
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_identity_policy_is_bound_even_without_using_references(self):
        strict = self.inspect("renamed_outer")
        enabled = inspect_structure(self.root, self.declaration("renamed_outer", body=True)["id"],
                                    self.declaration("selected_external_leaf", body=False)["id"],
                                    allow_using_shadows=True)
        self.assertEqual(enabled["status"], "checked", enabled)
        self.assertNotEqual(strict["input_sha256"]["identity_policy"],
                            enabled["input_sha256"]["identity_policy"])

    def test_wrong_parameter_local_global_and_expression_shapes_stay_unknown(self):
        for name in ("wrong_parameter", "forwards_local", "reads_global",
                     "modifies_parameter", "adds_value", "converts_value", "writes_extra"):
            with self.subTest(name=name):
                result = self.inspect(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_recursive_and_wrong_or_missing_leaf_stay_unknown(self):
        recursive = self.inspect("recursive_forward")
        self.assertEqual(recursive["status"], "unknown", recursive)
        missing = self.inspect("renamed_outer", "missing-leaf-id")
        self.assertEqual(missing["status"], "unknown", missing)
        wrong_leaf = inspect_structure(
            self.root, self.declaration("renamed_outer", body=True)["id"],
            self.declaration("renamed_middle", body=True)["id"])
        self.assertEqual(wrong_leaf["status"], "unknown", wrong_leaf)

    def test_pointer_and_reference_parameters_are_not_scalar_by_value(self):
        for name in ("pointer_parameter", "reference_parameter"):
            with self.subTest(name=name):
                result = self.inspect(name)
                self.assertEqual(result["status"], "unknown", result)

    def test_real_depth_and_ast_budget_boundaries(self):
        source = Path(self.temporary.name) / "scalar_forwarding_depth.cpp"
        lines = ["float scalar_leaf(float);"]
        lines.append("float chain0(float value) { return scalar_leaf(value); }")
        lines.extend(
            f"float chain{index}(float renamed) {{ return chain{index - 1}(renamed); }}"
            for index in range(1, 33))
        source.write_text("\n".join(lines) + "\n")
        collected = collect(source, CLANG, ["-std=c++17"], "chain32",
                            full_translation_unit=True)
        self.assertEqual(collected["status"], "collected", collected)
        root = collected["ast_roots"][0]
        declarations = {}
        for node in _walk(root):
            if node.get("kind") != "FunctionDecl" or not node.get("name"):
                continue
            declarations.setdefault(node["name"], []).append(node)
        for name, nodes in declarations.items():
            if name == "scalar_leaf" or name.startswith("chain"):
                self.assertEqual(len(nodes), 1, (name, nodes))
        leaf_id = declarations["scalar_leaf"][0]["id"]

        accepted = inspect_structure(root, declarations["chain31"][0]["id"], leaf_id)
        self.assertEqual(accepted["status"], "checked", accepted)
        self.assertEqual(len(accepted["wrapper_declaration_ids"]), 32)
        self.assertEqual(accepted["wrapper_declaration_ids"][0],
                         declarations["chain31"][0]["id"])
        self.assertEqual(accepted["wrapper_declaration_ids"][-1],
                         declarations["chain0"][0]["id"])

        refused = inspect_structure(root, declarations["chain32"][0]["id"], leaf_id)
        self.assertEqual(refused["status"], "unknown", refused)
        self.assertEqual(refused["reason"], "wrapper_cycle_or_depth_budget")
        self.assertEqual(len(refused["wrapper_declaration_ids"]), 32)

        tiny = inspect_structure(
            root, declarations["chain0"][0]["id"], leaf_id, max_ast_nodes=1)
        self.assertEqual(tiny["status"], "unknown", tiny)
        self.assertEqual(tiny["reason"], "ast_node_budget_exceeded")
        boolean = inspect_structure(
            root, declarations["chain0"][0]["id"], leaf_id, max_ast_nodes=True)
        self.assertEqual(boolean["status"], "unknown", boolean)
        self.assertEqual(boolean["reason"], "invalid_inputs_or_budget")


if __name__ == "__main__":
    unittest.main()
