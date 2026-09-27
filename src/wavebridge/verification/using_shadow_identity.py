"""Restricted identity lookup for Clang's expanded function using references.

This is not general AST deduplication. One ordinary occurrence must exist and
every additional occurrence must belong to an independently matched expansion
of that function under an implicit UsingShadowDecl. The original AST is kept.
"""
from wavebridge.verification.getter_returns import _hash

IDENTITY_POLICY = "using-shadow-function-reference/v1"


class IdentityUnknown(ValueError):
    pass


class UsingShadowIndex:
    def __init__(self, root, budget):
        self.nodes, self.groups, self.observations = {}, [], []
        self.validated, self.representatives = set(), {}
        pending, count = [(root, None)], 0
        while pending:
            node, group = pending.pop()
            count += 1
            if count > budget:
                raise IdentityUnknown("ast_node_budget_exceeded")
            if (not isinstance(node, dict) or not isinstance(node.get("inner", []), list) or
                    any(not isinstance(child, dict) for child in node.get("inner", []))):
                raise IdentityUnknown("malformed_ast")
            identifier = node.get("id")
            if isinstance(identifier, str) and identifier:
                self.nodes.setdefault(identifier, []).append((node, group))
            children = node.get("inner", [])
            if (node.get("kind") == "UsingShadowDecl" and len(children) == 1 and
                    children[0].get("kind") == "FunctionDecl"):
                new_group = len(self.groups)
                self.groups.append((node, children[0], group))
                pending.append((children[0], new_group))
            else:
                pending.extend((child, group) for child in children)

    @staticmethod
    def _same_declaration(ordinary, reference):
        if ordinary == reference:
            return "exact"
        # Only the root declaration's direct loc.file omission is supported.
        # Preserve offsets, ranges, macro locations and every descendant field.
        left, right = ordinary.get("loc"), reference.get("loc")
        if not isinstance(left, dict) or not isinstance(right, dict):
            raise IdentityUnknown("using_shadow_declaration_conflict")
        if ("file" in left) == ("file" in right):
            raise IdentityUnknown("using_shadow_declaration_conflict")
        explicit = left if "file" in left else right
        if (not isinstance(explicit["file"], str) or not explicit["file"] or
                any(type(explicit.get(key)) is not int or explicit[key] < minimum
                    for key, minimum in (("offset", 0), ("col", 1), ("tokLen", 1)))):
            raise IdentityUnknown("using_shadow_location_evidence_missing")
        if ({key: value for key, value in left.items() if key != "file"} !=
                {key: value for key, value in right.items() if key != "file"} or
                {key: value for key, value in ordinary.items() if key != "loc"} !=
                {key: value for key, value in reference.items() if key != "loc"}):
            raise IdentityUnknown("using_shadow_declaration_conflict")
        return "root_loc_file_omission_only"

    def _validate_group(self, group):
        if group in self.validated:
            return
        shadow, reference, enclosing = self.groups[group]
        if enclosing is not None:
            raise IdentityUnknown("nested_using_shadow_expansion_unsupported")
        shadow_occurrences = self.nodes.get(shadow.get("id"), [])
        if (len(shadow_occurrences) != 1 or shadow_occurrences[0][0] is not shadow or
                shadow.get("isImplicit") is not True):
            raise IdentityUnknown("using_shadow_identity_not_unique_or_implicit")
        target = shadow.get("target")
        expected = {key: reference.get(key) for key in ("id", "kind", "name", "type")}
        if (target != expected or expected["kind"] != "FunctionDecl" or
                not isinstance(expected["name"], str) or not expected["name"] or
                not isinstance(expected["type"], dict)):
            raise IdentityUnknown("using_shadow_target_mismatch")
        ordinary = [node for node, owner in self.nodes.get(reference.get("id"), []) if owner is None]
        if len(ordinary) != 1 or ordinary[0].get("kind") != "FunctionDecl":
            raise IdentityUnknown("using_shadow_ordinary_declaration_not_unique")
        original = ordinary[0]
        match = self._same_declaration(original, reference)
        pairs = [(original, reference)]
        while pairs:
            left, right = pairs.pop()
            if left.get("kind") == "UsingShadowDecl" and left.get("inner"):
                raise IdentityUnknown("nested_using_shadow_expansion_unsupported")
            self.representatives[id(right)] = left
            pairs.extend(zip(left.get("inner", []), right.get("inner", [])))
        self.validated.add(group)
        self.observations.append({"shadow_declaration_id": shadow["id"],
                                  "target_declaration_id": original["id"], "match": match,
                                  "ordinary_sha256": _hash(original),
                                  "reference_expansion_sha256": _hash(reference)})

    def unique(self, identifier):
        occurrences = self.nodes.get(identifier, []) if isinstance(identifier, str) else []
        ordinary = [node for node, group in occurrences if group is None]
        if len(ordinary) != 1:
            raise IdentityUnknown("ordinary_ast_identity_not_unique")
        selected = ordinary[0]
        for node, group in occurrences:
            if group is not None:
                self._validate_group(group)
                if self.representatives.get(id(node)) is not selected:
                    raise IdentityUnknown("using_shadow_descendant_identity_conflict")
        return selected
