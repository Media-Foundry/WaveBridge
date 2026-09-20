import copy
import unittest
from unittest.mock import patch

from wavebridge.verification.kernel_arguments import check


ABI = {"int": {"bits": 32, "signed": True},
       "unsigned int": {"bits": 32, "signed": False},
       "signed char": {"bits": 8, "signed": True}}


def binding(identifier="count"):
    leaf = {"kind": "DeclRefExpr", "type": {"qualType": "const int"},
            "referencedDecl": {"kind": "VarDecl", "id": identifier}}
    return {"position": 2, "parameter_declaration_id": "parameter",
            "parameter_type": {"qualType": "int"},
            "argument_ast": {"kind": "ImplicitCastExpr", "castKind": "LValueToRValue",
                             "type": {"qualType": "int"}, "inner": [leaf]}}


def interval(identifier="count", lower=1, upper=1023):
    return {"declaration_id": identifier, "lower": lower, "upper": upper,
            "type": {"qualType": "const int"}}


class KernelArgumentTests(unittest.TestCase):
    def test_checks_exact_declref_interval_and_records_scope(self):
        report = binding()
        domains = [interval(), interval("unused", 1, 8)]
        before = copy.deepcopy((report, domains, ABI))
        result = check(report, domains, ABI)
        self.assertEqual("checked", result["status"])
        self.assertEqual("kernel-argument-domain-check/v1", result["schema_version"])
        self.assertEqual("count", result["declaration_id"])
        self.assertEqual({"lower": 1, "upper": 1023}, result["interval"])
        self.assertEqual("interval", result["value_kind"])
        self.assertEqual("parameter", result["parameter_declaration_id"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        self.assertEqual(before, (report, domains, ABI))

    def test_literal_is_checked_without_interval(self):
        report = binding()
        report["argument_ast"] = {"kind": "ParenExpr", "inner": [
            {"kind": "IntegerLiteral", "value": "7", "type": {"qualType": "int"}}]}
        result = check(report, [], ABI)
        self.assertEqual("checked", result["status"])
        self.assertEqual("constant", result["value_kind"])
        self.assertEqual(7, result["value"])

    def test_missing_wrong_type_and_duplicate_interval_are_not_accepted(self):
        self.assertEqual("argument_declaration_interval_missing",
                         check(binding(), [interval("other")], ABI)["reason"])
        wrong = interval()
        wrong["type"] = {"qualType": "int"}
        self.assertEqual("declaration_interval_leaf_type_mismatch",
                         check(binding(), [wrong], ABI)["reason"])
        self.assertEqual("declaration_interval_ids_not_unique",
                         check(binding(), [interval(), interval()], ABI)["reason"])

    def test_negative_unsigned_and_partial_narrowing_reject(self):
        report = binding()
        report["parameter_type"] = {"qualType": "unsigned int"}
        report["argument_ast"]["type"] = {"qualType": "unsigned int"}
        report["argument_ast"]["castKind"] = "IntegralCast"
        self.assertEqual("integer_conversion_not_value_preserving",
                         check(report, [interval(lower=-1)], ABI)["reason"])
        report["parameter_type"] = {"qualType": "signed char"}
        report["argument_ast"]["type"] = {"qualType": "signed char"}
        self.assertEqual("integer_conversion_not_value_preserving",
                         check(report, [interval(upper=128)], ABI)["reason"])

    def test_pointer_call_bad_cast_and_malformed_json_stay_unknown(self):
        report = binding()
        report["argument_ast"] = {"kind": "CallExpr", "type": {"qualType": "int"}}
        self.assertEqual("argument_leaf_not_supported_scalar_integer",
                         check(report, [interval()], ABI)["reason"])
        report = binding()
        report["argument_ast"]["castKind"] = "BitCast"
        self.assertEqual("unsupported_argument_cast", check(report, [interval()], ABI)["reason"])
        self.assertEqual("inputs_not_expected_objects", check([], [], ABI)["reason"])
        report = binding()
        report["position"] = True
        self.assertEqual("parameter_position_invalid", check(report, [], ABI)["reason"])
        malformed = interval()
        malformed["lower"] = True
        self.assertEqual("declaration_interval_bounds_invalid",
                         check(binding(), [malformed], ABI)["reason"])

    def test_pointer_and_float_arguments_remain_unknown_even_with_domain_evidence(self):
        pointer = binding()
        pointer_leaf = pointer["argument_ast"]["inner"][0]
        pointer_leaf["type"] = {"qualType": "const float *"}
        pointer["argument_ast"]["type"] = {"qualType": "const float *"}
        pointer["parameter_type"] = {"qualType": "const float *"}
        pointer_domain = interval()
        pointer_domain["type"] = {"qualType": "const float *"}
        before = copy.deepcopy((pointer, pointer_domain))
        result = check(pointer, [pointer_domain], ABI)
        self.assertEqual("unknown", result["status"])
        self.assertEqual("non_scalar_integer_type_unsupported", result["reason"])
        self.assertEqual(before, (pointer, pointer_domain))

        floating = binding()
        floating["argument_ast"] = {"kind": "FloatingLiteral", "value": "0.00001",
                                    "type": {"qualType": "float"}}
        floating["parameter_type"] = {"qualType": "float"}
        self.assertEqual("argument_leaf_not_supported_scalar_integer",
                         check(floating, [], ABI)["reason"])

    def test_final_parameter_and_nonconverting_type_changes_reject_without_mutation(self):
        report = binding()
        report["parameter_type"] = {"qualType": "unsigned int"}
        before = copy.deepcopy(report)
        result = check(report, [interval()], ABI)
        self.assertEqual("parameter_type_chain_mismatch", result["reason"])
        self.assertEqual(before, report)

        for cast_kind in ("NoOp", "LValueToRValue"):
            report = binding()
            report["argument_ast"]["castKind"] = cast_kind
            report["argument_ast"]["type"] = {"qualType": "unsigned int"}
            before = copy.deepcopy(report)
            result = check(report, [interval()], ABI)
            self.assertEqual("nonconverting_cast_changes_base_type", result["reason"])
            self.assertEqual(before, report)

    def test_initial_domain_and_budgets_are_checked(self):
        tiny = {**ABI, "signed char": {"bits": 3, "signed": True}}
        report = binding()
        report["argument_ast"]["inner"][0]["type"] = {"qualType": "const signed char"}
        domain = interval(lower=-4, upper=4)
        domain["type"] = {"qualType": "const signed char"}
        self.assertEqual("argument_domain_not_representable_in_initial_type",
                         check(report, [domain], tiny)["reason"])
        with patch("wavebridge.verification.kernel_arguments.MAX_INTERVALS", 0):
            self.assertEqual("declaration_interval_budget_exceeded",
                             check(binding(), [interval()], ABI)["reason"])
        report = binding()
        wrapper = report["argument_ast"]
        for _ in range(65):
            wrapper = {"kind": "ImplicitCastExpr", "castKind": "NoOp",
                       "type": {"qualType": "int"}, "inner": [wrapper]}
        report["argument_ast"] = wrapper
        self.assertEqual("argument_cast_budget_exceeded",
                         check(report, [interval()], ABI)["reason"])


if __name__ == "__main__":
    unittest.main()
