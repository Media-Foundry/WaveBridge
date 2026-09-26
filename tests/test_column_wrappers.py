"""Only concrete bool replacement and expression-free loop hint wrappers are supported."""
from copy import deepcopy
import unittest

from test_column_loops import loop, root_with
from test_column_nested import program
from wavebridge.analysis.column_loops import recover


def substitution(value=False, parameter=True):
    literal = {"kind": "CXXBoolLiteralExpr", "type": {"qualType": "bool"},
               "valueCategory": "prvalue", "value": value}
    declaration = {"kind": "NonTypeTemplateParmDecl", "id": "flag",
                   "type": {"qualType": "bool"}}
    return {"kind": "SubstNonTypeTemplateParmExpr", "type": {"qualType": "bool"},
            "valueCategory": "prvalue", "inner": [declaration, literal] if parameter else [literal]}


def analyze(expression):
    return recover(root_with(loop(body={"kind": "CompoundStmt", "inner": [expression]})), "fn", 32)


class ColumnWrapperTests(unittest.TestCase):
    def test_bool_replacement_with_and_without_parameter_child(self):
        for parameter in (False, True):
            for value in (False, True):
                report = analyze(substitution(value, parameter))
                self.assertEqual(report["status"], "recovered", report)
                self.assertFalse(report["checked"])

    def test_incomplete_or_nonliteral_template_evidence_is_unknown(self):
        invalid = []
        for value in (0, 1, "false", None):
            invalid.append(substitution(value))
        for key, value in (("inner", []), ("inner", [None]), ("valueCategory", "lvalue"),
                           ("type", {"qualType": "int"})):
            node = substitution()
            node[key] = value
            invalid.append(node)
        for key, value in (("id", None), ("isParameterPack", True), ("inner", [{}]),
                           ("type", {"qualType": "bool &"})):
            node = substitution()
            node["inner"][0][key] = value
            invalid.append(node)
        node = substitution()
        node["inner"][-1]["inner"] = [{"kind": "CallExpr"}]
        invalid.append(node)
        for node in invalid:
            self.assertEqual(analyze(node)["status"], "unknown", node)

    def test_hint_wrapper_exposes_loop_without_resetting_nested_check(self):
        for contents in ([], [{}]):
            root = program()
            body = root["inner"][-1]["inner"][0]["inner"][0]["inner"][-1]
            original = body["inner"][0]
            body["inner"] = [{"kind": "AttributedStmt", "inner": [
                {"kind": "LoopHintAttr", "inner": contents}, original]}]
            report = recover(root, "fn", 32)
            self.assertEqual(report["status"], "recovered", report)
            self.assertEqual([item["lexical_loop_depth"] for item in report["loops"]], [0, 1])
            self.assertEqual(report["loops"][0]["nested_loops"][0]["iterations"], 4)

    def test_other_attributes_arguments_and_malformed_wrappers_stay_unknown(self):
        valid = {"kind": "AttributedStmt", "inner": [{"kind": "LoopHintAttr"},
                 {"kind": "ForStmt", "inner": []}]}
        variants = []
        for attr in ({"kind": "AssumeAttr"}, {"kind": "LoopHintAttr", "inner": [None]},
                     {"kind": "LoopHintAttr", "inner": [{"kind": "IntegerLiteral", "value": "4"}]}):
            node = deepcopy(valid)
            node["inner"][0] = attr
            variants.append(node)
        for inner in ([], [valid["inner"][1]], [valid["inner"][0], {}],
                      [valid["inner"][0], {"kind": "WhileStmt"}]):
            variants.append({"kind": "AttributedStmt", "inner": inner})
        for node in variants:
            self.assertEqual(analyze(node)["status"], "unknown")

    def test_partial_nested_evidence_does_not_upgrade_failing_parent(self):
        root = program()
        body = root["inner"][-1]["inner"][0]["inner"][0]["inner"][-1]
        body["inner"].append({"kind": "CallExpr", "inner": []})
        report = recover(root, "fn", 32)
        outer = report["loops"][0]
        self.assertEqual(len(outer["nested_loops"]), 1)
        self.assertEqual(outer["nested_loops"][0]["iterations"], 4)
        self.assertEqual(outer["status"], "unknown")
        self.assertEqual(outer["reason"], "call_in_body")
        self.assertEqual(outer["body_preserves_induction"], "not_established")
        self.assertEqual(outer["body_preserves_bound"], "not_established")
        self.assertEqual(report["status"], "unknown")
        self.assertFalse(report["checked"])
        self.assertFalse(report["deployable"])


if __name__ == "__main__":
    unittest.main()
