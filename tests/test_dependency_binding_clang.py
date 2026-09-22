"""Same-invocation real compiler dependency evidence, not a frozen snapshot."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wavebridge.frontend.clang_ast import collect
from wavebridge.source import run


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class DependencyBindingClangTests(unittest.TestCase):
    def test_header_changes_bind_observed_contents_and_temp_paths_do_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            header = root / "value header.h"
            header.write_text("#define STEP 4\n")
            source = root / "input.cpp"
            source.write_text('#include <stddef.h>\n#include "value header.h"\nvoid target() {}\n')
            args = (source, shutil.which("clang++"), ["-std=c++17"], "target")
            first = collect(*args, dependency_binding="required")
            second = collect(*args, dependency_binding="required")
            self.assertEqual("collected", first["status"], first)
            self.assertEqual("observed", first["dependency_binding"]["status"])
            self.assertTrue(any(Path(item["resolved_path"]).name == "stddef.h"
                                for item in first["dependency_binding"]["files"]))
            self.assertEqual(first["dependency_binding"]["manifest_sha256"],
                             second["dependency_binding"]["manifest_sha256"])
            header.write_text("#define STEP 8\n")
            third = collect(*args, dependency_binding="required")
            self.assertNotEqual(first["dependency_binding"]["manifest_sha256"],
                                third["dependency_binding"]["manifest_sha256"])
            self.assertEqual(first["source_sha256"], third["source_sha256"])
            self.assertFalse(third["compilation_input_closure_established"])

    def test_source_entry_defaults_to_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.cpp"
            source.write_text("void target(int n, int tid) { for(int i=tid;i<n;i+=4) {} }\n")
            report = run(source, shutil.which("clang++"), ["-std=c++17"], "target", 32, root / "out")
            self.assertEqual("analyzed", report["status"], report)
            self.assertEqual("required", report["dependency_binding_mode"])
            self.assertEqual("observed", report["dependency_binding"]["status"])
            self.assertFalse(report["checked"])
            self.assertFalse(report["compilation_input_closure_established"])

    def test_missing_manifest_blocks_successful_ast(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.cpp"
            source.write_text("void target() {}\n")
            with patch("wavebridge.frontend.clang_ast.observe", return_value={"status": "unknown"}):
                report = run(source, shutil.which("clang++"), [], "target", 32, Path(directory) / "out")
            self.assertEqual("unknown", report["status"])
            self.assertEqual("frontend_dependency_binding_failed", report["reason"])
            self.assertIsNone(report["analysis"])

    def test_dependency_options_and_response_files_cannot_override_collector(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.cpp"
            source.write_text("void target() {}\n")
            for flags in (["-MFelsewhere"], ["@response"], ["-Wp,-MD,elsewhere"], ["-Xclang", "-dependency-file"]):
                result = collect(source, shutil.which("clang++"), flags, "target", dependency_binding="required")
                self.assertEqual("input_error", result["status"])


if __name__ == "__main__":
    unittest.main()
