"""Compare typed accumulator/loop templates, never infer equal entry values."""

from wavebridge.analysis.local_contribution import recover
from wavebridge.analysis.integer_constants import evaluate
from wavebridge.verification.getter_returns import _hash


class _Unknown(Exception):
    pass


KINDS = {"VarDecl", "DeclStmt", "ForStmt", "CompoundStmt", "DeclRefExpr",
         "ImplicitCastExpr", "ParenExpr", "IntegerLiteral", "FloatingLiteral",
         "BinaryOperator", "CompoundAssignOperator", "ArraySubscriptExpr"}
METADATA = {"id", "name", "loc", "range", "isUsed", "isReferenced"}
FIELDS = {"kind", "type", "valueCategory", "opcode", "castKind", "value", "init",
          "computeLHSType", "computeResultType", "nonOdrUseReason", "storageClass",
          "tls", "constexpr", "fpoptions"}


def _snapshot(root, kernel, bits, budget):
    declarations = {}
    pending, count = [root], 0
    while pending:
        node = pending.pop()
        count += 1
        if count > budget:
            raise _Unknown("ast_node_budget_exceeded")
        if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
            raise _Unknown("malformed_ast")
        if str(node.get("kind", "")).endswith("Decl") and node.get("id"):
            declarations.setdefault(node["id"], []).append(node)
        pending.extend(node.get("inner", []))

    def declaration(identifier):
        found = declarations.get(identifier, [])
        if len(found) != 1:
            raise _Unknown("declaration_identity_not_unique")
        return found[0]

    function = declaration(kernel)
    if function.get("kind") != "FunctionDecl":
        raise _Unknown("not_ordinary_function")
    local = recover(root, kernel, bits)
    if local["status"] != "recovered":
        raise _Unknown("local_not_recovered:" + str(local["reason"]))
    loop = local["loop"]
    roles = {"accumulator": local["accumulator_declaration_id"],
             "loaded_value": local["value_declaration_id"],
             "induction": loop["induction"]["declaration_id"],
             "input": local["input_parameter_id"]}
    for role, field in (("start", "start"), ("bound", "bound")):
        item = loop[field]
        if item["kind"] in {"declaration_reference", "parameter"}:
            roles[role] = item["declaration_id"]
    if len(set(roles.values())) != len(roles):
        raise _Unknown("roles_not_injective")
    parameters = [n for n in function.get("inner", []) if n.get("kind") == "ParmVarDecl"]
    positions = {n["id"]: i for i, n in enumerate(parameters)}
    bindings = {}
    for role, identifier in roles.items():
        decl = declaration(identifier)
        info = decl.get("type")
        if not isinstance(info, dict) or not isinstance(info.get("qualType"), str):
            raise _Unknown("role_type_missing")
        if set(info) - {"qualType", "desugaredQualType"}:
            raise _Unknown("role_type_alias_or_metadata_unsupported")
        bindings[role] = {"declaration_id": identifier, "kind": decl["kind"], "type": info,
                          "parameter_position": positions.get(identifier)}
    reverse = {identifier: role for role, identifier in roles.items()}
    constants = {}

    def canonical(node, depth=0):
        if depth > 128:
            raise _Unknown("fragment_depth_exceeded")
        if not node:
            return {}
        kind = node.get("kind")
        if kind not in KINDS or set(node) - METADATA - FIELDS - {"inner", "referencedDecl"}:
            raise _Unknown("unsupported_fragment_kind_or_field")
        normalized = {key: value for key, value in node.items() if key in FIELDS}
        for key in ("type", "computeLHSType", "computeResultType"):
            if key in node:
                info = node[key]
                if (not isinstance(info, dict) or not isinstance(info.get("qualType"), str) or
                        set(info) - {"qualType", "desugaredQualType"}):
                    raise _Unknown("fragment_type_unsupported")
        if kind not in {"DeclStmt", "ForStmt", "CompoundStmt"} and "type" not in node:
            raise _Unknown("fragment_type_missing")
        if kind == "CompoundAssignOperator" and any(k not in node for k in ("computeLHSType", "computeResultType")):
            raise _Unknown("computation_type_missing")
        if kind == "VarDecl":
            role = reverse.get(node.get("id"))
            if role not in {"accumulator", "loaded_value", "induction"}:
                raise _Unknown("unbound_fragment_declaration")
            normalized["role"] = role
        if kind == "DeclRefExpr":
            stub = node.get("referencedDecl")
            if not isinstance(stub, dict) or set(stub) - {"id", "kind", "name", "type"}:
                raise _Unknown("unsupported_reference_stub")
            identifier = stub.get("id")
            decl = declaration(identifier)
            if stub.get("kind") != decl.get("kind") or stub.get("type") != decl.get("type"):
                raise _Unknown("reference_declaration_mismatch")
            if identifier in reverse:
                normalized["reference"] = {"role": reverse[identifier], "type": decl["type"]}
            else:
                constant = evaluate(root, identifier, bits)
                if constant.get("status") != "evaluated":
                    raise _Unknown("external_reference_not_resolved_constant")
                # The evaluator resolves dependencies recursively; validate every
                # observed declaration identity, not only the direct reference.
                for source in constant["sources"]:
                    declaration(source["declaration_id"])
                constants[identifier] = constant
                normalized["reference"] = {"constant": constant["value"], "type": decl["type"]}
        elif "referencedDecl" in node:
            raise _Unknown("unexpected_reference_field")
        if "inner" in node:
            normalized["inner"] = [canonical(child, depth + 1) for child in node["inner"]]
        return normalized

    bodies = [n for n in function.get("inner", []) if n.get("kind") == "CompoundStmt"]
    if len(bodies) != 1:
        raise _Unknown("body_not_unique")
    loops = [n for n in bodies[0].get("inner", []) if n.get("kind") == "ForStmt" and
             n.get("range") == loop["range"]]
    if len(loops) != 1:
        raise _Unknown("selected_loop_not_unique")
    template = {"accumulator": canonical(declaration(roles["accumulator"])),
                "loop": canonical(loops[0]),
                "roles": {role: {k: v for k, v in binding.items() if k != "declaration_id"}
                          for role, binding in bindings.items()}}
    return {"local_recovery": local, "role_bindings": bindings, "constants": constants,
            "consumer": local["consumer"], "template": template, "template_sha256": _hash(template)}


