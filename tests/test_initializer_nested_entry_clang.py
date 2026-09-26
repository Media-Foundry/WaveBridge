"""Real-Clang initializer history through an outer loop to nested-loop entry."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.initializer_domain import check_nested_entry


CLANG = shutil.which("clang++")
ABI = {
    "int": {"bits": 32, "signed": True},
    "unsigned int": {"bits": 32, "signed": False},
}

SOURCE = r"""
unsigned int external_leaf();
unsigned int getter() { return external_leaf(); }
void opaque();

int preserved(int *output, int outer_bound, int inner_bound) {
  int value = getter();
  for (int outer = 0; outer < outer_bound; ++outer) {
    if (outer >= outer_bound) break;
    for (int inner = 0; inner < inner_bound; ++inner) {
      if (inner >= inner_bound) break;
      output[outer * inner_bound + inner] = value;
    }
  }
  return value;
}
int write_before_inner(int *output, int outer_bound, int inner_bound) {
  int value = getter();
  for (int outer = 0; outer < outer_bound; ++outer) {
    if (outer >= outer_bound) break;
    value = 7;
    for (int inner = 0; inner < inner_bound; ++inner) {
      if (inner >= inner_bound) break;
      output[inner] = value;
    }
  }
  return value;
}
int write_after_inner(int *output, int outer_bound, int inner_bound) {
  int value = getter();
  for (int outer = 0; outer < outer_bound; ++outer) {
    if (outer >= outer_bound) break;
    for (int inner = 0; inner < inner_bound; ++inner) {
      if (inner >= inner_bound) break;
      output[inner] = value;
    }
    value = 7;
  }
  return value;
}
int alias_before_inner(int *output, int outer_bound, int inner_bound) {
  int value = getter();
  for (int outer = 0; outer < outer_bound; ++outer) {
    if (outer >= outer_bound) break;
    int& alias = value;
    alias = 7;
    for (int inner = 0; inner < inner_bound; ++inner) {
      if (inner >= inner_bound) break;
      output[inner] = value;
    }
  }
  return value;
}
int outer_header_write(int *output, int outer_bound, int inner_bound) {
  int value = getter();
  for (int outer = (value = 0); outer < outer_bound; ++outer) {
    if (outer >= outer_bound) break;
    for (int inner = 0; inner < inner_bound; ++inner) {
      if (inner >= inner_bound) break;
      output[inner] = value;
    }
  }
  return value;
}
int source_history_write(int *output, int outer_bound, int inner_bound) {
  int value = getter();
  value = 3;
  for (int outer = 0; outer < outer_bound; ++outer) {
    if (outer >= outer_bound) break;
    for (int inner = 0; inner < inner_bound; ++inner) {
      if (inner >= inner_bound) break;
      output[inner] = value;
    }
  }
  return value;
}
int unrelated_loop(int *output, int outer_bound, int inner_bound) {
  int value = getter();
  for (int outer = 0; outer < outer_bound; ++outer) {
    if (outer >= outer_bound) break;
    for (int inner = 0; inner < inner_bound; ++inner) {
      if (inner >= inner_bound) break;
      output[inner] = value;
    }
  }
  for (int other = 0; other < inner_bound; ++other) {
    if (other >= inner_bound) break;
    output[other] = value;
  }
  return value;
}
int opaque_history(int *output, int outer_bound, int inner_bound) {
  int value = getter();
  opaque();
  for (int outer = 0; outer < outer_bound; ++outer) {
    if (outer >= outer_bound) break;
    for (int inner = 0; inner < inner_bound; ++inner) {
      if (inner >= inner_bound) break;
      output[inner] = value;
    }
  }
  return value;
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class InitializerNestedEntryClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-initializer-nested-entry-")
        cls.source = Path(cls.temporary.name) / "initializer_nested_entry.cpp"
        cls.source.write_text(SOURCE, encoding="utf-8")
        report = collect(cls.source, CLANG, ["-std=c++17"], "preserved",
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
        bodies = [child for child in function.get("inner", [])
                  if isinstance(child, dict) and child.get("kind") == "CompoundStmt"]
        self.assertEqual(len(bodies), 1, name)
        direct_loops = [node for node in bodies[0].get("inner", [])
                        if node.get("kind") == "ForStmt"]
        self.assertGreaterEqual(len(direct_loops), 1, name)
        outer = direct_loops[0]
        nested = [node for node in _walk(outer)
                  if node.get("kind") == "ForStmt" and node is not outer]
        self.assertEqual(len(nested), 1, name)
        values = [node for node in _walk(function)
                  if node.get("kind") == "VarDecl" and node.get("name") == "value"]
        self.assertEqual(len(values), 1, name)
        return values[0], outer, nested[0], direct_loops

    def contract(self):
        return {
            "schema_version": "getter-leaf-domain/v1",
            "declaration_id": self.leaf["id"],
            "arguments": [],
            "return_type": {"qualType": "unsigned int"},
            "lower": 0,
            "upper": 31,
        }

    def check(self, name, *, inner_id=None, history_protocols=None,
              work_protocols=None, integer_types=None):
        value, outer, inner, _ = self.selection(name)
        return check_nested_entry(
            self.payload, value["id"], outer["id"], inner["id"] if inner_id is None else inner_id,
            self.contract(), ABI if integer_types is None else integer_types,
            {} if history_protocols is None else history_protocols,
            {} if work_protocols is None else work_protocols)

    def test_value_is_conditionally_preserved_to_each_reached_nested_entry(self):
        result = self.check("preserved")
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["value_preserved_to_nested_entry"])
        self.assertEqual(result["result_interval"], {"lower": 0, "upper": 31})
        self.assertFalse(result["nested_loop_reachability_established"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_outer_work_before_after_and_alias_writes_are_rejected(self):
        for name in ("write_before_inner", "write_after_inner", "alias_before_inner"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["value_preserved_to_nested_entry"])

    def test_outer_header_and_preloop_history_writes_are_rejected(self):
        for name in ("outer_header_write", "source_history_write"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["value_preserved_to_nested_entry"])

    def test_inner_identity_must_be_nested_under_the_selected_outer_loop(self):
        _, _, inner, direct = self.selection("unrelated_loop")
        self.assertEqual(len(direct), 2)
        result = self.check("unrelated_loop", inner_id=direct[1]["id"])
        self.assertEqual(result["status"], "unknown", result)
        self.assertFalse(result["value_preserved_to_nested_entry"])
        missing = self.check("preserved", inner_id="missing-inner")
        self.assertEqual(missing["status"], "unknown", missing)

    def test_old_success_report_cannot_replace_an_effect_protocol(self):
        call = next(node for node in _walk(self.function("opaque_history"))
                    if node.get("kind") == "CallExpr" and
                    node.get("type", {}).get("qualType") == "void")
        forged = {call["id"]: {
            "schema_version": "loop-exit-work-preservation/v1",
            "status": "checked",
            "work_preserves_protected": "conditional",
        }}
        result = self.check("opaque_history", history_protocols=forged)
        self.assertEqual(result["status"], "unknown", result)
        self.assertFalse(result["value_preserved_to_nested_entry"])

        unsigned_abi = {
            "int": {"bits": 32, "signed": False},
            "unsigned int": {"bits": 32, "signed": False},
        }
        invalid_abi = self.check("preserved", integer_types=unsigned_abi)
        self.assertEqual(invalid_abi["status"], "unknown", invalid_abi)


if __name__ == "__main__":
    unittest.main()
