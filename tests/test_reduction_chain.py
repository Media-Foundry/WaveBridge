"""Real Clang structural linking; no GPU or external intrinsic semantics."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from wavebridge.source import run
from wavebridge.analysis.reduction_chain import recover
from wavebridge.analysis import reduction_discovery
from wavebridge.analysis import reduction_chain
from wavebridge.analysis.shared_storage import recover as recover_storage
from wavebridge.frontend.clang_ast import _walk


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class ReductionChainTests(unittest.TestCase):
    def setUp(self):
        fixture = Path(__file__).parent / "fixtures"
        helpers = (fixture / "reduction_entry.cpp").read_text().split("float entry(")[0]
        entry = (fixture / "normalization_output.cpp").read_text().split("void wrong_column(")[0]
        entry = entry.replace("float reduce_partial(float, float *);", "")
        self.source = helpers + entry.replace("reduce_partial(partial, scratch)", "aggregate(partial, scratch)")

    def analyze(self, source):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.cpp"
            path.write_text(source)
            output = Path(temporary) / "report"
            report = run(path, shutil.which("clang++"), ["-std=c++17"], "entry", 32, output)
            root = json.loads((output / "ast.json").read_text())["ast_roots"][0]
            return report, root

    def test_connects_renamed_source_without_oracle_and_keeps_obligations(self):
        source = self.source.replace("aggregate", "different_block").replace("subgroup", "different_warp")
        report, _ = self.analyze(source)
        chain = report["reduction_chain"]
        self.assertEqual("recovered", chain["status"], chain)
        self.assertEqual([16, 8, 4, 2, 1], chain["offsets"])
        self.assertEqual(256, chain["block_threads"])
        self.assertEqual(32, chain["width"])
        self.assertEqual(3, len(chain["links"]))
        self.assertEqual("recovered", chain["shared_storage"]["status"])
        self.assertEqual(32, chain["shared_storage"]["extent_elements"])
        self.assertEqual("not_proven_shared", chain["shared_storage"]["storage_kind"])
        self.assertEqual(chain["links"][0]["callee_id"], chain["links"][1]["caller_id"])
        self.assertEqual(chain["links"][1]["callee_id"], chain["links"][2]["caller_id"])
        self.assertFalse(chain["checked"])
        self.assertFalse(chain["deployable"])
        self.assertTrue(chain["unresolved_calls"])
        self.assertIn("analysis/reduction_chain.py", report["implementation_sha256"])
        self.assertIn("analysis/entry_control.py", report["implementation_sha256"])
        self.assertEqual(chain["entry_control"]["status"], "recovered")
        self.assertEqual(len(chain["entry_control"]["loop_obligations"]), 1)
        self.assertEqual(chain["entry_control"]["participation"], "not_established")

    def test_real_early_return_does_not_inherit_local_structure_participation(self):
        source = self.source.replace("float partial = 0.0f;", "if (tid != 0) return;\n  float partial = 0.0f;")
        report, _ = self.analyze(source)
        chain = report["reduction_chain"]
        self.assertEqual(chain["status"], "recovered", chain)
        self.assertEqual(chain["entry_control"]["status"], "unknown")
        self.assertEqual(chain["entry_control"]["reason"], "unsupported_prefix_control_or_expression")
        self.assertFalse(chain["checked"])

    def test_value_parameter_is_not_assumed_to_be_first(self):
        source = self.source.replace("aggregate(float value, float *shared)", "aggregate(float *shared, float value)")
        source = source.replace("aggregate(partial, scratch)", "aggregate(scratch, partial)")
        report, _ = self.analyze(source)
        self.assertEqual("recovered", report["reduction_chain"]["status"])
        self.assertEqual(1, report["reduction_chain"]["links"][0]["argument_index"])
        self.assertEqual(0, report["reduction_chain"]["shared_storage"]["argument_index"])

    def test_array_extents_are_not_assumed_from_width(self):
        for declaration, extent, status in (("float scratch[2];", 2, "declared_static_extent"),
                                             ("extern float scratch[];", None, "external_allocation_required")):
            with self.subTest(declaration=declaration):
                report, _ = self.analyze(self.source.replace("float scratch[32];", declaration))
                storage = report["reduction_chain"]["shared_storage"]
                self.assertEqual("recovered", storage["status"])
                self.assertEqual(extent, storage["extent_elements"])
                self.assertEqual(status, storage["capacity_status"])
                self.assertEqual("not_established", storage["runtime_capacity"])
                self.assertFalse(storage["checked"])

    def test_array_binding_refuses_casts_and_missing_local_declaration(self):
        report, root = self.analyze(self.source)
        chain = report["reduction_chain"]
        link = chain["links"][0]
        storage = chain["shared_storage"]
        call = next(n for n in _walk(root) if n.get("kind") == "CallExpr" and n.get("range") == link["call_range"])
        argument = call["inner"][storage["argument_index"] + 1]
        self.assertEqual("ArrayToPointerDecay", argument["castKind"])
        argument["castKind"] = "BitCast"
        result = recover_storage(root, chain["function_id"], link["callee_id"], link["call_range"], storage["parameter_id"])
        self.assertEqual("unsupported_array_conversion", result["reason"])
        argument["castKind"] = "ArrayToPointerDecay"
        declaration = next(n for n in _walk(root) if n.get("kind") == "VarDecl" and n.get("id") == storage["array_declaration_id"])
        declaration["id"] = "different-local-array"
        result = recover_storage(root, chain["function_id"], link["callee_id"], link["call_range"], storage["parameter_id"])
        self.assertEqual("preceding_local_array_not_unique", result["reason"])

    def test_external_shared_extent_is_not_static_allocation_evidence(self):
        report, root = self.analyze(self.source)
        chain = report["reduction_chain"]
        link = chain["links"][0]
        storage = chain["shared_storage"]
        declaration = next(n for n in _walk(root) if n.get("kind") == "VarDecl" and n.get("id") == storage["array_declaration_id"])
        # AST mutation tests classification only; not evidence of accepted HIP syntax.
        declaration["storageClass"] = "extern"
        declaration.setdefault("inner", []).append({"kind": "CUDASharedAttr"})
        result = recover_storage(root, chain["function_id"], link["callee_id"], link["call_range"], storage["parameter_id"])
        self.assertEqual(32, result["extent_elements"])
        self.assertEqual("shared_dynamic", result["storage_kind"])
        self.assertEqual("launch_bytes_required", result["capacity_status"])
        self.assertEqual("invalid_declaration_id", recover_storage(root, chain["function_id"], link["callee_id"], link["call_range"], None)["reason"])

    def test_inconsistent_width_and_step_are_not_connected(self):
        variants = [
            (self.source.replace("constexpr int step = 256", "constexpr int step = 128"),
             "column_step_block_threads_mismatch"),
            (self.source.replace("constexpr int width = 32;", "constexpr int width = 32; constexpr int different_width = 16;")
             .replace("coordinate() / width", "coordinate() / different_width")
             .replace("coordinate() % width", "coordinate() % different_width")
             .replace("threads / width", "threads / different_width"), "block_xor_width_mismatch")]
        for source, reason in variants:
            with self.subTest(reason=reason):
                report, _ = self.analyze(source)
                self.assertEqual("unknown", report["reduction_chain"]["status"])
                self.assertEqual(reason, report["reduction_chain"]["reason"])

    def test_missing_consumer_definition_and_budget_remain_unknown(self):
        source = self.source.replace("void entry(", "float external(float, float *);\nvoid entry(")
        report, _ = self.analyze(source.replace("aggregate(partial, scratch)", "external(partial, scratch)"))
        self.assertEqual("consumer_block_not_unique", report["reduction_chain"]["reason"])
        report, root = self.analyze(self.source)
        with patch.object(reduction_discovery, "MAX_CANDIDATE_ATTEMPTS", 0):
            result = recover(root, report["reduction_chain"]["function_id"], 32)
        self.assertEqual("discovery_budget_incomplete", result["reason"])

    def test_ambiguous_component_reports_are_not_resolved_by_list_order(self):
        report, root = self.analyze(self.source)
        function_id = report["reduction_chain"]["function_id"]
        for key, reason in (("block_candidates", "consumer_block_not_unique"),
                            ("xor_candidates", "block_xor_not_unique")):
            discovered = reduction_discovery.discover(root, function_id, 32)
            discovered[key].append(discovered[key][0])
            with self.subTest(key=key), patch.object(reduction_chain, "discover", return_value=discovered):
                result = recover(root, function_id, 32)
                self.assertEqual("unknown", result["status"])
                self.assertEqual(reason, result["reason"])


if __name__ == "__main__":
    unittest.main()
