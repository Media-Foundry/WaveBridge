"""Check an integer field snapshot/counter/return suffix, not device API semantics."""
from wavebridge.verification.getter_returns import _hash


def check(root, function_id, *, max_ast_nodes=1_000_000):
    result = {"schema_version": "field-snapshot-return/v1", "status": "unknown", "reason": None,
              "scope": "returned_integer_equals_field_value_read_at_selected_suffix_assignment",
              "prefix_effects_checked": False, "field_value_initialized": False,
              "field_numeric_domain": None, "API_success_verified": False,
              "function_reachability_proved": False, "source_program_checked": False, "deployable": False,
              "assumptions": ["faithful valid C++ AST and ordinary sequential execution",
                  "execution reaches the selected suffix and returns normally",
                  "selected field is valid to read; counter increment has defined behavior",
                  "distinct selected global declarations denote distinct storage",
                  "no asynchronous interference, nonlocal jumps or lifetime replacement"],
              "limitations": ["not a proof of API success, initialized properties, device selection or field range",
                  "prefix calls, runtime linkage and whole-function safety are not checked"]}
    try:
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                not isinstance(function_id, str) or not function_id or type(max_ast_nodes) is not int or
                not 1 <= max_ast_nodes <= 10_000_000):
            raise ValueError("invalid_selection_or_budget")
        pending, index, parents, count = [(root, None)], {}, {}, 0
        while pending:
            node, parent = pending.pop(); count += 1
            if count > max_ast_nodes: raise ValueError("ast_node_budget_exceeded")
            if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
                raise ValueError("malformed_ast")
            index.setdefault(node.get("id"), []).append(node)
            parents[id(node)] = parent
            pending.extend((c, node) for c in node.get("inner", []))

        def unique(identifier):
            values = index.get(identifier, [])
            if not isinstance(identifier, str) or len(values) != 1:
                raise ValueError("identity_not_unique")
            return values[0]

        def children(node, kind, size=None):
            if node.get("kind") != kind or unique(node.get("id")) is not node:
                raise ValueError("shape_or_identity_unsupported")
            values = node.get("inner", [])
            if size is not None and len(values) != size: raise ValueError("arity_unsupported")
            return values

        def typed(node, category):
            if node.get("type") != {"qualType": "int"} or node.get("valueCategory") != category:
                raise ValueError("plain_int_type_required")

        function = unique(function_id)
        members = children(function, "FunctionDecl")
        bodies = [n for n in members if n.get("kind") == "CompoundStmt"]
        if (function.get("type") != {"qualType": "int ()"} or len(bodies) != 1 or
                any(n.get("kind") == "ParmVarDecl" for n in members)):
            raise ValueError("plain_zero_argument_function_required")
        body = bodies[0]
        statements = children(body, "CompoundStmt")
        if len(statements) < 4: raise ValueError("snapshot_suffix_missing")
        assignment, increment, returned = statements[-3:]
        lhs, rhs = children(assignment, "BinaryOperator", 2); typed(assignment, "lvalue")
        if assignment.get("opcode") != "=": raise ValueError("snapshot_not_assignment")

        def global_storage(node):
            children(node, "DeclRefExpr", 0); typed(node, "lvalue")
            reference = node.get("referencedDecl", {})
            declaration = unique(reference.get("id"))
            if (declaration.get("kind") != "VarDecl" or reference.get("kind") != "VarDecl" or
                    declaration.get("type") != {"qualType": "int"} or reference.get("type") != declaration["type"] or
                    parents[id(declaration)].get("kind") not in {"TranslationUnitDecl", "NamespaceDecl"} or
                    declaration.get("init") is None or
                    any(declaration.get(k) is not None for k in ("tls", "tlsKind", "thread_local", "threadLocal")) or
                    any(n.get("kind", "").endswith("Attr") for n in declaration.get("inner", []))):
                raise ValueError("plain_defined_global_int_required")
            return declaration

        snapshot = global_storage(lhs)
        member, = children(rhs, "ImplicitCastExpr", 1); typed(rhs, "prvalue")
        if rhs.get("castKind") != "LValueToRValue": raise ValueError("field_conversion_unsupported")
        base, = children(member, "MemberExpr", 1); typed(member, "lvalue")
        if member.get("isArrow") is not False: raise ValueError("direct_object_field_required")
        field = unique(member.get("referencedMemberDecl"))
        if field.get("kind") != "FieldDecl" or field.get("type") != {"qualType": "int"} or field.get("isBitfield"):
            raise ValueError("plain_int_field_required")
        children(base, "DeclRefExpr", 0)
        reference = base.get("referencedDecl", {})
        obj = unique(reference.get("id"))
        declaration_statement = parents[id(obj)]
        if (obj.get("kind") != "VarDecl" or reference.get("kind") != "VarDecl" or
                base.get("type") != obj.get("type") or reference.get("type") != obj.get("type") or
                base.get("valueCategory") != "lvalue" or obj.get("init") is None or
                obj.get("storageClass") not in (None, "auto", "register") or
                any(obj.get(k) is not None for k in ("tls", "tlsKind", "thread_local", "threadLocal")) or
                declaration_statement.get("kind") != "DeclStmt" or parents[id(declaration_statement)] is not body or
                statements.index(declaration_statement) >= len(statements) - 3):
            raise ValueError("field_base_not_prior_automatic_object")
        counter_ref, = children(increment, "UnaryOperator", 1)
        if increment.get("opcode") != "++" or type(increment.get("isPostfix")) is not bool:
            raise ValueError("counter_increment_unsupported")
        typed(increment, "prvalue" if increment["isPostfix"] else "lvalue")
        counter = global_storage(counter_ref)
        if counter["id"] == snapshot["id"]: raise ValueError("counter_overwrites_snapshot")
        read, = children(returned, "ReturnStmt", 1)
        ref, = children(read, "ImplicitCastExpr", 1); typed(read, "prvalue")
        if read.get("castKind") != "LValueToRValue" or global_storage(ref)["id"] != snapshot["id"]:
            raise ValueError("return_not_same_snapshot")
        result.update(status="checked", function_id=function_id,
                      snapshot_assignment_id=assignment["id"], field_read_id=rhs["id"],
                      object_declaration_id=obj["id"], field_declaration_id=field["id"],
                      snapshot_declaration_id=snapshot["id"], counter_declaration_id=counter["id"],
                      unchecked_prefix_statement_ids=[n.get("id") for n in statements[:-3]],
                      input_sha256={"root": _hash(root), "function": _hash(function_id)})
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        result["reason"] = str(error)
    return result
