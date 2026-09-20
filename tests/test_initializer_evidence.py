import unittest

from wavebridge.analysis.initializer_evidence import inspect


RANGE = {"begin": {"offset": 1}, "end": {"offset": 2}}


def function(function_id, name="renamed", body=None):
    inner = [] if body is None else [{"kind": "CompoundStmt", "inner": [
        {"kind": "ReturnStmt", "inner": [body]}]}]
    return {"id": function_id, "kind": "FunctionDecl", "name": name,
            "type": {"qualType": "int ()"}, "range": RANGE, "inner": inner}


def call(call_id, function_id, args=None):
    callee = {"kind": "DeclRefExpr", "referencedDecl": {
        "id": function_id, "kind": "FunctionDecl", "name": "any"}}
    return {"id": call_id, "kind": "CallExpr", "range": RANGE,
            "inner": [callee, *(args or [])]}


def variable(initializer, qual_type="const int", declaration_id="v"):
    return {"id": declaration_id, "kind": "VarDecl", "name": "arbitrary",
            "type": {"qualType": qual_type}, "init": "c", "range": RANGE,
            "inner": [initializer, {"kind": "CUDAConstantAttr"}]}


def root(initializer, qual_type="const int", declarations=None):
    return {"kind": "TranslationUnitDecl", "inner": [
        *(declarations or []), variable(initializer, qual_type)]}


class InitializerEvidenceTests(unittest.TestCase):
    def test_single_renamed_no_argument_call_is_evidence_not_value_equivalence(self):
        leaf = function("leaf")
        wrapper = function("wrapper", body=call("nested", "leaf"))
        result = inspect(root(call("origin", "wrapper"), declarations=[leaf, wrapper]), "v")
        self.assertEqual("evidence", result["status"])
        self.assertEqual("wrapper", result["calls"][0]["callee_declaration_id"])
        self.assertEqual("external_leaf", result["calls"][0]["trace"]["status"])
        self.assertEqual("not_established", result["value_equivalence"])
        self.assertEqual("unknown", result["start_semantics"])
        self.assertFalse(result["checked"])

    def test_pseudo_object_keeps_all_children_and_does_not_select_a_value(self):
        origin = call("origin", "getter")
        pseudo = {"kind": "PseudoObjectExpr", "range": RANGE, "inner": [
            {"kind": "MSPropertyRefExpr"}, {"kind": "OpaqueValueExpr"}, origin]}
        initializer = {"kind": "IntegralCast", "range": RANGE, "inner": [pseudo]}
        result = inspect(root(initializer, declarations=[function("getter")]), "v")
        self.assertEqual(initializer, result["initializer_ast"])
        self.assertEqual(1, len(result["calls"]))
        self.assertEqual("not_established", result["value_equivalence"])

    def test_arguments_and_member_receiver_remain_unknown_or_preserved(self):
        with_arg = call("c", "target", [{"kind": "IntegerLiteral", "value": "1"}])
        result = inspect(root(with_arg, declarations=[function("target")]), "v")
        self.assertEqual("unknown", result["status"])
        self.assertEqual("call_has_arguments", result["calls"][0]["reason"])
        member = {"id": "m", "kind": "CXXMemberCallExpr", "inner": [
            {"kind": "MemberExpr", "referencedMemberDecl": "method",
             "inner": [{"kind": "DeclRefExpr", "name": "receiver"}]}]}
        result = inspect(root(member, declarations=[
            {**function("method"), "kind": "CXXMethodDecl"}]), "v")
        self.assertEqual("evidence", result["calls"][0]["status"])
        self.assertTrue(result["calls"][0]["receiver_ast"])
        self.assertEqual("not_established", result["calls"][0]["receiver_purity"])

    def test_duplicate_call_id_is_deduplicated_but_multiple_calls_are_ambiguous(self):
        first = call("same", "a")
        duplicate = call("same", "a")
        initializer = {"kind": "InitListExpr", "inner": [first, duplicate]}
        result = inspect(root(initializer, declarations=[function("a")]), "v")
        self.assertEqual(1, len(result["calls"]))
        self.assertEqual("evidence", result["status"])
        initializer = {"kind": "InitListExpr", "inner": [call("a1", "a"), call("b1", "b")]}
        result = inspect(root(initializer, declarations=[function("a"), function("b")]), "v")
        self.assertEqual("unknown", result["status"])
        self.assertEqual("initializer_contains_multiple_calls", result["reason"])
        self.assertEqual(2, len(result["calls"]))

    def test_specialized_calls_are_counted_as_unknown_evidence(self):
        specialized = {"id": "special", "kind": "CXXOperatorCallExpr", "range": RANGE,
                       "inner": [call("nested", "a")]}
        result = inspect(root(specialized, declarations=[function("a")]), "v")
        self.assertEqual("unknown", result["status"])
        self.assertEqual(2, len(result["calls"]))
        self.assertEqual("unsupported_call_kind", result["calls"][0]["reason"])
        cuda = {"id": "launch", "kind": "CUDAKernelCallExpr", "range": RANGE, "inner": []}
        result = inspect(root(cuda), "v")
        self.assertEqual("unsupported_call_kind", result["calls"][0]["reason"])

    def test_no_call_mutable_volatile_and_missing_initializer_are_unknown(self):
        literal = {"kind": "IntegerLiteral", "value": "3"}
        self.assertEqual("initializer_contains_no_calls", inspect(root(literal), "v")["reason"])
        self.assertEqual("variable_not_const_nonvolatile", inspect(root(literal, "int"), "v")["reason"])
        self.assertEqual("variable_not_const_nonvolatile",
                         inspect(root(literal, "const volatile int"), "v")["reason"])
        self.assertEqual("unique_initialized_variable_not_found",
                         inspect({"kind": "TranslationUnitDecl", "inner": []}, "v")["reason"])


if __name__ == "__main__":
    unittest.main()
