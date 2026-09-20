import unittest

from wavebridge.analysis.column_loops import recover


RANGE = {"begin": {"offset": 1}, "end": {"offset": 2}}


def typed(kind, **fields):
    return {"kind": kind, "type": {"qualType": "int"}, "range": RANGE, **fields}


def ref(declaration_id, kind="VarDecl", name="renamed"):
    return typed("DeclRefExpr", referencedDecl={"id": declaration_id, "kind": kind, "name": name})


def literal(value):
    return typed("IntegerLiteral", value=str(value))


def var(declaration_id, initializer, name="anything", const=False):
    qual = "const int" if const else "int"
    return {"id": declaration_id, "kind": "VarDecl", "name": name, "type": {"qualType": qual},
            "init": "c", "range": RANGE, "inner": [initializer]}


def loop(step=32, induction_id="i", body=None, bound_id="limit", start_id="seed"):
    induction = var(induction_id, ref(start_id), name="not_col")
    condition = typed("BinaryOperator", opcode="<", inner=[ref(induction_id), ref(bound_id, "ParmVarDecl")])
    increment = typed("CompoundAssignOperator", opcode="+=", inner=[ref(induction_id), literal(step)])
    return {"kind": "ForStmt", "range": RANGE,
            "inner": [{"kind": "DeclStmt", "range": RANGE, "inner": [induction]}, {},
                      condition, increment, body or {"kind": "CompoundStmt", "range": RANGE, "inner": []}]}


def root_with(loop_node, extra=None, function_id="fn"):
    body = {"kind": "CompoundStmt", "range": RANGE, "inner": [loop_node]}
    function = {"id": function_id, "kind": "FunctionDecl", "name": "arbitrary",
                "range": RANGE, "inner": [body]}
    return {"kind": "TranslationUnitDecl", "inner": [*(extra or []), function]}


