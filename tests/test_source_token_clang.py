"""Real Clang source-token edits, not GPU adaptation or semantic validation."""
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.transforms.source_token import edit


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class SourceTokenClangTests(unittest.TestCase):
    def collect_source(self, path):
        result = collect(path, shutil.which("clang++"), ["-std=c++17"], "target",
                         full_translation_unit=True, dependency_binding="required")
        self.assertEqual("collected", result["status"], result.get("execution"))
        return result["ast_roots"][0]

    def propose(self, path, root):
        # Name selects a fixture declaration only; this is not semantic width recovery.
        declaration, = [n for n in _walk(root)
                        if n.get("kind") == "VarDecl" and n.get("name") == "width"]
        source = path.read_bytes()
        return edit(source, hashlib.sha256(source).hexdigest(), root,
                    declaration["id"], 64, source_path=str(path))

    def test_edit_reparses_as_new_source_and_preserves_other_constants(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.cpp"
            source = ("// 字节偏移\nconstexpr int width = 32;\n"
                      "int target(int x) { return x / width + 32; }\n"
                      "int launch() { return target(32); }\n").encode()
            path.write_bytes(source)
            result = self.propose(path, self.collect_source(path))
            self.assertEqual("generated_unvalidated_candidate", result["status"], result)
            expected = source.replace(b"width = 32", b"width = 64", 1)
            self.assertEqual(expected, result["candidate_source"])
            target = Path(directory) / "candidate.cpp"
            target.write_bytes(result["candidate_source"])
            fresh = self.collect_source(target)
            declaration, = [n for n in _walk(fresh)
                            if n.get("kind") == "VarDecl" and n.get("name") == "width"]
            self.assertEqual("64", declaration["inner"][0]["value"])
            for flag in ("checked", "source_program_checked", "deployable"):
                self.assertFalse(result["manifest"][flag])

    def test_macro_initializer_is_not_a_direct_main_source_token(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.cpp"
            path.write_text("#define WIDTH 32\nconstexpr int width = WIDTH;\n"
                            "int target() { return width; }\n")
            result = self.propose(path, self.collect_source(path))
            self.assertEqual("unknown", result["status"])
            self.assertNotIn("candidate_source", result)

    def test_header_initializer_cannot_edit_same_offset_in_main_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.cpp"
            (Path(directory) / "width.h").write_text("constexpr int width = 32;\n")
            path.write_text('#include "width.h"\nint target() { return width; }\n')
            result = self.propose(path, self.collect_source(path))
            self.assertEqual("unknown", result["status"])
            self.assertNotIn("candidate_source", result)


if __name__ == "__main__":
    unittest.main()
