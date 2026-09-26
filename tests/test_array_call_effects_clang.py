"""Real-Clang effects for one direct helper call on an automatic float array."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.array_call_effects import check


CLANG = shutil.which("clang++")

SOURCE = r"""
float global_value;
float unknown_scalar();

void safe_helper(float* data) {
  int local_index = 0;
  float local_value = 1.0f;
  data[local_index] = local_value;
  local_index = 1;
}
void global_helper(float* data) { global_value = data[0]; }
void reassign_helper(float* data) { data = nullptr; }
void reference_helper(float* data) { float& alias = data[0]; alias = 2.0f; }
void dereference_helper(float* data) { *data = 2.0f; }
void unknown_call_helper(float* data) { data[0] = unknown_scalar(); }

void safe_caller() {
  int protected_value = 7;
  float buffer[8] = {};
  safe_helper(buffer);
  (void)protected_value;
}
void global_caller() {
  int protected_value = 7;
  float buffer[8] = {};
  global_helper(buffer);
}
void reassign_caller() {
  int protected_value = 7;
  float buffer[8] = {};
  reassign_helper(buffer);
}
void reference_caller() {
  int protected_value = 7;
  float buffer[8] = {};
  reference_helper(buffer);
}
void dereference_caller() {
  int protected_value = 7;
  float buffer[8] = {};
  dereference_helper(buffer);
}
void unknown_call_caller() {
  int protected_value = 7;
  float buffer[8] = {};
  unknown_call_helper(buffer);
}
void pointer_caller(float* pointer) {
  int protected_value = 7;
  safe_helper(pointer);
}
void offset_caller() {
  int protected_value = 7;
  float buffer[8] = {};
  safe_helper(buffer + 1);
}
void oversized_caller() {
  int protected_value = 7;
  float buffer[4097] = {};
  safe_helper(buffer);
}
void other_protected() {
  int protected_value = 11;
  (void)protected_value;
}

struct Select {
  float operator()(float a, float b) const { return a < b ? b : a; }
};
struct Writes {
  float operator()(float a, float b) const { return global_value = a + b; }
};
struct Calls {
  float operator()(float a, float b) const { return unknown_scalar(); }
};
void select_helper(float* data) { Select r; data[0] = r(data[0], 1.0f); }
void writes_helper(float* data) { Writes r; data[0] = r(data[0], 1.0f); }
void calls_helper(float* data) { Calls r; data[0] = r(data[0], 1.0f); }
void argument_helper(float* data) { Select r; data[0] = r(global_value = 2.0f, 1.0f); }
void select_caller() { int protected_value = 7; float buffer[8] = {}; select_helper(buffer); }
void writes_caller() { int protected_value = 7; float buffer[8] = {}; writes_helper(buffer); }
void calls_caller() { int protected_value = 7; float buffer[8] = {}; calls_helper(buffer); }
void argument_caller() { int protected_value = 7; float buffer[8] = {}; argument_helper(buffer); }
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class ArrayCallEffectsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-array-call-effects-")
        cls.source = Path(cls.temporary.name) / "array_call_effects.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "safe_caller",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def function(self, name):
        matches = [node for node in self.functions if node.get("name") == name and
                   any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                       for child in node.get("inner", []))]
        self.assertEqual(len(matches), 1, name)
        return matches[0]

    def inputs(self, caller):
        function = self.function(caller)
        calls = [node for node in _walk(function) if node.get("kind") == "CallExpr"]
        self.assertEqual(len(calls), 1, (caller, calls))
        protected = [node for node in _walk(function)
                     if node.get("kind") == "VarDecl" and
                     node.get("name") == "protected_value"]
        self.assertEqual(len(protected), 1, caller)
        return calls[0], protected[0]

    def check(self, caller, *, protected=None, **kwargs):
        call, local = self.inputs(caller)
        declaration = local if protected is None else protected
        return check(self.root, call["id"], declaration["id"], **kwargs)

    def test_helper_array_and_local_writes_preserve_separate_int_storage(self):
        result = self.check("safe_caller")
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["protected_storage_preserved"])
        self.assertTrue(result["explicit_write_targets_checked"])
        self.assertEqual(result["pending_effects"], [])
        self.assertEqual(result["binding"]["array_extent"], 8)
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        self.assertFalse(result["array_bounds_checked"])
        self.assertIn("stays within", " ".join(result["assumptions"]).lower())

    def test_global_parameter_reference_and_dereference_writes_are_rejected(self):
        for name in ("global_caller", "reassign_caller", "reference_caller",
                     "dereference_caller"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertNotEqual(result["status"], "checked", result)
                self.assertFalse(result["protected_storage_preserved"])

    def test_unknown_helper_call_retains_partial_write_classification_only(self):
        result = self.check("unknown_call_caller")
        self.assertEqual(result["status"], "unknown", result)
        self.assertTrue(result["explicit_write_targets_checked"])
        self.assertTrue(result["pending_effects"])
        self.assertFalse(result["protected_storage_preserved"])
        self.assertFalse(result["source_program_checked"])

    def test_argument_array_and_protected_scope_bindings_are_exact(self):
        for name in ("pointer_caller", "offset_caller", "oversized_caller"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "unknown", result)

        other_values = [node for node in _walk(self.function("other_protected"))
                        if node.get("kind") == "VarDecl" and
                        node.get("name") == "protected_value"]
        self.assertEqual(len(other_values), 1)
        wrong_scope = self.check("safe_caller", protected=other_values[0])
        self.assertEqual(wrong_scope["status"], "unknown", wrong_scope)

    def test_wrong_id_and_budget_fail_closed(self):
        call, protected = self.inputs("safe_caller")
        self.assertEqual(check(self.root, "missing-call", protected["id"])["status"], "unknown")
        self.assertEqual(check(self.root, call["id"], "missing-protected")["status"], "unknown")
        for budget in (1, True):
            with self.subTest(max_ast_nodes=budget):
                result = check(
                    self.root, call["id"], protected["id"], max_ast_nodes=budget)
                self.assertEqual(result["status"], "unknown", result)

    def test_scalar_operator_body_is_checked_without_closing_lifecycle(self):
        original = self.check("select_caller")
        self.assertIn("CXXOperatorCallExpr", [e["kind"] for e in original["pending_effects"]])
        result = self.check("select_caller", use_scalar_operators=True)
        self.assertEqual(result["status"], "unknown", result)
        self.assertTrue(result["explicit_write_targets_checked"])
        self.assertEqual(len(result["scalar_operator_checks"]), 1)
        self.assertEqual(result["scalar_operator_checks"][0]["body_no_memory_write"]["status"], "checked")
        self.assertNotIn("CXXOperatorCallExpr", [e["kind"] for e in result["pending_effects"]])
        self.assertIn("local_object_lifecycle", [e["kind"] for e in result["pending_effects"]])
        self.assertFalse(result["protected_storage_preserved"])

    def test_scalar_operator_effects_and_argument_writes_fail_closed(self):
        for name in ("writes_caller", "calls_caller"):
            with self.subTest(name=name):
                result = self.check(name, use_scalar_operators=True)
                self.assertEqual(result["status"], "unknown", result)
                self.assertEqual(result["scalar_operator_checks"], [])
                self.assertIn("CXXOperatorCallExpr", [e["kind"] for e in result["pending_effects"]])
        result = self.check("argument_caller", use_scalar_operators=True)
        self.assertEqual(result["status"], "unknown", result)
        self.assertFalse(result["explicit_write_targets_checked"])
        self.assertFalse(result["protected_storage_preserved"])


if __name__ == "__main__":
    unittest.main()
