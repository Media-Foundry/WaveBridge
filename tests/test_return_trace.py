import copy
import unittest

from wavebridge.analysis.return_trace import trace


def function(node_id, name, return_expr=None, params=0, body_extra=None):
    inner = [{"id": f"p{i}", "kind": "ParmVarDecl"} for i in range(params)]
    if return_expr is not None:
        statements = [{"kind": "ReturnStmt", "range": {}, "inner": [return_expr]}]
        statements.extend(body_extra or [])
        inner.append({"kind": "CompoundStmt", "range": {}, "inner": statements})
    return {"id": node_id, "kind": "FunctionDecl", "name": name,
            "type": {"qualType": "unsigned int ()"}, "range": {}, "inner": inner}


def direct_call(node_id, target_id, target_name, args=None):
    callee = {"id": node_id + "r", "kind": "DeclRefExpr", "range": {},
              "referencedDecl": {"id": target_id, "kind": "FunctionDecl", "name": target_name}}
    return {"id": node_id, "kind": "CallExpr", "range": {}, "inner": [callee, *(args or [])]}


def root(*nodes): return {"kind": "TranslationUnitDecl", "inner": list(nodes)}


class ReturnTraceTests(unittest.TestCase):
    def test_no_argument_chain_reaches_external_leaf_and_records_cast(self):
        leaf = function("leaf", "external")
        call = direct_call("call", "leaf", "external")
        cast = {"kind": "ImplicitCastExpr", "castKind": "IntegralCast",
                "type": {"qualType": "unsigned int"}, "range": {"begin": {}, "end": {}},
                "inner": [call]}
        getter = function("getter", "renamed_getter", cast)
        result = trace(root(getter, leaf), "getter")
        self.assertEqual(result["status"], "external_leaf")
        self.assertEqual(result["leaf"]["name"], "external")
        self.assertEqual(result["steps"][0]["return_casts"][0]["cast_kind"], "IntegralCast")
        self.assertEqual(result["steps"][0]["return_expression_ast"], cast)
        self.assertEqual(result["steps"][0]["callee_expression_ast"], call["inner"][0])
        self.assertEqual(result["semantic_interpretation"], "not_established")

    def test_duplicate_start_intermediate_and_leaf_ids_are_unknown(self):
        getter = function("getter", "getter", direct_call("c", "middle", "middle"))
        middle = function("middle", "middle", direct_call("c2", "leaf", "leaf"))
        leaf = function("leaf", "leaf")
        for duplicate in (getter, middle, leaf):
            for first in (True, False):
                with self.subTest(duplicate=duplicate["id"], first=first):
                    nodes = [getter, middle, leaf]
                    nodes.insert(0 if first else len(nodes), copy.deepcopy(duplicate))
                    result = trace(root(*nodes), "getter")
                    self.assertEqual(result["status"], "unknown")
                    self.assertEqual(result["reason"], "callee_declaration_ambiguous")
                    self.assertFalse(result["checked"])

    def test_intermediate_member_receiver_and_static_declaration_are_preserved(self):
        receiver = {"kind": "DeclRefExpr", "referencedDecl": {"id": "obj", "kind": "VarDecl"}}
        member = {"kind": "MemberExpr", "referencedMemberDecl": "method", "inner": [receiver]}
        call = {"kind": "CallExpr", "type": {"qualType": "unsigned int"}, "inner": [member]}
        method = function("method", "method", direct_call("c2", "leaf", "leaf"))
        method.update(kind="CXXMethodDecl", storageClass="static")
        result = trace(root(function("getter", "getter", call), method, function("leaf", "leaf")), "getter")
        self.assertEqual(result["status"], "external_leaf")
        self.assertEqual(result["steps"][0]["member_receiver_ast"], [receiver])
        self.assertEqual(result["steps"][0]["receiver_purity"], "not_established")
        self.assertEqual(result["steps"][0]["call_type"], "unsigned int")
        self.assertEqual(result["steps"][1]["storage_class"], "static")
        self.assertEqual(result["steps"][1]["declaration_kind"], "CXXMethodDecl")
        self.assertEqual(result["semantic_interpretation"], "not_established")

    def test_conflicting_same_id_body_and_declaration_do_not_depend_on_order(self):
        getter = function("getter", "getter", direct_call("c", "target", "target"))
        declaration = function("target", "target")
        definition = function("target", "target", {"kind": "IntegerLiteral", "value": "9"})
        for nodes in ((declaration, definition), (definition, declaration)):
            result = trace(root(getter, *nodes), "getter")
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(result["reason"], "callee_declaration_ambiguous")

    def test_defined_callee_with_parameters_is_unknown(self):
        getter = function("getter", "getter", direct_call("c", "target", "target"))
        target = function("target", "target", direct_call("c2", "leaf", "leaf"), params=1)
        leaf = function("leaf", "leaf")
        self.assertEqual(trace(root(getter, target, leaf), "getter")["reason"],
                         "defined_callee_has_parameters")

    def test_defined_callee_with_arguments_or_unsupported_body_is_unknown(self):
        argument = {"kind": "IntegerLiteral", "value": "1"}
        getter = function("getter", "getter", direct_call("c", "target", "target", [argument]))
        target = function("target", "target", direct_call("c2", "leaf", "leaf"))
        leaf = function("leaf", "leaf")
        self.assertEqual(trace(root(getter, target, leaf), "getter")["reason"],
                         "defined_callee_call_has_arguments")
        try_body = function("try", "try")
        try_body["inner"].append({"kind": "CXXTryStmt", "range": {}})
        self.assertEqual(trace(root(try_body), "try")["reason"], "unsupported_body")

    def test_external_leaf_preserves_complete_arguments(self):
        argument = {"id": "arg", "kind": "BinaryOperator", "opcode": "+", "range": {},
                    "inner": [{"kind": "IntegerLiteral", "value": "1"},
                              {"kind": "IntegerLiteral", "value": "2"}]}
        getter = function("getter", "getter", direct_call("c", "leaf", "leaf", [argument]))
        result = trace(root(getter, function("leaf", "leaf")), "getter")
        self.assertEqual(result["leaf"]["arguments"], [argument])

    def test_member_call_is_evidence_without_receiver_purity(self):
        member = {"id": "m", "kind": "MemberExpr", "referencedMemberDecl": "method",
                  "range": {}, "inner": [{"kind": "DeclRefExpr", "referencedDecl":
                                           {"id": "obj", "kind": "VarDecl"}}]}
        call = {"id": "c", "kind": "CXXMemberCallExpr", "range": {}, "inner": [member]}
        method = function("method", "method"); method["kind"] = "CXXMethodDecl"
        result = trace(root(function("getter", "getter", call), method), "getter")
        self.assertEqual(result["steps"][0]["receiver_purity"], "not_established")
        self.assertEqual(result["leaf"]["member_receiver_ast"], member["inner"])

    def test_cycle_missing_multistatement_arithmetic_and_depth_are_unknown(self):
        cycle_a = function("a", "a", direct_call("ca", "b", "b"))
        cycle_b = function("b", "b", direct_call("cb", "a", "a"))
        missing = function("missing_getter", "missing_getter", direct_call("cm", "absent", "absent"))
        arithmetic = function("arith", "arith", {"kind": "BinaryOperator", "opcode": "+"})
        multi = function("multi", "multi", direct_call("cx", "leaf", "leaf"),
                         body_extra=[{"kind": "NullStmt"}])
        leaf = function("leaf", "leaf")
        deep_middle = function("middle", "middle", direct_call("cd2", "leaf", "leaf"))
        deep_start = function("deep", "deep", direct_call("cd", "middle", "middle"))
        cases = [(root(cycle_a, cycle_b), "a", 16, "call_cycle"),
                 (root(missing), "missing_getter", 16, "callee_definition_missing"),
                 (root(arithmetic), "arith", 16, "return_expression_not_call"),
                 (root(multi, leaf), "multi", 16, "body_not_single_return"),
                 (root(deep_start, deep_middle, leaf),
                  "deep", 1, "max_depth_exceeded")]
        for tree, declaration_id, depth, reason in cases:
            with self.subTest(reason=reason):
                self.assertEqual(trace(tree, declaration_id, depth)["reason"], reason)

    def test_invalid_start_or_depth_is_unknown(self):
        self.assertEqual(trace({}, "missing")["reason"], "callee_definition_missing")
        self.assertEqual(trace(root(), "missing", 0)["reason"], "invalid_max_depth")
        self.assertEqual(trace(root(function("leaf", "leaf")), "leaf")["reason"],
                         "start_definition_has_no_body")


if __name__ == "__main__": unittest.main()
