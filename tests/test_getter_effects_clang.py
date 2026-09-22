"""Real-source wrapper checks; external leaf premises remain explicit fixtures."""

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.getter_returns import check, check_no_memory_write
from tests.test_getter_effects import protocol
from tests.test_getter_returns import ABI


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class GetterEffectsClangTests(unittest.TestCase):
    def test_real_cuda_builtin_cast_still_needs_explicit_domain_and_effect(self):
        collected = collect(Path(__file__).parent / "fixtures/getter_builtin.cu",
                            shutil.which("clang++"),
                            ["-std=c++17", "--cuda-device-only", "--cuda-gpu-arch=sm_80",
                             "-nocudainc", "-nocudalib"], "builtin_getter",
                            full_translation_unit=True)
        self.assertEqual(collected["status"], "collected", collected.get("execution"))
        root = collected["ast_roots"][0]
        functions = {node["name"]: node for node in _walk(root)
                     if node.get("kind") == "FunctionDecl" and node.get("name")}
        getter = functions["builtin_getter"]
        cast = [node for node in _walk(getter) if node.get("castKind") == "BuiltinFnToFnPtr"]
        self.assertEqual(len(cast), 1)
        leaf = cast[0]["inner"][0]["referencedDecl"]["id"]
        contract = {"schema_version": "getter-leaf-domain/v1", "declaration_id": leaf,
                    "arguments": [], "return_type": {"qualType": "int"},
                    "lower": 0, "upper": 7}
        for name in ("builtin_getter", "builtin_with_store", "builtin_with_call"):
            start = functions[name]["id"]
            result = check_no_memory_write(root, start, contract, ABI,
                                           protocol(root, start=start, leaf=leaf))
            self.assertEqual(result["status"], "checked" if name == "builtin_getter"
                             else "unknown", result)
            self.assertFalse(result["external_leaf_effect_verified"])
            self.assertFalse(result["deployable"])
        self.assertEqual(check_no_memory_write(root, getter["id"], contract, ABI, None)
                         ["status"], "unknown")
        # Builtin identity does not make signed-to-unsigned value preservation unconditional.
        contract["lower"] = -1
        self.assertEqual(check(root, getter["id"], contract, ABI)["status"], "rejected")

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
