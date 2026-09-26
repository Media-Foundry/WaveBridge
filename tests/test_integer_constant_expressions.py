"""Small-domain and malformed-AST checks for the explicitly restricted subset."""
from copy import deepcopy
import unittest

from wavebridge.analysis.integer_constants import evaluate
from test_integer_constants import INT, literal, variable, root

BOOL = {"qualType": "bool"}


def binary(opcode, left, right, type_info=INT):
    return {"kind": "BinaryOperator", "opcode": opcode, "type": type_info,
            "inner": [left, right]}


def condition(predicate, yes, no):
    return {"kind": "ConditionalOperator", "type": INT, "inner": [predicate, yes, no]}


def boolean(value):
    return {"kind": "CXXBoolLiteralExpr", "type": BOOL, "value": value}


def run(expression, bits=32):
    return evaluate(root(variable("target", "not_a_kernel_specific_name", expression)), "target", bits)


class IntegerConstantExpressionTests(unittest.TestCase):
    def test_small_domain_shift_values_and_bounds(self):
        for bits in range(2, 10):
            for left in range(min(33, 1 << (bits - 1))):
                for right in range(-1, bits + 1):
                    for opcode in ("<<", ">>"):
                        got = run(binary(opcode, literal("l", left), literal("r", right)), bits)
                        valid_count = 0 <= right < bits
                        expected = (left * 2 ** right if opcode == "<<" else left // 2 ** right) if valid_count else None
                        supported = valid_count and expected < (1 << (bits - 1))
                        self.assertEqual(got["status"], "evaluated" if supported else "unknown",
                                         (bits, left, right, opcode, got))
                        if supported:
                            self.assertEqual(got["value"], expected)

    def test_negative_operands_and_unsigned_counts_rejected(self):
        for opcode in ("<<", ">>"):
            self.assertEqual(run(binary(opcode, literal("l", -1), literal("r", 0)))["status"], "unknown")
            count = literal("r", 1, {"qualType": "unsigned int"})
            self.assertEqual(run(binary(opcode, literal("l", 1), count))["reason"],
                             "unsupported_shift_operand_type")

    def test_comparison_predicates_select_exact_branch(self):
        operations = {"<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
                      ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
                      "==": lambda a, b: a == b, "!=": lambda a, b: a != b}
        for opcode, expected in operations.items():
            for left in range(-3, 4):
                for right in range(-3, 4):
                    pred = binary(opcode, literal("l", left), literal("r", right), BOOL)
                    result = run(condition(pred, literal("yes", 11), literal("no", 23)))
                    self.assertEqual(result["value"], 11 if expected(left, right) else 23)
                    self.assertFalse(result["checked"])

    def test_only_selected_operand_is_evaluated(self):
        bad = binary("/", literal("a", 1), literal("b", 0))
        for truth, yes, no in ((True, literal("yes", 8), bad), (False, bad, literal("no", 8))):
            self.assertEqual(run(condition(boolean(truth), yes, no))["value"], 8)
        self.assertEqual(run(condition(boolean(True), bad, literal("ok", 8)))["reason"], "division_by_zero")
        # The dead operand's type still participates in C++ conditional typing.
        self.assertEqual(run(condition(boolean(True), literal("ok", 8),
                                       literal("u", 8, {"qualType": "unsigned int"})))["status"], "unknown")

    def test_logical_short_circuit_does_not_execute_call(self):
        call = {"kind": "CallExpr", "type": BOOL, "inner": []}
        for opcode, truth, value in (("&&", False, 23), ("||", True, 11)):
            pred = binary(opcode, boolean(truth), call, BOOL)
            self.assertEqual(run(condition(pred, literal("yes", 11), literal("no", 23)))["value"], value)
        pred = binary("&&", boolean(True), call, BOOL)
        self.assertEqual(run(condition(pred, literal("yes", 11), literal("no", 23)))["status"], "unknown")

    def test_concrete_substitution_literal_not_parameter_name_or_cached_value(self):
        parameter = {"kind": "NonTypeTemplateParmDecl", "id": "p", "type": INT, "name": "anything"}
        expr = {"kind": "SubstNonTypeTemplateParmExpr", "type": INT,
                "value": "999", "inner": [parameter, literal("l", 7)]}
        result = run(expr)
        self.assertEqual(result["value"], 7)
        self.assertEqual(result["template_substitutions"][0]["parameter_id"], "p")
        expr["inner"] = [literal("l", 9)]
        self.assertEqual(run(expr)["value"], 9)
        for wrong in ({"kind": "CallExpr", "type": INT},
                      literal("u", 7, {"qualType": "unsigned int"}),
                      dict(literal("l", 7), inner=[{"kind": "CallExpr", "type": INT}]),
                      dict(literal("l", 7), valueCategory="lvalue")):
            expr["inner"] = [wrong]
            self.assertEqual(run(expr)["status"], "unknown")
        for extra in ({"isParameterPack": True}, {"type": {"qualType": "unsigned int"}}, {"id": None}):
            expr["inner"] = [dict(parameter, **extra), literal("l", 7)]
            self.assertEqual(run(expr)["status"], "unknown")

    def test_malformed_predicates_are_unknown(self):
        cases = [boolean("true"), {"kind": "CallExpr", "type": BOOL},
                 binary("<", literal("a", 1), literal("b", 2), INT),
                 binary("<", literal("a", 1), literal("b", 2, {"qualType": "unsigned int"}), BOOL)]
        for pred in cases:
            self.assertEqual(run(condition(pred, literal("yes", 1), literal("no", 2)))["status"], "unknown")
        wrong = condition(boolean(True), literal("yes", 1), literal("no", 2))
        for kind in ("BinaryConditionalOperator", "CXXOperatorCallExpr"):
            value = deepcopy(wrong)
            value["kind"] = kind
            self.assertEqual(run(value)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
