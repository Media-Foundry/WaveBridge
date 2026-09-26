"""Real-Clang tests for the narrow scalar-expression no-write subset."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.scalar_expression_effects import check_no_memory_write


CLANG = shutil.which("clang++")

SOURCE = r"""
float unknown_float();
float global_value;

float array_arithmetic(int i, int j) {
  float a[2][4] = {};
  float b[2] = {};
  return a[i][j] - b[i];
}
float scalar_arithmetic(float x, float y) { return +(x * y) - (y / 2.0f); }
int integer_arithmetic(int x, int y) { return ((x + y) * (x - y)) % (y + 1); }
float parenthesized(float x) { return (((x))); }
float automatic_local(float x) { float local = x; return local; }

int incremented(int i) { return i++; }
float pointer_read(float* pointer) { return *pointer; }
float reference_read(float& reference) { return reference; }
float volatile_read(volatile float value) { return value; }
float global_read() { return global_value; }
float static_local_read() { static float value = 1.0f; return value; }
float thread_local_read() { thread_local float value = 1.0f; return value; }
float unknown_call() { return unknown_float(); }
float assignment(float x, float y) { return (x = y); }
float comma_expression(float x, float y) { return (x, y); }
float explicit_cast(int value) { return static_cast<float>(value); }

struct Number { float value; };
Number operator+(Number left, Number right) { return {left.value + right.value}; }
float overloaded(Number left, Number right) { return (left + right).value; }
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class ScalarExpressionEffectsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-scalar-effects-")
        cls.source = Path(cls.temporary.name) / "scalar_expression_effects.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "array_arithmetic",
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

    def expression(self, name):
        functions = [node for node in self.functions if node.get("name") == name]
        self.assertEqual(len(functions), 1, name)
        returns = [node for node in _walk(functions[0]) if node.get("kind") == "ReturnStmt"]
        self.assertEqual(len(returns), 1, name)
        children = [child for child in returns[0].get("inner", [])
                    if isinstance(child, dict) and child]
        self.assertEqual(len(children), 1, name)
        return children[0]

    def check(self, name, **kwargs):
        expression = self.expression(name)
        return check_no_memory_write(self.root, expression["id"], **kwargs)

    def test_fixed_arrays_indices_and_scalar_arithmetic_are_checked(self):
        for name in ("array_arithmetic", "scalar_arithmetic", "integer_arithmetic",
                     "parenthesized", "automatic_local"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "checked", result)
                self.assertEqual(result["conclusion"]["status"], "conditional")
                self.assertEqual(result["conclusion"]["property"], "no_memory_write")
                self.assertEqual(result["conclusion"]["subject"], "exact_scalar_expression")
                self.assertEqual(result["value_semantics"], "not_established")
                self.assertFalse(result["numeric_contract_checked"])
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_mutation_call_comma_and_cast_shapes_stay_unknown(self):
        for name in ("incremented", "unknown_call", "assignment", "comma_expression",
                     "explicit_cast", "overloaded"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_pointer_reference_and_volatile_reads_stay_unknown(self):
        for name in ("pointer_read", "reference_read", "volatile_read", "global_read",
                     "static_local_read", "thread_local_read"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "unknown", result)

    def test_missing_id_and_budget_are_fail_closed(self):
        self.assertEqual(check_no_memory_write(self.root, "missing")["status"], "unknown")
        expression = self.expression("scalar_arithmetic")
        tiny = check_no_memory_write(self.root, expression["id"], max_ast_nodes=1)
        self.assertEqual(tiny["status"], "unknown", tiny)
        boolean = check_no_memory_write(self.root, expression["id"], max_ast_nodes=True)
        self.assertEqual(boolean["status"], "unknown", boolean)


if __name__ == "__main__":
    unittest.main()
