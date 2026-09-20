import copy
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.getter_returns import check


RANGE = {"begin": {"offset": 1}, "end": {"offset": 2}}
ABI = {
    "int": {"bits": 32, "signed": True},
    "unsigned int": {"bits": 32, "signed": False},
    "unsigned long": {"bits": 64, "signed": False},
    "unsigned char": {"bits": 8, "signed": False},
}


def literal(value=0, cast_type="unsigned int"):
    raw = {"kind": "IntegerLiteral", "value": str(value),
           "type": {"qualType": "int"}, "valueCategory": "prvalue", "range": RANGE}
    return {"kind": "ImplicitCastExpr", "castKind": "IntegralCast", "inner": [raw],
            "type": {"qualType": cast_type}, "valueCategory": "prvalue", "range": RANGE}


def call(node_id, target_id, target_name, arguments=(), return_type="unsigned long"):
    parameter_types = [argument.get("type", {}).get("qualType", "") for argument in arguments]
    signature = f"{return_type} ({', '.join(parameter_types)})"
    reference = {"kind": "DeclRefExpr", "referencedDecl": {
        "id": target_id, "kind": "FunctionDecl", "name": target_name},
        "type": {"qualType": signature}, "valueCategory": "lvalue", "range": RANGE}
    decay = {"kind": "ImplicitCastExpr", "castKind": "FunctionToPointerDecay",
             "inner": [reference], "type": {"qualType": signature.replace(" (", " (*)(", 1)},
             "valueCategory": "prvalue", "range": RANGE}
    return {"id": node_id, "kind": "CallExpr", "inner": [decay, *arguments],
            "type": {"qualType": return_type}, "valueCategory": "prvalue", "range": RANGE}


def returned(expression, target_type=None):
    if target_type is not None:
        expression = {"kind": "ImplicitCastExpr", "castKind": "IntegralCast",
                      "inner": [expression], "type": {"qualType": target_type},
                      "valueCategory": "prvalue", "range": RANGE}
    return {"kind": "CompoundStmt", "inner": [
        {"kind": "ReturnStmt", "inner": [expression], "range": RANGE}], "range": RANGE}


def function(node_id, name, expression=None, return_type="unsigned int", *,
             kind="FunctionDecl", static=False, parameters=()):
    inner = [{"kind": "ParmVarDecl", "id": f"{node_id}-p{i}",
              "type": {"qualType": parameter_type}}
             for i, parameter_type in enumerate(parameters)]
    if expression is not None:
        inner.append(returned(expression, return_type if expression["type"]["qualType"] != return_type
                              else None))
    result = {"id": node_id, "kind": kind, "name": name, "inner": inner,
              "type": {"qualType": f"{return_type} ({', '.join(parameters)})"}, "range": RANGE}
    if static:
        result["storageClass"] = "static"
    return result


def fixture(*, upper=255, start_type="unsigned int", leaf_argument=0):
    leaf = function("leaf", "external_index", return_type="unsigned long",
                    parameters=("unsigned int",))
    middle_call = call("leaf-call", "leaf", "external_index", [literal(leaf_argument)])
    middle = function("middle", "middle", middle_call, return_type=start_type)
    start_call = call("middle-call", "middle", "middle", return_type=start_type)
    start = function("start", "getter", start_call, return_type=start_type,
                     kind="CXXMethodDecl", static=True)
    root = {"kind": "TranslationUnitDecl", "inner": [start, middle, leaf]}
    contract = {
        "schema_version": "getter-leaf-domain/v1", "declaration_id": "leaf",
        "arguments": [0], "return_type": {"qualType": "unsigned long"},
        "lower": 0, "upper": upper,
    }
    return root, contract


