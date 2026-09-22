"""Real source -> body preservation; external assumptions are fixture-only.

No recovery/property checker is mocked. These tests do not validate a launch,
coordinate values, source validity, or GPU execution.
"""
import copy
from pathlib import Path
import shutil
import unittest

from wavebridge.analysis.column_loops import recover
from wavebridge.analysis.initializer_value import link
from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.column_body import check
from tests.test_getter_effects import protocol
from tests.test_getter_returns import ABI


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class ColumnBodyPropertiesClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        collected = collect(Path(__file__).parent / "fixtures/column_body_properties.cpp",
                            shutil.which("clang++"), ["-std=c++17", "-fms-extensions"],
                            "good", full_translation_unit=True,
                            dependency_binding="required")
        if collected["status"] != "collected":
            raise AssertionError(collected)
        cls.root = collected["ast_roots"][0]
        cls.root_hash = _hash(cls.root)
        cls.functions = {node["name"]: node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")}
        cls.leaf_id = cls.functions["leaf"]["id"]

    def property_inputs(self, loop):
        result = {}
        for expression in _walk(loop["inner"][-1]):
            if expression.get("kind") != "PseudoObjectExpr":
                continue
            linked = link(self.root, expression)
            observed = linked["receiver_evaluation_observation"]
            receiver = {
                "schema_version": "property-receiver-assumptions/v1",
                "root_sha256": self.root_hash,
                **{key: observed[key] for key in (
                    "expression_id", "receiver_id", "receiver_declaration_id",
                    "call_id", "callee_declaration_id")},
                "receiver_initialized_and_alive_assumed": True,
                "extension_static_member_evaluation_assumed": True,
                "evidence_reference": "fixture-only receiver assumptions",
            }
            result[expression["id"]] = {
                "leaf_contract": {
                    "schema_version": "getter-leaf-domain/v1", "declaration_id": self.leaf_id,
                    "return_type": {"qualType": "unsigned int"}, "arguments": [],
                    "lower": 0, "upper": 7,
                },
                "effect_protocol": protocol(self.root, start=linked["callee_declaration_id"],
                                            leaf=self.leaf_id),
                "receiver_protocol": receiver,
            }
        return result

    def inputs(self, name="good"):
        function = self.functions[name]
        loop = next(node for node in _walk(function) if node.get("kind") == "ForStmt")
        binding = {
            "schema_version": "column-body-assumptions/v1",
            "root_sha256": self.root_hash, "function_id": function["id"],
            "loop_id": loop["id"], "source_validity_assumed": True,
            "no_alias_with_protected_declarations_assumed": True,
            "evidence_reference": "fixture-only validity and memory non-alias assumptions",
        }
        return function["id"], loop["id"], ABI, self.property_inputs(loop), binding

    def test_safe_body_checks_every_property_without_upgrading_source_recovery(self):
        for name, count in (("good", 1), ("two_properties", 2), ("read_only_cast", 1)):
            with self.subTest(name=name):
                inputs = self.inputs(name)
                result = check(self.root, *inputs)
                self.assertEqual(result["status"], "checked", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])
                self.assertEqual(len(inputs[3]), count)
                ordinary = recover(self.root, inputs[0], 32)
                self.assertEqual(ordinary["status"], "unknown")
                self.assertEqual(ordinary["loops"][0]["body_preserves_induction"], "not_established")

    def test_effect_and_context_mutations_cannot_establish_body_preservation(self):
        for name in ("changed_induction", "changed_bound", "hidden_reference", "opaque_body",
                     "nested_loop", "comma_target", "changed_index", "static_induction", "nested_context"):
            with self.subTest(name=name):
                result = check(self.root, *self.inputs(name))
                self.assertEqual(result["status"], "unknown", result)
                self.assertNotIn("conclusion", result)

    def test_missing_extra_and_wrong_property_evidence_is_not_accepted(self):
        for mutation in ("missing", "extra", "wrong_effect", "wrong_receiver", "self_signed"):
            inputs = list(self.inputs("two_properties"))
            properties = inputs[3]
            first = next(iter(properties))
            if mutation == "missing":
                del properties[first]
            elif mutation == "extra":
                properties["absent"] = copy.deepcopy(properties[first])
            elif mutation == "wrong_effect":
                properties[first]["effect_protocol"]["external_leaf_no_memory_write_assumed"] = False
            elif mutation == "wrong_receiver":
                properties[first]["receiver_protocol"]["expression_id"] = "other"
            else:
                properties[first] = {"status": "checked", "conclusion": {"property": "no_memory_write"}}
            with self.subTest(mutation=mutation):
                self.assertEqual(check(self.root, *inputs)["status"], "unknown")

    def test_external_body_binding_is_required_and_strict(self):
        for key, value in (("root_sha256", "0" * 64), ("function_id", "other"),
                           ("loop_id", "other"), ("source_validity_assumed", False),
                           ("no_alias_with_protected_declarations_assumed", 1),
                           ("evidence_reference", "")):
            inputs = list(self.inputs())
            inputs[4][key] = value
            with self.subTest(key=key):
                self.assertEqual(check(self.root, *inputs)["status"], "unknown")

    def test_duplicate_loop_stale_root_and_budget_remain_unknown(self):
        inputs = self.inputs()
        for budget in (1, True, 0, 10_000_001):
            self.assertEqual(check(self.root, *inputs, max_ast_nodes=budget)["status"], "unknown")
        root = copy.deepcopy(self.root)
        loop = next(node for node in _walk(root) if node.get("id") == inputs[1])
        root["inner"].append(copy.deepcopy(loop))
        self.assertEqual(check(root, *inputs)["status"], "unknown")
        self.assertEqual(check(dict(self.root, changed=True), *inputs)["status"], "unknown")
