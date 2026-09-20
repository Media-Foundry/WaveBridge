import unittest

from wavebridge.analysis.local_contribution import recover


R = {"begin": {"offset": 1}, "end": {"offset": 2}}


def ref(identifier, kind="VarDecl", declared_type="int"):
    return {"kind": "DeclRefExpr", "range": R, "type": {"qualType": "int"},
            "referencedDecl": {"id": identifier, "kind": kind,
                               "type": {"qualType": declared_type}}}


def lit_int(value):
    return {"kind": "IntegerLiteral", "value": str(value), "type": {"qualType": "int"}, "range": R}


def var(identifier, qual_type, initializer=None):
    node = {"id": identifier, "kind": "VarDecl", "type": {"qualType": qual_type}, "range": R}
    if initializer is not None:
        node.update(init="c", inner=[initializer])
    return node


def fixture(product_right="v", zero="0.0", index="col", extra_loop_statement=None):
    input_parameter = {"id": "input", "kind": "ParmVarDecl", "type": {"qualType": "const float *"}}
    bound_parameter = {"id": "bound", "kind": "ParmVarDecl", "type": {"qualType": "int"}}
    start = var("start", "const int", lit_int(0))
    accumulator = var("sum", "float", {"kind": "FloatingLiteral", "value": zero})
    induction = var("col", "int", ref("start"))
    init = {"kind": "DeclStmt", "inner": [induction]}
    condition = {"kind": "BinaryOperator", "opcode": "<", "inner": [ref("col"), ref("bound", "ParmVarDecl")]}
    increment = {"kind": "CompoundAssignOperator", "opcode": "+=", "inner": [ref("col"), lit_int(4)]}
    load = {"kind": "ArraySubscriptExpr", "inner": [ref("input", "ParmVarDecl"), ref(index)]}
    value = {"kind": "DeclStmt", "inner": [var("v", "const float", load)]}
    product = {"kind": "BinaryOperator", "opcode": "*", "inner": [ref("v"), ref(product_right)]}
    update = {"kind": "CompoundAssignOperator", "opcode": "+=",
              "inner": [ref("sum", declared_type="float"), product]}
    loop_body = {"kind": "CompoundStmt", "inner": [value, update] + ([extra_loop_statement] if extra_loop_statement else [])}
    loop = {"kind": "ForStmt", "range": R, "inner": [init, {}, condition, increment, loop_body]}
    shared = {"kind": "DeclStmt", "inner": [var("shared", "float[8]")]}
    call = {"kind": "CallExpr", "range": R, "inner": [ref("consume", "FunctionDecl"),
                                                           ref("sum"), ref("shared")]}
    total = {"kind": "DeclStmt", "range": R, "inner": [var("total", "const float", call)]}
    function = {"id": "kernel", "kind": "FunctionDecl", "range": R,
                "inner": [input_parameter, bound_parameter, {"kind": "CompoundStmt", "range": R,
                          "inner": [{"kind": "DeclStmt", "inner": [accumulator]}, loop, shared, total]}]}
    return {"kind": "TranslationUnitDecl", "inner": [start,
            {"id": "consume", "kind": "FunctionDecl"}, function]}


class LocalContributionTests(unittest.TestCase):
    def test_recovers_sum_of_squares_and_consumer(self):
        result = recover(fixture(), "kernel", 32)
        self.assertEqual("recovered", result["status"])
        self.assertEqual("sum", result["accumulator_declaration_id"])
        self.assertEqual("input", result["input_parameter_id"])
        self.assertEqual("consume", result["consumer"]["callee_declaration_id"])
        self.assertEqual(0, result["consumer"]["argument_index"])
        self.assertEqual(4, result["loop_recurrence"]["step"])
        self.assertFalse(result["checked"])

    def test_nonzero_and_different_product_are_unknown(self):
        self.assertEqual("accumulator_not_initialized_to_float_zero",
                         recover(fixture(zero="1.0"), "kernel", 32)["reason"])
        self.assertEqual("multiplication_not_same_loaded_value",
                         recover(fixture(product_right="other"), "kernel", 32)["reason"])

    def test_wrong_index_and_extra_update_are_unknown(self):
        self.assertEqual("load_index_not_induction",
                         recover(fixture(index="other"), "kernel", 32)["reason"])
        extra = {"kind": "CompoundAssignOperator", "opcode": "+=", "inner": [ref("sum"), ref("v")]}
        self.assertEqual("loop_body_not_exactly_load_and_accumulate",
                         recover(fixture(extra_loop_statement=extra), "kernel", 32)["reason"])

    def test_call_or_initialized_declaration_before_consumer_is_unknown(self):
        tree = fixture()
        statements = tree["inner"][-1]["inner"][-1]["inner"]
        statements.insert(2, {"kind": "CallExpr", "inner": [ref("other", "FunctionDecl")]})
        self.assertEqual("consumer_must_use_accumulator_once", recover(tree, "kernel", 32)["reason"])
        tree = fixture()
        statements = tree["inner"][-1]["inner"][-1]["inner"]
        statements[2] = {"kind": "DeclStmt", "inner": [var("shared", "float[8]", lit_int(0))]}
        self.assertEqual("statement_before_consumer_not_uninitialized_shared_array",
                         recover(tree, "kernel", 32)["reason"])

    def test_hidden_loop_and_missing_consumer_are_unknown(self):
        tree = fixture()
        statements = tree["inner"][-1]["inner"][-1]["inner"]
        statements.insert(2, {"kind": "WhileStmt", "inner": []})
        self.assertEqual("statement_before_consumer_not_shared_array_declaration",
                         recover(tree, "kernel", 32)["reason"])
        tree = fixture()
        tree["inner"][-1]["inner"][-1]["inner"].pop()
        self.assertEqual("accumulator_consumer_not_found", recover(tree, "kernel", 32)["reason"])

    def test_prefix_is_skipped_but_explicitly_not_analyzed(self):
        tree = fixture()
        statements = tree["inner"][-1]["inner"][-1]["inner"]
        statements.insert(0, {"kind": "BinaryOperator", "opcode": "+=", "range": R,
                              "inner": [ref("input", "ParmVarDecl"), lit_int(1)]})
        result = recover(tree, "kernel", 32)
        self.assertEqual("recovered", result["status"])
        self.assertEqual("not_analyzed", result["prefix_scope"])
        self.assertEqual([R], result["prefix_statement_ranges"])

    def test_pointer_type_nested_consumer_and_side_effect_argument_are_unknown(self):
        tree = fixture()
        tree["inner"][-1]["inner"][0]["type"]["qualType"] = "volatile float *"
        self.assertEqual("input_not_float_pointer_parameter", recover(tree, "kernel", 32)["reason"])
        tree = fixture()
        statements = tree["inner"][-1]["inner"][-1]["inner"]
        statements[-1] = {"kind": "IfStmt", "inner": [lit_int(1), statements[-1]]}
        self.assertEqual("non_direct_or_nested_call_before_consumer", recover(tree, "kernel", 32)["reason"])
        tree = fixture()
        call_node = tree["inner"][-1]["inner"][-1]["inner"][-1]["inner"][0]["inner"][0]
        call_node["inner"][2] = {"kind": "UnaryOperator", "opcode": "++", "inner": [ref("shared")]}
        self.assertEqual("consumer_other_argument_may_have_side_effects",
                         recover(tree, "kernel", 32)["reason"])


if __name__ == "__main__":
    unittest.main()
