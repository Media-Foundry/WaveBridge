"""Real source default provenance -> field checks; no injected default values."""
import copy
from pathlib import Path
import shutil
import unittest

from wavebridge.analysis.constructor_arguments import inspect
from wavebridge.analysis.constructor_fields import recover
from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.constructor_values import check
from tests.test_getter_returns import ABI


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class ConstructorDefaultsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/constructor_defaults.cpp",
                         shutil.which("clang++"), ["-std=c++20"], "good",
                         full_translation_unit=True, dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]
        cls.functions = {node["name"]: node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")}

    def inputs(self, name="good", root=None):
        root = self.root if root is None else root
        function = next(node for node in _walk(root) if node.get("id") == self.functions[name]["id"])
        expression = next(node for node in _walk(function) if node.get("kind") == "CXXConstructExpr")
        arguments = inspect(root, expression, 32)
        fields = recover(root, arguments.get("constructor_declaration_id"))
        return arguments, fields

    def test_nonunit_defaults_reach_checker_with_raw_call_preserved(self):
        before = copy.deepcopy(self.root)
        arguments, fields = self.inputs()
        self.assertEqual(arguments["status"], "inspected", arguments)
        for position, value in ((1, 7), (2, 13)):
            item = arguments["arguments"][position]
            self.assertEqual(item["pre_conversion_constant"]["value"], value)
            if item["argument_ast"].get("inner", []):
                # Newer Clang dumps the real expression directly: keep using
                # that pre-existing path, without inventing a declaration link.
                self.assertEqual(item["default_source_ast"], item["argument_ast"]["inner"][0])
                self.assertIsNone(item["default_source_binding"])
            else:
                self.assertEqual(item["default_source_binding"]["parameter_position"], position)
                self.assertEqual(item["default_source_binding"]["parameter_id"],
                                 fields["field_mappings"][position]["parameter_id"])
        result = check(arguments, fields, ABI)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual([field["value"] for field in result["fields"]], [256, 7, 13])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        self.assertEqual(self.root, before)

    def test_calls_redeclarations_and_immediate_defaults_remain_unknown(self):
        for name in ("called", "redeclared", "immediate"):
            with self.subTest(name=name):
                arguments, fields = self.inputs(name)
                source_less = any(item["default_argument"] and not item["argument_ast"].get("inner")
                                  for item in arguments["arguments"])
                if name != "redeclared" or source_less:
                    self.assertEqual(arguments["status"], "unknown", arguments)
                self.assertEqual(check(arguments, fields, ABI)["status"], "unknown")

    def test_narrowing_is_not_confused_with_default_provenance(self):
        arguments, fields = self.inputs("narrow")
        result = check(arguments, fields, ABI)
        self.assertNotEqual(result["status"], "checked", result)
        if arguments["status"] == "inspected":
            self.assertEqual(result["status"], "rejected", result)
            self.assertEqual(result["reason"], "integer_conversion_not_value_preserving")

    def test_checker_rejects_missing_and_tampered_default_binding(self):
        if self.inputs()[0]["arguments"][1]["default_source_binding"] is None:
            self.skipTest("compiler already exposes default source; declaration-link path not used")
        for mutation in ("constructor", "parameter", "position", "source", "casts", "raw_type", "paren_type", "missing"):
            arguments, fields = self.inputs()
            arguments = copy.deepcopy(arguments)
            item = arguments["arguments"][1]
            if mutation == "constructor":
                item["default_source_binding"]["constructor_declaration_id"] = "other"
            elif mutation == "parameter":
                item["default_source_binding"]["parameter_id"] = "other"
            elif mutation == "position":
                item["default_source_binding"]["parameter_position"] = 2
            elif mutation == "source":
                item["default_source_ast"] = copy.deepcopy(arguments["arguments"][2]["default_source_ast"])
            elif mutation == "casts":
                item["casts"] = []
            elif mutation == "raw_type":
                item["argument_ast"]["type"] = {"qualType": "int"}
            elif mutation == "paren_type":
                source = item["default_source_ast"]
                literal = source["inner"][0]
                source["inner"] = [{"kind": "ParenExpr", "type": literal["type"], "inner": [
                    {"kind": "ParenExpr", "type": {"qualType": "unsigned int"}, "inner": [literal]}]}]
            else:
                del arguments["default_constructor_declaration_ast"]
            with self.subTest(mutation=mutation):
                result = check(arguments, fields, ABI)
                self.assertNotEqual(result["status"], "checked")
                if mutation == "paren_type":
                    self.assertEqual(result["reason"], "default_source_parenthesis_type_mismatch")

    def test_missing_or_shared_parameter_source_cannot_be_invented(self):
        if self.inputs()[0]["arguments"][1]["default_source_binding"] is None:
            self.skipTest("compiler already exposes default source; declaration-link path not used")
        for mutation in ("missing", "shared", "redecl"):
            root = copy.deepcopy(self.root)
            arguments, _ = self.inputs(root=root)
            constructor_id = arguments["constructor_declaration_id"]
            constructor = next(node for node in _walk(root) if node.get("id") == constructor_id)
            parameters = [node for node in constructor["inner"] if node.get("kind") == "ParmVarDecl"]
            if mutation == "missing":
                parameters[1]["inner"] = []
            elif mutation == "shared":
                root["inner"].append(copy.deepcopy(parameters[1]["inner"][0]))
            else:
                root["inner"].append({"kind": "CXXConstructorDecl", "id": "later", "previousDecl": constructor_id})
            with self.subTest(mutation=mutation):
                result, _ = self.inputs(root=root)
                self.assertEqual(result["status"], "unknown", result)
