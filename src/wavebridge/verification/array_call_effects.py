"""Restricted array-call write footprint; unresolved calls never imply purity."""
import re

from wavebridge.analysis.column_loops import ASSIGNMENT_OPCODES, _hinted_loop, _Unknown as BodyUnknown
from wavebridge.verification.builtin_calls import _Unknown
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.scalar_expression_effects import _type


def check(root, call_id, protected_declaration_id, *, max_ast_nodes=None):
    budget = 1_000_000 if max_ast_nodes is None else max_ast_nodes
    result = {"schema_version": "array-call-write-footprint/v1", "status": "unknown", "reason": None,
              "scope": "restricted_single_array_call_preserves_distinct_caller_local",
              "binding": None, "explicit_writes": [], "pending_effects": [],
              "explicit_write_targets_checked": False, "protected_storage_preserved": False,
              "source_program_checked": False, "deployable": False, "array_bounds_checked": False,
              "assumptions": ["AST is faithful, source execution is valid and selected call returns normally",
                              "caller array and protected automatic object are alive and distinct at the call",
                              "every array access stays within its live object; no asynchronous interference"],
              "limitations": ["not array-bounds, value, reduction or communication correctness",
                              "explicit writes alone do not account for pending calls or object lifecycle effects"],
              "budget": {"max_ast_nodes": budget, "max_array_extent": 4096}}
    try:
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                any(not isinstance(value, str) or not value for value in (call_id, protected_declaration_id)) or
                type(budget) is not int or not 1 <= budget <= 10_000_000):
            raise _Unknown("invalid_inputs_or_budget")
        index, functions, pending, count = {}, [], [root], 0
        while pending:
            node = pending.pop()
            count += 1
            if count > budget:
                raise _Unknown("ast_node_budget_exceeded")
            if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
                raise _Unknown("malformed_ast")
            if isinstance(node.get("id"), str):
                index.setdefault(node["id"], []).append(node)
            if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"}:
                functions.append(node)
            pending.extend(node.get("inner", []))

        def exact(identifier):
            nodes = index.get(identifier, [])
            if len(nodes) != 1:
                raise _Unknown("declaration_or_expression_not_unique")
            return nodes[0]

        def children(node):
            items = node.get("inner", [])
            if any(not isinstance(item, dict) or not item for item in items):
                raise _Unknown("unsupported_empty_expression_operand")
            return items

        def automatic(node):
            return (node.get("kind") == "VarDecl" and node.get("storageClass") in (None, "auto", "register")
                    and all(node.get(key) is None for key in ("tls", "tlsKind", "thread_local", "threadLocal"))
                    and not any(str(c.get("kind", "")).endswith("Attr") for c in node.get("inner", [])))

        def ref(node, identifier=None):
            if node.get("kind") != "DeclRefExpr" or children(node):
                raise _Unknown("not_plain_declaration_reference")
            referenced = node.get("referencedDecl", {})
            declaration = exact(referenced.get("id"))
            if (referenced.get("kind") != declaration.get("kind") or
                    _type(referenced) != _type(declaration) or _type(node) != _type(declaration) or
                    (identifier is not None and referenced.get("id") != identifier)):
                raise _Unknown("reference_declaration_mismatch")
            return declaration

        call = exact(call_id)
        parts = children(call)
        if call.get("kind") != "CallExpr" or _type(call) != "void" or len(parts) != 2:
            raise _Unknown("unsupported_call_signature")
        decay, argument = parts
        if (decay.get("kind") != "ImplicitCastExpr" or decay.get("castKind") != "FunctionToPointerDecay"
                or len(children(decay)) != 1 or _type(decay) != "void (*)(float *)"):
            raise _Unknown("callee_not_direct_function_decay")
        callee = ref(children(decay)[0])
        if callee.get("kind") != "FunctionDecl" or _type(callee) != "void (float *)" or callee.get("variadic"):
            raise _Unknown("unsupported_callee_declaration")
        parameters = [n for n in children(callee) if n.get("kind") == "ParmVarDecl"]
        bodies = [n for n in children(callee) if n.get("kind") == "CompoundStmt"]
        if len(parameters) != 1 or _type(parameters[0]) != "float *" or len(bodies) != 1:
            raise _Unknown("callee_parameter_or_body_unsupported")
        parameter = parameters[0]
        exact(parameter.get("id"))
        if (argument.get("kind") != "ImplicitCastExpr" or argument.get("castKind") != "ArrayToPointerDecay"
                or _type(argument) != "float *" or len(children(argument)) != 1):
            raise _Unknown("argument_not_direct_array_decay")
        array = ref(children(argument)[0])
        extent = re.fullmatch(r"float\[(\d+)\]", _type(array) or "")
        protected = exact(protected_declaration_id)
        if (not automatic(array) or not extent or not 1 <= int(extent[1]) <= 4096 or
                not automatic(protected) or _type(protected) not in {"int", "const int"} or
                array.get("id") == protected_declaration_id):
            raise _Unknown("caller_storage_not_distinct_supported_automatic_objects")
        contexts = []
        for function in functions:
            for body in function.get("inner", []):
                if body.get("kind") != "CompoundStmt":
                    continue
                statements = body.get("inner", [])
                positions = [i for i, n in enumerate(statements) if n is call]
                declarations = {d.get("id"): i for i, n in enumerate(statements) if n.get("kind") == "DeclStmt"
                                for d in n.get("inner", []) if d.get("kind") == "VarDecl"}
                if (len(positions) == 1 and all(key in declarations and declarations[key] < positions[0]
                                              for key in (array["id"], protected_declaration_id))):
                    contexts.append(function)
        if len(contexts) != 1:
            raise _Unknown("call_and_objects_not_ordered_in_same_function_body")
        result["binding"] = {"caller_id": contexts[0].get("id"), "call_id": call_id, "callee_id": callee["id"],
                             "parameter_id": parameter["id"], "parameter_index": 0,
                             "array_declaration_id": array["id"], "array_extent": int(extent[1]),
                             "protected_declaration_id": protected_declaration_id}
        body = bodies[0]
        locals_, pending = {}, [body]
        while pending:
            node = pending.pop()
            if node.get("kind") == "VarDecl":
                if not automatic(node) or exact(node.get("id")) is not node:
                    raise _Unknown("helper_local_storage_unsupported")
                ty = _type(node) or ""
                if "&" in ty or "*" in ty or "volatile" in ty or "[" in ty:
                    raise _Unknown("helper_local_alias_or_type_unsupported")
                locals_[node["id"]] = node
                if ty not in {"int", "const int", "float", "const float", "bool", "const bool"}:
                    result["pending_effects"].append({"kind": "local_object_lifecycle", "id": node["id"]})
            pending.extend(node.get("inner", []))

        def storage(node):
            while node.get("kind") == "ParenExpr" and len(children(node)) == 1:
                node = children(node)[0]
            if node.get("kind") == "DeclRefExpr":
                declaration = ref(node)
                if declaration.get("id") not in locals_ or _type(declaration) not in {"int", "float", "bool"}:
                    raise _Unknown("write_not_supported_helper_local")
                return {"kind": "helper_local", "declaration_id": declaration["id"]}
            if node.get("kind") == "ArraySubscriptExpr" and len(children(node)) == 2 and _type(node) == "float":
                base = children(node)[0]
                if (base.get("kind") != "ImplicitCastExpr" or base.get("castKind") != "LValueToRValue" or
                        _type(base) != "float *" or len(children(base)) != 1):
                    raise _Unknown("write_array_base_unsupported")
                ref(children(base)[0], parameter["id"])
                return {"kind": "parameter_array_element", "declaration_id": parameter["id"],
                        "caller_array_declaration_id": array["id"], "index_ast": children(node)[1]}
            raise _Unknown("unsupported_write_storage_target")

        allowed = {"CompoundStmt", "DeclStmt", "VarDecl", "DeclRefExpr", "ImplicitCastExpr", "ParenExpr",
                   "BinaryOperator", "CompoundAssignOperator", "UnaryOperator", "ArraySubscriptExpr",
                   "IntegerLiteral", "FloatingLiteral", "CXXBoolLiteralExpr", "ConditionalOperator",
                   "IfStmt", "NullStmt", "ReturnStmt"}
        calls = {"CallExpr", "CXXMemberCallExpr", "CXXOperatorCallExpr", "CXXConstructExpr", "CXXDefaultArgExpr"}
        pending = [(body, [])]
        while pending:
            node, path = pending.pop()
            kind = node.get("kind")
            if kind == "AttributedStmt":
                target = _hinted_loop(node)
                pending.append((target, path + [len(node["inner"]) - 1]))
                continue
            if kind == "ForStmt":
                parts = node.get("inner", [])
                if len(parts) != 5 or parts[1] != {}:
                    raise _Unknown("helper_loop_shape_unsupported")
                pending.extend((parts[i], path + [i]) for i in reversed((0, 2, 3, 4)))
                continue
            if kind == "SubstNonTypeTemplateParmExpr":
                parts = children(node)
                if (not parts or parts[-1].get("kind") not in {"IntegerLiteral", "CXXBoolLiteralExpr"} or
                        any(n.get("kind") != "NonTypeTemplateParmDecl" for n in parts[:-1])):
                    raise _Unknown("template_replacement_unsupported")
                pending.append((parts[-1], path + [len(parts) - 1]))
                continue
            if kind in calls:
                result["pending_effects"].append({"kind": kind, "id": node.get("id"), "callee_body_child_path": path})
            elif kind not in allowed:
                raise _Unknown("unsupported_helper_effect_node:" + str(kind))
            if kind == "UnaryOperator" and node.get("opcode") in {"&", "*"}:
                raise _Unknown("address_escape_or_dereference_unsupported")
            if kind == "VarDecl" and node.get("init") is not None:
                result["explicit_writes"].append({"expression_id": node.get("id"), "opcode": "initialization",
                                                  "callee_body_child_path": path,
                                                  "target": {"kind": "helper_local", "declaration_id": node["id"]}})
            mutation = ((kind in {"BinaryOperator", "CompoundAssignOperator"} and node.get("opcode") in ASSIGNMENT_OPCODES)
                        or (kind == "UnaryOperator" and node.get("opcode") in {"++", "--"}))
            if mutation:
                operands = children(node)
                target = storage(operands[0])
                result["explicit_writes"].append({"expression_id": node.get("id"), "opcode": node.get("opcode"),
                                                  "callee_body_child_path": path, "target": target})
            pending.extend((child, path + [i]) for i, child in reversed(list(enumerate(children(node)))))
        result.update(explicit_write_targets_checked=True,
                      input_sha256={"root": _hash(root), "call_id": _hash(call_id),
                                    "protected_declaration_id": _hash(protected_declaration_id)})
        if result["pending_effects"]:
            result["reason"] = "unresolved_call_or_lifecycle_effects"
        else:
            result.update(status="checked", protected_storage_preserved=True)
    except BodyUnknown as error:
        result["reason"] = error.reason
    except _Unknown as error:
        result["reason"] = str(error)
    except (TypeError, ValueError, KeyError, IndexError, RecursionError):
        result["reason"] = "unsupported_input_representation"
    return result
