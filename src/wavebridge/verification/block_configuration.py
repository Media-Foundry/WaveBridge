"""Compare launch block fields under explicit axis identities, never infer axes by name."""
import hashlib
import json

from wavebridge.verification.constructor_values import check as check_fields


def check_guarded_local_coordinate(payload, selection, initializer_id, assignment_id, quotient_id,
                                   object_id, power_selection, conversion_contract, output_contract,
                                   integer_types, axis_protocol, coordinate_initializer_id, *,
                                   query_guard_id, instantiated_function_id=None, max_ast_nodes=1_000_000):
    """Derive a device initializer domain from a fresh multidimensional block copy.

    The protocol identifies API axes and the local-ID leaf, but supplies no
    dimensions or coordinate bounds. API/ABI realization remains an assumption.
    """
    from wavebridge.verification.launch_binding import check_guarded_configuration_copy
    from wavebridge.verification.initializer_domain import check_source
    from wavebridge.verification.getter_returns import _hash

    result = {"schema_version": "guarded-block-coordinate/v1", "status": "unknown", "reason": None,
              "scope": "selected_device_local_initializer_under_explicit_configuration_and_coordinate_API",
              "checks": {}, "dimensions": None, "derived_leaf_domain": None,
              "coordinate_initialization_domain_checked": False, "coordinate_API_verified": False,
              "runtime_configuration_verified": False, "hardware_limits_checked": False,
              "coordinate_history_checked": False, "thread_participation_checked": False,
              "source_program_checked": False, "deployable": False, "assumptions": []}
    try:
        keys = {"schema_version", "ast_root_sha256", "kernel_declaration_id", "launch_id",
                "configuration_declaration_id", "configuration_parameter_id", "record_declaration_id",
                "block_position", "fields", "coordinate", "semantics"}
        if (not isinstance(axis_protocol, dict) or set(axis_protocol) != keys or
                axis_protocol["schema_version"] != "launch-coordinate-assumptions/v1" or
                axis_protocol["semantics"] != "bound_parameter_axes_define_selected_kernel_workgroup_extents" or
                type(axis_protocol["block_position"]) is not int or axis_protocol["block_position"] != 1):
            raise ValueError("explicit_axis_API_protocol_required_without_numeric_bounds")
        axes, coordinate = axis_protocol["fields"], axis_protocol["coordinate"]
        if (not isinstance(axes, dict) or set(axes) != {"x", "y", "z"} or
                any(not isinstance(v, str) or not v for v in axes.values()) or len(set(axes.values())) != 3 or
                not isinstance(coordinate, dict) or set(coordinate) != {"declaration_id", "return_type", "axis", "semantics"} or
                coordinate["semantics"] != "workgroup_local_id" or type(coordinate["axis"]) is not int or
                coordinate["axis"] not in (0, 1, 2)):
            raise ValueError("axis_or_coordinate_identity_protocol_invalid")
        if (not isinstance(selection, dict) or any(axis_protocol[k] != selection.get(k)
                for k in ("ast_root_sha256", "kernel_declaration_id", "launch_id", "configuration_declaration_id"))):
            raise ValueError("axis_protocol_selection_mismatch")
        bound = check_guarded_configuration_copy(payload, selection, initializer_id, assignment_id, quotient_id,
                    object_id, power_selection, conversion_contract, output_contract, integer_types,
                    query_guard_id=query_guard_id, configuration_position=1,
                    instantiated_function_id=instantiated_function_id, max_ast_nodes=max_ast_nodes)
        result["checks"]["configuration"] = bound
        if bound["status"] != "checked" or bound["configuration_slot_field_domains_under_model"] is not True:
            raise ValueError("fresh_configuration_field_domains_not_checked")
        result["assumptions"] = bound["assumptions"] + [
            "the bound configuration parameter fields define the selected kernel workgroup extents according to the explicit axis API protocol",
            "the exact external coordinate leaf denotes the stated workgroup local axis for this selected kernel invocation",
            "runtime realizes that configuration and all kernel/API preconditions hold; these premises are not verified here"]
        copied = bound["checks"]["copy"]
        if (axis_protocol["configuration_parameter_id"] != bound["configuration_parameter_id"] or
                axis_protocol["record_declaration_id"] != copied["record_declaration_id"]):
            raise ValueError("axis_protocol_record_or_parameter_mismatch")
        fields = {f["field_id"]: f["interval"] for f in bound["fields"]}
        if len(fields) != 3 or set(fields) != set(axes.values()):
            raise ValueError("axis_fields_not_exact_record_bijection")
        dimensions = {}
        for axis, identifier in axes.items():
            interval = fields[identifier]
            if (type(interval.get("lower")) is not int or type(interval.get("upper")) is not int or
                    interval["lower"] != interval["upper"] or interval["lower"] <= 0):
                raise ValueError("positive_singleton_dimensions_required")
            dimensions[axis] = interval["lower"]
        axis = ("x", "y", "z")[coordinate["axis"]]
        leaf = {"schema_version": "getter-leaf-domain/v1", "declaration_id": coordinate["declaration_id"],
                "return_type": coordinate["return_type"], "arguments": [coordinate["axis"]],
                "lower": 0, "upper": dimensions[axis] - 1}
        result.update(dimensions=dimensions, block_thread_count=dimensions["x"] * dimensions["y"] * dimensions["z"],
                      derived_leaf_domain=leaf, selected_axis=axis)
        # A valid initializer in another function must not consume this launch's domain.
        root, index, pending, count = payload["ast"], {}, [payload["ast"]], 0
        while pending:
            node = pending.pop(); count += 1
            if count > max_ast_nodes or not isinstance(node, dict):
                raise ValueError("coordinate_owner_AST_budget_or_shape_invalid")
            index.setdefault(node.get("id"), []).append(node)
            for slot in ("inner", "array_filler"):
                children = node.get(slot, [])
                if not isinstance(children, list) or any(not isinstance(c, dict) for c in children):
                    raise ValueError("coordinate_owner_AST_children_invalid")
                pending.extend(c for c in children if c)
        kernels = index.get(bound["kernel_declaration_id"], [])
        declarations = index.get(coordinate_initializer_id, [])
        if len(kernels) != 1 or len(declarations) != 1:
            raise ValueError("coordinate_owner_or_declaration_not_unique")
        bodies = [n for n in kernels[0].get("inner", []) if n.get("kind") == "CompoundStmt"]
        direct = [v for body in bodies for stmt in body.get("inner", []) if stmt.get("kind") == "DeclStmt"
                  for v in stmt.get("inner", []) if v is declarations[0]]
        if len(bodies) != 1 or len(direct) != 1:
            raise ValueError("coordinate_initializer_not_direct_selected_kernel_local")
        initialized = check_source(root, coordinate_initializer_id, leaf, integer_types, max_ast_nodes=max_ast_nodes)
        result["checks"]["initializer"] = initialized
        result["assumptions"] = list(dict.fromkeys(result["assumptions"] + initialized["assumptions"]))
        if (initialized["status"] != "checked" or
                initialized["input_sha256"]["root"] != bound["input_sha256"]["root"] or
                initialized["input_sha256"]["leaf_contract"] != _hash(leaf) or
                initialized["input_sha256"]["integer_types"] != _hash(integer_types)):
            raise ValueError("fresh_coordinate_initializer_not_checked")
        result.update(status="checked", coordinate_initialization_domain_checked=True,
                      kernel_declaration_id=bound["kernel_declaration_id"], launch_id=bound["launch_id"],
                      coordinate_initializer_id=coordinate_initializer_id, result_interval=initialized["result_interval"],
                      input_sha256={"root": bound["input_sha256"]["root"], "payload": _hash(payload),
                                    "configuration_inputs": _hash(bound["input_sha256"]),
                                    "axis_protocol": _hash(axis_protocol),
                                    "coordinate_initializer_id": _hash(coordinate_initializer_id)})
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        result["reason"] = str(error)
    return result


