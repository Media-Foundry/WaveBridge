"""Check value preservation for a declared integer interval and explicit widths."""
import hashlib
import json


def check_interval(lower, upper, source_bits, source_signed, target_bits, target_signed):
    inputs = {"lower": lower, "upper": upper, "source_bits": source_bits,
              "source_signed": source_signed, "target_bits": target_bits,
              "target_signed": target_signed}
    report = {"schema_version": "integer-conversion-check/v1", "status": "unknown",
              "reason": None, "inputs": inputs, "checker": "interval-representability/v1",
              "scope": "value_preserving_integer_conversion_on_declared_interval",
              "source_program_checked": False, "deployable": False,
              "assumptions": ["source values lie within the declared interval",
                              "declared widths and signedness match the source and target types"]}
    if (any(type(value) is not int for value in (lower, upper, source_bits, target_bits)) or
            type(source_signed) is not bool or type(target_signed) is not bool or
            not 2 <= source_bits <= 128 or not 2 <= target_bits <= 128 or lower > upper):
        report["reason"] = "unsupported_input"
        return report
    report["input_sha256"] = hashlib.sha256(json.dumps(inputs, sort_keys=True,
                                                       separators=(",", ":")).encode()).hexdigest()

    def limits(bits, signed):
        return (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if signed else (0, (1 << bits) - 1)

    source_min, source_max = limits(source_bits, source_signed)
    target_min, target_max = limits(target_bits, target_signed)
    if lower < source_min or upper > source_max:
        report["reason"] = "interval_not_representable_in_source_type"
    elif lower < target_min or upper > target_max:
        report.update(status="rejected", reason="conversion_not_value_preserving",
                      counterexample=lower if lower < target_min else upper)
    else:
        report["status"] = "checked"
    return report
