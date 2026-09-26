"""Real-Clang literal default-argument observations inside array helpers."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.array_call_effects import check


CLANG = shutil.which("clang++")

SOURCE = r"""
int global_counter;
unsigned unknown_mask();

float literal_leaf(float value, unsigned mask = 0xffffffffu) { return value; }
float bool_leaf(float value, bool enabled = true) { return value; }
float write_leaf(float value, unsigned mask = (global_counter = 1, 0u)) {
  return value;
}
float call_leaf(float value, unsigned mask = unknown_mask()) { return value; }
float redeclared_leaf(float value, unsigned mask = 7u);
float redeclared_leaf(float value, unsigned mask) { return value; }

void literal_helper(float *data) { data[0] = literal_leaf(data[0]); }
void bool_helper(float *data) { data[0] = bool_leaf(data[0]); }
void write_helper(float *data) { data[0] = write_leaf(data[0]); }
void call_helper(float *data) { data[0] = call_leaf(data[0]); }
void redeclared_helper(float *data) { data[0] = redeclared_leaf(data[0]); }
void explicit_helper(float *data) { data[0] = literal_leaf(data[0], 0u); }

void literal_caller() {
  int protected_value = 7; float buffer[8] = {}; literal_helper(buffer);
  (void)protected_value;
}
void bool_caller() {
  int protected_value = 7; float buffer[8] = {}; bool_helper(buffer);
}
void write_caller() {
  int protected_value = 7; float buffer[8] = {}; write_helper(buffer);
}
void call_caller() {
  int protected_value = 7; float buffer[8] = {}; call_helper(buffer);
}
void redeclared_caller() {
  int protected_value = 7; float buffer[8] = {}; redeclared_helper(buffer);
}
void explicit_caller() {
  int protected_value = 7; float buffer[8] = {}; explicit_helper(buffer);
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class ArrayDefaultArgumentsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-array-defaults-")
        cls.source = Path(cls.temporary.name) / "array_default_arguments.cpp"
        cls.source.write_text(SOURCE, encoding="utf-8")
        report = collect(cls.source, CLANG, ["-std=c++17"], "literal_caller",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def function(self, name):
        matches = [node for node in self.functions if node.get("name") == name and
                   any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                       for child in node.get("inner", []))]
        self.assertEqual(len(matches), 1, name)
        return matches[0]

    def inputs(self, caller):
        function = self.function(caller)
        calls = [node for node in _walk(function) if node.get("kind") == "CallExpr"]
        protected = [node for node in _walk(function)
                     if node.get("kind") == "VarDecl" and
                     node.get("name") == "protected_value"]
        self.assertEqual(len(calls), 1, caller)
        self.assertEqual(len(protected), 1, caller)
        return calls[0]["id"], protected[0]["id"]

    def run_check(self, caller, **kwargs):
        call_id, protected_id = self.inputs(caller)
        return check(self.root, call_id, protected_id, **kwargs)

    def test_literal_unsigned_and_bool_defaults_are_checked_but_call_remains_pending(self):
        for caller, expected_type in (("literal_caller", "unsigned int"),
                                      ("bool_caller", "bool")):
            with self.subTest(caller=caller):
                result = self.run_check(caller, use_literal_defaults=True)
                self.assertEqual(result["status"], "unknown", result)
                self.assertEqual(len(result["default_argument_checks"]), 1)
                default = result["default_argument_checks"][0]
                self.assertEqual(default["status"], "checked")
                literal_type = default["literal_ast"]["type"].get(
                    "desugaredQualType", default["literal_ast"]["type"].get("qualType"))
                self.assertEqual(literal_type, expected_type)
                self.assertTrue(result["explicit_write_targets_checked"])
                self.assertIn("CallExpr", [effect["kind"]
                                            for effect in result["pending_effects"]])
                self.assertNotIn("CXXDefaultArgExpr", [effect["kind"]
                                                       for effect in result["pending_effects"]])
                self.assertFalse(result["protected_storage_preserved"])
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_default_mode_preserves_default_argument_pending_effect(self):
        result = self.run_check("literal_caller")
        self.assertEqual(result["status"], "unknown", result)
        self.assertIn("CXXDefaultArgExpr", [effect["kind"]
                                           for effect in result["pending_effects"]])
        self.assertNotIn("default_argument_checks", result)

    def test_side_effecting_or_calling_default_value_is_not_discharged(self):
        for caller in ("write_caller", "call_caller"):
            with self.subTest(caller=caller):
                result = self.run_check(caller, use_literal_defaults=True)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["protected_storage_preserved"])
                self.assertIn("CXXDefaultArgExpr", [effect["kind"]
                                                   for effect in result["pending_effects"]])

    def test_inherited_default_from_redeclaration_is_not_discharged(self):
        result = self.run_check("redeclared_caller", use_literal_defaults=True)
        self.assertEqual(result["status"], "unknown", result)
        self.assertFalse(result["protected_storage_preserved"])
        self.assertIn("CXXDefaultArgExpr", [effect["kind"]
                                           for effect in result["pending_effects"]])

    def test_explicit_argument_has_no_default_placeholder_or_default_check(self):
        result = self.run_check("explicit_caller", use_literal_defaults=True)
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["default_argument_checks"], [])
        self.assertNotIn("CXXDefaultArgExpr", [effect["kind"]
                                               for effect in result["pending_effects"]])
        self.assertIn("CallExpr", [effect["kind"] for effect in result["pending_effects"]])


if __name__ == "__main__":
    unittest.main()
