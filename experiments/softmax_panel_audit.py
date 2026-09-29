"""Recheck a pinned historical HIP panel without launching a GPU or proving AST semantics."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

from experiments import softmax_hip_reference as reference
from experiments import softmax_hip_pilot as pilot
from experiments.softmax_hip_pilot import validate_protocol


def digest(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("nonstandard_json_constant")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def audit_panel(report):
    """Validate recorded observations, never accept saved numeric pass flags."""
    if (report.get("schema_version") != "softmax-manual-hip-pilot/v1" or
            report.get("status") != "finite_numeric_cases_passed" or
            any(report.get(k) is not True for k in
                ("GPU_executed", "inputs_unchanged", "adapted_inputs_unchanged", "binary_unchanged"))):
        raise ValueError("recorded_panel_not_complete")
    protocol = report["protocol"]
    validate_protocol(protocol)
    # Python bool/int equality must not let malformed protocol types pass.
    panel = protocol["cases"]
    if any(type(v) is not int for k in ("rows", "columns") for v in panel[k]):
        raise ValueError("panel_dimension_type_mismatch")
    expected = set(itertools.product(panel["rows"], panel["columns"], panel["patterns"]))
    seen, commands, widths, libraries = set(), set(), set(), set()
    fresh_checks = []
    for case in report["cases"]:
        if type(case.get("rows")) is not int or type(case.get("columns")) is not int:
            raise ValueError("case_dimension_type_mismatch")
        key = case["rows"], case["columns"], case["pattern"]
        if key not in expected or key in seen:
            raise ValueError("unexpected_or_duplicate_case")
        seen.add(key)
        execution = case["execution"]
        command = execution.get("command")
        if (execution.get("status") != "completed" or type(execution.get("returncode")) is not int or
                execution["returncode"] != 0 or not isinstance(command, list) or len(command) != 4 or
                not isinstance(command[0], str) or not command[0] or
                command[1:] != [str(key[0]), str(key[1]), key[2]]):
            raise ValueError("recorded_command_mismatch")
        commands.add(command[0])
        observed = strict_json(execution["stdout"])
        if observed != case["observed"]:
            raise ValueError("stdout_and_saved_observation_mismatch")
        values = {"rows": key[0], "columns": key[1], "api_width": 32, "device_width": 32,
                  "api_calls": 1, "softmax_dispatch_launch_count": 1,
                  "padded_rows": ((key[0] + 7) // 8) * 8, "grid": (key[0] + 7) // 8}
        if (any(type(observed.get(k)) is not int or observed[k] != v for k, v in values.items()) or
                observed.get("block") != [32, 4, 1] or
                any(type(v) is not int for v in observed["block"]) or
                observed.get("padding_sentinel_preserved") is not True):
            raise ValueError("recorded_launch_observation_mismatch")
        fresh = reference.evaluate(observed["output"], reference.reference(
            reference.make_input(*key), key[0], key[1]), key[0], key[1])
        if fresh["status"] != "passed":
            raise ValueError("fresh_numeric_check_failed")
        fresh_checks.append({"rows": key[0], "columns": key[1], "pattern": key[2],
                             "numeric_check": fresh,
                             "stdout_sha256": digest(execution["stdout"].encode())})
        widths.add(observed["api_width"])
        library = case["loaded_hip_api_library"]
        libraries.add((library["path"], library["sha256"]))
    if seen != expected or len(commands) != 1 or len(libraries) != 1:
        raise ValueError("incomplete_or_mixed_panel")
    return {"status": "recorded_panel_rechecked", "case_count": len(seen),
            "fresh_numeric_checks": fresh_checks,
            "observed_columns": sorted({k[1] for k in seen}), "observed_rows": sorted({k[0] for k in seen}),
            "observed_api_widths": sorted(widths), "recorded_executable": next(iter(commands)),
            "recorded_api_library": list(next(iter(libraries))),
            "continuous_interval_gpu_tested": False, "host_parameter_domain_proved": False,
            "API_semantics_proved": False, "GPU_executed_by_audit": False,
            "source_program_checked": False, "deployable": False}


def run(path, expected_sha256, output):
    data = path.read_bytes()
    if digest(data) != expected_sha256:
        raise ValueError("pinned_report_hash_mismatch")
    report = strict_json(data)
    result = audit_panel(report)
    files = dict(report["adapted_input_hashes"])
    files["softmax-hip"] = report["binary_sha256"]
    if not {"PersistentSoftmax.hip.cuh", "wavebridge_softmax_compat.h",
            "pytorch-softmax-hip.hip.cpp"} <= files.keys():
        raise ValueError("required_adapted_source_identity_missing")
    for name, expected in files.items():
        if Path(name).name != name or name in (".", ".."):
            raise ValueError("artifact_name_not_local")
        if digest((path.parent / name).read_bytes()) != expected:
            raise ValueError("current_artifact_hash_mismatch")
    if Path(result["recorded_executable"]).resolve() != (path.parent / "softmax-hip").resolve():
        raise ValueError("recorded_executable_not_bound_artifact")
    result.update(report_sha256=expected_sha256, current_artifact_hashes=files,
                  audit_implementation_sha256=digest(Path(__file__).read_bytes()),
                  reference_implementation_sha256=digest(Path(reference.__file__).read_bytes()),
                  protocol_validator_implementation_sha256=digest(Path(pilot.__file__).read_bytes()),
                  runtime_library_currently_revalidated=False,
                  limitations=["historical observations are not a new device execution",
                               "no AST-to-binary or host invocation correspondence proof",
                               "recorded shared-library identity is not revalidated against current runtime"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "case_count": result["case_count"],
                      "sha256": digest(output.read_bytes())}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.report, args.report_sha256, args.output)
