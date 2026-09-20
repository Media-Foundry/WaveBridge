"""Real source-to-analysis regressions; fixtures are not benchmark coverage."""

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.analysis.column_loops import recover
from wavebridge.source import run


SOURCE = Path(__file__).parent / "fixtures/column_loops.cpp"
COMPILER = shutil.which("clang++")


@unittest.skipUnless(COMPILER, "requires real clang++")
class ColumnLoopsClangTests(unittest.TestCase):
    def test_real_step_changes_and_mutation_rejection(self):
        frontend = collect(SOURCE, COMPILER, ["-std=c++17"], "columns",
                           full_translation_unit=True)
        self.assertEqual(frontend["status"], "collected")
        root = frontend["ast_roots"][0]
        functions = {node["name"]: node["id"] for node in _walk(root)
                     if node.get("kind") == "FunctionDecl"}
        for name, expected in (("columns", 256), ("renamed", 128)):
            with self.subTest(name=name):
                loops = recover(root, functions[name], 32)["loops"]
                self.assertEqual(len(loops), 1)
                self.assertEqual(loops[0]["status"], "recovered", loops)
                self.assertEqual(loops[0]["step"], expected)
        for name in ("hidden_increment", "changing_bound"):
            with self.subTest(name=name):
                loops = recover(root, functions[name], 32)["loops"]
                self.assertEqual(loops[0]["status"], "unknown", loops)

    def test_source_entry_saves_bound_evidence_without_manual_model(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "evidence"
            report = run(SOURCE, COMPILER, ["-std=c++17"], "columns", 32, output)
            self.assertEqual(report["status"], "analyzed", report)
            self.assertFalse(report["deployable"])
            self.assertEqual(report["analysis"]["loops"][0]["step"], 256)
            self.assertTrue((output / "ast.json").is_file())
            self.assertEqual(len(report["ast_report_sha256"]), 64)
            with self.assertRaises(FileExistsError):
                run(SOURCE, COMPILER, [], "columns", 32, output)


if __name__ == "__main__":
    unittest.main()
