"""Real-Clang checks for the narrow builtin ``++`` column-loop subset."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from wavebridge.analysis.column_loops import recover
from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.column_coverage import check_interval


CLANG = shutil.which("clang++")

SOURCE = r"""
extern "C" int printf(const char*, ...);

void prefix_loop(int count, int* output) {
  for (int renamed = 0; renamed < count; ++renamed) output[renamed] = renamed + 10;
}
void postfix_loop(int count, int* output) {
  for (int renamed = 0; renamed < count; renamed++) output[renamed] = renamed + 10;
}
void direct_body_write(int count, int* output) {
  for (int i = 0; i < count; ++i) { output[i] = i; i = i + 1; }
}
void reference_body_write(int count, int* output) {
  for (int i = 0; i < count; ++i) { typedef int& Alias; Alias r = i; r = 4; output[i] = i; }
}
void comma_body_write(int count, int* output) {
  for (int i = 0; i < count; ++i) { (output[0], i) = 4; }
}
void increment_other(int count, int* output) {
  int other = 0;
  for (int i = 0; i < count; ++other) output[i] = i;
}
void cast_increment(int count, int* output) {
  for (int i = 0; i < count; ++(static_cast<int&>(i))) output[i] = i;
}
void unsigned_induction(int count, int* output) {
  for (unsigned i = 0; i < static_cast<unsigned>(count); ++i) output[i] = i;
}
void decrement(int count, int* output) {
  for (int i = count; i > 0; --i) output[i - 1] = i;
}

int main() {
  int prefix[6] = {}, postfix[6] = {};
  prefix_loop(6, prefix);
  postfix_loop(6, postfix);
  int equal = 1;
  for (int i = 0; i < 6; ++i) {
    if (prefix[i] != postfix[i] || prefix[i] != i + 10) equal = 0;
  }
  printf("%d %d %d\n", equal, prefix[0], prefix[5]);
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class ColumnIncrementClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.source = Path(cls.temporary.name) / "column_increment.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "prefix_loop",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.functions = {node["name"]: node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_prefix_and_postfix_builtin_increment_recover_step_one(self):
        for name, postfix in (("prefix_loop", False), ("postfix_loop", True)):
            with self.subTest(name=name):
                result = recover(self.root, self.functions[name]["id"], 32)
                self.assertEqual(result["status"], "recovered", result)
                self.assertEqual(len(result["loops"]), 1)
                loop = result["loops"][0]
                self.assertEqual(loop["step"], 1)
                self.assertEqual(loop["step_source"]["kind"], "builtin_increment")
                self.assertEqual(loop["step_source"]["value"], 1)
                self.assertEqual(loop["increment_ast"]["kind"], "UnaryOperator")
                self.assertEqual(loop["increment_ast"]["opcode"], "++")
                self.assertIs(loop["increment_ast"].get("isPostfix", False), postfix)
                self.assertTrue(loop["header_recurrence_observed"])

    def test_body_writes_and_aliases_remain_rejected(self):
        expected_reasons = {
            "direct_body_write": "protected_variable_may_be_modified",
            "reference_body_write": "unsupported_body_effect",
            "comma_body_write": "unsupported_storage_target",
        }
        for name, reason in expected_reasons.items():
            with self.subTest(name=name):
                result = recover(self.root, self.functions[name]["id"], 32)
                self.assertEqual(result["status"], "unknown", result)
                # Ordinary recovered loops report the body rejection as the
                # loop's primary reason; body_effect_reason is reserved for the
                # separate coordinate-header observation path.
                loop = result["loops"][0]
                self.assertEqual(loop["reason"], reason)
                self.assertTrue(loop["header_recurrence_observed"])
                self.assertEqual(loop["body_preserves_induction"], "not_established")

    def test_only_exact_signed_induction_builtin_increment_is_supported(self):
        for name in ("increment_other", "cast_increment", "unsigned_induction", "decrement"):
            with self.subTest(name=name):
                result = recover(self.root, self.functions[name]["id"], 32)
                self.assertEqual(result["status"], "unknown", result)
                self.assertNotEqual(result["loops"][0]["reason"], None)

    def test_cpu_prefix_and_postfix_visit_the_same_sequence(self):
        binary = Path(self.temporary.name) / "column_increment"
        compiled = subprocess.run([CLANG, "-std=c++17", str(self.source), "-o", str(binary)],
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  check=False, timeout=10)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        executed = subprocess.run([str(binary)], text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, check=False, timeout=5)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertEqual(executed.stdout.strip(), "1 10 15")

    def test_independent_coverage_model_keeps_last_increment_overflow_unknown(self):
        # This stride-2 arithmetic model is deliberately independent of the
        # source-level ++ cases above. It records the remaining coverage
        # checker's last-increment obligation, not evidence about either loop.
        result = check_interval(0, 127, [0, 1], 2, int_bits=8)
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["reason"], "signed_increment_overflow")
        self.assertFalse(result["source_program_checked"])


if __name__ == "__main__":
    unittest.main()
