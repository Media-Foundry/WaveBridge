"""Parser fixtures only; real SDK ABI evidence is collected separately."""
import copy
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
