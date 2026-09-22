import copy
import unittest

from wavebridge.verification.getter_returns import check_no_memory_write, _hash
from tests.test_getter_returns import ABI, fixture, literal


def protocol(root, *, start="start", leaf="leaf", no_write=True,
             normal_return=True, evidence="probe.ll#memory(none)"):
    return {
        "schema_version": "getter-leaf-effect-assumption/v1",
        "root_sha256": _hash(root),
        "start_declaration_id": start,
        "external_leaf_declaration_id": leaf,
        "external_leaf_no_memory_write_assumed": no_write,
        "valid_calls_and_external_leaf_returns_normally_assumed": normal_return,
        "evidence_reference": evidence,
    }


class GetterEffectsTests(unittest.TestCase):
    def test_explicit_effect_assumption_checks_only_wrapper_chain(self):
        root, contract = fixture()
        result = check_no_memory_write(root, "start", contract, ABI, protocol(root))
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["getter_return_check"]["status"], "checked")
        self.assertEqual(result["conclusion"]["property"], "no_memory_write")
        self.assertEqual(result["effect_evidence"], {
            "reference": "probe.ll#memory(none)",
            "verification_status": "unverified",
        })
        self.assertFalse(result["external_leaf_effect_verified"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_missing_false_or_empty_external_premises_remain_unknown(self):
        root, contract = fixture()
        cases = [None, {}, protocol(root, no_write=False),
                 protocol(root, normal_return=False), protocol(root, evidence="  "),
                 protocol(root, no_write=1), protocol(root, normal_return=1)]
        for item in cases:
            with self.subTest(protocol=item):
                result = check_no_memory_write(root, "start", contract, ABI, item)
                self.assertEqual(result["status"], "unknown", result)
                self.assertNotIn("conclusion", result)

    def test_protocol_must_bind_exact_inputs_and_declarations(self):
        root, contract = fixture()
        mutations = []
        for key, value in (("root_sha256", "0" * 64),
                           ("start_declaration_id", "other"),
                           ("external_leaf_declaration_id", "other"),
                           ("schema_version", "other/v1")):
            item = protocol(root)
            item[key] = value
            mutations.append(item)
        for index, item in enumerate(mutations):
            with self.subTest(index=index):
                result = check_no_memory_write(root, "start", contract, ABI, item)
                self.assertEqual(result["status"], "unknown", result)

    def test_value_domain_is_freshly_checked_and_bound(self):
        root, contract = fixture()
        changed = copy.deepcopy(contract)
        changed["upper"] = 127
        result = check_no_memory_write(root, "start", changed, ABI, protocol(root))
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["input_sha256"]["leaf_contract"], _hash(changed))
        self.assertNotEqual(result["input_sha256"]["leaf_contract"], _hash(contract))
        changed["upper"] = 1 << 32
        result = check_no_memory_write(root, "start", changed, ABI, protocol(root))
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["getter_return_check"]["status"], "rejected")
        self.assertNotIn("conclusion", result)

    def test_const_attribute_never_substitutes_for_protocol(self):
        root, contract = fixture()
        root["inner"][-1]["inner"].append({"kind": "ConstAttr", "isImplicit": True})
        result = check_no_memory_write(root, "start", contract, ABI, None)
        self.assertEqual(result["status"], "unknown", result)
        self.assertNotIn("conclusion", result)

    def test_assignment_and_opaque_call_in_wrapper_body_remain_unknown(self):
        cases = []
        root, contract = fixture()
        body = root["inner"][1]["inner"][-1]["inner"]
        body.insert(0, {"kind": "BinaryOperator", "opcode": "=", "inner": [literal(), literal()]})
        cases.append((root, contract))
        root, contract = fixture()
        body = root["inner"][1]["inner"][-1]["inner"]
        body.insert(0, {"kind": "CallExpr", "inner": [],
                        "type": {"qualType": "void"}, "valueCategory": "prvalue"})
        cases.append((root, contract))
        for root, contract in cases:
            with self.subTest(body=root["inner"][1]["inner"][-1]["inner"]):
                result = check_no_memory_write(root, "start", contract, ABI, protocol(root))
                self.assertEqual(result["status"], "unknown", result)
                self.assertEqual(result["reason"], "getter_return_check_not_checked")
                self.assertNotIn("conclusion", result)


if __name__ == "__main__":
    unittest.main()
