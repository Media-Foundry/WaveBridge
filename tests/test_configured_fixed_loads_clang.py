"""Fresh native configuration -> coordinate -> fixed guarded load composition."""
import copy
from pathlib import Path
import unittest

import test_query_output_native_clang as query_fixture
from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect
from wavebridge.verification.block_configuration import check_guarded_coordinate_to_fixed_loads
from wavebridge.verification.getter_returns import _hash


@unittest.skipUnless(query_fixture.PLUGIN, "requires compiler-matched native plugin")
class ConfiguredFixedLoadsTests(unittest.TestCase):
    composed_selection = query_fixture.QueryOutputTests.composed_selection
    quotient_selection = query_fixture.QueryOutputTests.quotient_selection
    source_guard_selection = query_fixture.QueryOutputTests.source_guard_selection
    constructor_args = query_fixture.QueryOutputTests.constructor_args
    contracts = query_fixture.QueryOutputTests.contracts

    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/configured_fixed_loads.cu",
                         query_fixture.COMPILER, Path(query_fixture.PLUGIN),
                         ["-std=c++17", "--cuda-host-only", "-nocudainc", "-nocudalib"])
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.payload = report["payload"]
        cls.nodes = list(_walk(cls.payload["ast"]))
        cls.functions = {n.get("name"): n for n in cls.nodes if n.get("kind") == "FunctionDecl"}
        cls.ids = {name: node["id"] for name, node in cls.functions.items()}

    def arguments(self, launch_name="configured_fixed", kernel_name="configured_fixed_load"):
        constructor, guard = self.constructor_args(launch_name)
        host = self.functions[launch_name]
        launch = next(n for n in _walk(host) if n.get("kind") == "CUDAKernelCallExpr")
        config = launch["inner"][1]
        selection = {"schema_version": "launch-selection/v1",
                     "ast_root_sha256": _hash(self.payload["ast"]),
                     "kernel_declaration_id": self.functions[kernel_name]["id"],
                     "launch_id": launch["id"],
                     "configuration_declaration_id": self.functions["cudaConfigureCall"]["id"],
                     "configuration_expression_ids": [n["id"] for n in config["inner"][1:]]}
        record = next(n for n in self.nodes if n.get("kind") == "CXXRecordDecl" and
                      n.get("name") == "GuardDimsAlias" and n.get("completeDefinition"))
        configure = self.functions["cudaConfigureCall"]
        fields = {n["name"]: n["id"] for n in record["inner"] if n.get("kind") == "FieldDecl"}
        protocol = {"schema_version": "launch-coordinate-assumptions/v1",
                    **{key: selection[key] for key in ("ast_root_sha256", "kernel_declaration_id",
                                                       "launch_id", "configuration_declaration_id")},
                    "configuration_parameter_id": [n["id"] for n in configure["inner"]
                                                   if n.get("kind") == "ParmVarDecl"][1],
                    "record_declaration_id": record["id"], "block_position": 1,
                    "fields": fields,
                    "coordinate": {"declaration_id": self.functions["local_leaf"]["id"],
                                   "return_type": {"qualType": "unsigned long"}, "axis": 0,
                                   "semantics": "workgroup_local_id"},
                    "semantics": "bound_parameter_axes_define_selected_kernel_workgroup_extents"}
        kernel = self.functions[kernel_name]
        declarations = {n.get("name"): n for n in _walk(kernel)
                        if n.get("kind") in {"VarDecl", "ParmVarDecl"} and n.get("name")}
        loops = [n for n in _walk(kernel) if n.get("kind") == "ForStmt"]
        abi = dict(constructor[-1])
        abi["unsigned long"] = {"bits": 64, "signed": False}
        positional = [self.payload, selection, *constructor[:-1], abi, protocol,
                      declarations["lane"]["id"], loops[0]["id"], loops[1]["id"], {}, {},
                      declarations["input"]["id"], declarations["n"]["id"], [0, 128]]
        binding = {"offset_declaration_id": declarations["offset"]["id"],
                   "row_declaration_id": declarations["first_batch"]["id"],
                   "stride_parameter_id": declarations["stride"]["id"],
                   "row_interval": [0, 4095], "stride_interval": [0, 128]}
        return positional, {"pointer_binding": binding, "query_guard_id": guard}

    def run_case(self, launch_name="configured_fixed", kernel_name="configured_fixed_load", **changes):
        args, kwargs = self.arguments(launch_name, kernel_name)
        kwargs.update(changes)
        return check_guarded_coordinate_to_fixed_loads(*args, **kwargs)

    def test_fresh_configuration_composes_to_selected_load(self):
        before = copy.deepcopy(self.payload)
        result = self.run_case()
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["fresh_configuration_composed"])
        self.assertTrue(result["guarded_load_relation_checked"])
        self.assertTrue(result["entry_pointer_history_checked"])
        self.assertEqual(result["result_interval"], {"lower": 0, "upper": 31})
        self.assertEqual(result["dimensions"], {"x": 32, "y": 4, "z": 1})
        self.assertEqual(result["checks"]["coordinate"]["input_sha256"]["root"],
                         result["checks"]["loads"]["input_sha256"]["root"])
        self.assertEqual(result["input_sha256"]["native_envelope"], _hash(self.payload))
        self.assertEqual(result["input_sha256"]["load_inputs"],
                         _hash(result["checks"]["loads"]["input_sha256"]))
        self.assertEqual(result["checks"]["loads"]["input_sha256"]["count_interval"], _hash([0, 128]))
        self.assertEqual(result["checks"]["loads"]["pointer_history_check"]["input_sha256"]["pointer_binding"],
                         _hash(self.arguments()[1]["pointer_binding"]))
        for key in ("source_program_checked", "deployable", "actual_thread_participation_checked",
                    "count_common_across_lanes_checked", "memory_load_coverage_checked",
                    "runtime_configuration_verified"):
            self.assertFalse(result[key])
        self.assertEqual(before, self.payload)

    def test_configuration_width_must_match_source_label_width(self):
        result = self.run_case("configured_fixed_16", "configured_fixed_load")
        self.assertEqual(result["checks"]["coordinate"]["status"], "checked", result)
        self.assertEqual(result["checks"]["coordinate"]["dimensions"]["x"], 16)
        self.assertEqual(result["status"], "unknown", result)
        self.assertFalse(result["guarded_load_relation_checked"])

    def test_wrong_load_and_mutated_inputs_fail_closed(self):
        cases = (("configured_fixed_wrong_index", "configured_fixed_load_wrong_index"),
                 ("configured_fixed_changed_n", "configured_fixed_load_changed_n"),
                 ("configured_fixed_changed_pointer", "configured_fixed_load_changed_pointer"))
        for launch, kernel in cases:
            with self.subTest(kernel=kernel):
                result = self.run_case(launch, kernel)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["guarded_load_relation_checked"])

    def test_wrong_owner_loop_root_and_protocols_fail_closed(self):
        args, kwargs = self.arguments()
        other_args, _ = self.arguments("configured_fixed_wrong_index", "configured_fixed_load_wrong_index")
        for position in (11, 12, 13):
            changed = list(args)
            changed[position] = other_args[position]
            with self.subTest(position=position):
                self.assertEqual(check_guarded_coordinate_to_fixed_loads(*changed, **kwargs)["status"], "unknown")
        stale = copy.deepcopy(args[10])
        stale["ast_root_sha256"] = "0" * 64
        changed = list(args); changed[10] = stale
        self.assertEqual(check_guarded_coordinate_to_fixed_loads(*changed, **kwargs)["status"], "unknown")
        changed = list(args); changed[15] = {"unused": {"schema_version": "not-a-protocol"}}
        self.assertEqual(check_guarded_coordinate_to_fixed_loads(*changed, **kwargs)["status"], "unknown")

    def test_budget_identity_and_no_hand_filled_domain_escape(self):
        args, kwargs = self.arguments()
        self.assertEqual(check_guarded_coordinate_to_fixed_loads(*args, **kwargs, max_ast_nodes=1)["status"], "unknown")
        duplicate = copy.deepcopy(self.payload)
        lane_id = args[11]
        duplicate["ast"]["inner"].append(copy.deepcopy(next(n for n in _walk(duplicate["ast"])
                                                               if n.get("id") == lane_id)))
        self.assertEqual(check_guarded_coordinate_to_fixed_loads(duplicate, *args[1:], **kwargs)["status"], "unknown")
        with self.assertRaises(TypeError):
            check_guarded_coordinate_to_fixed_loads(*args, **kwargs, derived_leaf_domain={"lower": 0, "upper": 31})


if __name__ == "__main__":
    unittest.main()
