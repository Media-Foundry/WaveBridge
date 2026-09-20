"""Check constructor value models under an explicit ABI, never authorize deployment."""
import argparse
import hashlib
import json
from pathlib import Path

from wavebridge.frontend.clang_ast import _sha256
from wavebridge.verification.constructor_values import check


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field: " + key)
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("non-finite JSON constant: " + value)


def _host_guard_assumptions(site, source, abi):
    """Bind a reported domain as an explicit premise, never re-prove its guard."""
    gate = {"status": "unknown", "reason": None,
            "source_guard_semantics": "not_revalidated_by_this_checker"}
    guard = site.get("host_guard_intervals")
    if not isinstance(guard, dict) or guard.get("schema_version") != "launch-guards/v1":
        gate["reason"] = "host_guard_report_missing_or_wrong_schema"
    elif guard.get("status") != "recovered":
        gate["reason"] = "host_guard_not_recovered"
    elif (not isinstance(site.get("launch_id"), str) or not site["launch_id"] or
          guard.get("launch_id") != site["launch_id"]):
        gate["reason"] = "host_guard_launch_id_mismatch"
    elif guard.get("interpretation") != "necessary_conditions_to_pass_supported_early_returns_only":
        gate["reason"] = "host_guard_interpretation_unsupported"
    else:
        bits = guard.get("int_bits")
        int_type = abi["types"].get("int")
        if (type(bits) is not int or not 2 <= bits <= 128 or
                type(source.get("int_bits")) is not int or source["int_bits"] != bits or
                not isinstance(int_type, dict) or type(int_type.get("bits")) is not int or
                int_type["bits"] != bits or int_type.get("signed") is not True):
            gate["reason"] = "host_guard_integer_abi_mismatch"
        elif not isinstance(guard.get("intervals"), list) or not guard["intervals"]:
            gate["reason"] = "host_guard_intervals_missing"
        else:
            gate.update(status="usable_as_explicit_assumption", guard_report_sha256=hashlib.sha256(
                json.dumps(guard, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode()).hexdigest())
            return gate, guard["intervals"]
    return gate, []


def run(source_report, abi_file, output, *, use_host_guard_assumptions=False):
    if type(use_host_guard_assumptions) is not bool:
        raise ValueError("use_host_guard_assumptions must be an explicit boolean")
    source_report, abi_file, output = map(Path, (source_report, abi_file, output))
    if output.exists():
        raise FileExistsError("output must be a new file")
    source_bytes, abi_bytes = source_report.read_bytes(), abi_file.read_bytes()
    source = json.loads(source_bytes, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    abi = json.loads(abi_bytes, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    if not isinstance(source, dict) or source.get("schema_version") != "source-column-evidence/v1":
        raise ValueError("expected a source-column-evidence/v1 report")
    if source.get("status") != "analyzed":
        raise ValueError("source analysis did not run successfully")
    if not isinstance(abi, dict) or abi.get("schema_version") != "integer-abi-assumptions/v1" or not isinstance(abi.get("types"), dict):
        raise ValueError("expected explicit integer-abi-assumptions/v1 types")
    launches = source.get("launch_facts", {})
    if not isinstance(launches, dict) or not isinstance(launches.get("sites", []), list):
        raise ValueError("launch facts must contain a sites list")
    sites = launches.get("sites", [])
    checks = []
    for site_index, site in enumerate(sites):
        if not isinstance(site, dict):
            raise ValueError("launch site must be an object")
        constructors = site.get("configuration_constructor_arguments", [])
        if not isinstance(constructors, list):
            raise ValueError("constructor arguments must be a list")
        premise_gate, intervals = (_host_guard_assumptions(site, source, abi)
                                   if use_host_guard_assumptions else (None, None))
        # Missing positions stay unknown rather than silently shrinking coverage.
        for position in range(2):
            constructor = constructors[position] if position < len(constructors) else None
            fields = constructor.get("field_initialization") if isinstance(constructor, dict) else None
            item = {"site_index": site_index, "configuration_position": position,
                    "result": check(constructor, fields, abi["types"],
                                    declaration_intervals=intervals)}
            if use_host_guard_assumptions:
                item["host_guard_premise_gate"] = premise_gate
            checks.append(item)
    report = {
        "schema_version": ("conditional-configuration-check/v2" if use_host_guard_assumptions
                           else "conditional-configuration-check/v1"), "status": "unknown",
        "source_report_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "abi_sha256": hashlib.sha256(abi_bytes).hexdigest(),
        "source_ast_binding": "not_validated_by_this_checker",
        "abi_source_binding": "explicit_external_assumption_not_established",
        "source_program_checked": False, "deployable": False, "checks": checks,
        "scope": ("constructor_integer_field_domain_models_only" if use_host_guard_assumptions
                  else "constructor_integer_field_value_models_only"),
        "host_guard_assumptions_enabled": use_host_guard_assumptions,
        "implementation_sha256": {name: _sha256(Path(__file__).parent / name) for name in (
            "configuration_check.py", "verification/constructor_values.py",
            "verification/integer_conversion.py")},
    }
    statuses = [item["result"]["status"] for item in checks]
    premises_usable = all(item.get("host_guard_premise_gate", {}).get("status") ==
                          "usable_as_explicit_assumption" for item in checks) if use_host_guard_assumptions else True
    report["all_configuration_models_checked"] = (
        bool(checks) and premises_usable and all(status == "checked" for status in statuses))
    if "rejected" in statuses:
        report["status"] = "rejected"
    elif report["all_configuration_models_checked"]:
        report["status"] = "checked"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_report", type=Path)
    parser.add_argument("--abi", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--use-host-guard-assumptions", action="store_true",
                        help="Explicitly assume recovered host guard intervals; does not prove source validity")
    arguments = parser.parse_args(argv)
    try:
        report = run(arguments.source_report, arguments.abi, arguments.output,
                     use_host_guard_assumptions=arguments.use_host_guard_assumptions)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({"status": report["status"], "output": str(arguments.output),
                      "source_program_checked": False}))
    return {"checked": 0, "rejected": 1, "unknown": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
