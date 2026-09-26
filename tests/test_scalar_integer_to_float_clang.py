"""Real-Clang no-write checks for an explicitly enabled integer-to-float cast."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.scalar_expression_effects import check_no_memory_write


CLANG = shutil.which("clang++")

SOURCE = r"""
int integer_leaf();

float signed_value(int value) { return value; }
float unsigned_value(unsigned int value) { return value; }
float arithmetic_value(int value) { return value + 1; }
float incremented(int value) { return value++; }
float called() { return integer_leaf(); }
float explicit_cast(int value) { return static_cast<float>(value); }

template <class T> bool zero_compare(T value) { return value == 0; }
template bool zero_compare<float>(float);
template bool zero_compare<double>(double);
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class ScalarIntegerToFloatClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-scalar-int-to-float-")
        cls.source = Path(cls.temporary.name) / "scalar_integer_to_float.cpp"
        cls.source.write_text(SOURCE, encoding="utf-8")
        report = collect(cls.source, CLANG, ["-std=c++17"], "signed_value",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name") and
                         any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                             for child in node.get("inner", []))]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def expression(self, name, root=None):
        tree = self.root if root is None else root
        functions = [node for node in _walk(tree)
                     if node.get("kind") == "FunctionDecl" and node.get("name") == name and
                     any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                         for child in node.get("inner", []))]
        self.assertEqual(len(functions), 1, name)
        returns = [node for node in _walk(functions[0]) if node.get("kind") == "ReturnStmt"]
        self.assertEqual(len(returns), 1, name)
        children = [child for child in returns[0].get("inner", [])
                    if isinstance(child, dict) and child]
        self.assertEqual(len(children), 1, name)
        return children[0]

    def check(self, name, *, root=None, enabled=False):
        tree = self.root if root is None else root
        expression = self.expression(name, tree)
        return check_no_memory_write(
            tree, expression["id"], allow_integer_to_float=enabled)

    def template_expression(self, root=None):
        tree = self.root if root is None else root
        matches = []
        for function in _walk(tree):
            if function.get("kind") != "FunctionDecl" or function.get("name") != "zero_compare":
                continue
            parameters = [child for child in function.get("inner", [])
                          if isinstance(child, dict) and child.get("kind") == "ParmVarDecl"]
            bodies = [child for child in function.get("inner", [])
                      if isinstance(child, dict) and child.get("kind") == "CompoundStmt"]
            if (len(parameters) == 1 and
                    parameters[0].get("type", {}).get("qualType") == "float" and len(bodies) == 1):
                returns = [node for node in _walk(bodies[0]) if node.get("kind") == "ReturnStmt"]
                if len(returns) == 1 and len(returns[0].get("inner", [])) == 1:
                    matches.append(returns[0]["inner"][0])
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_signed_and_unsigned_integral_to_float_are_checked_only_when_enabled(self):
        for name in ("signed_value", "unsigned_value", "arithmetic_value"):
            with self.subTest(name=name):
                old = self.check(name)
                self.assertEqual(old["status"], "unknown", old)
                self.assertEqual(old["reason"], "unsupported_scalar_expression")

                result = self.check(name, enabled=True)
                self.assertEqual(result["status"], "checked", result)
                self.assertEqual(result["result_type"], "float")
                self.assertEqual(result["value_semantics"], "not_established")
                self.assertFalse(result["numeric_contract_checked"])
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_operand_writes_and_calls_are_not_hidden_by_the_cast(self):
        for name in ("incremented", "called"):
            with self.subTest(name=name):
                result = self.check(name, enabled=True)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_explicit_cast_is_outside_the_implicit_cast_subset(self):
        result = self.check("explicit_cast", enabled=True)
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["reason"], "unsupported_scalar_expression")

    def test_cast_kind_and_type_evidence_are_checked(self):
        original = self.expression("signed_value")
        self.assertEqual(original.get("kind"), "ImplicitCastExpr")
        self.assertEqual(original.get("castKind"), "IntegralToFloating")
        self.assertEqual(original.get("type", {}).get("qualType"), "float")

        mutations = ("cast_kind", "target_type", "missing_type")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                changed = deepcopy(self.root)
                expression = self.expression("signed_value", changed)
                if mutation == "cast_kind":
                    expression["castKind"] = "IntegralCast"
                elif mutation == "target_type":
                    expression["type"] = {"qualType": "int"}
                else:
                    expression.pop("type", None)
                result = check_no_memory_write(
                    changed, expression["id"], allow_integer_to_float=True)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_template_shared_direct_literal_is_narrowly_normalized(self):
        expression = self.template_expression()
        literals = [node for node in _walk(expression)
                    if node.get("kind") == "IntegerLiteral" and node.get("value") == "0"]
        self.assertEqual(len(literals), 1)
        shared_id = literals[0]["id"]
        occurrences = [node for node in _walk(self.root)
                       if node.get("kind") == "IntegerLiteral" and node.get("id") == shared_id]
        self.assertGreaterEqual(len(occurrences), 2)

        old = check_no_memory_write(self.root, expression["id"])
        self.assertEqual(old["status"], "unknown", old)
        result = check_no_memory_write(
            self.root, expression["id"], allow_integer_to_float=True)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["result_type"], "bool")
        self.assertFalse(result["numeric_contract_checked"])

        changed = deepcopy(self.root)
        changed_expression = self.template_expression(changed)
        copies = [node for node in _walk(changed)
                  if node.get("kind") == "IntegerLiteral" and node.get("id") == shared_id]
        self.assertGreaterEqual(len(copies), 2)
        copies[-1]["value"] = "1"
        conflict = check_no_memory_write(
            changed, changed_expression["id"], allow_integer_to_float=True)
        self.assertEqual(conflict["status"], "unknown", conflict)
        self.assertFalse(conflict["source_program_checked"])
        self.assertFalse(conflict["deployable"])

    def test_flag_and_budget_are_strict(self):
        expression = self.expression("signed_value")
        invalid = check_no_memory_write(
            self.root, expression["id"], allow_integer_to_float=1)
        self.assertEqual(invalid["status"], "unknown", invalid)
        for budget in (1, True):
            with self.subTest(max_ast_nodes=budget):
                result = check_no_memory_write(
                    self.root, expression["id"], max_ast_nodes=budget,
                    allow_integer_to_float=True)
                self.assertEqual(result["status"], "unknown", result)


if __name__ == "__main__":
    unittest.main()
