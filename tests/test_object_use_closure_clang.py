"""Whole-function source uses, native captures and independently checked copies."""
import copy
import os
from pathlib import Path
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect
from wavebridge.verification.integer_selection import _hash
from wavebridge.verification.object_use_closure import check

PLUGIN = os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")
ABI = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False}}


@unittest.skipUnless(PLUGIN, "requires compiler-matched native capture plugin")
class ObjectUseClosureClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/object_uses.cpp", COMPILER,
                         Path(PLUGIN), ["-std=c++17"])
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.payload = report["payload"]

    def inputs(self, name, payload):
        root = payload["ast"]
        function = next(n for n in _walk(root) if n.get("kind") == "FunctionDecl"
                        and n.get("name") == name)
        source = next(n for n in _walk(function) if n.get("kind") == "VarDecl"
                      and n.get("name") == "source")
        protocols = {}
        root_hash = _hash(root)

        def visit(node, depth=0):
            if node.get("kind") == "VarDecl" and node.get("name") == "target" and depth:
                expression = next(n for n in _walk(node) if n.get("kind") == "CXXConstructExpr")
                protocols[expression["id"]] = {
                    "schema_version": "capture-source-assumptions/v1", "root_sha256": root_hash,
                    "copy_expression_id": expression["id"], "source_declaration_id": source["id"],
                    "source_initialized_alive_assumed": True,
                    "closure_instances_from_recorded_lambdas_assumed": True,
                    "source_and_closures_share_recorded_activation_assumed": True,
                    "source_program_valid_assumed": True,
                    "evidence_reference": "explicit fixture lifetime/activation assumptions, not runtime proof",
                }
            for child in node.get("inner", []):
                if node.get("kind") == "LambdaExpr" and child.get("kind") == "CXXRecordDecl":
                    continue
                visit(child, depth + int(node.get("kind") == "LambdaExpr" and
                                         child.get("kind") == "CompoundStmt"))
        visit(function)
        return source, protocols

    def run_check(self, name="three_branches", payload=None, **kwargs):
        payload = self.payload if payload is None else payload
        source, protocols = self.inputs(name, payload)
        return check(payload, source["id"], ABI, {}, protocols, **kwargs)

    def test_plain_and_all_three_branches_are_checked(self):
        for name in ("plain_copy", "three_branches"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "checked", report)
                self.assertFalse(report["source_program_checked"])
                self.assertFalse(report["deployable"])
                for field in ("source_object_preservation", "prior_aliases", "untracked_memory_effects",
                              "launch_semantics"):
                    self.assertEqual(report[field], "not_established")
                expected = ({"explicit_source_references": 1, "capture_initializers": 0,
                             "direct_copies": 1, "captured_copies": 0, "lambdas": 0}
                            if name == "plain_copy" else
                            {"explicit_source_references": 7, "capture_initializers": 4,
                             "direct_copies": 0, "captured_copies": 3, "lambdas": 4})
                self.assertEqual(report["counts"], expected)

    def test_writes_aliases_and_addresses_are_not_closed_uses(self):
        for name in ("direct_write", "write_inside_lambda", "write_in_other_branch",
                     "reference_alias", "cast_alias", "address_escape"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "unknown", report)

    def test_capture_kind_and_closure_escape_boundaries(self):
        for name in ("by_value_capture", "named_closure", "passed_closure", "init_capture_alias"):
            with self.subTest(name=name):
                self.assertEqual(self.run_check(name)["status"], "unknown")

    def test_storage_and_opaque_effects_are_not_supported(self):
        for name in ("static_source", "tls_source", "opaque_assembly"):
            with self.subTest(name=name):
                self.assertEqual(self.run_check(name)["status"], "unknown")

    def test_no_source_reference_is_not_a_general_call_effect_proof(self):
        report = self.run_check("ordinary_opaque_call")
        self.assertEqual(report["status"], "checked", report)
        self.assertEqual(report["opaque_call_effects"], "not_established")
        self.assertEqual(report["untracked_memory_effects"], "not_established")
        self.assertEqual(report["source_object_preservation"], "not_established")

    def test_protocols_must_cover_every_copy_branch_exactly(self):
        source, protocols = self.inputs("three_branches", self.payload)
        self.assertEqual(len(protocols), 3)
        changed = copy.deepcopy(protocols)
        del changed[next(iter(changed))]
        self.assertEqual(check(self.payload, source["id"], ABI, {}, changed)["status"], "unknown")
        changed = dict(protocols, unrelated={})
        self.assertEqual(check(self.payload, source["id"], ABI, {}, changed)["status"], "unknown")
        changed = copy.deepcopy(protocols)
        next(iter(changed.values()))["source_initialized_alive_assumed"] = False
        self.assertEqual(check(self.payload, source["id"], ABI, {}, changed)["status"], "unknown")

    def test_missing_duplicate_and_misbound_capture_metadata(self):
        for mutation in ("missing", "duplicate", "lambda", "initializer", "kind", "path", "extra"):
            payload = copy.deepcopy(self.payload)
            source, _ = self.inputs("three_branches", payload)
            edge = next(item for item in payload["captures"]
                        if item["captured_declaration_id"] == source["id"])
            if mutation == "missing":
                payload["captures"].remove(edge)
            elif mutation == "duplicate":
                payload["captures"].append(copy.deepcopy(edge))
            elif mutation == "lambda":
                edge["lambda_id"] = "wrong_lambda"
            elif mutation == "initializer":
                edge["initializer_expression_id"] = "wrong_initializer"
            elif mutation == "kind":
                edge["capture_kind"] = "by_copy"
            elif mutation == "path":
                edge["enclosing_lambda_ids"] = ["wrong_parent"]
            else:
                extra = dict(edge, lambda_id="invented", initializer_expression_id="invented")
                payload["captures"].append(extra)
            with self.subTest(mutation=mutation):
                self.assertEqual(self.run_check(payload=payload)["status"], "unknown")

    def test_input_immutability_budget_and_missing_source(self):
        before = copy.deepcopy(self.payload)
        self.assertEqual(self.run_check("plain_copy")["status"], "checked")
        self.assertEqual(self.payload, before)
        for budget in (0, True, 1, 10_000_001):
            self.assertEqual(self.run_check(max_ast_nodes=budget)["status"], "unknown")
        self.assertEqual(check(self.payload, "missing", ABI, {}, {})["status"], "unknown")
