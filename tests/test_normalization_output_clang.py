"""Real Clang dataflow regression; not a floating-point proof."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.analysis.normalization_output import recover
from wavebridge.source import run


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class NormalizationOutputClangTests(unittest.TestCase):
    def test_source_links_scale_and_column_store(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence"
            report = run(Path(__file__).parent / "fixtures/normalization_output.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "entry", 32, output)
            result = report["normalization_output"]
            self.assertEqual(result["status"], "recovered", result)
            self.assertFalse(result["checked"])
            self.assertFalse(result["deployable"])
            root = json.loads((output / "ast.json").read_text())["ast_roots"][0]
            functions = {n["name"]: n["id"] for n in _walk(root)
                         if n.get("kind") == "FunctionDecl"}
            self.assertEqual(result["consumer_declaration_id"], functions["reduce_partial"])
            self.assertEqual(result["scale_function_id"], functions["inverse_root"])
            self.assertEqual(result["local_loop"]["step"], 256)
            self.assertEqual(result["output_loop"]["step"], 256)
            self.assertEqual(result["count_parameter_id"],
                             result["local_loop"]["bound"]["declaration_id"])
            self.assertEqual(result["conversion_semantics"], "not_established")
            self.assertTrue(any(cast["cast_kind"] == "IntegralToFloating"
                                for cast in result["casts"]))
            for name in ("wrong_column", "wrong_stride"):
                result = recover(root, functions[name], 32)
                self.assertEqual(result["status"], "unknown", (name, result))


if __name__ == "__main__":
    unittest.main()
