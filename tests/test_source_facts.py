import json
from pathlib import Path
import tempfile
import unittest

from wavebridge.analysis.source_facts import extract, main


def report(*roots, status="collected", schema="clang-ast-source/v1"):
    return {"schema_version": schema, "status": status, "ast_roots": list(roots)}


def ref(node_id, name, kind="FunctionDecl"):
    return {"id": node_id, "kind": "DeclRefExpr",
            "referencedDecl": {"id": node_id + "d", "kind": kind, "name": name},
            "range": {"begin": {"line": 2}, "end": {"line": 2}}}


class SourceFactTests(unittest.TestCase):
    def test_direct_call_is_structural_and_survives_rename(self):
        for name in ("first_name", "renamed_without_rule"):
            with self.subTest(name=name):
                root = {"id": "0x0", "kind": "FunctionDecl", "inner": [
                    {"id": "0x1", "kind": "CallExpr", "range": {"begin": {}, "end": {}},
                     "inner": [{"kind": "ImplicitCastExpr", "inner": [ref("0x2", name)]}]}
                ]}
                result = extract(report(root))
                call = result["facts"]["calls"][0]
                self.assertEqual(call["resolution"], "direct")
                self.assertEqual(call["callee"]["name"], name)
                self.assertFalse(result["deployable"])

    def test_argument_function_reference_is_not_mistaken_for_callee(self):
        root = {"kind": "FunctionDecl", "inner": [
            {"id": "call", "kind": "CallExpr", "range": {},
             "inner": [ref("invoke", "invoke"), ref("callback", "callback")]}
        ]}
        result = extract(report(root))
        call = result["facts"]["calls"][0]
        self.assertEqual(call["callee"]["name"], "invoke")
        self.assertNotEqual(call["callee"]["name"], "callback")
        self.assertEqual(len(result["facts"]["declaration_references"]), 2)

    def test_indirect_call_remains_unknown(self):
        root = {"kind": "FunctionDecl", "inner": [
            {"id": "call", "kind": "CallExpr", "range": {},
             "inner": [ref("fp", "fp", kind="VarDecl"), ref("arg", "looks_callable")]}
        ]}
        call = extract(report(root))["facts"]["calls"][0]
        self.assertEqual(call["resolution"], "unknown")
        self.assertEqual(call["reason"], "indirect_or_unresolved_callee")

    def test_specialized_call_kinds_are_unknown_not_silently_dropped(self):
        for kind in ("CXXMemberCallExpr", "CXXOperatorCallExpr", "CUDAKernelCallExpr"):
            with self.subTest(kind=kind):
                root = {"kind": "FunctionDecl", "inner": [
                    {"id": "call", "kind": kind, "range": {"begin": {}, "end": {}}}
                ]}
                calls = extract(report(root))["facts"]["calls"]
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0]["resolution"], "unknown")
                self.assertEqual(calls[0]["reason"], "unsupported_call_kind")
                self.assertEqual(calls[0]["call_kind"], kind)

    def test_duplicate_clang_ids_are_isolated_by_report_hash_and_root(self):
        roots = ({"id": "same", "kind": "UnaryOperator", "opcode": "-", "range": {}},
                 {"id": "same", "kind": "UnaryOperator", "opcode": "!", "range": {}})
        operators = extract(report(*roots))["facts"]["operators"]
        self.assertNotEqual(operators[0]["node_id"], operators[1]["node_id"])
        self.assertIn(":root0:same", operators[0]["node_id"])
        self.assertIn(":root1:same", operators[1]["node_id"])
        other = extract({**report(*roots), "compiler_sha256": "different"})
        self.assertNotEqual(operators[0]["node_id"], other["facts"]["operators"][0]["node_id"])

    def test_operator_and_loop_ranges_are_preserved(self):
        source_range = {"begin": {"line": 3}, "end": {"line": 5}}
        root = {"kind": "FunctionDecl", "inner": [
            {"id": "loop", "kind": "ForStmt", "range": source_range,
             "inner": [{"id": "op", "kind": "CompoundAssignOperator", "opcode": "+=",
                        "range": source_range}]}
        ]}
        result = extract(report(root))["facts"]
        self.assertEqual(result["loops"][0]["range"], source_range)
        self.assertEqual(result["operators"][0]["opcode"], "+=")

    def test_unsupported_or_unsuccessful_input_is_rejected(self):
        for value in (report({}, schema="future/v2"), report({}, status="compile_failed"),
                      {"schema_version": "clang-ast-source/v1", "status": "collected",
                       "ast_roots": [1]}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                extract(value)

    def test_cli_exclusive_output_and_input_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path, output_path = root / "input.json", root / "output.json"
            input_path.write_text(json.dumps(report({"kind": "FunctionDecl"})))
            output_path.write_text("old")
            with self.assertRaises(SystemExit):
                main([str(input_path), "--output", str(output_path)])
            self.assertEqual(output_path.read_text(), "old")
            with self.assertRaises(SystemExit):
                main([str(input_path), "--output", str(input_path)])


if __name__ == "__main__":
    unittest.main()