class GetterReturnsTests(unittest.TestCase):
    def test_limits_malformed_children_and_nonfinite_inputs_remain_unknown(self):
        root, contract = fixture()
        with patch("wavebridge.verification.getter_returns.MAX_AST_NODES", 2):
            self.assertEqual(check(root, "start", contract, ABI)["status"], "unknown")
        with patch("wavebridge.verification.getter_returns.MAX_CALL_DEPTH", 1):
            self.assertEqual(check(root, "start", contract, ABI)["status"], "unknown")
        root["inner"][0]["inner"][-1]["inner"].append(None)
        self.assertEqual(check(root, "start", contract, ABI)["status"], "unknown")
        root, contract = fixture()
        contract["extra"] = float("nan")
        self.assertEqual(check(root, "start", contract, ABI)["reason"], "input_hash_unsupported")

    def test_expression_depth_and_real_function_cycle_remain_unknown(self):
        root, contract = fixture()
        start = root["inner"][0]
        start["kind"] = "FunctionDecl"
        root["inner"][1]["inner"][-1] = returned(call("cycle", "start", "renamed", return_type="unsigned int"))
        self.assertEqual(check(root, "start", contract, ABI)["reason"], "getter_cycle_or_depth_budget")
        root, contract = fixture()
        stmt = root["inner"][0]["inner"][-1]["inner"][0]
        expr = stmt["inner"][0]
        for _ in range(34):
            expr = {"kind": "ParenExpr", "type": {"qualType": "unsigned int"},
                    "valueCategory": "prvalue", "inner": [expr]}
        stmt["inner"] = [expr]
        self.assertEqual(check(root, "start", contract, ABI)["status"], "unknown")

    def test_nonstatic_start_and_argument_conversion_loss_remain_unknown(self):
        root, contract = fixture()
        root["inner"][0].pop("storageClass")
        self.assertEqual(check(root, "start", contract, ABI)["status"], "unknown")
        root, contract = fixture(leaf_argument=256)
        contract["arguments"] = [256]
        # An 8-bit assumed unsigned int cannot preserve literal 256 at the leaf call.
        abi = dict(ABI, **{"unsigned int": {"bits": 8, "signed": False}})
        self.assertEqual(check(root, "start", contract, abi)["status"], "unknown")

    def test_safe_chain_is_checked_with_bounded_evidence(self):
        root, contract = fixture()
        result = check(root, "start", contract, ABI)
        self.assertEqual(result["status"], "checked", result)
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        hashes = result.get("input_sha256")
        self.assertEqual(set(hashes), {"root", "start_declaration_id",
                                       "leaf_contract", "integer_types"})
        self.assertTrue(all(isinstance(value, str) and len(value) == 64
                            for value in hashes.values()))
        self.assertTrue(result.get("conversion_checks"))
        self.assertEqual(result["completion"], {
            "status": "conditional",
            "external_leaf_declaration_id": "leaf",
            "external_arguments": [0],
            "maximum_call_edges": 2,
            "premise": "valid calls and the exact external leaf returns normally",
        })

    def test_return_narrowing_outside_interval_is_rejected(self):
        root, contract = fixture(upper=256, start_type="unsigned char")
        result = check(root, "start", contract, ABI)
        self.assertEqual(result["status"], "rejected", result)
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        self.assertTrue(any(item.get("conversion", {}).get("status") == "rejected"
                            for item in result.get("conversion_checks", [])))
        self.assertNotIn("completion", result)

    def test_contract_mismatch_and_bad_structure_are_unknown(self):
        mutations = {}
        root, contract = fixture(leaf_argument=1)
        mutations["argument_mismatch"] = (root, contract, ABI)
        root, contract = fixture()
        root["inner"].append(copy.deepcopy(root["inner"][1]))
        mutations["duplicate_id"] = (root, contract, ABI)
        root, contract = fixture()
        body = root["inner"][1]["inner"][-1]["inner"]
        body.append({"kind": "NullStmt"})
        mutations["multiple_statements"] = (root, contract, ABI)
        root, contract = fixture()
        expression = root["inner"][1]["inner"][-1]["inner"][0]["inner"][0]
        root["inner"][1]["inner"][-1]["inner"][0]["inner"] = [
            {"kind": "BinaryOperator", "opcode": "+", "inner": [expression, literal(1)],
             "type": {"qualType": "unsigned int"}, "valueCategory": "prvalue"}]
        mutations["arithmetic"] = (root, contract, ABI)
        root, contract = fixture()
        root["inner"][1]["inner"][-1] = returned(
            call("cycle", "start", "getter", return_type="unsigned int"))
        mutations["cycle"] = (root, contract, ABI)
        root, contract = fixture()
        root["inner"][1]["inner"].insert(0, {
            "kind": "ParmVarDecl", "id": "middle-parameter",
            "type": {"qualType": "unsigned int"}})
        mutations["parameterized_internal_getter"] = (root, contract, ABI)
        root, contract = fixture()
        leaf_call = root["inner"][1]["inner"][-1]["inner"][0]["inner"][0]["inner"][0]
        leaf_call["inner"][0]["castKind"] = "BitCast"
        mutations["unsupported_callee_cast"] = (root, contract, ABI)
        root, contract = fixture()
        mutations["missing_abi"] = (root, contract, {"int": ABI["int"]})
        for name, (tree, leaf_contract, integer_types) in mutations.items():
            with self.subTest(name=name):
                result = check(tree, "start", leaf_contract, integer_types)
                self.assertEqual(result["status"], "unknown", result)
                self.assertNotIn("completion", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_contract_and_leaf_shape_validation_remain_unknown(self):
        cases = []
        root, contract = fixture()
        bad = copy.deepcopy(contract); bad["schema_version"] = "other/v1"
        cases.append((root, bad))
        root, contract = fixture()
        bad = copy.deepcopy(contract); bad["arguments"] = [-1]
        cases.append((root, bad))
        root, contract = fixture()
        bad = copy.deepcopy(contract); bad["return_type"] = {"qualType": "unsigned int"}
        cases.append((root, bad))
        root, contract = fixture()
        root["inner"][-1]["inner"].append(returned(literal(0)))
        cases.append((root, contract))
        root, contract = fixture()
        root["inner"][-1]["variadic"] = True
        cases.append((root, contract))
        for tree, leaf_contract in cases:
            with self.subTest(contract=leaf_contract):
                self.assertEqual(check(tree, "start", leaf_contract, ABI)["status"], "unknown")


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class GetterReturnsClangTests(unittest.TestCase):
    def test_real_clang_external_leaf_chain(self):
        report = collect(Path(__file__).parent / "fixtures/getter_returns.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "getter_entry",
                         full_translation_unit=True)
        self.assertEqual(report["status"], "collected", report.get("execution"))
        root = report["ast_roots"][0]
        declarations = {}
        for node in _walk(root):
            if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"} and node.get("name"):
                declarations.setdefault(node["name"], []).append(node)
        start = [node for node in declarations["getter_entry"] if any(
            child.get("kind") == "CompoundStmt" for child in node.get("inner", []))]
        leaf = declarations["external_index"]
        self.assertEqual(len(start), 1)
        self.assertEqual(len(leaf), 1)
        contract = {
            "schema_version": "getter-leaf-domain/v1", "declaration_id": leaf[0]["id"],
            "arguments": [0], "return_type": {"qualType": "unsigned long"},
            "lower": 0, "upper": 255,
        }
        result = check(root, start[0]["id"], contract, ABI)
        self.assertEqual(result["status"], "checked", result)
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])


if __name__ == "__main__":
    unittest.main()
