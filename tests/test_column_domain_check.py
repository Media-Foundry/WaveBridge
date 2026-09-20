"""Composition fixtures: mocked recovery, real argument and coverage checks."""
import copy
from contextlib import ExitStack
import unittest
from unittest.mock import patch

from wavebridge.column_domain_check import check
from wavebridge.verification.getter_returns import _hash
from tests.test_kernel_arguments import ABI, binding as argument_binding, interval


class ColumnDomainTests(unittest.TestCase):
    def setUp(self):
        ref = {"kind": "DeclRefExpr", "referencedDecl": {"id": "parameter"}}
        read = {"kind": "ImplicitCastExpr", "castKind": "LValueToRValue", "inner": [ref]}
        self.body = {"kind": "CompoundStmt", "inner": [
            {"kind": "ForStmt", "range": {"begin": i}, "inner": [copy.deepcopy(read)]}
            for i in (1, 2)]}
        self.root = {"kind": "TranslationUnitDecl", "inner": [
            {"kind": "FunctionDecl", "id": "kernel", "inner": [self.body]}]}
        self.binding = {"schema_version": "thread-start-assumptions/v1",
                        "kernel_declaration_id": "kernel", "launch_id": "launch"}
        self.thread = {"schema_version": "conditional-thread-start-check/v1", "status": "checked",
                       "kernel_declaration_id": "kernel", "launch_id": "launch", "int_bits": 32,
                       "start_interval": {"lower": 0, "upper": 255}, "start_declaration_id": "tid"}
        self.bind_hashes()
        self.columns = {"status": "recovered", "function_id": "kernel", "loops": [
            {"status": "recovered", "range": {"begin": i}, "step": 256,
             "bound": {"kind": "parameter", "declaration_id": "parameter"},
             "start": {"kind": "declaration_reference", "declaration_id": "tid"}}
            for i in (1, 2)]}
        self.site = {"launch_id": "launch", "kernel_declaration_id": "kernel",
                     "parameter_binding_status": "bound_by_position",
                     "parameter_bindings": [argument_binding()]}
        self.launches = {"sites": [self.site]}
        self.guards = {"schema_version": "launch-guards/v1", "status": "recovered",
                       "launch_id": "launch", "int_bits": 32, "intervals": [interval()],
                       "interpretation": "necessary_conditions_to_pass_supported_early_returns_only"}

    def bind_hashes(self):
        self.binding["ast_root_sha256"] = _hash(self.root)
        self.thread["input_sha256"] = {"root": _hash(self.root), "binding": _hash(self.binding),
                                       "integer_types": _hash(ABI)}

    def run_check(self, enabled=True):
        with ExitStack() as stack:
            for name, value in (("recover_columns", self.columns), ("inspect_launch", self.launches),
                                ("recover_guards", self.guards)):
                stack.enter_context(patch("wavebridge.column_domain_check." + name, return_value=value))
            return check(self.root, self.thread, ABI, self.binding, use_host_guard_assumptions=enabled)

    def test_two_loops_entire_host_interval(self):
        result = self.run_check()
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(len(result["loops"]), 2)
        for loop in result["loops"]:
            self.assertEqual(loop["coverage"]["interval_checked"], {"lower": 1, "upper": 1023})
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_explicit_opt_in_and_hash_binding(self):
        for enabled in (False, 1, None):
            self.assertEqual(self.run_check(enabled)["status"], "unknown")
        for key in ("root", "binding", "integer_types"):
            self.bind_hashes()
            self.thread["input_sha256"][key] = "stale"
            self.assertEqual(self.run_check()["status"], "unknown")

    def test_parameter_write_escape_and_early_exit_are_unknown(self):
        for extra in ({"kind": "DeclRefExpr", "referencedDecl": {"id": "parameter"}},
                      {"kind": "UnaryOperator", "opcode": "&", "inner": [
                          {"kind": "DeclRefExpr", "referencedDecl": {"id": "parameter"}}]},
                      {"kind": "ReturnStmt"}):
            self.setUp()
            self.body["inner"].insert(0, extra)
            self.bind_hashes()
            self.assertEqual(self.run_check()["status"], "unknown")

    def test_conditionally_reached_loop_not_accepted(self):
        self.body["inner"][0] = {"kind": "IfStmt", "inner": [self.body["inner"][0]]}
        self.bind_hashes()
        self.assertEqual(self.run_check()["reason"], "column_loops_not_direct_kernel_statements")

    def test_wrong_stride_start_and_missing_parameter(self):
        for key, value in (("step", 128), ("start", {"kind": "declaration_reference", "declaration_id": "other"})):
            self.setUp()
            self.columns["loops"][0][key] = value
            self.assertEqual(self.run_check()["status"], "unknown")
        for bindings in ([], [argument_binding(), argument_binding()]):
            self.setUp()
            self.site["parameter_bindings"] = bindings
            self.assertEqual(self.run_check()["status"], "unknown")

    def test_guard_and_launch_mismatch(self):
        for target, key, value in (("guards", "status", "unknown"), ("guards", "int_bits", 64),
                                   ("guards", "launch_id", "other"), ("site", "kernel_declaration_id", "other")):
            self.setUp()
            getattr(self, target)[key] = value
            self.assertEqual(self.run_check()["status"], "unknown")

    def test_final_increment_overflow_is_unknown(self):
        self.guards["intervals"] = [interval(upper=(1 << 31) - 1)]
        result = self.run_check()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["loops"][0]["coverage"]["reason"], "signed_increment_overflow")

    def test_argument_conversion_rejection_propagates(self):
        argument = self.site["parameter_bindings"][0]
        argument["parameter_type"] = {"qualType": "signed char"}
        argument["argument_ast"]["type"] = {"qualType": "signed char"}
        argument["argument_ast"]["castKind"] = "IntegralCast"
        self.assertEqual(self.run_check()["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
