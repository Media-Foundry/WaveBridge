"""Real-Clang guarded output-store relation checks for a nested loop."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.guarded_stores import check


CLANG = shutil.which("clang++")
ABI32 = {
    "int": {"bits": 32, "signed": True},
    "unsigned int": {"bits": 32, "signed": False},
}

SOURCE = r"""
unsigned int external_leaf();
unsigned int getter() { return external_leaf(); }

constexpr int OUTER_COUNT = 2;
constexpr int INNER_COUNT = 4;
void direct_store(float *output, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) {
        output[outer * n + it * step] = 1.0f;
      } else {
        break;
      }
    }
  }
}

void mutually_exclusive_stores(float *output, int m, int n, float sum) {
  int local_idx = getter();
  const int step = 32;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) {
        if (sum == 0.0f) {
          output[outer * n + it * step] = 0.0f;
        } else {
          output[outer * n + it * step] = sum;
        }
      } else {
        break;
      }
    }
  }
}

void plus_one_index(float *output, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) {
        output[outer * n + it * step + 1] = 1.0f;
      } else {
        break;
      }
    }
  }
}

void wrong_base(float *output, float *other, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) {
        other[outer * n + it * step] = 1.0f;
      } else {
        break;
      }
    }
  }
}

void double_store(float *output, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) {
        output[outer * n + it * step] = 1.0f;
        output[outer * n + it * step] = 2.0f;
      } else {
        break;
      }
    }
  }
}

void missing_else_store(float *output, int m, int n, float sum) {
  int local_idx = getter();
  const int step = 32;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) {
        if (sum == 0.0f) {
          output[outer * n + it * step] = 0.0f;
        }
      } else {
        break;
      }
    }
  }
}

void rhs_side_effect(float *output, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) {
        output[outer * n + it * step] = (n++, 1.0f);
      } else {
        break;
      }
    }
  }
}

void unsupported_index(float *output, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) {
        output[(outer * n + it * step) + (local_idx - local_idx)] = 1.0f;
      } else {
        break;
      }
    }
  }
}

void overflowing_index(float *output, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) {
        output[outer * n + it * step + 2147483647 - 2147483647] = 1.0f;
      } else {
        break;
      }
    }
  }
}

