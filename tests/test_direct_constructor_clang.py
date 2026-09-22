"""Real declaration-anchored constructor lookup; copy effects stay unknown."""
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
class DirectConstructorClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/direct_constructor.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "entry",
                         full_translation_unit=True, dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]

    def expressions(self, root=None):
        return [node for node in _walk(self.root if root is None else root)
                if node.get("kind") == "CXXConstructExpr"]

    def test_direct_values_reach_existing_field_checker_without_name_matching(self):
        seen = []
        for expression in self.expressions():
            if len(expression.get("inner", [])) != 3:
                continue
            if any(argument.get("kind") == "CXXDefaultArgExpr" for argument in expression["inner"]):
                continue
            report = inspect(self.root, expression, 32)
            if report["status"] != "inspected":
                continue  # Calls and missing default sources remain unsupported.
            fields = recover(self.root, report["constructor_declaration_id"])
            result = check(report, fields, ABI)
            self.assertEqual(result["status"], "checked", result)
            values = [field["value"] for field in result["fields"]]
            seen.append((report["constructor_identity"]["record_declaration_id"], values))
            self.assertFalse(report["checked"])
            self.assertFalse(result["deployable"])
        self.assertEqual(len(seen), 2)
        self.assertNotEqual(seen[0][0], seen[1][0])
        self.assertEqual([item[1] for item in seen], [[256, 1, 1], [128, 1, 1]])

    def test_copy_identity_does_not_imply_copy_field_semantics(self):
        copies = [expression for expression in self.expressions() if len(expression["inner"]) == 1]
        self.assertEqual(len(copies), 4)
        for expression in copies:
            report = inspect(self.root, expression, 32)
            self.assertEqual(report["status"], "inspected", report)
            self.assertEqual(report["arguments"][0]["status"], "symbolic")
            self.assertEqual(report["constructor_identity"]["copy_or_move_semantics"], "not_established")
            fields = recover(self.root, report["constructor_declaration_id"])
            self.assertEqual(check(report, fields, ABI)["status"], "unknown")

    def test_calls_and_missing_default_sources_still_block_values(self):
        calls, defaults = 0, 0
        for expression in self.expressions():
            if len(expression["inner"]) != 3:
                continue
            report = inspect(self.root, expression, 32)
            self.assertIsNotNone(report["constructor_declaration_id"])
            for argument in report["arguments"]:
                if argument["reason"] == "unsupported_argument_expression":
                    calls += 1
                    self.assertEqual(report["status"], "unknown")
                if argument["default_argument"]:
                    defaults += 1
                    if argument["default_source_ast"] is None:
                        self.assertEqual(report["status"], "unknown")
                        self.assertEqual(argument["reason"], "default_argument_source_missing_or_ambiguous")
                    else:
                        self.assertEqual(argument["pre_conversion_constant"]["value"], 1)
        self.assertEqual((calls, defaults), (1, 2))

    def test_missing_anchor_wrong_signature_and_budgets_fail_closed(self):
        expression = self.expressions()[0]
        for mutation in ("no_anchor", "wrong_anchor", "wrong_type", "wrong_signature", "base"):
            changed = copy.deepcopy(expression)
            if mutation == "no_anchor":
                del changed["type"]["typeAliasDeclId"]
            elif mutation == "wrong_anchor":
                changed["type"]["typeAliasDeclId"] = "absent"
            elif mutation == "wrong_type":
                changed["type"]["desugaredQualType"] = "unrelated::Shape"
            elif mutation == "wrong_signature":
                changed["ctorType"]["qualType"] = "void (double)"
            else:
                changed["constructionKind"] = "non-virtual base"
            with self.subTest(mutation=mutation):
                self.assertEqual(inspect(self.root, changed, 32)["status"], "unknown")
        for budget in (1, 0, True, 10_000_001):
            self.assertEqual(inspect(self.root, expression, 32, max_ast_nodes=budget)["status"], "unknown")

    def test_record_and_declaration_ambiguity_cannot_select_a_constructor(self):
        for mutation in ("duplicate_alias", "duplicate_record", "duplicate_ctor_id",
                         "same_signature", "template", "inherited"):
            root = copy.deepcopy(self.root)
            expression = self.expressions(root)[0]
            identity = inspect(root, expression, 32)["constructor_identity"]
            nodes = {node.get("id"): node for node in _walk(root)}
            record = nodes[identity["record_declaration_id"]]
            constructor = nodes[identity["constructor_declaration_id"]]
            if mutation == "duplicate_alias":
                root["inner"].append(copy.deepcopy(nodes[identity["alias_declaration_id"]]))
            elif mutation == "duplicate_record":
                root["inner"].append(copy.deepcopy(record))
            elif mutation == "duplicate_ctor_id":
                root["inner"].append({"id": constructor["id"], "kind": "VarDecl"})
            elif mutation == "same_signature":
                record["inner"].append(dict(constructor, id="second-ctor"))
            elif mutation == "template":
                record["inner"].append({"kind": "FunctionTemplateDecl", "inner": []})
            else:
                record["bases"] = [{"type": {"qualType": "Base"}}]
            with self.subTest(mutation=mutation):
                self.assertEqual(inspect(root, expression, 32)["status"], "unknown")
