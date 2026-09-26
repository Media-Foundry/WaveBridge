"""Native observations for instantiated template record objects and constructors."""

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
int global_counter;

template <class T> struct Op {};
template <class T> struct WithConstructor {
  WithConstructor() { ++global_counter; }
};
template <class T> struct WithDestructor {
  ~WithDestructor() { ++global_counter; }
};

template <class T> void helper() {
  Op<T> r;
  WithConstructor<T> constructed;
  WithDestructor<T> destructed;
  (void)r;
  (void)constructed;
  (void)destructed;
}

void instantiate() { helper<float>(); }
"""


@unittest.skipUnless(PLUGIN, "requires compiler-matched native observation plugin")
class NativeTemplateObjectsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-native-template-objects-")
        cls.source = Path(cls.temporary.name) / "native_template_objects.cpp"
        cls.source.write_text(SOURCE, encoding="utf-8")
        cls.report = collect(cls.source, COMPILER, Path(PLUGIN), ["-std=c++17"])
        if cls.report["status"] != "collected":
            raise AssertionError(cls.report)
        cls.payload = cls.report["payload"]
        cls.root = cls.payload["ast"]
        cls.nodes = {}
        for node in _walk(cls.root):
            identifier = node.get("id")
            if isinstance(identifier, str) and identifier:
                cls.nodes.setdefault(identifier, []).append(node)
        for field in ("local_record_objects", "constructor_calls"):
            if not isinstance(cls.payload.get(field), list):
                raise AssertionError(f"native payload has no {field} list")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def instantiated_variable(self, name, type_spelling):
        matches = [node for node in _walk(self.root)
                   if node.get("kind") == "VarDecl" and node.get("name") == name and
                   node.get("type", {}).get("qualType") == type_spelling]
        self.assertEqual(len(matches), 1, (name, type_spelling, matches))
        return matches[0]

    def local_record(self, variable):
        matches = [row for row in self.payload["local_record_objects"]
                   if row.get("variable_declaration_id") == variable["id"]]
        self.assertEqual(len(matches), 1, (variable, matches))
        return matches[0]

    def construct_expression(self, variable):
        expressions = [node for node in _walk(variable)
                       if node.get("kind") == "CXXConstructExpr"]
        self.assertEqual(len(expressions), 1, variable)
        return expressions[0]

    def constructor_record(self, expression):
        matches = [row for row in self.payload["constructor_calls"]
                   if row.get("expression_id") == expression["id"]]
        self.assertEqual(len(matches), 1, (expression, matches))
        return matches[0]

    def test_instantiated_template_locals_are_present_in_record_inventory(self):
        expected = {
            "r": ("Op<float>", False),
            "constructed": ("WithConstructor<float>", False),
            "destructed": ("WithDestructor<float>", True),
        }
        for name, (spelling, nontrivial_destructor) in expected.items():
            with self.subTest(name=name):
                variable = self.instantiated_variable(name, spelling)
                row = self.local_record(variable)
                self.assertEqual(row["support_status"], "observed")
                self.assertTrue(row["has_automatic_storage_duration"])
                self.assertIs(type(row["has_nontrivial_destructor"]), bool)
                self.assertEqual(row["has_nontrivial_destructor"], nontrivial_destructor)
                records = self.nodes.get(row["record_declaration_id"], [])
                self.assertTrue(records)
                self.assertTrue(all(node.get("kind") == "ClassTemplateSpecializationDecl"
                                    for node in records))

    def test_constructor_observations_bind_exact_same_context_ast_nodes(self):
        self.assertEqual(
            self.payload["constructor_call_coverage"],
            "visited_construct_expressions_not_exhaustive")
        self.assertEqual(
            self.payload["constructor_call_semantics"],
            "compiler_identity_not_effect_or_lifetime_proof")
        for name, spelling in (("r", "Op<float>"),
                               ("constructed", "WithConstructor<float>"),
                               ("destructed", "WithDestructor<float>")):
            with self.subTest(name=name):
                variable = self.instantiated_variable(name, spelling)
                expression = self.construct_expression(variable)
                observation = self.constructor_record(expression)
                self.assertEqual(observation["expression_id"], expression["id"])
                self.assertIs(type(observation["is_trivial"]), bool)
                self.assertIs(type(observation["is_default_constructor"]), bool)
                self.assertTrue(observation["is_default_constructor"])
                arguments = [child["id"] for child in expression.get("inner", [])
                             if isinstance(child, dict) and child]
                self.assertEqual(observation["argument_expression_ids"], arguments)
                constructors = self.nodes.get(observation["constructor_declaration_id"], [])
                records = self.nodes.get(observation["record_declaration_id"], [])
                self.assertTrue(constructors)
                self.assertTrue(records)
                self.assertTrue(all(node.get("kind") == "CXXConstructorDecl"
                                    for node in constructors))
                self.assertTrue(all(node.get("kind") == "ClassTemplateSpecializationDecl"
                                    for node in records))
                self.assertTrue(any(
                    child.get("kind") == "CXXConstructorDecl" and
                    child.get("id") == observation["constructor_declaration_id"]
                    for record in records for child in record.get("inner", [])
                    if isinstance(child, dict)))

    def test_user_constructor_is_not_misreported_as_trivial(self):
        variable = self.instantiated_variable("constructed", "WithConstructor<float>")
        observation = self.constructor_record(self.construct_expression(variable))
        self.assertFalse(observation["is_trivial"])

    def test_user_destructor_remains_visible_independently_of_constructor_flag(self):
        variable = self.instantiated_variable("destructed", "WithDestructor<float>")
        local = self.local_record(variable)
        observation = self.constructor_record(self.construct_expression(variable))
        self.assertTrue(local["has_nontrivial_destructor"])
        self.assertIsNotNone(local["destructor_declaration_id"])
        destructors = self.nodes.get(local["destructor_declaration_id"], [])
        self.assertTrue(destructors)
        self.assertTrue(all(node.get("kind") == "CXXDestructorDecl" for node in destructors))
        # Constructor triviality and destructor nontriviality are distinct facts.
        self.assertIs(type(observation["is_trivial"]), bool)

    def test_native_collection_remains_observation_only(self):
        self.assertFalse(self.report["source_program_checked"])
        self.assertFalse(self.report["deployable"])


if __name__ == "__main__":
    unittest.main()
