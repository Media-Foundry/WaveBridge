"""Recipe safety guards only; these tests never build LLVM or validate Polygeist."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments/baselines/build_polygeist_frontend.sh"


@unittest.skipUnless(shutil.which("bash") and shutil.which("git"), "bash/git required")
class PolygeistBuildRecipeTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run(["bash", str(SCRIPT), *map(str, args)],
                              capture_output=True, text=True, timeout=10)

    def test_shell_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_uses_cmake_pool_without_duplicate_llvm_pool(self):
        recipe = SCRIPT.read_text()
        self.assertIn("-DLLVM_PARALLEL_LINK_JOBS= ", recipe)
        self.assertIn("-DCMAKE_JOB_POOLS=wavebridge_link=1", recipe)
        self.assertIn("-DCMAKE_JOB_POOL_LINK=wavebridge_link", recipe)
        self.assertNotIn("-DLLVM_PARALLEL_LINK_JOBS=1", recipe)

    def test_missing_arguments_do_not_start_build(self):
        result = self.invoke()
        self.assertEqual(2, result.returncode)
        self.assertIn("usage:", result.stderr)

    def test_invalid_parallelism_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "build"
            for jobs in ("0", "17", "-1", "all", "1.5"):
                with self.subTest(jobs=jobs):
                    result = self.invoke(ROOT, output, jobs)
                    self.assertEqual(2, result.returncode)
                    self.assertFalse(output.exists())

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "keep.txt"
            marker.write_text("user evidence")
            result = self.invoke(ROOT, directory)
            self.assertEqual(2, result.returncode)
            self.assertIn("Refusing to overwrite", result.stderr)
            self.assertEqual("user evidence", marker.read_text())

    def test_unrelated_repository_is_rejected_before_creating_build(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "build"
            result = self.invoke(ROOT, output)
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(output.exists())

    def test_nested_build_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested"
            result = self.invoke(directory, output)
            self.assertEqual(2, result.returncode)
            self.assertIn("outside the source checkout", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
