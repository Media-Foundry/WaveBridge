"""CPU-only boundary checks; mocked calls are not GPU evidence."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

from experiments import module_replay as replay


class FakeHip:
    """No CDLL or device access: records the high-level execution ordering."""
    def __init__(self, runtime, *, output=b"", wrong_device=False, fail=None):
        self.calls = []
        self.output = output
        self.wrong_device = wrong_device
        self.fail = fail
        self.allocations = 0

    def record(self, name):
        self.calls.append({"api": name, "returncode": 0})
        if self.fail == name:
            raise replay.HipCallError(name, 99, "injected failure")

    def initialize(self):
        self.record("initialize")
        return {"runtime_version": 1, "driver_version": 1}

    def device_identity(self, ordinal):
        self.record("device_identity")
        return {"name": "wrong GPU" if self.wrong_device else "AMD Radeon Pro W7900",
                "pci_bus_id": "0000:53:00.0"}

    def malloc(self, size):
        self.record("malloc")
        self.allocations += 1
        return self.allocations

    def memcpy_h2d(self, handle, data):
        self.record("memcpy_h2d")

    def module_load(self, data):
        self.record("module_load")
        self.loaded = data
        return 3

    def module_get_function(self, module, symbol):
        self.record("module_get_function")
        self.symbol = symbol
        return 4

    def module_launch(self, function, grid, block, shared_bytes, arguments):
        self.record("module_launch")
        self.launch = (grid, block, shared_bytes, arguments)

    def synchronize(self):
        self.record("synchronize")

    def memcpy_d2h(self, handle, size):
        self.record("memcpy_d2h")
        return self.output

    def free(self, handle):
        self.record("free")

    def module_unload(self, handle):
        self.record("module_unload")


class ModuleReplayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.baseline = self.root / "baseline"
        self.baseline.mkdir()
        self.code = self.root / "device.co"
        self.code.write_bytes(b"not an accepted GPU object")
        self.runtime = self.root / "mock-runtime.so"
        self.runtime.write_bytes(b"never loaded")
        env = patch.dict(os.environ, {"HIP_VISIBLE_DEVICES": "0"})
        env.start()
        self.addCleanup(env.stop)

    def fixture(self):
        raw = struct.pack("<f", 0.0) * replay.COUNT
        for name, content in (("input.f32", raw), ("expected.f32", raw),
                              ("reference.py", replay.REFERENCE.read_bytes()),
                              ("protocol.json", replay.REPOSITORY_PROTOCOL.read_bytes())):
            (self.baseline / name).write_bytes(content)
        pins = dict(replay.PINNED_SHA256)
        pins["code_object"] = hashlib.sha256(self.code.read_bytes()).hexdigest()
        pins["input.f32"] = pins["expected.f32"] = hashlib.sha256(raw).hexdigest()
        patched = patch.dict(replay.PINNED_SHA256, pins)
        patched.start()
        self.addCleanup(patched.stop)
        return raw

    def execute(self, api):
        code, path = replay.run(self.code, self.baseline, self.root / "run",
                                self.runtime, runtime_factory=lambda _: api)
        return code, json.loads(path.read_text())

    def test_unaccepted_code_never_loads_runtime(self):
        factory = Mock()
        code, path = replay.run(self.code, self.baseline, self.root / "run",
                                self.runtime, runtime_factory=factory)
        self.assertNotEqual(code, 0)
        factory.assert_not_called()

    def test_mocked_pass_records_fixed_launch_not_proof(self):
        raw = self.fixture()
        api = FakeHip(self.runtime, output=raw)
        code, report = self.execute(api)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(api.loaded, self.code.read_bytes())
        self.assertEqual(api.symbol, replay.SYMBOL)
        self.assertEqual(api.launch[:3], ((3, 1, 1), (256, 1, 1), 128))
        self.assertEqual(api.launch[3][2:], (777, ctypes.c_float(1.0e-5).value))
        for flag in ("deployable", "source_program_checked", "actual_fp_laws_verified",
                     "numeric_contract_checked", "runtime_wave_independently_measured"):
            self.assertFalse(report[flag])
        self.assertEqual([x["api"] for x in api.calls][-3:],
                         ["free", "free", "module_unload"])

    def test_wrong_device_prevents_allocation_or_module_load(self):
        self.fixture()
        api = FakeHip(self.runtime, wrong_device=True)
        code, report = self.execute(api)
        self.assertNotEqual(code, 0)
        self.assertEqual(report["failure"]["reason"], "device_identity_mismatch")
        self.assertEqual([x["api"] for x in api.calls], ["initialize", "device_identity"])

    def test_nonfinite_output_is_numeric_failure(self):
        self.fixture()
        api = FakeHip(self.runtime, output=struct.pack("<f", float("nan")) * replay.COUNT)
        code, report = self.execute(api)
        self.assertNotEqual(code, 0)
        self.assertEqual(report["status"], "numeric_mismatch")
        self.assertFalse(report["finite_input_numeric_pass"])

    def test_launch_failure_preserves_error_and_cleans_resources(self):
        self.fixture()
        api = FakeHip(self.runtime, fail="module_launch")
        code, report = self.execute(api)
        self.assertNotEqual(code, 0)
        self.assertEqual(report["failure"]["api"], "module_launch")
        self.assertEqual([x["api"] for x in api.calls][-3:],
                         ["free", "free", "module_unload"])

    def test_cleanup_failure_cannot_be_success(self):
        raw = self.fixture()
        api = FakeHip(self.runtime, output=raw, fail="free")
        code, report = self.execute(api)
        self.assertNotEqual(code, 0)
        self.assertEqual(report["status"], "cleanup_failed")
        self.assertEqual(len(report["cleanup_errors"]), 2)
        self.assertTrue(report["comparison"]["passed"])

    def test_pinned_code_bytes_survive_path_mutation_before_runtime(self):
        raw = self.fixture()
        original = self.code.read_bytes()
        api = FakeHip(self.runtime, output=raw)

        def factory(_):
            self.code.write_bytes(b"different code after validation")
            return api

        code, path = replay.run(self.code, self.baseline, self.root / "run",
                                self.runtime, runtime_factory=factory)
        self.assertEqual(code, 0)
        self.assertEqual(api.loaded, original)
        report = json.loads(path.read_text())
        self.assertFalse(report["deployable"])
        self.assertFalse(report["source_program_checked"])
        self.assertFalse(report["actual_fp_laws_verified"])

    def test_missing_input_never_loads_runtime(self):
        factory = Mock()
        code, path = replay.run(self.root / "missing", self.baseline,
                                self.root / "run", self.runtime,
                                runtime_factory=factory)
        self.assertNotEqual(code, 0)
        self.assertTrue(path.is_file())
        factory.assert_not_called()

    def test_ctypes_launch_passes_addresses_with_exact_abi_values(self):
        api = object.__new__(replay.HipRuntime)

        def inspect(name, *args, recorded_arguments=None):
            self.assertEqual(name, "hipModuleLaunchKernel")
            self.assertEqual(args[1:9], (3, 1, 1, 256, 1, 1, 128, None))
            params = args[9]
            self.assertEqual(ctypes.cast(params[0], ctypes.POINTER(ctypes.c_void_p))[0], 1234)
            self.assertEqual(ctypes.cast(params[1], ctypes.POINTER(ctypes.c_void_p))[0], 5678)
            self.assertEqual(ctypes.cast(params[2], ctypes.POINTER(ctypes.c_int))[0], 777)
            epsilon = ctypes.cast(params[3], ctypes.POINTER(ctypes.c_float))[0]
            self.assertEqual(struct.pack("<f", epsilon).hex(), "acc52737")
            self.assertIsNone(args[10])

        api._call = Mock(side_effect=inspect)
        api.module_launch(ctypes.c_void_p(1), replay.GRID, replay.BLOCK, 128,
                          (ctypes.c_void_p(1234), ctypes.c_void_p(5678), 777, 1.0e-5))
        api._call.assert_called_once()

    def test_ctypes_module_load_submits_exact_buffer(self):
        api = object.__new__(replay.HipRuntime)
        raw = b"test\x00binary\xffbytes"

        def inspect(name, *args, recorded_arguments=None):
            self.assertEqual(name, "hipModuleLoadData")
            self.assertEqual(ctypes.string_at(args[1], len(raw)), raw)
            self.assertEqual(recorded_arguments["image_sha256"], hashlib.sha256(raw).hexdigest())

        api._call = Mock(side_effect=inspect)
        api.module_load(raw)
        api._call.assert_called_once()


if __name__ == "__main__":
    unittest.main()
