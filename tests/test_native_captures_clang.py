"""Optional native frontend tests; CI supplies a compiler-matched plugin."""
import os
from pathlib import Path
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect
from wavebridge.record_copy_check import check as check_copy


PLUGIN = os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")


@unittest.skipUnless(PLUGIN, "requires WB_NATIVE_CAPTURE_PLUGIN built for the selected compiler")
class NativeCapturesClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = collect(Path(__file__).parent / "fixtures/native_captures.cpp",
                             COMPILER, Path(PLUGIN), ["-std=c++17"])
        if cls.report["status"] != "collected":
            raise AssertionError(cls.report)
        cls.payload = cls.report["payload"]
        cls.nodes = {}
        for node in _walk(cls.payload["ast"]):
            cls.nodes.setdefault(node.get("id"), []).append(node)

    def test_inputs_and_dependencies_bound_without_checking_program(self):
        self.assertTrue(self.report["inputs_stable"])
        self.assertEqual(self.report["dependency_binding"]["status"], "observed")
        self.assertIn("stdout_sha256", self.report["execution"])
        self.assertFalse(self.report["source_program_checked"])
        self.assertFalse(self.report["deployable"])
        self.assertEqual(self.report["runtime_source_identity"], "not_established")

    def test_compiler_failure_does_not_become_collection(self):
        report = collect(Path(__file__).parent / "fixtures/native_captures.cpp",
                         COMPILER, Path(PLUGIN), ["-std=wavebridge-invalid-standard"])
        self.assertEqual(report["status"], "compile_failed")
        self.assertIsNone(report["payload"])

    def test_native_ids_resolve_in_same_embedded_ast(self):
        for capture in self.payload["captures"]:
            with self.subTest(capture=capture):
                for key, kind in (("lambda_id", "LambdaExpr"),
                                  ("closure_declaration_id", "CXXRecordDecl")):
                    self.assertTrue(any(n.get("kind") == kind for n in self.nodes[capture[key]]))
                if capture["support_status"] == "observed":
                    field = self.nodes[capture["field_declaration_id"]][0]
                    self.assertEqual(field["kind"], "FieldDecl")
                    self.assertEqual(self.nodes[capture["captured_declaration_id"]][0]["kind"], "VarDecl")
                    self.assertIn(capture["initializer_expression_id"], self.nodes)

    def test_same_type_captures_have_distinct_exact_fields(self):
        grouped = {}
        for capture in self.payload["captures"]:
            if capture["support_status"] == "observed":
                grouped.setdefault(capture["lambda_id"], []).append(capture)
        pairs = [captures for captures in grouped.values() if len(captures) == 2]
        self.assertEqual(len(pairs), 2)
        for pair in pairs:
            self.assertEqual(len({c["field_declaration_id"] for c in pair}), 2)
            self.assertEqual(len({c["captured_declaration_id"] for c in pair}), 2)
            # Corroborate API binding against each initializer's lexical reference.
            for capture in pair:
                initializer = self.nodes[capture["initializer_expression_id"]][0]
                references = [n["referencedDecl"]["id"] for n in _walk(initializer)
                              if n.get("kind") == "DeclRefExpr"]
                self.assertEqual(references, [capture["captured_declaration_id"]])

    def test_nested_path_keeps_outer_value_capture(self):
        nested = [c for c in self.payload["captures"] if c["enclosing_lambda_ids"]]
        self.assertEqual(len(nested), 1)
        inner = nested[0]
        outer = next(c for c in self.payload["captures"]
                     if c["lambda_id"] == inner["enclosing_lambda_ids"][-1])
        self.assertEqual(inner["captured_declaration_id"], outer["captured_declaration_id"])
        self.assertNotEqual(inner["field_declaration_id"], outer["field_declaration_id"])
        self.assertNotEqual(inner["capture_kind"], outer["capture_kind"])
        inner_type = self.nodes[inner["field_declaration_id"]][0]["type"]["qualType"]
        outer_type = self.nodes[outer["field_declaration_id"]][0]["type"]["qualType"]
        self.assertIn("&", inner_type)
        self.assertNotIn("&", outer_type)

    def test_init_and_this_captures_retained_as_unsupported(self):
        unsupported = [c for c in self.payload["captures"] if c["support_status"] == "unsupported"]
        self.assertTrue(any(c["is_init_capture"] for c in unsupported))
        self.assertTrue(any(c["is_this_capture"] for c in unsupported))
        self.assertTrue(all(c["unsupported_reason"] for c in unsupported))

    def test_capture_initializer_lambda_not_in_new_closure_body(self):
        found = False
        for capture in self.payload["captures"]:
            if not capture["is_init_capture"]:
                continue
            initializer = self.nodes[capture["initializer_expression_id"]][0]
            lambda_ids = {n["id"] for n in _walk(initializer) if n.get("kind") == "LambdaExpr"}
            for nested in self.payload["captures"]:
                if nested["lambda_id"] in lambda_ids:
                    found = True
                    self.assertEqual(nested["enclosing_lambda_ids"], [])
        self.assertTrue(found)

    def test_copy_checker_consumes_same_context_without_upgrading_identity(self):
        report = collect(Path(__file__).parent / "fixtures/record_copy.cpp",
                         COMPILER, Path(PLUGIN), ["-std=c++17"])
        self.assertEqual(report["status"], "collected", report)
        root = report["payload"]["ast"]
        captures = report["payload"]["captures"]
        abi = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False}}
        for name in ("captured_copy", "reference_captured_copy", "nested_captured_copy"):
            function = next(n for n in _walk(root)
                            if n.get("kind") == "FunctionDecl" and n.get("name") == name)
            target = next(n for n in _walk(function)
                          if n.get("kind") == "VarDecl" and n.get("name") == "target")
            expression = next(n for n in _walk(target) if n.get("kind") == "CXXConstructExpr")
            result = check_copy(root, expression["id"], abi)
            with self.subTest(name=name):
                self.assertEqual(result["status"], "checked", result)
                self.assertTrue(any(c["captured_declaration_id"] == result["source_declaration_id"]
                                    for c in captures))
                self.assertEqual(result["source_object_identity"], "not_established")
                self.assertFalse(result["deployable"])


class NativeCapturesInputTests(unittest.TestCase):
    def test_invalid_timeout_never_runs_compiler(self):
        for value in (0, -1, True, float("nan"), float("inf")):
            result = collect(Path("missing"), "missing", Path("missing"), [], timeout=value)
            self.assertEqual(result["reason"], "invalid_arguments")
            self.assertNotIn("execution", result)

    def test_missing_compiler_not_collected(self):
        result = collect(Path("missing"), "wavebridge-nonexistent-compiler", Path("missing"), [])
        self.assertEqual(result["status"], "tool_missing")

    def test_frontend_and_dependency_overrides_rejected(self):
        for argument in ("-MF", "-Xclang", "-Xpreprocessor", "@args", "-Wp,-M", "-fplugin=other"):
            result = collect(Path("missing"), "missing", Path("missing"), [argument])
            self.assertEqual(result["reason"], "frontend_and_dependency_options_owned_by_collector")
            self.assertNotIn("execution", result)
