"""Real lambda AST repetitions must not inflate syntactic launch counts."""
from collections import Counter
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.analysis.launch_facts import inspect


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class LaunchFactsClangTests(unittest.TestCase):
    def test_same_lambda_node_repetitions_are_one_syntactic_site(self):
        report = collect(Path(__file__).parent / "fixtures/lambda_launch.cu",
                         shutil.which("clang++"),
                         ["-std=c++17", "--cuda-host-only", "-nocudainc", "-nocudalib"],
                         "target", full_translation_unit=True, dependency_binding="required")
        self.assertEqual("collected", report["status"], report.get("execution"))
        root = report["ast_roots"][0]
        kernel = report["function_locations"][0]["id"]
        counts = Counter(n["id"] for n in _walk(root) if n.get("kind") == "CUDAKernelCallExpr")
        self.assertEqual(1, len(counts))
        self.assertGreater(next(iter(counts.values())), 1)
        result = inspect(root, kernel)
        self.assertEqual("evidence", result["status"], result)
        self.assertEqual(1, len(result["sites"]))
        site = result["sites"][0]
        self.assertEqual(counts[site["launch_id"]], site["ast_occurrences"])
        self.assertEqual("bound_by_position", site["parameter_binding_status"])
        self.assertEqual("not_checked", result["host_reachability"])
        self.assertFalse(result["checked"])
        self.assertFalse(result["deployable"])


if __name__ == "__main__":
    unittest.main()
