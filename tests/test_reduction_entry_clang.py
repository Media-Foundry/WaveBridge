"""Real compilation exercises discovery without manually selected helper IDs."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.source import run


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class ReductionEntryClangTests(unittest.TestCase):
    def test_source_entry_discovers_only_reachable_reductions(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence"
            report = run(Path(__file__).parent / "fixtures/reduction_entry.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "entry", 32, output)
            self.assertEqual(report["status"], "analyzed")
            self.assertFalse(report["checked"])
            self.assertFalse(report["deployable"])
            root = json.loads((output / "ast.json").read_text())["ast_roots"][0]
            functions = {node["name"]: node["id"] for node in _walk(root)
                         if node.get("kind") == "FunctionDecl"}
            discovery = report["reduction_discovery"]
            blocks = discovery["block_candidates"]
            xors = discovery["xor_candidates"]
            self.assertEqual([item["function_id"] for item in blocks],
                             [functions["aggregate"]])
            self.assertEqual([item["function_id"] for item in xors],
                             [functions["subgroup"]])
            self.assertEqual(blocks[0]["width"], 32)
            self.assertEqual(blocks[0]["block_threads"], 256)
            self.assertEqual(xors[0]["offsets"], [16, 8, 4, 2, 1])
            self.assertEqual(xors[0]["external_shuffle_semantics"], "not_established")
            self.assertFalse(blocks[0]["checked"])
            self.assertFalse(xors[0]["checked"])
            self.assertIn("analysis/reduction_discovery.py", report["implementation_sha256"])


if __name__ == "__main__":
    unittest.main()
