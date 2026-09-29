"""Check value preservation for a declared integer interval and explicit widths."""
import hashlib
import json


def check_bitpattern_equality(bits):
    """Equality reflection, not numeric preservation, for a full bitvector.

    Both conversions must preserve every bit of the same-width representation.
    Signed interpretation can change a numeric value without losing identity.
    This function does not establish that any source cast meets that premise.
    """
    report = {"schema_version": "bitpattern-equality-check/v1", "status": "unknown",
              "reason": None, "bits": bits, "source_program_checked": False,
              "deployable": False, "numeric_value_preservation_established": False,
              "scope": "equal_converted_patterns_imply_equal_source_patterns",
              "assumptions": ["both conversions preserve all bits at the declared equal width",
                              "determinate padding-free trap-free bitvectors with unique two's-complement signed decoding",
                              "source and destination value equality is equivalent to all-bit equality"]}
    if type(bits) is not int or not 2 <= bits <= 128:
        report["reason"] = "unsupported_width"
        return report
    report.update(status="checked", domain={"lower": 0, "upper": (1 << bits) - 1},
                  equality_reflected=True, argument="identity_on_all_same_width_bit_patterns",
                  input_sha256=hashlib.sha256(str(bits).encode()).hexdigest())
    return report


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
