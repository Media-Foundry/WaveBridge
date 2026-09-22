"""Real Clang property -> fresh receiver/getter composition; no GPU/API oracle."""
import copy
from pathlib import Path
import shutil
import unittest

from wavebridge.analysis.initializer_value import link
from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.getter_returns import _hash, check_property_no_memory_write
from tests.test_getter_effects import protocol
from tests.test_getter_returns import ABI


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class PropertyEffectsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/property_effects.cpp",
                         shutil.which("clang++"), ["-std=c++17", "-fms-extensions"],
                         "good", full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.functions = {node["name"]: node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")}
        cls.leaf = cls.functions["leaf"]["id"]

    def inputs(self, name="good"):
        expression = next(node for node in _walk(self.functions[name])
                          if node.get("kind") == "PseudoObjectExpr")
        linked = link(self.root, expression)
        contract = {"schema_version": "getter-leaf-domain/v1", "declaration_id": self.leaf,
                    "return_type": {"qualType": "unsigned int"}, "arguments": [],
                    "lower": 0, "upper": 7}
        pseudo = linked.get("pseudo_object") or {}
        receiver = {
            "schema_version": "property-receiver-assumptions/v1",
            "root_sha256": _hash(self.root), "expression_id": expression["id"],
            "receiver_id": pseudo.get("receiver_id"),
            "receiver_declaration_id": pseudo.get("receiver_declaration_id"),
            "call_id": linked.get("call_id"),
            "callee_declaration_id": linked.get("callee_declaration_id"),
            "receiver_initialized_and_alive_assumed": True,
            "extension_static_member_evaluation_assumed": True,
            "evidence_reference": "fixture-only external readiness/extension assumptions",
        }
        effect = protocol(self.root, start=linked.get("callee_declaration_id"), leaf=self.leaf)
        return expression["id"], contract, effect, receiver

    def run_check(self, inputs, root=None, **kwargs):
        expr, contract, effect, receiver = inputs
        return check_property_no_memory_write(self.root if root is None else root, expr,
                                               contract, ABI, effect, receiver, **kwargs)

    def test_exact_property_composes_both_premises(self):
        result = self.run_check(self.inputs())
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["getter_effect_check"]["status"], "checked")
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        self.assertFalse(result["external_receiver_premises_verified"])

    def test_unsupported_receiver_sources_remain_unknown(self):
        for name in ("volatile_case", "tls_case", "alias_case", "internal_case", "called_receiver"):
            with self.subTest(name=name):
                result = self.run_check(self.inputs(name))
                self.assertEqual(result["status"], "unknown", result)
                self.assertNotIn("conclusion", result)

    def test_missing_or_mismatched_receiver_and_leaf_protocols(self):
        for key, value in (("root_sha256", "0" * 64), ("expression_id", "other"),
                           ("receiver_id", "other"), ("receiver_declaration_id", "other"),
                           ("call_id", "other"), ("callee_declaration_id", "other"),
                           ("receiver_initialized_and_alive_assumed", False),
                           ("extension_static_member_evaluation_assumed", 1),
                           ("evidence_reference", "")):
            inputs = self.inputs()
            inputs[3][key] = value
            with self.subTest(key=key):
                self.assertEqual(self.run_check(inputs)["status"], "unknown")
        expr, contract, effect, receiver = self.inputs()
        self.assertEqual(self.run_check((expr, contract, None, receiver))["status"], "unknown")
        self.assertEqual(self.run_check((expr, contract, effect, None))["status"], "unknown")

    def test_expression_is_selected_from_whole_root_and_budget_is_enforced(self):
        inputs = self.inputs()
        self.assertEqual(self.run_check(inputs, max_ast_nodes=1)["reason"], "ast_node_budget_exceeded")
        self.assertEqual(self.run_check(("absent", *inputs[1:]))["reason"], "property_expression_not_unique")
        root = copy.deepcopy(self.root)
        expression = next(node for node in _walk(root) if node.get("id") == inputs[0])
        root["inner"].append(copy.deepcopy(expression))
        self.assertEqual(self.run_check(inputs, root=root)["reason"], "property_expression_not_unique")

    def test_stale_root_abi_leaf_and_effect_bindings_cannot_pass(self):
        inputs = self.inputs()
        for budget in (True, 0, 10_000_001):
            self.assertEqual(self.run_check(inputs, max_ast_nodes=budget)["status"], "unknown")
        root = dict(self.root, diagnostic_note="changed input")
        self.assertEqual(self.run_check(inputs, root=root)["status"], "unknown")
        expr, contract, effect, receiver = inputs
        self.assertEqual(check_property_no_memory_write(
            self.root, expr, contract, {}, effect, receiver)["status"], "unknown")
        for key, value in (("declaration_id", "other"),
                           ("return_type", {"qualType": "int"})):
            changed = dict(contract, **{key: value})
            self.assertEqual(self.run_check((expr, changed, effect, receiver))["status"], "unknown")
        for key in ("root_sha256", "start_declaration_id", "external_leaf_declaration_id"):
            changed = dict(effect, **{key: "other"})
            self.assertEqual(self.run_check((expr, contract, changed, receiver))["status"], "unknown")
        root = copy.deepcopy(self.root)
        root["inner"].append({"id": expr, "kind": "IntegerLiteral", "value": "1"})
        self.assertEqual(self.run_check(inputs, root=root)["reason"], "property_expression_not_unique")
