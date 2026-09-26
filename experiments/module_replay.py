#!/usr/bin/env python3
"""Replay one pinned logical32 code object through the HIP module API.

This is deliberately not a general module runner.  It accepts only the saved
3x777 W7900 baseline artifacts listed below, records every HIP return code, and
never turns a finite numeric pass into a static or deployability conclusion.
"""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import sys


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "benchmarks/cases/llama-rmsnorm/reference.py"
REPOSITORY_PROTOCOL = ROOT / "benchmarks/cases/llama-rmsnorm/protocol.json"
DEFAULT_RUNTIME = Path(
    "/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/libamdhip64.so.7"
)

PINNED_SHA256 = {
    "code_object": "b5c8b8abaf3972c79b7008a50116d83d7a4d1a4ae53dbe8f76b5e397ac4c9977",
    "input.f32": "3ea02eace646a0e9d8301fb3f51945f1a3104e35407e0a1ca6e5830af8cb091c",
    "expected.f32": "ff840c560d5e2eef94479ae62eabc25015a3b9611d7d4cf917e1c4095788d196",
    "protocol.json": "f8706a25e68b2354cc839c5d9a08aee7e0abf1fded236bcdfe1f3d577808dcae",
    "reference.py": "a2d2c860d1c9fffd37a24c1e08765afb1d19851825f47b1131da321d11eafb75",
}

NROWS = 3
NCOLS = 777
COUNT = NROWS * NCOLS
EPSILON = 1.0e-5
EPSILON_F32 = ctypes.c_float(EPSILON).value
EPSILON_F32_BITS = struct.unpack("<I", struct.pack("<f", EPSILON_F32))[0]
GRID = (3, 1, 1)
BLOCK = (256, 1, 1)
SHARED_BYTES = 128
SYMBOL = "_Z22rms_norm_f32_logical32PKfPfif"
EXPECTED_DEVICE_NAME = "AMD Radeon Pro W7900"
EXPECTED_PCI_BUS_ID = "0000:53:00.0"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ValidationError(ValueError):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail or reason


class HipCallError(RuntimeError):
    def __init__(self, api: str, code: int, detail: str):
        super().__init__(f"{api} returned {code}: {detail}")
        self.api = api
        self.code = code
        self.detail = detail


def _strict_json(path: Path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"non-finite JSON value: {value}")

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=nonfinite)


