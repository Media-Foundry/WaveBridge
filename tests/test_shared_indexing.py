import copy
import unittest

from wavebridge.verification.shared_indexing import check


ABI = {
    "int": {"bits": 32, "signed": True},
    "unsigned int": {"bits": 32, "signed": False},
    "unsigned char": {"bits": 8, "signed": False},
}
BINDINGS = {
    "group_declaration_id": "group", "lane_declaration_id": "lane",
    "width_declaration_id": "width", "block_declaration_id": "block",
}


def node(kind, ty="int", category="prvalue", **fields):
    return {"kind": kind, "type": {"qualType": ty}, "valueCategory": category, **fields}


def ref(identifier, ty="const int"):
    return node("DeclRefExpr", ty, "lvalue", id=identifier + "-ref",
                referencedDecl={"id": identifier, "kind": "VarDecl"})


def cast(expression, ty="int", kind="LValueToRValue"):
    return node("ImplicitCastExpr", ty, "prvalue", castKind=kind, inner=[expression])


def literal(value, ty="int"):
    return node("IntegerLiteral", ty, "prvalue", value=str(value))


def binary(opcode, left, right, ty="int"):
    return node("BinaryOperator", "bool" if opcode in {"==", "<"} else ty,
                "prvalue", opcode=opcode, inner=[left, right])


def fixture(index_type="int"):
    group = cast(ref("group"), index_type)
    lane = cast(ref("lane"), index_type)
    width = cast(ref("width"), index_type)
    block = cast(ref("block"), index_type)
    return {
        "writer_predicate": binary("==", copy.deepcopy(lane), literal(0, index_type)),
        "writer_index": group,
        "gather_predicate": binary("<", copy.deepcopy(lane),
                                     binary("/", block, width, index_type)),
        "gather_index": lane,
    }


class SharedIndexingTests(unittest.TestCase):
    def test_expected_predicates_and_active_indices_are_checked(self):
        result = check(fixture(), BINDINGS, 32, 256, ABI)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["groups"], 8)
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        self.assertIn("pointer validity, shared capacity, aliasing and synchronization are not checked",
                      result["limitations"])

    def test_wrong_predicate_operation_and_active_indices_are_rejected(self):
        cases = []
        accesses = fixture(); accesses["writer_predicate"]["opcode"] = "<"
        cases.append(accesses)
        accesses = fixture(); accesses["gather_predicate"]["opcode"] = "=="
        cases.append(accesses)
        accesses = fixture(); accesses["writer_index"] = cast(ref("lane"))
        cases.append(accesses)
        accesses = fixture(); accesses["gather_index"] = cast(ref("group"))
        cases.append(accesses)
        for accesses in cases:
            with self.subTest(accesses=accesses):
                self.assertEqual(check(accesses, BINDINGS, 32, 256, ABI)["status"], "rejected")

    def test_missing_or_repeated_bindings_are_unknown(self):
        missing = dict(BINDINGS); missing.pop("lane_declaration_id")
        repeated = dict(BINDINGS); repeated["lane_declaration_id"] = repeated["group_declaration_id"]
        extra = dict(BINDINGS, other="other")
        for bindings in (missing, repeated, extra):
            with self.subTest(bindings=bindings):
                self.assertEqual(check(fixture(), bindings, 32, 256, ABI)["status"], "unknown")

    def test_unsupported_operator_and_unknown_declaration_are_unknown(self):
        accesses = fixture(); accesses["writer_predicate"]["opcode"] = ">"
        self.assertEqual(check(accesses, BINDINGS, 32, 256, ABI)["status"], "unknown")
        accesses = fixture()
        accesses["gather_index"]["inner"][0]["referencedDecl"]["id"] = "other"
        self.assertEqual(check(accesses, BINDINGS, 32, 256, ABI)["status"], "unknown")

    def test_non_value_preserving_cast_is_rejected(self):
        accesses = fixture()
        # The block constant 256 cannot pass through an 8-bit cast on gather-active evaluation.
        block = accesses["gather_predicate"]["inner"][1]["inner"][0]
        accesses["gather_predicate"]["inner"][1]["inner"][0] = cast(block, "unsigned char", "IntegralCast")
        result = check(accesses, BINDINGS, 32, 256, ABI)
        self.assertEqual(result["status"], "rejected", result)

    def test_bool_is_language_type_not_implicit_integer_abi(self):
        accesses = fixture(); accesses["writer_predicate"]["type"] = {"qualType": "int"}
        self.assertEqual(check(accesses, BINDINGS, 32, 256, ABI)["status"], "unknown")
        abi = dict(ABI, bool={"bits": 8, "signed": False})
        self.assertEqual(check(accesses, BINDINGS, 32, 256, abi)["status"], "unknown")

    def test_only_active_gather_indices_need_value_preserving_casts(self):
        accesses = fixture()
        accesses["gather_index"] = cast(accesses["gather_index"], "unsigned char", "IntegralCast")
        # Lanes 256..511 never evaluate the gather subscript: only lanes 0,1 do.
        self.assertEqual(check(accesses, BINDINGS, 512, 1024, ABI)["status"], "checked")

    def test_malformed_discriminators_are_unknown(self):
        accesses = fixture()
        accesses["writer_predicate"]["opcode"] = []
        self.assertEqual(check(accesses, BINDINGS, 32, 256, ABI)["status"], "unknown")
        accesses = fixture()
        accesses["writer_index"]["inner"][0]["referencedDecl"]["id"] = []
        self.assertEqual(check(accesses, BINDINGS, 32, 256, ABI)["status"], "unknown")
        accesses = fixture()
        accesses["gather_index"]["castKind"] = []
        self.assertEqual(check(accesses, BINDINGS, 32, 256, ABI)["status"], "unknown")

    def test_invalid_block_width_and_input_hashes(self):
        for width, block in ((0, 256), (30, 256), (16, 1025), (8, 256)):
            with self.subTest(width=width, block=block):
                self.assertEqual(check(fixture(), BINDINGS, width, block, ABI)["status"], "unknown")
        result = check(fixture(), BINDINGS, 32, 256, ABI)
        self.assertEqual(set(result["input_sha256"]),
                         {"access_asts", "bindings", "width", "block_threads", "integer_types"})


if __name__ == "__main__":
    unittest.main()
