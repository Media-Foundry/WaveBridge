"""Real-Clang loop recovery under conditional scalar-call effect premises."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.analysis.column_loops import (
    recover,
    recover_with_builtin_effects,
    recover_with_call_effects,
)
from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.scalar_forwarding import inspect_structure


CLANG = shutil.which("clang++")

SOURCE = r"""
float selected_leaf(float);
float unknown_float();
float global_value;
int global_counter;
constexpr int inner_bound = 3;

float forward_one(float value) { return selected_leaf(value); }
static float forward_two(float renamed) { return forward_one(renamed); }
float writing_wrapper(float value) { global_value = value; return selected_leaf(value); }

void scalar_argument(int tid, int n, float x, float* output) {
  for (int col = tid; col < n; col += 256) output[col] = forward_two(x);
}
void array_argument(int tid, int n, float x, float* output) {
  float local[2] = {x, x};
  for (int col = tid; col < n; col += 256) output[col] = forward_two(local[1] - x);
}
void writes_column(int tid, int n, float x, float* output) {
  for (int col = tid; col < n; col += 256) { output[col] = forward_two(x); col = 2; }
}
void writes_bound(int tid, int n, float x, float* output) {
  for (int col = tid; col < n; col += 256) { output[col] = forward_two(x); n = 2; }
}
void reference_alias(int tid, int n, float x, float* output) {
  for (int col = tid; col < n; col += 256) {
    int& alias = col; output[col] = forward_two(x); alias = 2;
  }
}
void increment_argument(int tid, int n, float x, float* output) {
  for (int col = tid; col < n; col += 256) output[col] = forward_two(x++);
}
void assignment_argument(int tid, int n, float x, float* output) {
  for (int col = tid; col < n; col += 256) output[col] = forward_two(x = 1.0f);
}
void unknown_argument_call(int tid, int n, float* output) {
  for (int col = tid; col < n; col += 256) output[col] = forward_two(unknown_float());
}
void comma_callee(int tid, int n, float x, float* output) {
  for (int col = tid; col < n; col += 256)
    output[col] = (global_counter++, forward_two)(x);
}
void wrapper_writes_global(int tid, int n, float x, float* output) {
  for (int col = tid; col < n; col += 256) output[col] = writing_wrapper(x);
}
void nested_positive(int tid, int n, float x, float* output) {
  for (int col = tid; col < n; col += 256)
    for (int j = 0; j < inner_bound; j += 1) output[col + j] = forward_two(x);
}
void nested_writes_outer(int tid, int n, float x, float* output) {
  for (int col = tid; col < n; col += 256)
    for (int j = 0; j < inner_bound; j += 1) {
      output[col + j] = forward_two(x); col = 2;
    }
}
void dynamic_break(int tid, int n, float x, float* output) {
  for (int col = tid; col < n; col += 256) {
    if (x > 0.0f) break;
    output[col] = forward_two(x);
  }
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class ColumnScalarEffectsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-column-scalars-")
        cls.source = Path(cls.temporary.name) / "column_scalar_effects.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "scalar_argument",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.payload = {"ast": cls.root}
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and
                         any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                             for child in node.get("inner", []))]
        cls.leaf = cls._declaration("selected_leaf", body=False)
        cls.start = cls._declaration("forward_two", body=True)
        forwarding = inspect_structure(cls.root, cls.start["id"], cls.leaf["id"])
        if forwarding["status"] != "checked":
            raise AssertionError(forwarding)
        cls.root_sha256 = forwarding["input_sha256"]["root"]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def _declaration(cls, name, *, body):
        matches = []
        for node in [item for item in _walk(cls.root)
                     if item.get("kind") == "FunctionDecl" and item.get("name") == name]:
            has_body = any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                           for child in node.get("inner", []))
            if has_body is body:
                matches.append(node)
        if len(matches) != 1:
            raise AssertionError((name, matches))
        return matches[0]

    def function(self, name):
        matches = [node for node in self.functions if node.get("name") == name]
        self.assertEqual(len(matches), 1, name)
        return matches[0]

    def wrapper_call(self, name):
        calls = [node for node in _walk(self.function(name))
                 if node.get("kind") == "CallExpr"]
        candidates = []
        for call in calls:
            refs = [node.get("referencedDecl", {}) for node in _walk(call)
                    if node.get("kind") == "DeclRefExpr"]
            if any(ref.get("id") in {self.start["id"]} or ref.get("name") == "writing_wrapper"
                   for ref in refs):
                candidates.append(call)
        self.assertEqual(len(candidates), 1, (name, calls))
        return candidates[0]

    def protocol(self, call_id):
        return {
            "schema_version": "scalar-leaf-effect-assumption/v1",
            "root_sha256": self.root_sha256,
            "call_expression_id": call_id,
            "leaf_declaration_id": self.leaf["id"],
            "leaf_no_memory_write_assumed": True,
            "valid_call_and_normal_return_assumed": True,
            "evidence_reference": "column-scalar-test-external-leaf-effect",
        }

    def protocols(self, name):
        call = self.wrapper_call(name)
        return {call["id"]: self.protocol(call["id"])}

    def composed(self, name, protocols=None, **kwargs):
        function = self.function(name)
        return recover_with_call_effects(
            self.payload, function["id"], 32,
            self.protocols(name) if protocols is None else protocols, **kwargs)

    def test_scalar_and_fixed_array_arguments_recover_only_in_new_entry(self):
        for name in ("scalar_argument", "array_argument"):
            with self.subTest(name=name):
                function = self.function(name)
                self.assertEqual(recover(self.root, function["id"], 32)["status"], "unknown")
                builtin = recover_with_builtin_effects(
                    self.payload, function["id"], 32, self.protocols(name))
                self.assertEqual(builtin["status"], "unknown", builtin)
                result = self.composed(name)
                self.assertEqual(result["schema_version"], "column-loop-call-effects/v1")
                self.assertEqual(result["status"], "recovered", result)
                self.assertEqual(result["recovery"]["schema_version"],
                                 "column-loop-recovery-with-call-effects/v1")
                self.assertEqual(len(result["call_effect_checks"]), 1)
                self.assertTrue(all(check["status"] == "checked"
                                    for check in result["call_effect_checks"].values()))
                loop = result["recovery"]["loops"][0]
                self.assertEqual(loop["body_preserves_induction"],
                                 "established_under_external_call_effect_assumptions")
                self.assertEqual(loop["body_preserves_bound"],
                                 "established_under_external_call_effect_assumptions")
                self.assertFalse(result["checked"])
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_call_protocol_does_not_hide_loop_or_argument_effects(self):
        names = ("writes_column", "writes_bound", "reference_alias", "increment_argument",
                 "assignment_argument", "unknown_argument_call", "comma_callee",
                 "wrapper_writes_global", "dynamic_break")
        for name in names:
            with self.subTest(name=name):
                result = self.composed(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["checked"])
                self.assertFalse(result["deployable"])

    def test_nested_callback_recovers_but_outer_write_stays_unknown(self):
        result = self.composed("nested_positive")
        self.assertEqual(result["status"], "recovered", result)
        outer = result["recovery"]["loops"][0]
        self.assertEqual(len(outer["nested_loops"]), 1)
        nested = outer["nested_loops"][0]
        self.assertEqual(nested["recurrence"]["status"], "recovered")
        self.assertEqual(nested["enclosing_storage_preserved"],
                         "established_under_external_call_effect_assumptions")
        refused = self.composed("nested_writes_outer")
        self.assertEqual(refused["status"], "unknown", refused)

    def test_missing_stale_and_unused_protocols_fail_closed(self):
        call = self.wrapper_call("scalar_argument")
        self.assertEqual(self.composed("scalar_argument", {})["status"], "unknown")
        stale = self.protocol(call["id"])
        stale["root_sha256"] = "stale"
        self.assertEqual(self.composed("scalar_argument", {call["id"]: stale})["status"],
                         "unknown")
        missing = self.protocol(call["id"])
        del missing["leaf_no_memory_write_assumed"]
        self.assertEqual(self.composed("scalar_argument", {call["id"]: missing})["status"],
                         "unknown")
        extra = self.protocols("scalar_argument")
        extra["unused-call"] = deepcopy(next(iter(extra.values())))
        result = self.composed("scalar_argument", extra)
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["reason"], "unused_call_protocols")
        self.assertEqual(result["unused_call_protocol_ids"], ["unused-call"])
        too_many = {f"unused-{index}": deepcopy(next(iter(extra.values())))
                    for index in range(65)}
        self.assertEqual(self.composed("scalar_argument", too_many)["reason"],
                         "invalid_inputs_or_budget")
        for budget in (1, True):
            with self.subTest(max_ast_nodes=budget):
                limited = self.composed(
                    "scalar_argument", self.protocols("scalar_argument"),
                    max_ast_nodes=budget)
                self.assertEqual(limited["status"], "unknown", limited)


if __name__ == "__main__":
    unittest.main()
