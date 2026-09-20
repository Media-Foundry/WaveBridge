"""Bind a direct array argument; declaration extent is not runtime capacity proof."""
import re

from wavebridge.frontend.clang_ast import _walk
from wavebridge.analysis.local_contribution import _children, _direct_call, _Unknown


def recover(root, caller_id, callee_id, call_range, shared_parameter_id):
    result = {"schema_version": "source-array-binding/v1", "status": "unknown",
              "reason": None, "array_declaration_id": None, "parameter_id": shared_parameter_id,
              "argument_index": None, "storage_kind": "unknown", "extent_elements": None,
              "capacity_status": "not_established", "checked": False, "deployable": False,
              "aliasing": "not_established", "runtime_capacity": "not_established"}

    def unknown(reason):
        result["reason"] = reason
        return result

    if not isinstance(root, dict) or not isinstance(call_range, dict):
        return unknown("invalid_root_or_call_range")
    if any(not isinstance(value, str) or not value for value in (caller_id, callee_id, shared_parameter_id)):
        return unknown("invalid_declaration_id")
    definitions = {}
    for identifier in (caller_id, callee_id):
        matches = [node for node in _walk(root)
                   if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"}
                   and node.get("id") == identifier
                   and any(c.get("kind") == "CompoundStmt" for c in _children(node))]
        if len(matches) != 1:
            return unknown("function_definition_not_unique")
        definitions[identifier] = matches[0]
    parameters = [p for p in _children(definitions[callee_id]) if p.get("kind") == "ParmVarDecl"]
    positions = [i for i, p in enumerate(parameters) if p.get("id") == shared_parameter_id]
    if len(positions) != 1:
        return unknown("shared_parameter_not_unique")
    body = next(c for c in _children(definitions[caller_id]) if c.get("kind") == "CompoundStmt")
    calls = [node for node in _walk(body) if node.get("kind") == "CallExpr" and node.get("range") == call_range]
    if len(calls) != 1:
        return unknown("consumer_call_not_unique")
    try:
        target, arguments = _direct_call(calls[0])
    except _Unknown:
        return unknown("consumer_call_unsupported")
    if target != callee_id or len(arguments) != len(parameters):
        return unknown("consumer_signature_mismatch")
    position = positions[0]
    current = arguments[position]
    original = current
    decay_count = 0
    while current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
        children = _children(current)
        if len(children) != 1:
            return unknown("ambiguous_array_wrapper")
        if current.get("kind") == "ImplicitCastExpr":
            if current.get("castKind") != "ArrayToPointerDecay":
                return unknown("unsupported_array_conversion")
            decay_count += 1
        current = children[0]
    reference = current.get("referencedDecl", {})
    if (decay_count != 1 or current.get("kind") != "DeclRefExpr" or
            not isinstance(reference, dict) or reference.get("kind") != "VarDecl"):
        return unknown("argument_not_direct_array_decay")
    array_id = reference.get("id")
    if not isinstance(array_id, str) or not array_id:
        return unknown("invalid_array_declaration_id")
    # Only a direct declaration preceding this call in the caller's top-level body.
    declarations = []
    for statement in _children(body):
        if any(node is calls[0] for node in _walk(statement)):
            break
        if statement.get("kind") == "DeclStmt":
            declarations.extend(node for node in _children(statement)
                                if node.get("kind") == "VarDecl" and node.get("id") == array_id)
    if len(declarations) != 1:
        return unknown("preceding_local_array_not_unique")
    declaration = declarations[0]
    info = declaration.get("type", {})
    if not isinstance(info, dict):
        return unknown("unsupported_array_type")
    type_name = info.get("desugaredQualType", info.get("qualType", ""))
    if not isinstance(type_name, str):
        return unknown("unsupported_array_type")
    match = re.fullmatch(r"float\s*\[([0-9]{1,20})?\]", type_name)
    if not match:
        return unknown("unsupported_array_type")
    extent = int(match[1]) if match[1] else None
    if extent is not None and extent <= 0:
        return unknown("nonpositive_array_extent")
    shared = any(node.get("kind") == "CUDASharedAttr" for node in _children(declaration))
    external = declaration.get("storageClass") == "extern"
    result.update(status="recovered", argument_index=position, array_declaration_id=array_id,
                  argument_ast=original, declaration_range=declaration.get("range"),
                  declaration_type=info, shared_attribute_present=shared,
                  storage_class=declaration.get("storageClass"), extent_elements=extent,
                  capacity_status=("declared_static_extent" if extent is not None and not external else
                                   "launch_bytes_required" if shared else "external_allocation_required"),
                  storage_kind=("shared_static" if extent is not None and not external else "shared_dynamic") if shared else "not_proven_shared")
    return result
