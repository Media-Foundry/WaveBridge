"""Fresh complete TU value checks must respect actual field storage shape."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.constructor_source_check import check

ABI = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False}}


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class ConstructorValueEffectsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(__file__).parent / "fixtures/constructor_value_effects.cpp"
        report = collect(cls.source, shutil.which("clang++"), ["-std=c++17"], "ordinary",
                         full_translation_unit=True, dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]

    def result(self, name):
        function = next(n for n in _walk(self.root) if n.get("kind") == "FunctionDecl"
                        and n.get("name") == name)
        expression = next(n for n in _walk(function) if n.get("kind") == "CXXConstructExpr")
        return check(self.root, expression["id"], ABI, {})

    def test_plain_field_retains_value_with_fresh_effect_check(self):
        report = self.result("ordinary")
        self.assertEqual(report["status"], "checked", report)
        self.assertEqual(report["fields"][0]["value"], 99)
        effects = report["constructor_effects"]
        self.assertEqual(effects["status"], "checked", effects)
        self.assertEqual(effects["input_sha256"]["root"], report["input_sha256"]["root"])
        self.assertEqual(effects["constructor_declaration_id"],
                         report["constructor_arguments"]["constructor_declaration_id"])
        self.assertEqual(report["call_argument_effects"], "not_established")
        self.assertEqual(report["post_construction_escape"], "not_established")
        self.assertFalse(report["deployable"])

    def test_bitfield_cannot_receive_plain_integer_value_guarantee(self):
        report = self.result("narrowed")
        self.assertEqual(report["status"], "unknown", report)
        self.assertEqual(report["fields"], [])
        self.assertEqual(report["constructor_effects"]["status"], "unknown")
        self.assertEqual(report["constructor_effects"]["reason"], "record_field_shape_unsupported")

    def test_volatile_storage_stays_unknown(self):
        report = self.result("volatile_value")
        self.assertEqual(report["status"], "unknown", report)
        self.assertEqual(report["fields"], [])

    def test_cpu_execution_distinguishes_bitfield_from_plain_unsigned(self):
        with tempfile.TemporaryDirectory(prefix="wb-field-storage-") as directory:
            executable = Path(directory) / "check"
            compiled = subprocess.run([shutil.which("clang++"), "-std=c++17",
                "-DWAVEBRIDGE_VALUE_EFFECTS_EXECUTION", str(self.source), "-o", str(executable)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
            self.assertEqual(executed.returncode, 0, executed.stderr)
