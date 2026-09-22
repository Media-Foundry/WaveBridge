"""Traversal/budget unit tests; mocked property effects are not source evidence."""
import unittest
from unittest.mock import patch

from wavebridge.analysis.column_loops import _Unknown, _check_body
from wavebridge.verification.column_body import check
from wavebridge.verification.getter_returns import _hash
from tests.test_coordinate_header import fixture as coordinate_fixture
from tests.test_getter_returns import ABI


def inputs(property_count=1):
    root, loop = coordinate_fixture()
    loop["id"] = "loop"
    function = next(node for node in root["inner"]
                    if node.get("kind") == "FunctionDecl" and node.get("id") == "kernel")
    function["inner"].insert(0, {
        "kind": "ParmVarDecl", "id": "count", "type": {"qualType": "int"}, "inner": [],
    })
    for identifier in ("thread-receiver", "block-receiver"):
        root["inner"].append({
            "kind": "VarDecl", "id": identifier, "storageClass": "extern",
            "type": {"qualType": "const builtin_t"}, "inner": [],
        })
    expressions = [{"kind": "PseudoObjectExpr", "id": f"property-{index}", "inner": []}
                   for index in range(property_count)]
    loop["inner"][-1]["inner"] = expressions
    protocols = {
        expression["id"]: {
            "leaf_contract": {}, "effect_protocol": {}, "receiver_protocol": {},
        }
        for expression in expressions
    }
    binding = {
        "schema_version": "column-body-assumptions/v1",
        "root_sha256": _hash(root), "function_id": "kernel", "loop_id": "loop",
        "source_validity_assumed": True,
        "no_alias_with_protected_declarations_assumed": True,
        "evidence_reference": "unit-test-only assumptions",
    }
    return root, protocols, binding


def checked_property(*args, **kwargs):
    expression_id = args[1]
    return {
        "status": "checked",
        "conclusion": {"property": "no_memory_write", "expression_id": expression_id},
    }


class ColumnBodyUnitTests(unittest.TestCase):
    def test_private_callback_requires_literal_true_and_default_still_rejects(self):
        body = {"kind": "CompoundStmt", "inner": [
            {"kind": "PseudoObjectExpr", "id": "property", "inner": [
                {"kind": "CallExpr", "inner": []}]}]}
        with self.assertRaises(_Unknown):
            _check_body(body, set())
        for value in (False, None, 1, {}, "checked"):
            with self.subTest(value=value), self.assertRaises(_Unknown):
                _check_body(body, set(), property_callback=lambda node, value=value: value)
        _check_body(body, set(), property_callback=lambda node: True)

    @patch("wavebridge.verification.column_body.check_property_no_memory_write",
           side_effect=checked_property)
    def test_eight_properties_are_consumed_but_empty_and_nine_are_rejected(self, mocked):
        root, protocols, binding = inputs(8)
        result = check(root, "kernel", "loop", ABI, protocols, binding)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(set(result["property_checks"]), set(protocols))
        self.assertEqual(mocked.call_count, 8)

        root, _, binding = inputs(0)
        self.assertEqual(check(root, "kernel", "loop", ABI, {}, binding)["status"], "unknown")
        root, protocols, binding = inputs(9)
        self.assertEqual(check(root, "kernel", "loop", ABI, protocols, binding)["status"], "unknown")

    @patch("wavebridge.verification.column_body.check_property_no_memory_write",
           side_effect=checked_property)
    def test_same_function_id_on_another_node_is_fail_closed(self, mocked):
        root, protocols, binding = inputs()
        root["inner"].append({"kind": "VarDecl", "id": "kernel", "inner": []})
        binding["root_sha256"] = _hash(root)
        result = check(root, "kernel", "loop", ABI, protocols, binding)
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["reason"], "function_declaration_not_unique")
        mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
