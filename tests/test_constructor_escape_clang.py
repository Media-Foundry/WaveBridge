"""Constructor publication defeats caller-only direct DeclRef write scans."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.constructor_source_check import check as check_construction
from wavebridge.record_copy_check import check as check_copy

ABI = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False}}


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class ConstructorEscapeClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = Path(__file__).parent / "fixtures/constructor_escape.cpp"
        report = collect(cls.fixture, shutil.which("clang++"), ["-std=c++17"],
                         "no_publication", full_translation_unit=True, dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]

    def inputs(self, name):
        function = next(n for n in _walk(self.root)
                        if n.get("kind") == "FunctionDecl" and n.get("name") == name)
        variables = {n["name"]: n for n in _walk(function)
                     if n.get("kind") == "VarDecl" and n.get("name") in {"source", "target"}}
        constructors = {name: next(n for n in _walk(variable) if n.get("kind") == "CXXConstructExpr")
                        for name, variable in variables.items()}
        return function, variables, constructors

    def test_publication_constructors_do_not_gain_field_domain_approval(self):
        for name in ("no_publication", "body_publication", "initializer_publication", "argument_publication"):
            _, _, constructors = self.inputs(name)
            report = check_construction(self.root, constructors["source"]["id"], ABI, {})
            with self.subTest(name=name):
                if name == "no_publication":
                    self.assertEqual(report["status"], "checked", report)
                else:
                    self.assertEqual(report["status"], "unknown", report)

    def test_copy_relation_does_not_certify_source_history(self):
        for name in ("no_publication", "body_publication", "initializer_publication"):
            function, variables, constructors = self.inputs(name)
            # All three callers have just one explicit source reference: the
            # copy argument. Constructor publication has no caller DeclRef.
            references = [n for n in _walk(function) if n.get("kind") == "DeclRefExpr"
                          and n.get("referencedDecl", {}).get("id") == variables["source"]["id"]]
            self.assertEqual(len(references), 1)
            report = check_copy(self.root, constructors["target"]["id"], ABI)
            with self.subTest(name=name):
                self.assertEqual(report["status"], "checked", report)
                self.assertEqual(report["source_object_preservation"], "not_established")
                self.assertFalse(report["deployable"])

    def test_real_execution_observes_implicit_publication_mutation(self):
        with tempfile.TemporaryDirectory(prefix="wb-constructor-escape-") as directory:
            executable = Path(directory) / "escape"
            compiled = subprocess.run([shutil.which("clang++"), "-std=c++17",
                "-DWAVEBRIDGE_ESCAPE_EXECUTION", str(self.fixture), "-o", str(executable)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
            self.assertEqual(executed.returncode, 0, executed.stderr)
