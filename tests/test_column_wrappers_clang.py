"""Real-Clang checks for bool substitutions and loop-hint wrappers.

The checks below do not infer a template branch, erase a conditional operand,
or assign execution/performance meaning to a loop hint.
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
int opaque_value() { return 9; }
constexpr int inner_bound = 3;

template <bool Choice>
void bool_value(int n, int* output) {
  for (int i = 0; i < n; i += 1) output[i] = Choice ? i + 1 : i + 2;
}
template <bool Choice>
void bool_dead_write(int n, int* output) {
  for (int i = 0; i < n; i += 1) output[i] = Choice ? i : (i = 2);
}
template <bool Choice>
void bool_dead_call(int n, int* output) {
  for (int i = 0; i < n; i += 1) output[i] = Choice ? i : opaque_value();
}

void instantiate_templates(int n, int* output) {
  bool_value<true>(n, output);
  bool_value<false>(n, output);
  bool_dead_write<true>(n, output);
  bool_dead_call<true>(n, output);
}

void wrapped_inner(int n, int* output) {
  for (int i = 0; i < n; i += 1) {
#pragma unroll
    for (int j = 0; j < inner_bound; j += 1) output[i * inner_bound + j] = i + j;
  }
}
void wrapped_writes_outer(int n, int* output) {
  for (int i = 0; i < n; i += 1) {
#pragma unroll
    for (int j = 0; j < inner_bound; j += 1) { output[j] = j; i = 2; }
  }
}
void wrapped_inner_call(int n, int* output) {
  for (int i = 0; i < n; i += 1) {
#pragma unroll
    for (int j = 0; j < inner_bound; j += 1) output[j] = opaque_value();
  }
}
void wrapped_inner_break(int n, int* output) {
  for (int i = 0; i < n; i += 1) {
#pragma unroll
    for (int j = 0; j < inner_bound; j += 1) { output[j] = j; break; }
  }
}
void wrapped_third_level(int n, int* output) {
  for (int i = 0; i < n; i += 1) {
#pragma unroll
    for (int j = 0; j < inner_bound; j += 1) {
#pragma unroll
      for (int k = 0; k < inner_bound; k += 1) output[k] = i + j + k;
    }
  }
}
void counted_hint(int n, int* output) {
  for (int outer = 0; outer < n; outer += 1) {
#pragma clang loop unroll_count(4)
    for (int i = 0; i < inner_bound; i += 1) output[i] = outer + i;
  }
}

int main() {
  int yes[4] = {}, no[4] = {}, nested[6] = {};
  bool_value<true>(4, yes);
  bool_value<false>(4, no);
  wrapped_inner(2, nested);
  int ok = 1;
  for (int i = 0; i < 4; ++i)
    if (yes[i] != i + 1 || no[i] != i + 2) ok = 0;
  for (int i = 0; i < 2; ++i)
    for (int j = 0; j < 3; ++j)
      if (nested[i * 3 + j] != i + j) ok = 0;
  printf("%d %d %d %d\n", ok, yes[3], no[3], nested[5]);
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class ColumnWrappersClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.source = Path(cls.temporary.name) / "column_wrappers.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "instantiate_templates",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def ordinary(self, name):
        matches = [node for node in self.functions if node["name"] == name and
                   any(child.get("kind") == "CompoundStmt"
                       for child in node.get("inner", []) if isinstance(child, dict)) and
                   not any(child.get("kind") == "TemplateArgument"
                           for child in node.get("inner", []) if isinstance(child, dict))]
        self.assertEqual(len(matches), 1, name)
        return matches[0]

    def specialization(self, name, value):
        matches = []
        for node in self.functions:
            if node["name"] != name:
                continue
            arguments = [child for child in node.get("inner", [])
                         if isinstance(child, dict) and child.get("kind") == "TemplateArgument"]
            # Clang JSON spells a bool template argument as -1/0, rather
            # than Python's 1/0 convention.
            expected = -1 if value else 0
            if len(arguments) == 1 and arguments[0].get("value") == expected:
                if any(child.get("kind") == "CompoundStmt"
                       for child in node.get("inner", []) if isinstance(child, dict)):
                    matches.append(node)
        self.assertEqual(len(matches), 1, (name, value, matches))
        return matches[0]

    def result(self, function):
        return recover(self.root, function["id"], 32)

    def test_concrete_bool_substitutions_are_effect_free_values(self):
        for value in (True, False):
            with self.subTest(value=value):
                result = self.result(self.specialization("bool_value", value))
                self.assertEqual(result["status"], "recovered", result)
                self.assertFalse(result["checked"])
                self.assertFalse(result["deployable"])

    def test_bool_replacement_never_deletes_effectful_conditional_branch(self):
        for name, reason in (("bool_dead_write", "protected_variable_may_be_modified"),
                             ("bool_dead_call", "call_in_body")):
            with self.subTest(name=name):
                result = self.result(self.specialization(name, True))
                self.assertEqual(result["status"], "unknown", result)
                self.assertEqual(result["loops"][0]["reason"], reason)

    def test_loop_hint_wraps_exactly_one_supported_inner_loop(self):
        result = self.result(self.ordinary("wrapped_inner"))
        self.assertEqual(result["status"], "recovered", result)
        outer = result["loops"][0]
        self.assertEqual(len(outer["nested_loops"]), 1)
        self.assertEqual(outer["nested_loops"][0]["recurrence"]["status"], "recovered")
        self.assertFalse(outer["nested_loops"][0]["checked"])

    def test_wrapped_effects_break_and_deeper_loop_remain_unknown(self):
        names = ("wrapped_writes_outer", "wrapped_inner_call", "wrapped_inner_break",
                 "wrapped_third_level")
        for name in names:
            with self.subTest(name=name):
                result = self.result(self.ordinary(name))
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["checked"])
                self.assertFalse(result["deployable"])

    def test_loop_hint_with_expression_is_not_silently_treated_as_plain_unroll(self):
        function = self.ordinary("counted_hint")
        hints = [node for node in _walk(function) if node.get("kind") == "LoopHintAttr"]
        self.assertTrue(hints)
        has_expression_child = any(any(isinstance(child, dict) and child
                                       for child in hint.get("inner", [])) for hint in hints)
        result = self.result(function)
        if has_expression_child:
            self.assertEqual(result["status"], "unknown", result)
        else:
            # Some Clang JSON versions omit the count expression. Acceptance in
            # that representation remains only an effect-shape observation.
            self.assertIn(result["status"], {"recovered", "unknown"})
        self.assertFalse(result["checked"])
        self.assertFalse(result["deployable"])

    def test_cpu_oracle_executes_only_safe_positive_cases(self):
        binary = Path(self.temporary.name) / "column_wrappers"
        compiled = subprocess.run([CLANG, "-std=c++17", str(self.source), "-o", str(binary)],
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  check=False, timeout=10)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        executed = subprocess.run([str(binary)], text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, check=False, timeout=5)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertEqual(executed.stdout.strip(), "1 4 5 3")


if __name__ == "__main__":
    unittest.main()
