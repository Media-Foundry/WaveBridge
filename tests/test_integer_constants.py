import unittest

from wavebridge.analysis.integer_constants import evaluate

INT = {"qualType": "int"}
CONST_INT = {"qualType": "const int"}


def literal(node_id, value, type_info=INT):
    return {"id": node_id, "kind": "IntegerLiteral", "value": str(value),
            "type": type_info, "range": {"begin": {}, "end": {}}}


def variable(node_id, name, expression, **extra):
    return {"id": node_id, "kind": "VarDecl", "name": name, "type": CONST_INT,
            "constexpr": True, "init": "c", "range": {}, "inner": [expression], **extra}


def reference(node_id, declaration_id, name="irrelevant"):
    return {"id": node_id, "kind": "DeclRefExpr", "type": CONST_INT, "range": {},
            "referencedDecl": {"id": declaration_id, "kind": "VarDecl", "name": name}}


def root(*nodes): return {"kind": "TranslationUnitDecl", "inner": list(nodes)}


class IntegerConstantTests(unittest.TestCase):
    def test_rename_and_cuda_attribute_do_not_affect_value(self):
        for name in ("width", "completely_renamed"):
            var = variable("v", name, literal("n", 32))
            var["inner"].append({"kind": "CUDAConstantAttr"})
            self.assertEqual(evaluate(root(var), "v", 32)["value"], 32)

    def test_multiply_32_by_8(self):
        expression = {"kind": "BinaryOperator", "opcode": "*", "type": INT,
                      "range": {"begin": {}, "end": {}},
                      "inner": [literal("a", 32), literal("b", 8)]}
        result = evaluate(root(variable("v", "threads", expression)), "v", 32)
        self.assertEqual(result["value"], 256)
        self.assertIsNotNone(result["expression_range"])
        self.assertFalse(result["checked"])

    def test_signed_overflow_is_unknown(self):
        expression = {"kind": "BinaryOperator", "opcode": "+", "type": INT,
                      "inner": [literal("a", 2147483647), literal("b", 1)]}
        self.assertEqual(evaluate(root(variable("v", "x", expression)), "v", 32)["reason"],
                         "signed_overflow")
        min_decl = variable("min", "min", literal("minlit", -2147483648))
        overflow_remainder = {"kind": "BinaryOperator", "opcode": "%", "type": INT,
                              "inner": [reference("minref", "min"),
                                        {"kind": "UnaryOperator", "opcode": "-", "type": INT,
                                         "inner": [literal("one", 1)]}]}
        rem_decl = variable("rem", "rem", overflow_remainder)
        self.assertEqual(evaluate(root(min_decl, rem_decl), "rem", 32)["reason"],
                         "signed_overflow")

    def test_cpp_negative_division_and_remainder(self):
        def negative(node_id):
            return {"kind": "UnaryOperator", "opcode": "-", "type": INT,
                    "inner": [literal(node_id, 7)]}
        division = {"kind": "BinaryOperator", "opcode": "/", "type": INT,
                    "inner": [negative("seven"), literal("three", 3)]}
        remainder = {"kind": "BinaryOperator", "opcode": "%", "type": INT,
                     "inner": [negative("seven2"), literal("three2", 3)]}
        self.assertEqual(evaluate(root(variable("d", "d", division)), "d", 32)["value"], -2)
        self.assertEqual(evaluate(root(variable("r", "r", remainder)), "r", 32)["value"], -1)

    def test_missing_and_cycle_are_unknown(self):
        missing = variable("a", "a", reference("r", "missing"))
        self.assertEqual(evaluate(root(missing), "a", 32)["reason"], "missing_declaration")
        first, second = variable("a", "a", reference("ra", "b")), variable("b", "b", reference("rb", "a"))
        self.assertEqual(evaluate(root(first, second), "a", 32)["reason"], "cyclic_reference")

    def test_nonconst_unsigned_divzero_and_call_are_unknown(self):
        nonconst = variable("n", "n", literal("x", 1)); nonconst.pop("constexpr"); nonconst["type"] = INT
        unsigned = variable("u", "u", literal("ux", 1, {"qualType": "unsigned int"})); unsigned["type"] = {"qualType": "const unsigned int"}
        divzero = {"kind": "BinaryOperator", "opcode": "/", "type": INT,
                   "inner": [literal("one", 1), literal("zero", 0)]}
        call = {"kind": "CallExpr", "type": INT, "inner": []}
        cases = [(root(nonconst), "n", "variable_not_constexpr_or_const"),
                 (root(unsigned), "u", "unsupported_or_unsigned_type"),
                 (root(variable("z", "z", divzero)), "z", "division_by_zero"),
                 (root(variable("c", "c", call)), "c", "unsupported_cast_or_call")]
        for tree, decl_id, reason in cases:
            with self.subTest(reason=reason): self.assertEqual(evaluate(tree, decl_id, 32)["reason"], reason)

    def test_unsupported_casts_and_invalid_width_are_unknown(self):
        explicit = {"kind": "CStyleCastExpr", "type": INT, "inner": [literal("x", 1)]}
        implicit = {"kind": "ImplicitCastExpr", "castKind": "IntegralCast",
                    "type": {"qualType": "unsigned int"}, "inner": [literal("y", 1)]}
        self.assertEqual(evaluate(root(variable("e", "e", explicit)), "e", 32)["reason"], "unsupported_cast_or_call")
        self.assertEqual(evaluate(root(variable("i", "i", implicit)), "i", 32)["reason"], "unsupported_cast")
        volatile = variable("vol", "vol", literal("vx", 1))
        volatile["type"] = {"qualType": "const volatile int"}
        self.assertEqual(evaluate(root(volatile), "vol", 32)["reason"],
                         "unsupported_or_unsigned_type")
        for width in (None, True, 1, 129):
            self.assertEqual(evaluate(root(variable("v", "v", literal("q", 1))), "v", width)["reason"], "invalid_int_bits")


if __name__ == "__main__": unittest.main()
