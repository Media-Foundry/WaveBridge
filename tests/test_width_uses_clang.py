"""Real source -> fresh width-use inventory; no GPU or rewrite authorization."""
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import collect
from wavebridge.analysis.width_uses import inspect


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class WidthUsesClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures = Path(__file__).parent / "fixtures"
        helpers = (fixtures / "reduction_entry.cpp").read_text().split("float unrelated(")[0]
        entry = (fixtures / "normalization_output.cpp").read_text().split("void wrong_column(")[0]
        entry = entry.replace("float reduce_partial(float, float *);", "")
        cls.source = helpers + entry.replace("reduce_partial(partial, scratch)",
                                             "aggregate(partial, scratch)")

    def analyze(self, source):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.cpp"
            path.write_text(source)
            artifact = collect(path, shutil.which("clang++"), ["-std=c++17"], "entry",
                               full_translation_unit=True, dependency_binding="required")
            self.assertEqual("collected", artifact["status"], artifact.get("execution"))
            return inspect(artifact["ast_roots"][0], artifact["function_locations"][0]["id"], 32)

    def test_only_five_supported_uses_are_classified_even_after_renaming(self):
        source = self.source.replace("width", "not_a_width_name").replace("subgroup", "renamed")
        result = self.analyze(source)
        self.assertEqual("evidence", result["status"], result)
        for flag in ("checked", "source_program_checked", "deployable"):
            self.assertFalse(result[flag])

    def test_external_value_address_reference_and_diagnostic_uses_stay_unknown(self):
        extras = [
            "int data_format(int x) { return x / width; }",
            "const int* escape() { return &width; }",
            "const int& alias = width;",
            "int printf(const char*, ...); void show() { printf(\"%d\", width); }",
            "int unused() { return width; }",
        ]
        for extra in extras:
            with self.subTest(extra=extra):
                result = self.analyze(self.source + extra)
                self.assertEqual("unknown", result["status"], result)
                self.assertFalse(result["deployable"])

    def test_same_literal_in_different_declaration_is_not_a_width_reference(self):
        result = self.analyze(self.source + "constexpr int data_format=32; int f(){return data_format;}")
        self.assertEqual("evidence", result["status"], result)

    def test_target_width64_reparsed_independently(self):
        result = self.analyze(self.source.replace("constexpr int width = 32;", "constexpr int width = 64;"))
        self.assertEqual("evidence", result["status"], result)
        self.assertFalse(result["source_program_checked"])


if __name__ == "__main__":
    unittest.main()
