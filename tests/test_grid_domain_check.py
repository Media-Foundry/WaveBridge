"""Fresh recovery orchestration; grid field arithmetic has independent tests."""
import unittest
from unittest.mock import patch
from contextlib import ExitStack

from wavebridge.grid_domain_check import check
from wavebridge.verification.getter_returns import _hash


class GridDomainTests(unittest.TestCase):
    def setUp(self):
        self.root = {}
        self.abi = {"int": {"bits": 32, "signed": True}}
        self.binding = {"schema_version": "grid-domain-assumptions/v1", "ast_root_sha256": _hash({}),
                        "kernel_declaration_id": "kernel", "launch_id": "launch",
                        "configuration_position": 0, "axis_binding": {"axes": "explicit"}}
        self.site = {"launch_id": "launch", "kernel_declaration_id": "kernel",
                     "configuration_arguments": [{"grid": "raw"}, {}, {}, {}]}
        self.guards = {"schema_version": "launch-guards/v1", "status": "recovered",
                       "launch_id": "launch", "int_bits": 32, "intervals": [],
                       "interpretation": "necessary_conditions_to_pass_supported_early_returns_only"}
        self.grid = {"status": "checked", "dimensions": {"x": {"lower": 1, "upper": 8},
                     "y": {"lower": 1, "upper": 1}, "z": {"lower": 1, "upper": 1}}}

    def run_check(self, enabled=True):
        with ExitStack() as stack:
            recovery_calls = {}
            for name, value in (("inspect_launch", {"sites": self.sites if hasattr(self, "sites") else [self.site]}),
                                ("inspect_constructor", {"constructor_declaration_id": "ctor"}),
                                ("recover_fields", {"fields": "fresh"}), ("recover_guards", self.guards)):
                recovery_calls[name] = stack.enter_context(patch("wavebridge.grid_domain_check." + name, return_value=value))
            grid = stack.enter_context(patch("wavebridge.grid_domain_check.check_grid", return_value=self.grid))
            result = check(self.root, "kernel", "launch", self.abi, self.binding,
                           use_host_guard_assumptions=enabled)
            self.recovery_calls = recovery_calls
            return result, grid

    def test_constructor_fields_and_guard_intervals_are_forwarded(self):
        result, grid = self.run_check()
        self.assertEqual(result["status"], "checked")
        site, abi, axes, intervals = grid.call_args.args
        self.assertEqual(site["configuration_constructor_arguments"][0]["field_initialization"], {"fields": "fresh"})
        self.assertEqual(intervals, [])
        self.assertEqual(axes, self.binding["axis_binding"])
        self.assertEqual(abi, self.abi)
        self.recovery_calls["inspect_constructor"].assert_called_once_with(self.root, {"grid": "raw"}, 32)
        self.recovery_calls["recover_fields"].assert_called_once_with(self.root, "ctor")
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_binding_or_explicit_flag_mismatch(self):
        for flag in (False, 1, None):
            self.assertEqual(self.run_check(flag)[0]["status"], "unknown")
        original = dict(self.binding)
        for key, value in (("configuration_position", False), ("configuration_position", 1),
                           ("ast_root_sha256", "stale"), ("kernel_declaration_id", "other"),
                           ("launch_id", "other")):
            self.binding = {**original, key: value}
            self.assertEqual(self.run_check()[0]["status"], "unknown")

    def test_missing_duplicate_wrong_launch(self):
        for sites in ([], [self.site, self.site], [{**self.site, "kernel_declaration_id": "other"}]):
            self.sites = sites
            self.assertEqual(self.run_check()[0]["status"], "unknown")

    def test_guard_mismatch_and_missing_abi(self):
        original = dict(self.guards)
        for key, value in (("status", "unknown"), ("launch_id", "other"), ("int_bits", 64)):
            self.guards = {**original, key: value}
            result, grid = self.run_check()
            self.assertEqual(result["status"], "unknown")
            grid.assert_not_called()
        self.guards = original
        self.abi = {}
        self.assertEqual(self.run_check()[0]["status"], "unknown")

    def test_grid_failure_propagates(self):
        for status in ("rejected", "unknown"):
            self.grid = {"status": status, "reason": "component_failure"}
            self.assertEqual(self.run_check()[0]["status"], status)


if __name__ == "__main__":
    unittest.main()
