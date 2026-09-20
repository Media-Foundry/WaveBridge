import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from wavebridge.frontend import clang_ast


class ClangAstTests(unittest.TestCase):
    def test_multiple_json_roots_are_preserved(self):
        raw = '{"kind":"FunctionDecl","name":"f"}\n {"kind":"FunctionDecl","name":"g"}'
        roots = clang_ast.parse_json_roots(raw)
        self.assertEqual([root["name"] for root in roots], ["f", "g"])

    def test_success_records_real_ast_and_location_only(self):
        ast = {"kind": "FunctionDecl", "id": "0x1", "name": "target",
               "loc": {"file": "case.cpp", "line": 4}, "inner": []}
        with self.case_files() as (source, compiler), \
             mock.patch.object(clang_ast, "invoke", return_value=record(stdout=json.dumps(ast))):
            report = clang_ast.collect(source, str(compiler), ["-DVALUE=1"], "target")
        self.assertEqual(report["status"], "collected")
        self.assertEqual(report["ast_roots"], [ast])
        self.assertEqual(report["function_locations"][0]["location"]["line"], 4)
        self.assertEqual(report["relation_recovery"], "not_implemented")
        self.assertFalse(report["manual_oracle_read"])
        self.assertNotIn("relations", report)
        self.assertIn("-DVALUE=1", report["command"])
        self.assertEqual(report["command"][-1], str(source.resolve()))

    def test_nonzero_compiler_exit_is_distinct(self):
        with self.case_files() as (source, compiler), \
             mock.patch.object(clang_ast, "invoke", return_value=record(returncode=1, stderr="bad source")):
            report = clang_ast.collect(source, str(compiler), [], "target")
        self.assertEqual(report["status"], "compile_failed")
        self.assertEqual(report["reason"], "compiler_nonzero_exit")

    def test_timeout_is_distinct_and_keeps_logs(self):
        with self.case_files() as (source, compiler), \
             mock.patch.object(clang_ast, "invoke", return_value=record(status="timeout", returncode=None,
                                                                         stdout="partial")):
            report = clang_ast.collect(source, str(compiler), [], "target")
        self.assertEqual(report["status"], "timeout")
        self.assertEqual(report["execution"]["stdout"], "partial")

    def test_empty_success_is_no_symbol(self):
        with self.case_files() as (source, compiler), \
             mock.patch.object(clang_ast, "invoke", return_value=record(stdout="")):
            report = clang_ast.collect(source, str(compiler), [], "missing")
        self.assertEqual(report["status"], "no_symbol")

    def test_timeout_kills_process_group_and_decodes_bytes(self):
        process = mock.Mock(pid=123, returncode=None)
        process.communicate.side_effect = [
            subprocess.TimeoutExpired(["clang"], 1, output=b"partial", stderr=b"diagnostic"),
            (b"partial-final", b"diagnostic-final"),
        ]
        with mock.patch.object(clang_ast.subprocess, "Popen", return_value=process), \
             mock.patch.object(clang_ast.os, "killpg") as killpg:
            result = clang_ast.invoke(["clang"], 1, Path.cwd())
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["stdout"], "partial-final")
        killpg.assert_called_once_with(123, clang_ast.signal.SIGKILL)

    def test_nonfinite_timeout_is_input_error_without_invocation(self):
        with self.case_files() as (source, compiler), mock.patch.object(clang_ast, "invoke") as invoke:
            for timeout in (float("nan"), float("inf"), 0.0):
                report = clang_ast.collect(source, str(compiler), [], "target", timeout)
                self.assertEqual(report["reason"], "invalid_timeout")
        invoke.assert_not_called()

    def test_malformed_or_nonobject_root_is_rejected(self):
        for raw in ("{", "[]"):
            with self.subTest(raw=raw), self.assertRaises((json.JSONDecodeError, ValueError)):
                clang_ast.parse_json_roots(raw)

    def test_cli_refuses_existing_output_without_invocation(self):
        with self.case_files() as (source, compiler), tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "ast.json"
            output.write_text("historical evidence")
            with mock.patch.object(clang_ast, "collect") as collect, self.assertRaises(SystemExit):
                clang_ast.main([str(source), "--compiler", str(compiler), "--symbol", "target",
                                "--output", str(output)])
            collect.assert_not_called()
            self.assertEqual(output.read_text(), "historical evidence")

    def test_cli_refuses_source_as_output_without_invocation(self):
        with self.case_files() as (source, compiler), \
             mock.patch.object(clang_ast, "collect") as collect, self.assertRaises(SystemExit):
            clang_ast.main([str(source), "--compiler", str(compiler), "--symbol", "target",
                            "--output", str(source)])
        collect.assert_not_called()

    class case_files:
        def __enter__(self):
            self.temp = tempfile.TemporaryDirectory()
            root = Path(self.temp.name)
            source, compiler = root / "case.cpp", root / "clang++"
            source.write_text("void target() {}\n")
            compiler.write_bytes(b"compiler")
            return source, compiler

        def __exit__(self, *args):
            self.temp.cleanup()


def record(status="completed", returncode=0, stdout="", stderr=""):
    return {"command": ["clang"], "timeout_seconds": 1, "status": status,
            "returncode": returncode, "stdout": stdout, "stderr": stderr,
            "duration_seconds": 0.0}


if __name__ == "__main__":
    unittest.main()
