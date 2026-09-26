"""Real-Clang body effects for restricted fixed-float-array initialization."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.analysis.column_loops import _check_body, _Unknown
from wavebridge.frontend.clang_ast import _walk, collect


CLANG = shutil.which("clang++")

SOURCE = r"""
float unknown_float();
struct Record { Record(); };

void literal_array() { float values[2] = {0.0f}; }
void value_initialized_array() { float values[2] = {}; }
void complete_literal_array() { float values[2] = {1.0f, 2.0f}; }
void increment_initializer(int col) {
  float values[2] = {static_cast<float>(col++)};
}
void call_initializer() { float values[2] = {unknown_float()}; }
void reference_initializer(float input) { float& alias = input; }
void record_initializer() { Record value; }
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class ArrayInitializerEffectsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-array-initializers-")
        cls.source = Path(cls.temporary.name) / "array_initializer_effects.cpp"
        cls.source.write_text(SOURCE, encoding="utf-8")
        report = collect(cls.source, CLANG, ["-std=c++17"], "literal_array",
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

    def body(self, name):
        bodies = [child for child in self.function(name).get("inner", [])
                  if isinstance(child, dict) and child.get("kind") == "CompoundStmt"]
        self.assertEqual(len(bodies), 1, name)
        return bodies[0]

    def protected(self, name, declaration_name):
        matches = [node for node in _walk(self.function(name))
                   if node.get("kind") in {"VarDecl", "ParmVarDecl"} and
                   node.get("name") == declaration_name]
        self.assertEqual(len(matches), 1, (name, declaration_name))
        return {matches[0]["id"]}

    def init_list(self, name):
        matches = [node for node in _walk(self.function(name))
                   if node.get("kind") == "InitListExpr"]
        self.assertEqual(len(matches), 1, name)
        return matches[0]

    def assert_unknown(self, body, protected_ids=frozenset()):
        with self.assertRaises(_Unknown):
            _check_body(body, set(protected_ids))

    def test_literal_and_implicit_zero_fill_fixed_arrays_are_supported(self):
        for name in ("literal_array", "value_initialized_array",
                     "complete_literal_array"):
            with self.subTest(name=name):
                initializer = self.init_list(name)
                self.assertEqual(initializer.get("type", {}).get("qualType"), "float[2]")
                filler = initializer.get("array_filler")
                # The partial and empty forms exercise Clang's out-of-inner
                # implicit-value filler representation, not a synthetic tree.
                if name != "complete_literal_array":
                    self.assertIsInstance(filler, list)
                    self.assertEqual(initializer.get("inner", []), [])
                else:
                    self.assertNotIn("array_filler", initializer)
                    self.assertEqual(len(initializer.get("inner", [])), 2)
                _check_body(self.body(name), set())

    def test_initializer_writes_calls_references_and_records_remain_unknown(self):
        self.assert_unknown(
            self.body("increment_initializer"),
            self.protected("increment_initializer", "col"))
        self.assert_unknown(self.body("call_initializer"))
        self.assert_unknown(
            self.body("reference_initializer"),
            self.protected("reference_initializer", "input"))
        self.assert_unknown(self.body("record_initializer"))

    def test_malformed_array_filler_shapes_fail_closed(self):
        body = deepcopy(self.body("literal_array"))
        initializer = next(node for node in _walk(body)
                           if node.get("kind") == "InitListExpr")
        initializer["array_filler"] = {"kind": "ImplicitValueInitExpr"}
        self.assert_unknown(body)

        body = deepcopy(self.body("literal_array"))
        initializer = next(node for node in _walk(body)
                           if node.get("kind") == "InitListExpr")
        initializer["array_filler"] = []
        self.assert_unknown(body)

        for malformed_type in (None, {"qualType": 7}):
            with self.subTest(malformed_type=malformed_type):
                body = deepcopy(self.body("literal_array"))
                initializer = next(node for node in _walk(body)
                                   if node.get("kind") == "InitListExpr")
                if malformed_type is None:
                    initializer.pop("type", None)
                else:
                    initializer["type"] = malformed_type
                self.assert_unknown(body)

    def test_hidden_side_effect_in_array_filler_is_not_ignored(self):
        source_filler = self.init_list("increment_initializer")["array_filler"]
        self.assertEqual(source_filler[-1].get("kind"), "CXXStaticCastExpr")
        self.assertTrue(any(node.get("kind") == "UnaryOperator" and node.get("opcode") == "++"
                            for node in _walk(source_filler[-1])))
        body = deepcopy(self.body("literal_array"))
        initializer = next(node for node in _walk(body)
                           if node.get("kind") == "InitListExpr")
        filler = initializer.get("array_filler")
        self.assertIsInstance(filler, list)
        initializer["array_filler"] = [deepcopy(filler[0]), deepcopy(source_filler[-1])]
        self.assert_unknown(body, self.protected("increment_initializer", "col"))


if __name__ == "__main__":
    unittest.main()
