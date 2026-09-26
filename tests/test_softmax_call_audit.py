"""Inventory fixtures do not establish call effects or workload coverage."""
import unittest

from experiments.softmax_call_audit import inventory


def function(identifier, *statements, kind="FunctionDecl", name="same"):
    return {"kind": kind, "id": identifier, "name": name, "storageClass": "static",
            "inner": [{"kind": "CompoundStmt", "inner": list(statements)}]}


def call(identifier, kind="FunctionDecl"):
    return {"kind": "CallExpr", "inner": [{"kind": "DeclRefExpr",
            "referencedDecl": {"id": identifier, "kind": kind}}]}


class SoftmaxCallAuditTests(unittest.TestCase):
    def test_method_reference_observation_does_not_override_resolver(self):
        root = {"inner": [function("entry", call("method", "CXXMethodDecl")),
                          function("method", call("external"), kind="CXXMethodDecl"),
                          {"kind": "FunctionDecl", "id": "external", "name": "leaf"}]}
        result = inventory(root, "entry")
        edge = result["edges"][0]
        self.assertEqual(edge["observed_reference_id"], "method")
        self.assertIsNone(edge["production_resolution"]["callee_id"])
        self.assertFalse(edge["dispatch_checked"])
        self.assertFalse(edge["effects_checked"])
        self.assertEqual(result["functions"][-1]["definition_count"], 0)
        self.assertFalse(result["deployable"])

    def test_duplicate_definition_does_not_choose_by_name(self):
        result = inventory({"inner": [function("entry", call("wrong")), function("entry")]}, "entry")
        self.assertEqual(result["functions"][0]["definition_count"], 2)
        self.assertEqual(result["edges"], [])

    def test_indirect_callee_does_not_consume_argument_function_reference(self):
        indirect = {"kind": "CallExpr", "inner": [{"kind": "DeclRefExpr",
                    "referencedDecl": {"kind": "VarDecl", "id": "pointer"}},
                    call("argument_function")["inner"][0]]}
        result = inventory({"inner": [function("entry", indirect)]}, "entry")
        self.assertIsNone(result["edges"][0]["inventory_target_id"])

    def test_budget_and_cycle_preserve_diagnostic_boundary(self):
        root = {"inner": [function("a", call("b")), function("b", call("a"))]}
        limited = inventory(root, "a", max_functions=1)
        self.assertTrue(limited["budget_exhausted"])
        self.assertEqual(limited["pending_ids"], ["b"])
        complete = inventory(root, "a")
        self.assertFalse(complete["budget_exhausted"])
        self.assertEqual(len(complete["functions"]), 2)


if __name__ == "__main__":
    unittest.main()
