"""Whole-function source uses, native captures and independently checked copies."""
import copy
import os
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect
from wavebridge.verification.integer_selection import _hash
from wavebridge.verification.object_use_closure import _reference_use_effects, check, inspect_structure

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
            if (node.get("kind") == "CXXConstructExpr" and depth and
                    any(n.get("kind") == "DeclRefExpr" and
                        n.get("referencedDecl", {}).get("id") == source["id"] for n in _walk(node))):
                expression = node
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

    def run_structure(self, name="three_branches", payload=None, **kwargs):
        payload = self.payload if payload is None else payload
        source, _ = self.inputs(name, payload)
        # No capture protocol, inferred value oracle, or earlier successful
        # child report is passed to the independent structure entry point.
        return inspect_structure(payload, source["id"], ABI, {}, **kwargs)

    def test_independent_closure_never_calls_conditional_copy_or_identity(self):
        before = copy.deepcopy(self.payload)
        with patch("wavebridge.verification.object_use_closure.check_record_copy",
                   side_effect=AssertionError("conditional copy used")), \
                patch("wavebridge.verification.object_use_closure.check_capture_source",
                      side_effect=AssertionError("conditional identity used")), \
                patch("wavebridge.capture_source_check.check_record_copy",
                      side_effect=AssertionError("nested conditional copy used")):
            for name in ("plain_copy", "three_branches", "by_value_flow", "captured_by_value_flow"):
                with self.subTest(name=name):
                    report = self.run_structure(name)
                    self.assertEqual(report["status"], "checked", report)
                    self.assertEqual(report["schema_version"], "object-explicit-use-structure/v1")
                    self.assertEqual(report["source_order"]["status"], "checked")
                    self.assertEqual(report["source_reference_use_effects"]["status"], "checked")
                    self.assertEqual(report["copy_cleanup_observations"]["status"], "checked")
                    self.assertNotIn("capture_protocols", report["input_sha256"])
                    self.assertNotIn("conditional_on_existing_capture_protocols",
                                     report["source_reference_use_effects"].values())
                    self.assertNotIn("copy_checks", report)
                    self.assertNotIn("capture_checks", report)
                    self.assertEqual(report["conditional_initialization"]["completion"]["status"], "conditional")
                    for key in ("source_lifetime", "source_object_preservation",
                                "reachability_and_execution_order", "opaque_call_effects"):
                        self.assertEqual(report[key], "not_established")
                    self.assertFalse(report["source_program_checked"])
                    self.assertFalse(report["deployable"])
                    for child in report["copy_structures"]:
                        self.assertEqual(child["schema_version"], "record-copy-structure/v1")
                    for child in report["capture_structures"]:
                        self.assertEqual(child["schema_version"], "capture-source-structure/v1")
                        self.assertNotIn("identity_completion", child)
        self.assertEqual(self.payload, before)

    def test_unreachable_structure_does_not_establish_completion_or_lifetime(self):
        report = self.run_structure("unreachable_copy_flow")
        self.assertEqual(report["status"], "checked", report)
        self.assertEqual(report["conditional_initialization"]["completion"]["status"], "conditional")
        self.assertEqual(report["source_lifetime"], "not_established")
        self.assertEqual(report["reachability_and_execution_order"], "not_established")
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "unreachable-uses"
            built = subprocess.run([COMPILER, "-std=c++17", "-DWAVEBRIDGE_OBJECT_USES_EXECUTION",
                                    str(Path(__file__).parent / "fixtures/object_uses.cpp"),
                                    "-o", str(executable)], capture_output=True, text=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_independent_closure_rejects_writes_aliases_and_unsupported_effects(self):
        for name in ("direct_write", "write_inside_lambda", "write_in_other_branch", "reference_alias",
                     "cast_alias", "address_escape", "by_reference_flow", "by_value_capture",
                     "named_closure", "passed_closure", "init_capture_alias", "static_source",
                     "tls_source", "opaque_assembly", "attributed_copy_flow", "captured_attributed_copy_flow"):
            with self.subTest(name=name):
                self.assertEqual(self.run_structure(name)["status"], "unknown")
        # The established conditional-value interface deliberately has wider
        # attribute tolerance. The new path must not silently narrow that API.
        for name in ("attributed_copy_flow", "captured_attributed_copy_flow"):
            self.assertEqual(self.run_check(name)["status"], "checked")

    def test_independent_parent_does_not_upgrade_unknown_children(self):
        cleanup = self.run_structure("side_effect_cleanup_copy")
        self.assertEqual(cleanup["status"], "checked", cleanup)
        self.assertEqual(cleanup["copy_cleanup_observations"]["status"], "unknown")
        order = self.run_structure("goto_flow")
        self.assertEqual(order["status"], "checked", order)
        self.assertEqual(order["source_order"]["status"], "unknown")
        opaque = self.run_structure("ordinary_opaque_call")
        self.assertEqual(opaque["status"], "checked", opaque)
        self.assertEqual(opaque["opaque_call_effects"], "not_established")
        for report in (cleanup, order, opaque):
            self.assertEqual(report["source_lifetime"], "not_established")
            self.assertEqual(report["source_object_preservation"], "not_established")
            self.assertFalse(report["deployable"])

    def test_independent_closure_rechecks_missing_or_misbound_native_capture(self):
        for mutation in ("missing", "duplicate", "field", "initializer", "kind"):
            payload = copy.deepcopy(self.payload)
            source, _ = self.inputs("three_branches", payload)
            edge = next(item for item in payload["captures"]
                        if item["captured_declaration_id"] == source["id"])
            if mutation == "missing":
                payload["captures"].remove(edge)
            elif mutation == "duplicate":
                payload["captures"].append(copy.deepcopy(edge))
            elif mutation == "field":
                edge["field_declaration_id"] = "unrelated"
            elif mutation == "initializer":
                edge["initializer_expression_id"] = "unrelated"
            else:
                edge["capture_kind"] = "by_copy"
            payload["capture_structures"] = [{"status": "checked"}]
            with self.subTest(mutation=mutation):
                self.assertEqual(self.run_structure(payload=payload)["status"], "unknown")

    def test_independent_closure_rejects_invalid_inputs_and_budget(self):
        for budget in (0, True, 1, 10_000_001):
            self.assertEqual(self.run_structure(max_ast_nodes=budget)["status"], "unknown")
        for payload in (None, {}, {"ast": self.payload["ast"]}):
            self.assertEqual(inspect_structure(payload, "missing", ABI, {})["status"], "unknown")
        self.assertEqual(inspect_structure(self.payload, "missing", ABI, {})["status"], "unknown")

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

    def test_composition_accepts_source_checked_origin_without_origin_boolean(self):
        for name, version in ((name, version) for name in ("three_branches", "captured_by_value_flow")
                              for version in (2, 3)):
            source, protocols = self.inputs(name, self.payload)
            for protocol in protocols.values():
                protocol["schema_version"] = f"capture-source-assumptions/v{version}"
                del protocol["closure_instances_from_recorded_lambdas_assumed"]
                if version == 3:
                    del protocol["source_and_closures_share_recorded_activation_assumed"]
            with self.subTest(name=name, version=version):
                report = check(self.payload, source["id"], ABI, {}, protocols)
                self.assertEqual(report["status"], "checked", report)
                self.assertEqual(report["source_order"]["status"], "checked")
                self.assertEqual(report["source_reference_use_effects"]["status"], "checked")
                for capture in report["capture_checks"]:
                    self.assertEqual(capture["closure_origin"]["status"], "checked")
                    self.assertNotIn("closure_instances_from_recorded_lambdas_assumed",
                                     capture["identity_completion"]["premises"])
                    if version == 3:
                        self.assertNotIn("source_and_closures_share_recorded_activation_assumed",
                                         capture["identity_completion"]["premises"])

    def test_writes_aliases_and_addresses_are_not_closed_uses(self):
        for name in ("direct_write", "write_inside_lambda", "write_in_other_branch",
                     "reference_alias", "cast_alias", "address_escape"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "unknown", report)

    def test_hash_modes_preserve_complete_checker_reports(self):
        for name in ("plain_copy", "three_branches", "direct_write"):
            with self.subTest(name=name):
                with patch.dict(os.environ, {"WAVEBRIDGE_JSON_HASH_MODE": "streaming"}):
                    streaming = self.run_check(name)
                with patch.dict(os.environ, {"WAVEBRIDGE_JSON_HASH_MODE": "one-shot"}):
                    one_shot = self.run_check(name)
                self.assertEqual(streaming["status"],
                                 "unknown" if name == "direct_write" else "checked")
                self.assertEqual(streaming, one_shot)

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

    def test_parameter_copies_compose_without_assuming_callee_purity(self):
        for name in ("by_value_flow", "captured_by_value_flow"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "checked", report)
                copies = report["copy_checks"] + [r["copy_check"] for r in report["capture_checks"]]
                self.assertEqual(len(copies), 2)
                for copy_report in copies:
                    self.assertEqual(copy_report["local_copy_effects"]["status"], "checked")
                    target = copy_report["parameter_target"]
                    self.assertEqual(target["status"], "checked")
                    self.assertEqual(target["callee_body_effects"], "not_established")
                self.assertEqual(report["source_object_preservation"], "not_established")
                self.assertFalse(report["deployable"])
        self.assertEqual(self.run_check("by_reference_flow")["status"], "unknown")

    def test_copy_ancestor_cleanup_observations_are_narrow_and_checked(self):
        plain = self.run_check("plain_copy")
        self.assertEqual(plain["status"], "checked", plain)
        plain_cleanup = plain["copy_cleanup_observations"]
        self.assertEqual(plain_cleanup["schema_version"],
                         "copy-enclosing-cleanup-observations/v1")
        self.assertEqual(plain_cleanup["status"], "checked", plain)
        self.assertEqual(plain_cleanup["wrappers"], [])
        self.assertTrue(all(row["wrapper_ids"] == [] for row in plain_cleanup["copies"]))

        wrapped = self.run_check("captured_by_value_flow")
        cleanup = wrapped["copy_cleanup_observations"]
        self.assertEqual(wrapped["status"], "checked", wrapped)
        self.assertEqual(cleanup["status"], "checked", wrapped)
        self.assertTrue(cleanup["wrappers"])
        self.assertTrue(all(row["wrapper_ids"] for row in cleanup["copies"]))
        for observation in cleanup["wrappers"]:
            self.assertEqual(observation["num_objects"], 0)
            self.assertIs(observation["cleanups_have_side_effects"], False)
        self.assertEqual(wrapped["source_object_preservation"], "not_established")
        self.assertFalse(wrapped["deployable"])

    def test_side_effecting_cleanup_wrapper_does_not_upgrade_parent_closure(self):
        report = self.run_check("side_effect_cleanup_copy")
        self.assertEqual(report["status"], "checked", report)
        cleanup = report["copy_cleanup_observations"]
        self.assertEqual(cleanup["status"], "unknown", report)
        self.assertTrue(cleanup["copies"][0]["wrapper_ids"])
        self.assertEqual(report["source_object_preservation"], "not_established")
        self.assertFalse(report["source_program_checked"])
        self.assertFalse(report["deployable"])

    def test_ancestor_cleanup_does_not_cover_other_earlier_cleanup(self):
        for name in ("standalone_temporary_before_copy", "ended_scope_before_copy"):
            with self.subTest(name=name):
                report = self.run_structure(name)
                self.assertEqual(report["status"], "checked", report)
                self.assertEqual(report["source_order"]["status"], "checked")
                self.assertEqual(report["source_reference_use_effects"]["status"], "checked")
                cleanup = report["copy_cleanup_observations"]
                self.assertEqual(cleanup["status"], "checked")
                self.assertEqual(cleanup["other_scope_destructors_and_cleanup_events"], "not_established")
                self.assertEqual(report["source_object_preservation"], "not_established")
                self.assertFalse(report["deployable"])
                if name == "standalone_temporary_before_copy":
                    function = next(n for n in _walk(self.payload["ast"])
                                    if n.get("kind") == "FunctionDecl" and n.get("name") == name)
                    wrapper_ids = {n["id"] for n in _walk(function)
                                   if n.get("kind") == "ExprWithCleanups"}
                    side_effecting = {observation["expression_id"]
                                      for observation in self.payload["expression_cleanups"]
                                      if observation["expression_id"] in wrapper_ids
                                      and observation["cleanups_have_side_effects"] is True}
                    self.assertTrue(side_effecting)
                    self.assertTrue(side_effecting.isdisjoint(
                        {observation["expression_id"] for observation in cleanup["wrappers"]}))
        # CPU main verifies each earlier destructor increments a global count
        # before the later copy, while the copied source field remains 3.
        # This is a scope-boundary witness, not a source-mutation counterexample.
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "earlier-cleanups"
            built = subprocess.run([COMPILER, "-std=c++17", "-DWAVEBRIDGE_OBJECT_USES_EXECUTION",
                                    str(Path(__file__).parent / "fixtures/object_uses.cpp"),
                                    "-o", str(executable)], capture_output=True, text=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_cleanup_metadata_must_exactly_bind_copy_ancestor_wrappers(self):
        baseline = self.run_check("captured_by_value_flow")
        cleanup = baseline["copy_cleanup_observations"]
        self.assertEqual(cleanup["status"], "checked", baseline)
        wrapper_id = cleanup["wrappers"][0]["expression_id"]
        for mutation in ("missing", "duplicate", "subexpression", "flag_true", "flag_nonbool",
                         "count_nonzero", "count_nonbool", "ast_conflict", "ast_null",
                         "coverage_missing", "count_semantics_wrong"):
            payload = copy.deepcopy(self.payload)
            records = payload["expression_cleanups"]
            record = next(item for item in records if item["expression_id"] == wrapper_id)
            if mutation == "missing":
                records.remove(record)
            elif mutation == "duplicate":
                records.append(copy.deepcopy(record))
            elif mutation == "subexpression":
                record["subexpression_id"] = "wrong_subexpression"
            elif mutation == "flag_true":
                record["cleanups_have_side_effects"] = True
            elif mutation == "flag_nonbool":
                record["cleanups_have_side_effects"] = 0
            elif mutation == "count_nonzero":
                record["num_objects"] = 1
            elif mutation == "count_nonbool":
                record["num_objects"] = False
            elif mutation == "coverage_missing":
                del payload["cleanup_coverage"]
            elif mutation == "count_semantics_wrong":
                payload["cleanup_object_count_semantics"] = "destructor_count"
            else:
                wrapper = next(node for node in _walk(payload["ast"])
                               if node.get("id") == wrapper_id and
                               node.get("kind") == "ExprWithCleanups")
                wrapper["cleanupsHaveSideEffects"] = None if mutation == "ast_null" else True
            with self.subTest(mutation=mutation):
                report = self.run_check("captured_by_value_flow", payload)
                self.assertEqual(report["status"], "checked", report)
                self.assertEqual(report["copy_cleanup_observations"]["status"], "unknown", report)
                self.assertEqual(report["source_object_preservation"], "not_established")
                self.assertFalse(report["deployable"])

    def test_cpu_value_vs_reference_mutation_is_a_separate_observation(self):
        # Finite CPU evidence only; the checker above does not certify history.
        with tempfile.TemporaryDirectory(prefix="wb-parameter-flow-") as directory:
            executable = Path(directory) / "run"
            built = subprocess.run(
                [COMPILER, "-std=c++17", "-DWAVEBRIDGE_OBJECT_USES_EXECUTION",
                 str(Path(__file__).parent / "fixtures/object_uses.cpp"), "-o", str(executable)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_source_statement_order_and_fresh_immediate_chains(self):
        for name in ("plain_copy", "three_branches", "by_value_flow",
                     "captured_by_value_flow", "nested_scope_flow", "switch_flow"):
            with self.subTest(name=name):
                result = self.run_check(name)
                order = result["source_order"]
                self.assertEqual(order["status"], "checked", result)
                self.assertEqual(len(order["copies"]), result["copy_count"])
                for row in order["copies"]:
                    self.assertLess(row["source_statement_position"], row["copy_enclosing_statement_position"])
                    expected = 2 if name == "three_branches" else 1 if name == "captured_by_value_flow" else 0
                    self.assertEqual(len(row["immediate_invocation_chain"]), expected)
                self.assertEqual(order["source_lifetime"], "not_established")
                self.assertEqual(order["source_value_preservation"], "not_established")
                self.assertFalse(order["deployable"])

    def test_all_fresh_copy_effects_are_required_for_use_effects(self):
        for name in ("plain_copy", "three_branches", "by_value_flow", "captured_by_value_flow"):
            with self.subTest(name=name):
                report = self.run_check(name)
                effects = report["source_reference_use_effects"]
                self.assertEqual(effects["status"], "checked", report)
                self.assertEqual({row["copy_expression_id"] for row in effects["copies"]},
                                 set(report["direct_copy_expression_ids"] + report["captured_copy_expression_ids"]))
                self.assertEqual(effects["source_object_preservation"], "not_established")
                self.assertEqual(effects["source_destination_nonoverlap"], "not_established")
                self.assertFalse(effects["deployable"])

    def test_real_unknown_copy_effect_does_not_inherit_reference_closure_success(self):
        for name in ("attributed_copy_flow", "captured_attributed_copy_flow"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "checked", report)
                self.assertEqual(report["source_order"]["status"], "checked")
                effects = report["source_reference_use_effects"]
                self.assertEqual(effects["status"], "unknown")
                self.assertEqual(effects["reason"], "one_or_more_copy_effects_unknown")
                self.assertEqual(effects["copies"][0]["status"], "unknown")

    def test_unclosed_references_never_establish_use_effects(self):
        for name in ("direct_write", "reference_alias", "address_escape", "named_closure"):
            with self.subTest(name=name):
                self.assertEqual(self.run_check(name)["source_reference_use_effects"]["status"], "unknown")

    def test_use_effect_composition_rejects_incomplete_or_misbound_fresh_reports(self):
        # Mutated child reports exercise composition binding, not compilable
        # source counterexamples. Public check never accepts caller reports.
        report = self.run_check("by_value_flow")
        source_id = report["variable_id"]
        root_hash = report["input_sha256"]["root"]
        paths = {identifier: () for identifier in report["direct_copy_expression_ids"]}
        for mutation in ("missing", "duplicate", "source", "root", "role", "effect_unknown", "effect_label"):
            copies = copy.deepcopy(report["copy_checks"])
            captures = []
            if mutation == "missing": copies.pop()
            elif mutation == "duplicate": copies.append(copy.deepcopy(copies[0]))
            elif mutation == "source": copies[0]["source_declaration_id"] = "wrong"
            elif mutation == "root": copies[0]["input_sha256"]["root"] = "wrong"
            elif mutation == "role": captures.append({"copy_check": copies.pop()})
            elif mutation == "effect_unknown": copies[0]["local_copy_effects"]["status"] = "unknown"
            else: copies[0]["local_copy_effects"]["source_parameter_accesses"] = "unmodeled"
            with self.subTest(mutation=mutation):
                result = _reference_use_effects(source_id, root_hash, paths, copies, captures)
                self.assertEqual(result["status"], "unknown", result)

    def test_switch_must_be_contained_after_source_declaration(self):
        positive = self.run_check("switch_flow")["source_order"]
        self.assertEqual(positive["status"], "checked")
        self.assertEqual(len(positive["structured_switch_ids"]), 1)
        negative = self.run_check("switch_before_source")["source_order"]
        self.assertEqual(negative["status"], "unknown")
        self.assertEqual(negative["reason"], "source_order_switch_not_after_source_declaration")
        for mutation in ("missing_switch_id", "orphan_break"):
            payload = copy.deepcopy(self.payload)
            function = next(n for n in _walk(payload["ast"]) if n.get("kind") == "FunctionDecl"
                            and n.get("name") == "switch_flow")
            if mutation == "missing_switch_id":
                switch = next(n for n in _walk(function) if n.get("kind") == "SwitchStmt")
                del switch["id"]
            else:
                body = next(n for n in function["inner"] if n.get("kind") == "CompoundStmt")
                body["inner"].append({"kind": "BreakStmt"})
            with self.subTest(mutation=mutation):
                self.assertEqual(self.run_check("switch_flow", payload)["source_order"]["status"], "unknown")

    def test_nonlocal_loop_and_exception_control_remain_unknown_for_order(self):
        for name in ("loop_flow", "goto_flow", "try_flow"):
            with self.subTest(name=name):
                result = self.run_check(name)
                self.assertEqual(result["source_order"]["status"], "unknown")
                if result["status"] == "checked":
                    self.assertEqual(result["source_order"]["reason"], "source_order_control_flow_unsupported")
                else:
                    self.assertEqual(result["status"], "unknown")
                    self.assertEqual(result["reason"], "selected_ast_contains_empty_placeholder")
                    self.assertEqual(result["source_order"]["reason"], "explicit_use_closure_not_checked")

    def test_order_uses_ast_statements_not_source_offsets(self):
        payload = copy.deepcopy(self.payload)
        function = next(n for n in _walk(payload["ast"]) if n.get("kind") == "FunctionDecl"
                        and n.get("name") == "by_value_flow")
        body = next(n for n in function["inner"] if n.get("kind") == "CompoundStmt")
        declaration = body["inner"].pop(0)
        body["inner"].append(declaration)  # deliberate malformed AST; source offsets unchanged
        result = self.run_check("by_value_flow", payload)
        self.assertEqual(result["source_order"]["status"], "unknown", result)
        self.assertEqual(result["source_order"]["reason"], "copy_statement_not_after_source_declaration")

    def test_unrecognized_statement_cannot_establish_order(self):
        payload = copy.deepcopy(self.payload)
        function = next(n for n in _walk(payload["ast"]) if n.get("kind") == "FunctionDecl"
                        and n.get("name") == "by_value_flow")
        body = next(n for n in function["inner"] if n.get("kind") == "CompoundStmt")
        body["inner"].append({"kind": "UnmodeledTransferStmt"})
        result = self.run_check("by_value_flow", payload)
        self.assertEqual(result["source_order"]["status"], "unknown")
        self.assertEqual(result["source_order"]["reason"], "source_order_control_flow_unsupported")

    def test_false_condition_do_wrappers_preserve_only_structural_order(self):
        for name in ("do_false_flow", "do_zero_flow", "do_break_flow", "do_nested_switch"):
            with self.subTest(name=name):
                order = self.run_check(name)["source_order"]
                self.assertEqual(order["status"], "checked", order)
                self.assertEqual(len(order["false_condition_do_wrappers"]), 1)
                self.assertEqual(order["source_lifetime"], "not_established")
                self.assertEqual(order["execution_reachability_and_count"], "not_established")

    def test_real_general_do_and_crossing_case_are_not_supported(self):
        for name in ("do_dynamic_flow", "do_true_flow", "do_continue_flow", "do_before_source", "case_into_do"):
            with self.subTest(name=name):
                order = self.run_check(name)["source_order"]
                self.assertEqual(order["status"], "unknown", order)

    def test_do_condition_requires_exact_literal_and_shape(self):
        for mutation in ("bool_integer", "bool_string", "hidden_child", "wrong_type",
                         "wrong_category", "extra_child", "missing_id", "nonzero", "wrong_cast"):
            payload = copy.deepcopy(self.payload)
            name = "do_zero_flow" if mutation in {"nonzero", "wrong_cast"} else "do_false_flow"
            function = next(n for n in _walk(payload["ast"]) if n.get("kind") == "FunctionDecl" and n.get("name") == name)
            node = next(n for n in _walk(function) if n.get("kind") == "DoStmt")
            condition = node["inner"][1]
            if mutation == "bool_integer": condition["value"] = 0
            elif mutation == "bool_string": condition["value"] = "false"
            elif mutation == "hidden_child": condition["inner"] = [{"kind": "CallExpr"}]
            elif mutation == "wrong_type": condition["type"] = {"qualType": "int"}
            elif mutation == "wrong_category": condition["valueCategory"] = "lvalue"
            elif mutation == "extra_child": node["inner"].append({"kind": "NullStmt"})
            elif mutation == "missing_id": del node["id"]
            elif mutation == "nonzero": condition["inner"][0]["value"] = "1"
            else: condition["castKind"] = "NoOp"
            with self.subTest(mutation=mutation):
                self.assertEqual(self.run_check(name, payload)["source_order"]["status"], "unknown")
