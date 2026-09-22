"""Copy-time field equality is deliberately separate from object history."""
import copy
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.record_copy_check import check

ABI = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False}}


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class RecordCopyClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/record_copy.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "implicit_copy",
                         full_translation_unit=True, dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]

    def inputs(self, name="implicit_copy", root=None):
        root = self.root if root is None else root
        function = next(node for node in _walk(root)
                        if node.get("kind") == "FunctionDecl" and node.get("name") == name)
        target = next(node for node in _walk(function)
                      if node.get("kind") == "VarDecl" and node.get("name") == "target")
        expression = next(node for node in _walk(target) if node.get("kind") == "CXXConstructExpr")
        source = next(node for node in function.get("inner", []) if node.get("kind") == "ParmVarDecl") if name == "parameter_copy" else next(
            node for node in _walk(function) if node.get("kind") == "VarDecl" and node.get("name") == "source")
        return expression["id"], source["id"]

    def run_check(self, name="implicit_copy", root=None, **kwargs):
        root = self.root if root is None else root
        expression_id, _ = self.inputs(name, root)
        return check(root, expression_id, ABI, **kwargs)

    def test_implicit_manual_and_parameter_copies_preserve_same_field_ids(self):
        for name, count in (("implicit_copy", 3), ("manual_copy", 2), ("parameter_copy", 3)):
            with self.subTest(name=name):
                result = self.run_check(name)
                self.assertEqual(result["status"], "checked", result)
                self.assertEqual(result["source_declaration_id"], self.inputs(name)[1])
                self.assertEqual(len(result["field_mappings"]), count)
                for mapping in result["field_mappings"]:
                    self.assertEqual(mapping["target_field_id"], mapping["source_field_id"])
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_copy_does_not_prove_source_preservation_since_initialization(self):
        result = self.run_check("changed_before_copy")
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["source_object_preservation"], "not_established")
        self.assertEqual(result["launch_semantics"], "not_established")
        self.assertNotIn("fields", result)  # No fabricated construction-time numeric values.

    def test_bad_or_unsupported_copies_never_check(self):
        for name in ("alias_copy", "swapped_copy", "writing_copy", "bitfield_copy",
                     "volatile_copy", "union_copy", "pointer_copy", "polymorphic_copy"):
            with self.subTest(name=name):
                result = self.run_check(name)
                self.assertNotEqual(result["status"], "checked")
                self.assertEqual(result["field_mappings"], [])

    def test_capture_does_not_establish_runtime_source_object_identity(self):
        result = self.run_check("captured_copy")
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["source_declaration_id"], self.inputs("captured_copy")[1])
        self.assertEqual(result["source_declaration_binding"], "lexical_declref_only")
        self.assertEqual(result["source_object_identity"], "not_established")
        self.assertEqual(result["source_object_preservation"], "not_established")
        self.assertNotIn("fields", result)

    def test_misbound_source_and_duplicate_expression_are_rejected(self):
        for mutation in ("source_id", "source_type", "duplicate_expression", "reference_source"):
            root = copy.deepcopy(self.root)
            expression_id, source_id = self.inputs(root=root)
            expression = next(node for node in _walk(root) if node.get("id") == expression_id)
            reference = next(node for node in _walk(expression) if node.get("kind") == "DeclRefExpr")
            if mutation == "source_id":
                reference["referencedDecl"]["id"] = "absent"
            elif mutation == "source_type":
                reference["referencedDecl"]["type"] = {"qualType": "int"}
            elif mutation == "duplicate_expression":
                conflicting = copy.deepcopy(expression)
                conflicting["constructionKind"] = "non-virtual base"
                root["inner"].append(conflicting)
            else:
                source = next(node for node in _walk(root) if node.get("id") == source_id)
                source["type"] = {"qualType": "Plain &"}
            with self.subTest(mutation=mutation):
                self.assertNotEqual(check(root, expression_id, ABI)["status"], "checked")

    def test_budget_missing_id_and_missing_abi_are_unknown(self):
        for budget in (0, True, 1, 10_000_001):
            self.assertEqual(self.run_check(max_ast_nodes=budget)["status"], "unknown")
        expression_id, _ = self.inputs()
        self.assertEqual(check(self.root, "missing", ABI)["status"], "unknown")
        self.assertEqual(check(self.root, expression_id, {})["status"], "unknown")

    def test_checker_binds_inputs_without_mutating_root(self):
        before = copy.deepcopy(self.root)
        result = self.run_check()
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(self.root, before)
        self.assertIn("input_sha256", result)

    def test_identical_same_id_occurrences_are_not_execution_counts(self):
        root = copy.deepcopy(self.root)
        expression_id, _ = self.inputs(root=root)
        expression = next(node for node in _walk(root) if node.get("id") == expression_id)
        root["inner"].append(copy.deepcopy(expression))
        result = check(root, expression_id, ABI)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["expression_ast_occurrences"], 2)
        self.assertEqual(result["launch_semantics"], "not_established")

    def test_initializer_and_member_identity_are_checked_from_current_root(self):
        for mutation in ("missing", "field_duplicate", "parameter", "member", "arrow", "hidden_child"):
            root = copy.deepcopy(self.root)
            expression_id, _ = self.inputs(root=root)
            original = check(root, expression_id, ABI)
            constructor = next(node for node in _walk(root)
                               if node.get("id") == original["constructor_declaration_id"])
            initializer = next(node for node in constructor["inner"] if node.get("kind") == "CXXCtorInitializer")
            member = next(node for node in _walk(initializer) if node.get("kind") == "MemberExpr")
            base = member["inner"][0]
            if mutation == "missing":
                constructor["inner"].remove(initializer)
            elif mutation == "field_duplicate":
                field_id = initializer["anyInit"]["id"]
                field = next(node for node in _walk(root) if node.get("kind") == "FieldDecl" and node.get("id") == field_id)
                root["inner"].append(copy.deepcopy(field))
            elif mutation == "parameter":
                base["referencedDecl"]["id"] = "unrelated"
            elif mutation == "member":
                member["referencedMemberDecl"] = "unrelated"
            elif mutation == "arrow":
                member["isArrow"] = True
            else:
                base["inner"] = [{"kind": "CallExpr"}]
            with self.subTest(mutation=mutation):
                result = check(root, expression_id, ABI)
                self.assertNotEqual(result["status"], "checked")
                self.assertEqual(result["field_mappings"], [])
