import unittest

from wavebridge.analysis.constructor_fields import recover


R = {"begin": {"offset": 1}, "end": {"offset": 2}}
TYPE = {"qualType": "Alias", "desugaredQualType": "unsigned int"}


def parameter(identifier):
    return {"id": identifier, "kind": "ParmVarDecl", "type": dict(TYPE), "range": R}


def field(identifier, name):
    return {"id": identifier, "kind": "FieldDecl", "name": name, "type": dict(TYPE), "range": R}


def initializer(field_node, parameter_id, cast_kind="LValueToRValue"):
    reference = {"kind": "DeclRefExpr", "range": R, "type": dict(TYPE),
                 "referencedDecl": {"id": parameter_id, "kind": "ParmVarDecl"}}
    expression = {"kind": "ImplicitCastExpr", "castKind": cast_kind, "range": R,
                  "type": dict(TYPE), "inner": [reference]}
    return {"kind": "CXXCtorInitializer", "anyInit": field_node,
            "range": R, "inner": [expression]}


def fixture(mapping=(0, 1, 2), body=None):
    fields = [field(f"f{i}", name) for i, name in enumerate(("alpha", "beta", "gamma"))]
    parameters = [parameter(f"p{i}") for i in range(3)]
    initializers = [initializer(field_node, f"p{mapping[index]}")
                    for index, field_node in enumerate(fields)]
    constructor = {"id": "ctor", "kind": "CXXConstructorDecl", "range": R,
                   "inner": [*parameters, *initializers,
                             {"kind": "CompoundStmt", "range": R, "inner": body or []}]}
    record = {"id": "record", "kind": "CXXRecordDecl", "name": "Arbitrary",
              "range": R, "inner": [*fields, constructor]}
    return {"kind": "TranslationUnitDecl", "inner": [record]}


class ConstructorFieldTests(unittest.TestCase):
    def test_recovers_positional_mapping_without_using_names(self):
        result = recover(fixture(), "ctor")
        self.assertEqual("recovered", result["status"])
        self.assertEqual([0, 1, 2], [item["parameter_position"] for item in result["field_mappings"]])
        self.assertEqual("all_direct_record_fields_initialized", result["record_completeness"])
        self.assertFalse(result["checked"])

    def test_field_exchange_is_preserved_as_structure_not_name_semantics(self):
        result = recover(fixture((1, 0, 2)), "ctor")
        self.assertEqual("recovered", result["status"])
        self.assertEqual([1, 0, 2], [item["parameter_position"] for item in result["field_mappings"]])
        self.assertEqual("not_established", result["actual_configuration_values"])

    def test_body_base_duplicate_and_arithmetic_are_unknown(self):
        self.assertEqual("constructor_body_not_empty",
                         recover(fixture(body=[{"kind": "NullStmt"}]), "ctor")["reason"])
        tree = fixture()
        ctor = tree["inner"][0]["inner"][-1]
        ctor["inner"][3]["anyInit"] = {"kind": "CXXRecordDecl", "id": "base"}
        self.assertEqual("base_or_delegating_initializer_unsupported", recover(tree, "ctor")["reason"])
        tree = fixture()
        ctor = tree["inner"][0]["inner"][-1]
        ctor["inner"][4]["anyInit"] = ctor["inner"][3]["anyInit"]
        self.assertEqual("duplicate_field_initializer", recover(tree, "ctor")["reason"])
        tree = fixture()
        ctor = tree["inner"][0]["inner"][-1]
        ctor["inner"][3]["inner"] = [{"kind": "BinaryOperator", "opcode": "+", "inner": []}]
        self.assertEqual("field_initializer_not_exact_parameter_reference", recover(tree, "ctor")["reason"])

    def test_unknown_cast_type_mismatch_and_incomplete_record_are_unknown(self):
        tree = fixture()
        ctor = tree["inner"][0]["inner"][-1]
        ctor["inner"][3]["inner"][0]["castKind"] = "IntegralCast"
        self.assertEqual("unsupported_field_initializer_cast", recover(tree, "ctor")["reason"])
        tree = fixture()
        tree["inner"][0]["inner"][0]["type"]["desugaredQualType"] = "int"
        self.assertEqual("field_parameter_desugared_type_mismatch", recover(tree, "ctor")["reason"])
        tree = fixture()
        tree["inner"][0]["inner"].insert(3, field("extra", "delta"))
        self.assertEqual("constructor_field_initializers_not_complete_for_record",
                         recover(tree, "ctor")["reason"])

    def test_record_ownership_absence_is_partial_not_complete(self):
        tree = fixture()
        ctor = tree["inner"][0]["inner"][-1]
        detached = {"kind": "TranslationUnitDecl", "inner": [ctor]}
        result = recover(detached, "ctor")
        self.assertEqual("recovered", result["status"])
        self.assertEqual("record_ownership_not_uniquely_established", result["record_completeness"])


if __name__ == "__main__":
    unittest.main()
