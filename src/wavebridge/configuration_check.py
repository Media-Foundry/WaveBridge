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


def run(source_report, abi_file, output):
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
        # Missing positions stay unknown rather than silently shrinking coverage.
        for position in range(2):
            constructor = constructors[position] if position < len(constructors) else None
            fields = constructor.get("field_initialization") if isinstance(constructor, dict) else None
            checks.append({"site_index": site_index, "configuration_position": position,
                           "result": check(constructor, fields, abi["types"])})
    report = {
        "schema_version": "conditional-configuration-check/v1", "status": "unknown",
        "source_report_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "abi_sha256": hashlib.sha256(abi_bytes).hexdigest(),
        "source_ast_binding": "not_validated_by_this_checker",
        "abi_source_binding": "explicit_external_assumption_not_established",
        "source_program_checked": False, "deployable": False, "checks": checks,
        "scope": "constructor_integer_field_value_models_only",
        "implementation_sha256": {name: _sha256(Path(__file__).parent / name) for name in (
            "configuration_check.py", "verification/constructor_values.py",
            "verification/integer_conversion.py")},
    }
    statuses = [item["result"]["status"] for item in checks]
    report["all_configuration_models_checked"] = bool(checks) and all(status == "checked" for status in statuses)
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
    arguments = parser.parse_args(argv)
    try:
        report = run(arguments.source_report, arguments.abi, arguments.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({"status": report["status"], "output": str(arguments.output),
                      "source_program_checked": False}))
    return {"checked": 0, "rejected": 1, "unknown": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
