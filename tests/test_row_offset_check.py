import copy
import unittest
from unittest.mock import patch

from wavebridge.row_offset_check import check
from wavebridge.verification.getter_returns import _hash


class RowOffsetCompositionTests(unittest.TestCase):
    def setUp(self):
        self.root = {"kind": "TranslationUnitDecl"}
        self.abi = {"int": {"bits": 32, "signed": True}}
        self.binding = {"ast_root_sha256": _hash(self.root),
                        "kernel_declaration_id": "k", "launch_id": "l"}
        common = {"status": "checked", "kernel_declaration_id": "k", "launch_id": "l",
                  "input_sha256": {"root": _hash(self.root), "integer_types": _hash(self.abi)}}
        expression = {"kind": "BinaryOperator", "opcode": "*", "type": {"qualType": "int"},
                      "valueCategory": "prvalue",
                      "inner": [{"kind": "ImplicitCastExpr", "castKind": "LValueToRValue",
                                 "type": {"qualType": "int"}, "valueCategory": "prvalue",
                                 "inner": [{"kind": "DeclRefExpr", "type": {"qualType": "int"},
                                            "valueCategory": "lvalue",
                                            "referencedDecl": {"id": identifier, "kind": kind}}]}
                                for identifier, kind in (("r", "VarDecl"), ("n", "ParmVarDecl"))]}
        self.row = {**copy.deepcopy(common), "row_declaration_id": "r",
                    "row_interval": {"lower": 0, "upper": 7},
                    "prefix_recovery": {"status": "recovered", "function_id": "k",
                                        "row_declaration_id": "r", "start_declaration_id": "t",
                                        "count_parameter_id": "n",
                                        "source_offset": {"offset_ast": copy.deepcopy(expression)},
                                        "output_offset": {"offset_ast": copy.deepcopy(expression)}}}
        self.thread = {**copy.deepcopy(common), "start_declaration_id": "t"}
        loop = {"parameter_declaration_id": "n", "argument_domain": {
            "status": "checked", "parameter_declaration_id": "n", "value_kind": "interval",
            "interval": {"lower": 1, "upper": 1023}}}
        self.columns = {**copy.deepcopy(common), "loops": [copy.deepcopy(loop), copy.deepcopy(loop)]}

    def run_check(self):
        with patch("wavebridge.row_offset_check.check_row", return_value=self.row), \
                patch("wavebridge.row_offset_check.check_thread", return_value=self.thread), \
                patch("wavebridge.row_offset_check.check_columns", return_value=self.columns):
            return check(self.root, "k", "l", self.abi, self.binding, self.binding,
                         use_host_guard_assumptions=True)

    def test_checks_both_expressions_without_deployment(self):
        result = self.run_check()
        self.assertEqual("checked", result["status"], result)
        self.assertEqual({"lower": 0, "upper": 7}, result["row_interval"])
        for name in ("source_offset", "output_offset"):
            self.assertEqual("checked", result["checks"][name]["status"])
        self.assertFalse(result["deployable"])
        self.assertFalse(result["source_program_checked"])
        self.assertEqual(_hash(True), result["input_sha256"]["use_host_guard_assumptions"])
        self.assertEqual(_hash("k"), result["input_sha256"]["kernel_id"])
        self.assertEqual(_hash("l"), result["input_sha256"]["launch_id"])

    def test_rejects_wrong_second_offset_even_when_first_passes(self):
        expression = self.row["prefix_recovery"]["output_offset"]["offset_ast"]
        expression["inner"][1] = copy.deepcopy(expression["inner"][0])
        result = self.run_check()
        self.assertEqual("rejected", result["status"], result)
        self.assertEqual("checked", result["checks"]["source_offset"]["status"])

    def test_missing_expression_and_upstream_unknown_are_not_checked(self):
        del self.row["prefix_recovery"]["source_offset"]["offset_ast"]
        self.assertEqual("unknown", self.run_check()["status"])
        self.row["status"] = "unknown"
        self.assertEqual("row_coordinate_not_checked", self.run_check()["reason"])

    def test_mismatched_launch_root_and_abi_evidence(self):
        for report in (self.row, self.thread, self.columns):
            original = copy.deepcopy(report)
            for field, value in (("launch_id", "wrong"), ("kernel_declaration_id", "wrong"),
                                 ("input_sha256", {"root": "wrong"})):
                report[field] = value
                self.assertEqual("unknown", self.run_check()["status"])
                report.clear()
                report.update(copy.deepcopy(original))

    def test_count_domains_and_prefix_coordinates_must_agree(self):
        self.columns["loops"][1]["argument_domain"]["interval"]["upper"] = 9
        self.assertEqual("column_domains_disagree", self.run_check()["reason"])
        self.columns["loops"][1]["argument_domain"]["interval"]["upper"] = 1023
        self.columns["loops"][1]["parameter_declaration_id"] = "other"
        self.assertEqual("column_parameter_binding_mismatch", self.run_check()["reason"])
        self.row["prefix_recovery"]["start_declaration_id"] = "other"
        self.assertEqual("prefix_coordinate_binding_mismatch", self.run_check()["reason"])

    def test_external_bindings_must_match_before_recovery(self):
        self.binding["launch_id"] = "wrong"
        self.assertEqual("root_kernel_launch_binding_mismatch", self.run_check()["reason"])


if __name__ == "__main__":
    unittest.main()
