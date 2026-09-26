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
    def test_source_pipeline_does_not_compose_persistent_or_side_effecting_local_values(self):
        source = (Path(__file__).parent / "fixtures/normalization_output.cpp").read_text()
        mutations = [("float partial = 0.0f;", "static float partial = 0.0f;"),
                     ("float partial = 0.0f;", "thread_local float partial = 0.0f;"),
                     ("const float value = input[col];", "static const float value = input[col];"),
                     ("const float value = input[col];", "thread_local const float value = input[col];"),
                     ("float scratch[32];", "float scratch[(partial = 7.0f, 32)];")]
        with tempfile.TemporaryDirectory() as temporary:
            for index, (old, new) in enumerate(mutations):
                path = Path(temporary) / f"variant{index}.cpp"
                path.write_text(source.replace(old, new))
                report = run(path, shutil.which("clang++"), ["-std=c++17"], "entry", 32,
                             Path(temporary) / f"evidence{index}")
                self.assertEqual("unknown", report["local_contribution"]["status"], report)
                self.assertEqual("unknown", report["normalization_output"]["status"], report)
                self.assertFalse(report["normalization_output"]["checked"])
                self.assertFalse(report["normalization_output"]["deployable"])

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