def check_guarded_coordinate_to_statement(payload, selection, initializer_id, assignment_id, quotient_id,
                                         object_id, power_selection, conversion_contract, output_contract,
                                         integer_types, axis_protocol, coordinate_initializer_id, statement_id,
                                         call_protocols, *, query_guard_id, instantiated_function_id=None,
                                         max_ast_nodes=1_000_000, use_static_branches=False):
    """Carry a configuration-derived coordinate to a later direct statement.

    This checks the prefix only. A selected loop's body and subsequent entries
    are deliberately outside this conclusion, including when that body writes
    the coordinate. All history no-alias/valid-execution premises remain.
    """
    from wavebridge.verification.initializer_domain import check_to_statement
    from wavebridge.verification.getter_returns import _hash

    result = {"schema_version": "guarded-coordinate-to-statement/v1", "status": "unknown", "reason": None,
              "scope": "configuration_derived_coordinate_at_first_entry_to_selected_direct_statement",
              "checks": {}, "assumptions": [], "result_interval": None,
              "value_preserved_to_statement": False, "target_body_checked": False,
              "target_evaluation_checked": False,
              "later_iterations_checked": False, "target_reachability_proved": False,
              "coordinate_API_verified": False, "runtime_configuration_verified": False,
              "source_program_checked": False, "deployable": False}
    try:
        if (not isinstance(statement_id, str) or not statement_id or not isinstance(call_protocols, dict) or
                len(call_protocols) > 64 or type(use_static_branches) is not bool or
                any(not isinstance(k, str) or not k or not isinstance(v, dict) for k, v in call_protocols.items())):
            raise ValueError("invalid_history_selection_or_protocols")
        coordinate = check_guarded_local_coordinate(payload, selection, initializer_id, assignment_id, quotient_id,
                        object_id, power_selection, conversion_contract, output_contract, integer_types,
                        axis_protocol, coordinate_initializer_id, query_guard_id=query_guard_id,
                        instantiated_function_id=instantiated_function_id, max_ast_nodes=max_ast_nodes)
        result["checks"]["coordinate"] = coordinate
        result["assumptions"] = list(coordinate["assumptions"])
        if coordinate["status"] != "checked" or coordinate["coordinate_initialization_domain_checked"] is not True:
            raise ValueError("fresh_configuration_coordinate_domain_not_checked")
        leaf = coordinate["derived_leaf_domain"]
        history = check_to_statement(payload, coordinate_initializer_id, statement_id, leaf, integer_types,
                                     call_protocols, max_ast_nodes=max_ast_nodes,
                                     use_static_branches=use_static_branches)
        result["checks"]["history"] = history
        result["assumptions"] = list(dict.fromkeys(result["assumptions"] + history["assumptions"]))
        if history["status"] != "checked" or history["value_preserved_to_statement"] is not True:
            raise ValueError("fresh_coordinate_history_not_checked")
        if (history["selection"]["function_id"] != coordinate["kernel_declaration_id"] or
                history["selection"]["declaration_id"] != coordinate_initializer_id or
                history["selection"]["target_statement_id"] != statement_id or
                history["result_interval"] != coordinate["result_interval"] or
                history["input_sha256"] != {"root": coordinate["input_sha256"]["root"],
                    "declaration_id": _hash(coordinate_initializer_id), "leaf_contract": _hash(leaf),
                    "integer_types": _hash(integer_types), "statement_id": _hash(statement_id),
                    "call_protocols": _hash(call_protocols), "static_branches": _hash(use_static_branches)}):
            raise ValueError("fresh_history_domain_or_input_binding_mismatch")
        result.update(status="checked", value_preserved_to_statement=True,
                      kernel_declaration_id=coordinate["kernel_declaration_id"], launch_id=coordinate["launch_id"],
                      coordinate_initializer_id=coordinate_initializer_id, statement_id=statement_id,
                      result_interval=coordinate["result_interval"],
                      input_sha256={"root": coordinate["input_sha256"]["root"],
                                    "coordinate_inputs": _hash(coordinate["input_sha256"]),
                                    "history_inputs": _hash(history["input_sha256"]),
                                    "max_ast_nodes": _hash(max_ast_nodes)})
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        result["reason"] = str(error)
    return result


