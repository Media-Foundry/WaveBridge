"""Malformed AST evidence must not establish builtin increment recurrence."""

from copy import deepcopy
import unittest

from test_column_loops import loop, ref, root_with, typed
from wavebridge.analysis.column_loops import recover


def candidate(postfix=False):
    node = loop()
    operand = ref("i")
    operand.update(valueCategory="lvalue")
    operand["referencedDecl"]["type"] = {"qualType": "int"}
    node["inner"][3] = typed("UnaryOperator", opcode="++", isPostfix=postfix,
                             valueCategory="prvalue" if postfix else "lvalue",
                             inner=[operand])
    return node


class ColumnIncrementTests(unittest.TestCase):
    def test_prefix_postfix_and_parentheses_preserve_observation(self):
        for postfix in (False, True):
            node = candidate(postfix)
            inc = node["inner"][3]
            inc["inner"] = [typed("ParenExpr", valueCategory="lvalue", inner=inc["inner"])]
            result = recover(root_with(node), "fn", 32)
            self.assertEqual(result["status"], "recovered", result)
            self.assertEqual(result["loops"][0]["step"], 1)
            self.assertEqual(result["loops"][0]["increment_ast"], inc)
            self.assertFalse(result["checked"])
            self.assertFalse(result["deployable"])

    def test_missing_or_contradictory_unary_evidence_is_unknown(self):
        base = candidate()
        variants = []
        for key, value in (("isPostfix", None), ("isPostfix", 0),
                           ("valueCategory", "prvalue"),
                           ("type", {"qualType": "volatile int"}),
                           ("inner", []), ("opcode", "--")):
            node = deepcopy(base)
            node["inner"][3][key] = value
            variants.append(node)
        for key, value in (("valueCategory", "prvalue"),
                           ("type", {"qualType": "unsigned int"}),
                           ("kind", "CXXStaticCastExpr")):
            node = deepcopy(base)
            node["inner"][3]["inner"][0][key] = value
            variants.append(node)
        for declaration in ({"id": "other", "kind": "VarDecl", "type": {"qualType": "int"}},
                            {"id": "i", "kind": "VarDecl"},
                            {"id": "i", "kind": "VarDecl", "type": {"qualType": "int &"}}):
            node = deepcopy(base)
            node["inner"][3]["inner"][0]["referencedDecl"] = declaration
            variants.append(node)
        for node in variants:
            with self.subTest(increment=node["inner"][3]):
                result = recover(root_with(node), "fn", 32)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["loops"][0]["header_recurrence_observed"])


if __name__ == "__main__":
    unittest.main()
