import unittest
from unittest.mock import patch

from wavebridge.verification.constructor_values import check


ABI = {"int": {"bits": 32, "signed": True},
       "unsigned int": {"bits": 32, "signed": False}}
R = {"begin": {"offset": 1}, "end": {"offset": 2}}


def argument(position, value, source="integer_literal", symbolic=False):
    leaf = ({"kind": "IntegerLiteral", "value": str(value), "type": {"qualType": "int"}}
            if source == "integer_literal" else
            {"kind": "DeclRefExpr", "type": {"qualType": "const int"},
             "referencedDecl": {"id": f"decl{position}", "kind": "VarDecl"}})
    cast = {"cast_kind": "IntegralCast", "source_type": {"qualType": "int"},
            "destination_type": {"desugaredQualType": "unsigned int", "qualType": "Alias"},
            "range": R}
    return {"position": position, "status": "symbolic" if symbolic else "evidence",
            **({"declaration_id": f"decl{position}"} if symbolic else {}),
            "argument_ast": {"kind": "ImplicitCastExpr", "inner": [leaf]}, "casts": [cast],
            "pre_conversion_constant": None if symbolic else {"status": "evaluated", "value": value,
                "source": source, **({"declaration_id": f"decl{position}"}
                                      if source != "integer_literal" else {})}}


def constructor(values=(2, 3, 4), sources=None):
    sources = sources or ("integer_literal",) * len(values)
    return {"schema_version": "constructor-arguments/v1", "status": "inspected",
            "constructor_declaration_id": "ctor",
            "arguments": [argument(i, value, sources[i]) for i, value in enumerate(values)]}


def fields(positions=(0, 1, 2)):
    mappings = []
    for field_index, position in enumerate(positions):
        mappings.append({"field_id": f"f{field_index}", "field_name": f"name{field_index}",
                         "parameter_id": f"p{position}", "parameter_position": position,
                         "parameter_type": {"desugaredQualType": "unsigned int", "qualType": "Alias"},
                         "field_type": {"desugaredQualType": "unsigned int", "qualType": "Alias"},
                         "casts": [{"cast_kind": "LValueToRValue",
                                    "source_type": {"desugaredQualType": "unsigned int"},
                                    "destination_type": {"desugaredQualType": "unsigned int"}}]})
    return {"schema_version": "constructor-fields/v1", "status": "recovered",
            "constructor_declaration_id": "ctor",
            "record_completeness": "all_direct_record_fields_initialized",
            "field_mappings": mappings}


