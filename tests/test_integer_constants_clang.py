"""Optional real Clang check for source-derived constants and reference links."""

from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.analysis.integer_constants import evaluate


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class IntegerConstantsClangTests(unittest.TestCase):
    def test_actual_initializer_expressions_and_types(self):
        source = Path(__file__).parent / "fixtures/integer_constants.cpp"
        report = collect(source, shutil.which("clang++"), ["-std=c++17"],
                         "arbitrary_entry", full_translation_unit=True)
        self.assertEqual(report["status"], "collected", report.get("execution"))
        root = report["ast_roots"][0]
        declarations = {node["name"]: node["id"] for node in _walk(root)
                        if node.get("kind") == "VarDecl" and "init" in node}
        for name, expected in (("original_width", 32), ("renamed_width", 32),
                               ("block_threads", 256), ("quotient", -2),
                               ("remainder", -1)):
            with self.subTest(name=name):
                result = evaluate(root, declarations[name], int_bits=32)
                self.assertEqual(result["value"], expected, result)
        for name in ("unsigned_value", "mutable_width"):
            with self.subTest(name=name):
                result = evaluate(root, declarations[name], int_bits=32)
                self.assertEqual(result["status"], "unknown", result)


if __name__ == "__main__":
    unittest.main()
