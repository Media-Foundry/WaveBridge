"""Full-view collection must retain declaration identity, not join by spelling."""

from pathlib import Path
import shutil
import unittest

from wavebridge.frontend import clang_ast


class TranslationUnitTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
    def test_full_view_contains_referenced_helper_definition(self):
        source = Path(__file__).parent / "fixtures/source_calls.cpp"
        report = clang_ast.collect(source, shutil.which("clang++"), ["-std=c++17"],
                                   "arbitrary_entry", full_translation_unit=True)
        self.assertEqual(report["status"], "collected", report.get("execution"))
        self.assertEqual(report["collection_scope"], "translation_unit")
        self.assertIsNone(report["execution"]["stdout"])
        self.assertEqual(report["execution"]["stdout_retention"],
                         "parsed_ast_only_not_verbatim")
        self.assertNotIn("-ast-dump-filter=arbitrary_entry", report["command"])
        self.assertEqual(len(report["ast_roots"]), 1)
        nodes = list(clang_ast._walk(report["ast_roots"][0]))
        definitions = {node["id"]: node for node in nodes
                       if node.get("kind") == "FunctionDecl"
                       and any(child.get("kind") == "CompoundStmt"
                               for child in node.get("inner", []))}
        leaf_refs = [node["referencedDecl"]["id"] for node in nodes
                     if node.get("kind") == "DeclRefExpr"
                     and node.get("referencedDecl", {}).get("name") == "leaf"]
        self.assertTrue(leaf_refs)
        self.assertTrue(all(identifier in definitions for identifier in leaf_refs))


if __name__ == "__main__":
    unittest.main()
