"""Native envelope -> freshly composed automatic-object initialization check."""
import copy
import os
from pathlib import Path
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect
from wavebridge.verification.object_initialization import check

PLUGIN = os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")
ABI = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False}}


@unittest.skipUnless(PLUGIN, "requires compiler-matched native cleanup observations")
class ObjectInitializationClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/object_initialization.cpp",
                         COMPILER, Path(PLUGIN), ["-std=c++17"])
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.payload = report["payload"]

    def inputs(self, name, payload):
        function = next(n for n in _walk(payload["ast"]) if n.get("kind") == "FunctionDecl"
                        and n.get("name") == name)
        variable = next(n for n in _walk(function) if n.get("kind") == "VarDecl" and n.get("name") == "value")
        expression = next((n for n in _walk(variable) if n.get("kind") == "CXXConstructExpr"), None)
        domains = {}
        if expression:
            for argument in expression.get("inner", []):
                refs = [n["referencedDecl"] for n in _walk(argument) if n.get("kind") == "DeclRefExpr"
                        and n.get("referencedDecl", {}).get("kind") == "ParmVarDecl"]
                if refs:
                    domains[argument["id"]] = [{"declaration_id": ref["id"], "type": ref["type"],
                                               "lower": 1, "upper": 4096} for ref in refs]
        return variable, expression, domains

    def run_check(self, name="scalar_temporary", payload=None, **kwargs):
        payload = self.payload if payload is None else payload
        variable, _, domains = self.inputs(name, payload)
        return check(payload, variable["id"], ABI, domains, **kwargs)

    def test_plain_and_scalar_temporary_initialization(self):
        for name in ("direct_literal", "scalar_temporary", "nested_target"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "checked", report)
                self.assertFalse(report["source_program_checked"])
                self.assertFalse(report["deployable"])
                self.assertEqual(report["completion"]["status"], "conditional")
                self.assertEqual(report["prior_aliases"], "not_established")
                self.assertEqual(report["post_initialization_value_preservation"], "not_established")
                if name == "direct_literal":
                    self.assertEqual(report["fields"][0]["value"], 7)
                else:
                    self.assertEqual(report["fields"][0]["interval"], {"lower": 1, "upper": 1024})

    def test_nonautomatic_effectful_or_unsupported_targets(self):
        for name in ("static_target", "tls_target", "volatile_target", "attributed_target",
                     "reference_target", "lambda_target", "destructor_temporary"):
            with self.subTest(name=name):
                self.assertEqual(self.run_check(name)["status"], "unknown")

    def test_cleanup_observations_are_required_exact_and_conservative(self):
        for mutation in ("missing", "duplicate", "subexpression", "side_effects", "count", "bool_count",
                         "nonboolean_flag", "coverage", "semantics", "old_envelope", "ast_conflict"):
            payload = copy.deepcopy(self.payload)
            variable, expression, _ = self.inputs("scalar_temporary", payload)
            wrapper = variable["inner"][0]
            records = payload["expression_cleanups"]
            record = next(r for r in records if r["expression_id"] == wrapper["id"])
            if mutation == "missing":
                records.remove(record)
            elif mutation == "duplicate":
                records.append(copy.deepcopy(record))
            elif mutation == "subexpression":
                record["subexpression_id"] = "unrelated"
            elif mutation == "side_effects":
                record["cleanups_have_side_effects"] = True
            elif mutation == "count":
                record["num_objects"] = 1
            elif mutation == "bool_count":
                record["num_objects"] = False
            elif mutation == "nonboolean_flag":
                record["cleanups_have_side_effects"] = 0
            elif mutation == "coverage":
                payload["cleanup_coverage"] = "unverified"
            elif mutation == "semantics":
                payload["cleanup_object_count_semantics"] = "destructor_count"
            elif mutation == "ast_conflict":
                wrapper["cleanupsHaveSideEffects"] = True
            else:
                del payload["expression_cleanups"]
            with self.subTest(mutation=mutation):
                self.assertEqual(self.run_check(payload=payload)["status"], "unknown")

    def test_target_ast_shape_and_identity_are_fresh(self):
        for mutation in ("extra_child", "type_mismatch", "unknown_attribute", "duplicate", "unknown_storage"):
            payload = copy.deepcopy(self.payload)
            variable, _, _ = self.inputs("direct_literal", payload)
            if mutation == "extra_child":
                variable["inner"].append({"kind": "UnknownEffectExpr"})
            elif mutation == "type_mismatch":
                variable["type"] = {"qualType": "AnotherRecord"}
            elif mutation == "unknown_attribute":
                variable["inner"].append({"kind": "UnknownEffectAttr"})
            elif mutation == "duplicate":
                payload["ast"]["inner"].append(copy.deepcopy(variable))
            else:
                variable["storageClass"] = "unverified"
            with self.subTest(mutation=mutation):
                self.assertEqual(self.run_check("direct_literal", payload)["status"], "unknown")

    def test_missing_domains_budgets_and_immutability(self):
        before = copy.deepcopy(self.payload)
        self.assertEqual(self.run_check()["status"], "checked")
        self.assertEqual(before, self.payload)
        variable, _, _ = self.inputs("scalar_temporary", self.payload)
        self.assertEqual(check(self.payload, variable["id"], ABI, {})["status"], "unknown")
        for budget in (0, True, 1, 10_000_001):
            self.assertEqual(self.run_check(max_ast_nodes=budget)["status"], "unknown")
