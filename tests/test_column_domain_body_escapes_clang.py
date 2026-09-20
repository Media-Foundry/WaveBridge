"""Real-AST column-domain composition regressions for body-effect escapes.

The conditional thread report below is an explicit fixture premise.  This test
does not recover or check a thread-coordinate getter; all column-loop, launch,
positional argument and host-guard evidence is recovered from the real AST.
"""

from pathlib import Path
import shutil
import unittest

from wavebridge.analysis.launch_facts import inspect as inspect_launch
from wavebridge.column_domain_check import check
from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.getter_returns import _hash


SOURCE = Path(__file__).parent / "fixtures/column_domain_body_escapes.cu"
COMPILER = shutil.which("clang++")
ABI = {"int": {"bits": 32, "signed": True}}


@unittest.skipUnless(COMPILER, "requires real clang++")
class ColumnDomainBodyEscapesClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frontend = collect(
            SOURCE, COMPILER,
            ["-std=c++17", "--cuda-host-only", "-nocudainc", "-nocudalib"],
            "ordinary_columns", full_translation_unit=True)
        if frontend.get("status") != "collected":
            raise AssertionError(frontend)
        cls.root = frontend["ast_roots"][0]
        cls.root_hash = _hash(cls.root)
        cls.functions = {
            node["name"]: node for node in _walk(cls.root)
            if node.get("kind") == "FunctionDecl" and isinstance(node.get("id"), str)
        }

    def run_composition(self, kernel_name, launcher_name):
        kernel = self.functions[kernel_name]
        launcher = self.functions[launcher_name]
        launch_nodes = [node for node in _walk(launcher)
                        if node.get("kind") == "CUDAKernelCallExpr"]
        self.assertEqual(len(launch_nodes), 1)
        launch_id = launch_nodes[0]["id"]

        launches = inspect_launch(self.root, kernel["id"])
        sites = [site for site in launches["sites"] if site.get("launch_id") == launch_id]
        self.assertEqual(len(sites), 1, launches)
        seed_parameter = next(child for child in kernel.get("inner", [])
                              if child.get("kind") == "ParmVarDecl" and
                              child.get("name") == "seed")
        tid_declarations = [node for node in _walk(kernel)
                            if node.get("kind") == "VarDecl" and node.get("name") == "tid"]
        self.assertEqual(len(tid_declarations), 1)
        # The source makes tid=seed explicit, but its coordinate interpretation
        # is deliberately supplied as a conditional fixture premise here.
        self.assertIsInstance(seed_parameter.get("id"), str)
        start_id = tid_declarations[0]["id"]
        binding = {
            "schema_version": "thread-start-assumptions/v1",
            "ast_root_sha256": self.root_hash,
            "kernel_declaration_id": kernel["id"],
            "launch_id": launch_id,
            "fixture_coordinate_premise": "tid_is_assumed_to_range_over_0_through_255",
        }
        thread = {
            "schema_version": "conditional-thread-start-check/v1",
            "status": "checked", "kernel_declaration_id": kernel["id"],
            "launch_id": launch_id, "int_bits": 32,
            "start_interval": {"lower": 0, "upper": 255},
            "start_declaration_id": start_id,
            "fixture_only": "thread_getter_not_checked",
            "input_sha256": {"root": self.root_hash, "integer_types": _hash(ABI),
                             "binding": _hash(binding)},
        }
        return check(self.root, thread, ABI, binding,
                     use_host_guard_assumptions=True)

    def test_real_launch_guard_and_ordinary_loop_compose(self):
        result = self.run_composition("ordinary_columns", "launch_ordinary")
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(len(result["loops"]), 1)
        self.assertEqual(result["loops"][0]["coverage"]["interval_checked"],
                         {"lower": 1, "upper": 1023})
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_real_composition_rejects_hidden_body_effects_as_unknown(self):
        cases = (
            ("direct_columns", "launch_direct"),
            ("static_cast_columns", "launch_static_cast"),
            ("c_style_columns", "launch_c_style"),
            ("comma_columns", "launch_comma"),
            ("asm_columns", "launch_asm"),
        )
        for kernel, launcher in cases:
            with self.subTest(kernel=kernel):
                result = self.run_composition(kernel, launcher)
                self.assertEqual(result["status"], "unknown", result)
                self.assertEqual(result["reason"], "column_recovery_incomplete")

    def test_real_composition_rejects_reference_aliases_but_accepts_value_copy(self):
        aliases = (
            ("using_ref_columns", "launch_using_ref"),
            ("typedef_ref_columns", "launch_typedef_ref"),
            ("nested_ref_columns", "launch_nested_ref"),
        )
        for kernel, launcher in aliases:
            with self.subTest(kernel=kernel):
                result = self.run_composition(kernel, launcher)
                self.assertEqual(result["status"], "unknown", result)
                self.assertEqual(result["reason"], "column_recovery_incomplete")
        value_copy = self.run_composition("value_alias_columns", "launch_value_alias")
        self.assertEqual(value_copy["status"], "checked", value_copy)
        casts = [node for node in _walk(self.functions["static_cast_value_columns"])
                 if node.get("kind") == "CXXStaticCastExpr"]
        self.assertEqual(len(casts), 1, casts)
        self.assertEqual(casts[0].get("type", {}).get("qualType"), "int")
        cast_copy = self.run_composition("static_cast_value_columns",
                                         "launch_static_cast_value")
        self.assertEqual(cast_copy["status"], "checked", cast_copy)


if __name__ == "__main__":
    unittest.main()
