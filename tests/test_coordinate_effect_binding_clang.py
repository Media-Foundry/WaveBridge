"""Real Clang coordinate property effects; the surrounding launch is explicit test input."""

import copy
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.analysis.initializer_value import link
from wavebridge.device_evidence import _coordinate_effects
from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.getter_returns import _hash
from tests.test_getter_effects import protocol as effect_protocol
from tests.test_getter_returns import ABI


SOURCE = r"""
extern unsigned row_leaf();
extern unsigned start_leaf();
extern unsigned bad_leaf();
extern int written_state;

struct Holder {
  __declspec(property(get = get_row)) unsigned row;
  __declspec(property(get = get_start)) unsigned start;
  __declspec(property(get = get_bad)) unsigned bad;
  static unsigned get_row() { return row_leaf(); }
  static unsigned get_start() { return start_leaf(); }
  static unsigned get_bad() { written_state = 1; return bad_leaf(); }
};

extern const Holder object;
unsigned entry() { return object.row + object.start; }
unsigned bad_entry() { return object.bad; }
"""


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class CoordinateEffectBindingClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        source = Path(cls.temporary.name) / "coordinate_effects.cpp"
        source.write_text(SOURCE)
        report = collect(source, shutil.which("clang++"),
                         ["-std=c++17", "-fms-extensions"], "entry",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.functions = {node["name"]: node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")}

    def property_inputs(self, function_name, leaf_name, lower, upper):
        expression = next(node for node in _walk(self.functions[function_name])
                          if node.get("kind") == "PseudoObjectExpr")
        linked = link(self.root, expression)
        leaf = self.functions[leaf_name]["id"]
        domain = {
            "schema_version": "getter-leaf-domain/v1",
            "declaration_id": leaf,
            "return_type": {"qualType": "unsigned int"},
            "arguments": [], "lower": lower, "upper": upper,
        }
        pseudo = linked["pseudo_object"]
        receiver = {
            "schema_version": "property-receiver-assumptions/v1",
            "root_sha256": _hash(self.root),
            "expression_id": expression["id"],
            "receiver_id": pseudo["receiver_id"],
            "receiver_declaration_id": pseudo["receiver_declaration_id"],
            "call_id": linked["call_id"],
            "callee_declaration_id": linked["callee_declaration_id"],
            "receiver_initialized_and_alive_assumed": True,
            "extension_static_member_evaluation_assumed": True,
            "evidence_reference": "fixture-only receiver readiness premise",
        }
        effect = effect_protocol(self.root, start=linked["callee_declaration_id"], leaf=leaf)
        return linked, domain, {"effect_protocol": effect, "receiver_protocol": receiver}

    def inputs(self):
        row_link, row_domain, row_protocol = self.property_inputs("entry", "row_leaf", 0, 7)
        expressions = [node for node in _walk(self.functions["entry"])
                       if node.get("kind") == "PseudoObjectExpr"]
        start_expression = next(node for node in expressions
                                if node["id"] != row_link["pseudo_object"]["expression_id"])
        start_link = link(self.root, start_expression)
        start_leaf = self.functions["start_leaf"]["id"]
        start_domain = {
            "schema_version": "getter-leaf-domain/v1", "declaration_id": start_leaf,
            "return_type": {"qualType": "unsigned int"}, "arguments": [],
            "lower": 0, "upper": 255,
        }
        start_pseudo = start_link["pseudo_object"]
        start_receiver = {
            "schema_version": "property-receiver-assumptions/v1",
            "root_sha256": _hash(self.root),
            "expression_id": start_expression["id"],
            "receiver_id": start_pseudo["receiver_id"],
            "receiver_declaration_id": start_pseudo["receiver_declaration_id"],
            "call_id": start_link["call_id"],
            "callee_declaration_id": start_link["callee_declaration_id"],
            "receiver_initialized_and_alive_assumed": True,
            "extension_static_member_evaluation_assumed": True,
            "evidence_reference": "fixture-only receiver readiness premise",
        }
        start_protocol = {
            "effect_protocol": effect_protocol(
                self.root, start=start_link["callee_declaration_id"], leaf=start_leaf),
            "receiver_protocol": start_receiver,
        }
        side = {"checks": {"integers": {"checks": {"row_offsets": {"checks": {
            "row": {"status": "checked", "derived_leaf_domain": row_domain,
                    "prefix_recovery": {"row_initializer_evidence": {"value_link": row_link}}},
            "thread": {"status": "checked", "derived_leaf_domain": start_domain,
                       "recovery": {"initializer": {"value_link": start_link}}},
        }}}}}}
        protocol = {"integer_types": ABI, "coordinate_effects": {
            "row": row_protocol, "start": start_protocol,
        }}
        return side, protocol

    def run_check(self, side=None, protocol=None, root=None):
        default_side, default_protocol = self.inputs()
        return _coordinate_effects(
            self.root if root is None else root,
            default_protocol if protocol is None else protocol,
            default_side if side is None else side,
            max_ast_nodes=100_000,
        )

    def test_two_exact_coordinate_properties_are_checked_conditionally(self):
        result = self.run_check()
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(set(result["checks"]), {"row", "start"})
        self.assertTrue(all(item["status"] == "checked" for item in result["checks"].values()))
        self.assertFalse(result["external_premises_verified"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_missing_or_incomplete_coordinate_protocol_is_unknown(self):
        _, protocol = self.inputs()
        for changed in ({}, {"row": protocol["coordinate_effects"]["row"]},
                        {**protocol["coordinate_effects"], "extra": {}}):
            with self.subTest(keys=set(changed)):
                candidate = dict(protocol, coordinate_effects=changed)
                self.assertEqual(self.run_check(protocol=candidate)["status"], "unknown")

    def test_stale_root_and_receiver_bindings_are_unknown(self):
        side, protocol = self.inputs()
        changed = copy.deepcopy(protocol)
        changed["coordinate_effects"]["row"]["receiver_protocol"]["root_sha256"] = "0" * 64
        self.assertEqual(self.run_check(side=side, protocol=changed)["status"], "unknown")
        changed = copy.deepcopy(protocol)
        changed["coordinate_effects"]["start"]["receiver_protocol"]["receiver_id"] = "other"
        self.assertEqual(self.run_check(side=side, protocol=changed)["status"], "unknown")
        changed_root = dict(self.root, diagnostic_note="stale root")
        self.assertEqual(self.run_check(side=side, protocol=protocol, root=changed_root)["status"],
                         "unknown")

    def test_wrong_callee_or_unknown_expression_is_unknown(self):
        side, protocol = self.inputs()
        changed = copy.deepcopy(side)
        changed["checks"]["integers"]["checks"]["row_offsets"]["checks"]["row"] \
            ["prefix_recovery"]["row_initializer_evidence"]["value_link"] \
            ["callee_declaration_id"] = "other"
        self.assertEqual(self.run_check(side=changed, protocol=protocol)["status"], "unknown")
        changed = copy.deepcopy(side)
        changed["checks"]["integers"]["checks"]["row_offsets"]["checks"]["thread"] \
            ["recovery"]["initializer"]["value_link"]["pseudo_object"]["expression_id"] = "absent"
        self.assertEqual(self.run_check(side=changed, protocol=protocol)["status"], "unknown")

    def test_property_getter_with_write_is_not_applicable(self):
        side, protocol = self.inputs()
        bad_link, bad_domain, bad_protocol = self.property_inputs("bad_entry", "bad_leaf", 0, 7)
        changed = copy.deepcopy(side)
        changed_row = changed["checks"]["integers"]["checks"]["row_offsets"]["checks"]["row"]
        changed_row["prefix_recovery"]["row_initializer_evidence"]["value_link"] = bad_link
        changed_row["derived_leaf_domain"] = bad_domain
        changed_protocol = copy.deepcopy(protocol)
        changed_protocol["coordinate_effects"]["row"] = bad_protocol
        result = self.run_check(side=changed, protocol=changed_protocol)
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["checks"]["row"]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
