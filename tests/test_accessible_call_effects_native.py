"""Native builtin-backed effects for one restricted accessible callee chain."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect
from wavebridge.verification.accessible_call_effects import check_callee
from wavebridge.verification.array_call_effects import check as check_array
from wavebridge.verification.getter_returns import _hash


PLUGIN = os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")

SOURCE = r"""
int global_counter;
int mutable_control = 1;
const int constant_control = 1;
thread_local const int thread_control = 1;
float unknown_float(float);

float absolute_leaf(float value) { return __builtin_fabsf(value); }
float forwarded(float value) { return absolute_leaf(value); }
float accessible(float value, int selector, unsigned mask) {
  return forwarded(value);
}
float invoke(float value) { return accessible(value, 1, 2u); }
float invoke_outer_write(float value) {
  return accessible(value, global_counter = 1, 2u);
}

float writes_global(float value) {
  global_counter = 1;
  return absolute_leaf(value);
}
float invoke_write(float value) { return writes_global(value); }

float changes_inner_argument(float value) { return absolute_leaf(++value); }
float invoke_inner_write(float value) { return changes_inner_argument(value); }

float calls_unknown(float value) { return unknown_float(value); }
float invoke_unknown(float value) { return calls_unknown(value); }

float controlled_inner(float value, int control) { return absolute_leaf(value); }
float controlled_constant(float value) {
  return controlled_inner(value, (constant_control << 2) | 1);
}
float controlled_thread(float value) {
  return controlled_inner(value, (thread_control << 2) | 1);
}
float controlled_mutable(float value) {
  return controlled_inner(value, (mutable_control << 2) | 1);
}
float controlled_write(float value) {
  return controlled_inner(value, (mutable_control = 3));
}
float invoke_controlled_constant(float value) { return controlled_constant(value); }
float invoke_controlled_thread(float value) { return controlled_thread(value); }
float invoke_controlled_mutable(float value) { return controlled_mutable(value); }
float invoke_controlled_write(float value) { return controlled_write(value); }

