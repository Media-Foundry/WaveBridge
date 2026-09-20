"""Real-Clang regression for builtin callee casts in reduction discovery."""

from pathlib import Path
import shutil
import unittest

from wavebridge.analysis.reduction_discovery import discover
from wavebridge.frontend.clang_ast import _walk, collect


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class BuiltinCallClangTests(unittest.TestCase):
    def test_builtin_function_edge_preserves_cast_and_missing_body(self):
        report = collect(Path(__file__).parent / "fixtures/builtin_call.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "builtin_entry",
                         full_translation_unit=True)
        self.assertEqual("collected", report["status"], report.get("execution"))
        root = report["ast_roots"][0]
        functions = {node.get("name"): node for node in _walk(root)
                     if node.get("kind") == "FunctionDecl" and
                     node.get("name") in {"builtin_entry", "__builtin_popcount"}}
        self.assertEqual({"builtin_entry", "__builtin_popcount"}, set(functions))

        result = discover(root, functions["builtin_entry"]["id"], 32)
        builtin_id = functions["__builtin_popcount"]["id"]
        edges = [edge for edge in result["call_edges"]
                 if edge.get("callee_id") == builtin_id]
        self.assertEqual(1, len(edges), result)
        casts = edges[0]["callee_casts"]
        self.assertTrue(any(cast.get("cast_kind") == "BuiltinFnToFnPtr" for cast in casts), casts)
        builtin_cast = next(cast for cast in casts if cast.get("cast_kind") == "BuiltinFnToFnPtr")
        self.assertIsInstance(builtin_cast.get("source_type"), dict)
        self.assertIsInstance(builtin_cast.get("destination_type"), dict)
        self.assertIn("range", builtin_cast)
        self.assertEqual("not_established", result["external_call_semantics"])

        unresolved = [item for item in result["unresolved_calls"]
                      if item.get("callee_id") == builtin_id]
        self.assertEqual(1, len(unresolved), result)
        self.assertEqual("callee_unique_definition_not_found", unresolved[0]["reason"])
        self.assertFalse(result["analysis_complete"])
        self.assertFalse(result["checked"])
        self.assertFalse(result["deployable"])


if __name__ == "__main__":
    unittest.main()
