"""Real-Clang tests for narrow host API call observations."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from experiments import softmax_host_api_evidence


CLANG = shutil.which("clang++")
FIXTURE = Path(__file__).parent / "fixtures" / "host_api_boundary.cpp"


@unittest.skipUnless(CLANG, "requires real clang++")
class SoftmaxHostApiEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(FIXTURE, CLANG, ["-std=c++17"], "declaration_only",
                         full_translation_unit=True, dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]

    def function(self, name, root=None):
        root = self.root if root is None else root
        values = [node for node in _walk(root)
                  if node.get("kind") == "FunctionDecl" and node.get("name") == name and
                  any(child.get("kind") == "CompoundStmt"
                      for child in node.get("inner", []) if isinstance(child, dict))]
        self.assertEqual(len(values), 1, name)
        return values[0]

    def selection(self, caller_name, root=None):
        root = self.root if root is None else root
        caller = self.function(caller_name, root)
        variables = [node for node in _walk(caller)
                     if node.get("kind") == "VarDecl" and node.get("name") == "width"]
        calls = [node for node in _walk(caller) if node.get("kind") == "CallExpr"]
        self.assertEqual(len(variables), 1, caller_name)
        self.assertEqual(len(calls), 1, caller_name)
        call = calls[0]
        refs = [node for node in _walk(call)
                if node.get("kind") == "DeclRefExpr" and
                node.get("referencedDecl", {}).get("kind") == "FunctionDecl"]
        self.assertEqual(len(refs), 1, caller_name)
        return call, refs[0]["referencedDecl"]["id"], variables[0]

    def observe(self, caller_name, root=None, **kwargs):
        root = self.root if root is None else root
        call, declaration_id, variable = self.selection(caller_name, root)
        return softmax_host_api_evidence.observe_call(
            root, call["id"], declaration_id, variable["id"], **kwargs)

    def test_declaration_only_call_is_observed_without_runtime_value(self):
        result = self.observe("declaration_only")
        self.assertEqual(result["status"], "observed", result)
        self.assertEqual(result["matching_symbol_definition_ids_observed"], [])
        self.assertIsNone(result["runtime_return_interval"])
        self.assertFalse(result["runtime_implementation_linkage_verified"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_same_name_other_namespace_is_not_a_matching_definition(self):
        result = self.observe("declaration_only")
        self.assertEqual(result["matching_symbol_definition_ids_observed"], [])

    def test_visible_definition_is_recorded_without_upgrading_runtime_linkage(self):
        result = self.observe("definition_visible")
        self.assertEqual(result["status"], "observed", result)
        self.assertEqual(len(result["matching_symbol_definition_ids_observed"]), 1)
        self.assertIsNone(result["runtime_return_interval"])
        self.assertFalse(result["runtime_implementation_linkage_verified"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_identity_shape_and_budget_fail_with_value_error(self):
        call, declaration_id, variable = self.selection("declaration_only")
        for budget in (0, True, 10_000_001):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                softmax_host_api_evidence.observe_call(
                    self.root, call["id"], declaration_id, variable["id"],
                    max_ast_nodes=budget)

        wrong = deepcopy(self.root)
        wrong_call, wrong_declaration, wrong_variable = self.selection("declaration_only", wrong)
        callee_ref = next(node for node in _walk(wrong_call)
                          if node.get("kind") == "DeclRefExpr" and
                          node.get("referencedDecl", {}).get("kind") == "FunctionDecl")
        other = next(node for node in _walk(wrong)
                     if node.get("kind") == "FunctionDecl" and node.get("name") == "warp_size" and
                     node.get("id") != wrong_declaration and
                     any(child.get("kind") == "CompoundStmt"
                         for child in node.get("inner", []) if isinstance(child, dict)))
        callee_ref["referencedDecl"]["id"] = other["id"]
        with self.assertRaises(ValueError):
            softmax_host_api_evidence.observe_call(
                wrong, wrong_call["id"], wrong_declaration, wrong_variable["id"])

        duplicate = deepcopy(self.root)
        duplicate_call, duplicate_declaration, duplicate_variable = self.selection(
            "declaration_only", duplicate)
        duplicate["inner"].append(deepcopy(duplicate_call))
        with self.assertRaises(ValueError):
            softmax_host_api_evidence.observe_call(
                duplicate, duplicate_call["id"], duplicate_declaration,
                duplicate_variable["id"])

        with self.assertRaises(ValueError):
            self.observe("not_direct_initializer")

    def test_download_bytes_are_hash_and_utf8_bound_when_supported(self):
        verify = getattr(softmax_host_api_evidence, "verify_download", None)
        if verify is None:
            self.skipTest("verify_download is not part of this implementation")
        data = "fixed upstream text \u03c0".encode()
        digest = hashlib.sha256(data).hexdigest()
        self.assertEqual(verify(data, digest), data.decode())
        with self.assertRaises(ValueError):
            verify(data, "0" * 64)
        with self.assertRaises(ValueError):
            verify(b"\xff", hashlib.sha256(b"\xff").hexdigest())


if __name__ == "__main__":
    unittest.main()
