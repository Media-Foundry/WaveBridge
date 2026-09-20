from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.analysis.constructor_arguments import inspect


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class ConstructorArgumentClangTests(unittest.TestCase):
    def test_explicit_constructor_values_and_default_evidence_boundary(self):
        frontend = collect(Path(__file__).parent / "fixtures/constructor_arguments.cpp",
                           shutil.which("clang++"), ["-std=c++17"], "entry",
                           full_translation_unit=True)
        self.assertEqual(frontend["status"], "collected")
        root = frontend["ast_roots"][0]
        functions = {node["name"]: node for node in _walk(root)
                     if node.get("kind") == "FunctionDecl"}
        expression = next(node for node in _walk(functions["entry"])
                          if node.get("kind") in {"CXXFunctionalCastExpr", "CXXTemporaryObjectExpr"})
        result = inspect(root, expression, 32)
        if expression["kind"] == "CXXTemporaryObjectExpr":
            # Some Clang versions omit a precise constructor ID in this form.
            # Do not synthesize one from its name or signature to pass the test.
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(result["reason"], "not_constructor_functional_cast")
            self.assertFalse(result["checked"])
            return
        self.assertEqual(result["status"], "inspected", result)
        self.assertEqual([item["pre_conversion_constant"]["value"] for item in result["arguments"]],
                         [256, 1, 1])
        self.assertFalse(result["checked"])
        self.assertEqual(result["actual_configuration_values"], "not_established")
        expression = next(node for node in _walk(functions["defaults"])
                          if node.get("kind") == "CXXFunctionalCastExpr")
        result = inspect(root, expression, 32)
        for argument in result["arguments"][1:]:
            self.assertTrue(argument["default_argument"])
            if argument["default_source_ast"] is None:
                self.assertEqual(argument["status"], "unknown")
                self.assertIsNone(argument["pre_conversion_constant"])
            else:
                self.assertEqual(argument["pre_conversion_constant"]["value"], 1)


if __name__ == "__main__":
    unittest.main()
