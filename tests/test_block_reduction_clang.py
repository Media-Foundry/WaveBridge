"""Real AST stage extraction does not establish external coordinate/barrier semantics."""

from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.analysis.block_reduction import recover
from wavebridge.verification.block_routes import check


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class BlockReductionClangTests(unittest.TestCase):
    def test_real_shared_partial_pattern_and_missing_barrier(self):
        report = collect(Path(__file__).parent / "fixtures/block_reduction.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "block_sum",
                         full_translation_unit=True)
        self.assertEqual(report["status"], "collected", report.get("execution"))
        root = report["ast_roots"][0]
        functions = {n["name"]: n["id"] for n in _walk(root) if n.get("kind") == "FunctionDecl"}
        result = recover(root, functions["block_sum"], functions["reduce_group"],
                         functions["rendezvous"], 32)
        self.assertEqual(result["status"], "recovered", result)
        self.assertEqual(result["width"], 32)
        self.assertEqual(result["block_threads"], 256)
        self.assertEqual(result["coordinate_equality"], "not_established")
        routes = check(result["block_threads"], result["width"], [16, 8, 4, 2, 1])
        self.assertEqual(routes["status"], "checked")
        self.assertFalse(routes["source_program_checked"])
        unsigned = recover(root, functions["unsigned_block_sum"], functions["reduce_group"],
                           functions["rendezvous"], 32)
        self.assertEqual(unsigned["status"], "recovered", unsigned)
        self.assertEqual(unsigned["conversion_semantics"], "not_established")
        self.assertTrue(unsigned["casts"])
        missing = recover(root, functions["missing_barrier"], functions["reduce_group"],
                          functions["rendezvous"], 32)
        self.assertEqual(missing["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