def _load_reference():
    spec = importlib.util.spec_from_file_location("wavebridge_module_replay_reference", REFERENCE)
    if spec is None or spec.loader is None:
        raise ValidationError("reference_import_failed", "reference module has no loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_inputs(code_object: Path, baseline_dir: Path,
                    runtime: Path = DEFAULT_RUNTIME) -> dict:
    """Validate every pinned byte input without loading HIP or calling a GPU API."""
    try:
        code_object = Path(code_object).resolve(strict=True)
        baseline_dir = Path(baseline_dir).resolve(strict=True)
        runtime = Path(runtime).resolve(strict=True)
    except OSError as error:
        raise ValidationError("required_input_missing", str(error)) from error
    if not code_object.is_file() or not baseline_dir.is_dir() or not runtime.is_file():
        raise ValidationError("required_input_not_regular_file_or_directory")
    if os.environ.get("HIP_VISIBLE_DEVICES") != "0":
        raise ValidationError("hip_visible_devices_must_be_exactly_zero")

    paths = {
        "code_object": code_object,
        "input.f32": baseline_dir / "input.f32",
        "expected.f32": baseline_dir / "expected.f32",
        "protocol.json": baseline_dir / "protocol.json",
        "reference.py": baseline_dir / "reference.py",
    }
    raw_inputs = {}
    for name, path in paths.items():
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise ValidationError("pinned_input_unreadable", f"{name}: {error}") from error
        digest = hashlib.sha256(raw).hexdigest()
        if digest != PINNED_SHA256[name]:
            raise ValidationError("pinned_input_hash_mismatch", name)
        raw_inputs[name] = raw

    # The comparator is imported only from the repository path, never from the
    # baseline directory.  Both its bytes and the protocol it imports are pinned.
    if _sha(REFERENCE) != PINNED_SHA256["reference.py"]:
        raise ValidationError("repository_reference_hash_mismatch")
    if _sha(REPOSITORY_PROTOCOL) != PINNED_SHA256["protocol.json"]:
        raise ValidationError("repository_protocol_hash_mismatch")
    if raw_inputs["reference.py"] != REFERENCE.read_bytes():
        raise ValidationError("baseline_reference_not_repository_reference")
    if raw_inputs["protocol.json"] != REPOSITORY_PROTOCOL.read_bytes():
        raise ValidationError("baseline_protocol_not_repository_protocol")
    try:
        protocol = _strict_json(paths["protocol.json"])
        reference = _load_reference()
    except (OSError, UnicodeError, ValueError) as error:
        raise ValidationError("reference_or_protocol_load_failed", str(error)) from error

    input_bytes = raw_inputs["input.f32"]
    expected_bytes = raw_inputs["expected.f32"]
    if len(input_bytes) != COUNT * 4 or len(expected_bytes) != COUNT * 4:
        raise ValidationError("pinned_array_size_mismatch")
    inputs = struct.unpack(f"<{COUNT}f", input_bytes)
    expected = struct.unpack(f"<{COUNT}f", expected_bytes)
    if not all(math.isfinite(value) for value in (*inputs, *expected)):
        raise ValidationError("pinned_array_contains_nonfinite")
    if protocol != reference.PROTOCOL:
        raise ValidationError("repository_reference_protocol_mismatch")

    return {
        "paths": {name: str(path) for name, path in paths.items()},
        "sha256": {name: PINNED_SHA256[name] for name in paths},
        "runtime": {"path": str(runtime), "sha256": _sha(runtime)},
        "shape": [NROWS, NCOLS],
        "code_object_bytes": raw_inputs["code_object"],
        "input_bytes": input_bytes,
        "expected_values": expected,
        "reference": reference,
    }


