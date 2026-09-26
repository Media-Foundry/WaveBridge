"""Finite contribution accounting for a two-stage shared-partial reduction."""

from collections import Counter
import hashlib
import json


def check(block_threads, width, offsets, *, second_offsets=None, writer_lane=0,
          shared_slots=None, barrier=True, load_offset=0):
    second = offsets if second_offsets is None else second_offsets
    report = {
        "schema_version": "block-route-check/v1", "status": "unknown", "reason": None,
        "checker": "finite-block-partials/v1",
        "limits": {"max_block_threads": 1024, "max_width": 64, "max_stages": 16},
        "block_threads": block_threads, "width": width,
        "first_offsets": offsets, "second_offsets": second,
        "writer_lane": writer_lane, "shared_slots": shared_slots,
        "barrier": barrier, "load_offset": load_offset,
        "scope": "two_stage_full_active_logical_xor_contribution_counts",
        "source_program_checked": False, "deployable": False,
        "assumptions": ["linear thread coordinate equals block-local thread index",
                        "each logical reduction uses snapshot XOR-add semantics",
                        "all block threads participate and reach the barrier",
                        "shared stores become visible before partial loads"],
        "floating_point_equivalence": "not_checked",
        "runtime_shared_capacity": "not_checked",
    }
    if (type(block_threads) is not int or not 1 <= block_threads <= 1024 or
            type(width) is not int or not 2 <= width <= 64 or width & (width - 1) or
            block_threads % width):
        report["reason"] = "unsupported_shape"
        return report
    groups = block_threads // width
    if groups > width:
        report["reason"] = "too_many_partials_for_one_logical_group"
        return report
    if any(not isinstance(stages, list) or len(stages) > 16 or
           any(type(value) is not int or not 0 <= value < width for value in stages)
           for stages in (offsets, second)):
        report["reason"] = "unsupported_routes"
        return report
    if type(writer_lane) is not int or not 0 <= writer_lane < width or type(load_offset) is not int:
        report["reason"] = "unsupported_writer_or_load_offset"
        return report
    if barrier is not True:
        report["reason"] = "barrier_precondition_missing"
        return report
    capacity = groups if shared_slots is None else shared_slots
    if type(capacity) is not int or not 0 <= capacity <= 1024:
        report["reason"] = "unsupported_shared_capacity"
        return report
    report["shared_slots"] = capacity
    report["input_sha256"] = hashlib.sha256(json.dumps(
        {"block_threads": block_threads, "width": width, "offsets": offsets,
         "second_offsets": second, "writer_lane": writer_lane, "shared_slots": capacity,
         "barrier": barrier, "load_offset": load_offset}, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    if capacity < groups:
        report.update(status="rejected", reason="shared_store_out_of_bounds")
        return report

    def reduce_lanes(lanes, stages):
        for offset in stages:
            previous = lanes
            lanes = [previous[tid] + previous[(tid // width) * width + ((tid % width) ^ offset)]
                     for tid in range(block_threads)]
        return lanes

    lanes = reduce_lanes([Counter({tid: 1}) for tid in range(block_threads)], offsets)
    shared = {group: lanes[group * width + writer_lane] for group in range(groups)}
    seeds = []
    for tid in range(block_threads):
        lane = tid % width
        if lane < groups:
            slot = lane + load_offset
            if slot not in shared:
                report.update(status="rejected", reason="partial_load_unwritten_or_out_of_bounds",
                              counterexample={"thread": tid, "slot": slot})
                return report
            seeds.append(shared[slot])
        else:
            seeds.append(Counter())
    outputs = reduce_lanes(seeds, second)
    expected = Counter({tid: 1 for tid in range(block_threads)})
    for tid, contributions in enumerate(outputs):
        if contributions != expected:
            report.update(status="rejected", reason="coverage_or_multiplicity_mismatch",
                          counterexample={"thread": tid,
                                          "missing": sorted(set(expected) - set(contributions)),
                                          "repeated": {str(k): v for k, v in contributions.items() if v != 1}})
            return report
    report.update(status="checked", threads_checked=block_threads, partials_checked=groups)
    return report


def compare(source, target):
    """Compare explicit route models, not source programs or IEEE results.

    Both sides must specify every model input. Equal block-local input labels
    are a premise, not an inferred mapping between different source programs.
    Ordered DAG identity uses shared exact tuple interning, not digest equality.
    Zero seeds and operand order are retained: no associativity, commutativity
    or floating-point neutral-element simplification is applied.
    """
    result = {
        "schema_version": "block-route-comparison/v1", "status": "unknown", "reason": None,
        "scope": "conditional_same_block_input_contributions_and_ordered_add_DAGs",
        "source_program_checked": False, "deployable": False,
        "floating_point_equivalence": "not_checked",
        "contribution_multisets_equal": None, "ordered_add_dags_equal": None,
        "checks": {},
        "assumptions": ["input contribution at each block-local thread is identical on both sides",
                        "all premises of both finite block-route checks hold",
                        "addition nodes represent the same operation and numerical environment"],
        "remaining_obligations": ["source_target_input_value_correspondence",
                                  "source_intrinsic_and_machine_operation_correspondence",
                                  "participation_synchronization_and_memory_visibility",
                                  "external_floating_point_contract_and_device_execution"],
    }
    keys = {"block_threads", "width", "offsets", "second_offsets", "writer_lane",
            "shared_slots", "barrier", "load_offset"}
    for label, model in (("source", source), ("target", target)):
        if not isinstance(model, dict) or set(model) != keys:
            result["reason"] = label + "_explicit_model_fields_required"
            return result
        # These optional legacy inputs must not silently select defaults here.
        if model["second_offsets"] is None or model["shared_slots"] is None:
            result["reason"] = label + "_implicit_defaults_not_allowed"
            return result
        report = check(**model)
        result["checks"][label] = report
        if report["status"] != "checked":
            result.update(status=report["status"], reason=label + "_route_not_checked")
            return result
    result["input_sha256"] = {side: result["checks"][side]["input_sha256"]
                              for side in ("source", "target")}
    if source["block_threads"] != target["block_threads"]:
        result["reason"] = "different_block_input_mapping_not_established"
        return result

    nodes = {}

    def intern(node):
        if node not in nodes:
            nodes[node] = len(nodes)
        return nodes[node]

    def outputs(model):
        block, width = model["block_threads"], model["width"]

        def reduce_lanes(lanes, stages):
            for offset in stages:
                previous = lanes
                lanes = [intern(("add", previous[tid],
                                 previous[(tid // width) * width + ((tid % width) ^ offset)]))
                         for tid in range(block)]
            return lanes

        lanes = reduce_lanes([intern(("input", tid)) for tid in range(block)], model["offsets"])
        groups = block // width
        shared = [lanes[group * width + model["writer_lane"]] for group in range(groups)]
        zero = intern(("zero_seed",))
        seeds = [shared[tid % width + model["load_offset"]] if tid % width < groups else zero
                 for tid in range(block)]
        return reduce_lanes(seeds, model["second_offsets"])

    left, right = outputs(source), outputs(target)
    mismatches = [tid for tid, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]
    result.update(status="evidence", contribution_multisets_equal=True,
                  ordered_add_dags_equal=not mismatches, compared_threads=len(left),
                  differing_output_threads=mismatches, interned_nodes=len(nodes),
                  operation_relation="ordered_add_DAGs_differ" if mismatches else "identical_ordered_add_DAGs")
    return result
