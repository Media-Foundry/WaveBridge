"""Concrete function-template instances in the object initialization/use chain."""

import copy
import os
from pathlib import Path
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect
from wavebridge.verification.constructor_argument_effects import check as check_arguments
from wavebridge.verification.integer_selection import _hash
from wavebridge.verification.object_initialization import check as check_initialization
from wavebridge.verification.object_use_closure import inspect_structure


PLUGIN = os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")
ABI = {
    "int": {"bits": 32, "signed": True},
    "unsigned int": {"bits": 32, "signed": False},
}


@unittest.skipUnless(PLUGIN, "requires compiler-matched native capture plugin")
class ObjectTemplateScopeClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(
            Path(__file__).parent / "fixtures/object_template_scope.cpp",
            COMPILER,
            Path(PLUGIN),
            ["-std=c++17"],
        )
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.payload = report["payload"]

    def concrete_function(self, payload, name):
        matches = []
        for node in _walk(payload["ast"]):
            if node.get("kind") != "FunctionDecl" or node.get("name") != name:
                continue
            children = node.get("inner", [])
            arguments = [child for child in children
                         if child.get("kind") == "TemplateArgument"]
            if (any(child.get("kind") == "CompoundStmt" for child in children) and
                    len(arguments) == 2 and
                    arguments[0].get("type", {}).get("qualType") == "int" and
                    arguments[1].get("value") == 7):
                matches.append(node)
        self.assertEqual(len(matches), 1, (name, matches))
        return matches[0]

    def inputs(self, payload, name):
        function = self.concrete_function(payload, name)
        source = next(node for node in _walk(function)
                      if node.get("kind") == "VarDecl" and node.get("name") == "source")
        constructor = next(node for node in _walk(source)
                           if node.get("kind") == "CXXConstructExpr")
        domains = {}
        for argument in constructor.get("inner", []):
            if not any(node.get("kind") == "CallExpr" for node in _walk(argument)):
                continue
            references = {
                node["referencedDecl"]["id"]: node["referencedDecl"]
                for node in _walk(argument)
                if node.get("kind") == "DeclRefExpr" and
                node.get("referencedDecl", {}).get("kind") in {"VarDecl", "ParmVarDecl"}
            }
            domains[argument["id"]] = [
                {"declaration_id": identifier, "type": declaration["type"],
                 "lower": 1, "upper": 4096}
                for identifier, declaration in references.items()
            ]
        return function, source, constructor, domains

    def reports(self, payload, name, selected_id=None):
        function, source, constructor, domains = self.inputs(payload, name)
        selected_id = function["id"] if selected_id is None else selected_id
        return self.reports_from_ids(
            payload, selected_id, source["id"], constructor["id"], domains)

    def reports_from_ids(self, payload, selected_id, source_id, constructor_id, domains):
        return (
            check_arguments(
                payload["ast"], constructor_id, ABI, domains,
                instantiated_function_id=selected_id,
            ),
            check_initialization(
                payload, source_id, ABI, domains,
                instantiated_function_id=selected_id,
            ),
            inspect_structure(
                payload, source_id, ABI, domains,
                instantiated_function_id=selected_id,
            ),
        )

    def test_literal_and_minimum_instances_compose_all_three_layers(self):
        for name in ("literal_init", "selected_init"):
            with self.subTest(name=name):
                arguments, initialization, uses = self.reports(self.payload, name)
                self.assertEqual(arguments["status"], "checked", arguments)
                self.assertEqual(initialization["status"], "checked", initialization)
                self.assertEqual(uses["status"], "checked", uses)
                function, source, _, _ = self.inputs(self.payload, name)
                self.assertEqual(arguments["concrete_caller"]["function_id"], function["id"])
                self.assertEqual(initialization["concrete_caller"]["function_id"], function["id"])
                self.assertEqual(
                    uses["conditional_initialization"]["concrete_caller"]["function_id"],
                    function["id"],
                )
                for report in (arguments, initialization, uses):
                    self.assertEqual(
                        report["input_sha256"]["instantiated_function_id"],
                        _hash(function["id"]),
                    )
                self.assertEqual(uses["function_id"], function["id"])
                self.assertEqual(uses["variable_id"], source["id"])
                self.assertEqual(uses["copy_count"], 1)
                self.assertEqual(len(uses["copy_structures"]), 1)
                self.assertEqual(uses["source_object_preservation"], "not_established")
                self.assertFalse(uses["source_program_checked"])
                self.assertFalse(uses["deployable"])

    def test_opt_in_is_required_and_default_behavior_stays_unknown(self):
        for name in ("literal_init", "selected_init"):
            function, source, constructor, domains = self.inputs(self.payload, name)
            reports = (
                check_arguments(self.payload["ast"], constructor["id"], ABI, domains),
                check_initialization(self.payload, source["id"], ABI, domains),
                inspect_structure(self.payload, source["id"], ABI, domains),
            )
            with self.subTest(name=name, function_id=function["id"]):
                self.assertTrue(all(report["status"] == "unknown" for report in reports), reports)

    def test_wrong_instance_or_template_pattern_does_not_select_the_body(self):
        literal, _, _, _ = self.inputs(self.payload, "literal_init")
        other = self.concrete_function(self.payload, "selected_init")
        template = next(node for node in _walk(self.payload["ast"])
                        if node.get("kind") == "FunctionTemplateDecl" and
                        node.get("name") == "literal_init")
        for selected_id in (other["id"], template["id"], "missing-function"):
            with self.subTest(selected_id=selected_id):
                reports = self.reports(self.payload, "literal_init", selected_id)
                self.assertTrue(all(report["status"] == "unknown" for report in reports),
                                (literal["id"], reports))

    def test_dependent_duplicate_or_bodyless_selected_entity_is_unknown(self):
        for mutation in ("dependent", "duplicate", "missing_body",
                         "malformed_integral_argument", "missing_mangled_name"):
            payload = copy.deepcopy(self.payload)
            function, source, constructor, domains = self.inputs(payload, "literal_init")
            selected_id = function["id"]
            source_id = source["id"]
            constructor_id = constructor["id"]
            if mutation == "dependent":
                function["isDependent"] = True
            elif mutation == "duplicate":
                payload["ast"].setdefault("inner", []).append(copy.deepcopy(function))
            elif mutation == "malformed_integral_argument":
                argument = next(child for child in function["inner"]
                                if child.get("kind") == "TemplateArgument" and
                                child.get("value") == 7)
                argument["type"] = {"qualType": "float"}
            elif mutation == "missing_mangled_name":
                function.pop("mangledName", None)
            else:
                function["inner"] = [child for child in function.get("inner", [])
                                     if child.get("kind") != "CompoundStmt"]
            with self.subTest(mutation=mutation):
                reports = self.reports_from_ids(
                    payload, selected_id, source_id, constructor_id, domains)
                self.assertTrue(all(report["status"] == "unknown" for report in reports), reports)

    def test_constructor_identity_shared_across_instances_is_unknown(self):
        payload = copy.deepcopy(self.payload)
        literal_function, literal_source, literal_constructor, literal_domains = self.inputs(
            payload, "literal_init")
        _, _, other_constructor, _ = self.inputs(payload, "selected_init")
        other_constructor["id"] = literal_constructor["id"]
        reports = self.reports_from_ids(
            payload,
            literal_function["id"],
            literal_source["id"],
            literal_constructor["id"],
            literal_domains,
        )
        self.assertTrue(all(report["status"] == "unknown" for report in reports), reports)

    def test_direct_dynamic_constructor_argument_remains_unknown(self):
        arguments, initialization, uses = self.reports(self.payload, "direct_dynamic_init")
        self.assertEqual(arguments["status"], "unknown", arguments)
        self.assertEqual(initialization["status"], "unknown", initialization)
        self.assertEqual(uses["status"], "unknown", uses)
        self.assertFalse(uses["source_program_checked"])
        self.assertFalse(uses["deployable"])


if __name__ == "__main__":
    unittest.main()
