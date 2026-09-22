"""Real-source wrapper checks; external leaf premises remain explicit fixtures."""

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.getter_returns import check_no_memory_write
from tests.test_getter_effects import protocol
from tests.test_getter_returns import ABI


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class GetterEffectsClangTests(unittest.TestCase):
    def test_real_signed_leaf_wrapper_and_effect_mutations(self):
        for extra in ("", "sink = 1;", "opaque();"):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "getter.cpp"
                source.write_text(
                    "extern int leaf(); extern int sink; extern void opaque();\n"
                    "unsigned getter() { " + extra + " return leaf(); }\n")
                collected = collect(source, shutil.which("clang++"), ["-std=c++17"],
                                    "getter", full_translation_unit=True)
                self.assertEqual(collected["status"], "collected")
                root = collected["ast_roots"][0]
                declarations = {node["name"]: node for node in _walk(root)
                                if node.get("kind") == "FunctionDecl" and node.get("name")}
                start, leaf = declarations["getter"]["id"], declarations["leaf"]["id"]
                contract = {"schema_version": "getter-leaf-domain/v1",
                            "declaration_id": leaf, "arguments": [],
                            "return_type": {"qualType": "int"}, "lower": 0, "upper": 7}
                result = check_no_memory_write(
                    root, start, contract, ABI, protocol(root, start=start, leaf=leaf))
                self.assertEqual(result["status"], "unknown" if extra else "checked", result)
                self.assertFalse(result["external_leaf_effect_verified"])
                self.assertFalse(result["deployable"])
