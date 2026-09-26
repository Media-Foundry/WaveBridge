"""Real-Clang call-site composition for restricted builtin wrappers."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect
from wavebridge.verification.builtin_calls import (
    check_call_no_memory_write,
    check_wrapper_no_memory_write,
    inspect_structure,
)


PLUGIN = os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")

SOURCE = r"""
int counter;
float unknown_external();

float renamed_free_target() { return __builtin_huge_valf(); }

struct RenamedBox {
  static float renamed_static_target() { return __builtin_nanf(""); }
};

RenamedBox make_receiver() { counter += 1; return {}; }

float call_free() { return renamed_free_target(); }
float call_static() { return RenamedBox::renamed_static_target(); }
float call_builtin() { return __builtin_huge_valf(); }
float call_comma_callee() { return (counter++, renamed_free_target)(); }
float call_side_effect_receiver() { return make_receiver().renamed_static_target(); }
float call_pointer() { float (*pointer)() = &renamed_free_target; return pointer(); }
float call_unknown_external() { return unknown_external(); }
"""


@unittest.skipUnless(PLUGIN, "requires compiler-matched native observation plugin")
class BuiltinCallsiteClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-builtin-callsite-")
        cls.source = Path(cls.temporary.name) / "builtin_callsite.cpp"
        cls.source.write_text(SOURCE)
        cls.report = collect(cls.source, COMPILER, Path(PLUGIN), ["-std=c++17"])
        if cls.report["status"] != "collected":
            raise AssertionError(cls.report)
        cls.payload = cls.report["payload"]
        cls.root = cls.payload["ast"]
        cls.definitions = [node for node in _walk(cls.root)
                           if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"} and
                           any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                               for child in node.get("inner", []))]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def declaration(self, name):
        matches = [node for node in self.definitions if node.get("name") == name]
        self.assertEqual(len(matches), 1, (name, matches))
        return matches[0]

    def returned_call(self, function_name):
        function = self.declaration(function_name)
        returns = [node for node in _walk(function) if node.get("kind") == "ReturnStmt"]
        self.assertEqual(len(returns), 1, function_name)
        calls = [node for node in _walk(returns[0]) if node.get("kind") == "CallExpr"]
        self.assertTrue(calls, function_name)
        return calls[0]

    def leaf_record_in(self, declaration_name):
        identifiers = {node.get("id") for node in _walk(self.declaration(declaration_name))}
        matches = [record for record in self.payload["builtin_calls"]
                   if record["call_expression_id"] in identifiers]
        self.assertEqual(len(matches), 1, (declaration_name, matches))
        return matches[0]

    def effect_protocol(self, record):
        structure = inspect_structure(self.payload, record["call_expression_id"])
        self.assertEqual(structure["status"], "checked", structure)
        return {
            "schema_version": "builtin-leaf-effect-assumption/v1",
            "native_envelope_sha256": structure["input_sha256"]["native_envelope"],
            "call_expression_id": record["call_expression_id"],
            "callee_declaration_id": record["callee_declaration_id"],
            "builtin_no_memory_write_assumed": True,
            "valid_call_and_normal_return_assumed": True,
            "evidence_reference": "callsite-test-external-leaf-effect",
        }

    def test_free_static_and_direct_builtin_calls_are_conditionally_checked(self):
        cases = (
            ("call_free", self.leaf_record_in("renamed_free_target")),
            ("call_static", self.leaf_record_in("renamed_static_target")),
            ("call_builtin", self.leaf_record_in("call_builtin")),
        )
        for function_name, leaf in cases:
            call = self.returned_call(function_name)
            result = check_call_no_memory_write(
                self.payload, call["id"], self.effect_protocol(leaf))
            with self.subTest(function=function_name):
                self.assertEqual(result["status"], "checked", result)
                self.assertEqual(result["conclusion"]["status"], "conditional")
                self.assertEqual(result["conclusion"]["property"], "no_memory_write")
                self.assertEqual(result["conclusion"]["subject"], "exact_call_expression")
                self.assertEqual(result["conclusion"]["call_expression_id"], call["id"])
                self.assertEqual(result["target_check"]["status"], "checked")
                self.assertFalse(result["external_leaf_effect_verified"])
                self.assertEqual(result["value_semantics"], "not_established")
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_callee_receiver_pointer_and_unknown_external_stay_unknown(self):
        free_leaf = self.leaf_record_in("renamed_free_target")
        static_leaf = self.leaf_record_in("renamed_static_target")
        cases = (
            ("call_comma_callee", free_leaf),
            ("call_side_effect_receiver", static_leaf),
            ("call_pointer", free_leaf),
            ("call_unknown_external", free_leaf),
        )
        for function_name, leaf in cases:
            call = self.returned_call(function_name)
            result = check_call_no_memory_write(
                self.payload, call["id"], self.effect_protocol(leaf))
            with self.subTest(function=function_name):
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_wrapper_success_does_not_override_effectful_receiver_or_callee(self):
        for target_name, caller_name in (
                ("renamed_free_target", "call_comma_callee"),
                ("renamed_static_target", "call_side_effect_receiver")):
            leaf = self.leaf_record_in(target_name)
            protocol = self.effect_protocol(leaf)
            wrapper = check_wrapper_no_memory_write(
                self.payload, self.declaration(target_name)["id"], protocol)
            self.assertEqual(wrapper["status"], "checked", wrapper)
            callsite = check_call_no_memory_write(
                self.payload, self.returned_call(caller_name)["id"], protocol)
            self.assertEqual(callsite["status"], "unknown", callsite)


if __name__ == "__main__":
    unittest.main()
