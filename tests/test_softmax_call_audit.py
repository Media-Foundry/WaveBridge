"""Inventory fixtures do not establish call effects or workload coverage."""
import unittest
import json
import tempfile
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch

from experiments.softmax_call_audit import inventory, run_native, HIP_NATIVE_SHA


def function(identifier, *statements, kind="FunctionDecl", name="same"):
    return {"kind": kind, "id": identifier, "name": name, "storageClass": "static",
            "inner": [{"kind": "CompoundStmt", "inner": list(statements)}]}


def call(identifier, kind="FunctionDecl"):
    return {"kind": "CallExpr", "inner": [{"kind": "DeclRefExpr",
            "referencedDecl": {"id": identifier, "kind": kind}}]}


class SoftmaxCallAuditTests(unittest.TestCase):
    def test_identical_repeats_are_opt_in_observations_not_checker_success(self):
        declaration = function("entry", call("leaf"))
        root = {"inner": [declaration, {"kind": "UsingShadowDecl", "inner": [deepcopy(declaration)]}]}
        frozen = deepcopy(root)
        self.assertEqual(inventory(root, "entry")["edges"], [])
        result = inventory(root, "entry", observe_identical_repeats=True)
        item = result["functions"][0]
        self.assertEqual(item["definition_count"], 2)
        self.assertTrue(item["all_declaration_occurrences_identical"])
        self.assertTrue(item["repeated_definition_traversed"])
        self.assertEqual(len(result["edges"]), 1)
        self.assertFalse(result["edges"][0]["effects_checked"])
        self.assertFalse(result["source_program_checked"])
        self.assertEqual(root, frozen)

    def test_same_body_with_conflicting_declaration_metadata_is_not_traversed(self):
        declaration = function("entry", call("leaf"))
        conflict = deepcopy(declaration)
        conflict["storageClass"] = "extern"
        result = inventory({"inner": [declaration, conflict]}, "entry", observe_identical_repeats=True)
        self.assertFalse(result["functions"][0]["all_declaration_occurrences_identical"])
        self.assertEqual(result["edges"], [])

    def test_native_input_mismatch_rejected_before_loading_or_output(self):
        with patch("experiments.softmax_call_audit.sha", return_value="wrong"), \
                self.assertRaisesRegex(ValueError, "sealed_native_input_hash_mismatch"):
            run_native("missing-native", "missing-output")
        # Opt-in modes have dependencies; invalid combinations must fail before
        # reading an artifact, creating output or beginning an expensive replay.
        for options in ({"outer_calls": True}, {"outer_calls": 1},
                        {"outer_calls": True, "unary_forwarding": True}):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, "invalid_using_shadows_option"):
                run_native("missing-native", "missing-output", **options)

    def test_mock_native_run_retains_conflicts_without_claiming_a_path(self):
        entry = function("entry", call("wrapper"))
        builtin_call = call("builtin")
        builtin_call["id"] = "math-call"
        wrapper = function("wrapper", builtin_call)
        conflict = deepcopy(wrapper)
        conflict["loc"] = {"file": "different-location.h"}
        payload = {"ast": {"kind": "TranslationUnitDecl", "inner": [entry, wrapper, conflict]},
                   "builtin_calls": [{"call_expression_id": "math-call",
                                      "builtin_name": "__builtin_expf"}]}
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "native.json"
            source.write_text(json.dumps({"status": "collected", "payload": payload}))
            with patch("experiments.softmax_call_audit.sha", return_value=HIP_NATIVE_SHA), \
                    patch("experiments.softmax_call_audit.select_entry", return_value=entry), \
                    patch("experiments.softmax_call_audit.implementation_hashes", return_value={}):
                report = run_native(source, Path(temporary) / "output")
        self.assertEqual(len(report["repeated_declaration_occurrences"]), 2)
        self.assertEqual(len(report["inventory"]["edges"]), 1)
        self.assertEqual(len(report["math_builtin_checks"]), 1)
        self.assertEqual(report["math_builtin_checks"][0]["structure_check"]["status"], "unknown")
        self.assertFalse(report["ast_modified"])
        self.assertFalse(report["source_program_checked"])
        self.assertFalse(report["deployable"])
        self.assertEqual(report["external_effect_protocols"], {})
        self.assertFalse(report["outer_calls_enabled"])
        self.assertEqual(report["outer_call_checks"], [])

    def test_method_reference_observation_does_not_override_resolver(self):
        root = {"inner": [function("entry", call("method", "CXXMethodDecl")),
                          function("method", call("external"), kind="CXXMethodDecl"),
                          {"kind": "FunctionDecl", "id": "external", "name": "leaf"}]}
        result = inventory(root, "entry")
        edge = result["edges"][0]
        self.assertEqual(edge["observed_reference_id"], "method")
        self.assertIsNone(edge["production_resolution"]["callee_id"])
        self.assertFalse(edge["dispatch_checked"])
        self.assertFalse(edge["effects_checked"])
        self.assertEqual(result["functions"][-1]["definition_count"], 0)
        self.assertFalse(result["deployable"])

    def test_duplicate_definition_does_not_choose_by_name(self):
        result = inventory({"inner": [function("entry", call("wrong")), function("entry")]}, "entry")
        self.assertEqual(result["functions"][0]["definition_count"], 2)
        self.assertEqual(result["edges"], [])

    def test_indirect_callee_does_not_consume_argument_function_reference(self):
        indirect = {"kind": "CallExpr", "inner": [{"kind": "DeclRefExpr",
                    "referencedDecl": {"kind": "VarDecl", "id": "pointer"}},
                    call("argument_function")["inner"][0]]}
        result = inventory({"inner": [function("entry", indirect)]}, "entry")
        self.assertIsNone(result["edges"][0]["inventory_target_id"])

    def test_budget_and_cycle_preserve_diagnostic_boundary(self):
        root = {"inner": [function("a", call("b")), function("b", call("a"))]}
        limited = inventory(root, "a", max_functions=1)
        self.assertTrue(limited["budget_exhausted"])
        self.assertEqual(limited["pending_ids"], ["b"])
        complete = inventory(root, "a")
        self.assertFalse(complete["budget_exhausted"])
        self.assertEqual(len(complete["functions"]), 2)


if __name__ == "__main__":
    unittest.main()
