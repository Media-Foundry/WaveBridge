"""Real Clang ordinary nested loops; no synthetic break or mocked recovery."""
import copy
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.initializer_domain import check_fixed_nested_entry


CLANG = shutil.which("clang++")
ABI = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False}}
SOURCE = r"""
unsigned external_leaf();
unsigned getter() { return external_leaf(); }
void opaque();
constexpr int OUTER = 2, INNER = 4;
#define CASE(NAME, BEFORE, INSIDE, AFTER) \
void NAME(int* output) { \
 int value = getter(); \
 for (int i=0; i<OUTER; ++i) { \
  BEFORE \
  for (int j=0; j<INNER; ++j) { output[i*4+j]=value+j*32; INSIDE } \
  AFTER \
 } \
}
CASE(good, , , )
CASE(before, ++value;, , )
CASE(inside, , ++value;, )
CASE(after, , , ++value;)
CASE(alias, using Ref=int&; Ref ref=value; ++ref;, , )
CASE(call, , opaque();, )
CASE(inner_induction, , ++j;, )
CASE(outer_induction, , ++i;, )
CASE(exit_early, , break;, )
void header_write(int* output) {
 int value=getter();
 for(int i=(value=0); i<OUTER; ++i) {
  for(int j=0; j<INNER; ++j) output[j]=value;
 }
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class FixedNestedEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="wb-fixed-nested-")
        source = Path(cls.temp.name) / "fixture.cpp"
        source.write_text(SOURCE)
        report = collect(source, CLANG, ["-std=c++17"], "good", full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.payload = {"ast": report["ast_roots"][0]}
        cls.functions = {n.get("name"): n for n in _walk(cls.payload["ast"])
                         if n.get("kind") == "FunctionDecl"}
        cls.leaf = {"schema_version": "getter-leaf-domain/v1",
                    "declaration_id": cls.functions["external_leaf"]["id"],
                    "arguments": [], "return_type": {"qualType": "unsigned int"},
                    "lower": 0, "upper": 31}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def args(self, name):
        nodes = list(_walk(self.functions[name]))
        local, = [n for n in nodes if n.get("kind") == "VarDecl" and n.get("name") == "value"]
        outer, inner = [n for n in nodes if n.get("kind") == "ForStmt"]
        return [self.payload, local["id"], outer["id"], inner["id"], self.leaf, ABI, {}, {}]

    def test_original_nest_preserves_local_without_break(self):
        before = copy.deepcopy(self.payload)
        report = check_fixed_nested_entry(*self.args("good"))
        self.assertEqual(report["status"], "checked", report)
        self.assertEqual(report["result_interval"], {"lower": 0, "upper": 31})
        self.assertEqual(report["outer_header_iterations"], 2)
        self.assertEqual(report["nested_checks"][0]["check"]["iterations"], 4)
        for key in ("reachability_proved", "body_completion_proved", "column_coverage_checked",
                    "external_call_effects_verified", "source_program_checked", "deployable"):
            self.assertFalse(report[key])
        self.assertEqual(before, self.payload)

    def test_writes_and_aliases_on_all_paths_are_unknown(self):
        for name in ("before", "inside", "after", "alias", "header_write",
                     "inner_induction", "outer_induction"):
            with self.subTest(name=name):
                r = check_fixed_nested_entry(*self.args(name))
                self.assertEqual(r["status"], "unknown", r)
                self.assertFalse(r["value_preserved_to_nested_entry"])

    def test_opaque_call_and_break_are_not_erased(self):
        for name in ("call", "exit_early"):
            r = check_fixed_nested_entry(*self.args(name))
            self.assertEqual(r["status"], "unknown", r)

    def test_wrong_nested_selection_and_unused_protocol_fail_closed(self):
        args = self.args("good")
        args[3] = self.args("after")[3]
        self.assertEqual(check_fixed_nested_entry(*args)["status"], "unknown")
        args = self.args("good")
        args[-1] = {"unused": {"status": "checked"}}
        self.assertEqual(check_fixed_nested_entry(*args)["status"], "unknown")
        self.assertEqual(check_fixed_nested_entry(*self.args("good"), max_ast_nodes=1)["status"], "unknown")

    def test_semantic_slot_duplicate_and_malformed_children_fail_closed(self):
        args = self.args("good")
        args[0] = copy.deepcopy(self.payload)
        inner, = [n for n in _walk(args[0]["ast"]) if n.get("id") == args[3]]
        args[0]["ast"]["array_filler"] = [copy.deepcopy(inner)]
        self.assertEqual(check_fixed_nested_entry(*args)["status"], "unknown")
        args[0]["ast"]["array_filler"] = "invalid"
        self.assertEqual(check_fixed_nested_entry(*args)["status"], "unknown")
