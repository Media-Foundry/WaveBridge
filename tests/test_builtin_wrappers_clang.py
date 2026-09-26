"""Real-Clang checks for restricted single-return builtin wrapper chains."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect
from wavebridge.verification.builtin_calls import (
    check_wrapper_no_memory_write,
    inspect_structure,
)


PLUGIN = os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")

SOURCE = r"""
int global_counter;
float external_float();

float renamed_free_leaf() { return __builtin_huge_valf(); }
float renamed_free_outer() { return renamed_free_leaf(); }

struct RenamedContainer {
  static float renamed_static_middle() noexcept { return renamed_free_outer(); }
  static float renamed_static_outer() noexcept { return renamed_static_middle(); }
  float instance_wrapper() { return renamed_free_leaf(); }
  virtual float virtual_wrapper() { return renamed_free_leaf(); }
};

float nan_leaf() { return __builtin_nanf(""); }
float writes_before_leaf() { global_counter += 1; return __builtin_huge_valf(); }
float comma_return() { return (external_float(), __builtin_huge_valf()); }
float recursive_wrapper() { return recursive_wrapper(); }
float external_wrapper() { return external_float(); }
float parameter_wrapper(int value) { return value ? __builtin_huge_valf() : 0.0f; }
"""


@unittest.skipUnless(PLUGIN, "requires compiler-matched native observation plugin")
class BuiltinWrappersClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-builtin-wrappers-")
        cls.source = Path(cls.temporary.name) / "builtin_wrappers.cpp"
        cls.source.write_text(SOURCE)
        cls.report = collect(cls.source, COMPILER, Path(PLUGIN), ["-std=c++17"])
        if cls.report["status"] != "collected":
            raise AssertionError(cls.report)
        cls.payload = cls.report["payload"]
        cls.root = cls.payload["ast"]
        cls.definitions = [node for node in _walk(cls.root)
                           if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"} and
                           any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                               for child in node.get("inner", []))]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def declaration(self, name):
        matches = [node for node in self.definitions if node.get("name") == name]
        self.assertEqual(len(matches), 1, (name, matches))
        return matches[0]

    def builtin_record(self, name):
        matches = [record for record in self.payload["builtin_calls"]
                   if record.get("builtin_name") == name]
        # This fixture intentionally contains several huge-val calls. Select
        # the one lexically inside the named leaf declaration by AST ancestry.
        if name == "__builtin_huge_valf":
            leaf_ids = {node.get("id") for node in _walk(self.declaration("renamed_free_leaf"))}
            matches = [record for record in matches
                       if record["call_expression_id"] in leaf_ids]
        self.assertEqual(len(matches), 1, (name, matches))
        return matches[0]

    def effect_protocol(self, record):
        structure = inspect_structure(self.payload, record["call_expression_id"])
        self.assertEqual(structure["status"], "checked", structure)
        return {
            "schema_version": "builtin-leaf-effect-assumption/v1",
            "native_envelope_sha256": structure["input_sha256"]["native_envelope"],
            "call_expression_id": record["call_expression_id"],
            "callee_declaration_id": record["callee_declaration_id"],
            "builtin_no_memory_write_assumed": True,
            "valid_call_and_normal_return_assumed": True,
            "evidence_reference": "wrapper-test-external-leaf-effect",
        }

    def test_renamed_free_and_static_chains_are_conditionally_checked(self):
        leaf = self.builtin_record("__builtin_huge_valf")
        protocol = self.effect_protocol(leaf)
        chains = {
            "renamed_free_leaf": ["renamed_free_leaf"],
            "renamed_free_outer": ["renamed_free_outer", "renamed_free_leaf"],
            "renamed_static_middle": ["renamed_static_middle", "renamed_free_outer",
                                      "renamed_free_leaf"],
            "renamed_static_outer": ["renamed_static_outer", "renamed_static_middle",
                                     "renamed_free_outer", "renamed_free_leaf"],
        }
        for name, chain in chains.items():
            with self.subTest(name=name):
                result = check_wrapper_no_memory_write(
                    self.payload, self.declaration(name)["id"], protocol)
                self.assertEqual(result["status"], "checked", result)
                self.assertEqual(result["conclusion"]["status"], "conditional")
                self.assertEqual(result["conclusion"]["property"], "no_memory_write")
                self.assertEqual(result["conclusion"]["subject"],
                                 "restricted_single_return_wrapper_chain")
                self.assertEqual(result["wrapper_declaration_ids"],
                                 [self.declaration(item)["id"] for item in chain])
                self.assertEqual(result["leaf_check"]["status"], "checked")
                self.assertFalse(result["external_leaf_effect_verified"])
                self.assertEqual(result["value_semantics"], "not_established")
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_writes_comma_recursion_and_unknown_external_stay_unknown(self):
        protocol = self.effect_protocol(self.builtin_record("__builtin_huge_valf"))
        for name in ("writes_before_leaf", "comma_return", "recursive_wrapper",
                     "external_wrapper", "parameter_wrapper"):
            with self.subTest(name=name):
                result = check_wrapper_no_memory_write(
                    self.payload, self.declaration(name)["id"], protocol)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_instance_and_virtual_methods_are_not_static_wrapper_chains(self):
        protocol = self.effect_protocol(self.builtin_record("__builtin_huge_valf"))
        for name in ("instance_wrapper", "virtual_wrapper"):
            with self.subTest(name=name):
                result = check_wrapper_no_memory_write(
                    self.payload, self.declaration(name)["id"], protocol)
                self.assertEqual(result["status"], "unknown", result)

    def test_protocol_must_name_the_exact_reached_leaf(self):
        huge = self.builtin_record("__builtin_huge_valf")
        nan = self.builtin_record("__builtin_nanf")
        wrong_leaf = self.effect_protocol(nan)
        result = check_wrapper_no_memory_write(
            self.payload, self.declaration("renamed_static_outer")["id"], wrong_leaf)
        self.assertEqual(result["status"], "unknown", result)

        stale = deepcopy(self.effect_protocol(huge))
        stale["call_expression_id"] = "other"
        result = check_wrapper_no_memory_write(
            self.payload, self.declaration("renamed_free_leaf")["id"], stale)
        self.assertEqual(result["status"], "unknown", result)

    def test_real_chain_depth_boundary_is_exactly_32_wrappers(self):
        source = Path(self.temporary.name) / "builtin_wrapper_depth.cpp"
        lines = ["float chain0() { return __builtin_huge_valf(); }"]
        lines.extend(f"float chain{index}() {{ return chain{index - 1}(); }}"
                     for index in range(1, 33))
        source.write_text("\n".join(lines) + "\n")
        collected = collect(source, COMPILER, Path(PLUGIN), ["-std=c++17"])
        self.assertEqual(collected["status"], "collected", collected)
        payload = collected["payload"]
        definitions = {node.get("name"): node for node in _walk(payload["ast"])
                       if node.get("kind") == "FunctionDecl" and
                       any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                           for child in node.get("inner", []))}
        self.assertTrue(all(f"chain{index}" in definitions for index in range(33)))
        records = [record for record in payload["builtin_calls"]
                   if record.get("builtin_name") == "__builtin_huge_valf"]
        self.assertEqual(len(records), 1, records)
        leaf = records[0]
        structure = inspect_structure(payload, leaf["call_expression_id"])
        self.assertEqual(structure["status"], "checked", structure)
        protocol = {
            "schema_version": "builtin-leaf-effect-assumption/v1",
            "native_envelope_sha256": structure["input_sha256"]["native_envelope"],
            "call_expression_id": leaf["call_expression_id"],
            "callee_declaration_id": leaf["callee_declaration_id"],
            "builtin_no_memory_write_assumed": True,
            "valid_call_and_normal_return_assumed": True,
            "evidence_reference": "wrapper-depth-boundary-leaf-effect",
        }

        accepted = check_wrapper_no_memory_write(
            payload, definitions["chain31"]["id"], protocol)
        self.assertEqual(accepted["status"], "checked", accepted)
        self.assertEqual(len(accepted["wrapper_declaration_ids"]), 32)
        self.assertEqual(accepted["wrapper_declaration_ids"][0], definitions["chain31"]["id"])
        self.assertEqual(accepted["wrapper_declaration_ids"][-1], definitions["chain0"]["id"])

        refused = check_wrapper_no_memory_write(
            payload, definitions["chain32"]["id"], protocol)
        self.assertEqual(refused["status"], "unknown", refused)
        self.assertEqual(refused["reason"], "wrapper_cycle_or_depth_budget")
        self.assertEqual(len(refused["wrapper_declaration_ids"]), 32)
        self.assertFalse(refused["source_program_checked"])
        self.assertFalse(refused["deployable"])


if __name__ == "__main__":
    unittest.main()
