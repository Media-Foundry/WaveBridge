"""Same-invocation compiler enum observations, not runtime range proofs."""
import os
from pathlib import Path
import unittest
from wavebridge.frontend.native_captures import collect
from wavebridge.frontend.clang_ast import _walk

PLUGIN = os.environ.get("WB_ENUM_CAPTURE_PLUGIN") or os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_ENUM_CAPTURE_COMPILER") or os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")


@unittest.skipUnless(PLUGIN, "requires compiler-matched enum observation plugin")
class NativeEnumTypesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = collect(Path(__file__).parent / "fixtures/native_enum_types.cpp", COMPILER,
                             Path(PLUGIN), ["-std=c++17"])
        if cls.report["status"] != "collected": raise AssertionError(cls.report)
        cls.payload = cls.report["payload"]
        cls.declarations = {n["id"]: n for n in _walk(cls.payload["ast"]) if n.get("kind") == "EnumDecl"}
        cls.records = {cls.declarations[r["enum_declaration_id"]]["name"]: r for r in cls.payload["enum_types"]}

    def test_named_values_and_ids_belong_to_same_ast(self):
        raw = self.payload["enum_types"]
        self.assertEqual(len(raw), 3)
        self.assertEqual(len({r["enum_declaration_id"] for r in raw}), len(raw))
        ids = [v["declaration_id"] for r in raw for v in r["enumerators"]]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(set(self.records), {"Positive", "Signed", "Wide"})
        expected = {"Positive": [0, 1, 1055], "Signed": [-4, 0, 1], "Wide": [9223372036854775815]}
        for name, record in self.records.items():
            declaration = self.declarations[record["enum_declaration_id"]]
            constants = [n for n in declaration["inner"] if n.get("kind") == "EnumConstantDecl"]
            self.assertEqual([n["id"] for n in constants], [v["declaration_id"] for v in record["enumerators"]])
            self.assertEqual([int(v["value_decimal"]) for v in record["enumerators"]], expected[name])

    def test_underlying_and_promotion_are_distinct(self):
        positive = self.records["Positive"]
        self.assertEqual(positive["underlying_type"], "unsigned int")
        self.assertFalse(positive["underlying_signed"])
        self.assertEqual(positive["promotion_type"], "int")
        self.assertTrue(positive["promotion_signed"])
        self.assertEqual(positive["promotion_bits"], self.payload["ast_int_bits"])
        self.assertFalse(positive["is_fixed"])
        self.assertTrue(self.records["Signed"]["underlying_signed"])
        self.assertTrue(self.records["Wide"]["is_fixed"])
        self.assertTrue(self.records["Wide"]["is_scoped"])
        # Clang may populate this internal slot even for scoped enums. It is
        # not evidence that the language permits their implicit conversion.
        self.assertIn(self.records["Wide"]["promotion_type"], (None, "unsigned long long"))

    def test_observation_does_not_claim_exhaustive_runtime_domain(self):
        self.assertIn("not_exhaustive", self.payload["enum_type_coverage"])
        self.assertIn("not_runtime_domain_proof", self.payload["enum_type_semantics"])
        self.assertFalse(self.payload["source_program_checked"])
        self.assertFalse(self.payload["deployable"])
        self.assertTrue(self.report["inputs_stable"])
