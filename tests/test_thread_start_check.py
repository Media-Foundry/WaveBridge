"""Composition gates with mocked frontend/configuration, real integer checkers.

These fixtures test orchestration, not source recovery or GPU behavior.
"""
import copy
from contextlib import ExitStack
import unittest
from unittest.mock import patch

from wavebridge.thread_start_check import check
from wavebridge.verification.getter_returns import _hash
from tests.test_getter_returns import fixture, ABI
from tests.test_initializer_domain import reports


class ThreadStartCompositionTests(unittest.TestCase):
    def setUp(self):
        self.root, _ = fixture()
        self.start_declaration = {"kind": "VarDecl", "id": "tid",
                                  "type": {"qualType": "const int"}}
        self.root["inner"].append({"kind": "FunctionDecl", "id": "kernel", "inner": [
            {"kind": "CompoundStmt", "inner": [
                {"kind": "DeclStmt", "inner": [self.start_declaration]}]}]})
        self.binding = {
            "schema_version": "thread-start-assumptions/v1", "ast_root_sha256": _hash(self.root),
            "kernel_declaration_id": "kernel", "launch_id": "launch", "axis_binding": {},
            "configuration_positions": {"grid": 0, "block": 1},
            "coordinate": {"semantics": "workgroup_local_id", "axis": 0,
                           "declaration_id": "leaf", "return_type": {"qualType": "unsigned long"}},
        }
        self.columns = {"status": "recovered", "function_id": "kernel", "loops": [
            {"status": "recovered", "step": 256,
             "start": {"kind": "declaration_reference", "declaration_id": "tid"}}]}
        self.launches = {"sites": [{"launch_id": "launch", "kernel_declaration_id": "kernel",
                                    "configuration_arguments": [{}, {}, {}, {}]}]}
        link, _ = reports()
        link["callee_declaration_id"] = "start"
        self.origin = {"status": "evidence", "value_link": link}
        self.block = {"status": "checked", "dimensions": {"x": 256, "y": 1, "z": 1}}
        self.chain = {"status": "recovered", "function_id": "kernel", "block_threads": 256}

    def run_check(self):
        with ExitStack() as stack:
            for name, value in {
                "recover_columns": self.columns,
                "recover_chain": self.chain,
                "inspect_launch": self.launches, "inspect_constructor": {},
                "check_block": self.block, "inspect_initializer": self.origin,
            }.items():
                stack.enter_context(patch("wavebridge.thread_start_check." + name, return_value=value))
            return check(self.root, "kernel", "launch", ABI, self.binding)

    def test_composes_real_getter_and_initializer_checks_from_block_domain(self):
        result = self.run_check()
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["start_interval"], {"lower": 0, "upper": 255})
        self.assertEqual(result["derived_leaf_domain"]["upper"], 255)
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_persistent_ambiguous_or_attributed_start_cannot_compose(self):
        for change in ({"storageClass": "static"}, {"tls": "dynamic"},
                       {"tlsKind": "none"}, {"inner": [{"kind": "AlignedAttr"}]}):
            with self.subTest(change=change):
                original = copy.deepcopy(self.start_declaration)
                self.start_declaration.update(change)
                self.binding["ast_root_sha256"] = _hash(self.root)
                result = self.run_check()
                self.assertEqual(result["status"], "unknown", result)
                self.assertEqual(result["reason"], "start_not_unique_direct_automatic_const_int")
                self.start_declaration.clear()
                self.start_declaration.update(original)
        self.root["inner"].append(copy.deepcopy(self.start_declaration))
        self.binding["ast_root_sha256"] = _hash(self.root)
        self.assertEqual(self.run_check()["status"], "unknown")

    def test_global_or_nested_start_is_outside_supported_entry_subset(self):
        kernel = self.root["inner"][-1]
        body = kernel["inner"][0]
        statement = body["inner"].pop()
        self.root["inner"].append(self.start_declaration)
        self.binding["ast_root_sha256"] = _hash(self.root)
        self.assertEqual(self.run_check()["status"], "unknown")
        self.root["inner"].pop()
        body["inner"].append({"kind": "CompoundStmt", "inner": [statement]})
        self.binding["ast_root_sha256"] = _hash(self.root)
        self.assertEqual(self.run_check()["status"], "unknown")

    def test_stale_root_kernel_launch_or_coordinate_protocol_stays_unknown(self):
        original = copy.deepcopy(self.binding)
        for key, value in (("ast_root_sha256", "stale"), ("kernel_declaration_id", "other"),
                           ("launch_id", "other"), ("schema_version", "other/v1")):
            self.binding = dict(original, **{key: value})
            self.assertEqual(self.run_check()["status"], "unknown")
        for axis in (1, True, None):
            self.binding = copy.deepcopy(original)
            self.binding["coordinate"]["axis"] = axis
            self.assertEqual(self.run_check()["status"], "unknown")

    def test_disconnected_loops_and_launches_do_not_compose(self):
        original = copy.deepcopy(self.columns)
        self.columns["loops"][0]["step"] = 128
        self.assertEqual(self.run_check()["status"], "unknown")
        self.columns = copy.deepcopy(original)
        other = copy.deepcopy(self.columns["loops"][0])
        other["start"]["declaration_id"] = "other"
        self.columns["loops"].append(other)
        self.assertEqual(self.run_check()["status"], "unknown")
        self.columns = original
        self.launches["sites"].append(copy.deepcopy(self.launches["sites"][0]))
        self.assertEqual(self.run_check()["status"], "unknown")
        self.launches["sites"] = []
        self.assertEqual(self.run_check()["status"], "unknown")

    def test_failed_components_or_wrong_external_leaf_cannot_pass(self):
        self.binding["coordinate"]["declaration_id"] = "unrelated"
        self.assertEqual(self.run_check()["status"], "unknown")
        self.binding["coordinate"]["declaration_id"] = "leaf"
        self.block["status"] = "rejected"
        self.assertEqual(self.run_check()["status"], "rejected")
        self.block = {"status": "checked", "dimensions": {"x": 300, "y": 1, "z": 1}}
        self.chain["block_threads"] = 300
        self.columns["loops"][0]["step"] = 300
        self.origin["value_link"]["conversions_outer_to_inner"][0]["target_type"] = "unsigned char"
        self.assertEqual(self.run_check()["status"], "rejected")

    def test_configuration_positions_and_checked_dimension_schema_are_gated(self):
        for positions in (None, {}, {"grid": 1, "block": 0}, {"grid": 0, "block": True}):
            self.binding["configuration_positions"] = positions
            self.assertEqual(self.run_check()["status"], "unknown")
        self.binding["configuration_positions"] = {"grid": 0, "block": 1}
        for dimensions in (None, {}, {"x": True, "y": 1, "z": 1},
                           {"x": 256, "y": 2, "z": 1}, {"x": 128, "y": 1, "z": 1}):
            self.block["dimensions"] = dimensions
            self.assertEqual(self.run_check()["status"], "unknown")

    def test_block_checker_does_not_assume_the_coordinate_conclusion(self):
        from wavebridge.verification.block_configuration import check as block_check
        report = block_check({}, {}, {}, {})
        self.assertNotIn("kernel_uses_x_coordinate_for_recovered_column_start", report["premises"])


if __name__ == "__main__":
    unittest.main()
