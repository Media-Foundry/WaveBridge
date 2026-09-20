import copy
import unittest

from wavebridge.analysis.entry_control import recover


TARGET_RANGE = {"begin": {"offset": 100}, "end": {"offset": 110}}


def direct_call(node_id, callee_id, *, call_range=None, arguments=()):
    reference = {"kind": "DeclRefExpr", "id": node_id + "-ref", "referencedDecl": {
        "kind": "FunctionDecl", "id": callee_id, "name": callee_id}, "inner": []}
    decay = {"kind": "ImplicitCastExpr", "castKind": "FunctionToPointerDecay",
             "inner": [reference]}
    return {"kind": "CallExpr", "id": node_id, "range": call_range or {
        "begin": {"offset": 1}, "end": {"offset": 2}},
        "inner": [decay, *arguments]}


def static_member_call(node_id, callee_id):
    receiver = {"kind": "DeclRefExpr", "id": node_id + "-object",
                "referencedDecl": {"kind": "VarDecl", "id": "builtin-object"}, "inner": []}
    member = {"kind": "MemberExpr", "id": node_id + "-member", "isArrow": False,
              "referencedMemberDecl": callee_id, "inner": [receiver]}
    decay = {"kind": "ImplicitCastExpr", "castKind": "FunctionToPointerDecay",
             "inner": [member]}
    return {"kind": "CallExpr", "id": node_id, "range": {
        "begin": {"offset": 20}, "end": {"offset": 25}}, "inner": [decay]}


def declaration(node_id="local", initializer=None):
    variable = {"kind": "VarDecl", "id": node_id, "inner": []}
    if initializer is not None:
        variable["init"] = "c"
        variable["inner"].append(initializer)
    return {"kind": "DeclStmt", "inner": [variable]}


def bounded_loop():
    init = declaration("i", {"kind": "IntegerLiteral", "value": "0", "inner": []})
    condition = {"kind": "BinaryOperator", "opcode": "<", "inner": [
        {"kind": "DeclRefExpr", "referencedDecl": {"kind": "VarDecl", "id": "i"}, "inner": []},
        {"kind": "IntegerLiteral", "value": "4", "inner": []}]}
    increment = {"kind": "UnaryOperator", "opcode": "++", "inner": [
        {"kind": "DeclRefExpr", "referencedDecl": {"kind": "VarDecl", "id": "i"}, "inner": []}]}
    return {"kind": "ForStmt", "range": {"begin": {"offset": 30}, "end": {"offset": 60}},
            "inner": [init, condition, increment, {"kind": "CompoundStmt", "inner": []}]}


def root(*statements):
    function = {"kind": "FunctionDecl", "id": "kernel", "name": "kernel", "inner": [
        {"kind": "CompoundStmt", "inner": list(statements)}]}
    return {"kind": "TranslationUnitDecl", "inner": [function]}


def run(tree):
    return recover(tree, "kernel", "helper", TARGET_RANGE)


