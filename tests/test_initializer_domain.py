import copy
import unittest

from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.initializer_domain import check


ABI = {
    "int": {"bits": 32, "signed": True},
    "unsigned int": {"bits": 32, "signed": False},
    "unsigned char": {"bits": 8, "signed": False},
}


def reports(lower=0, upper=255, target="const int"):
    link = {
        "schema_version": "initializer-value-link/v1", "status": "recovered",
        "call_id": "call", "callee_declaration_id": "getter",
        "call_type": "unsigned int",
        "conversions_outer_to_inner": [{
            "cast_kind": "IntegralCast", "source_type": "unsigned int",
            "target_type": target, "range": {"begin": {}, "end": {}},
            "value_preservation": "not_established",
        }],
    }
    getter = {
        "schema_version": "getter-return-domain-check/v1", "status": "checked",
        "start_declaration_id": "getter", "return_type": "unsigned int",
        "return_interval": {"lower": lower, "upper": upper},
        "input_sha256": {"integer_types": _hash(ABI)},
        "source_program_checked": False, "deployable": False,
    }
    return link, getter


class InitializerDomainTests(unittest.TestCase):
    def test_unsigned_call_to_signed_initializer_is_checked_on_small_domain(self):
        link, getter = reports()
        result = check(link, getter, ABI)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["result_type"], "int")
        self.assertEqual(result["result_interval"], {"lower": 0, "upper": 255})
        self.assertEqual(result["conversion_checks"][0]["conversion"]["status"], "checked")
        self.assertEqual(set(result["input_sha256"]),
                         {"value_link", "getter_report", "integer_types"})
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        self.assertEqual(result["receiver_purity"], "not_established")
        self.assertEqual(result["coordinate_semantics"], "not_established")

    def test_initializer_narrowing_is_rejected(self):
        link, getter = reports(upper=256, target="unsigned char")
        result = check(link, getter, ABI)
        self.assertEqual(result["status"], "rejected", result)
        self.assertEqual(result["conversion_checks"][-1]["conversion"]["status"], "rejected")
        self.assertFalse(result["source_program_checked"])

    def test_binding_abi_type_and_chain_failures_are_unknown(self):
        cases = {}
        link, getter = reports(); link["callee_declaration_id"] = "other"
        cases["callee"] = (link, getter, ABI)
        link, getter = reports(); link["call_type"] = "int"
        cases["call_type"] = (link, getter, ABI)
        link, getter = reports(); getter["input_sha256"]["integer_types"] = "0" * 64
        cases["abi_hash"] = (link, getter, ABI)
        link, getter = reports(); link["conversions_outer_to_inner"][0]["source_type"] = "int"
        cases["chain"] = (link, getter, ABI)
        link, getter = reports(); link["conversions_outer_to_inner"][0]["cast_kind"] = "NoOp"
        cases["cast_kind"] = (link, getter, ABI)
        for name, arguments in cases.items():
            with self.subTest(name=name):
                result = check(*arguments)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_unknown_reports_and_missing_or_invalid_domain(self):
        cases = []
        link, getter = reports(); link["status"] = "unknown"
        cases.append((link, getter, ABI))
        link, getter = reports(); getter["status"] = "unknown"
        cases.append((link, getter, ABI))
        link, getter = reports(); getter.pop("return_interval")
        cases.append((link, getter, ABI))
        link, getter = reports(); getter["return_interval"] = {"lower": 4, "upper": 3}
        cases.append((link, getter, ABI))
        link, getter = reports(); getter.pop("return_type")
        cases.append((link, getter, ABI))
        cases.extend([(None, getter, ABI), (link, None, ABI), (link, getter, None)])
        for arguments in cases:
            with self.subTest(arguments=arguments):
                self.assertEqual(check(*arguments)["status"], "unknown")

    def test_conversion_order_is_inner_to_outer_and_budget_is_bounded(self):
        link, getter = reports(target="int")
        link["conversions_outer_to_inner"] = [
            {"cast_kind": "IntegralCast", "source_type": "int", "target_type": "unsigned int"},
            {"cast_kind": "IntegralCast", "source_type": "unsigned int", "target_type": "int"},
        ]
        result = check(link, getter, ABI)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["result_type"], "unsigned int")
        too_many = copy.deepcopy(link)
        too_many["conversions_outer_to_inner"] = [
            {"cast_kind": "IntegralCast", "source_type": "unsigned int",
             "target_type": "unsigned int"} for _ in range(33)]
        self.assertEqual(check(too_many, getter, ABI)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
