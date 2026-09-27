"""Real Clang using references; mutated AST negatives are explicitly fixtures."""
from copy import deepcopy
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.scalar_forwarding import inspect_structure
from wavebridge.verification.scalar_call_effects import check_no_memory_write

CLANG = os.environ.get("WB_USING_SHADOW_COMPILER") or shutil.which("clang++")


@unittest.skipUnless(CLANG, "requires real clang++")
class UsingShadowIdentityClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-using-shadow-")
        directory = Path(cls.temporary.name)
        (directory / "api.h").write_text("""
float selected_leaf(float value);
float global_value;
inline float middle(float renamed) { return selected_leaf(renamed); }
inline float writing(float renamed) { global_value = renamed; return selected_leaf(renamed); }
""")
        source = directory / "using.cpp"
        source.write_text("""
#include "api.h"
namespace imported { using ::middle; using ::selected_leaf; using ::writing; }
float outer(float value) { return imported::middle(value); }
float bad_argument(float value) { return imported::middle(value++); }
float bad_wrapper(float value) { return imported::writing(value); }
""")
        report = collect(source, CLANG, ["-std=c++17"], "outer", full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]
        cls.expansions = [node for node in _walk(cls.root) if node.get("kind") == "UsingShadowDecl"
                          and node.get("inner")]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        if not self.expansions:
            self.skipTest("compiler does not emit expanded UsingShadowDecl function references")

    def declaration(self, name, root=None):
        return next(node for node in (self.root if root is None else root)["inner"]
                    if node.get("kind") == "FunctionDecl" and node.get("name") == name)

    def shadow(self, root, name="middle"):
        return next(node for node in _walk(root) if node.get("kind") == "UsingShadowDecl"
                    and node.get("target", {}).get("name") == name and node.get("inner"))

    def check(self, root=None, name="outer", **options):
        root = self.root if root is None else root
        return inspect_structure(root, self.declaration(name, root)["id"],
                                 self.declaration("selected_leaf", root)["id"], **options)

    def test_real_expansion_is_opt_in_and_keeps_original_ast(self):
        before = _hash(self.root)
        self.assertEqual(self.check()["status"], "unknown")
        report = self.check(allow_using_shadows=True)
        self.assertEqual(report["status"], "checked", report)
        self.assertTrue(report["using_shadow_references"])
        self.assertEqual(before, _hash(self.root))
        self.assertFalse(report["source_program_checked"])
        self.assertFalse(report["deployable"])
        self.assertEqual(report["effect_semantics"], "not_established")

    def test_call_composition_keeps_argument_and_external_leaf_obligations(self):
        for name, expected in (("outer", "checked"), ("bad_argument", "unknown"),
                               ("bad_wrapper", "unknown")):
            with self.subTest(name=name):
                call = next(n for n in _walk(self.declaration(name)) if n.get("kind") == "CallExpr")
                protocol = {"schema_version": "scalar-leaf-effect-assumption/v1",
                            "root_sha256": _hash(self.root), "call_expression_id": call["id"],
                            "leaf_declaration_id": self.declaration("selected_leaf")["id"],
                            "leaf_no_memory_write_assumed": True,
                            "valid_call_and_normal_return_assumed": True,
                            "evidence_reference": "explicit test assumption, not established"}
                result = check_no_memory_write(self.root, call["id"], protocol, allow_using_shadows=True)
                self.assertEqual(result["status"], expected, result)
                self.assertFalse(result["external_leaf_effect_verified"])
                self.assertFalse(result["deployable"])
                if expected == "checked":
                    self.assertEqual(result["conclusion"]["status"], "conditional")
                    self.assertEqual(check_no_memory_write(self.root, call["id"], protocol)["status"], "unknown")

    def test_source_wrapper_side_effect_is_not_hidden_by_using(self):
        result = self.check(name="writing", allow_using_shadows=True)
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["reason"], "wrapper_not_single_return")

    def test_mutated_type_body_target_or_location_conflicts_are_unknown(self):
        for variant in ("parameter", "body", "target", "offset", "nested_location", "implicit"):
            with self.subTest(variant=variant):
                root = deepcopy(self.root)
                shadow = self.shadow(root)
                reference = shadow["inner"][0]
                if variant == "parameter":
                    reference["inner"][0]["type"]["qualType"] = "double"
                elif variant == "body":
                    reference["inner"].append({"kind": "UnknownEffect", "id": "extra"})
                elif variant == "target":
                    shadow["target"]["id"] = "wrong"
                elif variant == "offset":
                    reference["loc"]["offset"] += 1
                elif variant == "nested_location":
                    reference["inner"][0]["loc"]["file"] = "different.h"
                else:
                    shadow["isImplicit"] = 1
                result = self.check(root, allow_using_shadows=True)
                self.assertEqual(result["status"], "unknown", result)

    def test_root_file_omission_is_narrow_and_two_explicit_files_must_match(self):
        root = deepcopy(self.root)
        ordinary = self.declaration("middle", root)
        reference = self.shadow(root)["inner"][0]
        # An explicit representation fixture, not a new compiler observation.
        reference["loc"] = deepcopy(ordinary["loc"])
        ordinary["loc"].pop("file", None)
        reference["loc"]["file"] = str(Path(self.temporary.name) / "api.h")
        accepted = self.check(root, allow_using_shadows=True)
        self.assertEqual(accepted["status"], "checked", accepted)
        self.assertIn("root_loc_file_omission_only", [x["match"] for x in accepted["using_shadow_references"]])
        ordinary["loc"]["file"] = "different.h"
        self.assertEqual(self.check(root, allow_using_shadows=True)["status"], "unknown")

    def test_missing_or_duplicate_ordinary_definition_is_not_repaired(self):
        for duplicate in (False, True):
            root = deepcopy(self.root)
            ordinary = self.declaration("middle", root)
            if duplicate:
                root["inner"].append(deepcopy(ordinary))
            else:
                root["inner"].remove(ordinary)
            self.assertEqual(self.check(root, allow_using_shadows=True)["status"], "unknown")

    def test_explicit_opt_in_and_budget_are_strict(self):
        for options in ({"allow_using_shadows": 1}, {"allow_using_shadows": True, "max_ast_nodes": 1}):
            self.assertEqual(self.check(**options)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
