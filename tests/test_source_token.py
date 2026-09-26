import copy
import hashlib
import unittest

from wavebridge.transforms.source_token import edit


def fixture(prefix=b""):
    source = prefix + b"constexpr const int arbitrary = 32;\n"
    offset = source.index(b"32")
    literal = {
        "id": "literal", "kind": "IntegerLiteral", "value": "32",
        "valueCategory": "prvalue", "type": {"qualType": "int"},
        "range": {"begin": {"offset": offset, "tokLen": 2},
                  "end": {"offset": offset, "tokLen": 2}},
    }
    declaration = {
        "id": "selected", "kind": "VarDecl", "name": "arbitrary",
        "constexpr": True, "init": "c", "type": {"qualType": "const int"},
        "loc": {"file": "/workspace/input.cpp", "offset": len(prefix)},
        "inner": [literal, {"id": "attr", "kind": "CUDAConstantAttr", "implicit": True}],
    }
    root = {"kind": "TranslationUnitDecl", "inner": [declaration]}
    return source, root


def digest(value):
    return hashlib.sha256(value).hexdigest()


class SourceTokenTests(unittest.TestCase):
    def run_edit(self, source, root, target=64, expected=None):
        return edit(source, digest(source) if expected is None else expected,
                    root, "selected", target, source_path="/workspace/input.cpp")

    def test_generates_only_one_unvalidated_byte_token_edit(self):
        source, root = fixture()
        result = self.run_edit(source, root)
        self.assertEqual("generated_unvalidated_candidate", result["status"], result)
        self.assertEqual(source.replace(b"32", b"64"), result["candidate_source"])
        manifest = result["manifest"]
        self.assertEqual(digest(source), manifest["source_sha256"])
        self.assertEqual(digest(result["candidate_source"]), manifest["candidate_sha256"])
        self.assertEqual("not_established", manifest["semantic_role"])
        for key in ("checked", "source_program_checked", "deployable"):
            self.assertFalse(result[key]); self.assertFalse(manifest[key])

    def test_non_token_bytes_and_utf8_byte_offsets_are_preserved(self):
        prefix = "// 寬度\n".encode("utf-8")
        source, root = fixture(prefix)
        result = self.run_edit(source, root, 128)
        offset = root["inner"][0]["inner"][0]["range"]["begin"]["offset"]
        self.assertEqual(source[:offset], result["candidate_source"][:offset])
        self.assertEqual(source[offset + 2:], result["candidate_source"][offset + 3:])
        self.assertEqual(offset, result["manifest"]["edit"]["byte_offset"])

    def test_hash_range_and_identity_conflicts_are_unknown(self):
        source, root = fixture()
        self.assertEqual("source_sha256_mismatch", self.run_edit(source, root, expected="0" * 64)["reason"])
        wrong = copy.deepcopy(root); wrong["inner"][0]["inner"][0]["range"]["begin"]["offset"] += 1
        self.assertEqual("literal_source_range_not_one_exact_token", self.run_edit(source, wrong)["reason"])
        duplicate = copy.deepcopy(root); duplicate["inner"].append(copy.deepcopy(duplicate["inner"][0]))
        self.assertEqual("declaration_id_not_unique", self.run_edit(source, duplicate)["reason"])
        conflict = copy.deepcopy(root); conflict["inner"].append({"id": "selected", "kind": "FunctionDecl"})
        self.assertEqual("declaration_id_not_unique", self.run_edit(source, conflict)["reason"])

    def test_macro_header_and_missing_locations_are_unknown(self):
        source, root = fixture()
        for mutation in (lambda loc: loc.update(expansionLoc={"offset": loc["offset"]}),
                         lambda loc: loc.update(includedFrom={"file": "header.h"}),
                         lambda loc: loc.pop("offset")):
            changed = copy.deepcopy(root)
            mutation(changed["inner"][0]["inner"][0]["range"]["begin"])
            with self.subTest(changed=changed):
                self.assertEqual("unknown", self.run_edit(source, changed)["status"])

    def test_literal_explicit_file_must_be_the_main_source(self):
        source, root = fixture()
        for endpoint in ("begin", "end"):
            changed = copy.deepcopy(root)
            changed["inner"][0]["inner"][0]["range"][endpoint]["file"] = "/tmp/header.h"
            self.assertEqual("literal_explicit_file_not_main_source",
                             self.run_edit(source, changed)["reason"])

    def test_non_plain_declarations_and_literals_are_unknown(self):
        source, root = fixture()
        changes = [
            lambda d, lit: d.update(constexpr=False),
            lambda d, lit: d["type"].update(typeAliasDeclId="alias"),
            lambda d, lit: d.update(kind="ParmVarDecl"),
            lambda d, lit: d.update(storageClass="static"),
            lambda d, lit: d.update(tlsKind="dynamic"),
            lambda d, lit: lit.update(kind="UnaryOperator"),
            lambda d, lit: lit.update(valueCategory="lvalue"),
            lambda d, lit: lit.update(inner=[{"kind": "IntegerLiteral"}]),
            lambda d, lit: lit["type"].update(qualType="long"),
            lambda d, lit: lit["type"].update(desugaredQualType="long"),
            lambda d, lit: d["inner"].append({"kind": "DeclRefExpr"}),
            lambda d, lit: d["inner"][1].update(implicit=False),
            lambda d, lit: d["inner"][1].update(kind="UnknownAttr"),
        ]
        for change in changes:
            changed = copy.deepcopy(root)
            declaration, literal = changed["inner"][0], changed["inner"][0]["inner"][0]
            change(declaration, literal)
            with self.subTest(change=change):
                self.assertEqual("unknown", self.run_edit(source, changed)["status"])

    def test_invalid_target_and_inputs_are_unknown(self):
        source, root = fixture()
        for target in (True, -1, 2_147_483_648):
            self.assertEqual("unknown", self.run_edit(source, root, target)["status"])
        self.assertEqual("unknown", edit("not bytes", digest(source), root, "selected", 64,
                                         source_path="/workspace/input.cpp")["status"])

    def test_non_ascii_noncanonical_literal_and_boolean_range_are_unknown(self):
        source, root = fixture()
        for value in ("032", "٣٢", "2147483648", "9" * 5000):
            changed = copy.deepcopy(root)
            changed["inner"][0]["inner"][0]["value"] = value
            self.assertEqual("unknown", self.run_edit(source, changed)["status"])
        changed = copy.deepcopy(root)
        changed["inner"][0]["inner"][0]["range"]["end"]["offset"] = True
        self.assertEqual("literal_source_range_not_one_exact_token",
                         self.run_edit(source, changed)["reason"])

    def test_budget_rejects_large_or_cyclic_roots(self):
        source, root = fixture()
        result = edit(source, digest(source), root, "selected", 64,
                      source_path="/workspace/input.cpp", max_ast_nodes=1)
        self.assertEqual("ast_node_budget_exceeded", result["reason"])
        cyclic = copy.deepcopy(root)
        cyclic["inner"].append(cyclic)
        result = edit(source, digest(source), cyclic, "selected", 64,
                      source_path="/workspace/input.cpp", max_ast_nodes=10)
        self.assertEqual("ast_node_budget_exceeded", result["reason"])
        self.assertEqual("invalid_inputs", edit(source, digest(source), root, "selected", 64,
                         source_path="/workspace/input.cpp", max_ast_nodes=True)["reason"])

    def test_declaration_must_explicitly_name_supplied_main_source(self):
        source, root = fixture()
        for location in ({"offset": 0},
                         {"file": "/workspace/other.cpp", "offset": 0},
                         {"file": "/workspace/input.cpp", "offset": 0,
                          "includedFrom": {"file": "header.h"}}):
            changed = copy.deepcopy(root)
            changed["inner"][0]["loc"] = location
            self.assertEqual("declaration_not_explicitly_bound_to_main_source",
                             self.run_edit(source, changed)["reason"])


if __name__ == "__main__":
    unittest.main()
