"""Real native capture chains with explicit, unverified lifetime assumptions."""
import copy
import os
import subprocess
import tempfile
from pathlib import Path
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect
from wavebridge.verification.integer_selection import _hash
from wavebridge.capture_source_check import check
from wavebridge.verification.object_use_closure import check as check_uses

PLUGIN = os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")
ABI = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False}}


@unittest.skipUnless(PLUGIN, "requires compiler-matched WB_NATIVE_CAPTURE_PLUGIN")
class CaptureSourceClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/capture_source.cpp",
                         COMPILER, Path(PLUGIN), ["-std=c++17"])
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.payload = report["payload"]

    def inputs(self, name="one_reference", payload=None):
        payload = self.payload if payload is None else payload
        root = payload["ast"]
        function = next(n for n in _walk(root)
                        if n.get("kind") == "FunctionDecl" and n.get("name") == name)
        target = next(n for n in _walk(function)
                      if n.get("kind") == "VarDecl" and n.get("name") == "target")
        expression = next(n for n in _walk(target) if n.get("kind") == "CXXConstructExpr")
        source = next(n["referencedDecl"] for n in _walk(expression) if n.get("kind") == "DeclRefExpr")
        protocol = {
            "schema_version": "capture-source-assumptions/v1",
            "root_sha256": _hash(root), "copy_expression_id": expression["id"],
            "source_declaration_id": source["id"],
            "source_initialized_alive_assumed": True,
            "closure_instances_from_recorded_lambdas_assumed": True,
            "source_and_closures_share_recorded_activation_assumed": True,
            "source_program_valid_assumed": True,
            "evidence_reference": "test-only explicit assumptions; not runtime evidence",
        }
        return expression["id"], protocol

    def run_check(self, name="one_reference", payload=None, **kwargs):
        payload = self.payload if payload is None else payload
        expression, protocol = self.inputs(name, payload)
        return check(payload, expression, ABI, protocol, **kwargs)

    def test_one_and_two_reference_layers(self):
        for name, depth in (("one_reference", 1), ("nested_references", 2),
                            ("initializer_evaluation", 1)):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "checked", report)
                self.assertEqual(len(report["capture_chain"]), depth)
                self.assertEqual(report["source_object_identity"], "conditional_same_dynamic_object_at_copy_evaluation")
                self.assertFalse(report["identity_completion"]["external_evidence_verified"])
                self.assertEqual(report["copy_check"]["source_object_identity"], "not_established")
                self.assertFalse(report["source_program_checked"])
                self.assertFalse(report["deployable"])

    def v2_protocol(self, name, payload=None):
        expression, protocol = self.inputs(name, payload)
        protocol["schema_version"] = "capture-source-assumptions/v2"
        del protocol["closure_instances_from_recorded_lambdas_assumed"]
        return expression, protocol

    def test_v2_derives_origin_from_fresh_immediate_receiver_paths(self):
        for name, depth in (("immediate_reference", 1), ("immediate_nested", 2),
                            ("initializer_evaluation", 1)):
            expression, protocol = self.v2_protocol(name)
            with self.subTest(name=name):
                report = check(self.payload, expression, ABI, protocol)
                self.assertEqual(report["status"], "checked", report)
                self.assertEqual(report["schema_version"], "capture-source-check/v2")
                self.assertEqual(report["closure_origin"]["status"], "checked")
                self.assertEqual(len(report["closure_origin"]["invocation_checks"]), depth)
                self.assertNotIn("closure_instances_from_recorded_lambdas_assumed",
                                 report["identity_completion"]["premises"])
                self.assertIn("source_initialized_alive_assumed", report["identity_completion"]["premises"])
                self.assertIn("source_and_closures_share_recorded_activation_assumed",
                              report["identity_completion"]["premises"])
                self.assertEqual(report["source_object_preservation"], "not_established")

    def test_v2_rejects_named_passed_returned_and_nonimmediate_outer(self):
        for name in ("one_reference", "nested_references", "passed_reference",
                     "returned_reference", "named_outer_immediate_inner"):
            expression, protocol = self.v2_protocol(name)
            with self.subTest(name=name):
                report = check(self.payload, expression, ABI, protocol)
                self.assertEqual(report["status"], "unknown", report)
                self.assertEqual(report["reason"], "fresh_closure_origin_invocation_not_checked")
                self.assertEqual(report["closure_origin"]["status"], "unknown")

    def test_v2_does_not_accept_old_origin_boolean_or_missing_remaining_premises(self):
        expression, protocol = self.v2_protocol("immediate_reference")
        changed = dict(protocol, closure_instances_from_recorded_lambdas_assumed=True)
        self.assertEqual(check(self.payload, expression, ABI, changed)["status"], "unknown")
        for key in ("source_initialized_alive_assumed", "source_and_closures_share_recorded_activation_assumed"):
            changed = dict(protocol)
            del changed[key]
            self.assertEqual(check(self.payload, expression, ABI, changed)["status"], "unknown")

    def test_v2_origin_does_not_hide_a_real_source_write(self):
        expression, protocol = self.v2_protocol("immediate_changed_source")
        identity = check(self.payload, expression, ABI, protocol)
        self.assertEqual(identity["status"], "checked", identity)
        self.assertEqual(identity["closure_origin"]["status"], "checked")
        self.assertEqual(identity["source_object_preservation"], "not_established")
        uses = check_uses(self.payload, protocol["source_declaration_id"], ABI, {}, {expression: protocol})
        self.assertEqual(uses["status"], "unknown", uses)
        self.assertEqual(uses["reason"], "source_reference_not_capture_initializer_or_direct_copy_argument")
        # Execute this one well-defined function, never the dangling-return fixture.
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "capture-origin"
            built = subprocess.run([COMPILER, "-std=c++17", "-DWAVEBRIDGE_CAPTURE_ORIGIN_EXECUTION",
                                    str(Path(__file__).parent / "fixtures/capture_source.cpp"),
                                    "-o", str(executable)], capture_output=True, text=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_identity_does_not_imply_value_preservation(self):
        report = self.run_check("changed_source")
        self.assertEqual(report["status"], "checked", report)
        self.assertEqual(report["source_object_preservation"], "not_established")
        self.assertEqual(report["launch_semantics"], "not_established")

    def test_any_value_capture_cannot_be_original_object_identity(self):
        for name in ("value_capture", "outer_copy_inner_reference"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertNotEqual(report["status"], "checked", report)

    def test_unsupported_sources_and_contexts(self):
        for name in ("source_inside_outer", "alias_capture", "static_source", "tls_source",
                     "init_capture", "generic_capture", "direct_without_capture"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertNotEqual(report["status"], "checked", report)

    def test_missing_misbound_or_nonboolean_protocol(self):
        expression, protocol = self.inputs()
        for key in protocol:
            for value in (None, False, 1, "", [], {}):
                changed = dict(protocol, **{key: value})
                with self.subTest(key=key, value=value):
                    self.assertNotEqual(check(self.payload, expression, ABI, changed)["status"], "checked")
        self.assertNotEqual(check(self.payload, expression, ABI, {})["status"], "checked")

    def test_missing_duplicate_or_misbound_native_edges(self):
        for mutation in ("missing", "duplicate", "field", "initializer", "outer_path", "unsupported"):
            payload = copy.deepcopy(self.payload)
            expression, protocol = self.inputs(payload=payload)
            edge = next(c for c in payload["captures"]
                        if c["captured_declaration_id"] == protocol["source_declaration_id"])
            if mutation == "missing":
                payload["captures"].remove(edge)
            elif mutation == "duplicate":
                payload["captures"].append(copy.deepcopy(edge))
            elif mutation == "field":
                edge["field_declaration_id"] = "unrelated"
            elif mutation == "initializer":
                edge["initializer_expression_id"] = "unrelated"
            elif mutation == "outer_path":
                edge["enclosing_lambda_ids"] = ["unrelated"]
            else:
                edge["support_status"] = "unsupported"
            with self.subTest(mutation=mutation):
                self.assertNotEqual(check(payload, expression, ABI, protocol)["status"], "checked")

    def test_fresh_ast_cannot_be_replaced_by_successful_copy_report(self):
        payload = copy.deepcopy(self.payload)
        expression, _ = self.inputs(payload=payload)
        for node in _walk(payload["ast"]):
            if node.get("id") == expression:
                node["inner"] = []
        payload["copy_check"] = {"status": "checked"}
        expression, protocol = self.inputs()  # Old binding also cannot bless the changed AST.
        self.assertNotEqual(check(payload, expression, ABI, protocol)["status"], "checked")

    def test_ast_path_and_reference_field_are_freshly_checked(self):
        for mutation in ("extra_target_path", "field_type", "template_argument"):
            payload = copy.deepcopy(self.payload)
            expression, protocol = self.inputs(payload=payload)
            edge = next(c for c in payload["captures"]
                        if c["captured_declaration_id"] == protocol["source_declaration_id"])
            if mutation == "extra_target_path":
                target = next(n for n in _walk(payload["ast"]) if n.get("id") == expression)
                payload["ast"]["inner"].append(copy.deepcopy(target))
            elif mutation == "field_type":
                for node in _walk(payload["ast"]):
                    if node.get("id") == edge["field_declaration_id"]:
                        node["type"] = {"qualType": "Plain"}
            else:
                function = next(n for n in _walk(payload["ast"])
                                if n.get("kind") == "FunctionDecl" and n.get("name") == "one_reference")
                function["inner"].append({"kind": "TemplateArgument", "type": {"qualType": "int"}})
            # Rebind the external premise to the changed input, so rejection
            # must come from fresh structure checking, not an obsolete hash.
            expression, protocol = self.inputs(payload=payload)
            with self.subTest(mutation=mutation):
                self.assertNotEqual(check(payload, expression, ABI, protocol)["status"], "checked")

    def test_budget_and_input_immutability(self):
        before = copy.deepcopy(self.payload)
        report = self.run_check()
        self.assertEqual(report["status"], "checked", report)
        self.assertEqual(before, self.payload)
        for budget in (True, 0, 1, 10_000_001):
            with self.subTest(budget=budget):
                self.assertNotEqual(self.run_check(max_ast_nodes=budget)["status"], "checked")
