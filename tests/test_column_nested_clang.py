"""Real-Clang checks for the bounded one-level nested ``for`` subset.

The accepted cases establish only the recorded recurrence and conditional
body-preservation facts. They do not prove reachability, memory validity,
normal completion, or source-program correctness.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from wavebridge.analysis.column_loops import recover
from wavebridge.frontend.clang_ast import _walk, collect


CLANG = shutil.which("clang++")

SOURCE = r"""
extern "C" int printf(const char*, ...);
int opaque() { return 0; }
constexpr int inner_bound = 4;
constexpr int edge_bound = 127;

void one_level(int n, int* output) {
  for (int i = 0; i < n; i += 1)
    for (int j = 0; j < inner_bound; j += 1) output[i * inner_bound + j] = i + j;
}
void shadowed_name(int n, int* output) {
  for (int i = 0; i < n; i += 1) {
    for (int i = 0; i < inner_bound; i += 1) output[i] = i;
  }
}
void inner_body_writes_outer_induction(int n, int* output) {
  for (int i = 0; i < n; i += 1)
    for (int j = 0; j < inner_bound; j += 1) { output[j] = j; i = 2; }
}
void inner_body_writes_outer_bound(int n, int* output) {
  for (int i = 0; i < n; i += 1)
    for (int j = 0; j < inner_bound; j += 1) { output[j] = j; n = 2; }
}
void reference_hides_outer_write(int n, int* output) {
  for (int i = 0; i < n; i += 1)
    for (int j = 0; j < inner_bound; j += 1) { int& alias = i; alias = 2; output[j] = j; }
}
void inner_body_writes_inner_induction(int n, int* output) {
  for (int i = 0; i < n; i += 1)
    for (int j = 0; j < inner_bound; j += 1) { output[j] = j; j = 2; }
}
void inner_start_is_outer(int n, int* output) {
  for (int i = 0; i < n; i += 1)
    for (int j = i; j < inner_bound; j += 1) output[j] = j;
}
void inner_runtime_bound(int n, int runtime_bound, int* output) {
  for (int i = 0; i < n; i += 1)
    for (int j = 0; j < runtime_bound; j += 1) output[j] = j;
}
void inner_break(int n, int* output) {
  for (int i = 0; i < n; i += 1)
    for (int j = 0; j < inner_bound; j += 1) { output[j] = j; break; }
}
void inner_call(int n, int* output) {
  for (int i = 0; i < n; i += 1)
    for (int j = 0; j < inner_bound; j += 1) output[j] = opaque();
}
void third_level(int n, int* output) {
  for (int i = 0; i < n; i += 1)
    for (int j = 0; j < inner_bound; j += 1)
      for (int k = 0; k < inner_bound; k += 1) output[k] = i + j + k;
}
void modeled_eight_bit_overflow(int n, int* output) {
  for (int i = 0; i < n; i += 1)
    for (int j = 126; j < edge_bound; j += 2) output[0] = j;
}

int main() {
  int first[8] = {}, second[4] = {};
  one_level(2, first);
  shadowed_name(2, second);
  int ok = 1;
  for (int i = 0; i < 2; ++i)
    for (int j = 0; j < 4; ++j)
      if (first[i * 4 + j] != i + j) ok = 0;
  for (int j = 0; j < 4; ++j) if (second[j] != j) ok = 0;
  printf("%d %d %d\n", ok, first[7], second[3]);
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class ColumnNestedClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.source = Path(cls.temporary.name) / "column_nested.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "one_level",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.functions = {node["name"]: node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def recover(self, name, bits=32):
        return recover(self.root, self.functions[name]["id"], bits)

    def test_one_level_and_shadowed_induction_ids_are_recovered(self):
        for name in ("one_level", "shadowed_name"):
            with self.subTest(name=name):
                result = self.recover(name)
                self.assertEqual(result["status"], "recovered", result)
                outer = result["loops"][0]
                self.assertEqual(outer["status"], "recovered")
                self.assertEqual(len(outer["nested_loops"]), 1)
                nested = outer["nested_loops"][0]
                self.assertEqual(nested["recurrence"]["status"], "recovered")
                self.assertGreaterEqual(nested["iterations"], 0)
                self.assertEqual(nested["enclosing_storage_preserved"],
                                 "established_in_supported_effect_subset")
                self.assertEqual(nested["completion"],
                                 "conditional_on_valid_body_execution")
                self.assertFalse(nested["checked"])
                self.assertFalse(nested["deployable"])
                if name == "shadowed_name":
                    inner_loop = nested["recurrence"]
                    self.assertNotEqual(outer["induction"]["declaration_id"],
                                        inner_loop["induction"]["declaration_id"])

    def test_unsupported_nested_effects_and_shapes_remain_unknown(self):
        names = (
            "inner_body_writes_outer_induction", "inner_body_writes_outer_bound",
            "reference_hides_outer_write", "inner_body_writes_inner_induction",
            "inner_start_is_outer", "inner_runtime_bound", "inner_break", "inner_call",
            "third_level",
        )
        for name in names:
            with self.subTest(name=name):
                result = self.recover(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["checked"])
                self.assertFalse(result["deployable"])

        deep = self.recover("third_level")
        self.assertEqual([loop["lexical_loop_depth"] for loop in deep["loops"]],
                         [0, 1, 2])
        self.assertEqual(deep["loops"][1]["status"], "unknown")
        self.assertEqual(deep["loops"][1]["reason"], "nested_loop_in_body")
        self.assertTrue(all(not loop["nested_loops"] for loop in deep["loops"][1:]))

    def test_external_eight_bit_model_rejects_final_inner_increment_overflow(self):
        result = self.recover("modeled_eight_bit_overflow", bits=8)
        self.assertEqual(result["status"], "unknown", result)
        self.assertFalse(result["checked"])
        self.assertFalse(result["deployable"])

    def test_cpu_oracle_runs_only_safe_positive_functions(self):
        binary = Path(self.temporary.name) / "column_nested"
        compiled = subprocess.run([CLANG, "-std=c++17", str(self.source), "-o", str(binary)],
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  check=False, timeout=10)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        executed = subprocess.run([str(binary)], text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, check=False, timeout=5)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertEqual(executed.stdout.strip(), "1 4 3")


if __name__ == "__main__":
    unittest.main()
