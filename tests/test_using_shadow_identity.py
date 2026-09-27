"""Representation fixtures, not compiler observations or source semantics."""
from copy import deepcopy
import unittest

from wavebridge.verification.using_shadow_identity import UsingShadowIndex, IdentityUnknown


def fixture():
    declaration = {"kind": "FunctionDecl", "id": "function", "name": "f",
                   "type": {"qualType": "float (float)"},
                   "loc": {"offset": 0, "col": 1, "tokLen": 1},
                   "inner": [{"kind": "ParmVarDecl", "id": "parameter",
                              "name": "x", "type": {"qualType": "float"}}]}
    shadow = {"kind": "UsingShadowDecl", "id": "shadow", "isImplicit": True,
              "target": {key: declaration[key] for key in ("id", "kind", "name", "type")},
              "inner": [deepcopy(declaration)]}
    root = {"kind": "TranslationUnitDecl", "inner": [declaration, shadow]}
    return root, declaration, shadow


class UsingShadowIdentityTests(unittest.TestCase):
    def test_returns_original_objects_not_reference_copies(self):
        root, original, shadow = fixture()
        frozen = deepcopy(root)
        index = UsingShadowIndex(root, 100)
        self.assertIs(index.unique("function"), original)
        self.assertIs(index.unique("parameter"), original["inner"][0])
        self.assertEqual(root, frozen)
        self.assertEqual(len(index.observations), 1)
        self.assertEqual(index.observations[0]["match"], "exact")

    def test_identical_ordinary_duplicates_are_not_using_references(self):
        root, original, _ = fixture()
        root["inner"].append(deepcopy(original))
        with self.assertRaises(IdentityUnknown):
            UsingShadowIndex(root, 100).unique("function")

    def test_matching_function_does_not_hide_duplicate_ordinary_descendant(self):
        root, original, _ = fixture()
        root["inner"].append(deepcopy(original["inner"][0]))
        index = UsingShadowIndex(root, 100)
        self.assertIs(index.unique("function"), original)
        with self.assertRaisesRegex(IdentityUnknown, "ordinary_ast_identity_not_unique"):
            index.unique("parameter")

    def test_multiple_shadows_must_all_match(self):
        root, original, shadow = fixture()
        second = deepcopy(shadow)
        second["id"] = "second-shadow"
        root["inner"].append(second)
        index = UsingShadowIndex(root, 100)
        self.assertIs(index.unique("parameter"), original["inner"][0])
        self.assertEqual(len(index.observations), 2)
        second["inner"][0]["inner"][0]["type"] = {"qualType": "double"}
        with self.assertRaises(IdentityUnknown):
            UsingShadowIndex(root, 100).unique("parameter")

    def test_root_location_omission_does_not_allow_other_missing_metadata(self):
        root, original, shadow = fixture()
        shadow["inner"][0]["loc"]["file"] = "source.h"
        self.assertIs(UsingShadowIndex(root, 100).unique("function"), original)
        for key in ("offset", "col", "tokLen"):
            changed = deepcopy(root)
            del changed["inner"][1]["inner"][0]["loc"][key]
            with self.subTest(key=key), self.assertRaises(IdentityUnknown):
                UsingShadowIndex(changed, 100).unique("function")

    def test_shadow_target_owner_and_budget_are_checked(self):
        for variant in ("target", "implicit", "owner", "missing", "extra_child"):
            root, original, shadow = fixture()
            if variant == "target":
                shadow["target"]["id"] = "other"
            elif variant == "implicit":
                shadow["isImplicit"] = False
            elif variant == "owner":
                shadow["kind"] = "NamespaceDecl"
            elif variant == "missing":
                root["inner"].remove(original)
            else:
                shadow["inner"].append({"kind": "UnknownEffect"})
            with self.subTest(variant=variant), self.assertRaises(IdentityUnknown):
                UsingShadowIndex(root, 100).unique("parameter")
        with self.assertRaisesRegex(IdentityUnknown, "ast_node_budget_exceeded"):
            UsingShadowIndex(fixture()[0], 1)


if __name__ == "__main__":
    unittest.main()
