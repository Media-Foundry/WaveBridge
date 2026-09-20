"""A real MS-property AST must not become an unproved value-equivalence claim."""

from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.analysis.initializer_evidence import inspect


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class InitializerEvidenceClangTests(unittest.TestCase):
    def test_property_calls_are_preserved_without_assigning_index_semantics(self):
        report = collect(Path(__file__).parent / "fixtures/initializer_evidence.cpp",
                         shutil.which("clang++"), ["-std=c++17", "-fms-extensions"],
                         "entry", full_translation_unit=True)
        self.assertEqual(report["status"], "collected", report.get("execution"))
        root = report["ast_roots"][0]
        variables = {n["name"]: n["id"] for n in _walk(root)
                     if n.get("kind") == "VarDecl" and n.get("init")}
        for name in ("original", "renamed", "with_arithmetic"):
            with self.subTest(name=name):
                evidence = inspect(root, variables[name])
                self.assertEqual(evidence["value_equivalence"], "not_established")
                self.assertEqual(evidence["start_semantics"], "unknown")
                self.assertFalse(evidence["checked"])
                self.assertEqual(len(evidence["calls"]), 1)
                self.assertEqual(evidence["calls"][0]["trace"]["leaf"]["name"],
                                 "external_id")
        self.assertEqual(inspect(root, variables["mutable_value"])["status"], "unknown")
        static = inspect(root, variables["static_property"])
        self.assertEqual(static["value_link"]["status"], "recovered", static["value_link"])
        self.assertEqual(static["value_link"]["call_id"], static["calls"][0]["call_id"])
        self.assertEqual(static["value_link"]["callee_declaration_id"],
                         static["calls"][0]["callee_declaration_id"])
        self.assertFalse(static["checked"])
        for name in ("original", "static_arithmetic", "with_arithmetic"):
            self.assertEqual(inspect(root, variables[name])["value_link"]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