class EntryControlTests(unittest.TestCase):
    def test_plain_prefix_calls_and_top_level_loop_become_obligations(self):
        getter = static_member_call("getter", "hip-getter")
        ordinary = direct_call("prepare", "prepare-function")
        loop = bounded_loop()
        result = run(root(declaration(initializer={"kind": "IntegerLiteral", "value": "1", "inner": []}),
                          getter, ordinary, loop,
                          direct_call("target", "helper", call_range=TARGET_RANGE)))
        self.assertEqual(result["status"], "recovered", result)
        self.assertEqual(result["function_id"], "kernel")
        self.assertEqual(result["callee_id"], "helper")
        self.assertEqual(result["call_range"], TARGET_RANGE)
        obligation_ids = [item["declaration_id"] for item in result["call_obligations"]]
        self.assertEqual(obligation_ids, ["hip-getter", "prepare-function"])
        self.assertEqual(result["loop_obligations"][0]["range"], loop["range"])
        self.assertEqual(result["participation"], "not_established")
        self.assertFalse(result["checked"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_single_variable_initializer_may_hold_exact_target_call(self):
        target = direct_call("target", "helper", call_range=TARGET_RANGE)
        wrapped = {"kind": "ParenExpr", "inner": [
            {"kind": "ImplicitCastExpr", "castKind": "NoOp", "inner": [target]}]}
        result = run(root(declaration("partial", wrapped)))
        self.assertEqual(result["status"], "recovered", result)
        self.assertEqual(result["call_obligations"], [])
        self.assertEqual(result["loop_obligations"], [])

    def test_early_control_flow_before_target_is_unknown(self):
        forbidden = [
            {"kind": "ReturnStmt", "inner": []},
            {"kind": "IfStmt", "inner": []},
            {"kind": "GotoStmt", "inner": []},
            {"kind": "WhileStmt", "inner": []},
            {"kind": "DoStmt", "inner": []},
            {"kind": "SwitchStmt", "inner": []},
            {"kind": "BreakStmt", "inner": []},
            {"kind": "ContinueStmt", "inner": []},
            {"kind": "CXXThrowExpr", "inner": []},
            {"kind": "GCCAsmStmt", "inner": []},
            {"kind": "BinaryOperator", "opcode": "&&", "inner": [
                {"kind": "IntegerLiteral", "value": "1", "inner": []},
                {"kind": "IntegerLiteral", "value": "1", "inner": []}]},
            {"kind": "ConditionalOperator", "inner": []},
        ]
        for statement in forbidden:
            with self.subTest(kind=statement["kind"], opcode=statement.get("opcode")):
                tree = root(statement, direct_call("target", "helper", call_range=TARGET_RANGE))
                self.assertEqual(run(tree)["status"], "unknown")

    def test_nested_loop_divergent_target_and_unknown_prefix_are_unknown(self):
        nested = bounded_loop()
        nested["inner"][-1]["inner"].append(bounded_loop())
        cases = [
            root(nested, direct_call("target", "helper", call_range=TARGET_RANGE)),
            root({"kind": "IfStmt", "inner": [
                {"kind": "IntegerLiteral", "value": "1", "inner": []},
                direct_call("target", "helper", call_range=TARGET_RANGE)]}),
            root({"kind": "MysteryStmt", "inner": []},
                 direct_call("target", "helper", call_range=TARGET_RANGE)),
        ]
        for tree in cases:
            with self.subTest(tree=tree):
                self.assertEqual(run(tree)["status"], "unknown")

    def test_target_id_and_range_must_identify_one_top_level_call(self):
        wrong_id = root(direct_call("target", "other", call_range=TARGET_RANGE))
        wrong_range = root(direct_call("target", "helper", call_range={
            "begin": {"offset": 101}, "end": {"offset": 111}}))
        duplicate = root(direct_call("one", "helper", call_range=TARGET_RANGE),
                         direct_call("two", "helper", call_range=copy.deepcopy(TARGET_RANGE)))
        for tree in (wrong_id, wrong_range, duplicate):
            with self.subTest(tree=tree):
                self.assertEqual(run(tree)["status"], "unknown")

    def test_suffix_return_does_not_change_entry_prefix_result(self):
        tree = root(direct_call("before", "prepare"),
                    direct_call("target", "helper", call_range=TARGET_RANGE),
                    {"kind": "ReturnStmt", "inner": []})
        result = run(tree)
        self.assertEqual(result["status"], "recovered", result)
        self.assertEqual([item["declaration_id"] for item in result["call_obligations"]], ["prepare"])
        self.assertEqual(result["participation"], "not_established")

    def test_prefix_call_obligation_never_claims_termination_or_participation(self):
        result = run(root(direct_call("possibly-divergent", "unknown-behavior"),
                          direct_call("target", "helper", call_range=TARGET_RANGE)))
        self.assertEqual(result["status"], "recovered", result)
        self.assertEqual(result["call_obligations"][0]["declaration_id"], "unknown-behavior")
        self.assertEqual(result["participation"], "not_established")
        self.assertFalse(result["checked"])

    def test_prefix_depth_budget_is_unknown(self):
        expression = {"kind": "IntegerLiteral", "value": "0", "inner": []}
        for _ in range(65):
            expression = {"kind": "ParenExpr", "inner": [expression]}
        tree = root(declaration("deep", expression),
                    direct_call("target", "helper", call_range=TARGET_RANGE))
        self.assertEqual(run(tree)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
