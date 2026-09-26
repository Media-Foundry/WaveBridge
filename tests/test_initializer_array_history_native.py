"""Native array-call effects composed into initializer history."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.initializer_domain import check_to_statement


PLUGIN = os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")
ABI = {
    "int": {"bits": 32, "signed": True},
    "unsigned int": {"bits": 32, "signed": False},
}

SOURCE = r"""
unsigned int external_leaf();
unsigned int getter() { return external_leaf(); }
float unknown_float();
float global_value;

void safe_helper(float *data) { data[0] = 1.0f; }
void global_helper(float *data) { global_value = data[0]; }
void unknown_helper(float *data) { data[0] = unknown_float(); }

int safe_history(float *output) {
  float local[8] = {};
  int value = getter();
  safe_helper(local);
  for (int target = 0; target < 1; ++target) output[target] = value;
  return value;
}
int global_history(float *output) {
  float local[8] = {};
  int value = getter();
  global_helper(local);
  for (int target = 0; target < 1; ++target) output[target] = value;
  return value;
}
int unknown_history(float *output) {
  float local[8] = {};
  int value = getter();
  unknown_helper(local);
  for (int target = 0; target < 1; ++target) output[target] = value;
  return value;
}
int direct_write_history(float *output) {
  float local[8] = {};
  int value = getter();
  safe_helper(local);
  value = 9;
  for (int target = 0; target < 1; ++target) output[target] = value;
  return value;
}
int alias_write_history(float *output) {
  float local[8] = {};
  int value = getter();
  safe_helper(local);
  int& alias = value;
  alias = 9;
  for (int target = 0; target < 1; ++target) output[target] = value;
  return value;
}
"""


@unittest.skipUnless(PLUGIN, "requires compiler-matched native observation plugin")
class InitializerArrayHistoryNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-initializer-array-history-")
        cls.source = Path(cls.temporary.name) / "initializer_array_history.cpp"
        cls.source.write_text(SOURCE, encoding="utf-8")
        report = collect(cls.source, COMPILER, Path(PLUGIN), ["-std=c++17"])
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.payload = report["payload"]
        cls.root = cls.payload["ast"]
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")]
        leaves = [node for node in cls.functions if node.get("name") == "external_leaf" and
                  not any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                          for child in node.get("inner", []))]
        if len(leaves) != 1:
            raise AssertionError(leaves)
        cls.leaf = leaves[0]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @staticmethod
    def callee_name(call):
        children = [child for child in call.get("inner", [])
                    if isinstance(child, dict) and child]
        if not children:
            return None
        current = children[0]
        while current.get("kind") in {"ImplicitCastExpr", "ParenExpr"}:
            nested = [child for child in current.get("inner", [])
                      if isinstance(child, dict) and child]
            if len(nested) != 1:
                return None
            current = nested[0]
        referenced = current.get("referencedDecl", {})
        return referenced.get("name") if current.get("kind") == "DeclRefExpr" else None

    def function(self, name):
        matches = [node for node in self.functions if node.get("name") == name and
                   any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                       for child in node.get("inner", []))]
        self.assertEqual(len(matches), 1, name)
        return matches[0]

    def inputs(self, name):
        function = self.function(name)
        value = [node for node in _walk(function)
                 if node.get("kind") == "VarDecl" and node.get("name") == "value"]
        targets = [node for node in _walk(function) if node.get("kind") == "ForStmt"]
        calls = [node for node in _walk(function) if node.get("kind") == "CallExpr" and
                 self.callee_name(node) in {"safe_helper", "global_helper", "unknown_helper"}]
        self.assertEqual(len(value), 1, name)
        self.assertEqual(len(targets), 1, name)
        self.assertEqual(len(calls), 1, name)
        return value[0], targets[0], calls[0]

    def leaf_contract(self):
        return {
            "schema_version": "getter-leaf-domain/v1",
            "declaration_id": self.leaf["id"],
            "arguments": [],
            "return_type": {"qualType": "unsigned int"},
            "lower": 0,
            "upper": 31,
        }

    def request(self, name):
        value, _, call = self.inputs(name)
        return call, {
            "schema_version": "array-call-preservation-request/v1",
            "native_envelope_sha256": _hash(self.payload),
            "call_expression_id": call["id"],
            "protected_declaration_id": value["id"],
            "accessible_call_protocols": {},
        }

    def run_check(self, name, protocols=None):
        value, target, _ = self.inputs(name)
        if protocols is None:
            call, request = self.request(name)
            protocols = {call["id"]: request}
        return check_to_statement(
            self.payload, value["id"], target["id"], self.leaf_contract(), ABI,
            protocols)

    def test_array_only_helper_preserves_initialized_value_to_target_entry(self):
        result = self.run_check("safe_history")
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["value_preserved_to_statement"])
        self.assertEqual(result["result_interval"], {"lower": 0, "upper": 31})
        self.assertEqual(len(result["call_effect_checks"]), 1)
        child = next(iter(result["call_effect_checks"].values()))
        self.assertEqual(child["status"], "checked", child)
        self.assertTrue(child["protected_storage_preserved"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_global_write_unknown_call_and_later_source_writes_fail_closed(self):
        for name in ("global_history", "unknown_history", "direct_write_history",
                     "alias_write_history"):
            with self.subTest(name=name):
                result = self.run_check(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["value_preserved_to_statement"])

    def test_request_must_bind_payload_call_and_protected_declaration(self):
        call, valid = self.request("safe_history")
        for key, value in (("native_envelope_sha256", "stale"),
                           ("call_expression_id", "other"),
                           ("protected_declaration_id", "other")):
            with self.subTest(key=key):
                changed = deepcopy(valid)
                changed[key] = value
                result = self.run_check("safe_history", {call["id"]: changed})
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["value_preserved_to_statement"])

    def test_old_success_report_is_not_accepted_as_array_request(self):
        call, _ = self.request("safe_history")
        forged = {
            "schema_version": "array-call-write-footprint/v1",
            "status": "checked",
            "protected_storage_preserved": True,
            "source_program_checked": False,
            "deployable": False,
        }
        result = self.run_check("safe_history", {call["id"]: forged})
        self.assertEqual(result["status"], "unknown", result)
        self.assertFalse(result["value_preserved_to_statement"])

    def test_unused_array_request_is_rejected(self):
        call, valid = self.request("safe_history")
        other_call, other = self.request("global_history")
        result = self.run_check(
            "safe_history", {call["id"]: valid, other_call["id"]: other})
        self.assertEqual(result["status"], "unknown", result)
        self.assertIn(other_call["id"], result["unused_call_protocol_ids"])
        self.assertFalse(result["value_preserved_to_statement"])


if __name__ == "__main__":
    unittest.main()
