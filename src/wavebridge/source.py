"""Source-to-column-evidence entry point; never authorizes a GPU transformation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from wavebridge.frontend.clang_ast import collect, _sha256
from wavebridge.analysis.column_loops import recover
from wavebridge.analysis.initializer_evidence import inspect as inspect_initializer
from wavebridge.analysis.reduction_discovery import discover
from wavebridge.analysis.local_contribution import recover as recover_contribution
from wavebridge.analysis.normalization_output import recover as recover_output
from wavebridge.analysis.row_prefix import recover as recover_prefix
from wavebridge.analysis.launch_facts import inspect as inspect_launch
from wavebridge.analysis.constructor_arguments import inspect as inspect_constructor
from wavebridge.analysis.constructor_fields import recover as recover_constructor_fields
from wavebridge.analysis.launch_guards import recover as recover_launch_guards
from wavebridge.analysis.reduction_chain import recover as recover_chain


def run(source, compiler, compiler_args, symbol, int_bits, output_dir, timeout=30.0):
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    frontend = collect(source, compiler, compiler_args, symbol, timeout,
                       full_translation_unit=True)
    with (directory / "ast.json").open("x", encoding="utf-8") as stream:
        json.dump(frontend, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    report = {
        "schema_version": "source-column-evidence/v1", "status": "unknown",
        "source": frontend["source"], "source_sha256": frontend["source_sha256"],
        "ast_report": "ast.json", "compiler": frontend["compiler"],
        "ast_report_sha256": _sha256(directory / "ast.json"),
        "compiler_sha256": frontend["compiler_sha256"], "command": frontend["command"],
        "int_bits": int_bits, "int_bits_origin": "explicit_external_assumption",
        "checked": False, "deployable": False, "analysis": None,
        "implementation_sha256": {
            name: _sha256(Path(__file__).parent / name) for name in (
                "source.py", "frontend/clang_ast.py", "analysis/column_loops.py",
                "analysis/integer_constants.py", "analysis/initializer_evidence.py",
                "analysis/return_trace.py", "analysis/reduction_discovery.py",
                "analysis/block_reduction.py", "analysis/xor_reduction.py",
                "analysis/local_contribution.py", "analysis/normalization_output.py",
                "analysis/row_prefix.py", "analysis/launch_facts.py",
                "analysis/constructor_arguments.py", "analysis/constructor_fields.py",
                "analysis/launch_guards.py", "analysis/reduction_chain.py")
        },
    }
    locations = frontend["function_locations"]
    if frontend["status"] != "collected":
        report["reason"] = "frontend_" + frontend["status"]
    elif len(frontend["ast_roots"]) != 1 or len(locations) != 1:
        report["reason"] = "ambiguous_entry_or_compilation_view"
    else:
        report["analysis"] = recover(frontend["ast_roots"][0], locations[0]["id"], int_bits)
        # These are initializer call observations, not proof of the induction start value.
        origins = {}
        for loop in report["analysis"].get("loops", []):
            start = loop.get("start") or {}
            declaration_id = start.get("declaration_id")
            if declaration_id and declaration_id not in origins:
                origins[declaration_id] = inspect_initializer(frontend["ast_roots"][0], declaration_id)
        report["start_initializer_evidence"] = origins
        # Reachable structural candidates do not discharge intrinsic or coordinate assumptions.
        report["reduction_discovery"] = discover(
            frontend["ast_roots"][0], locations[0]["id"], int_bits)
        report["local_contribution"] = recover_contribution(
            frontend["ast_roots"][0], locations[0]["id"], int_bits)
        report["reduction_chain"] = recover_chain(
            frontend["ast_roots"][0], locations[0]["id"], int_bits)
        report["normalization_output"] = recover_output(
            frontend["ast_roots"][0], locations[0]["id"], int_bits)
        report["row_prefix"] = recover_prefix(
            frontend["ast_roots"][0], locations[0]["id"], int_bits)
        report["launch_facts"] = inspect_launch(frontend["ast_roots"][0], locations[0]["id"])
        for site in report["launch_facts"]["sites"]:
            site["host_guard_intervals"] = recover_launch_guards(
                frontend["ast_roots"][0], site.get("launch_id"), int_bits)
            site["configuration_constructor_arguments"] = [
                inspect_constructor(frontend["ast_roots"][0], expression, int_bits)
                for expression in site["configuration_arguments"][:2]]
            for constructor in site["configuration_constructor_arguments"]:
                constructor_id = constructor.get("constructor_declaration_id")
                if constructor_id is not None:
                    constructor["field_initialization"] = recover_constructor_fields(
                        frontend["ast_roots"][0], constructor_id)
        report["status"] = "analyzed"
        report["reason"] = None
    with (directory / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--compiler-arg", action="append", default=[])
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--int-bits", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    if not 2 <= args.int_bits <= 128:
        parser.error("--int-bits must be between 2 and 128")
    try:
        report = run(args.source, args.compiler, args.compiler_arg, args.symbol,
                     args.int_bits, args.output_dir, args.timeout)
    except FileExistsError:
        parser.error("output directory must not exist; evidence is never overwritten")
    print(json.dumps({"status": report["status"], "output_dir": str(args.output_dir)}))
    return 0 if report["status"] == "analyzed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
