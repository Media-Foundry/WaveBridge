from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.analysis.constructor_fields import recover


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class ConstructorFieldClangTests(unittest.TestCase):
    def test_parameter_permutation_is_recovered_and_body_mutation_is_unknown(self):
        frontend = collect(Path(__file__).parent / "fixtures/constructor_fields.cpp",
                           shutil.which("clang++"), ["-std=c++17"], "entry",
                           full_translation_unit=True)
        self.assertEqual(frontend["status"], "collected")
        root = frontend["ast_roots"][0]
        constructors = {node["name"]: node["id"] for node in _walk(root)
                        if node.get("kind") == "CXXConstructorDecl" and
                        any(child.get("kind") == "CompoundStmt" for child in node.get("inner", []))}
        result = recover(root, constructors["Permuted"],)
        self.assertEqual(result["status"], "recovered", result)
        mapping = {field["field_name"]: field["parameter_position"] for field in result["field_mappings"]}
        self.assertEqual(mapping, {"left": 1, "right": 0})
        self.assertFalse(result["checked"])
        self.assertEqual(recover(root, constructors["BodyWrites"])["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