class HipRuntime:
    """Narrow ctypes binding for the HIP calls used by this replay only."""

    HIP_MEMCPY_HOST_TO_DEVICE = 1
    HIP_MEMCPY_DEVICE_TO_HOST = 2

    def __init__(self, path: Path):
        self.path = Path(path)
        self.library = ctypes.CDLL(str(self.path))
        self.calls = []
        self._configure()

    def _configure(self):
        c_void_pp = ctypes.POINTER(ctypes.c_void_p)
        signatures = {
            "hipInit": ([ctypes.c_uint], ctypes.c_int),
            "hipSetDevice": ([ctypes.c_int], ctypes.c_int),
            "hipDeviceGet": ([ctypes.POINTER(ctypes.c_int), ctypes.c_int], ctypes.c_int),
            "hipDeviceGetName": ([ctypes.c_char_p, ctypes.c_int, ctypes.c_int], ctypes.c_int),
            "hipDeviceGetPCIBusId": ([ctypes.c_char_p, ctypes.c_int, ctypes.c_int], ctypes.c_int),
            "hipRuntimeGetVersion": ([ctypes.POINTER(ctypes.c_int)], ctypes.c_int),
            "hipDriverGetVersion": ([ctypes.POINTER(ctypes.c_int)], ctypes.c_int),
            "hipMalloc": ([c_void_pp, ctypes.c_size_t], ctypes.c_int),
            "hipFree": ([ctypes.c_void_p], ctypes.c_int),
            "hipMemcpy": ([ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int],
                           ctypes.c_int),
            "hipModuleLoadData": ([c_void_pp, ctypes.c_void_p], ctypes.c_int),
            "hipModuleGetFunction": ([c_void_pp, ctypes.c_void_p, ctypes.c_char_p], ctypes.c_int),
            "hipModuleLaunchKernel": ([ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                                       ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                                       ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
                                       c_void_pp, c_void_pp], ctypes.c_int),
            "hipDeviceSynchronize": ([], ctypes.c_int),
            "hipModuleUnload": ([ctypes.c_void_p], ctypes.c_int),
            "hipGetErrorString": ([ctypes.c_int], ctypes.c_char_p),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.library, name)
            function.argtypes = arguments
            function.restype = result

    def _error_string(self, code):
        value = self.library.hipGetErrorString(code)
        return value.decode(errors="replace") if value else "unknown HIP error"

    def _call(self, name, *args, recorded_arguments=None):
        code = int(getattr(self.library, name)(*args))
        item = {"api": name, "return_code": code}
        if recorded_arguments is not None:
            item["arguments"] = recorded_arguments
        self.calls.append(item)
        if code != 0:
            raise HipCallError(name, code, self._error_string(code))

    def initialize(self):
        self._call("hipInit", 0, recorded_arguments={"flags": 0})
        self._call("hipSetDevice", 0, recorded_arguments={"ordinal": 0})
        runtime = ctypes.c_int()
        driver = ctypes.c_int()
        self._call("hipRuntimeGetVersion", ctypes.byref(runtime))
        self._call("hipDriverGetVersion", ctypes.byref(driver))
        return {"runtime_version": runtime.value, "driver_version": driver.value}

    def device_identity(self, ordinal):
        device = ctypes.c_int()
        self._call("hipDeviceGet", ctypes.byref(device), ordinal,
                   recorded_arguments={"ordinal": ordinal})
        name = ctypes.create_string_buffer(256)
        pci = ctypes.create_string_buffer(64)
        self._call("hipDeviceGetName", name, len(name), device.value,
                   recorded_arguments={"ordinal": ordinal, "buffer_size": len(name)})
        self._call("hipDeviceGetPCIBusId", pci, len(pci), ordinal,
                   recorded_arguments={"ordinal": ordinal, "buffer_size": len(pci)})
        return {"ordinal": ordinal, "name": name.value.decode(errors="replace"),
                "pci_bus_id": pci.value.decode(errors="replace")}

    def malloc(self, size):
        pointer = ctypes.c_void_p()
        self._call("hipMalloc", ctypes.byref(pointer), size,
                   recorded_arguments={"size": size})
        return pointer

    def memcpy_h2d(self, destination, data):
        source = ctypes.create_string_buffer(data, len(data))
        self._call("hipMemcpy", destination, ctypes.cast(source, ctypes.c_void_p), len(data),
                   self.HIP_MEMCPY_HOST_TO_DEVICE,
                   recorded_arguments={"direction": "host_to_device", "size": len(data)})

    def memcpy_d2h(self, source, size):
        destination = ctypes.create_string_buffer(size)
        self._call("hipMemcpy", ctypes.cast(destination, ctypes.c_void_p), source, size,
                   self.HIP_MEMCPY_DEVICE_TO_HOST,
                   recorded_arguments={"direction": "device_to_host", "size": size})
        return destination.raw

    def module_load(self, image):
        module = ctypes.c_void_p()
        storage = ctypes.create_string_buffer(image, len(image))
        self._call("hipModuleLoadData", ctypes.byref(module), ctypes.cast(storage, ctypes.c_void_p),
                   recorded_arguments={"image_size": len(image),
                                       "image_sha256": hashlib.sha256(image).hexdigest()})
        return module

    def module_get_function(self, module, symbol):
        function = ctypes.c_void_p()
        self._call("hipModuleGetFunction", ctypes.byref(function), module, symbol.encode(),
                   recorded_arguments={"symbol": symbol})
        return function

    def module_launch(self, function, grid, block, shared_bytes, arguments):
        input_pointer, output_pointer, ncols, epsilon = arguments
        input_arg = ctypes.c_void_p(input_pointer.value)
        output_arg = ctypes.c_void_p(output_pointer.value)
        ncols_arg = ctypes.c_int(ncols)
        epsilon_arg = ctypes.c_float(epsilon)
        parameter_values = (ctypes.c_void_p * 4)(
            ctypes.cast(ctypes.byref(input_arg), ctypes.c_void_p),
            ctypes.cast(ctypes.byref(output_arg), ctypes.c_void_p),
            ctypes.cast(ctypes.byref(ncols_arg), ctypes.c_void_p),
            ctypes.cast(ctypes.byref(epsilon_arg), ctypes.c_void_p),
        )
        self._call(
            "hipModuleLaunchKernel", function, *grid, *block, shared_bytes, None,
            parameter_values, None,
            recorded_arguments={"grid": list(grid), "block": list(block),
                                "shared_bytes": shared_bytes,
                                "arguments": ["device_input_pointer", "device_output_pointer",
                                              {"ncols": ncols}, {"epsilon_f32": epsilon_arg.value}]},
        )

    def synchronize(self):
        self._call("hipDeviceSynchronize")

    def free(self, pointer):
        self._call("hipFree", pointer)

    def module_unload(self, module):
        self._call("hipModuleUnload", module)


