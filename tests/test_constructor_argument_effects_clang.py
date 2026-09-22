"""Real source -> fresh field/value/effect gates, with explicit argument domains."""
import copy
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.constructor_argument_effects import check

ABI = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False}}


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class ConstructorArgumentEffectsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/constructor_argument_effects.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "dynamic",
                         full_translation_unit=True, dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]

    def inputs(self, name, root):
        function = next(n for n in _walk(root) if n.get("kind") == "FunctionDecl"
                        and n.get("name") == name and
                        any(c.get("kind") == "CXXConstructExpr" for c in _walk(n)))
        expression = next(n for n in _walk(function) if n.get("kind") == "CXXConstructExpr")
        domains = {}
        for argument in expression["inner"]:
            if not any(n.get("kind") == "CallExpr" for n in _walk(argument)):
                continue
            refs = {n["referencedDecl"]["id"]: n["referencedDecl"] for n in _walk(argument)
                    if n.get("kind") == "DeclRefExpr" and
                    n.get("referencedDecl", {}).get("kind") in {"VarDecl", "ParmVarDecl"}}
            domains[argument["id"]] = [{"declaration_id": identifier, "type": ref["type"],
                                        "lower": 1, "upper": 4096} for identifier, ref in refs.items()]
        return expression, domains

    def run_check(self, name="dynamic", root=None, **kwargs):
        root = self.root if root is None else root
        expression, domains = self.inputs(name, root)
        return check(root, expression["id"], ABI, domains, **kwargs)

    def test_supported_automatic_operands_constants_and_defaults(self):
        for name in ("constant", "dynamic", "local", "earlier_initialization", "enabled_argument"):
            with self.subTest(name=name):
                result = self.run_check(name)
                self.assertEqual(result["status"], "checked", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])
                self.assertEqual(result["scope"], "selected_direct_constructor_argument_evaluations_only")
                self.assertEqual(result["constructor_source"]["call_argument_effects"], "not_established")
                self.assertEqual(result["post_construction_escape"], "not_established")
                self.assertEqual(result["outer_cleanup_exception_unwinding_and_destructor"], "excluded")

    def test_storage_capture_and_attribute_boundaries(self):
        for name in ("global_argument", "tls_argument", "extern_argument", "static_argument",
                     "local_tls_argument", "captured", "reference_argument", "cleanup_argument", "template_caller"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "unknown")
                if name in {"global_argument", "tls_argument", "extern_argument", "static_argument",
                            "local_tls_argument"}:
                    self.assertEqual(report["constructor_source"]["status"], "checked", report)

    def test_unknown_attributes_and_hidden_leaf_children(self):
        for mutation in ("callee_attribute", "parameter_attribute", "operand_attribute", "leaf_child",
                         "operand_storage", "attribute_payload"):
            root = copy.deepcopy(self.root)
            expression, _ = self.inputs("dynamic", root)
            references = [n for n in _walk(expression) if n.get("kind") == "DeclRefExpr"]
            callee_ref = next(n for n in references if n["referencedDecl"]["kind"] == "FunctionDecl")
            callee = next(n for n in _walk(root) if n.get("id") == callee_ref["referencedDecl"]["id"])
            operand = next(n for n in references if n["referencedDecl"]["kind"] == "ParmVarDecl")
            if mutation == "leaf_child":
                operand["inner"] = [{"kind": "UnknownEffectExpr"}]
            elif mutation == "operand_storage":
                target = next(n for n in _walk(root) if n.get("id") == operand["referencedDecl"]["id"])
                target["storageClass"] = "unknown_storage"
            elif mutation == "attribute_payload":
                callee["inner"].append({"kind": "CUDAHostAttr", "inner": [{"kind": "UnknownEffectExpr"}]})
            else:
                target = callee
                if mutation == "parameter_attribute":
                    target = next(n for n in callee["inner"] if n.get("kind") == "ParmVarDecl")
                if mutation == "operand_attribute":
                    target = next(n for n in _walk(root) if n.get("id") == operand["referencedDecl"]["id"])
                target.setdefault("inner", []).append({"kind": "UnknownEffectAttr"})
            with self.subTest(mutation=mutation):
                self.assertEqual(self.run_check(root=root)["status"], "unknown")

    def test_missing_domains_budget_and_immutability(self):
        before = copy.deepcopy(self.root)
        self.assertEqual(self.run_check()["status"], "checked")
        self.assertEqual(before, self.root)
        expression, _ = self.inputs("dynamic", self.root)
        self.assertEqual(check(self.root, expression["id"], ABI, {})["status"], "unknown")
        for budget in (0, True, 1, 10_000_001):
            self.assertEqual(self.run_check(max_ast_nodes=budget)["status"], "unknown")

    def test_enable_if_is_limited_to_recorded_true_literal_shape(self):
        for mutation in ("false", "extra_child", "unknown_expression"):
            root = copy.deepcopy(self.root)
            function = next(n for n in _walk(root) if n.get("kind") == "FunctionDecl"
                            and n.get("name") == "enabled_min")
            attribute = next(n for n in function["inner"] if n.get("kind") == "EnableIfAttr")
            if mutation == "false":
                attribute["inner"][0]["value"] = False
            elif mutation == "extra_child":
                attribute["inner"].append({"kind": "UnknownEffectExpr"})
            else:
                attribute["inner"][0]["kind"] = "UnknownEffectExpr"
            with self.subTest(mutation=mutation):
                self.assertEqual(self.run_check("enabled_argument", root=root)["status"], "unknown")