class ConstructorValueTests(unittest.TestCase):
    def test_same_and_exchanged_mapping_are_checked_by_position(self):
        result = check(constructor(), fields(), ABI)
        self.assertEqual("checked", result["status"])
        self.assertEqual([2, 3, 4], [field["value"] for field in result["fields"]])
        exchanged = check(constructor(), fields((1, 0, 2)), ABI)
        self.assertEqual("checked", exchanged["status"])
        self.assertEqual([3, 2, 4], [field["value"] for field in exchanged["fields"]])
        self.assertFalse(exchanged["source_program_checked"])
        self.assertFalse(exchanged["deployable"])

    def test_constructor_position_and_type_chain_mismatch_reject(self):
        report = fields()
        report["constructor_declaration_id"] = "other"
        self.assertEqual("constructor_declaration_id_mismatch", check(constructor(), report, ABI)["reason"])
        report = fields()
        report["field_mappings"][1]["parameter_position"] = 0
        self.assertEqual("parameter_positions_not_one_to_one", check(constructor(), report, ABI)["reason"])
        report = fields()
        report["field_mappings"][0]["parameter_type"] = {"qualType": "int"}
        self.assertEqual("final_type_chain_mismatch", check(constructor(), report, ABI)["reason"])

    def test_narrowing_and_negative_unsigned_reject(self):
        narrow_abi = {**ABI, "short": {"bits": 16, "signed": True}}
        report = constructor((70000, 1, 1))
        report["arguments"][0]["casts"][0]["destination_type"] = {"qualType": "short"}
        field_report = fields()
        field_report["field_mappings"][0]["parameter_type"] = {"qualType": "short"}
        field_report["field_mappings"][0]["field_type"] = {"qualType": "short"}
        field_report["field_mappings"][0]["casts"][0]["source_type"] = {"qualType": "short"}
        field_report["field_mappings"][0]["casts"][0]["destination_type"] = {"qualType": "short"}
        self.assertEqual("integer_conversion_not_value_preserving",
                         check(report, field_report, narrow_abi)["reason"])
        self.assertEqual("integer_conversion_not_value_preserving",
                         check(constructor((-1, 1, 1)), fields(), ABI)["reason"])

    def test_symbolic_unknown_abi_and_declaration_premise(self):
        report = constructor()
        report["arguments"][0] = argument(0, 0, symbolic=True)
        self.assertEqual("constructor_argument_not_constant", check(report, fields(), ABI)["reason"])
        self.assertEqual("integer_type_missing_from_abi", check(constructor(), fields(), {})["reason"])
        result = check(constructor(sources=("signed_int_declaration",) * 3), fields(), ABI)
        self.assertEqual("checked", result["status"])
        self.assertEqual(["decl0", "decl1", "decl2"], result["declaration_constant_premises"])
        self.assertFalse(result["source_program_checked"])

    def test_literal_raw_value_mismatch_and_budgets(self):
        report = constructor()
        report["arguments"][0]["argument_ast"]["inner"][0]["value"] = "99"
        self.assertEqual("literal_constant_value_mismatch", check(report, fields(), ABI)["reason"])
        with patch("wavebridge.verification.constructor_values.MAX_FIELDS", 2):
            result = check(constructor(), fields(), ABI)
        self.assertEqual("field_budget_exceeded", result["reason"])
        with patch("wavebridge.verification.constructor_values.MAX_CASTS", 2):
            result = check(constructor(), fields(), ABI)
        self.assertEqual("cast_budget_exceeded", result["reason"])

    def test_malformed_entries_positions_ids_and_empty_inputs_are_gated(self):
        report = constructor()
        report["arguments"][0] = None
        self.assertEqual("argument_entry_not_object", check(report, fields(), ABI)["reason"])
        report = constructor()
        report["arguments"][0]["casts"] = None
        self.assertEqual("argument_casts_not_list", check(report, fields(), ABI)["reason"])
        report = constructor()
        report["arguments"][0]["position"] = True
        self.assertEqual("argument_positions_not_exact_and_ordered", check(report, fields(), ABI)["reason"])
        field_report = fields()
        field_report["field_mappings"][0]["parameter_position"] = None
        self.assertEqual("parameter_position_not_integer", check(constructor(), field_report, ABI)["reason"])
        field_report = fields()
        field_report["field_mappings"][1]["field_id"] = "f0"
        self.assertEqual("field_ids_not_unique", check(constructor(), field_report, ABI)["reason"])
        empty_constructor, empty_fields = constructor(()), fields(())
        self.assertEqual("arguments_or_mappings_empty", check(empty_constructor, empty_fields, ABI)["reason"])

    def test_status_constant_status_and_no_cast_initial_range_are_gated(self):
        report = constructor()
        report["arguments"][0]["status"] = "inspected"
        self.assertEqual("argument_status_invalid", check(report, fields(), ABI)["reason"])
        report = constructor()
        report["arguments"][0]["pre_conversion_constant"]["status"] = "unknown"
        self.assertEqual("constructor_constant_not_evaluated", check(report, fields(), ABI)["reason"])
        report = constructor((200, 1, 1))
        report["arguments"][0]["casts"] = []
        report["arguments"][0]["argument_ast"] = {"kind": "IntegerLiteral", "value": "200",
                                                     "type": {"qualType": "signed char"}}
        char_abi = {**ABI, "signed char": {"bits": 8, "signed": True}}
        field_report = fields()
        field_report["field_mappings"][0]["parameter_type"] = {"qualType": "signed char"}
        field_report["field_mappings"][0]["field_type"] = {"qualType": "signed char"}
        field_report["field_mappings"][0]["casts"] = []
        self.assertEqual("constant_not_representable_in_initial_type",
                         check(report, field_report, char_abi)["reason"])

    def test_unhashable_status_cast_null_reference_and_empty_constructor_are_gated(self):
        report = constructor()
        report["arguments"][0]["status"] = []
        self.assertEqual("argument_status_invalid", check(report, fields(), ABI)["reason"])
        report = constructor()
        report["arguments"][0]["casts"][0]["cast_kind"] = {}
        self.assertEqual("unsupported_or_missing_cast_evidence",
                         check(report, fields(), ABI)["reason"])
        report = constructor(sources=("signed_int_declaration",) * 3)
        report["arguments"][0]["argument_ast"]["inner"][0]["referencedDecl"] = None
        self.assertEqual("declaration_constant_raw_ast_mismatch",
                         check(report, fields(), ABI)["reason"])
        report = constructor()
        report["constructor_declaration_id"] = ""
        field_report = fields()
        field_report["constructor_declaration_id"] = ""
        self.assertEqual("constructor_declaration_id_mismatch",
                         check(report, field_report, ABI)["reason"])

    def test_explicit_symbolic_interval_is_checked_without_fabricating_a_value(self):
        report = constructor()
        report["arguments"][0] = argument(0, 0, source="signed_int_declaration", symbolic=True)
        intervals = [{"declaration_id": "decl0", "lower": 1, "upper": 8,
                      "type": {"qualType": "const int"}}]
        result = check(report, fields(), ABI, intervals)
        self.assertEqual("constructor-values-check/v2", result["schema_version"])
        self.assertEqual("checked", result["status"])
        self.assertEqual("interval", result["fields"][0]["value_kind"])
        self.assertEqual({"lower": 1, "upper": 8}, result["fields"][0]["interval"])
        self.assertNotIn("value", result["fields"][0])
        self.assertEqual("constant", result["fields"][1]["value_kind"])
        self.assertIn("declaration_intervals", result["input_sha256"])
        self.assertEqual(["decl0"], result["interval_declaration_premises"])
        self.assertEqual(64, result["budget"]["max_intervals"])
        self.assertIn("each symbolic declaration runtime value lies within its supplied closed interval",
                      result["assumptions"])
        self.assertIn("the source guard producing each supplied interval is not verified by this checker",
                      result["assumptions"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

        unused = intervals + [{"declaration_id": "unused", "lower": 1, "upper": 1023,
                               "type": {"qualType": "const int"}}]
        result = check(report, fields(), ABI, unused)
        self.assertEqual(["decl0"], result["interval_declaration_premises"])

    def test_v1_assumptions_and_budget_remain_unchanged(self):
        result = check(constructor(), fields(), ABI)
        self.assertEqual("constructor-values-check/v1", result["schema_version"])
        self.assertNotIn("max_intervals", result["budget"])
        self.assertNotIn("interval_declaration_premises", result)
        self.assertEqual([
            "reports faithfully preserve the source AST evidence",
            "declaration-derived constants are accepted as explicit report premises",
            "the explicit ABI table matches the compilation target",
        ], result["assumptions"])

    def test_symbolic_interval_identity_type_and_constant_evidence_are_strict(self):
        report = constructor()
        report["arguments"][0] = argument(0, 0, source="signed_int_declaration", symbolic=True)
        base = [{"declaration_id": "decl0", "lower": 1, "upper": 8,
                 "type": {"qualType": "const int"}}]
        wrong = [dict(base[0], declaration_id="other")]
        self.assertEqual("symbolic_declaration_interval_missing",
                         check(report, fields(), ABI, wrong)["reason"])
        wrong = [dict(base[0], type={"qualType": "int"})]
        self.assertEqual("symbolic_interval_leaf_type_mismatch",
                         check(report, fields(), ABI, wrong)["reason"])
        report["arguments"][0]["declaration_id"] = "other"
        self.assertEqual("symbolic_argument_raw_declref_mismatch",
                         check(report, fields(), ABI, base)["reason"])
        report = constructor()
        report["arguments"][0] = argument(0, 0, source="signed_int_declaration", symbolic=True)
        report["arguments"][0]["pre_conversion_constant"] = {"status": "evaluated", "value": 1}
        self.assertEqual("symbolic_argument_has_constant_evidence",
                         check(report, fields(), ABI, base)["reason"])

    def test_interval_conversion_checks_whole_closed_range(self):
        report = constructor()
        report["arguments"][0] = argument(0, 0, source="signed_int_declaration", symbolic=True)
        negative = [{"declaration_id": "decl0", "lower": -1, "upper": 8,
                     "type": {"qualType": "const int"}}]
        self.assertEqual("integer_conversion_not_value_preserving",
                         check(report, fields(), ABI, negative)["reason"])
        narrow_abi = {**ABI, "signed char": {"bits": 4, "signed": True}}
        report["arguments"][0]["casts"][0]["destination_type"] = {"qualType": "signed char"}
        field_report = fields()
        mapping = field_report["field_mappings"][0]
        mapping["parameter_type"] = {"qualType": "signed char"}
        mapping["field_type"] = {"qualType": "signed char"}
        mapping["casts"][0]["source_type"] = {"qualType": "signed char"}
        mapping["casts"][0]["destination_type"] = {"qualType": "signed char"}
        partial = [{"declaration_id": "decl0", "lower": 0, "upper": 8,
                    "type": {"qualType": "const int"}}]
        self.assertEqual("integer_conversion_not_value_preserving",
                         check(report, field_report, narrow_abi, partial)["reason"])

    def test_interval_input_shape_uniqueness_and_budget_are_gated(self):
        report = constructor()
        report["arguments"][0] = argument(0, 0, source="signed_int_declaration", symbolic=True)
        valid = {"declaration_id": "decl0", "lower": 1, "upper": 8,
                 "type": {"qualType": "const int"}}
        self.assertEqual("declaration_intervals_not_list",
                         check(report, fields(), ABI, {})["reason"])
        self.assertEqual("declaration_interval_bounds_invalid",
                         check(report, fields(), ABI, [dict(valid, lower=True)])["reason"])
        self.assertEqual("declaration_interval_bounds_invalid",
                         check(report, fields(), ABI, [dict(valid, lower=9)])["reason"])
        self.assertEqual("declaration_interval_ids_not_unique",
                         check(report, fields(), ABI, [valid, dict(valid)])["reason"])
        self.assertEqual("type_evidence_missing",
                         check(report, fields(), ABI, [dict(valid, type=None)])["reason"])
        with patch("wavebridge.verification.constructor_values.MAX_FIELDS", 0):
            result = check(report, fields(), ABI, [valid])
        self.assertEqual("declaration_interval_budget_exceeded", result["reason"])

    def test_small_signed_narrowing_intervals_match_pointwise_enumeration(self):
        small_abi = {"int": {"bits": 4, "signed": True},
                     "unsigned int": {"bits": 4, "signed": False},
                     "signed char": {"bits": 3, "signed": True}}
        report = constructor()
        report["arguments"][0] = argument(0, 0, source="signed_int_declaration", symbolic=True)
        report["arguments"][0]["casts"][0]["destination_type"] = {"qualType": "signed char"}
        field_report = fields()
        mapping = field_report["field_mappings"][0]
        mapping["parameter_type"] = {"qualType": "signed char"}
        mapping["field_type"] = {"qualType": "signed char"}
        mapping["casts"][0]["source_type"] = {"qualType": "signed char"}
        mapping["casts"][0]["destination_type"] = {"qualType": "signed char"}
        for lower in range(-8, 8):
            for upper in range(lower, 8):
                interval = [{"declaration_id": "decl0", "lower": lower, "upper": upper,
                             "type": {"qualType": "const int"}}]
                status = check(report, field_report, small_abi, interval)["status"]
                expected = "checked" if all(-4 <= value <= 3
                                             for value in range(lower, upper + 1)) else "rejected"
                self.assertEqual(expected, status, (lower, upper))


if __name__ == "__main__":
    unittest.main()
