"""Real-Clang coverage for the restricted signed-int expression evaluator."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from wavebridge.analysis.integer_constants import evaluate
from wavebridge.frontend.clang_ast import _walk, collect


CLANG = shutil.which("clang++")


SOURCE = r"""
extern int opaque_value();
extern "C" int printf(const char*, ...);

template <int Parameter>
int calculate() {
  constexpr int renamed_power = 1 << Parameter;
  constexpr int renamed_group = renamed_power >> 2;
  constexpr int renamed_count = renamed_power / renamed_group;
  constexpr int renamed_batches = renamed_power <= 128 ? 2 : 1;
  constexpr int compare_eq = Parameter == 7 ? 17 : 19;
  constexpr int compare_ne = Parameter != 8 ? 23 : 29;
  constexpr int compare_lt = Parameter < 8 ? 31 : 37;
  constexpr int compare_le = Parameter <= 7 ? 37 : 39;
  constexpr int compare_gt = Parameter > 6 ? 43 : 45;
  constexpr int compare_ge = Parameter >= 7 ? 41 : 43;
  constexpr int integer_condition = Parameter ? 47 : 53;
  constexpr int negated_condition = !0 ? 59 : 61;
  constexpr int literal_condition = true ? 63 : 65;
  constexpr int conjunction = (Parameter == 7 && Parameter < 8) ? 67 : 71;
  constexpr int short_conjunction = (Parameter != 7 && opaque_value()) ? 69 : 71;
  constexpr int disjunction = (Parameter == 7 || opaque_value()) ? 73 : 79;
  constexpr int dead_division = Parameter == 7 ? 83 : (1 / 0);
  constexpr int dead_call = Parameter == 7 ? 89 : opaque_value();
  return renamed_power + renamed_group + renamed_count + renamed_batches +
         compare_eq + compare_ne + compare_lt + compare_le + compare_gt + compare_ge +
         integer_condition + negated_condition + literal_condition + conjunction +
         short_conjunction + disjunction + dead_division + dead_call;
}

int oracle_values() {
  return calculate<7>();
}

int main() {
  printf("%d %d %d %d %d\n", 1 << 7, (1 << 7) >> 2,
         (1 << 7) / ((1 << 7) >> 2), (1 << 7) <= 128 ? 2 : 1,
         oracle_values());
}
"""


# Parsed for conservative rejection only. This source is never linked or
# executed because several initializers have undefined/implementation-defined
# C++17 behavior.
UNSUPPORTED_SOURCE = r"""
const int negative_left_operand = -1 << 1;
const int negative_right_operand = -2 >> 1;
const int negative_shift_count = 1 << -1;
const int excessive_shift_count = 1 << 32;
const int signed_left_overflow = 1 << 31;
const int unsigned_shift = 1u << 2;
const int explicit_conversion = static_cast<int>(3u);
int unsupported_anchor() { return explicit_conversion; }
"""


def _declarations(root, name):
    return [node for node in _walk(root)
            if node.get("kind") == "VarDecl" and node.get("name") == name and
            isinstance(node.get("id"), str) and node.get("init") is not None]


def _evaluated(root, name):
    """Return one result only when every evaluable occurrence agrees."""
    results = [evaluate(root, node["id"], 32) for node in _declarations(root, name)]
    successes = [result for result in results if result["status"] == "evaluated"]
    if not successes or len({result["value"] for result in successes}) != 1:
        raise AssertionError((name, results))
    return successes[0]


@unittest.skipUnless(CLANG, "requires real clang++")
class IntegerConstantExpressionsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.source = Path(cls.temporary.name) / "expressions.cpp"
        cls.source.write_text(SOURCE)
        cls.unsupported_source = Path(cls.temporary.name) / "unsupported.cpp"
        cls.unsupported_source.write_text(UNSUPPORTED_SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "calculate",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        unsupported = collect(cls.unsupported_source, CLANG, ["-std=c++17"],
                              "unsupported_anchor", full_translation_unit=True)
        if unsupported["status"] != "collected":
            raise AssertionError(unsupported.get("execution"))
        cls.unsupported_root = unsupported["ast_roots"][0]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_template_substitution_shifts_and_conditional_values(self):
        expected = {
            "renamed_power": 128,
            "renamed_group": 32,
            "renamed_count": 4,
            "renamed_batches": 2,
            "compare_eq": 17,
            "compare_ne": 23,
            "compare_lt": 31,
            "compare_le": 37,
            "compare_gt": 43,
            "compare_ge": 41,
            "integer_condition": 47,
            "negated_condition": 59,
            "literal_condition": 63,
            "conjunction": 67,
        }
        for name, value in expected.items():
            with self.subTest(name=name):
                self.assertEqual(_evaluated(self.root, name)["value"], value)

        instantiated = [node for node in _walk(self.root)
                        if node.get("kind") == "SubstNonTypeTemplateParmExpr"]
        self.assertTrue(instantiated, "fixture must exercise a real template substitution")

    def test_short_circuit_does_not_evaluate_dead_call_or_division(self):
        for name, value in (("short_conjunction", 71), ("disjunction", 73),
                            ("dead_division", 83), ("dead_call", 89)):
            with self.subTest(name=name):
                self.assertEqual(_evaluated(self.root, name)["value"], value)

    def test_renamed_identifiers_do_not_supply_semantics(self):
        # These intentionally avoid names such as width, warp, block, or batch-size.
        self.assertEqual(_evaluated(self.root, "renamed_power")["value"], 128)
        self.assertEqual(_evaluated(self.root, "renamed_group")["value"], 32)

    def test_unsupported_or_undefined_shift_and_conversion_shapes_are_unknown(self):
        for name in (
                "negative_left_operand", "negative_right_operand",
                "negative_shift_count", "excessive_shift_count",
                "signed_left_overflow", "unsigned_shift", "explicit_conversion"):
            with self.subTest(name=name):
                results = [evaluate(self.unsupported_root, node["id"], 32)
                           for node in _declarations(self.unsupported_root, name)]
                self.assertTrue(results, name)
                self.assertTrue(all(result["status"] == "unknown" for result in results),
                                results)

    def test_compiled_cpu_oracle_for_legal_subset(self):
        binary = Path(self.temporary.name) / "oracle"
        compiled = subprocess.run(
            [CLANG, "-std=c++17", str(self.source), "-o", str(binary)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=10)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        executed = subprocess.run([str(binary)], text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, check=False, timeout=5)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        values = [int(value) for value in executed.stdout.split()]
        self.assertEqual(values[:4], [128, 32, 4, 2])
        expected_sum = sum((128, 32, 4, 2, 17, 23, 31, 37, 43, 41, 47, 59,
                            63, 67, 71, 73, 83, 89))
        self.assertEqual(values[4], expected_sum)


if __name__ == "__main__":
    unittest.main()
