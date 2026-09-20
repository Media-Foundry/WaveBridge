"""Static property call edges are not thread-index value proofs."""
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.analysis.reduction_discovery import discover


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class StaticPropertyClangTests(unittest.TestCase):
    def test_static_property_is_followed_but_dynamic_dispatch_is_not(self):
        frontend = collect(Path(__file__).parent / "fixtures/static_property.cpp",
                           shutil.which("clang++"), ["-std=c++17", "-fms-extensions"],
                           "entry", full_translation_unit=True)
        self.assertEqual(frontend["status"], "collected")
        root = frontend["ast_roots"][0]
        functions = {node["name"]: node["id"] for node in _walk(root)
                     if node.get("kind") == "FunctionDecl"}
        result = discover(root, functions["entry"], 32)
        self.assertIn(functions["bridge"], result["reachable_function_ids"])
        self.assertTrue(any(edge["callee_id"] == functions["external_coordinate"]
                            for edge in result["call_edges"]))
        self.assertFalse(result["analysis_complete"])
        self.assertFalse(result["checked"])
        dynamic = discover(root, functions["dynamic_entry"], 32)
        self.assertNotIn(functions["bridge"], dynamic["reachable_function_ids"])
        self.assertTrue(dynamic["unresolved_calls"])


if __name__ == "__main__":
    unittest.main()
