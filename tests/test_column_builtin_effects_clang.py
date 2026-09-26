"""Real-Clang composition of column loops with conditional builtin effects."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from wavebridge.analysis.column_loops import recover, recover_with_builtin_effects
from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect
from wavebridge.verification.builtin_calls import inspect_structure


PLUGIN = os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")

SOURCE = r"""
int global_counter;
constexpr int inner_bound = 3;

float builtin_leaf() { return __builtin_huge_valf(); }
float renamed_wrapper() { return builtin_leaf(); }
float unknown_call();
float writing_wrapper() { global_counter += 1; return __builtin_huge_valf(); }

void positive(int tid, int n, float* output) {
  for (int col = tid; col < n; col += 256) output[col] = renamed_wrapper();
}
void writes_column(int tid, int n, float* output) {
  for (int col = tid; col < n; col += 256) { output[col] = renamed_wrapper(); col = 2; }
}
void writes_bound(int tid, int n, float* output) {
  for (int col = tid; col < n; col += 256) { output[col] = renamed_wrapper(); n = 2; }
}
void reference_alias(int tid, int n, float* output) {
  for (int col = tid; col < n; col += 256) { int& alias = col; output[col] = renamed_wrapper(); alias = 2; }
}
void unknown_body_call(int tid, int n, float* output) {
  for (int col = tid; col < n; col += 256) output[col] = unknown_call();
}
void writing_wrapper_call(int tid, int n, float* output) {
  for (int col = tid; col < n; col += 256) output[col] = writing_wrapper();
}
void effectful_callee(int tid, int n, float* output) {
  for (int col = tid; col < n; col += 256) output[col] = (global_counter++, renamed_wrapper)();
}
void nested_positive(int tid, int n, float* output) {
  for (int col = tid; col < n; col += 256)
    for (int j = 0; j < inner_bound; j += 1) output[col + j] = renamed_wrapper();
}
void nested_writes_outer(int tid, int n, float* output) {
  for (int col = tid; col < n; col += 256)
    for (int j = 0; j < inner_bound; j += 1) { output[col + j] = renamed_wrapper(); col = 2; }
}
"""


@unittest.skipUnless(PLUGIN, "requires compiler-matched native observation plugin")
class ColumnBuiltinEffectsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-column-builtins-")
        cls.source = Path(cls.temporary.name) / "column_builtin_effects.cpp"
        cls.source.write_text(SOURCE)
        cls.collected = collect(cls.source, COMPILER, Path(PLUGIN), ["-std=c++17"])
        if cls.collected["status"] != "collected":
            raise AssertionError(cls.collected)
        cls.payload = cls.collected["payload"]
        cls.root = cls.payload["ast"]
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and
                         any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                             for child in node.get("inner", []))]
        leaf = next(node for node in cls.functions if node.get("name") == "builtin_leaf")
        leaf_ids = {node.get("id") for node in _walk(leaf)}
        records = [record for record in cls.payload["builtin_calls"]
                   if record["call_expression_id"] in leaf_ids]
        if len(records) != 1:
            raise AssertionError(records)
        cls.leaf_record = records[0]
        structure = inspect_structure(cls.payload, cls.leaf_record["call_expression_id"])
        if structure["status"] != "checked":
            raise AssertionError(structure)
        cls.effect_protocol = {
            "schema_version": "builtin-leaf-effect-assumption/v1",
            "native_envelope_sha256": structure["input_sha256"]["native_envelope"],
            "call_expression_id": cls.leaf_record["call_expression_id"],
            "callee_declaration_id": cls.leaf_record["callee_declaration_id"],
            "builtin_no_memory_write_assumed": True,
            "valid_call_and_normal_return_assumed": True,
            "evidence_reference": "column-test-external-builtin-effect",
        }

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def function(self, name):
        matches = [node for node in self.functions if node.get("name") == name]
        self.assertEqual(len(matches), 1, name)
        return matches[0]

    def calls(self, name):
        return [node for node in _walk(self.function(name)) if node.get("kind") == "CallExpr"]

    def protocols(self, name):
        calls = self.calls(name)
        self.assertEqual(len(calls), 1, (name, calls))
        return {calls[0]["id"]: dict(self.effect_protocol)}

    def composed(self, name, protocols=None):
        function = self.function(name)
        return recover_with_builtin_effects(
            self.payload, function["id"], 32,
            self.protocols(name) if protocols is None else protocols)

    def test_default_recovery_stays_unknown_but_exact_protocol_recovers(self):
        function = self.function("positive")
        default = recover(self.root, function["id"], 32)
        self.assertEqual(default["status"], "unknown", default)
        self.assertEqual(default["schema_version"], "column-loop-recovery/v1")
        self.assertNotIn("external_call_effects_verified", default)
        result = self.composed("positive")
        self.assertEqual(result["status"], "recovered", result)
        self.assertEqual(result["recovery"]["status"], "recovered")
        self.assertEqual(result["recovery"]["schema_version"],
                         "column-loop-recovery-with-external-calls/v1")
        self.assertFalse(result["recovery"]["external_call_effects_verified"])
        self.assertEqual(len(result["call_effect_checks"]), 1)
        self.assertTrue(all(check["status"] == "checked"
                            for check in result["call_effect_checks"].values()))
        loop = result["recovery"]["loops"][0]
        self.assertEqual(loop["body_preserves_induction"],
                         "established_under_external_call_effect_assumptions")
        self.assertEqual(loop["body_preserves_bound"],
                         "established_under_external_call_effect_assumptions")
        self.assertFalse(result["checked"])
        self.assertFalse(result["deployable"])

    def test_protocol_never_hides_writes_aliases_or_unsupported_calls(self):
        for name in ("writes_column", "writes_bound", "reference_alias",
                     "unknown_body_call", "writing_wrapper_call", "effectful_callee"):
            with self.subTest(name=name):
                result = self.composed(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["checked"])
                self.assertFalse(result["deployable"])

    def test_missing_or_wrong_call_protocol_is_fail_closed(self):
        call = self.calls("positive")[0]
        self.assertEqual(self.composed("positive", {})["status"], "unknown")
        wrong_key = {"other": dict(self.effect_protocol)}
        self.assertEqual(self.composed("positive", wrong_key)["status"], "unknown")
        stale = dict(self.effect_protocol)
        stale["call_expression_id"] = "other"
        self.assertEqual(self.composed("positive", {call["id"]: stale})["status"], "unknown")
        extra = self.protocols("positive")
        extra["unused-call"] = dict(self.effect_protocol)
        result = self.composed("positive", extra)
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["reason"], "unused_call_protocols")
        self.assertEqual(result["unused_call_protocol_ids"], ["unused-call"])

    def test_nested_call_uses_callback_without_upgrading_outer_writes(self):
        positive = self.composed("nested_positive")
        self.assertEqual(positive["status"], "recovered", positive)
        outer = positive["recovery"]["loops"][0]
        self.assertEqual(len(outer["nested_loops"]), 1)
        self.assertEqual(outer["nested_loops"][0]["recurrence"]["status"], "recovered")
        self.assertEqual(outer["nested_loops"][0]["enclosing_storage_preserved"],
                         "established_under_external_call_effect_assumptions")
        self.assertEqual(outer["body_preserves_induction"],
                         "established_under_external_call_effect_assumptions")
        refused = self.composed("nested_writes_outer")
        self.assertEqual(refused["status"], "unknown", refused)


if __name__ == "__main__":
    unittest.main()
