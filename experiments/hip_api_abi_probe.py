"""Compile-only SDK ABI observations, never an API correctness certificate."""
import argparse
import hashlib
import json
from pathlib import Path

from wavebridge.frontend.clang_ast import collect, _walk

FIELDS = {"int_bits", "status_bits", "underlying_bits", "underlying_is_unsigned",
          "underlying_is_unsigned_int", "success_as_int", "last_named_status_as_int",
          "unsigned_max_converts_to_minus_one"}
BOOL_FIELDS = {"underlying_is_unsigned", "underlying_is_unsigned_int", "unsigned_max_converts_to_minus_one"}


def observations(collection):
    if collection.get("status") != "collected":
        raise ValueError("collection_not_successful")
    roots = collection.get("ast_roots", [])
    if len(roots) != 1 or roots[0].get("kind") != "FunctionDecl" or roots[0].get("name") != "WaveBridgeHipAbiProbe":
        raise ValueError("unique_probe_function_required")
    constants = [n for n in _walk(roots[0]) if n.get("kind") == "EnumConstantDecl"]
    if len(constants) != len(FIELDS) or {n.get("name") for n in constants} != FIELDS:
        raise ValueError("probe_fields_missing_or_duplicated")
    result = {}
    identities = set()
    for declaration in constants:
        values = [n for n in _walk(declaration) if n.get("kind") == "ConstantExpr" and "value" in n]
        if len(values) != 1 or not isinstance(values[0]["value"], str):
            raise ValueError("unique_compiler_constant_observation_required")
        expression = values[0]
        for identifier in (declaration.get("id"), expression.get("id")):
            if not isinstance(identifier, str) or not identifier or identifier in identities:
                raise ValueError("observation_identity_missing_or_duplicated")
            identities.add(identifier)
        raw_value = expression["value"]
        spelling = expression.get("type", {}).get("desugaredQualType", expression.get("type", {}).get("qualType"))
        if declaration["name"] in BOOL_FIELDS:
            if spelling != "bool":
                raise ValueError("boolean_field_type_required")
            if raw_value not in ("true", "false"):
                raise ValueError("malformed_boolean_observation")
            value = raw_value == "true"
        else:
            if spelling not in {"int", "unsigned int", "long", "unsigned long", "long long", "unsigned long long"}:
                raise ValueError("integer_field_type_required")
            value = int(raw_value)
        result[declaration["name"]] = {"value": value, "expression_type": expression.get("type"),
                                        "declaration_id": declaration.get("id"),
                                        "constant_expression_id": expression.get("id")}
    return result


def run(compiler, include, output, *, hip_context_source=None):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("output_exists")
    source = Path(__file__).with_suffix(".cpp")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    driver_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    context = Path(hip_context_source).resolve(strict=True) if hip_context_source is not None else None
    context_hash = hashlib.sha256(context.read_bytes()).hexdigest() if context is not None else None
    arguments = ["-std=c++17", "-D__HIP_PLATFORM_AMD__=1", "-I", str(Path(include).resolve())]
    if context is not None:
        # Explicit recorded pilot recipe, never execute a command read from an artifact.
        arguments = ["-std=c++17", "-O2", "--offload-device-only", "-DWB_COMPILED_COOP_WIDTH=32",
                     "-I" + str(context.parent), "-x", "hip", "-include", str(context)]
    collection = collect(source, compiler, arguments,
                         "WaveBridgeHipAbiProbe", timeout=120, dependency_binding="required", toolchain_trace=True)
    report = {"schema_version": "hip-api-abi-observation/v1", "status": "unknown", "reason": None,
              "collection": collection, "observations": {}, "source_sha256": source_hash,
              "driver_sha256": driver_hash, "GPU_executed": False, "program_executed": False,
              "mode": "augmented_hip_device_context" if context is not None else "standalone_host",
              "context_source": str(context) if context is not None else None,
              "context_source_sha256": context_hash,
              "original_kernel_TU_ABI_binding": False, "runtime_enum_domain_established": False,
              "API_success_verified": False, "runtime_linkage_verified": False,
              "source_program_checked": False, "deployable": False,
              "limitations": ["probe translation unit, not identical to the original kernel translation unit",
                              "forced inclusion changes include level and base file; no context equivalence proof",
                              "compiler constant observations, not general conversion or API proofs",
                              "last named enumerator is not asserted to bound runtime expressions"]}
    try:
        if collection.get("toolchain_trace", {}).get("status") != "observed":
            raise ValueError("toolchain_trace_not_observed")
        report["observations"] = observations(collection)
        if (source_hash != hashlib.sha256(source.read_bytes()).hexdigest() or
                driver_hash != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()):
            raise ValueError("probe_implementation_changed")
        if context is not None:
            if context_hash != hashlib.sha256(context.read_bytes()).hexdigest():
                raise ValueError("context_source_changed")
            files = collection.get("dependency_binding", {}).get("files", [])
            matches = [entry for entry in files if entry.get("resolved_path") == str(context)]
            if len(matches) != 1 or matches[0].get("sha256") != context_hash:
                raise ValueError("context_source_dependency_binding_missing")
        report["status"] = "observed"
    except (ValueError, TypeError, KeyError) as error:
        report["reason"] = str(error)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "reason": report["reason"],
                      "observations": report["observations"], "output": str(output)}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--include", required=True, help="SDK include path for standalone host mode; context mode uses hipcc's SDK")
    parser.add_argument("--output", required=True)
    parser.add_argument("--hip-context-source", help="Use the recorded device-only pilot recipe with this source force-included")
    args = parser.parse_args()
    result = run(args.compiler, args.include, args.output, hip_context_source=args.hip_context_source)
    raise SystemExit(0 if result["status"] == "observed" else 2)
