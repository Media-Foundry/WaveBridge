"""Independent finite-lane dependency check, not floating-point equivalence."""

from collections import Counter
import hashlib
import json


def check(width, offsets):
    """Check all-to-all coverage with multiplicity under explicit logical XOR semantics."""
    report = {
        "schema_version": "xor-route-check/v1", "status": "unknown",
        "width": width, "offsets": list(offsets) if isinstance(offsets, list) else offsets, "reason": None,
        "checker": "finite-xor-contributors/v1",
        "limits": {"max_width": 64, "max_stages": 16},
        "scope": "finite_full_active_logical_group_xor_add_dependencies",
        "assumptions": ["all lanes participate in every stage",
                        "partner is logical_lane XOR offset within the group",
                        "each stage reads a snapshot of previous stage values",
                        "each lane initially owns one distinct contribution"],
        "floating_point_equivalence": "not_checked",
        "source_to_intrinsic_correspondence": "not_checked",
        "deployable": False,
    }
    if type(width) is not int or width < 2 or width > 64 or width & (width - 1):
        report["reason"] = "unsupported_width"
        return report
    if not isinstance(offsets, list) or len(offsets) > 16:
        report["reason"] = "unsupported_stage_count_or_container"
        return report
    if any(type(offset) is not int or not 0 <= offset < width for offset in offsets):
        report["reason"] = "offset_outside_logical_group"
        return report
    report["input_sha256"] = hashlib.sha256(json.dumps(
        {"width": width, "offsets": offsets}, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    lanes = [Counter({lane: 1}) for lane in range(width)]
    for offset in offsets:
        previous = lanes
        lanes = [previous[lane] + previous[lane ^ offset] for lane in range(width)]
    expected = Counter({lane: 1 for lane in range(width)})
    mismatches = []
    for lane, contributors in enumerate(lanes):
        if contributors != expected:
            mismatches.append({"lane": lane,
                               "missing": sorted(set(expected) - set(contributors)),
                               "repeated": {str(k): v for k, v in contributors.items() if v != 1}})
    report["status"] = "rejected" if mismatches else "checked"
    report["reason"] = "coverage_or_multiplicity_mismatch" if mismatches else None
    report["mismatches"] = mismatches
    report["lanes_checked"] = width
    return report
