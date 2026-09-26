"""Restricted scalar-expression no-write check, not a value or bounds proof."""
import re

from wavebridge.verification.builtin_calls import _children, _Unknown
from wavebridge.verification.getter_returns import _hash

MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000
FUNCTION_KINDS = {"FunctionDecl", "CXXMethodDecl", "CXXConstructorDecl", "CXXDestructorDecl"}


def _type(node):
    info = node.get("type")
    if not isinstance(info, dict):
        raise _Unknown("type_evidence_missing")
    if "typeAliasDeclId" in info and "desugaredQualType" not in info:
        raise _Unknown("alias_type_not_resolved")
    spelling = info.get("desugaredQualType", info.get("qualType"))
    if not isinstance(spelling, str) or not spelling:
        raise _Unknown("type_evidence_missing")
    return spelling


def _object_type(spelling):
    match = re.fullmatch(r"(const )?(float|int|unsigned int|bool)((?:\[[1-9][0-9]{0,8}\]){0,8})", spelling)
    if not match:
        raise _Unknown("object_type_unsupported")
    return (match[1] or "") + match[2], re.findall(r"\[[0-9]+\]", match[3])


def check_no_memory_write(root, expression_id, *, max_ast_nodes=None,
                          allow_constant_globals=False, allow_integer_bitwise=False):
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result = {"schema_version": "scalar-expression-no-memory-write/v1", "status": "unknown", "reason": None,
              "scope": "explicit_source_memory_writes_in_one_restricted_scalar_expression",
              "source_program_checked": False, "deployable": False, "value_semantics": "not_established",
              "numeric_contract_checked": False, "read_declaration_ids": [],
              "assumptions": ["AST faithfully describes one valid translation unit",
                              "referenced objects are initialized, alive and visible before this evaluation",
                              "indices and arithmetic are defined and evaluation completes normally",
                              "asynchronous or signal-handler effects are excluded"],
              "limitations": ["initialization history, bounds, overflow and lifetime are not checked",
                              "not purity, FP-environment, exact value or machine-code equivalence",
                              "enclosing call, wrapper body and loop are excluded"],
              "budget": {"max_ast_nodes": budget, "max_expression_depth": 64, "max_array_dimensions": 8}}
    try:
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                not isinstance(expression_id, str) or not expression_id or
                type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES or
                type(allow_constant_globals) is not bool or type(allow_integer_bitwise) is not bool):
            raise _Unknown("invalid_inputs_or_budget")
        index, automatic, pending, count = {}, set(), [(root, False)], 0
        while pending:
            node, in_body = pending.pop()
            count += 1
            if count > budget:
                raise _Unknown("ast_node_budget_exceeded")
            if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
                raise _Unknown("malformed_ast")
            identifier = node.get("id")
            if isinstance(identifier, str) and identifier:
                index.setdefault(identifier, []).append(node)
                if (node.get("kind") == "VarDecl" and in_body and
                        node.get("storageClass") in (None, "auto", "register") and
                        node.get("tls") is None and node.get("thread_local") is None):
                    automatic.add(identifier)
            function = node.get("kind") in FUNCTION_KINDS
            for child in node.get("inner", []):
                pending.append((child, child.get("kind") == "CompoundStmt" if function and isinstance(child, dict)
                                else False if function else in_body))

        def unique(identifier):
            values = index.get(identifier, [])
            if len(values) != 1:
                raise _Unknown("selected_identity_not_unique")
            return values[0]

        reads = set()

        def prepare(node, depth, category):
            if depth > 64:
                raise _Unknown("expression_depth_budget_exceeded")
            identifier = node.get("id")
            if not isinstance(identifier, str) or not identifier or unique(identifier) is not node:
                raise _Unknown("expression_identity_missing_or_conflicting")
            if node.get("valueCategory") != category:
                raise _Unknown("expression_category_mismatch")
            return _type(node), _children(node)

        def lvalue(node, depth):
            spelling, children = prepare(node, depth, "lvalue")
            base, dimensions = _object_type(spelling)
            if node.get("kind") == "ParenExpr" and len(children) == 1:
                if lvalue(children[0], depth + 1) != (base, dimensions):
                    raise _Unknown("paren_type_mismatch")
            elif node.get("kind") == "ConditionalOperator" and len(children) == 3:
                if (dimensions or value(children[0], depth + 1) != "bool" or
                        any(lvalue(child, depth + 1) != (base, dimensions) for child in children[1:])):
                    raise _Unknown("conditional_lvalue_type_mismatch")
            elif node.get("kind") == "DeclRefExpr":
                ref = node.get("referencedDecl")
                if children or not isinstance(ref, dict) or not isinstance(ref.get("id"), str) or not ref["id"]:
                    raise _Unknown("reference_not_plain_declaration")
                declaration = unique(ref["id"])
                kind = declaration.get("kind")
                constant_global = False
                if allow_constant_globals and kind == "VarDecl" and spelling in {"const int", "const unsigned int"}:
                    initializers = [n for n in _children(declaration) if n.get("kind") not in
                                    {"CUDADeviceAttr", "CUDAConstantAttr"}]
                    constant_global = (all(declaration.get(k) is None for k in
                                          ("tls", "tlsKind", "thread_local", "threadLocal")) and
                                       len(initializers) == 1 and initializers[0].get("kind") == "IntegerLiteral" and
                                       not _children(initializers[0]) and
                                       _type(initializers[0]) == spelling.removeprefix("const "))
                if (kind not in {"VarDecl", "ParmVarDecl"} or ref.get("kind") != kind or
                        _type(ref) != spelling or _type(declaration) != spelling or
                        (kind == "VarDecl" and ref["id"] not in automatic and not constant_global) or
                        (kind == "ParmVarDecl" and dimensions)):
                    raise _Unknown("reference_not_supported_local_or_parameter")
                reads.add(ref["id"])
            elif node.get("kind") == "ArraySubscriptExpr" and len(children) == 2:
                decay, subscript = children
                pointer, operands = prepare(decay, depth + 1, "prvalue")
                if (decay.get("kind") != "ImplicitCastExpr" or decay.get("castKind") != "ArrayToPointerDecay" or
                        len(operands) != 1):
                    raise _Unknown("array_base_not_direct_array_decay")
                source_base, source_dimensions = lvalue(operands[0], depth + 2)
                if not source_dimensions:
                    raise _Unknown("array_base_not_array")
                remaining = source_dimensions[1:]
                expected_pointer = source_base + (" (*)" + "".join(remaining) if remaining else " *")
                if pointer != expected_pointer or (base, dimensions) != (source_base, remaining):
                    raise _Unknown("array_element_type_mismatch")
                if value(subscript, depth + 1) != "int":
                    raise _Unknown("array_index_not_int")
            else:
                raise _Unknown("unsupported_lvalue_expression")
            return base, dimensions

        def value(node, depth):
            spelling, children = prepare(node, depth, "prvalue")
            if spelling not in {"float", "int", "unsigned int", "bool"}:
                raise _Unknown("scalar_value_type_unsupported")
            kind = node.get("kind")
            if kind == "ParenExpr" and len(children) == 1:
                if value(children[0], depth + 1) != spelling:
                    raise _Unknown("paren_type_mismatch")
            elif kind == "ImplicitCastExpr" and node.get("castKind") == "LValueToRValue" and len(children) == 1:
                base, dimensions = lvalue(children[0], depth + 1)
                if dimensions or base.removeprefix("const ") != spelling:
                    raise _Unknown("scalar_load_type_mismatch")
            elif kind == "ConditionalOperator" and len(children) == 3:
                if (value(children[0], depth + 1) != "bool" or
                        any(value(child, depth + 1) != spelling for child in children[1:])):
                    raise _Unknown("conditional_value_type_mismatch")
            elif kind == "BinaryOperator" and node.get("opcode") in {"<", "<=", ">", ">=", "==", "!="} and len(children) == 2:
                operands = [value(child, depth + 1) for child in children]
                if spelling != "bool" or operands[0] not in {"int", "unsigned int", "float"} or operands[0] != operands[1]:
                    raise _Unknown("comparison_operand_type_mismatch")
            elif (allow_integer_bitwise and kind == "BinaryOperator" and
                  node.get("opcode") in {"&", "|", "^", "<<", ">>"} and len(children) == 2):
                if spelling not in {"int", "unsigned int"} or any(value(child, depth + 1) != spelling for child in children):
                    raise _Unknown("bitwise_operand_type_mismatch")
            elif kind == "BinaryOperator" and node.get("opcode") in {"+", "-", "*", "/", "%"} and len(children) == 2:
                if spelling == "bool":
                    raise _Unknown("arithmetic_type_unsupported")
                if node.get("opcode") == "%" and spelling not in {"int", "unsigned int"}:
                    raise _Unknown("remainder_not_int")
                if any(value(child, depth + 1) != spelling for child in children):
                    raise _Unknown("arithmetic_operand_type_mismatch")
            elif kind == "UnaryOperator" and node.get("opcode") in {"+", "-"} and len(children) == 1:
                if spelling == "bool" or value(children[0], depth + 1) != spelling:
                    raise _Unknown("unary_operand_type_mismatch")
            elif kind == "CXXBoolLiteralExpr" and not children:
                if spelling != "bool" or type(node.get("value")) is not bool:
                    raise _Unknown("literal_type_or_value_missing")
            elif kind in {"IntegerLiteral", "FloatingLiteral"} and not children:
                if ((spelling not in {"int", "unsigned int"} if kind == "IntegerLiteral" else spelling != "float") or
                        not isinstance(node.get("value"), str)):
                    raise _Unknown("literal_type_or_value_missing")
            else:
                raise _Unknown("unsupported_scalar_expression")
            return spelling

        returned_type = value(unique(expression_id), 0)
        result.update(status="checked", result_type=returned_type, read_declaration_ids=sorted(reads),
                      input_sha256={"root": _hash(root), "expression_id": _hash(expression_id)},
                      conclusion={"status": "conditional", "property": "no_memory_write",
                                  "subject": "exact_scalar_expression", "expression_id": expression_id})
    except _Unknown as error:
        result["reason"] = str(error)
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "unsupported_input_representation"
    return result
