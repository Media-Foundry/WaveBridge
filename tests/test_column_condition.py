"""Conservative conditional body effects; not conditional value evaluation."""

import unittest

from test_column_loops import literal, loop, ref, root_with, typed
from wavebridge.analysis.column_loops import recover


def analyze(expression):
    return recover(root_with(loop(body={"kind": "CompoundStmt", "inner": [expression]})),
                   "fn", 32)


class ColumnConditionTests(unittest.TestCase):
    def test_all_three_operand_effects_are_checked(self):
        for position in range(3):
            children = [literal(0), literal(1), literal(2)]
            children[position] = typed("CompoundAssignOperator", opcode="+=",
                                       inner=[ref("i"), literal(1)])
            report = analyze(typed("ConditionalOperator", inner=children))
            self.assertEqual(report["status"], "unknown")
            self.assertEqual(report["loops"][0]["reason"], "protected_variable_may_be_modified")
            self.assertTrue(report["loops"][0]["header_recurrence_observed"])

    def test_malformed_or_gnu_conditionals_remain_unknown(self):
        for operands in (None, [], [literal(0)], [literal(0), literal(1)],
                         [literal(0), literal(1), {}], [literal(0), literal(1), None],
                         [literal(0), literal(1), literal(2), literal(3)]):
            with self.subTest(operands=operands):
                report = analyze(typed("ConditionalOperator", inner=operands))
                self.assertEqual(report["status"], "unknown")
                self.assertEqual(report["loops"][0]["reason"], "conditional_body_operands_ambiguous")
        self.assertEqual(analyze(typed("BinaryConditionalOperator", inner=[literal(1)]))["status"],
                         "unknown")

    def test_plain_value_condition_is_supported_without_proving_values(self):
        report = analyze(typed("ConditionalOperator", inner=[literal(0), ref("i"), ref("limit")]))
        self.assertEqual(report["status"], "recovered", report)
        self.assertFalse(report["checked"])
        self.assertFalse(report["deployable"])


if __name__ == "__main__":
    unittest.main()
