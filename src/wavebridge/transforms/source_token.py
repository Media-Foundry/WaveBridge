"""Generate one byte-exact integer-token candidate without semantic selection.

This primitive deliberately does not decide what a declaration means.  A
higher layer must select the declaration, recollect the candidate AST, and run
independent checks.
"""

from __future__ import annotations

import hashlib
from typing import Any


SCHEMA_VERSION = "source-token-edit/v1"
DEFAULT_MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unknown(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "unknown",
        "reason": reason,
        "checked": False,
        "source_program_checked": False,
        "deployable": False,
    }


def _location(node: dict[str, Any], source_path: str) -> tuple[int, int]:
    location = node.get("range")
    if not isinstance(location, dict):
        raise ValueError("literal_source_range_missing")
    begin, end = location.get("begin"), location.get("end")
    if not isinstance(begin, dict) or not isinstance(end, dict):
        raise ValueError("literal_source_range_missing")
    # Expansion/spelling pairs and includedFrom describe macro/header tokens,
    # not a byte token owned by the supplied main-source buffer.
    forbidden = {"expansionLoc", "spellingLoc", "includedFrom"}
    if (forbidden.intersection(begin) or forbidden.intersection(end) or
            begin.get("isMacroArgExpansion") is not None or
            end.get("isMacroArgExpansion") is not None):
        raise ValueError("literal_not_direct_main_source_token")
    if ("file" in begin and begin.get("file") != source_path) or \
            ("file" in end and end.get("file") != source_path):
        raise ValueError("literal_explicit_file_not_main_source")
    offset, length = begin.get("offset"), begin.get("tokLen")
    if (type(offset) is not int or type(length) is not int or offset < 0 or length <= 0 or
            type(end.get("offset")) is not int or type(end.get("tokLen")) is not int or
            end["offset"] != offset or end["tokLen"] != length):
        raise ValueError("literal_source_range_not_one_exact_token")
    return offset, length


