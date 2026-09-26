"""Real-Clang interval bounds for the restricted guarded-loop composition."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.loop_exit_guards import check_iteration_bounds


CLANG = shutil.which("clang++")

SOURCE = r"""
constexpr int small_bound = 8;
constexpr int signed8_bound = 127;
constexpr int large_bound = 1025;

void leading(int limit, int* output) {
  for (int i = 0; i < small_bound; i += 1) {
    if (i >= limit) break;
    output[i] = i;
  }
}
void trailing(int limit, int base, int stride, int* output) {
  for (int i = 0; i < small_bound; i += 1) {
    int idx = base + i * stride;
    if (idx < limit) { output[i] = idx; } else break;
  }
}
void prefix_overflow_on_break(int limit, int base, int* output) {
  for (int i = 0; i < small_bound; i += 1) {
    int idx = base + 10;
    if (idx < limit) { output[i] = idx; } else break;
  }
}
void prefix_overflow_later(int limit, int base, int stride, int* output) {
  for (int i = 0; i < small_bound; i += 1) {
    int idx = base + i * stride;
    if (idx < limit) { output[i] = idx; } else break;
  }
}
void final_increment(int limit, int* output) {
  for (int i = 126; i < signed8_bound; i += 2) {
    if (i >= limit) break;
    output[0] = i;
  }
}
void too_many_iterations(int limit, int* output) {
  for (int i = 0; i < large_bound; i += 1) {
    if (i >= limit) break;
    output[0] = i;
  }
}
void writes_dependency(int limit, int* output) {
  for (int i = 0; i < small_bound; i += 1) {
    if (i >= limit) break;
    limit = 2; output[i] = limit;
  }
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class LoopExitIterationBoundsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-loop-iteration-bounds-")
        cls.source = Path(cls.temporary.name) / "loop_exit_iteration_bounds.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "leading",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.payload = {"ast": cls.root}
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

    def inputs(self, name):
        function = self.function(name)
        loops = [node for node in _walk(function) if node.get("kind") == "ForStmt"]
        self.assertEqual(len(loops), 1, name)
        parameters = {node.get("name"): node for node in function.get("inner", [])
                      if isinstance(node, dict) and node.get("kind") == "ParmVarDecl"}
        return loops[0], parameters

    def check(self, name, intervals, *, int_bits=32, **kwargs):
        loop, parameters = self.inputs(name)
        domains = {parameters[key]["id"]: value for key, value in intervals.items()}
        return check_iteration_bounds(
            self.payload, loop["id"], int_bits, {}, domains, **kwargs)

    def test_leading_definite_and_possible_breaks_bound_work_counts(self):
        exact = self.check("leading", {"limit": [3, 3]})
        self.assertEqual(exact["status"], "checked", exact)
        self.assertEqual(exact["work_count_bounds"], [3, 3])
        self.assertIs(exact["iterations"][-1]["work_executes"], False)
        self.assertFalse(exact["full_iteration_domain_established"])
        self.assertFalse(exact["source_program_checked"])
        self.assertFalse(exact["deployable"])

        uncertain = self.check("leading", {"limit": [3, 5]})
        self.assertEqual(uncertain["status"], "checked", uncertain)
        self.assertEqual(uncertain["work_count_bounds"], [3, 5])
        self.assertEqual(uncertain["original_header_iteration_count"], 8)

    def test_trailing_prefix_dag_and_interval_inputs_are_evaluated_in_order(self):
        result = self.check(
            "trailing", {"limit": [5, 6], "base": [0, 0], "stride": [2, 2]})
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["work_count_bounds"], [3, 3])
        self.assertTrue(result["iterations"])
        required = set(result["work_check"]["connection_check"]["prefix_check"]
                       ["external_read_declaration_ids"])
        required.remove(result["work_check"]["connection_check"]["induction_declaration_id"])
        self.assertEqual(set(result["declaration_intervals"]), required)

    def test_prefix_overflow_is_checked_even_on_a_break_iteration(self):
        immediate = self.check(
            "prefix_overflow_on_break", {"limit": [-128, -128], "base": [120, 120]},
            int_bits=8)
        self.assertEqual(immediate["status"], "unknown", immediate)

        later = self.check(
            "prefix_overflow_later",
            {"limit": [127, 127], "base": [120, 120], "stride": [10, 10]},
            int_bits=8)
        self.assertEqual(later["status"], "unknown", later)

    def test_increment_overflow_depends_on_possible_work(self):
        overflow = self.check("final_increment", {"limit": [127, 127]}, int_bits=8)
        self.assertEqual(overflow["status"], "unknown", overflow)

        definite_break = self.check("final_increment", {"limit": [126, 126]}, int_bits=8)
        self.assertEqual(definite_break["status"], "checked", definite_break)
        self.assertEqual(definite_break["work_count_bounds"], [0, 0])
        self.assertIs(definite_break["iterations"][-1]["work_executes"], False)

    def test_domain_shape_budget_and_work_preservation_fail_closed(self):
        loop, parameters = self.inputs("leading")
        limit_id = parameters["limit"]["id"]
        missing = check_iteration_bounds(self.payload, loop["id"], 32, {}, {})
        self.assertEqual(missing["status"], "unknown", missing)
        extra = check_iteration_bounds(
            self.payload, loop["id"], 32, {}, {limit_id: [3, 3], "unused": [0, 0]})
        self.assertEqual(extra["status"], "unknown", extra)
        fake_bool = check_iteration_bounds(
            self.payload, loop["id"], 32, {}, {limit_id: [True, True]})
        self.assertEqual(fake_bool["status"], "unknown", fake_bool)

        large = self.check("too_many_iterations", {"limit": [2000, 2000]})
        self.assertEqual(large["status"], "unknown", large)
        modified = self.check("writes_dependency", {"limit": [3, 3]})
        self.assertEqual(modified["status"], "unknown", modified)
        for budget in (1, True):
            with self.subTest(max_ast_nodes=budget):
                limited = check_iteration_bounds(
                    self.payload, loop["id"], 32, {}, {limit_id: [3, 3]},
                    max_ast_nodes=budget)
                self.assertEqual(limited["status"], "unknown", limited)


if __name__ == "__main__":
    unittest.main()
