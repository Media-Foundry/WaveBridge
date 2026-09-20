import unittest

from wavebridge.analysis.declaration_index import build


def report(*roots, status="collected", schema="clang-ast-source/v1"):
    return {"schema_version": schema, "status": status, "ast_roots": list(roots)}


def decl(clang_id, name, kind="FunctionDecl", **extra):
    return {"id": clang_id, "kind": kind, "name": name,
            "range": {"begin": {"line": 1}, "end": {"line": 1}}, **extra}


def reference(node_id, target_id, name="same"):
    return {"id": node_id, "kind": "DeclRefExpr", "range": {},
            "referencedDecl": {"id": target_id, "kind": "FunctionDecl", "name": name}}


class DeclarationIndexTests(unittest.TestCase):
    def test_same_name_different_id_uses_exact_id(self):
        first, second = decl("a", "same"), decl("b", "same", inner=[{"kind": "CompoundStmt"}])
        root = {"kind": "TranslationUnitDecl", "inner": [first, second, reference("r", "a")]}
        result = build(report(root))
        resolved = result["references"][0]
        self.assertEqual(resolved["target_clang_id"], "a")
        self.assertFalse(resolved["target_body_present"])

    def test_reference_stub_is_not_a_complete_declaration(self):
        root = {"kind": "FunctionDecl", "inner": [reference("r", "missing")]}
        result = build(report(root))
        self.assertFalse(result["references"][0]["complete_declaration_node_found"])
        self.assertEqual(result["unresolved"][0]["reason"], "no_exact_declaration_node_in_root")

    def test_duplicate_ids_in_different_roots_are_isolated(self):
        root0 = {"kind": "TranslationUnitDecl", "inner": [decl("same", "left"),
                                                               reference("r", "same")]}
        root1 = {"kind": "TranslationUnitDecl", "inner": [decl("same", "right"),
                                                               reference("r", "same")]}
        result = build(report(root0, root1))
        self.assertEqual([item["target_name"] for item in result["references"]], ["left", "right"])
        self.assertNotEqual(result["references"][0]["target_declaration_id"],
                            result["references"][1]["target_declaration_id"])

    def test_forward_declaration_previous_chain_is_not_followed(self):
        forward = decl("forward", "work")
        definition = decl("definition", "work", previousDecl="forward",
                          inner=[{"kind": "CompoundStmt"}])
        root = {"kind": "TranslationUnitDecl", "inner": [forward, definition,
                                                               reference("r", "forward", "work")]}
        result = build(report(root))
        resolved = result["references"][0]
        self.assertTrue(resolved["complete_declaration_node_found"])
        self.assertFalse(resolved["target_body_present"])
        self.assertFalse(resolved["previous_decl_followed"])
        definition_fact = next(item for item in result["declarations"]
                               if item["clang_id"] == "definition")
        self.assertTrue(definition_fact["previous_decl_present"])
        self.assertFalse(definition_fact["previous_decl_followed"])

    def test_initializer_and_member_reference_are_recorded(self):
        variable = decl("field", "value", kind="FieldDecl", init="c",
                        inner=[{"kind": "IntegerLiteral"}])
        member = {"id": "m", "kind": "MemberExpr", "referencedMemberDecl": "field",
                  "range": {"begin": {}, "end": {}}}
        root = {"kind": "TranslationUnitDecl", "inner": [variable, member]}
        result = build(report(root))
        self.assertTrue(result["references"][0]["target_initializer_present"])
        self.assertEqual(result["references"][0]["reference_kind"], "referencedMemberDecl")

    def test_invalid_schema_status_or_roots_are_rejected(self):
        for value in (report({}, schema="future/v2"), report({}, status="compile_failed"),
                      {"schema_version": "clang-ast-source/v1", "status": "collected",
                       "ast_roots": [1]}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build(value)


if __name__ == "__main__":
    unittest.main()
