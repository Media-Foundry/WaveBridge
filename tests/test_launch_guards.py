import unittest

from wavebridge.analysis.launch_guards import recover


T = {"qualType": "int"}
CT = {"qualType": "const int"}


def ref(identifier):
    return {"kind": "ImplicitCastExpr", "castKind": "LValueToRValue", "type": T,
            "inner": [{"kind": "DeclRefExpr", "type": CT,
                       "referencedDecl": {"kind": "VarDecl", "id": identifier}}]}


def lit(value):
    return {"kind": "IntegerLiteral", "value": str(value), "type": T}


def compare(identifier, opcode, value):
    return {"kind": "BinaryOperator", "opcode": opcode, "inner": [ref(identifier), lit(value)]}


def guard(condition, has_else=False):
    node = {"kind": "IfStmt", "inner": [condition,
            {"kind": "ReturnStmt", "inner": [lit(3)]}], "range": {"begin": 10}}
    if has_else:
        node["hasElse"] = True
    return node


def decl(identifier, const=True):
    return {"kind": "DeclStmt", "inner": [{"kind": "VarDecl", "id": identifier,
            "type": CT if const else T, "range": {"begin": identifier}, "init": "c",
            "inner": [lit(0)]}]}


def launch(identifier="launch"):
    return {"kind": "CUDAKernelCallExpr", "id": identifier}


def function(statements):
    return {"kind": "TranslationUnitDecl", "inner": [{"kind": "FunctionDecl", "id": "host",
            "inner": [{"kind": "CompoundStmt", "inner": statements}]}]}


