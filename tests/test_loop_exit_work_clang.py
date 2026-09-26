"""Real-Clang work-preservation checks for connected loop exit guards."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.loop_exit_guards import (
    check_header_connection,
    check_work_preservation,
)
from wavebridge.verification.scalar_forwarding import inspect_structure


CLANG = shutil.which("clang++")

SOURCE = r"""
constexpr int column_bound = 8;
float selected_leaf(float);
float unknown_float();
float forward_one(float value) { return selected_leaf(value); }
static float forward_two(float renamed) { return forward_one(renamed); }

void leading_store(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    output[i] = i;
  }
}
void trailing_store(int limit, int base, int stride, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    int idx = base + i * stride;
    if (idx < limit) { output[i] = idx; } else break;
  }
}
void writes_induction(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    i = 2; output[0] = i;
  }
}
void writes_limit(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    limit = 2; output[i] = limit;
  }
}
void writes_base(int limit, int base, int stride, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    int idx = base + i * stride;
    if (idx < limit) { base = 2; output[i] = idx; } else break;
  }
}
void writes_stride(int limit, int base, int stride, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    int idx = base + i * stride;
    if (idx < limit) { stride = 2; output[i] = idx; } else break;
  }
}
void index_side_effect(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    output[i++] = i;
  }
}
void reference_alias(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    using Ref = int&; Ref alias = limit; alias = 2; output[i] = alias;
  }
}
void complex_lvalue(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    *(&limit) = 2; output[i] = limit;
  }
}
void inline_assembly(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    asm volatile("" : "+r"(limit)); output[i] = limit;
  }
}
void scalar_call(int limit, float x, float* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    output[i] = forward_two(x);
  }
}
void unknown_call(int limit, float x, float* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    output[i] = unknown_float();
  }
}
void scalar_argument_write(int limit, float x, float* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    output[i] = forward_two(x++);
  }
}
void nested_loop(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    for (int j = 0; j < 2; ++j) output[i] = j;
  }
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class LoopExitWorkClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-loop-exit-work-")
        cls.source = Path(cls.temporary.name) / "loop_exit_work.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "leading_store",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.payload = {"ast": cls.root}
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")]
        cls.leaf = cls._declaration("selected_leaf", body=False)
        cls.wrapper = cls._declaration("forward_two", body=True)
        forwarding = inspect_structure(cls.root, cls.wrapper["id"], cls.leaf["id"])
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
        matches = [node for node in self.functions if node.get("name") == name and
                   any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                       for child in node.get("inner", []))]
        self.assertEqual(len(matches), 1, name)
        return matches[0]

    def loop(self, name):
        loops = [node for node in _walk(self.function(name)) if node.get("kind") == "ForStmt"]
        self.assertTrue(loops, name)
        return loops[0]

    def wrapper_call(self, name):
        calls = [node for node in _walk(self.function(name)) if node.get("kind") == "CallExpr"]
        selected = []
        for call in calls:
            if any(node.get("kind") == "DeclRefExpr" and
                   node.get("referencedDecl", {}).get("id") == self.wrapper["id"]
                   for node in _walk(call)):
                selected.append(call)
        self.assertEqual(len(selected), 1, (name, calls))
        return selected[0]

    def protocol(self, call_id):
        return {
            "schema_version": "scalar-leaf-effect-assumption/v1",
            "root_sha256": self.root_sha256,
            "call_expression_id": call_id,
            "leaf_declaration_id": self.leaf["id"],
            "leaf_no_memory_write_assumed": True,
            "valid_call_and_normal_return_assumed": True,
            "evidence_reference": "loop-work-test-external-leaf-effect",
        }

    def protocols(self, name):
        call = self.wrapper_call(name)
        return {call["id"]: self.protocol(call["id"])}

    def check(self, name, protocols=None, **kwargs):
        return check_work_preservation(
            self.payload, self.loop(name)["id"], 32,
            {} if protocols is None else protocols, **kwargs)

    def test_leading_and_trailing_plain_stores_preserve_dependencies(self):
        for name in ("leading_store", "trailing_store"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "checked", result)
                self.assertEqual(result["scope"], "guarded_work_preserves_dependency_storage")
                self.assertEqual(result["connection_check"]["status"], "checked")
                self.assertTrue(result["protected_declaration_ids"])
                self.assertEqual(result["work_preserves_protected"], "conditional")
                self.assertEqual(result["call_effect_checks"], {})
                self.assertFalse(result["full_iteration_domain_established"])
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_writes_aliases_complex_lvalues_and_control_stay_unknown(self):
        names = ("writes_induction", "writes_limit", "writes_base", "writes_stride",
                 "index_side_effect", "reference_alias", "complex_lvalue",
                 "inline_assembly", "nested_loop")
        for name in names:
            with self.subTest(name=name):
                connection = check_header_connection(self.root, self.loop(name)["id"], 32)
                self.assertEqual(connection["status"], "checked", connection)
                result = self.check(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertNotEqual(result.get("work_preserves_protected"), "conditional")

    def test_scalar_call_requires_fresh_exact_protocol(self):
        protocols = self.protocols("scalar_call")
        result = self.check("scalar_call", protocols)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(len(result["call_effect_checks"]), 1)
        self.assertTrue(all(item["status"] == "checked"
                            for item in result["call_effect_checks"].values()))
        self.assertFalse(result["external_call_effects_verified"])

        self.assertEqual(self.check("scalar_call")["status"], "unknown")
        stale = deepcopy(protocols)
        next(iter(stale.values()))["root_sha256"] = "stale"
        self.assertEqual(self.check("scalar_call", stale)["status"], "unknown")
        self.assertEqual(self.check("unknown_call")["status"], "unknown")
        argument = self.check("scalar_argument_write", self.protocols("scalar_argument_write"))
        self.assertEqual(argument["status"], "unknown", argument)

    def test_unused_missing_and_budget_inputs_fail_closed(self):
        protocols = self.protocols("scalar_call")
        extra = deepcopy(protocols)
        extra["unused-call"] = deepcopy(next(iter(protocols.values())))
        unused = self.check("scalar_call", extra)
        self.assertEqual(unused["status"], "unknown", unused)
        self.assertEqual(unused["reason"], "unused_call_protocols")
        self.assertEqual(unused["unused_call_protocol_ids"], ["unused-call"])
        self.assertEqual(check_work_preservation(
            self.payload, "missing-loop", 32, {})["status"], "unknown")
        loop_id = self.loop("leading_store")["id"]
        for budget in (1, True):
            with self.subTest(max_ast_nodes=budget):
                limited = check_work_preservation(
                    self.payload, loop_id, 32, {}, max_ast_nodes=budget)
                self.assertEqual(limited["status"], "unknown", limited)


if __name__ == "__main__":
    unittest.main()