def edit(source: bytes, expected_source_sha256: str, root: object,
         declaration_id: str, target_integer: int, *, source_path: str,
         max_ast_nodes: int = DEFAULT_MAX_AST_NODES) -> dict[str, Any]:
    """Replace one selected literal token and return an unvalidated candidate.

    ``declaration_id`` is an identity selected by the caller.  This function
    checks only the declaration/token shape and byte binding; it does not infer
    a width, launch role, or any other program semantics.
    """
    if (not isinstance(source, bytes) or
            not isinstance(expected_source_sha256, str) or
            len(expected_source_sha256) != 64 or
            not isinstance(source_path, str) or not source_path or
            not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
            not isinstance(declaration_id, str) or not declaration_id or
            type(target_integer) is not int or not 0 <= target_integer <= 2_147_483_647 or
            type(max_ast_nodes) is not int or not 1 <= max_ast_nodes <= HARD_MAX_AST_NODES):
        return _unknown("invalid_inputs")
    source_hash = _sha256(source)
    if source_hash != expected_source_sha256.lower():
        return _unknown("source_sha256_mismatch")

    matches: list[dict[str, Any]] = []
    pending: list[object] = [root]
    nodes = 0
    while pending:
        node = pending.pop()
        nodes += 1
        if nodes > max_ast_nodes:
            return _unknown("ast_node_budget_exceeded")
        if not isinstance(node, dict):
            return _unknown("malformed_AST_node")
        if node.get("id") == declaration_id:
            matches.append(node)
        children = node.get("inner", [])
        if not isinstance(children, list):
            return _unknown("malformed_AST_children")
        pending.extend(children)
    if len(matches) != 1:
        return _unknown("declaration_id_not_unique")
    declaration = matches[0]
    if (declaration.get("kind") != "VarDecl" or
            declaration.get("constexpr") is not True or declaration.get("init") != "c" or
            declaration.get("storageClass") is not None or
            declaration.get("tls") is not None or declaration.get("tlsKind") is not None or
            declaration.get("isInvalidDecl") is not None):
        return _unknown("declaration_not_supported_constexpr_variable")
    declaration_location = declaration.get("loc")
    if (not isinstance(declaration_location, dict) or
            declaration_location.get("file") != source_path or
            type(declaration_location.get("offset")) is not int or
            declaration_location["offset"] < 0 or
            any(key in declaration_location for key in
                ("includedFrom", "expansionLoc", "spellingLoc", "isMacroArgExpansion"))):
        return _unknown("declaration_not_explicitly_bound_to_main_source")
    declaration_type = declaration.get("type")
    if (not isinstance(declaration_type, dict) or
            declaration_type.get("qualType") != "const int" or
            declaration_type.get("desugaredQualType", "const int") != "const int" or
            "typeAliasDeclId" in declaration_type):
        return _unknown("declaration_not_plain_const_int")

    children = declaration.get("inner", [])
    if not isinstance(children, list) or any(not isinstance(child, dict) or not child for child in children):
        return _unknown("declaration_children_malformed")
    expressions = [child for child in children
                   if not str(child.get("kind", "")).endswith("Attr")]
    attributes = [child for child in children
                  if str(child.get("kind", "")).endswith("Attr")]
    if (len(expressions) != 1 or any(attribute.get("kind") != "CUDAConstantAttr" or
                                     attribute.get("implicit") is not True or attribute.get("inner")
                                     for attribute in attributes)):
        return _unknown("initializer_not_single_literal_or_attribute_unsupported")
    literal = expressions[0]
    literal_type = literal.get("type")
    original = literal.get("value")
    if (literal.get("kind") != "IntegerLiteral" or literal.get("valueCategory") != "prvalue" or
            literal.get("inner") not in (None, []) or not isinstance(literal.get("id"), str) or
            not literal["id"] or not isinstance(literal_type, dict) or
            literal_type.get("qualType") != "int" or
            literal_type.get("desugaredQualType", "int") != "int" or
            "typeAliasDeclId" in literal_type or not isinstance(original, str) or
            len(original) > 10 or not original.isascii() or not original.isdecimal()):
        return _unknown("initializer_not_plain_integer_literal")
    original_value = int(original)
    if str(original_value) != original or not 0 <= original_value <= 2_147_483_647:
        return _unknown("initializer_integer_literal_not_canonical_signed32")
    try:
        offset, length = _location(literal, source_path)
    except ValueError as error:
        return _unknown(str(error))
    original_bytes = original.encode("ascii")
    if (length != len(original_bytes) or offset + length > len(source) or
            source[offset:offset + length] != original_bytes):
        return _unknown("literal_range_does_not_match_source_bytes")

    replacement = str(target_integer).encode("ascii")
    candidate = source[:offset] + replacement + source[offset + length:]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "generated_unvalidated_candidate",
        "reason": None,
        "checked": False,
        "source_program_checked": False,
        "deployable": False,
        "semantic_role": "not_established",
        "budget": {"max_ast_nodes": max_ast_nodes, "nodes_used": nodes},
        "source_sha256": source_hash,
        "candidate_sha256": _sha256(candidate),
        "source_path": source_path,
        "declaration_id": declaration_id,
        "literal_expression_id": literal["id"],
        "edit": {
            "byte_offset": offset,
            "original_byte_length": length,
            "replacement_byte_length": len(replacement),
            "original_token": original,
            "replacement_token": replacement.decode("ascii"),
        },
        "limitations": [
            "declaration_semantic_role_not_selected_or_checked",
            "candidate_AST_not_collected",
            "source_and_launch_relation_not_checked",
            "runtime_and_target_correctness_not_checked",
            "target_range_presumes_the_caller's_explicit_signed_32_bit_integer_model",
            "declaration_template_context_is_not_classified_by_this_primitive",
        ],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "generated_unvalidated_candidate",
        "reason": None,
        "candidate_source": candidate,
        "manifest": manifest,
        "checked": False,
        "source_program_checked": False,
        "deployable": False,
    }
