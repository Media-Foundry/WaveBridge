import copy
import unittest

from wavebridge.analysis.column_loops import recover


RANGE = {"begin": {"offset": 1}, "end": {"offset": 2}}


def typed(kind, ty, category, **fields):
    return {"kind": kind, "type": {"qualType": ty}, "valueCategory": category,
            "range": RANGE, **fields}


def ref(identifier, kind, ty="int"):
    return typed("DeclRefExpr", ty, "lvalue", referencedDecl={
        "id": identifier, "kind": kind, "type": {"qualType": ty}})


def pseudo(receiver_id, getter_id, prefix):
    source = ref(receiver_id, "VarDecl", "const builtin_t")
    receiver = typed("OpaqueValueExpr", "const builtin_t", "lvalue",
                     id=prefix + "-receiver", inner=[source])
    syntax = typed("MSPropertyRefExpr", "<pseudo-object type>", "lvalue",
                   inner=[receiver])
    member = typed("MemberExpr", "unsigned int ()", "lvalue", isArrow=False,
                   referencedMemberDecl=getter_id, inner=[receiver])
    decay = typed("ImplicitCastExpr", "unsigned int (*)()", "prvalue",
                  castKind="FunctionToPointerDecay", inner=[member])
    call = typed("CallExpr", "unsigned int", "prvalue", id=prefix + "-call",
                 inner=[decay])
    return typed("PseudoObjectExpr", "unsigned int", "prvalue", id=prefix + "-pseudo",
                 inner=[syntax, receiver, call])


def fixture():
    start = pseudo("thread-receiver", "thread-getter", "start")
    initializer = typed("ImplicitCastExpr", "int", "prvalue", castKind="IntegralCast",
                        inner=[start])
    induction = {"kind": "VarDecl", "id": "idx", "type": {"qualType": "int"},
                 "init": "c", "range": RANGE, "inner": [initializer]}
    condition = typed("BinaryOperator", "bool", "prvalue", opcode="<", inner=[
        ref("idx", "VarDecl"),
        typed("ImplicitCastExpr", "int", "prvalue", castKind="LValueToRValue",
              inner=[ref("count", "ParmVarDecl")])])
    increment = typed("CompoundAssignOperator", "int", "lvalue", opcode="+=",
                      computeLHSType={"qualType": "unsigned int"},
                      computeResultType={"qualType": "unsigned int"},
                      inner=[ref("idx", "VarDecl"),
                             pseudo("block-receiver", "block-getter", "step")])
    loop = {"kind": "ForStmt", "range": RANGE, "inner": [
        {"kind": "DeclStmt", "inner": [induction]}, {}, condition, increment,
        {"kind": "CompoundStmt", "inner": []}]}
    function = {"kind": "FunctionDecl", "id": "kernel", "inner": [
        {"kind": "CompoundStmt", "inner": [loop]}]}
    declarations = [
        {"kind": "CXXMethodDecl", "id": identifier, "storageClass": "static",
         "type": {"qualType": "unsigned int ()"}, "inner": []}
        for identifier in ("thread-getter", "block-getter")]
    root = {"kind": "TranslationUnitDecl", "inner": [*declarations, function]}
    return root, loop


class CoordinateHeaderObservationTests(unittest.TestCase):
    def test_exact_coordinate_header_is_observed_but_never_recovered(self):
        root, loop = fixture()
        report = recover(root, "kernel", 32)
        self.assertEqual(report["status"], "unknown", report)
        item = report["loops"][0]
        self.assertEqual(item["reason"], "unsupported_value_wrapper")
        self.assertIs(item["initializer_ast"], loop["inner"][0]["inner"][0]["inner"][0])
        self.assertIs(item["increment_ast"], loop["inner"][3])
        observation = item["coordinate_header_observation"]
        self.assertEqual(observation["status"], "observed", observation)
        self.assertEqual(observation["bound_parameter_id"], "count")
        self.assertEqual(observation["start_value_link"]["callee_declaration_id"],
                         "thread-getter")
        self.assertEqual(observation["step_value_link"]["callee_declaration_id"],
                         "block-getter")
        self.assertIsNone(item["step"])
        self.assertFalse(item["header_recurrence_observed"])
        self.assertEqual(item["body_preserves_induction"], "not_established")
        self.assertFalse(observation["recurrence_checked"])
        self.assertFalse(observation["launch_configuration_bound"])
        self.assertFalse(observation["integer_abi_checked"])

    def test_wrong_compute_types_bound_or_receiver_do_not_observe(self):
        mutations = []
        root, loop = fixture()
        loop["inner"][3]["computeResultType"] = {"qualType": "int"}
        mutations.append((root, "coordinate_increment_shape_unsupported"))
        root, loop = fixture()
        bound = loop["inner"][2]["inner"][1]["inner"][0]
        bound["referencedDecl"]["kind"] = "VarDecl"
        mutations.append((root, "coordinate_condition_binding_mismatch"))
        root, loop = fixture()
        step = loop["inner"][3]["inner"][1]
        wrong_receiver = copy.deepcopy(step["inner"][1])
        wrong_receiver["inner"][0]["referencedDecl"]["id"] = "other-receiver"
        step["inner"][0]["inner"] = [wrong_receiver]
        mutations.append((root, "coordinate_step_value_link_not_recovered"))
        for root, reason in mutations:
            with self.subTest(reason=reason):
                item = recover(root, "kernel", 32)["loops"][0]
                observation = item["coordinate_header_observation"]
                self.assertEqual(observation["status"], "unknown", observation)
                self.assertEqual(observation["reason"], reason)
                self.assertFalse(item["header_recurrence_observed"])
                self.assertIsNone(item["step"])

    def test_extra_initializer_cast_and_nonstatic_getter_are_not_observed(self):
        root, loop = fixture()
        original = loop["inner"][0]["inner"][0]["inner"][0]
        loop["inner"][0]["inner"][0]["inner"] = [
            typed("ImplicitCastExpr", "int", "prvalue", castKind="IntegralCast",
                  inner=[original])]
        item = recover(root, "kernel", 32)["loops"][0]
        self.assertEqual(item["coordinate_header_observation"]["status"], "unknown")

        root, _ = fixture()
        root["inner"][0].pop("storageClass")
        observation = recover(root, "kernel", 32)["loops"][0]["coordinate_header_observation"]
        self.assertEqual(observation["status"], "unknown", observation)
        self.assertEqual(observation["reason"], "coordinate_start_value_link_not_recovered")


if __name__ == "__main__":
    unittest.main()