class LaunchGuardTests(unittest.TestCase):
    def test_recovers_renamed_intervals_from_or_guard(self):
        condition = {"kind": "BinaryOperator", "opcode": "||", "inner": [
            compare("rows", "<", 1),
            {"kind": "BinaryOperator", "opcode": "||", "inner": [
                compare("rows", ">", 8), compare("columns", ">=", 1024)]}]}
        report = recover(function([decl("rows"), decl("columns"), guard(condition), launch()]),
                         "launch", 32)
        self.assertEqual("recovered", report["status"])
        by_id = {item["declaration_id"]: item for item in report["intervals"]}
        self.assertEqual((1, 8), (by_id["rows"]["lower"], by_id["rows"]["upper"]))
        self.assertEqual(1023, by_id["columns"]["upper"])
        self.assertFalse(report["checked"])

    def test_accepts_only_zero_condition_do_launch_wrapper(self):
        wrapped = {"kind": "DoStmt", "inner": [
            {"kind": "CompoundStmt", "inner": [launch()]},
            {"kind": "ImplicitCastExpr", "castKind": "IntegralToBoolean",
             "inner": [lit(0)]}]}
        report = recover(function([decl("x"), guard(compare("x", "<", 0)), wrapped]),
                         "launch", 32)
        self.assertEqual("recovered", report["status"])
        wrapped["inner"][1]["inner"][0]["value"] = "1"
        self.assertEqual("unique_top_level_launch_not_found",
                         recover(function([decl("x"), guard(compare("x", "<", 0)), wrapped]),
                                 "launch", 32)["reason"])

    def test_accepts_void_early_return(self):
        void_guard = {"kind": "IfStmt", "inner": [compare("x", "<", 1),
                                                     {"kind": "ReturnStmt"}]}
        report = recover(function([decl("x"), void_guard, launch()]), "launch", 32)
        self.assertEqual("recovered", report["status"])

    def test_rejects_mutable_else_nested_and_crossing_control(self):
        mutable = recover(function([decl("x", False), guard(compare("x", "<", 1)), launch()]),
                          "launch", 32)
        self.assertEqual("no_supported_guard", mutable["reason"])
        with_else = recover(function([decl("x"), guard(compare("x", "<", 1), True), launch()]),
                            "launch", 32)
        self.assertEqual("no_supported_guard", with_else["reason"])
        nested = {"kind": "IfStmt", "inner": [lit(1), launch()]}
        self.assertEqual("unique_top_level_launch_not_found",
            recover(function([decl("x"), guard(compare("x", "<", 1)), nested]),
                    "launch", 32)["reason"])
        switch = {"kind": "SwitchStmt", "inner": []}
        self.assertEqual("bypassing_control_flow_unsupported",
            recover(function([decl("x"), guard(compare("x", "<", 1)), switch, launch()]),
                    "launch", 32)["reason"])

    def test_rejects_writes_escape_bad_boundary_and_overflow(self):
        write = {"kind": "BinaryOperator", "opcode": "=", "inner": [
            {"kind": "DeclRefExpr", "type": CT,
             "referencedDecl": {"kind": "VarDecl", "id": "x"}}, lit(2)]}
        tree = function([decl("x"), guard(compare("x", "<", 1)), launch(), write])
        self.assertEqual("guard_variable_has_unsupported_use", recover(tree, "launch", 32)["reason"])
        bad = compare("x", "<", 1)
        bad["inner"][1]["type"] = {"qualType": "unsigned int"}
        bad_report = recover(function([decl("x"), guard(bad), launch()]), "launch", 32)
        self.assertEqual("no_supported_guard", bad_report["reason"])
        self.assertEqual("complement_boundary_overflow",
            recover(function([decl("x"), guard(compare("x", "<=", 2147483647)), launch()]),
                    "launch", 32)["reason"])

    def test_rejects_duplicate_launch_and_invalid_inputs(self):
        tree = function([decl("x"), guard(compare("x", "<", 1)), launch(), launch()])
        self.assertEqual("unique_top_level_launch_not_found", recover(tree, "launch", 32)["reason"])
        self.assertEqual("invalid_input", recover([], "launch", 32)["reason"])
        self.assertEqual("invalid_int_bits", recover({}, "launch", True)["reason"])

    def test_all_comparisons_and_reversed_operands_match_integer_complements(self):
        operations = {
            "<": lambda value: value < 1, "<=": lambda value: value <= 1,
            ">": lambda value: value > 1, ">=": lambda value: value >= 1,
        }
        reverse = {"<": ">", "<=": ">=", ">": "<", ">=": "<="}
        for opcode, bad in operations.items():
            for reversed_operands in (False, True):
                expression = compare("x", opcode, 1)
                if reversed_operands:
                    expression["opcode"] = reverse[opcode]
                    expression["inner"].reverse()
                report = recover(function([decl("x"), guard(expression), launch()]), "launch", 4)
                self.assertEqual("recovered", report["status"], (opcode, reversed_operands, report))
                interval = report["intervals"][0]
                represented = {value for value in range(-8, 8)
                               if (interval["lower"] is None or value >= interval["lower"]) and
                               (interval["upper"] is None or value <= interval["upper"])}
                self.assertEqual({value for value in range(-8, 8) if not bad(value)}, represented)

    def test_skips_unrelated_if_and_allows_ordinary_expression(self):
        unrelated = {"kind": "IfStmt", "inner": [
            {"kind": "CallExpr", "inner": []}, {"kind": "ReturnStmt"}]}
        call = {"kind": "CallExpr", "inner": []}
        report = recover(function([decl("x"), unrelated, call,
                                   guard(compare("x", "<", 1)), launch()]), "launch", 32)
        self.assertEqual("recovered", report["status"])
        self.assertEqual("unsupported_guard_term", report["skipped_guards"][0]["reason"])

    def test_declaration_must_be_unique_initialized_automatic_and_before_guard(self):
        duplicate = function([decl("x"), decl("x"), guard(compare("x", "<", 1)), launch()])
        self.assertEqual("no_supported_guard", recover(duplicate, "launch", 32)["reason"])
        missing_init = decl("x")
        missing_init["inner"][0].pop("init")
        self.assertEqual("no_supported_guard",
            recover(function([missing_init, guard(compare("x", "<", 1)), launch()]),
                    "launch", 32)["reason"])
        static = decl("x")
        static["inner"][0]["storageClass"] = "static"
        self.assertEqual("no_supported_guard",
            recover(function([static, guard(compare("x", "<", 1)), launch()]),
                    "launch", 32)["reason"])
        self.assertEqual("no_supported_guard",
            recover(function([guard(compare("x", "<", 1)), decl("x"), launch()]),
                    "launch", 32)["reason"])


if __name__ == "__main__":
    unittest.main()
