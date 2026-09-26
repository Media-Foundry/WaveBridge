"""Finite nested recurrences are separate from enclosing storage effects."""
import unittest

from test_column_loops import literal, loop, ref, root_with, typed, var
from wavebridge.analysis.column_loops import recover


def program(first=0, limit=4, step=1, inner_body=None):
    inner = loop(step, induction_id="j", bound_id="bound", body=inner_body)
    inner["inner"][0]["inner"][0]["inner"] = [literal(first)]
    inner["inner"][2]["inner"][1] = ref("bound")
    outer = loop(body={"kind": "CompoundStmt", "inner": [inner]})
    root = root_with(outer, [var("bound", literal(limit), const=True)])
    def add_declaration_types(node):
        if "referencedDecl" in node:
            node["referencedDecl"]["type"] = {"qualType": "int"}
        for child in node.get("inner", []):
            add_declaration_types(child)
    add_declaration_types(root)
    return root


class ColumnNestedTests(unittest.TestCase):
    def test_finite_counts_match_small_domain_enumeration(self):
        for first in range(8):
            for limit in range(8):
                for step in range(1, 5):
                    result = recover(program(first, limit, step), "fn", 32)
                    self.assertEqual(result["status"], "recovered", result)
                    evidence = result["loops"][0]["nested_loops"][0]
                    visits = list(range(first, limit, step))
                    self.assertEqual(evidence["iterations"], len(visits))
                    self.assertEqual(evidence["final_induction"], first + len(visits) * step)
                    self.assertFalse(evidence["checked"])
                    self.assertFalse(result["deployable"])

    def test_last_increment_overflow_rejects_parent(self):
        # The outer step remains representable in this explicitly supplied ABI.
        result = recover(program(126, 127, 2), "fn", 8)
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["loops"][0]["reason"], "nested_signed_increment_overflow")
        self.assertEqual(result["loops"][0]["body_preserves_induction"], "not_established")

    def test_inner_body_is_rechecked_against_outer_storage(self):
        for identifier in ("i", "limit", "seed"):
            body = {"kind": "CompoundStmt", "inner": [typed("CompoundAssignOperator", opcode="+=",
                    inner=[ref(identifier), literal(1)])]}
            result = recover(program(inner_body=body), "fn", 32)
            self.assertEqual(result["loops"][0]["status"], "unknown", result)
            self.assertEqual(result["loops"][0]["reason"], "protected_variable_may_be_modified")
            # The inner recurrence alone does not protect those outer declarations.
            self.assertEqual(result["loops"][1]["status"], "recovered")

    def test_unknown_inner_and_third_level_remain_unknown(self):
        for body in ({"kind": "WhileStmt", "inner": []}, {"kind": "CallExpr", "inner": []},
                     loop(induction_id="k")):
            result = recover(program(inner_body=body), "fn", 32)
            self.assertEqual(result["loops"][0]["status"], "unknown", result)


if __name__ == "__main__":
    unittest.main()
