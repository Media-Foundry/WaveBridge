"""Check reported shared allocation under explicit ABI and structural premises."""
import argparse
import hashlib
import json
from pathlib import Path

from wavebridge.configuration_check import _unique_object, _invalid_constant
from wavebridge.verification.shared_capacity import check


def run(source_report, abi_file, output):
    source_report, abi_file, output = map(Path, (source_report, abi_file, output))
    if output.exists():
        raise FileExistsError("output must be a new file")
    raw, abi_raw = source_report.read_bytes(), abi_file.read_bytes()
    source = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    abi = json.loads(abi_raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    if not isinstance(source, dict) or source.get("schema_version") != "source-column-evidence/v1" or source.get("status") != "analyzed":
        raise ValueError("expected analyzed source-column-evidence/v1")
    if not isinstance(abi, dict) or abi.get("schema_version") != "storage-abi-assumptions/v1" or not isinstance(abi.get("integer_types"), dict) or not isinstance(abi.get("sizeof_bytes"), dict):
        raise ValueError("expected explicit storage-abi-assumptions/v1")
    launches = source.get("launch_facts")
    if not isinstance(launches, dict) or not isinstance(launches.get("sites"), list):
        raise ValueError("launch sites missing")
    chain = source.get("reduction_chain")
    checks = [{"launch_id": site.get("launch_id") if isinstance(site, dict) else None,
               "result": check(chain, site, abi["integer_types"], abi["sizeof_bytes"])}
              for site in launches["sites"]]
    statuses = [item["result"]["status"] for item in checks]
    complete = launches.get("status") == "evidence" and launches.get("unresolved_sites") == []
    ids = [site.get("launch_id") if isinstance(site, dict) else None for site in launches["sites"]]
    unique_ids = all(isinstance(value, str) and value for value in ids) and len(set(ids)) == len(ids)
    complete = complete and unique_ids
    status = "rejected" if "rejected" in statuses else "checked" if complete and statuses and all(s == "checked" for s in statuses) else "unknown"
    report = {"schema_version": "conditional-shared-capacity-check/v1", "status": status,
              "scope": "reported_array_capacity_under_explicit_abi_and_structure_assumptions",
              "source_report_sha256": hashlib.sha256(raw).hexdigest(),
              "abi_sha256": hashlib.sha256(abi_raw).hexdigest(),
              "source_ast_binding": "not_revalidated", "source_program_checked": False,
              "deployable": False, "all_launch_sites_resolved": complete, "checks": checks,
              "unique_launch_ids": unique_ids,
              "premises": sorted({p for item in checks for p in item["result"]["premises"]}),
              "rejection_scope": "any_reported_site_has_a_conditional_capacity_counterexample_not_a_whole_program_proof",
              "implementation_sha256": {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                  for name in ("shared_capacity_check.py", "configuration_check.py",
                               "verification/shared_capacity.py", "verification/shared_bytes.py",
                               "verification/kernel_arguments.py", "verification/integer_conversion.py")}}
    with output.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_report", type=Path)
    parser.add_argument("--abi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run(args.source_report, args.abi, args.output)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps({"status": report["status"], "output": str(args.output)}))
    return {"checked": 0, "rejected": 1, "unknown": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
