import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.analysis.row_prefix import recover
from wavebridge.source import run


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class RowPrefixClangTests(unittest.TestCase):
    def test_real_source_prefix_and_wrong_row(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "evidence"
            report = run(Path(__file__).parent / "fixtures/row_prefix.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "entry", 32, directory)
            prefix = report["row_prefix"]
            self.assertEqual(prefix["status"], "recovered", prefix)
            self.assertFalse(prefix["checked"])
            self.assertFalse(prefix["deployable"])
            self.assertEqual(prefix["start_declaration_id"],
                             report["normalization_output"]["local_loop"]["start"]["declaration_id"])
            self.assertEqual(prefix["count_parameter_id"],
                             report["normalization_output"]["count_parameter_id"])
            self.assertTrue(prefix["casts"])
            root = json.loads((directory / "ast.json").read_text())["ast_roots"][0]
            wrong = next(n for n in _walk(root) if n.get("kind") == "FunctionDecl"
                         and n.get("name") == "wrong_row")
            self.assertEqual(recover(root, wrong["id"], 32)["status"], "unknown")

    def test_real_source_rejects_persistent_row_and_start_coordinates(self):
        fixture = (Path(__file__).parent / "fixtures/row_prefix.cpp").read_text()
        variants = {
            "static_row": ("const int row = row_value();",
                           "static const int row = row_value();"),
            "thread_local_row": ("const int row = row_value();",
                                 "thread_local const int row = row_value();"),
            "static_start": ("const int start = lane_value();",
                             "static const int start = lane_value();"),
            "thread_local_start": ("const int start = lane_value();",
                                   "thread_local const int start = lane_value();"),
        }
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            for name, (original, replacement) in variants.items():
                with self.subTest(name=name):
                    source = temporary_path / f"{name}.cpp"
                    source.write_text(fixture.replace(original, replacement))
                    report = run(source, shutil.which("clang++"), ["-std=c++17"],
                                 "entry", 32, temporary_path / f"{name}-evidence")
                    prefix = report["row_prefix"]
                    self.assertEqual(prefix["status"], "unknown", prefix)
                    self.assertFalse(prefix["checked"])
                    self.assertFalse(prefix["deployable"])

    def test_cpu_witness_persistent_coordinates_are_initialized_once(self):
        source_text = r"""
#include <cstdio>

int ordinary_calls = 0;
int static_calls = 0;
int thread_local_calls = 0;

int ordinary_coordinate() { return ordinary_calls++; }
int static_coordinate() { return static_calls++; }
int thread_local_coordinate() { return thread_local_calls++; }

int ordinary_value() {
  const int value = ordinary_coordinate();
  return value;
}

int static_value() {
  static const int value = static_coordinate();
  return value;
}

int thread_local_value() {
  thread_local const int value = thread_local_coordinate();
  return value;
}

int main() {
  const int ordinary_first = ordinary_value();
  const int ordinary_second = ordinary_value();
  const int static_first = static_value();
  const int static_second = static_value();
  const int thread_local_first = thread_local_value();
  const int thread_local_second = thread_local_value();
  std::printf("ordinary=%d,%d static=%d,%d thread_local=%d,%d\n",
              ordinary_first, ordinary_second, static_first, static_second,
              thread_local_first, thread_local_second);
}
"""
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            source = temporary_path / "coordinate_storage.cpp"
            executable = temporary_path / "coordinate_storage"
            source.write_text(source_text)
            compiled = subprocess.run(
                [shutil.which("clang++"), "-std=c++17", str(source), "-o", str(executable)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run(
                [str(executable)], capture_output=True, text=True, check=False,
            )
            self.assertEqual(executed.returncode, 0, executed.stderr)
            self.assertEqual(
                executed.stdout,
                "ordinary=0,1 static=0,0 thread_local=0,0\n",
            )


if __name__ == "__main__":
    unittest.main()
