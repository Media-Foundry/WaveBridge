"""Real-Clang composition for one source variable initializer domain."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.initializer_domain import check_source


CLANG = shutil.which("clang++")
ABI = {
    "int": {"bits": 32, "signed": True},
    "unsigned int": {"bits": 32, "signed": False},
}

SOURCE = r"""
unsigned int external_leaf();
unsigned int other_leaf();
unsigned int renamed_getter() { return external_leaf(); }
int global_counter;

int mutable_value() { int value = renamed_getter(); return value; }
int const_value() { const int value = renamed_getter(); return value; }
int static_value() { static int value = renamed_getter(); return value; }
int tls_value() { thread_local int value = renamed_getter(); return value; }
int reference_value() { const int& value = renamed_getter(); return value; }
int indirect_value() {
  unsigned int (*pointer)() = &renamed_getter;
  int value = pointer();
  return value;
}
int comma_value() {
  int value = (global_counter++, renamed_getter());
  return value;
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class SourceInitializerDomainClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-source-initializer-domain-")
        cls.source = Path(cls.temporary.name) / "source_initializer_domain.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "mutable_value",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")]
        cls.leaf = cls._function("external_leaf", body=False)
        cls.other_leaf = cls._function("other_leaf", body=False)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def _function(cls, name, *, body):
        matches = []
        for node in cls.functions:
            if node.get("name") != name:
                continue
            has_body = any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                           for child in node.get("inner", []))
            if has_body is body:
                matches.append(node)
        if len(matches) != 1:
            raise AssertionError((name, matches))
        return matches[0]

    def variable(self, function_name, root=None):
        tree = self.root if root is None else root
        functions = [node for node in _walk(tree)
                     if node.get("kind") == "FunctionDecl" and node.get("name") == function_name and
                     any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                         for child in node.get("inner", []))]
        self.assertEqual(len(functions), 1, function_name)
        variables = [node for node in _walk(functions[0])
                     if node.get("kind") == "VarDecl" and node.get("name") == "value"]
        self.assertEqual(len(variables), 1, function_name)
        return variables[0]

    def contract(self, *, leaf=None, lower=0, upper=255):
        declaration = self.leaf if leaf is None else leaf
        return {
            "schema_version": "getter-leaf-domain/v1",
            "declaration_id": declaration["id"],
            "arguments": [],
            "return_type": {"qualType": "unsigned int"},
            "lower": lower,
            "upper": upper,
        }

    def check(self, function_name, *, root=None, contract=None, **kwargs):
        tree = self.root if root is None else root
        variable = self.variable(function_name, tree)
        return check_source(
            tree, variable["id"], self.contract() if contract is None else contract,
            ABI, **kwargs)

    def test_mutable_unsigned_getter_to_signed_initializer_is_checked(self):
        result = self.check("mutable_value")
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["result_type"], "int")
        self.assertEqual(result["result_interval"], {"lower": 0, "upper": 255})
        self.assertEqual(result["checks"]["value_link"]["status"], "recovered")
        self.assertEqual(result["checks"]["getter"]["status"], "checked")
        self.assertEqual(result["checks"]["conversion"]["status"], "checked")
        self.assertFalse(result["value_preserved_to_use"])
        self.assertEqual(result["coordinate_semantics"], "not_established")
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_const_initializer_has_the_same_initialization_time_domain_only(self):
        result = self.check("const_value")
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["result_interval"], {"lower": 0, "upper": 255})
        self.assertFalse(result["value_preserved_to_use"])
        self.assertIn("initialization", result["scope"])

    def test_non_value_preserving_unsigned_to_int_conversion_is_not_checked(self):
        result = self.check(
            "mutable_value", contract=self.contract(lower=0, upper=(1 << 32) - 1))
        self.assertIn(result["status"], {"rejected", "unknown"}, result)
        self.assertNotEqual(result["status"], "checked")
        self.assertFalse(result["source_program_checked"])

    def test_storage_reference_and_effectful_initializer_shapes_stay_unknown(self):
        for name in ("static_value", "tls_value", "reference_value",
                     "indirect_value", "comma_value"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_duplicate_declaration_wrong_leaf_and_budget_fail_closed(self):
        variable = self.variable("mutable_value")
        mutated = deepcopy(self.root)
        mutated["inner"].append(deepcopy(variable))
        duplicate = self.check("mutable_value", root=mutated)
        self.assertEqual(duplicate["status"], "unknown", duplicate)

        wrong = self.check("mutable_value", contract=self.contract(leaf=self.other_leaf))
        self.assertEqual(wrong["status"], "unknown", wrong)
        for budget in (1, True):
            with self.subTest(max_ast_nodes=budget):
                result = self.check("mutable_value", max_ast_nodes=budget)
                self.assertEqual(result["status"], "unknown", result)


if __name__ == "__main__":
    unittest.main()