def check(chain, site, integer_types, axis_binding):
    result = {"schema_version": "block-configuration-check/v1", "status": "unknown",
              "reason": None, "field_check": None, "dimensions": None,
              "source_program_checked": False, "deployable": False,
              "premises": ["reports_faithfully_describe_same_ast",
                  "explicit_axis_field_binding_matches_launch_API",
                  "configuration_argument_1_is_block_dimensions",
                  "integer_ABI_and_declaration_constants_match_source_target",
                  "runtime_executes_reported_launch_without_other_configuration_changes"]}

    def unknown(reason):
        result["reason"] = reason
        return result

    if not all(isinstance(value, dict) for value in (chain, site, integer_types, axis_binding)):
        return unknown("inputs_not_objects")
    try:
        result["input_sha256"] = hashlib.sha256(json.dumps([chain, site, integer_types, axis_binding],
            sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    except (TypeError, ValueError, RecursionError):
        return unknown("input_hash_unsupported")
    if axis_binding.get("schema_version") != "launch-axis-assumptions/v1":
        return unknown("axis_binding_schema_missing")
    if chain.get("status") != "recovered" or not isinstance(chain.get("function_id"), str) or not chain["function_id"] or chain["function_id"] != site.get("kernel_declaration_id"):
        return unknown("chain_or_kernel_binding_missing")
    if not isinstance(site.get("launch_id"), str) or not site["launch_id"]:
        return unknown("launch_id_missing")
    if axis_binding.get("launch_id") != site["launch_id"]:
        return unknown("axis_launch_binding_mismatch")
    block = chain.get("block_threads")
    if type(block) is not int or not 1 <= block <= 1024:
        return unknown("block_model_unsupported")
    bits = chain.get("int_bits")
    integer = integer_types.get("int")
    if (type(bits) is not int or not 2 <= bits <= 128 or not isinstance(integer, dict)
            or type(integer.get("bits")) is not int or integer["bits"] != bits
            or integer.get("signed") is not True):
        return unknown("analysis_integer_abi_mismatch")
    constructors = site.get("configuration_constructor_arguments")
    if not isinstance(constructors, list) or len(constructors) != 2 or not isinstance(constructors[1], dict):
        return unknown("block_constructor_missing")
    constructor = constructors[1]
    identifier = constructor.get("constructor_declaration_id")
    if not isinstance(identifier, str) or not identifier or axis_binding.get("constructor_declaration_id") != identifier:
        return unknown("axis_constructor_binding_mismatch")
    axes = axis_binding.get("fields")
    if not isinstance(axes, dict) or set(axes) != {"x", "y", "z"} or any(not isinstance(v, str) or not v for v in axes.values()) or len(set(axes.values())) != 3:
        return unknown("axis_field_binding_invalid")
    fields = check_fields(constructor, constructor.get("field_initialization"), integer_types)
    result["field_check"] = fields
    if fields["status"] != "checked":
        result["status"] = fields["status"]
        result["reason"] = "block_field_values_not_checked"
        return result
    values = {item["field_id"]: item["value"] for item in fields["fields"]}
    if set(values) != set(axes.values()):
        return unknown("axis_fields_do_not_cover_record")
    dimensions = {axis: values[field] for axis, field in axes.items()}
    result.update(dimensions=dimensions, expected_dimensions={"x": block, "y": 1, "z": 1})
    if dimensions != result["expected_dimensions"]:
        result.update(status="rejected", reason="block_dimensions_disagree_with_one_dimensional_model")
    else:
        result["status"] = "checked"
    return result
