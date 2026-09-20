import json
from pathlib import Path
import tempfile
import unittest

from wavebridge.configuration_check import run


def constructor_fixture(symbolic):
    """Explicit report fixture, not recovered source or a GPU result."""
    integer, unsigned = {"qualType": "int"}, {"qualType": "unsigned int"}
    leaf = ({"kind": "DeclRefExpr", "type": integer,
             "referencedDecl": {"id": "rows", "kind": "VarDecl", "type": integer}}
            if symbolic else {"kind": "IntegerLiteral", "type": integer, "value": "256"})
    operand = ({"kind": "ImplicitCastExpr", "castKind": "LValueToRValue",
                "type": integer, "inner": [leaf]} if symbolic else leaf)
    casts = [{"cast_kind": "IntegralCast", "source_type": integer,
              "destination_type": unsigned}]
    if symbolic:
        casts.append({"cast_kind": "LValueToRValue", "source_type": integer,
                      "destination_type": integer})
    return {
        "schema_version": "constructor-arguments/v1", "status": "inspected",
        "constructor_declaration_id": "ctor",
        "arguments": [{"position": 0, "status": "symbolic" if symbolic else "evidence",
                       "declaration_id": "rows" if symbolic else None,
                       "argument_ast": {"kind": "ImplicitCastExpr", "castKind": "IntegralCast",
                                        "type": unsigned, "inner": [operand]},
                       "casts": casts,
                       "pre_conversion_constant": None if symbolic else {
                           "status": "evaluated", "source": "integer_literal", "value": 256}}],
        "field_initialization": {
            "schema_version": "constructor-fields/v1", "status": "recovered",
            "constructor_declaration_id": "ctor",
            "record_completeness": "all_direct_record_fields_initialized",
            "field_mappings": [{"field_id": "field", "field_name": "x", "parameter_id": "param",
                                "parameter_position": 0, "parameter_type": unsigned,
                                "field_type": unsigned, "casts": []}]}}


def source_fixture():
    return {"schema_version": "source-column-evidence/v1", "status": "analyzed", "int_bits": 32,
            "launch_facts": {"sites": [{"launch_id": "launch",
                "configuration_constructor_arguments": [constructor_fixture(True), constructor_fixture(False)],
                "host_guard_intervals": {"schema_version": "launch-guards/v1", "status": "recovered",
                    "launch_id": "launch", "int_bits": 32,
                    "interpretation": "necessary_conditions_to_pass_supported_early_returns_only",
                    "intervals": [{"declaration_id": "rows", "lower": 1, "upper": 8,
                                   "type": {"qualType": "int"}}]}}]}}


class ConfigurationCheckTests(unittest.TestCase):
    def test_host_guard_domains_require_opt_in_and_preserve_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "source.json"
            source.write_text(json.dumps(source_fixture()))
            original = source.read_bytes()
            abi = Path(__file__).parents[1] / "examples/abi/int32-conditional.json"
            default = run(source, abi, directory / "default.json")
            explicit = run(source, abi, directory / "explicit.json", use_host_guard_assumptions=True)
            self.assertEqual(default["status"], "unknown")
            self.assertEqual(default["schema_version"], "conditional-configuration-check/v1")
            self.assertEqual(explicit["status"], "checked", explicit)
            self.assertEqual(explicit["schema_version"], "conditional-configuration-check/v2")
            self.assertFalse(explicit["source_program_checked"])
            self.assertFalse(explicit["deployable"])
            self.assertEqual(source.read_bytes(), original)

    def test_guard_binding_and_abi_mismatch_do_not_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "source.json"
            abi = Path(__file__).parents[1] / "examples/abi/int32-conditional.json"
            for index, (key, value) in enumerate((
                ("launch_id", "other"), ("int_bits", 16), ("int_bits", True),
                ("status", "unknown"), ("intervals", []), ("interpretation", "guessed"),
            )):
                report = source_fixture()
                report["launch_facts"]["sites"][0]["host_guard_intervals"][key] = value
                source.write_text(json.dumps(report))
                result = run(source, abi, directory / f"check-{index}.json",
                             use_host_guard_assumptions=True)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["all_configuration_models_checked"])
                self.assertEqual(result["checks"][0]["host_guard_premise_gate"]["status"], "unknown")

    def test_negative_interval_is_not_value_preserving(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report = source_fixture()
            report["launch_facts"]["sites"][0]["host_guard_intervals"]["intervals"][0]["lower"] = -1
            source = directory / "source.json"
            source.write_text(json.dumps(report))
            abi = Path(__file__).parents[1] / "examples/abi/int32-conditional.json"
            result = run(source, abi, directory / "check.json", use_host_guard_assumptions=True)
            self.assertEqual(result["status"], "rejected", result)

    def test_empty_launches_cannot_pass_and_outputs_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "source.json"
            source.write_text(json.dumps({"schema_version": "source-column-evidence/v1",
                                          "status": "analyzed", "launch_facts": {"sites": []}}))
            abi = Path(__file__).parents[1] / "examples/abi/int32-conditional.json"
            result = run(source, abi, directory / "check.json")
            self.assertEqual(result["status"], "unknown")
            self.assertFalse(result["all_configuration_models_checked"])
            self.assertFalse(result["source_program_checked"])
            self.assertEqual(len(result["source_report_sha256"]), 64)
            with self.assertRaises(FileExistsError):
                run(source, abi, source)
            with self.assertRaises(FileExistsError):
                run(source, abi, directory / "check.json")

    def test_missing_constructor_positions_remain_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "source.json"
            source.write_text(json.dumps({"schema_version": "source-column-evidence/v1",
                                          "status": "analyzed", "launch_facts": {"sites": [{}]}}))
            abi = Path(__file__).parents[1] / "examples/abi/int32-conditional.json"
            result = run(source, abi, directory / "check.json")
            self.assertEqual(len(result["checks"]), 2)
            self.assertEqual(result["status"], "unknown")

    def test_malformed_or_duplicate_fields_do_not_produce_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "source.json"
            abi = Path(__file__).parents[1] / "examples/abi/int32-conditional.json"
            for content in (
                '{"status":"analyzed", "status":"unknown"}',
                '{"value": NaN}',
                '{"value": Infinity}',
                json.dumps({"schema_version": "source-column-evidence/v1", "status": "analyzed",
                            "launch_facts": None}),
            ):
                source.write_text(content)
                with self.assertRaises(ValueError):
                    run(source, abi, directory / "check.json")
                self.assertFalse((directory / "check.json").exists())


if __name__ == "__main__":
    unittest.main()
