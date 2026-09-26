"""Private fresh-child join fixtures, not independent source or value proofs."""
import copy
import unittest

from wavebridge.device_evidence import _local_entry_signature
from wavebridge.verification.getter_returns import _hash


def fixture():
    root = {"fixture": True}
    protocol = {"int_bits": 32, "integer_types": {"int": {"bits": 32, "signed": True}},
                "row_binding": {"coordinate": {"semantics": "workgroup_id", "axis": 0,
                                                 "return_type": {"qualType": "unsigned long"}}},
                "thread_binding": {"coordinate": {"semantics": "workgroup_local_id", "axis": 0,
                                                    "return_type": {"qualType": "unsigned long"}}}}
    local = {"function_id": "kernel", "loop": {"range": {"offset": 1}}, "value_declaration_id": "value"}
    roles = {name: {"declaration_id": name, "kind": "ParmVarDecl", "type": {"qualType": typ},
                    "parameter_position": position}
             for name, typ, position in (("input", "const float *", 0), ("bound", "int", 2),
                                          ("start", "const int", None), ("accumulator", "float", None))}
    automatic = "automatic_on_each_passage_through_declaration"
    prefix = {"status": "recovered", "function_id": "kernel", "declaration_evaluation": automatic,
              "normalization_output": {"local_contribution": copy.deepcopy(local)},
              "source_parameter_id": "input", "start_declaration_id": "start",
              "count_parameter_id": "bound", "row_declaration_id": "row"}
    offsets = {"status": "checked", "count_parameter_id": "bound", "row_declaration_id": "row",
               "row_interval": {"lower": 0, "upper": 7}, "count_interval": {"lower": 1, "upper": 1023},
               "checks": {"row": {"status": "checked", "prefix_recovery": prefix},
                          "thread": {"status": "checked", "declaration_evaluation": automatic,
                                     "start_declaration_id": "start", "start_interval": {"lower": 0, "upper": 255},
                                     "recovery": {"chain": {"accumulator_declaration_id": "accumulator"}}},
                          "source_offset": {"symbolic_relation": {"coefficient": 1, "row_power": 1, "count_power": 1},
                                            "result_type": "long"}}}
    side = {"kernel_declaration_id": "kernel", "checks": {"integers": {"checks": {"row_offsets": offsets}}}}
    snapshot = {"local_recovery": local, "role_bindings": roles,
                "input_sha256": _hash({"root": root, "kernel": "kernel", "int_bits": 32})}
    return root, protocol, side, snapshot


class LocalEntryBindingTests(unittest.TestCase):
    def test_connects_relations_without_runtime_value_claim(self):
        signature = _local_entry_signature(*fixture())
        self.assertEqual(0, signature["parameter_roles"]["input"]["parameter_position"])
        self.assertEqual({"lower": 0, "upper": 255}, signature["start_interval"])
        self.assertNotIn("leaf_value_correspondence", signature)

    def test_changed_roles_and_stale_snapshot_fail(self):
        for role in ("input", "bound", "start", "accumulator"):
            values = fixture()
            values[3]["role_bindings"][role]["declaration_id"] = "unrelated"
            with self.subTest(role=role), self.assertRaises(ValueError):
                _local_entry_signature(*values)
        values = fixture()
        values[0]["changed"] = True
        with self.assertRaises(ValueError):
            _local_entry_signature(*values)

    def test_local_loop_or_value_mismatch_fails(self):
        for key in ("loop", "value_declaration_id"):
            values = fixture()
            values[3]["local_recovery"][key] = "different"
            with self.subTest(key=key), self.assertRaises(ValueError):
                _local_entry_signature(*values)

    def test_persistent_or_unchecked_coordinate_fails(self):
        for child, key, value in (("row", "status", "unknown"), ("thread", "status", "unknown"),
                                  ("thread", "declaration_evaluation", "not_established")):
            values = fixture()
            values[2]["checks"]["integers"]["checks"]["row_offsets"]["checks"][child][key] = value
            with self.subTest(child=child, key=key), self.assertRaises(ValueError):
                _local_entry_signature(*values)


if __name__ == "__main__":
    unittest.main()
