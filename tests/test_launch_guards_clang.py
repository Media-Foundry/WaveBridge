import json
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.analysis.launch_guards import recover
from wavebridge.frontend.clang_ast import _walk
from wavebridge.source import run


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class LaunchGuardClangTests(unittest.TestCase):
    def test_real_cuda_launch_guards_and_bypass_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "evidence"
            report = run(Path(__file__).parent / "fixtures/launch_guards.cu",
                         shutil.which("clang++"),
                         ["-std=c++17", "--cuda-host-only", "-nocudainc", "-nocudalib"],
                         "entry", 32, directory)
            self.assertEqual(report["status"], "analyzed", report)
            root = json.loads((directory / "ast.json").read_text())["ast_roots"][0]
            functions = {node["name"]: node for node in _walk(root)
                         if node.get("kind") == "FunctionDecl" and node.get("name") in
                         {"direct_launch", "macro_style_launch", "ordinary_host_flow",
                          "escaped_launch", "bypassed_guard"}}
            for name, function in functions.items():
                launch = next(node for node in _walk(function) if node.get("kind") == "CUDAKernelCallExpr")
                result = recover(root, launch["id"], 32)
                if name in {"direct_launch", "macro_style_launch", "ordinary_host_flow"}:
                    self.assertEqual(result["status"], "recovered", result)
                    self.assertEqual(sorted((item["lower"], item["upper"]) for item in result["intervals"]),
                                     [(1, 8), (1, 1023)])
                    by_id = {item["declaration_id"]: item for item in result["intervals"]}
                    site = next(site for site in report["launch_facts"]["sites"]
                                if site["launch_id"] == launch["id"])
                    kernel_refs = {node.get("referencedDecl", {}).get("id")
                                   for node in _walk(site["parameter_bindings"][0]["argument_ast"])
                                   if node.get("kind") == "DeclRefExpr"}
                    self.assertEqual([(by_id[key]["lower"], by_id[key]["upper"])
                                      for key in kernel_refs if key in by_id], [(1, 1023)])
                    grid_refs = {node.get("referencedDecl", {}).get("id")
                                 for node in _walk(site["configuration_arguments"][0])
                                 if node.get("kind") == "DeclRefExpr"}
                    self.assertEqual([(by_id[key]["lower"], by_id[key]["upper"])
                                      for key in grid_refs if key in by_id], [(1, 8)])
                else:
                    self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["checked"])
                self.assertFalse(result["deployable"])
            self.assertEqual(len(functions), 5)
            self.assertEqual(len(report["launch_facts"]["sites"]), 5)
            self.assertIn("analysis/launch_guards.py", report["implementation_sha256"])
            self.assertTrue(all("host_guard_intervals" in site for site in report["launch_facts"]["sites"]))


if __name__ == "__main__":
    unittest.main()
