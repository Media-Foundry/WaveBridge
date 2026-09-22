"""Real property ASTs: header observation must never become recurrence proof.

The thread report below is a hand-built test premise, not a coordinate proof.
Loop and launch recovery are not mocked; the column gate must stop at the loop.
"""
from pathlib import Path
import shutil
import unittest

from wavebridge.analysis.column_loops import recover
from wavebridge.column_domain_check import check
from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.getter_returns import _hash


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class CoordinateColumnsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/coordinate_columns.cpp",
                         shutil.which("clang++"), ["-std=c++17", "-fms-extensions"],
                         "coordinate_columns", full_translation_unit=True,
                         dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]
        cls.functions = {n["name"]: n["id"] for n in _walk(cls.root)
                         if n.get("kind") == "FunctionDecl"}

    def test_body_preservation_is_checked_separately_without_establishing_recurrence(self):
        for name in ("coordinate_columns", "changed_body", "extra_cast", "arithmetic_step",
                     "reference_body", "changed_bound", "called_body"):
            with self.subTest(name=name):
                result = recover(self.root, self.functions[name], 32)
                self.assertEqual("unknown", result["status"])
                loop = result["loops"][0]
                self.assertIsNotNone(loop["initializer_ast"])
                self.assertIsNotNone(loop["increment_ast"])
                self.assertIsNone(loop["step"])
                self.assertFalse(loop["header_recurrence_observed"])
                body_status = ("established_in_supported_effect_subset" if name == "coordinate_columns"
                               else "not_established")
                self.assertEqual(body_status, loop["body_preserves_induction"])
                self.assertEqual(body_status, loop["body_preserves_bound"])
                if name == "changed_body":
                    self.assertEqual("protected_variable_may_be_modified", loop["body_effect_reason"])
                if name == "reference_body":
                    self.assertEqual("protected_variable_reference_alias", loop["body_effect_reason"])
                if name == "changed_bound":
                    self.assertEqual("protected_variable_may_be_modified", loop["body_effect_reason"])
                if name == "called_body":
                    self.assertEqual("call_in_body", loop["body_effect_reason"])
                observation = loop["coordinate_header_observation"]
                expected = "unknown" if name in ("extra_cast", "arithmetic_step") else "observed"
                self.assertEqual(expected, observation["status"], observation)

    def test_unmocked_column_gate_does_not_consume_observed_header(self):
        abi = {"int": {"bits": 32, "signed": True}}
        for name in ("coordinate_columns", "changed_body", "reference_body", "changed_bound", "called_body"):
            kernel = self.functions[name]
            binding = {"schema_version": "thread-start-assumptions/v1",
                       "ast_root_sha256": _hash(self.root), "kernel_declaration_id": kernel,
                       "launch_id": "fixture-not-runtime-launch"}
            thread = {"schema_version": "conditional-thread-start-check/v1", "status": "checked",
                      "kernel_declaration_id": kernel, "launch_id": binding["launch_id"],
                      "int_bits": 32, "start_interval": {"lower": 0, "upper": 255},
                      "input_sha256": {"root": _hash(self.root), "integer_types": _hash(abi),
                                       "binding": _hash(binding)},
                      "fixture_only": "hand_supplied_thread_premise_not_a_coordinate_proof"}
            result = check(self.root, thread, abi, binding, use_host_guard_assumptions=True)
            self.assertEqual("unknown", result["status"])
            self.assertEqual("column_recovery_incomplete", result["reason"])
            self.assertFalse(result["deployable"])


if __name__ == "__main__":
    unittest.main()
