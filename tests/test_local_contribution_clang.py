"""Source-linked contributions, distinct from conditional coverage checks."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.analysis.local_contribution import recover
from wavebridge.source import run
from wavebridge.verification.column_coverage import check


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class LocalContributionClangTests(unittest.TestCase):
    def test_real_storage_and_vla_counterexamples_are_unknown(self):
        artifact = collect(Path(__file__).parent / "fixtures/local_contribution_storage.cpp",
                           shutil.which("clang++"), ["-std=c++17"], "automatic",
                           full_translation_unit=True)
        self.assertEqual("collected", artifact["status"], artifact)
        root, = artifact["ast_roots"]
        functions = {node["name"]: node["id"] for node in _walk(root)
                     if node.get("kind") == "FunctionDecl"}
        self.assertEqual("recovered", recover(root, functions["automatic"], 32)["status"])
        for name, reason in (("static_accumulator", "accumulator_storage_not_automatic"),
                             ("thread_accumulator", "accumulator_storage_not_automatic"),
                             ("static_load", "loop_value_storage_not_automatic"),
                             ("thread_load", "loop_value_storage_not_automatic"),
                             ("array_bound_effect", "preconsumer_array_declaration_effects_not_supported")):
            result = recover(root, functions[name], 32)
            self.assertEqual("unknown", result["status"], (name, result))
            self.assertEqual(reason, result["reason"])
            self.assertEqual("not_established", result["declaration_evaluation"])
            self.assertFalse(result["checked"])

    def test_cpu_execution_demonstrates_initializer_and_bound_effects(self):
        names = ["automatic", "static_accumulator", "thread_accumulator", "static_load",
                 "thread_load", "array_bound_effect"]
        declarations = "\n".join("float " + name + "(const float *, int, int);" for name in names)
        main = declarations + r'''
extern "C" int printf(const char *, ...);
int main() {
  const float input[] = {1.0f, 2.0f};
  typedef float (*Function)(const float *, int, int);
  const Function functions[] = {automatic, static_accumulator, thread_accumulator,
                                static_load, thread_load, array_bound_effect};
  for (auto function : functions) {
    const float first = function(input, 2, 0);
    const float second = function(input, 2, 0);
    printf("%.0f %.0f\n", first, second);
  }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            driver, binary = Path(temporary) / "main.cpp", Path(temporary) / "run"
            driver.write_text(main)
            compilation = subprocess.run([shutil.which("clang++"), "-std=c++17",
                str(Path(__file__).parent / "fixtures/local_contribution_storage.cpp"),
                str(driver), "-o", str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(0, compilation.returncode, compilation.stderr)
            execution = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(0, execution.returncode, execution.stderr)
            self.assertEqual(["5 5", "5 10", "5 10", "2 2", "2 2", "7 7"],
                             execution.stdout.splitlines())

    def test_source_connects_squared_load_to_consumer(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence"
            report = run(Path(__file__).parent / "fixtures/local_contribution.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "entry", 32, output)
            result = report["local_contribution"]
            self.assertEqual(result["status"], "recovered", result)
            self.assertFalse(result["checked"])
            self.assertEqual(result["loop"]["step"], 256)
            root = json.loads((output / "ast.json").read_text())["ast_roots"][0]
            functions = {n["name"]: n["id"] for n in _walk(root)
                         if n.get("kind") == "FunctionDecl"}
            self.assertEqual(result["consumer_declaration_id"], functions["combine"])
            for name in ("wrong_index", "modified"):
                self.assertEqual(recover(root, functions[name], 32)["status"], "unknown", name)
            # Starts and bound remain explicit external inputs, not recovered GPU coordinates.
            coverage = check(777, list(range(256)), result["loop"]["step"])
            self.assertEqual(coverage["status"], "checked")
            self.assertFalse(coverage["source_program_checked"])


if __name__ == "__main__":
    unittest.main()