void array_helper(float *data) { data[0] = accessible(data[0], 1, 2u); }
void array_argument_write_helper(float *data) {
  data[0] = accessible(data[0], global_counter = 1, 2u);
}
void array_caller() {
  int protected_value = 7; float buffer[8] = {}; array_helper(buffer);
  (void)protected_value;
}
void array_argument_write_caller() {
  int protected_value = 7; float buffer[8] = {}; array_argument_write_helper(buffer);
  (void)protected_value;
}
"""


@unittest.skipUnless(PLUGIN, "requires compiler-matched native observation plugin")
class AccessibleCallEffectsNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-accessible-call-effects-")
        cls.source = Path(cls.temporary.name) / "accessible_call_effects.cpp"
        cls.source.write_text(SOURCE, encoding="utf-8")
        report = collect(cls.source, COMPILER, Path(PLUGIN), ["-std=c++17"])
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.payload = report["payload"]
        cls.root = cls.payload["ast"]
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")]
        cls.builtin = [row for row in cls.payload.get("builtin_calls", [])
                       if row.get("builtin_name") == "__builtin_fabsf"]
        if len(cls.builtin) != 1:
            raise AssertionError(cls.builtin)

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
        if current.get("kind") != "DeclRefExpr":
            return None
        referenced = current.get("referencedDecl", {})
        return referenced.get("name") if isinstance(referenced, dict) else None

    def function(self, name):
        matches = [node for node in self.functions if node.get("name") == name and
                   any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                       for child in node.get("inner", []))]
        self.assertEqual(len(matches), 1, name)
        return matches[0]

    def call(self, function_name, callee_name):
        matches = [node for node in _walk(self.function(function_name))
                   if node.get("kind") == "CallExpr" and
                   self.callee_name(node) == callee_name]
        self.assertEqual(len(matches), 1, (function_name, callee_name, matches))
        return matches[0]

    def protocol(self, outer_call):
        leaf = self.builtin[0]
        return {
            "schema_version": "builtin-accessible-storage-assumption/v1",
            "native_envelope_sha256": _hash(self.payload),
            "call_expression_id": outer_call["id"],
            "leaf_call_expression_id": leaf["call_expression_id"],
            "leaf_declaration_id": leaf["callee_declaration_id"],
            "leaf_preserves_accessible_storage_assumed": True,
            "valid_execution_and_normal_return_assumed": True,
            "evidence_reference": "test-accessible-builtin-effect-evidence",
        }

    def run_check(self, function_name, callee_name, *, payload=None, protocol=None,
                  max_ast_nodes=None):
        selected = self.payload if payload is None else payload
        call = self.call(function_name, callee_name)
        contract = self.protocol(call) if protocol is None else protocol
        return check_callee(selected, call["id"], contract,
                            max_ast_nodes=max_ast_nodes)

    def array_inputs(self, caller):
        function = self.function(caller)
        calls = [node for node in _walk(function) if node.get("kind") == "CallExpr"]
        protected = [node for node in _walk(function)
                     if node.get("kind") == "VarDecl" and
                     node.get("name") == "protected_value"]
        self.assertEqual(len(calls), 1, caller)
        self.assertEqual(len(protected), 1, caller)
        return calls[0], protected[0]

    def test_two_wrapper_chain_is_conditionally_checked(self):
        result = self.run_check("invoke", "accessible")
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["conclusion"]["subject"], "callee_execution_only")
        self.assertFalse(result["outer_argument_effects_checked"])
        self.assertFalse(result["external_leaf_effect_verified"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_outer_argument_write_is_explicitly_outside_callee_scope(self):
        result = self.run_check("invoke_outer_write", "accessible")
        self.assertEqual(result["status"], "checked", result)
        self.assertFalse(result["outer_argument_effects_checked"])
        self.assertEqual(result["conclusion"]["status"], "conditional")

    def test_wrapper_write_inner_argument_write_and_unknown_call_fail_closed(self):
        for function_name, callee_name in (
                ("invoke_write", "writes_global"),
                ("invoke_inner_write", "changes_inner_argument"),
                ("invoke_unknown", "calls_unknown")):
            with self.subTest(function=function_name):
                result = self.run_check(function_name, callee_name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_protocol_must_bind_outer_call_envelope_and_exact_leaf(self):
        outer = self.call("invoke", "accessible")
        valid = self.protocol(outer)
        variants = [None]
        for key, value in (
                ("native_envelope_sha256", "stale"),
                ("call_expression_id", "other"),
                ("leaf_call_expression_id", "other"),
                ("leaf_declaration_id", "other"),
                ("leaf_preserves_accessible_storage_assumed", False),
                ("leaf_preserves_accessible_storage_assumed", 1),
                ("valid_execution_and_normal_return_assumed", False),
                ("evidence_reference", "")):
            changed = deepcopy(valid)
            changed[key] = value
            variants.append(changed)
        for protocol in variants:
            with self.subTest(protocol=protocol):
                result = check_callee(self.payload, outer["id"], protocol)
                self.assertEqual(result["status"], "unknown", result)

    def test_native_leaf_observation_and_argument_ids_are_exact(self):
        outer = self.call("invoke", "accessible")
        valid = self.protocol(outer)
        leaf = self.builtin[0]
        cases = []
        missing = deepcopy(self.payload)
        missing["builtin_calls"] = [row for row in missing["builtin_calls"]
                                    if row.get("call_expression_id") !=
                                    leaf["call_expression_id"]]
        cases.append(("missing", missing))
        duplicate = deepcopy(self.payload)
        duplicate["builtin_calls"].append(deepcopy(leaf))
        cases.append(("duplicate", duplicate))
        wrong_arguments = deepcopy(self.payload)
        next(row for row in wrong_arguments["builtin_calls"]
             if row.get("call_expression_id") == leaf["call_expression_id"])[
                 "argument_expression_ids"] = []
        cases.append(("arguments", wrong_arguments))
        for name, payload in cases:
            with self.subTest(name=name):
                rebound = deepcopy(valid)
                rebound["native_envelope_sha256"] = _hash(payload)
                result = check_callee(payload, outer["id"], rebound)
                self.assertEqual(result["status"], "unknown", result)

        self.assertEqual(check_callee(self.payload, outer["id"], valid,
                                      max_ast_nodes=1)["status"], "unknown")
        self.assertEqual(check_callee(self.payload, outer["id"], valid,
                                      max_ast_nodes=True)["status"], "unknown")

    def test_array_composition_checks_normal_arguments_and_rejects_outer_write(self):
        helper_call = self.call("array_helper", "accessible")
        protocol = self.protocol(helper_call)
        outer, protected = self.array_inputs("array_caller")
        result = check_array(
            self.root, outer["id"], protected["id"], native_payload=self.payload,
            accessible_call_protocols={helper_call["id"]: protocol})
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["protected_storage_preserved"])
        self.assertEqual(result["pending_effects"], [])
        self.assertEqual(len(result["accessible_call_checks"]), 1)
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

        writing_call = self.call("array_argument_write_helper", "accessible")
        outer, protected = self.array_inputs("array_argument_write_caller")
        writing = check_array(
            self.root, outer["id"], protected["id"], native_payload=self.payload,
            accessible_call_protocols={writing_call["id"]: self.protocol(writing_call)})
        self.assertEqual(writing["status"], "unknown", writing)
        self.assertFalse(writing["protected_storage_preserved"])

    def test_array_composition_rejects_unused_accessible_protocol(self):
        helper_call = self.call("array_helper", "accessible")
        unrelated = self.call("invoke", "accessible")
        outer, protected = self.array_inputs("array_caller")
        result = check_array(
            self.root, outer["id"], protected["id"], native_payload=self.payload,
            accessible_call_protocols={helper_call["id"]: self.protocol(helper_call),
                                       unrelated["id"]: self.protocol(unrelated)})
        self.assertEqual(result["status"], "unknown", result)
        self.assertFalse(result["protected_storage_preserved"])

    def test_constant_integer_bitwise_control_is_checked_but_other_storage_is_not(self):
        positive = self.run_check("invoke_controlled_constant", "controlled_constant")
        self.assertEqual(positive["status"], "checked", positive)
        self.assertTrue(any("constant_control" == node.get("name")
                            for node in _walk(self.root)
                            if node.get("id") in {
                                declaration_id
                                for check in positive["argument_checks"]
                                for declaration_id in check.get("read_declaration_ids", [])}))

        for function_name, callee_name in (
                ("invoke_controlled_thread", "controlled_thread"),
                ("invoke_controlled_mutable", "controlled_mutable"),
                ("invoke_controlled_write", "controlled_write")):
            with self.subTest(function=function_name):
                result = self.run_check(function_name, callee_name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])


if __name__ == "__main__":
    unittest.main()