class ColumnLoopTests(unittest.TestCase):
    def test_missing_alias_type_evidence_never_means_value_storage(self):
        for info in ({"qualType": "Ref", "typeAliasDeclId": "alias"},
                     {"qualType": "Ref"}, {"qualType": "Ref", "desugaredQualType": "Other"}, {}):
            declaration = {"kind": "VarDecl", "id": "alias", "type": info,
                           "init": "c", "inner": [ref("i")]}
            body = {"kind": "CompoundStmt", "inner": [declaration]}
            self.assertEqual("unknown", recover(root_with(loop(body=body)), "fn", 32)["status"])
            target = ref("alias")
            target["referencedDecl"]["type"] = info
            body["inner"] = [typed("CompoundAssignOperator", opcode="+=", inner=[target, literal(1)])]
            self.assertEqual("unknown", recover(root_with(loop(body=body)), "fn", 32)["status"])

    def test_reference_storage_uses_declaration_not_expression_type(self):
        target = ref("alias")  # expression is int, declaration is a reference alias
        target["referencedDecl"]["type"] = {"qualType": "Ref", "desugaredQualType": "int &"}
        for update in (typed("CompoundAssignOperator", opcode="+=", inner=[target, literal(1)]),
                       typed("UnaryOperator", opcode="++", inner=[target])):
            body = {"kind": "CompoundStmt", "inner": [update]}
            self.assertEqual("unknown", recover(root_with(loop(body=body)), "fn", 32)["status"])

    def test_nonautomatic_induction_storage_is_unknown(self):
        for field, value in (("storageClass", "static"), ("storageClass", "extern"), ("tls", "dynamic")):
            candidate = loop()
            candidate["inner"][0]["inner"][0][field] = value
            report = recover(root_with(candidate), "fn", 32)
            self.assertEqual("induction_storage_not_automatic", report["loops"][0]["reason"])

    def test_complex_storage_targets_and_opaque_effects_fail_closed(self):
        for identifier in ("i", "limit", "seed"):
            for kind in ("CXXStaticCastExpr", "CStyleCastExpr"):
                target = typed(kind, castKind="NoOp", inner=[ref(identifier)])
                assignment = typed("CompoundAssignOperator", opcode="+=", inner=[target, literal(32)])
                result = recover(root_with(loop(body={"kind": "CompoundStmt", "inner": [assignment]})),
                                 "fn", 32)["loops"][0]
                self.assertEqual("unknown", result["status"])
                self.assertTrue(result["header_recurrence_observed"])
                self.assertEqual("not_established", result["body_preserves_induction"])
                self.assertEqual("not_established", result["body_preserves_bound"])
        for kind in ("GCCAsmStmt", "MSAsmStmt", "StmtExpr", "CXXConstructExpr", "FutureOpaqueExpr"):
            result = recover(root_with(loop(body={"kind": kind})), "fn", 32)
            self.assertEqual("unknown", result["status"])
            self.assertEqual("unsupported_body_effect", result["loops"][0]["reason"])

    def test_renamed_loop_and_step_change_are_recovered(self):
        result = recover(root_with(loop(8)), "fn", 32)
        self.assertEqual("recovered", result["status"])
        recovered = result["loops"][0]
        self.assertEqual("i", recovered["induction"]["declaration_id"])
        self.assertEqual("seed", recovered["start"]["declaration_id"])
        self.assertEqual("limit", recovered["bound"]["declaration_id"])
        self.assertEqual(8, recovered["step"])
        self.assertEqual("unproven", recovered["assumptions"]["memory_no_alias"])
        self.assertFalse(result["checked"])
        self.assertFalse(result["deployable"])

    def test_constant_step_and_bound_use_exact_ids(self):
        bound = var("bound-id", literal(100), const=True)
        stride = var("stride-id", literal(7), const=True)
        candidate = loop(bound_id="bound-id")
        candidate["inner"][2]["inner"][1] = ref("bound-id", "VarDecl")
        candidate["inner"][3]["inner"][1] = ref("stride-id")
        result = recover(root_with(candidate, [bound, stride]), "fn", 32)
        self.assertEqual("recovered", result["status"])
        self.assertEqual(100, result["loops"][0]["bound"]["value"])
        self.assertEqual(7, result["loops"][0]["step"])

    def test_same_name_different_id_does_not_join(self):
        stride = var("right-id", literal(4), name="same", const=True)
        candidate = loop()
        candidate["inner"][3]["inner"][1] = ref("wrong-id", name="same")
        result = recover(root_with(candidate, [stride]), "fn", 32)
        self.assertEqual("unknown", result["status"])
        self.assertEqual("step_not_resolved_signed_int_constant", result["loops"][0]["reason"])

    def test_body_modification_and_call_are_unknown(self):
        assignment = typed("BinaryOperator", opcode="=", inner=[ref("i"), literal(4)])
        result = recover(root_with(loop(body={"kind": "CompoundStmt", "inner": [assignment]})), "fn", 32)
        self.assertEqual("protected_variable_may_be_modified", result["loops"][0]["reason"])
        call = {"kind": "CallExpr", "range": RANGE, "inner": []}
        result = recover(root_with(loop(body={"kind": "CompoundStmt", "inner": [call]})), "fn", 32)
        self.assertEqual("call_in_body", result["loops"][0]["reason"])

    def test_index_read_comparison_nested_loop_and_reference_alias_boundaries(self):
        comparison = typed("BinaryOperator", opcode="<=", inner=[ref("i"), literal(10)])
        array_lvalue = {"kind": "ArraySubscriptExpr", "inner": [ref("output"), ref("i")]}
        store = typed("BinaryOperator", opcode="=", inner=[array_lvalue, comparison])
        accepted = recover(root_with(loop(body={"kind": "CompoundStmt", "inner": [store]})), "fn", 32)
        self.assertEqual("recovered", accepted["status"])
        nested = loop(body={"kind": "ForStmt", "range": RANGE, "inner": []})
        self.assertEqual("nested_loop_in_body", recover(root_with(nested), "fn", 32)["loops"][0]["reason"])
        alias = {"kind": "VarDecl", "type": {"qualType": "int &"}, "range": RANGE,
                 "init": "c", "inner": [ref("i")]}
        aliased = recover(root_with(loop(body={"kind": "CompoundStmt", "inner": [alias]})), "fn", 32)
        self.assertEqual("protected_variable_reference_alias", aliased["loops"][0]["reason"])

    def test_literal_range_and_unsupported_cast_are_unknown(self):
        candidate = loop(step=128)
        self.assertEqual("step_literal_out_of_range",
                         recover(root_with(candidate), "fn", 8)["loops"][0]["reason"])
        cast = typed("ImplicitCastExpr", castKind="IntegralCast", inner=[ref("seed")])
        candidate = loop()
        candidate["inner"][0]["inner"][0]["inner"] = [cast]
        self.assertEqual("unsupported_value_cast",
                         recover(root_with(candidate), "fn", 32)["loops"][0]["reason"])

    def test_unsupported_headers_and_wrong_function_are_unknown(self):
        candidate = loop()
        candidate["inner"][1] = {"kind": "NullStmt"}
        result = recover(root_with(candidate), "fn", 32)
        self.assertEqual("unsupported_for_header_slot", result["loops"][0]["reason"])
        self.assertEqual("function_unique_body_not_found", recover(root_with(loop()), "other", 32)["reason"])


if __name__ == "__main__":
    unittest.main()
