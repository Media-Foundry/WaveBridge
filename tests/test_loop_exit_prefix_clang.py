"""Real-Clang checks for restricted prefix values feeding loop exit guards."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.loop_exit_guards import check_prefix_values


CLANG = shutil.which("clang++")

SOURCE = r"""
int external_value();

void leading_empty(int n, int* output) {
  for (int i = 0; i < n; ++i) {
    if (i >= n) break;
    output[i] = i;
  }
}
void trailing_expression(int n, int base, int stride, int* output) {
  for (int i = 0; i < n; ++i) {
    int idx = base + i * stride;
    const int adjusted = +(idx + 1);
    if (adjusted < n) { output[i] = adjusted; } else break;
  }
}
void ordered_declaration(int n, int base, int* output) {
  for (int i = 0; i < n; ++i) {
    int first = base + i;
    int second = first * 2;
    if (second != n) { output[i] = second; } else break;
  }
}
void multiple_variables_one_statement(int n, int base, int* output) {
  for (int i = 0; i < n; ++i) {
    int first = base + i, second = first * 2;
    if (second != n) { output[i] = second; } else break;
  }
}
void assignment_prefix(int n, int base, int* output) {
  for (int i = 0; i < n; ++i) {
    base = base + i;
    if (base < n) { output[i] = base; } else break;
  }
}
void increment_prefix(int n, int base, int* output) {
  for (int i = 0; i < n; ++i) {
    ++base;
    if (base < n) { output[i] = base; } else break;
  }
}
void reference_prefix(int n, int base, int* output) {
  for (int i = 0; i < n; ++i) {
    int& alias = base;
    if (alias < n) { output[i] = alias; } else break;
  }
}
void static_prefix(int n, int base, int* output) {
  for (int i = 0; i < n; ++i) {
    static int saved = base;
    if (saved < n) { output[i] = saved; } else break;
  }
}
void tls_prefix(int n, int base, int* output) {
  for (int i = 0; i < n; ++i) {
    thread_local int saved = base;
    if (saved < n) { output[i] = saved; } else break;
  }
}
void volatile_prefix(int n, int base, int* output) {
  for (int i = 0; i < n; ++i) {
    volatile int saved = base;
    if (saved < n) { output[i] = saved; } else break;
  }
}
void call_prefix(int n, int* output) {
  for (int i = 0; i < n; ++i) {
    int saved = external_value();
    if (saved < n) { output[i] = saved; } else break;
  }
}
void self_read_prefix(int n, int* output) {
  for (int i = 0; i < n; ++i) {
    int saved = saved + 1;
    if (saved < n) { output[i] = saved; } else break;
  }
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class LoopExitPrefixClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-loop-exit-prefix-")
        cls.source = Path(cls.temporary.name) / "loop_exit_prefix.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "leading_empty",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def loop(self, name):
        functions = [node for node in self.functions if node.get("name") == name and
                     any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                         for child in node.get("inner", []))]
        self.assertEqual(len(functions), 1, name)
        loops = [node for node in _walk(functions[0]) if node.get("kind") == "ForStmt"]
        self.assertEqual(len(loops), 1, name)
        return loops[0]

    def inspect(self, name, **kwargs):
        return check_prefix_values(self.root, self.loop(name)["id"], **kwargs)

    def test_empty_leading_prefix_preserves_direct_guard_terms(self):
        result = self.inspect("leading_empty")
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["scope"], "exit_guard_values_after_restricted_prefix")
        self.assertEqual(result["prefix_values"], [])
        expression = result["guard_value_expression"]
        self.assertEqual(expression["opcode"], ">=")
        self.assertEqual([operand["kind"] for operand in expression["operands"]],
                         ["read", "read"])
        self.assertEqual(result["prefix_preserves_existing_objects"], "conditional")
        self.assertFalse(result["full_iteration_domain_established"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_ordered_prefix_initializers_are_substituted_into_guard(self):
        result = self.inspect("trailing_expression")
        self.assertEqual(result["status"], "checked", result)
        declarations = result["prefix_values"]
        self.assertEqual(len(declarations), 2)
        self.assertTrue(all(item["initializer_check"]["status"] == "checked"
                            for item in declarations))
        idx, adjusted = declarations
        self.assertEqual(idx["expression"]["kind"], "binary")
        self.assertEqual(idx["expression"]["opcode"], "+")
        self.assertEqual(adjusted["expression"]["kind"], "unary")
        guard = result["guard_value_expression"]
        self.assertEqual(guard["opcode"], "<")
        self.assertEqual(guard["operands"][0], {
            "kind": "prefix_value", "declaration_id": adjusted["declaration_id"],
            "type": "int",
        })
        self.assertEqual(guard["operands"][1]["kind"], "read")

        ordered = self.inspect("ordered_declaration")
        self.assertEqual(ordered["status"], "checked", ordered)
        self.assertEqual(len(ordered["prefix_values"]), 2)
        first, second = ordered["prefix_values"]
        self.assertEqual(second["expression"]["opcode"], "*")
        self.assertEqual(second["expression"]["operands"][0], {
            "kind": "prefix_value", "declaration_id": first["declaration_id"],
            "type": "int",
        })

    def test_writes_aliases_storage_and_calls_stay_unknown(self):
        names = ("assignment_prefix", "increment_prefix", "reference_prefix",
                 "static_prefix", "tls_prefix", "volatile_prefix", "call_prefix",
                 "self_read_prefix", "multiple_variables_one_statement")
        for name in names:
            with self.subTest(name=name):
                result = self.inspect(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_missing_identity_wrong_root_and_budget_fail_closed(self):
        self.assertEqual(check_prefix_values(self.root, "missing-loop")["status"], "unknown")
        loop_id = self.loop("leading_empty")["id"]
        self.assertEqual(check_prefix_values({"kind": "ForStmt", "inner": []}, loop_id)["status"],
                         "unknown")
        for budget in (1, True):
            with self.subTest(max_ast_nodes=budget):
                result = check_prefix_values(self.root, loop_id, max_ast_nodes=budget)
                self.assertEqual(result["status"], "unknown", result)


if __name__ == "__main__":
    unittest.main()
