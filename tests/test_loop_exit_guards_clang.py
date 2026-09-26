"""Real-Clang coverage for the narrow direct loop-exit guard partition."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.loop_exit_guards import inspect_structure


CLANG = shutil.which("clang++")

SOURCE = r"""
int unknown_int();

template <int N>
void template_guard(int limit, int* output) {
  for (int i = 0; i < N; ++i) {
    if (i >= limit) break;
    output[i] = i;
  }
}
template void template_guard<4>(int, int*);
template void template_guard<5>(int, int*);

void leading(int n, int limit, int* output) {
  for (int i = 0; i < n; ++i) {
    if (i >= limit) break;
    output[i] = i;
  }
}
void trailing(int n, int limit, int* output) {
  for (int i = 0; i < n; ++i) {
    output[i] = 0;
    if (i < limit) { output[i] = i; } else break;
  }
}
void leading_with_inner_break(int n, int limit, int* output) {
  for (int i = 0; i < n; ++i) {
    if (i >= limit) break;
    for (int j = 0; j < 2; ++j) {
      if (j == 1) break;
      output[i] = j;
    }
  }
}
void increment_guard(int n, int limit, int* output) {
  for (int i = 0; i < n; ++i) { if (i++ >= limit) break; output[i] = i; }
}
void call_guard(int n, int limit, int* output) {
  for (int i = 0; i < n; ++i) { if (unknown_int() >= limit) break; output[i] = i; }
}
void pointer_guard(int n, int* limit, int* output) {
  for (int i = 0; i < n; ++i) { if (i >= *limit) break; output[i] = i; }
}
void reference_guard(int n, int& limit, int* output) {
  for (int i = 0; i < n; ++i) { if (i >= limit) break; output[i] = i; }
}
void float_guard(int n, float limit, int* output) {
  for (int i = 0; i < n; ++i) { if (i >= limit) break; output[i] = i; }
}
void break_in_middle(int n, int limit, int* output) {
  for (int i = 0; i < n; ++i) { output[i] = i; if (i >= limit) break; output[i] += 1; }
}
void extra_break(int n, int limit, int* output) {
  for (int i = 0; i < n; ++i) {
    if (i >= limit) break;
    output[i] = i;
    if (i == 3) break;
  }
}
void has_continue(int n, int limit, int* output) {
  for (int i = 0; i < n; ++i) {
    if (i >= limit) break;
    if (i == 2) continue;
    output[i] = i;
  }
}
void switch_break_only(int n, int limit, int* output) {
  for (int i = 0; i < n; ++i) {
    switch (i) { case 1: break; default: output[i] = limit; }
  }
}
void direct_return(int n, int limit, int* output) {
  for (int i = 0; i < n; ++i) {
    if (i >= limit) break;
    if (i == 2) return;
    output[i] = i;
  }
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class LoopExitGuardsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-loop-exit-guards-")
        cls.source = Path(cls.temporary.name) / "loop_exit_guards.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "leading",
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

    def outer_loop(self, name):
        loops = [node for node in _walk(self.function(name)) if node.get("kind") == "ForStmt"]
        self.assertTrue(loops, name)
        return loops[0]

    def inspect(self, name, **kwargs):
        return inspect_structure(self.root, self.outer_loop(name)["id"], **kwargs)

    def test_leading_break_guard_reports_only_the_direct_partition(self):
        loop = self.outer_loop("leading")
        result = self.inspect("leading")
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["scope"], "direct_loop_exit_guard_partition")
        self.assertEqual(result["pattern"], "leading_break_guard")
        self.assertTrue(result["break_when"])
        self.assertEqual(result["loop_id"], loop["id"])
        self.assertEqual(len(result["guard_operand_checks"]), 2)
        self.assertTrue(all(check["status"] == "checked"
                            for check in result["guard_operand_checks"]))
        self.assertEqual(result["prefix_statement_ids"], [])
        self.assertEqual(len(result["work_statement_ids"]), 1)
        self.assertFalse(result["full_iteration_domain_established"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_trailing_else_break_and_inner_break_ownership_are_supported(self):
        trailing = self.inspect("trailing")
        self.assertEqual(trailing["status"], "checked", trailing)
        self.assertEqual(trailing["pattern"], "trailing_else_break")
        self.assertFalse(trailing["break_when"])
        self.assertEqual(len(trailing["prefix_statement_ids"]), 1)
        self.assertEqual(len(trailing["work_statement_ids"]), 1)

        nested = self.inspect("leading_with_inner_break")
        self.assertEqual(nested["status"], "checked", nested)
        self.assertEqual(nested["pattern"], "leading_break_guard")
        direct_breaks = [node for node in _walk(self.outer_loop("leading_with_inner_break"))
                         if node.get("kind") == "BreakStmt"]
        self.assertEqual(len(direct_breaks), 2)
        self.assertEqual(len(nested["work_statement_ids"]), 1)

    def test_effectful_or_noninteger_guard_operands_stay_unknown(self):
        for name in ("increment_guard", "call_guard", "pointer_guard",
                     "reference_guard", "float_guard"):
            with self.subTest(name=name):
                result = self.inspect(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_unsupported_exit_control_shapes_stay_unknown(self):
        for name in ("break_in_middle", "extra_break", "has_continue",
                     "switch_break_only", "direct_return"):
            with self.subTest(name=name):
                result = self.inspect(name)
                self.assertEqual(result["status"], "unknown", result)

    def test_missing_identity_and_budget_fail_closed(self):
        self.assertEqual(inspect_structure(self.root, "missing-loop")["status"], "unknown")
        loop_id = self.outer_loop("leading")["id"]
        for budget in (1, True):
            with self.subTest(max_ast_nodes=budget):
                result = inspect_structure(self.root, loop_id, max_ast_nodes=budget)
                self.assertEqual(result["status"], "unknown", result)

    def test_template_instances_bind_shared_statements_relative_to_each_loop(self):
        instances = []
        for function in self.functions:
            if function.get("name") != "template_guard":
                continue
            arguments = [child for child in function.get("inner", [])
                         if isinstance(child, dict) and child.get("kind") == "TemplateArgument"]
            loops = [node for node in _walk(function) if node.get("kind") == "ForStmt"]
            if len(arguments) == 1 and arguments[0].get("value") in {4, 5} and len(loops) == 1:
                instances.append((arguments[0]["value"], loops[0]))
        self.assertEqual([value for value, _ in sorted(instances)], [4, 5])
        reports = []
        for value, loop in sorted(instances):
            with self.subTest(template_argument=value):
                report = inspect_structure(self.root, loop["id"])
                self.assertEqual(report["status"], "checked", report)
                self.assertEqual(report["loop_id"], loop["id"])
                self.assertEqual(report["break_binding"]["id"], report["break_id"])
                self.assertTrue(report["break_binding"]["loop_relative_child_path"])
                self.assertEqual(report["branch_binding"]["id"], report["branch_id"])
                self.assertEqual(len(report["guard_operand_checks"]), 2)
                self.assertTrue(all(item["status"] == "checked"
                                    for item in report["guard_operand_checks"]))
                reports.append(report)
        # Clang versions may share a non-dependent BreakStmt pointer/ID across
        # instantiations.  Either way, each report must carry its selected-loop
        # child path rather than treating the statement ID as a global owner.
        if reports[0]["break_id"] == reports[1]["break_id"]:
            self.assertEqual(reports[0]["break_binding"]["loop_relative_child_path"],
                             reports[1]["break_binding"]["loop_relative_child_path"])
            self.assertNotEqual(reports[0]["loop_id"], reports[1]["loop_id"])

    def test_duplicate_loop_or_guard_identity_remains_unknown(self):
        loop = self.outer_loop("leading")
        duplicate_loop = deepcopy(self.root)
        duplicate_loop["inner"].append(deepcopy(loop))
        loop_result = inspect_structure(duplicate_loop, loop["id"])
        self.assertEqual(loop_result["status"], "unknown", loop_result)
        self.assertEqual(loop_result["reason"], "loop_identity_not_unique")

        duplicate_guard = deepcopy(self.root)
        copied_loop = next(node for node in _walk(duplicate_guard)
                           if node.get("kind") == "ForStmt" and node.get("id") == loop["id"])
        body = copied_loop["inner"][-1]
        branch = body["inner"][0]
        self.assertEqual(branch["kind"], "IfStmt")
        guard = branch["inner"][0]
        self.assertEqual(guard["kind"], "BinaryOperator")
        duplicate_guard["inner"].append(deepcopy(guard))
        guard_result = inspect_structure(duplicate_guard, loop["id"])
        self.assertEqual(guard_result["status"], "unknown", guard_result)
        self.assertEqual(guard_result["reason"], "selected_identity_not_unique")


if __name__ == "__main__":
    unittest.main()