def _public_validation(validation):
    return {key: value for key, value in validation.items()
            if key not in {"code_object_bytes", "input_bytes", "expected_values", "reference"}}


def run(code_object: Path, baseline_dir: Path, output_dir: Path,
        runtime: Path = DEFAULT_RUNTIME, *, runtime_factory=HipRuntime) -> tuple[int, Path]:
    """Validate pins, then perform exactly one explicit module replay."""
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    report_path = output_dir / "report.json"
    report = {
        "schema_version": "logical32-module-replay/v1", "status": "not_started",
        "script_sha256": _sha(Path(__file__)),
        "command": list(sys.argv),
        "command_sha256": hashlib.sha256(json.dumps(
            list(sys.argv), separators=(",", ":"), ensure_ascii=False).encode()).hexdigest(),
        "scope": "pinned_saved_logical32_code_object_module_api_replay",
        "symbol": SYMBOL, "launch": {"grid": list(GRID), "block": list(BLOCK),
                                      "dynamic_shared_bytes": SHARED_BYTES,
                                      "ncols": NCOLS,
                                      "epsilon_f32": {"value": EPSILON_F32,
                                                      "bits_hex": f"0x{EPSILON_F32_BITS:08x}"}},
        "metadata": {"target": "gfx1100", "wavefront_size": 32,
                     "source": "pinned_prior_saved_binary_observation",
                     "independently_parsed_in_this_replay": False},
        "runtime_wave_independently_measured": False,
        "input_validation": None, "runtime": None, "device": None,
        "api_calls": [], "cleanup_errors": [], "comparison": None,
        "GPU_executed": False,
        "source_program_checked": False, "actual_fp_laws_verified": False,
        "numeric_contract_checked": False, "deployable": False,
        "limitations": ["only the pinned finite 3x777 input is replayed",
                        "module selection and API success do not prove source equivalence",
                        "wavefront size is recorded metadata, not independently measured here",
                        "a numeric pass does not establish the conditional FP premises domain-wide"],
        "visible_device_environment": {key: os.environ.get(key) for key in
                                       ("HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES",
                                        "CUDA_VISIBLE_DEVICES")},
    }

    def finish(status, code, **extra):
        report.update(status=status, **extra)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True,
                                          allow_nan=False) + "\n")
        return code, report_path

    try:
        validation = validate_inputs(code_object, baseline_dir, runtime)
        report["input_validation"] = {"status": "validated", **_public_validation(validation)}
    except (OSError, UnicodeError, ValueError) as error:
        reason = error.reason if isinstance(error, ValidationError) else "input_validation_failed"
        return finish("invalid_inputs", 2,
                      input_validation={"status": "rejected", "reason": reason,
                                        "detail": str(error)})

    api = None
    module = input_device = output_device = None
    primary_failure = None
    try:
        runtime_path = Path(validation["runtime"]["path"])
        if _sha(runtime_path) != validation["runtime"]["sha256"]:
            raise ValidationError("runtime_changed_before_load")
        api = runtime_factory(runtime_path)
        report["runtime"] = {**validation["runtime"], **api.initialize()}
        identity = api.device_identity(0)
        report["device"] = identity
        if (not isinstance(identity.get("name"), str) or
                identity["name"].casefold() != EXPECTED_DEVICE_NAME.casefold() or
                not isinstance(identity.get("pci_bus_id"), str) or
                identity["pci_bus_id"].lower() != EXPECTED_PCI_BUS_ID.lower()):
            raise ValidationError("device_identity_mismatch", json.dumps(identity, sort_keys=True))

        input_device = api.malloc(len(validation["input_bytes"]))
        output_device = api.malloc(COUNT * 4)
        api.memcpy_h2d(input_device, validation["input_bytes"])
        # Make a missing/partial kernel write fail comparison instead of inheriting
        # allocator contents that happen to match expected output.
        nan_bytes = struct.pack("<I", 0x7FC00000) * COUNT
        api.memcpy_h2d(output_device, nan_bytes)
        module = api.module_load(validation["code_object_bytes"])
        function = api.module_get_function(module, SYMBOL)
        api.module_launch(function, GRID, BLOCK, SHARED_BYTES,
                          (input_device, output_device, NCOLS, EPSILON_F32))
        api.synchronize()
        report["GPU_executed"] = True
        output_bytes = api.memcpy_d2h(output_device, COUNT * 4)
        if len(output_bytes) != COUNT * 4:
            raise ValidationError("runtime_output_size_mismatch")
        output_path = output_dir / "output.f32"
        output_path.write_bytes(output_bytes)
        actual = struct.unpack(f"<{COUNT}f", output_bytes)
        comparison = validation["reference"].compare(actual, validation["expected_values"])
        report["output"] = {"path": str(output_path), "sha256": _sha(output_path),
                            "size": len(output_bytes)}
        report["comparison"] = comparison
        report["finite_input_numeric_pass"] = comparison.get("passed") is True
        report["status"] = "passed" if comparison.get("passed") is True else "numeric_mismatch"
    except HipCallError as error:
        primary_failure = {"reason": "hip_api_failed", "api": error.api,
                           "return_code": error.code, "detail": error.detail}
        report["status"] = "runtime_failed"
    except (OSError, UnicodeError, ValueError, struct.error) as error:
        reason = error.reason if isinstance(error, ValidationError) else "runtime_processing_failed"
        primary_failure = {"reason": reason, "detail": str(error)}
        report["status"] = "runtime_failed"
    except Exception as error:  # injected/runtime boundary must still yield a report
        primary_failure = {"reason": "unexpected_runtime_failure", "detail": str(error),
                           "exception_type": type(error).__name__}
        report["status"] = "runtime_failed"
    finally:
        if api is not None:
            for name, value, cleanup in (
                    ("device_input", input_device, api.free),
                    ("device_output", output_device, api.free),
                    ("module", module, api.module_unload)):
                if value is None:
                    continue
                try:
                    cleanup(value)
                except HipCallError as error:
                    report["cleanup_errors"].append({"resource": name, "api": error.api,
                                                     "return_code": error.code,
                                                     "detail": error.detail})
                except Exception as error:  # mock/runtime boundary must still be reported
                    report["cleanup_errors"].append({"resource": name,
                                                     "api": getattr(cleanup, "__name__", "cleanup"),
                                                     "return_code": None, "detail": str(error)})
            report["api_calls"] = list(getattr(api, "calls", []))

    if primary_failure is not None:
        report["failure"] = primary_failure
    if report["cleanup_errors"]:
        if primary_failure is not None:
            report["failure_before_cleanup"] = primary_failure
        return finish("cleanup_failed", 2)
    return finish(report["status"], 0 if report["status"] == "passed" else 2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-object", required=True, type=Path)
    parser.add_argument("--baseline-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    args = parser.parse_args(argv)
    try:
        code, report = run(args.code_object, args.baseline_dir, args.output_dir, args.runtime)
    except (OSError, ValueError) as error:
        parser.exit(3, str(error) + "\n")
    print(json.dumps({"exit_code": code, "report": str(report)}))
    return code


if __name__ == "__main__":
    sys.exit(main())