void branch_condition_side_effect(float *output, int m, int n, float sum) {
  int local_idx = getter();
  const int step = 32;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) {
        if ((sum += 1.0f) == 0.0f) {
          output[outer * n + it * step] = 0.0f;
        } else {
          output[outer * n + it * step] = sum;
        }
      } else {
        break;
      }
    }
  }
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class GuardedStoresClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-guarded-stores-")
        cls.source = Path(cls.temporary.name) / "guarded_stores.cpp"
        cls.source.write_text(SOURCE, encoding="utf-8")
        report = collect(cls.source, CLANG, ["-std=c++17"], "direct_store",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.payload = {"ast": cls.root}
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")]
        leaves = [node for node in cls.functions if node.get("name") == "external_leaf" and
                  not any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                          for child in node.get("inner", []))]
        if len(leaves) != 1:
            raise AssertionError(leaves)
        cls.leaf = leaves[0]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def function(self, name):
        matches = [node for node in self.functions if node.get("name") == name and
                   any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                       for child in node.get("inner", []))]
        self.assertEqual(len(matches), 1, name)
        return matches[0]

    def selection(self, name):
        function = self.function(name)
        body = next(child for child in function.get("inner", [])
                    if isinstance(child, dict) and child.get("kind") == "CompoundStmt")
        outer = [node for node in body.get("inner", []) if node.get("kind") == "ForStmt"]
        self.assertEqual(len(outer), 1, name)
        inner = [node for node in _walk(outer[0])
                 if node.get("kind") == "ForStmt" and node is not outer[0]]
        self.assertEqual(len(inner), 1, name)
        source = [node for node in _walk(function)
                  if node.get("kind") == "VarDecl" and node.get("name") == "local_idx"]
        params = {node.get("name"): node for node in function.get("inner", [])
                  if isinstance(node, dict) and node.get("kind") == "ParmVarDecl"}
        self.assertEqual(len(source), 1, name)
        self.assertIn("output", params)
        self.assertIn("n", params)
        return source[0], outer[0], inner[0], params

    def contract(self):
        return {
            "schema_version": "getter-leaf-domain/v1",
            "declaration_id": self.leaf["id"],
            "arguments": [],
            "return_type": {"qualType": "unsigned int"},
            "lower": 0,
            "upper": 31,
        }

    def run_check(self, name, *, n_interval=(0, 128), output_id=None,
                  max_ast_nodes=None):
        source, outer, inner, params = self.selection(name)
        return check(
            self.payload, source["id"], outer["id"], inner["id"], self.contract(), ABI32,
            {}, {}, {}, {params["n"]["id"]: list(n_interval)},
            params["output"]["id"] if output_id is None else output_id,
            max_ast_nodes=max_ast_nodes, use_source_constants=True)

    def test_direct_and_mutually_exclusive_stores_are_bound(self):
        for name, expected_sites in (("direct_store", 1),
                                     ("mutually_exclusive_stores", 2)):
            with self.subTest(name=name):
                result = self.run_check(name)
                self.assertEqual(result["status"], "checked", result)
                self.assertTrue(result["guarded_store_relation_checked"])
                self.assertEqual(len(result["store_sites"]), expected_sites)
                self.assertFalse(result["full_output_coverage_established"])
                self.assertFalse(result["output_pointer_history_checked"])
                self.assertFalse(result["lane_family_established"])
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_wrong_index_or_base_and_two_stores_do_not_check(self):
        expected = {
            "plus_one_index": "store_index_not_relative_row_and_iteration",
            "wrong_base": "store_base_not_selected_output",
            "double_store": "work_paths_do_not_all_store_exactly_once",
        }
        for name, reason in expected.items():
            with self.subTest(name=name):
                result = self.run_check(name)
                self.assertEqual(result["status"], "rejected", result)
                self.assertEqual(result["reason"], reason)
                self.assertFalse(result["guarded_store_relation_checked"])

    def test_every_dynamic_path_must_store_once_and_rhs_must_be_effect_free(self):
        expected = {
            "missing_else_store": "work_paths_do_not_all_store_exactly_once",
            # The fresh nested-work check catches this protected-bound write
            # before the store-specific pass; that is the intended layering.
            "rhs_side_effect": "nested_bounds_not_checked",
            "branch_condition_side_effect": "store_expression_effect_not_checked",
        }
        for name, reason in expected.items():
            with self.subTest(name=name):
                result = self.run_check(name)
                self.assertNotEqual(result["status"], "checked", result)
                self.assertEqual(result["reason"], reason)
                self.assertFalse(result["guarded_store_relation_checked"])

    def test_header_capacity_and_expression_subset_fail_closed(self):
        truncated = self.run_check("direct_store", n_interval=(0, 129))
        self.assertEqual(truncated["status"], "rejected", truncated)
        self.assertEqual(truncated["reason"], "header_may_truncate_declared_column_domain")
        self.assertFalse(truncated["guarded_store_relation_checked"])

        complex_index = self.run_check("unsupported_index")
        self.assertEqual(complex_index["status"], "unknown", complex_index)
        self.assertEqual(complex_index["reason"], "unsupported_store_index_read")
        self.assertFalse(complex_index["guarded_store_relation_checked"])

        overflow = self.run_check("overflowing_index")
        self.assertEqual(overflow["status"], "unknown", overflow)
        self.assertEqual(overflow["reason"], "store_index_arithmetic_may_overflow")
        self.assertFalse(overflow["guarded_store_relation_checked"])

    def test_output_identity_and_budget_are_bound(self):
        _, _, _, params = self.selection("wrong_base")
        wrong = self.run_check("direct_store", output_id=params["other"]["id"])
        self.assertNotEqual(wrong["status"], "checked", wrong)
        for budget in (1, True):
            with self.subTest(max_ast_nodes=budget):
                limited = self.run_check("direct_store", max_ast_nodes=budget)
                self.assertEqual(limited["status"], "unknown", limited)
                self.assertFalse(limited["guarded_store_relation_checked"])


if __name__ == "__main__":
    unittest.main()
