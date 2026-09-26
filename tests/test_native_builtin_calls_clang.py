"""Native builtin-call metadata is an identity observation, not value semantics."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect


PLUGIN = os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")

SOURCE = r"""
extern float ordinary_external(const char *);
using FunctionPointer = float (*)(const char *);

float observe_calls(FunctionPointer pointer) {
  float huge = __builtin_huge_valf();
  float nan = __builtin_nanf("");
  float ordinary = ordinary_external("");
  float indirect = pointer("");
  return huge + nan + ordinary + indirect;
}
"""


@unittest.skipUnless(PLUGIN, "requires compiler-matched native observation plugin")
class NativeBuiltinCallsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-native-builtins-")
        cls.source = Path(cls.temporary.name) / "native_builtin_calls.cpp"
        cls.source.write_text(SOURCE)
        cls.report = collect(cls.source, COMPILER, Path(PLUGIN), ["-std=c++17"])
        if cls.report["status"] != "collected":
            raise AssertionError(cls.report)
        cls.payload = cls.report["payload"]
        cls.root = cls.payload["ast"]
        cls.nodes = {}
        for node in _walk(cls.root):
            identifier = node.get("id")
            if isinstance(identifier, str):
                cls.nodes.setdefault(identifier, []).append(node)
        cls.function = next(node for node in _walk(cls.root)
                            if node.get("kind") == "FunctionDecl" and
                            node.get("name") == "observe_calls" and
                            any(child.get("kind") == "CompoundStmt"
                                for child in node.get("inner", [])
                                if isinstance(child, dict)))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @staticmethod
    def direct_callee_declaration(call):
        children = [child for child in call.get("inner", [])
                    if isinstance(child, dict) and child]
        if not children:
            return None
        current = children[0]
        while current.get("kind") in {"ImplicitCastExpr", "ParenExpr"}:
            wrapped = [child for child in current.get("inner", [])
                       if isinstance(child, dict) and child]
            if len(wrapped) != 1:
                return None
            current = wrapped[0]
        if current.get("kind") != "DeclRefExpr":
            return None
        declaration = current.get("referencedDecl")
        return declaration if isinstance(declaration, dict) else None

    @classmethod
    def direct_callee_name(cls, call):
        declaration = cls.direct_callee_declaration(call)
        return declaration.get("name") if declaration is not None else None

    def test_builtin_records_bind_exact_same_context_ast_nodes(self):
        records = self.payload["builtin_calls"]
        self.assertEqual(self.payload["builtin_call_coverage"],
                         "visited_direct_builtin_calls_not_exhaustive")
        self.assertEqual(self.payload["builtin_call_semantics"],
                         "compiler_identity_not_value_or_effect_proof")
        self.assertEqual(len(records), 2, records)
        self.assertEqual({record["builtin_name"] for record in records},
                         {"__builtin_huge_valf", "__builtin_nanf"})
        self.assertEqual(len({record["call_expression_id"] for record in records}), 2)
        for record in records:
            with self.subTest(record=record):
                self.assertIs(type(record["builtin_id"]), int)
                self.assertGreater(record["builtin_id"], 0)
                calls = self.nodes.get(record["call_expression_id"], [])
                self.assertTrue(calls)
                self.assertTrue(all(node.get("kind") == "CallExpr" for node in calls))
                self.assertTrue(all(self.direct_callee_name(node) == record["builtin_name"]
                                    for node in calls))
                self.assertTrue(all(
                    self.direct_callee_declaration(node).get("id") ==
                    record["callee_declaration_id"] for node in calls))
                declarations = self.nodes.get(record["callee_declaration_id"], [])
                self.assertTrue(declarations)
                self.assertTrue(all(node.get("kind") == "FunctionDecl"
                                    for node in declarations))
                self.assertTrue(all(node.get("name") == record["builtin_name"]
                                    for node in declarations))

    def test_argument_ids_are_the_exact_call_argument_expression_ids(self):
        by_name = {record["builtin_name"]: record
                   for record in self.payload["builtin_calls"]}
        self.assertEqual(by_name["__builtin_huge_valf"]["argument_expression_ids"], [])
        nan_record = by_name["__builtin_nanf"]
        calls = self.nodes[nan_record["call_expression_id"]]
        for call in calls:
            children = [child for child in call.get("inner", [])
                        if isinstance(child, dict) and child]
            self.assertEqual(nan_record["argument_expression_ids"],
                             [child["id"] for child in children[1:]])
        self.assertEqual(len(nan_record["argument_expression_ids"]), 1)
        argument = self.nodes[nan_record["argument_expression_ids"][0]][0]
        # Clang JSON retains the source token spelling, including quotes.
        self.assertTrue(any(node.get("kind") == "StringLiteral" and node.get("value") == '\"\"'
                            for node in _walk(argument)))

    def test_ordinary_and_pointer_calls_are_negative_controls(self):
        recorded = {record["call_expression_id"] for record in self.payload["builtin_calls"]}
        calls = [node for node in _walk(self.function) if node.get("kind") == "CallExpr"]
        controls = [node for node in calls
                    if self.direct_callee_name(node) in {"ordinary_external", "pointer"}]
        self.assertEqual({self.direct_callee_name(node) for node in controls},
                         {"ordinary_external", "pointer"})
        self.assertTrue(all(node["id"] not in recorded for node in controls))
        self.assertFalse(self.report["source_program_checked"])
        self.assertFalse(self.report["deployable"])


if __name__ == "__main__":
    unittest.main()