def compare(source_root, source_kernel, target_root, target_kernel, int_bits=32,
            *, max_ast_nodes=1_000_000):
    """Fresh typed structural comparison; prefix/entry values are not compared."""
    result = {"schema_version": "local-structure-comparison/v1", "status": "unknown", "reason": None,
              "scope": "automatic_accumulator_declaration_and_selected_loop_typed_AST_templates",
              "source_program_checked": False, "deployable": False,
              "local_structure_equal": None, "leaf_value_correspondence": "not_established",
              "entry_value_correspondence": "not_established", "consumer_correspondence": "not_established",
              "checks": {}, "remaining_obligations": ["prefix_and_entry_pointer_contents_start_bound_values",
                  "source_validity_aliasing_and_integer_iteration_domain",
                  "floating_point_environment_and_compilation_mode",
                  "consumer_binding_and_whole_kernel_source_target_relation"]}
    if (type(int_bits) is not int or not 2 <= int_bits <= 128 or type(max_ast_nodes) is not int or
            not 1 <= max_ast_nodes <= 10_000_000):
        result["reason"] = "invalid_limits"
        return result
    for side, root, kernel in (("source", source_root, source_kernel), ("target", target_root, target_kernel)):
        try:
            if not isinstance(root, dict) or not isinstance(kernel, str) or not kernel:
                raise _Unknown("invalid_inputs")
            snapshot = _snapshot(root, kernel, int_bits, max_ast_nodes)
            snapshot["input_sha256"] = _hash({"root": root, "kernel": kernel, "int_bits": int_bits})
            result["checks"][side] = snapshot
        except (_Unknown, RecursionError, TypeError, ValueError) as error:
            result["reason"] = side + ":" + str(error)
            return result
    equal = result["checks"]["source"]["template"] == result["checks"]["target"]["template"]
    result.update(status="evidence" if equal else "rejected", local_structure_equal=equal,
                  reason=None if equal else "typed_local_templates_differ_not_a_numeric_counterexample")
    return result
