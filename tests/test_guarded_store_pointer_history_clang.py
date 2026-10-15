"""Pending Real-Clang entry-pointer history for guarded relative output stores."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.guarded_stores import (
    _check_entry_pointer_history, check, check_entry_pointer)


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

void good(float *output, int row, int stride, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  int first_batch = row;
  int idx_offset = first_batch * stride + local_idx;
  output += idx_offset;
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

void offset_plus_one(float *output, int row, int stride, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  int first_batch = row;
  int idx_offset = first_batch * stride + local_idx + 1;
  output += idx_offset;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) { output[outer * n + it * step] = 1.0f; } else { break; }
    }
  }
}

void double_update(float *output, int row, int stride, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  int first_batch = row;
  int idx_offset = first_batch * stride + local_idx;
  output += idx_offset;
  output += 1;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) { output[outer * n + it * step] = 1.0f; } else { break; }
    }
  }
}

void alias_update(float *output, int row, int stride, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  int first_batch = row;
  int idx_offset = first_batch * stride + local_idx;
  using Ref = float *&;
  Ref alias = output;
  alias += idx_offset;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) { output[outer * n + it * step] = 1.0f; } else { break; }
    }
  }
}

void conditional_update(float *output, int row, int stride, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  int first_batch = row;
  int idx_offset = first_batch * stride + local_idx;
  if (row >= 0) output += idx_offset;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) { output[outer * n + it * step] = 1.0f; } else { break; }
    }
  }
}

void update_after_loop(float *output, int row, int stride, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  int first_batch = row;
  int idx_offset = first_batch * stride + local_idx;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) { output[outer * n + it * step] = 1.0f; } else { break; }
    }
  }
  output += idx_offset;
}

void changed_offset(float *output, int row, int stride, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  int first_batch = row;
  int idx_offset = first_batch * stride + local_idx;
  idx_offset += 1;
  output += idx_offset;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) { output[outer * n + it * step] = 1.0f; } else { break; }
    }
  }
}

void output_address_escape(float *output, int row, int stride, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  int first_batch = row;
  int idx_offset = first_batch * stride + local_idx;
  float **escaped = &output;
  (void)escaped;
  output += idx_offset;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) { output[outer * n + it * step] = 1.0f; } else { break; }
    }
  }
}

void offset_reference_escape(float *output, int row, int stride, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  int first_batch = row;
  int idx_offset = first_batch * stride + local_idx;
  int &escaped = idx_offset;
  (void)escaped;
  output += idx_offset;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) { output[outer * n + it * step] = 1.0f; } else { break; }
    }
  }
}

void static_row_snapshot(float *output, int row, int stride, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  static int first_batch = row;
  int idx_offset = first_batch * stride + local_idx;
  output += idx_offset;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) { output[outer * n + it * step] = 1.0f; } else { break; }
    }
  }
}

void goto_skips_update(float *output, int row, int stride, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  int first_batch = row;
  int idx_offset = first_batch * stride + local_idx;
  goto after_update;
  output += idx_offset;
after_update:
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) { output[outer * n + it * step] = 1.0f; } else { break; }
    }
  }
}

void lambda_captures_output(float *output, int row, int stride, int m, int n) {
  int local_idx = getter();
  const int step = 32;
  int first_batch = row;
  int idx_offset = first_batch * stride + local_idx;
  auto hidden = [&output]() { output += 1; };
  (void)hidden;
  output += idx_offset;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) { output[outer * n + it * step] = 1.0f; } else { break; }
    }
  }
}

void array_filler_escape(float *output, int row, int stride, int m, int n) {
  float **escaped[2] = {&output};
  (void)escaped;
  int local_idx = getter();
  const int step = 32;
  int first_batch = row;
  int idx_offset = first_batch * stride + local_idx;
  output += idx_offset;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int col = local_idx + it * step;
      if (col < n) { output[outer * n + it * step] = 1.0f; } else { break; }
    }
  }
}

#define READ_CASE(NAME, BEFORE, AFTER) \
void NAME(const float *input, int row, int stride, int n) { \
  int local_idx = getter(); \
  int first_batch = row; \
  int idx_offset = first_batch * stride + local_idx; \
  BEFORE \
  input += idx_offset; \
  AFTER \
  for (int outer = 0; outer < OUTER_COUNT; ++outer) { \
    for (int it = 0; it < INNER_COUNT; ++it) { \
      float loaded = input[outer * n + it * 32]; \
      (void)loaded; \
    } \
  } \
}
READ_CASE(readonly_good, , )
READ_CASE(readonly_write, , ++n;)
READ_CASE(readonly_alias, int &alias = n;, (void)alias;)
READ_CASE(readonly_pointer_alias, const float *&alias = input;, (void)alias;)
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class GuardedStorePointerHistoryClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-guarded-pointer-history-")
        cls.source = Path(cls.temporary.name) / "guarded_pointer_history.cpp"
        cls.source.write_text(SOURCE, encoding="utf-8")
        report = collect(cls.source, CLANG, ["-std=c++17"], "good",
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
        if not outer:
            # Negative control-flow fixtures may wrap the selected loop in a
            # LabelStmt; retain its real ID so the checker, not the selector,
            # rejects the unsupported path.
            loops = [node for node in _walk(body) if node.get("kind") == "ForStmt"]
            outer = [node for node in loops if any(
                child.get("kind") == "ForStmt" and child is not node for child in _walk(node))]
        self.assertEqual(len(outer), 1, name)
        inner = [node for node in _walk(outer[0])
                 if node.get("kind") == "ForStmt" and node is not outer[0]]
        self.assertEqual(len(inner), 1, name)
        variables = {node.get("name"): node for node in _walk(function)
                     if node.get("kind") == "VarDecl" and node.get("name")}
        params = {node.get("name"): node for node in function.get("inner", [])
                  if isinstance(node, dict) and node.get("kind") == "ParmVarDecl"}
        self.assertTrue({"local_idx", "first_batch", "idx_offset"}.issubset(variables))
        self.assertTrue({"output", "row", "stride", "n"}.issubset(params))
        return variables, params, outer[0], inner[0]

    def contract(self):
        return {
            "schema_version": "getter-leaf-domain/v1",
            "declaration_id": self.leaf["id"],
            "arguments": [],
            "return_type": {"qualType": "unsigned int"},
            "lower": 0,
            "upper": 31,
        }

    def run_check(self, name="good", *, binding_updates=None, integer_types=None,
                  max_ast_nodes=None, entry=True):
        variables, params, outer, inner = self.selection(name)
        binding = {
            "offset_declaration_id": variables["idx_offset"]["id"],
            "row_declaration_id": variables["first_batch"]["id"],
            "stride_parameter_id": params["stride"]["id"],
            "row_interval": [0, 2],
            "stride_interval": [0, 128],
        }
        if binding_updates:
            binding.update(binding_updates)
        arguments = (
            self.payload, variables["local_idx"]["id"], outer["id"], inner["id"],
            self.contract(), ABI32 if integer_types is None else integer_types,
            {}, {}, {}, {params["n"]["id"]: [0, 128]}, params["output"]["id"])
        if not entry:
            return check(*arguments, max_ast_nodes=max_ast_nodes, use_source_constants=True)
        return check_entry_pointer(
            *arguments, pointer_binding=binding, max_ast_nodes=max_ast_nodes,
            use_source_constants=True)

    def run_core(self, name="readonly_good", *, pointer_type="const float *",
                 readonly=True, max_ast_nodes=None):
        function = self.function(name)
        body = next(child for child in function.get("inner", []) if child.get("kind") == "CompoundStmt")
        variables = {node.get("name"): node for node in _walk(function)
                     if node.get("kind") == "VarDecl" and node.get("name")}
        params = {node.get("name"): node for node in function.get("inner", [])
                  if node.get("kind") == "ParmVarDecl"}
        outer = next(node for node in body.get("inner", []) if node.get("kind") == "ForStmt")
        inner = next(node for node in _walk(outer)
                     if node.get("kind") == "ForStmt" and node is not outer)
        source_statement = next(i for i, node in enumerate(body["inner"])
                                if node.get("kind") == "DeclStmt" and
                                any(child is variables["local_idx"] for child in node.get("inner", [])))
        outer_statement = body["inner"].index(outer)
        selection = {"function_id": function["id"], "declaration_id": variables["local_idx"]["id"],
                     "target_statement_id": outer["id"], "declaration_statement_index": source_statement,
                     "target_statement_index": outer_statement}
        binding = {"offset_declaration_id": variables["idx_offset"]["id"],
                   "row_declaration_id": variables["first_batch"]["id"],
                   "stride_parameter_id": params["stride"]["id"],
                   "row_interval": [0, 2], "stride_interval": [0, 128]}
        relation = {"row_id": variables["outer"]["id"], "count_id": params["n"]["id"],
                    "iteration_id": variables["it"]["id"], "stride": 32}
        return _check_entry_pointer_history(
            self.payload, variables["local_idx"]["id"], outer["id"], {"lower": 0, "upper": 31},
            selection, ABI32, params["input"]["id"], binding, relation,
            pointer_type=pointer_type,
            readonly_parameter_ids=(params["n"]["id"],) if readonly else (),
            max_ast_nodes=max_ast_nodes)

    def test_exact_entry_relative_pointer_history_is_checked(self):
        result = self.run_check()
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["output_pointer_history_checked"])
        self.assertFalse(result["full_output_coverage_established"])
        self.assertFalse(result["lane_family_established"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        self.assertEqual(result["entry_relative_offset_relation"]["stride_parameter_id"],
                         self.selection("good")[1]["stride"]["id"])
        self.assertNotEqual(result["entry_relative_offset_relation"].get("count_parameter_id"),
                            result["entry_relative_offset_relation"]["stride_parameter_id"])

        relative_only = self.run_check(entry=False)
        self.assertEqual(relative_only["status"], "checked", relative_only)
        self.assertFalse(relative_only["output_pointer_history_checked"])

    def test_offset_expression_and_update_count_are_exact(self):
        for name in ("offset_plus_one", "double_update"):
            with self.subTest(name=name):
                result = self.run_check(name)
                self.assertNotEqual(result["status"], "checked", result)
                self.assertFalse(result["output_pointer_history_checked"])

    def test_alias_conditional_late_and_modified_updates_fail_closed(self):
        for name in ("alias_update", "conditional_update", "update_after_loop",
                     "changed_offset", "output_address_escape",
                     "offset_reference_escape", "static_row_snapshot",
                     "goto_skips_update", "lambda_captures_output"):
            with self.subTest(name=name):
                result = self.run_check(name)
                self.assertNotEqual(result["status"], "checked", result)
                self.assertFalse(result["output_pointer_history_checked"])

        filler = self.run_check("array_filler_escape")
        self.assertEqual(filler["status"], "unknown", filler)
        self.assertEqual(filler["reason"], "pointer_or_offset_storage_write_or_escape")
        self.assertEqual(filler["store_check"]["status"], "checked")
        self.assertFalse(filler["output_pointer_history_checked"])

    def test_binding_roles_and_domains_are_exact(self):
        variables, params, _, _ = self.selection("good")
        variants = (
            {"offset_declaration_id": variables["first_batch"]["id"]},
            {"row_declaration_id": variables["idx_offset"]["id"]},
            {"stride_parameter_id": params["n"]["id"]},
            {"row_interval": None},
            {"stride_interval": [0]},
            {"extra": True},
        )
        for updates in variants:
            with self.subTest(updates=updates):
                result = self.run_check(binding_updates=updates)
                self.assertNotEqual(result["status"], "checked", result)
                self.assertFalse(result["output_pointer_history_checked"])

    def test_integer_abi_overflow_and_budget_are_unknown(self):
        overflow = self.run_check(binding_updates={
            "row_interval": [2147483647, 2147483647],
            "stride_interval": [2, 2],
        })
        self.assertEqual(overflow["status"], "unknown", overflow)
        self.assertFalse(overflow["output_pointer_history_checked"])

        unsigned = {
            "int": {"bits": 32, "signed": False},
            "unsigned int": {"bits": 32, "signed": False},
        }
        invalid_abi = self.run_check(integer_types=unsigned)
        self.assertEqual(invalid_abi["status"], "unknown", invalid_abi)
        for budget in (1, True):
            with self.subTest(max_ast_nodes=budget):
                limited = self.run_check(max_ast_nodes=budget)
                self.assertEqual(limited["status"], "unknown", limited)
                self.assertFalse(limited["output_pointer_history_checked"])

    def test_neutral_core_supports_const_input_and_closes_readonly_parameter_uses(self):
        result = self.run_core()
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["pointer_history_checked"])
        self.assertEqual(result["pointer_type"], "const float *")
        self.assertTrue(any(item["classification"] == "readonly_parameter_value_read"
                            for item in result["reference_classifications"]))
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_neutral_core_rejects_readonly_writes_aliases_and_pointer_alias(self):
        for name in ("readonly_write", "readonly_alias", "readonly_pointer_alias"):
            with self.subTest(name=name):
                result = self.run_core(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["pointer_history_checked"])
        self.assertEqual(self.run_core(pointer_type="float *")["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
