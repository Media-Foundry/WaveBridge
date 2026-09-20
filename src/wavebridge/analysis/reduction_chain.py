"""Recover one connected structural chain from a single AST, not an equivalence proof."""

from wavebridge.frontend.clang_ast import _walk
from wavebridge.analysis.local_contribution import recover as recover_local
from wavebridge.analysis.reduction_discovery import discover
from wavebridge.analysis.shared_storage import recover as recover_storage
from wavebridge.analysis.entry_control import recover as recover_entry


def recover(root, function_id, int_bits):
    # Do not accept caller-authored component reports or IDs from another AST.
    local = recover_local(root, function_id, int_bits)
    discovery = discover(root, function_id, int_bits)
    result = {
        "schema_version": "reduction-chain-recovery/v1", "status": "unknown",
        "reason": None, "function_id": function_id, "int_bits": int_bits,
        "checked": False, "deployable": False, "source_program_checked": False,
        "scope": "local_accumulator_to_block_to_xor_structural_connections_only",
        "links": [], "width": None, "block_threads": None, "offsets": None,
        "shared_storage": None,
        "entry_control": None,
        "unresolved_calls": discovery["unresolved_calls"],
        "external_preconditions": ["source_validity", "coordinate_and_conversion_semantics",
            "shuffle_and_barrier_semantics", "active_converged_participation",
            "shared_storage_capacity_and_aliasing", "launch_matches_thread_organization",
            "floating_point_contract"],
    }

    def unknown(reason):
        result["reason"] = reason
        return result

    if local["status"] != "recovered":
        return unknown("local_contribution_not_recovered")
    if not discovery["traversal_budget_complete"]:
        return unknown("discovery_budget_incomplete")
    blocks = [item for item in discovery["block_candidates"]
              if item["function_id"] == local["consumer_declaration_id"]]
    if len(blocks) != 1:
        return unknown("consumer_block_not_unique")
    block = blocks[0]
    definitions = [node for node in _walk(root)
                   if node.get("id") == block["function_id"] and
                   any(child.get("kind") == "CompoundStmt" for child in node.get("inner", [])
                       if isinstance(child, dict))]
    if len(definitions) != 1:
        return unknown("block_definition_not_unique")
    parameters = [node for node in definitions[0].get("inner", [])
                  if isinstance(node, dict) and node.get("kind") == "ParmVarDecl"]
    position = local["consumer"]["argument_index"]
    if not 0 <= position < len(parameters) or parameters[position].get("id") != block["bindings"]["value_parameter_id"]:
        return unknown("accumulator_parameter_binding_mismatch")
    xors = [item for item in discovery["xor_candidates"]
            if item["function_id"] == block["reduce_declaration_id"]]
    if len(xors) != 1:
        return unknown("block_xor_not_unique")
    xor = xors[0]
    if block["width"] != xor["width"]:
        return unknown("block_xor_width_mismatch")
    if local["loop"]["step"] != block["block_threads"]:
        return unknown("column_step_block_threads_mismatch")
    result["shared_storage"] = recover_storage(root, function_id, block["function_id"],
        local["consumer"]["call_range"], block["bindings"]["shared_parameter_id"])
    result["entry_control"] = recover_entry(root, function_id, block["function_id"],
                                          local["consumer"]["call_range"])
    result.update(status="recovered", width=block["width"],
                  block_threads=block["block_threads"], offsets=xor["offsets"],
                  accumulator_declaration_id=local["accumulator_declaration_id"],
                  mask=xor["mask"], conditional_route_check=xor["conditional_route_check"],
                  links=[
                      {"caller_id": function_id, "callee_id": block["function_id"],
                       "argument_index": position,
                       "parameter_id": block["bindings"]["value_parameter_id"],
                       "call_range": local["consumer"]["call_range"]},
                      {"caller_id": block["function_id"], "callee_id": xor["function_id"],
                       "call_ranges": [block["ranges"]["first_reduce"], block["ranges"]["final_reduce"]]},
                      {"caller_id": xor["function_id"], "callee_id": xor["shuffle_declaration_id"],
                       "call_range": xor["ranges"]["call"]}])
    return result
