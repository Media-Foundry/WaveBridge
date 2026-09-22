"""Complete real TU -> fresh expression checking -> construction-time field domains."""
import copy
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.constructor_source_check import check

ABI = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False}}


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class SourceConstructorClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).parent / "fixtures/source_constructor.cpp"
        report = collect(source, shutil.which("clang++"), ["-std=c++17"], "dynamic",
                         full_translation_unit=True, dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]

    def inputs(self, name="dynamic", root=None, bounds=(1, 4096)):
        root = self.root if root is None else root
        function = next(node for node in _walk(root)
                        if node.get("kind") == "FunctionDecl" and node.get("name") == name)
        constructors = [node for node in _walk(function) if node.get("kind") == "CXXConstructExpr"]
        constructor = constructors[-1] if name == "copy_config" else constructors[0]
        domains = {}
        for argument in constructor.get("inner", []):
            if not any(node.get("kind") == "CallExpr" for node in _walk(argument)):
                continue
            references = [node["referencedDecl"] for node in _walk(argument)
                          if node.get("kind") == "DeclRefExpr" and
                          node.get("referencedDecl", {}).get("kind") == "ParmVarDecl"]
            domains[argument["id"]] = [{"declaration_id": ref["id"], "type": ref["type"],
                                        "lower": bounds[0], "upper": bounds[1]} for ref in references]
        return constructor["id"], domains

    def run_check(self, name="dynamic", bounds=(1, 4096), root=None, **kwargs):
        root = self.root if root is None else root
        expression_id, domains = self.inputs(name, root, bounds)
        return check(root, expression_id, ABI, domains, **kwargs)

    @staticmethod
    def intervals(report):
        return {field["field_name"]: field.get("interval", {"lower": field.get("value"),
                                                            "upper": field.get("value")})
                for field in report["fields"]}

    def test_dynamic_and_defaults_connect_without_rewriting_original_ast(self):
        before = copy.deepcopy(self.root)
        result = self.run_check()
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(self.intervals(result), {"x": {"lower": 1, "upper": 1024},
                         "y": {"lower": 7, "upper": 7}, "z": {"lower": 13, "upper": 13}})
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        self.assertEqual(result["constructor_arguments"]["status"], "unknown")
        self.assertEqual(result["constructor_arguments"]["reason"], "one_or_more_arguments_unknown")
        self.assertEqual(len(result["selection_checks"]), 1)
        self.assertEqual(self.root, before)

    def test_constant_and_multiple_dynamic_arguments(self):
        result = self.run_check("constant")
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(self.intervals(result)["x"], {"lower": 256, "upper": 256})
        result = self.run_check("dual")
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(self.intervals(result), {"x": {"lower": 1, "upper": 1024},
                         "y": {"lower": 1, "upper": 512}, "z": {"lower": 3, "upper": 3}})

    def test_field_positions_are_not_inferred_from_names(self):
        result = self.run_check("swapped")
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(self.intervals(result)["x"], {"lower": 7, "upper": 7})
        self.assertEqual(self.intervals(result)["y"], {"lower": 1, "upper": 1024})

    def test_wrong_function_effects_copy_and_narrowing_do_not_check(self):
        for name in ("wrong", "modified", "copy_config"):
            with self.subTest(name=name):
                result = self.run_check(name)
                self.assertNotEqual(result["status"], "checked")
                self.assertEqual(result["fields"], [])
        result = self.run_check(bounds=(-8, 40))
        self.assertEqual(result["status"], "rejected", result)

    def test_missing_extra_misbound_and_fabricated_evidence_is_not_accepted(self):
        expression_id, domains = self.inputs()
        key = next(iter(domains))
        for mutation in ("missing", "extra", "wrong_expression", "wrong_decl", "fake_checked"):
            changed = copy.deepcopy(domains)
            if mutation == "missing":
                changed.clear()
            elif mutation == "extra":
                changed["unrelated"] = copy.deepcopy(changed[key])
            elif mutation == "wrong_expression":
                changed["unrelated"] = changed.pop(key)
            elif mutation == "wrong_decl":
                changed[key][0]["declaration_id"] = "unrelated"
            else:
                changed[key] = {"status": "checked", "return_interval": {"lower": 1, "upper": 1024}}
            with self.subTest(mutation=mutation):
                self.assertNotEqual(check(self.root, expression_id, ABI, changed)["status"], "checked")

    def test_current_source_is_rechecked_and_budget_enforced(self):
        expression_id, domains = self.inputs()
        root = copy.deepcopy(self.root)
        constructor = next(node for node in _walk(root) if node.get("id") == expression_id)
        call = next(node for node in _walk(constructor) if node.get("kind") == "CallExpr")
        callee_id = call["inner"][0]["inner"][0]["referencedDecl"]["id"]
        callee = next(node for node in _walk(root) if node.get("id") == callee_id)
        conditional = next(node for node in _walk(callee) if node.get("kind") == "ConditionalOperator")
        conditional["inner"][1], conditional["inner"][2] = conditional["inner"][2], conditional["inner"][1]
        self.assertNotEqual(check(root, expression_id, ABI, domains)["status"], "checked")
        for budget in (True, 0, 1, 10_000_001):
            self.assertEqual(self.run_check(max_ast_nodes=budget)["status"], "unknown")
        self.assertEqual(check(self.root, "absent", ABI, domains)["status"], "unknown")

    def test_root_and_domain_hashes_change_with_inputs(self):
        first = self.run_check()
        second = self.run_check(bounds=(2, 4096))
        self.assertEqual(first["status"], "checked", first)
        self.assertEqual(second["status"], "checked", second)
        self.assertNotEqual(first["input_sha256"], second["input_sha256"])

    def test_malformed_literal_and_duplicate_parameter_are_not_hidden(self):
        for mutation in ("child", "category", "paren_type", "parameter", "default_type"):
            root = copy.deepcopy(self.root)
            expression_id, domains = self.inputs("constant", root)
            constructor = next(node for node in _walk(root) if node.get("id") == expression_id)
            argument = constructor["inner"][0]
            if mutation == "parameter":
                # Inspect the real declaration first, then duplicate the explicit
                # (non-default) parameter, so default-source guards cannot mask it.
                original = check(root, expression_id, ABI, domains)
                decl = original["constructor_arguments"]["default_constructor_declaration_ast"]
                parameter = next(node for node in decl["inner"] if node.get("kind") == "ParmVarDecl")
                root["inner"].append(copy.deepcopy(parameter))
            elif mutation == "default_type":
                constructor["inner"][1]["type"] = {"qualType": "int"}
            else:
                literal = next(node for node in _walk(argument) if node.get("kind") == "IntegerLiteral")
                if mutation == "child":
                    literal["inner"] = [{"kind": "CallExpr", "type": {"qualType": "int"}}]
                elif mutation == "category":
                    literal["valueCategory"] = "lvalue"
                else:
                    # IntegralCast<int -> unsigned> should not hide a type-changing paren.
                    argument["inner"] = [{"kind": "ParenExpr", "valueCategory": "prvalue",
                                           "type": {"qualType": "int"}, "inner": [
                        {"kind": "ParenExpr", "valueCategory": "prvalue",
                         "type": {"qualType": "unsigned int"}, "inner": [literal]}]}]
            with self.subTest(mutation=mutation):
                result = check(root, expression_id, ABI, domains)
                self.assertNotEqual(result["status"], "checked")
                self.assertEqual(result["fields"], [])
