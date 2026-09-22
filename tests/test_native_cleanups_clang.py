"""Native cleanup observations are metadata, not complete lifetime proofs."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect

PLUGIN = os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")


@unittest.skipUnless(PLUGIN, "requires compiler-matched native observation plugin")
class NativeCleanupsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(__file__).parent / "fixtures/native_cleanups.cpp"
        cls.report = collect(cls.source, COMPILER, Path(PLUGIN), ["-std=c++17"])
        if cls.report["status"] != "collected":
            raise AssertionError(cls.report)
        cls.payload = cls.report["payload"]
        cls.root = cls.payload["ast"]

    def record_for(self, name):
        function = next(n for n in _walk(self.root) if n.get("kind") == "FunctionDecl"
                        and n.get("name") == name)
        cleanup = next(n for n in _walk(function) if n.get("kind") == "ExprWithCleanups")
        records = [r for r in self.payload["expression_cleanups"] if r["expression_id"] == cleanup["id"]]
        self.assertEqual(len(records), 1)
        return cleanup, records[0]

    def test_same_context_ids_and_explicit_nonexhaustive_coverage(self):
        self.assertEqual(self.payload["cleanup_coverage"], "visited_expressions_not_exhaustive")
        self.assertEqual(self.payload["cleanup_object_count_semantics"],
                         "clang_cleanup_objects_not_destructor_event_count")
        records = self.payload["expression_cleanups"]
        self.assertTrue(records)
        self.assertEqual(len({r["expression_id"] for r in records}), len(records))
        for record in records:
            matches = [n for n in _walk(self.root) if n.get("id") == record["expression_id"]]
            self.assertTrue(matches)
            self.assertTrue(all(n.get("kind") == "ExprWithCleanups" for n in matches))
            self.assertTrue(all(n["inner"][0]["id"] == record["subexpression_id"] for n in matches))
        self.assertFalse(self.report["source_program_checked"])
        self.assertFalse(self.report["deployable"])

    def test_scalar_and_destructor_cleanup_flags_are_distinct(self):
        _, scalar = self.record_for("scalar_temporary")
        destructor_ast, destructor = self.record_for("destructor_temporary")
        self.assertFalse(scalar["cleanups_have_side_effects"])
        self.assertTrue(destructor["cleanups_have_side_effects"])
        # C++ temporary destructors live in CXXBindTemporaryExpr, not the
        # ExprWithCleanups auxiliary objects array. Zero is not no cleanup.
        self.assertEqual(scalar["num_objects"], 0)
        self.assertEqual(destructor["num_objects"], 0)
        self.assertTrue(any(n.get("kind") == "CXXBindTemporaryExpr" for n in _walk(destructor_ast)))

    def test_lambda_body_observations_are_bound_and_deduplicated(self):
        function = next(n for n in _walk(self.root) if n.get("kind") == "FunctionDecl"
                        and n.get("name") == "in_lambda")
        closure = next(n for n in _walk(function) if n.get("kind") == "LambdaExpr")
        body = next(n for n in closure["inner"] if n.get("kind") == "CompoundStmt")
        expected = {n["id"] for n in _walk(body) if n.get("kind") == "ExprWithCleanups"}
        self.assertTrue(expected)
        observed = [r["expression_id"] for r in self.payload["expression_cleanups"]]
        self.assertTrue(expected.issubset(set(observed)))
        self.assertTrue(all(observed.count(identifier) == 1 for identifier in expected))

    def test_real_cpu_execution_observes_destructor_write(self):
        with tempfile.TemporaryDirectory(prefix="wb-cleanup-execution-") as directory:
            executable = Path(directory) / "check"
            compiled = subprocess.run([COMPILER, "-std=c++17", "-DWAVEBRIDGE_CLEANUP_EXECUTION",
                str(self.source), "-o", str(executable)], capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
            self.assertEqual(executed.returncode, 0, executed.stderr)
