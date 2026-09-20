import json
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.analysis.row_prefix import recover
from wavebridge.source import run


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class RowPrefixClangTests(unittest.TestCase):
    def test_real_source_prefix_and_wrong_row(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "evidence"
            report = run(Path(__file__).parent / "fixtures/row_prefix.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "entry", 32, directory)
            prefix = report["row_prefix"]
            self.assertEqual(prefix["status"], "recovered", prefix)
            self.assertFalse(prefix["checked"])
            self.assertFalse(prefix["deployable"])
            self.assertEqual(prefix["start_declaration_id"],
                             report["normalization_output"]["local_loop"]["start"]["declaration_id"])
            self.assertEqual(prefix["count_parameter_id"],
                             report["normalization_output"]["count_parameter_id"])
            self.assertTrue(prefix["casts"])
            root = json.loads((directory / "ast.json").read_text())["ast_roots"][0]
            wrong = next(n for n in _walk(root) if n.get("kind") == "FunctionDecl"
                         and n.get("name") == "wrong_row")
            self.assertEqual(recover(root, wrong["id"], 32)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
