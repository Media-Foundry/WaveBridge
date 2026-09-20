"""Real-Clang regressions for protected loop-variable writes and escapes."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from wavebridge.analysis.column_loops import recover
from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.column_coverage import check as check_coverage


SOURCE = Path(__file__).parent / "fixtures/column_loop_body_escapes.cpp"
COMPILER = shutil.which("clang++")


@unittest.skipUnless(COMPILER, "requires real clang++")
class ColumnLoopBodyEscapesClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frontend = collect(SOURCE, COMPILER, ["-std=c++17"], "ordinary_index",
                           full_translation_unit=True)
        if frontend.get("status") != "collected":
            raise AssertionError(frontend)
        cls.root = frontend["ast_roots"][0]
        cls.functions = {
            node["name"]: node["id"] for node in _walk(cls.root)
            if node.get("kind") == "FunctionDecl" and isinstance(node.get("id"), str)
        }

    def recovery(self, name):
        return recover(self.root, self.functions[name], 32)

    def test_ordinary_array_indexing_recovers_and_coverage_checks(self):
        report = self.recovery("ordinary_index")
        self.assertEqual(report["status"], "recovered", report)
        self.assertEqual(len(report["loops"]), 1)
        loop = report["loops"][0]
        self.assertEqual(loop["step"], 256)
        self.assertEqual(loop["start"]["kind"], "declaration_reference")

        # This is the standalone coverage checker fed by real recovered stride
        # evidence, not a full column_domain_check launch/guard composition.
        coverage = check_coverage(768, list(range(256)), loop["step"], int_bits=32)
        self.assertEqual(coverage["status"], "checked", coverage)

    def test_hidden_lvalue_writes_and_asm_are_unknown(self):
        for name in ("static_cast_alias", "c_style_alias", "comma_lvalue",
                     "inline_asm_escape"):
            with self.subTest(name=name):
                report = self.recovery(name)
                self.assertEqual(report["status"], "unknown", report)
                self.assertEqual(report["loops"][0]["status"], "unknown", report)

    def test_cpu_witness_static_cast_variant_writes_only_512_of_768_columns(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "column-body-escape"
            compiled = subprocess.run(
                [COMPILER, "-std=c++17", "-DWAVEBRIDGE_CPU_WITNESS", str(SOURCE),
                 "-o", str(executable)], capture_output=True, text=True, timeout=30,
                check=False)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run([str(executable)], capture_output=True, text=True,
                                      timeout=10, check=False)
            self.assertEqual(executed.returncode, 0, executed.stderr)


if __name__ == "__main__":
    unittest.main()
