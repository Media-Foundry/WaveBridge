"""Real-Clang checks for bounded multi-level array storage targets.

Accepted cases only classify a narrow AST storage shape under the existing
source-validity and no-alias premises. They do not establish bounds, pointer
provenance, allocation, or memory safety.
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
int opaque_index() { return 0; }

void local_two_dimensional(int n, int* result) {
  int local[4][3] = {};
  for (int i = 0; i < n; i += 1) {
    local[i][1] = i + 10;
    result[i] = local[i][1];
  }
}
void pointer_to_array(int n, int (*output)[3]) {
  for (int i = 0; i < n; i += 1) output[i][2] = i + 20;
}
void pointer_to_pointer(int n, int** output) {
  for (int i = 0; i < n; i += 1) output[i][1] = i + 30;
}

void inner_index_writes_induction(int n, int** output) {
  for (int i = 0; i < n; i += 1) output[i = 1][0] = i;
}
void outer_index_writes_induction(int n, int** output) {
  for (int i = 0; i < n; i += 1) output[i][i = 1] = i;
}
void outer_index_writes_bound(int n, int** output) {
  for (int i = 0; i < n; i += 1) output[i][n = 1] = i;
}
void nested_index_calls(int n, int** output) {
  for (int i = 0; i < n; i += 1) output[i][opaque_index()] = i;
}
void inner_index_calls(int n, int** output) {
  for (int i = 0; i < n; i += 1) output[opaque_index()][0] = i;
}
void conditional_base(int n, int (*left)[3], int (*right)[3], bool flag) {
  for (int i = 0; i < n; i += 1) (flag ? left : right)[i][0] = i;
}
void comma_base(int n, int (*left)[3], int (*right)[3]) {
  for (int i = 0; i < n; i += 1) (left, right)[i][0] = i;
}
void cast_base(int n, void* raw) {
  for (int i = 0; i < n; i += 1) reinterpret_cast<int (*)[3]>(raw)[i][0] = i;
}
void c_style_cast_base(int n, void* raw) {
  for (int i = 0; i < n; i += 1) ((int**)raw)[i][0] = i;
}
struct OverloadedRows {
  int* operator[](int index) { return rows[index]; }
  int rows[4][3];
};
void overloaded_base(int n, OverloadedRows& output) {
  for (int i = 0; i < n; i += 1) output[i][0] = i;
}
void reference_index_alias(int n, int** output) {
  for (int i = 0; i < n; i += 1) {
    using Ref = int&;
    Ref alias = i;
    output[alias += 1][0] = i;
  }
}

int main() {
  int local_result[4] = {};
  int array_result[4][3] = {};
  int rows[4][2] = {};
  int* pointers[4] = {rows[0], rows[1], rows[2], rows[3]};
  local_two_dimensional(4, local_result);
  pointer_to_array(4, array_result);
  pointer_to_pointer(4, pointers);
  int ok = 1;
  for (int i = 0; i < 4; ++i) {
    if (local_result[i] != i + 10) ok = 0;
    if (array_result[i][2] != i + 20) ok = 0;
    if (rows[i][1] != i + 30) ok = 0;
  }
  printf("%d %d %d %d\n", ok, local_result[3], array_result[3][2], rows[3][1]);
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class ColumnArrayClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.source = Path(cls.temporary.name) / "column_array.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "local_two_dimensional",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.functions = {node["name"]: node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def recover(self, name):
        return recover(self.root, self.functions[name]["id"], 32)

    def test_supported_multilevel_builtin_storage_targets_recover(self):
        for name in ("local_two_dimensional", "pointer_to_array", "pointer_to_pointer"):
            with self.subTest(name=name):
                result = self.recover(name)
                self.assertEqual(result["status"], "recovered", result)
                loop = result["loops"][0]
                self.assertTrue(loop["header_recurrence_observed"])
                self.assertEqual(loop["body_preserves_induction"],
                                 "established_in_supported_effect_subset")
                self.assertFalse(result["checked"])
                self.assertFalse(result["deployable"])

    def test_every_index_expression_is_still_effect_checked(self):
        expected = {
            "inner_index_writes_induction": "protected_variable_may_be_modified",
            "outer_index_writes_induction": "protected_variable_may_be_modified",
            "outer_index_writes_bound": "protected_variable_may_be_modified",
            "nested_index_calls": "call_in_body",
            "inner_index_calls": "call_in_body",
        }
        for name, reason in expected.items():
            with self.subTest(name=name):
                result = self.recover(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertEqual(result["loops"][0]["reason"], reason)

    def test_complex_or_overloaded_bases_and_reference_alias_are_rejected(self):
        names = (
            "conditional_base", "comma_base", "cast_base", "c_style_cast_base",
            "overloaded_base", "reference_index_alias",
        )
        for name in names:
            with self.subTest(name=name):
                result = self.recover(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["checked"])
                self.assertFalse(result["deployable"])

    def test_cpu_oracle_executes_only_safe_positive_cases(self):
        binary = Path(self.temporary.name) / "column_array"
        compiled = subprocess.run([CLANG, "-std=c++17", str(self.source), "-o", str(binary)],
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  check=False, timeout=10)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        executed = subprocess.run([str(binary)], text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, check=False, timeout=5)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertEqual(executed.stdout.strip(), "1 13 23 33")


if __name__ == "__main__":
    unittest.main()
