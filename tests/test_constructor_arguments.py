import unittest

from wavebridge.analysis.constructor_arguments import inspect


R = {"begin": {"offset": 1}, "end": {"offset": 2}}


def literal(value):
    return {"kind": "IntegerLiteral", "value": str(value), "range": R,
            "type": {"qualType": "int"}}


def reference(identifier, kind="VarDecl"):
    return {"kind": "DeclRefExpr", "range": R, "type": {"qualType": "const int"},
            "referencedDecl": {"id": identifier, "kind": kind, "type": {"qualType": "const int"}}}


def cast(child, kind="IntegralCast"):
    return {"kind": "ImplicitCastExpr", "castKind": kind, "range": R,
            "type": {"qualType": "unsigned int"}, "inner": [child]}


def expression(arguments):
    construct = {"kind": "CXXConstructExpr", "range": R,
                 "ctorType": {"qualType": "void (unsigned, unsigned, unsigned)"},
                 "type": {"qualType": "Config"}, "inner": arguments}
    functional = {"kind": "CXXFunctionalCastExpr", "castKind": "ConstructorConversion",
                  "conversionFunc": {"id": "ctor", "kind": "CXXConstructorDecl",
                                     "type": {"qualType": "void (unsigned, unsigned, unsigned)"}},
                  "type": {"qualType": "Config"}, "range": R, "inner": [construct]}
    return {"kind": "ParenExpr", "inner": [functional]}


def root_with_constant(value=256):
    declaration = {"id": "size", "kind": "VarDecl", "type": {"qualType": "const int"},
                   "constexpr": True, "init": "c", "inner": [literal(value)]}
    return {"kind": "TranslationUnitDecl", "inner": [declaration]}


class ConstructorArgumentTests(unittest.TestCase):
    def test_constant_symbolic_and_default_sources_are_preserved(self):
        default = {"kind": "CXXDefaultArgExpr", "range": R, "inner": [cast(literal(1))]}
        expr = expression([cast(reference("size")), cast(reference("dynamic", "ParmVarDecl")), default])
        result = inspect(root_with_constant(), expr, 32)
        self.assertEqual("inspected", result["status"])
        self.assertEqual("ctor", result["constructor_declaration_id"])
        self.assertEqual(256, result["arguments"][0]["pre_conversion_constant"]["value"])
        self.assertEqual("symbolic", result["arguments"][1]["status"])
        self.assertTrue(result["arguments"][2]["default_argument"])
        self.assertEqual(1, result["arguments"][2]["pre_conversion_constant"]["value"])
        self.assertEqual("not_established", result["actual_configuration_values"])
        self.assertFalse(result["checked"])

    def test_default_without_source_is_unknown_not_one(self):
        result = inspect(root_with_constant(), expression([
            {"kind": "CXXDefaultArgExpr", "inner": []}]), 32)
        self.assertEqual("unknown", result["status"])
        self.assertEqual("default_argument_source_missing_or_ambiguous",
                         result["arguments"][0]["reason"])
        self.assertIsNone(result["arguments"][0]["pre_conversion_constant"])

    def test_unknown_cast_side_effect_and_multiple_targets_are_rejected(self):
        result = inspect(root_with_constant(), expression([cast(literal(1), "FloatingToIntegral")]), 32)
        self.assertEqual("unsupported_argument_cast", result["arguments"][0]["reason"])
        side_effect = {"kind": "UnaryOperator", "opcode": "++", "inner": [reference("size")]}
        result = inspect(root_with_constant(), expression([side_effect]), 32)
        self.assertEqual("unsupported_argument_expression", result["arguments"][0]["reason"])
        expr = expression([literal(1)])
        expr["inner"][0]["inner"].append({"kind": "CXXConstructExpr"})
        self.assertEqual("constructor_target_missing_or_ambiguous",
                         inspect(root_with_constant(), expr, 32)["reason"])

    def test_literal_range_and_non_constructor_are_unknown(self):
        result = inspect(root_with_constant(), expression([literal(128)]), 8)
        self.assertEqual("pre_conversion_signed_integer_out_of_range",
                         result["arguments"][0]["reason"])
        self.assertEqual("not_constructor_functional_cast",
                         inspect(root_with_constant(), literal(1), 32)["reason"])


if __name__ == "__main__":
    unittest.main()
