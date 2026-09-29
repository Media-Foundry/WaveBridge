"""Parser fixtures only; real SDK ABI evidence is collected separately."""
import copy
import hashlib
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
from experiments.hip_api_abi_probe import FIELDS, BOOL_FIELDS, observations, run


class ApiAbiObservationTests(unittest.TestCase):
    def fixture(self):
        return {"status": "collected", "ast_roots": [{"kind": "FunctionDecl", "name": "WaveBridgeHipAbiProbe",
                "inner": [{"kind": "EnumConstantDecl", "name": key, "id": key,
                           "inner": [{"kind": "ConstantExpr", "id": key + "-expr",
                                      "type": {"qualType": "bool" if key in BOOL_FIELDS else "int"},
                                      "value": "true" if key in BOOL_FIELDS else str(i)}]}
                          for i, key in enumerate(sorted(FIELDS))]}]}

    def test_records_values_without_asserting_expected_abi(self):
        source = self.fixture()
        before = copy.deepcopy(source)
        result = observations(source)
        self.assertEqual(set(result), FIELDS)
        self.assertEqual(source, before)
        self.assertEqual(result["int_bits"]["value"], 0)
        expression = source["ast_roots"][0]["inner"][0]["inner"][0]
        expression.update(type={"qualType": "bool"}, value="true")
        with self.assertRaises(ValueError): observations(source)
        self.assertIs(result["underlying_is_unsigned"]["value"], True)

    def test_missing_duplicate_or_failed_collection_refused(self):
        for mutation in ("failed", "missing", "duplicate", "two_functions"):
            source = self.fixture()
            if mutation == "failed": source["status"] = "compile_failed"
            elif mutation == "missing": source["ast_roots"][0]["inner"].pop()
            elif mutation == "duplicate": source["ast_roots"][0]["inner"].append(copy.deepcopy(source["ast_roots"][0]["inner"][0]))
            else: source["ast_roots"] *= 2
            with self.assertRaises(ValueError): observations(source)

    def test_ambiguous_or_noninteger_constant_refused(self):
        for value in ("garbage", None):
            source = self.fixture()
            source["ast_roots"][0]["inner"][0]["inner"][0]["value"] = value
            with self.assertRaises(ValueError): observations(source)
        source = self.fixture()
        source["ast_roots"][0]["inner"][0]["inner"] *= 2
        with self.assertRaises(ValueError): observations(source)

    def test_trace_failure_cannot_be_reported_as_observed(self):
        source = self.fixture()
        source["toolchain_trace"] = {"status": "unknown"}
        with tempfile.TemporaryDirectory() as directory, patch("experiments.hip_api_abi_probe.collect", return_value=source):
            report = run("fixture-compiler", directory, Path(directory) / "report.json")
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(report["reason"], "toolchain_trace_not_observed")
        self.assertFalse(report["GPU_executed"])
        self.assertFalse(report["original_kernel_TU_ABI_binding"])

    def test_device_context_recipe_and_dependency_binding(self):
        context = (Path(__file__).parent / "fixtures/field_snapshot.cpp").resolve()
        source = self.fixture()
        source["toolchain_trace"] = {"status": "observed"}
        source["dependency_binding"] = {"files": [{"resolved_path": str(context),
            "sha256": hashlib.sha256(context.read_bytes()).hexdigest()}]}
        with tempfile.TemporaryDirectory() as directory, patch("experiments.hip_api_abi_probe.collect", return_value=source) as collect:
            report = run("fixture-compiler", directory, Path(directory) / "report.json", hip_context_source=context)
        args = collect.call_args.args[2]
        self.assertIn("--offload-device-only", args)
        self.assertEqual(args[args.index("-include") + 1], str(context))
        self.assertEqual(report["mode"], "augmented_hip_device_context")
        self.assertEqual(report["status"], "observed")
        self.assertFalse(report["original_kernel_TU_ABI_binding"])

    def test_missing_or_wrong_context_dependency_stays_unknown(self):
        context = Path(__file__).resolve()
        for entries in ([], [{"resolved_path": str(context), "sha256": "wrong"}]):
            source = self.fixture()
            source["toolchain_trace"] = {"status": "observed"}
            source["dependency_binding"] = {"files": entries}
            with tempfile.TemporaryDirectory() as directory, patch("experiments.hip_api_abi_probe.collect", return_value=source):
                report = run("fixture-compiler", directory, Path(directory) / "report.json", hip_context_source=context)
            self.assertEqual(report["status"], "unknown")
            self.assertEqual(report["reason"], "context_source_dependency_binding_missing")
