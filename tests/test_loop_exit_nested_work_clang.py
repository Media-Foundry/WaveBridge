"""Real-Clang checks for explicitly enabled nested guarded work loops."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.loop_exit_guards import check_work_preservation


CLANG = shutil.which("clang++")

SOURCE = r"""
constexpr int outer_bound = 8;
constexpr int inner_bound = 4;
int unknown_int();

void nested_leading(int outer_limit, int inner_limit, int* output) {
  for (int i = 0; i < outer_bound; i += 1) {
    if (i >= outer_limit) break;
    for (int j = 0; j < inner_bound; j += 1) {
      if (j >= inner_limit) break;
      output[i + j] = i + j;
    }
  }
}
void nested_trailing(int outer_limit, int inner_limit, int base, int stride, int* output) {
  for (int i = 0; i < outer_bound; i += 1) {
    if (i >= outer_limit) break;
    for (int j = 0; j < inner_bound; j += 1) {
      int idx = base + j * stride;
      if (idx < inner_limit) { output[i + j] = idx; } else break;
    }
  }
}
void inner_writes_outer_induction(int outer_limit, int inner_limit, int* output) {
  for (int i = 0; i < outer_bound; i += 1) {
    if (i >= outer_limit) break;
    for (int j = 0; j < inner_bound; j += 1) {
      if (j >= inner_limit) break;
      i = 2; output[j] = i;
    }
  }
}
void inner_writes_outer_guard(int outer_limit, int inner_limit, int* output) {
  for (int i = 0; i < outer_bound; i += 1) {
    if (i >= outer_limit) break;
    for (int j = 0; j < inner_bound; j += 1) {
      if (j >= inner_limit) break;
      outer_limit = 2; output[i + j] = outer_limit;
    }
  }
}
void inner_header_side_effect(int outer_limit, int inner_limit, int* output) {
  for (int i = 0; i < outer_bound; i += 1) {
    if (i >= outer_limit) break;
    for (int j = (i = 2); j < inner_bound; j += 1) {
      if (j >= inner_limit) break;
      output[j] = j;
    }
  }
}
void inner_prefix_side_effect(int outer_limit, int inner_limit, int base, int* output) {
  for (int i = 0; i < outer_bound; i += 1) {
    if (i >= outer_limit) break;
    for (int j = 0; j < inner_bound; j += 1) {
      base = base + j;
      if (base < inner_limit) { output[i + j] = base; } else break;
    }
  }
}
void inner_alias_writes_outer(int outer_limit, int inner_limit, int* output) {
  for (int i = 0; i < outer_bound; i += 1) {
    if (i >= outer_limit) break;
    for (int j = 0; j < inner_bound; j += 1) {
      if (j >= inner_limit) break;
      int& alias = i; alias = 2; output[j] = alias;
    }
  }
}
void inner_unknown_call(int outer_limit, int inner_limit, int* output) {
  for (int i = 0; i < outer_bound; i += 1) {
    if (i >= outer_limit) break;
    for (int j = 0; j < inner_bound; j += 1) {
      if (j >= inner_limit) break;
      output[i + j] = unknown_int();
    }
  }
}
void nested_while(int outer_limit, int inner_limit, int* output) {
  for (int i = 0; i < outer_bound; i += 1) {
    if (i >= outer_limit) break;
    int j = 0;
    while (j < inner_limit) { output[i + j] = j; ++j; }
  }
}
void nested_static_branch(int outer_limit, int inner_limit, int* output) {
  for (int i = 0; i < outer_bound; i += 1) {
    if (i >= outer_limit) break;
    for (int j = 0; j < inner_bound; j += 1) {
      if (j >= inner_limit) break;
      if (false) i = 2; else output[i + j] = j;
    }
  }
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class LoopExitNestedWorkClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-loop-nested-work-")
        cls.source = Path(cls.temporary.name) / "loop_exit_nested_work.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "nested_leading",
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

    def outer_loop(self, name):
        functions = [node for node in self.functions if node.get("name") == name and
                     any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                         for child in node.get("inner", []))]
        self.assertEqual(len(functions), 1, name)
        loops = [node for node in _walk(functions[0]) if node.get("kind") == "ForStmt"]
        self.assertGreaterEqual(len(loops), 1, name)
        return loops[0]

    def check(self, name, **kwargs):
        return check_work_preservation(
            self.payload, self.outer_loop(name)["id"], 32, {}, **kwargs)

    def test_two_guarded_loop_patterns_require_explicit_nested_mode(self):
        for name in ("nested_leading", "nested_trailing"):
            with self.subTest(name=name):
                legacy = self.check(name)
                self.assertEqual(legacy["status"], "unknown", legacy)
                self.assertEqual(legacy["schema_version"], "loop-exit-work-preservation/v1")
                result = self.check(name, use_nested_loops=True)
                self.assertEqual(result["status"], "checked", result)
                self.assertEqual(result["schema_version"],
                                 "loop-exit-work-preservation-with-nested-loops/v1")
                self.assertTrue(result["nested_loop_checks"])
                self.assertTrue(all(item["status"] == "checked"
                                    for item in result["nested_loop_checks"]))
                self.assertEqual(result["work_preserves_protected"], "conditional")
                self.assertFalse(result["full_iteration_domain_established"])
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_inner_work_cannot_modify_outer_dependencies_or_alias_them(self):
        names = ("inner_writes_outer_induction", "inner_writes_outer_guard",
                 "inner_alias_writes_outer")
        for name in names:
            with self.subTest(name=name):
                result = self.check(name, use_nested_loops=True)
                self.assertEqual(result["status"], "unknown", result)
                self.assertNotEqual(result.get("work_preserves_protected"), "conditional")

    def test_nested_header_prefix_calls_and_while_stay_unknown(self):
        names = ("inner_header_side_effect", "inner_prefix_side_effect",
                 "inner_unknown_call", "nested_while")
        for name in names:
            with self.subTest(name=name):
                result = self.check(name, use_nested_loops=True)
                self.assertEqual(result["status"], "unknown", result)

    def test_static_branch_mode_composes_without_hiding_reachable_writes(self):
        nested_only = self.check("nested_static_branch", use_nested_loops=True)
        self.assertEqual(nested_only["status"], "unknown", nested_only)
        combined = self.check(
            "nested_static_branch", use_nested_loops=True, use_static_branches=True)
        self.assertEqual(combined["status"], "checked", combined)
        self.assertTrue(combined["static_branch_decisions"])
        self.assertTrue(combined["nested_loop_checks"])

    def test_nested_mode_requires_a_strict_bool(self):
        for mode in (1, None, "true"):
            with self.subTest(use_nested_loops=mode):
                result = self.check("nested_leading", use_nested_loops=mode)
                self.assertEqual(result["status"], "unknown", result)


if __name__ == "__main__":
    unittest.main()
