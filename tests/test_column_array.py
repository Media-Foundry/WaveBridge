"""Storage-path recognition must not discard subscript evaluation effects."""
from copy import deepcopy
import unittest

from test_column_loops import literal, loop, ref, root_with, typed
from wavebridge.analysis.column_loops import recover


def array(indexes, root_type="int [4][4]"):
    base = ref("buffer")
    base["referencedDecl"]["type"] = {"qualType": root_type}
    for index in indexes:
        base = typed("ArraySubscriptExpr", valueCategory="lvalue", inner=[base, index])
    return base


def analyze(target):
    store = typed("BinaryOperator", opcode="=", inner=[target, literal(1)])
    return recover(root_with(loop(body={"kind": "CompoundStmt", "inner": [store]})), "fn", 32)


class ColumnArrayTests(unittest.TestCase):
    def test_builtin_multidimensional_paths_keep_conditioned_status(self):
        for root_type in ("int [4][4]", "int (*)[4]", "int **"):
            result = analyze(array([ref("i"), literal(0)], root_type))
            self.assertEqual(result["status"], "recovered", result)
            self.assertFalse(result["checked"])
            self.assertEqual(result["loops"][0]["assumptions"]["memory_no_alias"], "unproven")

    def test_each_index_is_evaluated_for_effects(self):
        for dimension in (0, 1):
            for protected in ("i", "limit", "seed"):
                indexes = [literal(0), literal(0)]
                indexes[dimension] = typed("UnaryOperator", opcode="++", inner=[ref(protected)])
                report = analyze(array(indexes))
                self.assertEqual(report["status"], "unknown", report)
                self.assertEqual(report["loops"][0]["reason"], "protected_variable_may_be_modified")

    def test_missing_type_alias_and_reference_roots_are_unknown(self):
        for info in (None, {}, {"qualType": "Alias", "typeAliasDeclId": "alias"},
                     {"qualType": "int (*)[4]", "typeAliasDeclId": "alias"},
                     {"qualType": "Alias", "desugaredQualType": "int (&)[4][4]"}):
            target = array([literal(0), literal(0)])
            target["inner"][0]["inner"][0]["referencedDecl"]["type"] = info
            self.assertEqual(analyze(target)["status"], "unknown")

    def test_malformed_shapes_and_depth_over_budget_fail_closed(self):
        base = array([literal(0), literal(0)])
        for children in ([], [base], [base, {}], [base, literal(0), literal(1)]):
            target = deepcopy(base)
            target["inner"] = children
            self.assertEqual(analyze(target)["status"], "unknown")
        target = deepcopy(base)
        target.pop("valueCategory")
        self.assertEqual(analyze(target)["status"], "unknown")
        self.assertEqual(analyze(array([literal(0)] * 9))["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
