"""Real-Clang nested iteration bounds using a fresh initializer interval."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.initializer_domain import check_nested_iteration_bounds


CLANG = shutil.which("clang++")
ABI32 = {
    "int": {"bits": 32, "signed": True},
    "unsigned int": {"bits": 32, "signed": False},
}

SOURCE = r"""
unsigned int external_leaf();
unsigned int getter() { return external_leaf(); }
void opaque();
constexpr int OUTER_COUNT = 2;
constexpr int INNER_COUNT = 4;

int bounded(int *output, int m, int n) {
  int value = getter();
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int idx = value + it;
      if (idx < n) { output[idx] = value; } else { break; }
    }
  }
  return value;
}
int history_modified(int *output, int m, int n) {
  int value = getter();
  value = 7;
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int idx = value + it;
      if (idx < n) { output[idx] = value; } else { break; }
    }
  }
  return value;
}
int unrelated(int *output, int m, int n) {
  int value = getter();
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int idx = value + it;
      if (idx < n) { output[idx] = value; } else { break; }
    }
  }
  for (int other = 0; other < INNER_COUNT; ++other) {
    if (other >= n) break;
    output[other] = value;
  }
  return value;
}
int opaque_history(int *output, int m, int n) {
  int value = getter();
  opaque();
  for (int outer = 0; outer < OUTER_COUNT; ++outer) {
    if (outer >= m) break;
    for (int it = 0; it < INNER_COUNT; ++it) {
      int idx = value + it;
      if (idx < n) { output[idx] = value; } else { break; }
    }
  }
  return value;
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class InitializerIterationBoundsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-initializer-iteration-bounds-")
        cls.source = Path(cls.temporary.name) / "initializer_iteration_bounds.cpp"
        cls.source.write_text(SOURCE, encoding="utf-8")
        report = collect(cls.source, CLANG, ["-std=c++17"], "bounded",
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
        direct = [node for node in body.get("inner", []) if node.get("kind") == "ForStmt"]
        self.assertGreaterEqual(len(direct), 1, name)
        outer = direct[0]
        nested = [node for node in _walk(outer)
                  if node.get("kind") == "ForStmt" and node is not outer]
        self.assertEqual(len(nested), 1, name)
        value = [node for node in _walk(function)
                 if node.get("kind") == "VarDecl" and node.get("name") == "value"]
        params = {node.get("name"): node for node in function.get("inner", [])
                  if isinstance(node, dict) and node.get("kind") == "ParmVarDecl"}
        self.assertEqual(len(value), 1, name)
        self.assertTrue({"m", "n"}.issubset(params))
        return value[0], outer, nested[0], direct, params

    def contract(self, upper=3):
        return {
            "schema_version": "getter-leaf-domain/v1",
            "declaration_id": self.leaf["id"],
            "arguments": [],
            "return_type": {"qualType": "unsigned int"},
            "lower": 0,
            "upper": upper,
        }

    def check(self, name="bounded", *, inner_id=None, contract=None,
              integer_types=None, intervals=None, history_protocols=None,
              work_protocols=None, inner_protocols=None):
        value, outer, inner, _, params = self.selection(name)
        domains = {params["n"]["id"]: [4, 8]} if intervals is None else intervals
        return check_nested_iteration_bounds(
            self.payload, value["id"], outer["id"],
            inner["id"] if inner_id is None else inner_id,
            self.contract() if contract is None else contract,
            ABI32 if integer_types is None else integer_types,
            {} if history_protocols is None else history_protocols,
            {} if work_protocols is None else work_protocols,
            {} if inner_protocols is None else inner_protocols,
            domains, use_source_constants=True)

    def test_source_initializer_interval_drives_nested_work_count_bounds(self):
        result = self.check()
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["iteration_bounds_established"])
        self.assertTrue(result["value_preserved_to_nested_entry"])
        self.assertEqual(result["source_interval"], {"lower": 0, "upper": 3})
        # idx=value+it, it=0..3 and idx<n: value=3,n=4 permits one
        # work iteration, while value=0,n>=4 permits all four.
        self.assertEqual(result["work_count_bounds"], [1, 4])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_external_domains_must_cover_exact_non_source_reads(self):
        value, _, _, _, params = self.selection("bounded")
        variants = ({},
                    {params["n"]["id"]: [4, 8], params["m"]["id"]: [0, 2]},
                    {params["n"]["id"]: [4, 8], value["id"]: [0, 3]})
        for domains in variants:
            with self.subTest(domains=domains):
                result = self.check(intervals=domains)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["iteration_bounds_established"])

    def test_wrong_inner_history_modification_and_unsigned_int_abi_fail_closed(self):
        _, _, _, direct, _ = self.selection("unrelated")
        self.assertEqual(len(direct), 2)
        wrong = self.check("unrelated", inner_id=direct[1]["id"])
        self.assertEqual(wrong["status"], "unknown", wrong)
        changed = self.check("history_modified")
        self.assertEqual(changed["status"], "unknown", changed)
        unsigned_abi = {
            "int": {"bits": 32, "signed": False},
            "unsigned int": {"bits": 32, "signed": False},
        }
        invalid = self.check(integer_types=unsigned_abi)
        self.assertEqual(invalid["status"], "unknown", invalid)

    def test_prefix_arithmetic_overflow_is_unknown(self):
        abi8 = {
            "int": {"bits": 8, "signed": True},
            "unsigned int": {"bits": 8, "signed": False},
        }
        _, _, _, _, params = self.selection("bounded")
        result = self.check(
            contract=self.contract(upper=127), integer_types=abi8,
            intervals={params["n"]["id"]: [127, 127]})
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["reason"], "nested_iteration_bounds_not_checked")
        self.assertEqual(result["iteration_check"]["reason"],
                         "signed_arithmetic_may_overflow")
        self.assertFalse(result["iteration_bounds_established"])

    def test_old_success_report_cannot_replace_fresh_history_effect_protocol(self):
        call = next(node for node in _walk(self.function("opaque_history"))
                    if node.get("kind") == "CallExpr" and
                    node.get("type", {}).get("qualType") == "void")
        forged = {call["id"]: {
            "schema_version": "initializer-to-nested-entry/v1",
            "status": "checked",
            "value_preserved_to_nested_entry": True,
        }}
        result = self.check("opaque_history", history_protocols=forged)
        self.assertEqual(result["status"], "unknown", result)
        self.assertFalse(result["iteration_bounds_established"])


if __name__ == "__main__":
    unittest.main()
