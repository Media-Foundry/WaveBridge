"""Source-linked contributions, distinct from conditional coverage checks."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.analysis.local_contribution import recover
from wavebridge.source import run
from wavebridge.verification.column_coverage import check


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class LocalContributionClangTests(unittest.TestCase):
    def test_source_connects_squared_load_to_consumer(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence"
            report = run(Path(__file__).parent / "fixtures/local_contribution.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "entry", 32, output)
            result = report["local_contribution"]
            self.assertEqual(result["status"], "recovered", result)
            self.assertFalse(result["checked"])
            self.assertEqual(result["loop"]["step"], 256)
            root = json.loads((output / "ast.json").read_text())["ast_roots"][0]
            functions = {n["name"]: n["id"] for n in _walk(root)
                         if n.get("kind") == "FunctionDecl"}
            self.assertEqual(result["consumer_declaration_id"], functions["combine"])
            for name in ("wrong_index", "modified"):
                self.assertEqual(recover(root, functions[name], 32)["status"], "unknown", name)
            # Starts and bound remain explicit external inputs, not recovered GPU coordinates.
            coverage = check(777, list(range(256)), result["loop"]["step"])
            self.assertEqual(coverage["status"], "checked")
            self.assertFalse(coverage["source_program_checked"])


if __name__ == "__main__":
    unittest.main()
