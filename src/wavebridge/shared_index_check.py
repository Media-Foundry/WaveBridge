"""Compose freshly checked helper coordinates with conditional shared indexing.

This does not establish pointer identity/capacity, barrier semantics, collective
participation, values written to shared memory, or complete source correctness.
"""

from wavebridge.block_coordinate_check import check as check_coordinates
from wavebridge.verification.shared_indexing import check as check_indexing, BINDING_KEYS


def check(root, thread_report, integer_types, binding):
    result = {
        "schema_version": "conditional-shared-index-check/v1", "status": "unknown", "reason": None,
        "source_program_checked": False, "deployable": False,
        "scope": "writer_and_gather_predicates_and_active_integer_subscripts_only",
        "premises": ["all premises of the fresh coordinate check remain required",
                     "recovered helper is faithful to the valid source AST",
                     "modeled threads reach the shared stages under the same launch protocol"],
        "limitations": ["does not check pointer identity, allocation capacity or aliasing",
                        "does not check stored values, synchronization or floating-point results"],
    }
    coordinates = check_coordinates(root, thread_report, integer_types, binding)
    result["coordinates"] = coordinates
    result["input_sha256"] = coordinates.get("input_sha256")
    if coordinates.get("status") != "checked":
        result.update(status=coordinates.get("status", "unknown"), reason="coordinates_not_checked")
        return result
    helper = coordinates.get("helper_recovery")
    if not isinstance(helper, dict) or helper.get("function_id") != coordinates.get("helper_declaration_id"):
        result["reason"] = "coordinate_helper_binding_missing"
        return result
    recovered_bindings = helper.get("bindings")
    if not isinstance(recovered_bindings, dict):
        result["reason"] = "helper_declaration_bindings_missing"
        return result
    indexing_bindings = {key: recovered_bindings.get(key) for key in BINDING_KEYS}
    indexing = check_indexing(helper.get("shared_access_asts"), indexing_bindings,
                              helper.get("width"), helper.get("block_threads"), integer_types)
    result["indexing"] = indexing
    result.update(status=indexing["status"], reason=indexing.get("reason"),
                  helper_declaration_id=helper["function_id"])
    return result
