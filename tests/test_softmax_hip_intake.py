"""Binding-unit tests for the executed HIP pilot intake manifest."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from experiments.pytorch_softmax_intake import sha
from experiments.softmax_hip_intake import verify_pilot


class SoftmaxHipIntakeTests(unittest.TestCase):
    def fixture(self, directory):
        directory = Path(directory)
        source_input = directory / "frozen-protocol.json"
        adapted_source = directory / "pytorch-softmax-hip.hip.cpp"
        adapted_header = directory / "PersistentSoftmax.hip.cuh"
        binary = directory / "softmax-hip"
        compiler = directory / "hipcc"
        sdk_input = directory / "libamdhip64.so.7"
        files = {
            source_input: b"frozen protocol bytes\n",
            adapted_source: b"adapted source bytes\n",
            adapted_header: b"adapted header bytes\n",
            binary: b"linked binary bytes\n",
            compiler: b"compiler wrapper bytes\n",
            sdk_input: b"observed SDK bytes\n",
        }
        for path, contents in files.items():
            path.write_bytes(contents)
        report = {
            "status": "finite_numeric_cases_passed",
            "cases": [{"case": index} for index in range(18)],
            "inputs_unchanged": True,
            "adapted_inputs_unchanged": True,
            "binary_unchanged": True,
            "input_hashes": {str(source_input): sha(source_input)},
            "adapted_input_hashes": {
                adapted_source.name: sha(adapted_source),
                adapted_header.name: sha(adapted_header),
            },
            "binary_sha256": sha(binary),
            "compiler_wrapper_sha256": sha(compiler),
            "compile": {"command": [str(compiler), "-std=c++17"]},
            "sdk_view_observation": {"inputs": [{
                "path": str(sdk_input),
                "observed_sha256": sha(sdk_input),
            }]},
        }
        paths = {"input": source_input, "adapted": adapted_source, "binary": binary,
                 "compiler": compiler, "sdk": sdk_input}
        return report, paths

    def test_complete_stable_manifest_returns_bound_compiler(self):
        with tempfile.TemporaryDirectory(prefix="wb-softmax-intake-") as temporary:
            report, paths = self.fixture(temporary)
            self.assertEqual(verify_pilot(report, Path(temporary)), paths["compiler"])

    def test_each_bound_file_change_is_rejected(self):
        for target in ("input", "adapted", "binary", "compiler", "sdk"):
            with self.subTest(target=target), tempfile.TemporaryDirectory(
                    prefix="wb-softmax-intake-") as temporary:
                report, paths = self.fixture(temporary)
                paths[target].write_bytes(paths[target].read_bytes() + b"changed")
                with self.assertRaises(ValueError):
                    verify_pilot(report, Path(temporary))

    def test_incomplete_or_unstable_reports_are_rejected(self):
        mutations = {
            "status": lambda report: report.update(status="runtime_failed"),
            "case_count": lambda report: report["cases"].pop(),
            "inputs": lambda report: report.update(inputs_unchanged=False),
            "adapted": lambda report: report.update(adapted_inputs_unchanged=False),
            "binary": lambda report: report.update(binary_unchanged=False),
        }
        with tempfile.TemporaryDirectory(prefix="wb-softmax-intake-") as temporary:
            baseline, _ = self.fixture(temporary)
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    report = deepcopy(baseline)
                    mutate(report)
                    with self.assertRaises(ValueError):
                        verify_pilot(report, Path(temporary))


if __name__ == "__main__":
    unittest.main()
