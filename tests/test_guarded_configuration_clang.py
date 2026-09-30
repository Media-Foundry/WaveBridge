"""Native CUDA AST through fresh numeric/copy/launch checks; no mocked recovery."""
import copy
from pathlib import Path
import unittest

import test_query_output_native_clang as query_fixture
from wavebridge.frontend.native_captures import collect
from wavebridge.frontend.clang_ast import _walk
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.launch_binding import check_guarded_configuration_copy
from wavebridge.verification.block_configuration import check_guarded_local_coordinate


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

    def coordinate_arguments(self, axis=0):
        args, guard, selection = self.arguments("configured_guard")
        args = list(args)
        args[-1] = {**args[-1], "unsigned long": {"bits": 64, "signed": False}}
        nodes = list(_walk(self.payload["ast"]))
        record = next(n for n in nodes if n.get("kind") == "CXXRecordDecl" and
                      n.get("name") == "GuardDimsAlias" and n.get("completeDefinition"))
        config = next(n for n in nodes if n.get("id") == selection["configuration_declaration_id"])
        protocol = {"schema_version": "launch-coordinate-assumptions/v1",
                    **{k: selection[k] for k in ("ast_root_sha256", "kernel_declaration_id", "launch_id",
                                                "configuration_declaration_id")},
                    "configuration_parameter_id": [n["id"] for n in config["inner"] if n.get("kind") == "ParmVarDecl"][1],
                    "record_declaration_id": record["id"], "block_position": 1,
                    "fields": {n["name"]: n["id"] for n in record["inner"] if n.get("kind") == "FieldDecl"},
                    "coordinate": {"declaration_id": self.ids["local_leaf"], "return_type": {"qualType": "unsigned long"},
                                   "axis": axis, "semantics": "workgroup_local_id"},
                    "semantics": "bound_parameter_axes_define_selected_kernel_workgroup_extents"}
        local = next(n["id"] for n in nodes if n.get("kind") == "VarDecl" and
                     n.get("name") == ("local_coordinate_x" if axis == 0 else "local_coordinate_y"))
        return args, guard, selection, protocol, local

    def test_coordinate_domains_come_from_two_dimensional_configuration(self):
        before = copy.deepcopy(self.payload)
        for axis, upper in ((0, 31), (1, 3)):
            args, guard, selection, protocol, local = self.coordinate_arguments(axis)
            report = check_guarded_local_coordinate(self.payload, selection, *args, protocol, local, query_guard_id=guard)
            self.assertEqual(report["status"], "checked", report)
            self.assertEqual(report["dimensions"], {"x": 32, "y": 4, "z": 1})
            self.assertEqual(report["block_thread_count"], 128)
            self.assertEqual(report["result_interval"], {"lower": 0, "upper": upper})
            self.assertEqual(report["derived_leaf_domain"]["upper"], upper)
            for key in ("coordinate_API_verified", "runtime_configuration_verified", "hardware_limits_checked",
                        "coordinate_history_checked", "thread_participation_checked", "source_program_checked", "deployable"):
                self.assertFalse(report[key])
        self.assertEqual(before, self.payload)

    def test_axis_roles_are_explicit_assumptions_not_field_name_heuristics(self):
        args, guard, selection, protocol, local = self.coordinate_arguments()
        protocol["fields"]["x"], protocol["fields"]["y"] = protocol["fields"]["y"], protocol["fields"]["x"]
        report = check_guarded_local_coordinate(self.payload, selection, *args, protocol, local, query_guard_id=guard)
        self.assertEqual(report["status"], "checked", report)
        self.assertEqual(report["result_interval"], {"lower": 0, "upper": 3})
        self.assertFalse(report["coordinate_API_verified"])

    def test_coordinate_wrong_owner_axis_and_field_identity_fail_closed(self):
        args, guard, selection, protocol, local = self.coordinate_arguments()
        changes = []
        bad = copy.deepcopy(protocol); bad["coordinate"]["axis"] = 1; changes.append((bad, local))
        bad = copy.deepcopy(protocol); bad["fields"]["x"] = "wrong"; changes.append((bad, local))
        bad = copy.deepcopy(protocol); bad["configuration_parameter_id"] = "wrong"; changes.append((bad, local))
        bad = copy.deepcopy(protocol); bad["coordinate"]["declaration_id"] = self.ids["local_y"]; changes.append((bad, local))
        bad = copy.deepcopy(protocol); bad["coordinate"]["return_type"] = {"qualType": "unsigned int"}; changes.append((bad, local))
        changes.append((protocol, args[0]))  # A valid getter initializer, but in the host function.
        for changed, selected_local in changes:
            report = check_guarded_local_coordinate(self.payload, selection, *args, changed, selected_local, query_guard_id=guard)
            self.assertEqual(report["status"], "unknown", report)
            self.assertFalse(report["coordinate_initialization_domain_checked"])

    def test_coordinate_protocol_cannot_supply_numeric_bounds_or_stale_root(self):
        args, guard, selection, protocol, local = self.coordinate_arguments()
        for changed in ({**protocol, "upper": 31},
                        {**protocol, "coordinate": {**protocol["coordinate"], "upper": 31}},
                        {**protocol, "fields": {**protocol["fields"], "upper": 31}},
                        {**protocol, "ast_root_sha256": "old"},
                        {**protocol, "block_position": True}):
            report = check_guarded_local_coordinate(self.payload, selection, *args, changed, local, query_guard_id=guard)
            self.assertEqual(report["status"], "unknown", report)
        self.assertEqual(check_guarded_local_coordinate(self.payload, selection, *args, protocol, local,
                         query_guard_id=guard, max_ast_nodes=1)["status"], "unknown")

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
