"""Actual Clang wrappers exercise structure, renaming and dimension changes."""

from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.analysis.return_trace import trace


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class ReturnTraceClangTests(unittest.TestCase):
    def test_member_chain_preserves_external_dimension_and_rejects_extra_work(self):
        report = collect(Path(__file__).parent / "fixtures/return_trace.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "wrapper",
                         full_translation_unit=True)
        self.assertEqual(report["status"], "collected", report.get("execution"))
        root = report["ast_roots"][0]
        declarations = {node["name"]: node["id"] for node in _walk(root)
                        if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"}}
        for name, dimension in (("getter", "0"), ("alternate", "1")):
            with self.subTest(name=name):
                result = trace(root, declarations[name])
                self.assertEqual(result["status"], "external_leaf", result)
                self.assertEqual(result["leaf"]["name"], "external_index")
                literals = [node["value"] for arg in result["leaf"]["arguments"]
                            for node in _walk(arg) if node.get("kind") == "IntegerLiteral"]
                self.assertEqual(literals, [dimension])
                self.assertFalse(result["checked"])
        for name in ("arithmetic_getter", "multi_statement"):
            with self.subTest(name=name):
                self.assertEqual(trace(root, declarations[name])["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
