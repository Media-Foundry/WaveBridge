"""Real-Clang composition of scalar forwarding, argument effects and leaf premises."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.scalar_call_effects import check_no_memory_write
from wavebridge.verification.scalar_forwarding import inspect_structure as inspect_forwarding


CLANG = shutil.which("clang++")

SOURCE = r"""
float selected_leaf(float);
float other_leaf(float);
float unknown_float();
float global_value;
int global_counter;

float renamed_first(float renamed) { return selected_leaf(renamed); }
static float renamed_second(float another) { return renamed_first(another); }
float writing_wrapper(float value) { global_value = value; return selected_leaf(value); }
float wrong_parameter_wrapper(float first, float second) { return selected_leaf(first); }

float positive(int i, float x) {
  float values[4] = {};
  return renamed_second(values[i] - x);
}
float increment_argument(float x) { return renamed_second(x++); }
float assignment_argument(float x) { return renamed_second(x = 1.0f); }
float comma_argument(float x) { return renamed_second((x, x)); }
float call_argument(float x) { return renamed_second(unknown_float()); }
float comma_callee(float x) { return (global_counter++, renamed_second)(x); }
float pointer_callee(float x) { float (*pointer)(float) = &renamed_second; return pointer(x); }
float calls_writing_wrapper(float x) { return writing_wrapper(x); }
float calls_wrong_parameter(float x) { return wrong_parameter_wrapper(x, x); }
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class ScalarCallEffectsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-scalar-calls-")
        cls.source = Path(cls.temporary.name) / "scalar_call_effects.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "positive",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.declarations = [node for node in _walk(cls.root)
                            if node.get("kind") == "FunctionDecl" and node.get("name")]
        cls.leaf = cls._unique_declaration("selected_leaf", body=False)
        cls.start = cls._unique_declaration("renamed_second", body=True)
        cls.forwarding = inspect_forwarding(cls.root, cls.start["id"], cls.leaf["id"])
        if cls.forwarding["status"] != "checked":
            raise AssertionError(cls.forwarding)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def _unique_declaration(cls, name, *, body):
        matches = []
        for node in cls.declarations:
            if node.get("name") != name:
                continue
            has_body = any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                           for child in node.get("inner", []))
            if has_body is body:
                matches.append(node)
        if len(matches) != 1:
            raise AssertionError((name, body, matches))
        return matches[0]

    def declaration(self, name, *, body=True):
        return self._unique_declaration(name, body=body)

    def returned_call(self, name):
        function = self.declaration(name)
        returns = [node for node in _walk(function) if node.get("kind") == "ReturnStmt"]
        self.assertEqual(len(returns), 1, name)
        calls = [node for node in _walk(returns[0]) if node.get("kind") == "CallExpr"]
        self.assertTrue(calls, name)
        return calls[0]

    def protocol(self, call_id):
        return {
            "schema_version": "scalar-leaf-effect-assumption/v1",
            "root_sha256": self.forwarding["input_sha256"]["root"],
            "call_expression_id": call_id,
            "leaf_declaration_id": self.leaf["id"],
            "leaf_no_memory_write_assumed": True,
            "valid_call_and_normal_return_assumed": True,
            "evidence_reference": "scalar-call-test-external-leaf-effect",
        }

    def check(self, name, protocol=None, **kwargs):
        call = self.returned_call(name)
        return check_no_memory_write(
            self.root, call["id"], self.protocol(call["id"]) if protocol is None else protocol,
            **kwargs)

    def test_wrapper_with_array_scalar_argument_is_conditionally_checked(self):
        call = self.returned_call("positive")
        result = self.check("positive")
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["conclusion"]["status"], "conditional")
        self.assertEqual(result["conclusion"]["property"], "no_memory_write")
        self.assertEqual(result["conclusion"]["subject"], "exact_call_expression")
        self.assertEqual(result["conclusion"]["call_expression_id"], call["id"])
        self.assertEqual(result["forwarding_check"]["status"], "checked")
        self.assertEqual(result["argument_check"]["status"], "checked")
        self.assertFalse(result["external_leaf_effect_verified"])
        self.assertEqual(result["value_semantics"], "not_established")
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_argument_and_callee_side_effect_shapes_stay_unknown(self):
        for name in ("increment_argument", "assignment_argument", "comma_argument",
                     "call_argument", "comma_callee", "pointer_callee"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_identity_policy_is_bound_even_without_using_references(self):
        strict = self.check("positive")
        enabled = self.check("positive", allow_using_shadows=True)
        self.assertEqual(enabled["status"], "checked", enabled)
        self.assertNotEqual(strict["input_sha256"]["identity_policy"],
                            enabled["input_sha256"]["identity_policy"])

    def test_bad_wrapper_body_or_signature_stays_unknown(self):
        for name in ("calls_writing_wrapper", "calls_wrong_parameter"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "unknown", result)

    def test_protocol_binding_and_strict_premises_are_fail_closed(self):
        call = self.returned_call("positive")
        valid = self.protocol(call["id"])
        variants = [None]
        for key, value in (
                ("root_sha256", "stale"),
                ("call_expression_id", "other"),
                ("leaf_declaration_id", self.declaration("other_leaf", body=False)["id"]),
                ("leaf_no_memory_write_assumed", False),
                ("leaf_no_memory_write_assumed", 1),
                ("valid_call_and_normal_return_assumed", False),
                ("valid_call_and_normal_return_assumed", 1),
                ("evidence_reference", "")):
            protocol = deepcopy(valid)
            protocol[key] = value
            variants.append(protocol)
        for protocol in variants:
            with self.subTest(protocol=protocol):
                result = check_no_memory_write(self.root, call["id"], protocol)
                self.assertEqual(result["status"], "unknown", result)

    def test_budget_boundaries_are_unknown(self):
        call = self.returned_call("positive")
        protocol = self.protocol(call["id"])
        for budget in (1, True):
            with self.subTest(budget=budget):
                result = check_no_memory_write(
                    self.root, call["id"], protocol, max_ast_nodes=budget)
                self.assertEqual(result["status"], "unknown", result)


if __name__ == "__main__":
    unittest.main()
