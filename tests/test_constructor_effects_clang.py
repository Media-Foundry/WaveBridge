"""Constructor implementation effects, not whole call-expression effects."""
import copy
import os
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.constructor_effects import check

ABI = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False},
       "unsigned char": {"bits": 8, "signed": False}}


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class ConstructorEffectsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/constructor_effects.cpp",
                         os.environ.get("WB_VISIBILITY_COMPILER", shutil.which("clang++")), ["-std=c++17"], "effects_entry",
                         full_translation_unit=True, dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]

    def constructor(self, name="PlainValue", root=None):
        root = self.root if root is None else root
        record = next(n for n in _walk(root) if n.get("kind") == "CXXRecordDecl"
                      and n.get("name") == name and n.get("completeDefinition") is True)
        return next(n for n in record["inner"] if n.get("kind") == "CXXConstructorDecl"
                    and n.get("isImplicit") is not True)

    def test_parameter_literal_and_builtin_conversion(self):
        for name in ("PlainValue", "LiteralField", "ConvertedField"):
            with self.subTest(name=name):
                report = check(self.root, self.constructor(name)["id"], ABI)
                self.assertEqual(report["status"], "checked", report)
                self.assertFalse(report["source_program_checked"])
                self.assertFalse(report["deployable"])

    def test_body_and_initializer_publication_are_unknown(self):
        for name in ("BodyPublished", "InitializerPublished", "BodyWrite", "ArithmeticField", "ThisRead"):
            with self.subTest(name=name):
                report = check(self.root, self.constructor(name)["id"], ABI)
                self.assertEqual(report["status"], "unknown", report)

    def test_default_visibility_does_not_hide_body_effects(self):
        report = check(self.root, self.constructor("VisibleValue")["id"], ABI)
        record = next(n for n in _walk(self.root) if n.get("kind") == "CXXRecordDecl"
                      and n.get("name") == "VisibleValue" and n.get("completeDefinition"))
        attribute = next(n for n in record["inner"] if n.get("kind") == "VisibilityAttr")
        if "visibility" not in attribute:
            # Older JSON producers omit the value: do not infer it from source.
            self.assertEqual(report["status"], "unknown", report)
            self.assertEqual(report["reason"], "record_attribute_unsupported")
            return
        self.assertEqual(report["status"], "checked", report)
        self.assertEqual(len(report["record_attribute_observations"]), 1)
        self.assertEqual(report["linker_resolution_and_interposition"], "not_established")
        self.assertFalse(report["deployable"])
        bad = check(self.root, self.constructor("VisibleBodyWrite")["id"], ABI)
        self.assertEqual(bad["status"], "unknown", bad)
        self.assertEqual(bad["reason"], "constructor_body_not_unique_and_empty")

    def test_visibility_mutations_fail_closed(self):
        for mutation in ("missing", "hidden", "protected", "child", "implicit", "other_attribute"):
            root = copy.deepcopy(self.root)
            constructor = self.constructor("VisibleValue", root)
            record = next(n for n in _walk(root) if n.get("kind") == "CXXRecordDecl"
                          and any(c is constructor for c in n.get("inner", [])))
            attribute = next(n for n in record["inner"] if n.get("kind") == "VisibilityAttr")
            if mutation == "missing":
                attribute.pop("visibility", None)
            elif mutation in {"hidden", "protected"}:
                attribute["visibility"] = mutation
            elif mutation == "child":
                attribute["inner"] = [{"kind": "CallExpr"}]
            elif mutation == "implicit":
                attribute["implicit"] = "true"
            else:
                record["inner"].append({"kind": "PackedAttr"})
            with self.subTest(mutation=mutation):
                report = check(root, constructor["id"], ABI)
                self.assertEqual(report["status"], "unknown", report)
                self.assertEqual(report["reason"], "record_attribute_unsupported")

    def test_complex_record_and_parameter_types_are_unknown(self):
        for name in ("PointerField", "ReferenceField", "VolatileField", "BitField", "BaseField",
                     "VirtualField", "UnionField", "ReferenceParameter"):
            with self.subTest(name=name):
                report = check(self.root, self.constructor(name)["id"], ABI)
                self.assertEqual(report["status"], "unknown", report)

    def test_constructor_success_is_not_call_argument_nonpublication(self):
        # argument_publication actually publishes &source before invoking this
        # safe ctor. CPU execution is covered by ConstructorEscapeClangTests.
        report = check(self.root, self.constructor()["id"], ABI)
        self.assertEqual(report["status"], "checked", report)
        self.assertEqual(report["call_argument_effects"], "not_established")
        self.assertEqual(report["post_construction_escape"], "not_established")

    def test_fresh_shape_and_identity_mismatches(self):
        for mutation in ("field_id", "parameter_id", "hidden_this", "unknown_attribute",
                         "parameter_attribute", "record_attribute", "duplicate_ctor"):
            root = copy.deepcopy(self.root)
            constructor = self.constructor(root=root)
            initializer = next(n for n in constructor["inner"] if n.get("kind") == "CXXCtorInitializer")
            if mutation == "field_id":
                initializer["anyInit"]["id"] = "unrelated"
            elif mutation == "parameter_id":
                reference = next(n for n in _walk(initializer) if n.get("kind") == "DeclRefExpr")
                reference["referencedDecl"]["id"] = "unrelated"
            elif mutation == "hidden_this":
                reference = next(n for n in _walk(initializer) if n.get("kind") == "DeclRefExpr")
                reference["inner"] = [{"kind": "CXXThisExpr"}]
            elif mutation == "unknown_attribute":
                constructor["inner"].append({"kind": "UnknownSideEffectAttr"})
            elif mutation == "parameter_attribute":
                parameter = next(n for n in constructor["inner"] if n.get("kind") == "ParmVarDecl")
                parameter.setdefault("inner", []).append({"kind": "UnknownSideEffectAttr"})
            elif mutation == "record_attribute":
                record = next(n for n in _walk(root) if n.get("kind") == "CXXRecordDecl"
                              and any(c is constructor for c in n.get("inner", [])))
                record["inner"].append({"kind": "UnknownSideEffectAttr"})
            else:
                root["inner"].append(copy.deepcopy(constructor))
            with self.subTest(mutation=mutation):
                self.assertEqual(check(root, constructor["id"], ABI)["status"], "unknown")

    def test_budget_missing_abi_and_immutability(self):
        before = copy.deepcopy(self.root)
        constructor_id = self.constructor()["id"]
        self.assertEqual(check(self.root, constructor_id, ABI)["status"], "checked")
        self.assertEqual(before, self.root)
        self.assertEqual(check(self.root, constructor_id, {})["status"], "unknown")
        for budget in (0, True, 1, 10_000_001):
            self.assertEqual(check(self.root, constructor_id, ABI, max_ast_nodes=budget)["status"], "unknown")
