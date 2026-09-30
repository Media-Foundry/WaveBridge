"""Native CUDA AST through fresh numeric/copy/launch checks; no mocked recovery."""
import copy
from pathlib import Path
import unittest

import test_query_output_native_clang as query_fixture
from wavebridge.frontend.native_captures import collect
from wavebridge.frontend.clang_ast import _walk
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.launch_binding import check_guarded_configuration_copy


@unittest.skipUnless(query_fixture.PLUGIN, "requires compiler-matched native plugin")
class GuardedConfigurationTests(unittest.TestCase):
    composed_selection = query_fixture.QueryOutputTests.composed_selection
    quotient_selection = query_fixture.QueryOutputTests.quotient_selection
    source_guard_selection = query_fixture.QueryOutputTests.source_guard_selection
    constructor_args = query_fixture.QueryOutputTests.constructor_args
    contracts = query_fixture.QueryOutputTests.contracts

    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/field_snapshot_launch.cu",
                         query_fixture.COMPILER, Path(query_fixture.PLUGIN),
                         ["-std=c++17", "--cuda-host-only", "-nocudainc", "-nocudalib"])
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.payload = report["payload"]
        cls.ids = {n["name"]: n["id"] for n in _walk(cls.payload["ast"]) if n.get("kind") == "FunctionDecl"}

    def arguments(self, name):
        args, guard = self.constructor_args(name)
        function = next(n for n in _walk(self.payload["ast"]) if n.get("id") == args[4]["callee_id"])
        launch = next(n for n in _walk(function) if n.get("kind") == "CUDAKernelCallExpr")
        config = launch["inner"][1]
        selection = {"schema_version": "launch-selection/v1", "ast_root_sha256": _hash(self.payload["ast"]),
                     "kernel_declaration_id": self.ids["guarded_target"], "launch_id": launch["id"],
                     "configuration_declaration_id": self.ids["cudaConfigureCall"],
                     "configuration_expression_ids": [n["id"] for n in config["inner"][1:]]}
        return args, guard, selection

    def run_check(self, name, position=1, **options):
        args, guard, selection = self.arguments(name)
        return check_guarded_configuration_copy(self.payload, selection, *args, query_guard_id=guard,
                                                configuration_position=position, **options)

    def test_exact_block_slot_uses_recovered_fields_and_keeps_API_debt(self):
        before = copy.deepcopy(self.payload)
        report = self.run_check("configured_guard")
        self.assertEqual(report["status"], "checked", report)
        self.assertEqual([f["interval"]["lower"] for f in report["fields"]], [32, 4, 1])
        self.assertEqual(report["configuration_position"], 1)
        args, _, selection = self.arguments("configured_guard")
        self.assertEqual(report["input_sha256"]["launch_selection"], _hash(selection))
        self.assertEqual(report["input_sha256"]["conversion_contract"], _hash(args[5]))
        self.assertEqual(report["input_sha256"]["output_contract"], _hash(args[6]))
        self.assertEqual(report["input_sha256"]["copy_inputs"], _hash(report["checks"]["copy"]["input_sha256"]))
        self.assertEqual(report["checks"]["copy"]["field_values_preserved_to_selected_copy_evaluation"], "conditional")
        self.assertEqual(report["copy_expression_id"], self.arguments("configured_guard")[2]["configuration_expression_ids"][1])
        for key in ("launch_API_semantics_verified", "all_configuration_arguments_checked",
                    "launch_execution_proved", "runtime_object_provenance_verified", "source_program_checked", "deployable"):
            self.assertFalse(report[key])
        self.assertEqual(before, self.payload)

    def test_position_is_exact_syntax_not_inferred_block_role(self):
        self.assertEqual(self.run_check("configured_grid", 0)["status"], "checked")
        self.assertEqual(self.run_check("configured_grid", 1)["status"], "unknown")
        self.assertEqual(self.run_check("configured_guard", 0)["status"], "unknown")

    def test_changed_source_invalid_position_and_budget_fail_closed(self):
        self.assertEqual(self.run_check("configured_write")["status"], "unknown")
        for position in (True, -1, 4, "1"):
            self.assertEqual(self.run_check("configured_guard", position)["status"], "unknown")
        self.assertEqual(self.run_check("configured_guard", max_ast_nodes=1)["status"], "unknown")

    def test_other_launch_and_swapped_slots_cannot_reuse_source_conclusion(self):
        args, guard, selection = self.arguments("configured_guard")
        other = self.arguments("configured_grid")[2]
        for bad in (other, {**selection, "configuration_expression_ids": selection["configuration_expression_ids"][::-1]},
                    {**selection, "ast_root_sha256": "stale"}):
            report = check_guarded_configuration_copy(self.payload, bad, *args,
                         query_guard_id=guard, configuration_position=1)
            self.assertEqual(report["status"], "unknown", report)
