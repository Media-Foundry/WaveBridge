"""Source label/guard recovery, not memory or GPU participation coverage."""
import copy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.column_coverage import check_fixed_guarded_labels

CLANG = shutil.which("clang++")
ABI = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False}}
SOURCE = r"""
unsigned leaf();
unsigned getter() { return leaf(); }
constexpr int BATCHES=2, ITERATIONS=4, WIDTH=32;
#define CASE(NAME, INDEX, OP, THEN, ELSE) \
void NAME(int* output, const int* input, int n, int rows) { \
 int lane=getter(); \
 for(int row=0; row<BATCHES; ++row) { \
  int count = row>=rows ? 0 : n; \
  for(int it=0; it<ITERATIONS; ++it) { \
   int column=INDEX; \
   if(column OP count) { THEN } else { ELSE } \
  } \
 } \
}
CASE(good, lane+it*WIDTH, <, output[it]=input[it];, output[it]=0;)
CASE(reordered, WIDTH*it+(lane+0), <, output[it]=input[it];, output[it]=0;)
CASE(wrong_stride, lane+it*31, <, output[it]=input[it];, output[it]=0;)
CASE(shifted, lane+it*WIDTH+1, <, output[it]=input[it];, output[it]=0;)
CASE(wrong_guard, lane+it*WIDTH, <=, output[it]=input[it];, output[it]=0;)
CASE(changed_count, lane+it*WIDTH, <, ++count; output[it]=input[it];, output[it]=0;)
CASE(alias_count, lane+it*WIDTH, <, using Ref=int&; Ref alias=count; ++alias;, output[it]=0;)
CASE(overflow, (lane+2147483647)-2147483647+it*WIDTH, <, output[it]=input[it];, output[it]=0;)
CASE(unchecked_memory, lane+it*WIDTH, <, output[0]=input[0];, output[it]=0;)
// Counting instrumentation must not erase earlier counts in its else branch.
CASE(cpu_counts, lane+it*WIDTH, <, ++output[column];, )
CASE(cpu_bad_counts, lane+it*31, <, ++output[column];, )
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class FixedGuardedLabelsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="wb-fixed-labels-")
        source = Path(cls.temp.name) / "labels.cpp"
        source.write_text(SOURCE)
        captured = collect(source, CLANG, ["-std=c++17"], "good", full_translation_unit=True)
        if captured["status"] != "collected":
            raise AssertionError(captured)
        cls.payload = {"ast": captured["ast_roots"][0]}
        cls.functions = {n.get("name"): n for n in _walk(cls.payload["ast"]) if n.get("kind") == "FunctionDecl"}
        cls.leaf = {"schema_version": "getter-leaf-domain/v1", "declaration_id": cls.functions["leaf"]["id"],
                    "arguments": [], "return_type": {"qualType": "unsigned int"}, "lower": 0, "upper": 31}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def arguments(self, name):
        nodes = list(_walk(self.functions[name]))
        local, = [n for n in nodes if n.get("kind") == "VarDecl" and n.get("name") == "lane"]
        outer, inner = [n for n in nodes if n.get("kind") == "ForStmt"]
        return [self.payload, local["id"], outer["id"], inner["id"], self.leaf, ABI, {}, {}]

    def test_dense_formal_labels_from_two_source_spellings(self):
        for name in ("good", "reordered", "cpu_counts"):
            report = check_fixed_guarded_labels(*self.arguments(name))
            self.assertEqual(report["status"], "checked", report["reason"])
            self.assertEqual(report["capacity"], 128)
            self.assertEqual(report["relation"], {"coordinate_coefficient": 1, "induction_coefficient": 32, "offset": 0})
            self.assertEqual(report["supported_count_domain"], {"lower": 0, "upper": 128})
            self.assertEqual(report["label_interval"], [0, 127])

    def test_incorrect_labels_guard_and_effects_do_not_pass(self):
        for name in ("wrong_stride", "shifted", "wrong_guard", "changed_count", "alias_count", "overflow", "cpu_bad_counts"):
            with self.subTest(name=name):
                report = check_fixed_guarded_labels(*self.arguments(name))
                self.assertEqual(report["status"], "unknown", report["reason"])
                self.assertFalse(report["formal_label_coverage_checked"])

    def test_label_coverage_is_not_load_coverage(self):
        report = check_fixed_guarded_labels(*self.arguments("unchecked_memory"))
        self.assertEqual(report["status"], "checked", report["reason"])
        self.assertIn("all inner-loop indirect stores, including through prior or retained aliases, "
                      "do not alias the selected count storage", report["assumptions"])
        for key in ("actual_thread_participation_checked", "guard_count_entry_domain_checked",
                    "memory_load_coverage_checked", "pointer_history_checked", "source_program_checked", "deployable"):
            self.assertFalse(report[key])

    def test_budget_wrong_loop_and_input_immutability(self):
        before = copy.deepcopy(self.payload)
        args = self.arguments("good")
        self.assertEqual(check_fixed_guarded_labels(*args, max_ast_nodes=1)["status"], "unknown")
        args[3] = self.arguments("reordered")[3]
        self.assertEqual(check_fixed_guarded_labels(*args)["status"], "unknown")
        self.assertEqual(self.payload, before)

    def test_dense_family_formula_matches_all_finite_prefixes(self):
        # Independent bounded enumeration checks the claimed label theorem,
        # not source memory execution or physical lane participation.
        for width in range(1, 9):
            for count in range(1, 9):
                for n in range(width * count + 1):
                    labels = [lane + it * width for lane in range(width) for it in range(count)
                              if lane + it * width < n]
                    self.assertEqual(sorted(labels), list(range(n)))

    def test_hidden_reference_children_are_unknown(self):
        args = self.arguments("good")
        args[0] = copy.deepcopy(self.payload)
        function = next(n for n in _walk(args[0]["ast"]) if n.get("id") == self.functions["good"]["id"])
        ref = next(n for n in _walk(function) if n.get("kind") == "DeclRefExpr" and
                   n.get("referencedDecl", {}).get("name") == "count")
        ref["array_filler"] = [{"id": "hidden", "kind": "IntegerLiteral", "type": {"qualType": "int"}, "value": "0"}]
        self.assertEqual(check_fixed_guarded_labels(*args)["status"], "unknown")

    def test_hidden_or_malformed_scalar_and_guard_slots_are_unknown(self):
        args = self.arguments("reordered")
        nodes = list(_walk(self.functions["reordered"]))
        label = next(n for n in nodes if n.get("kind") == "VarDecl" and n.get("name") == "column")
        guard = next(n for n in nodes if n.get("kind") == "IfStmt")
        expressions = [n for n in _walk(label) if n.get("kind") in
                       {"BinaryOperator", "ImplicitCastExpr", "ParenExpr", "IntegerLiteral"}]
        for target in [label, guard, guard["inner"][0], *expressions]:
            for filler in (None, [{"id": "hidden_effect", "kind": "GCCAsmStmt"}]):
                with self.subTest(kind=target["kind"], filler=filler):
                    mutated = copy.deepcopy(self.payload)
                    node = next(n for n in _walk(mutated["ast"]) if n.get("id") == target["id"])
                    node["array_filler"] = filler
                    report = check_fixed_guarded_labels(mutated, *args[1:])
                    self.assertEqual(report["status"], "unknown")
                    self.assertFalse(report["formal_label_coverage_checked"])

    def test_compiled_cpu_label_counts_and_wrong_stride_witness(self):
        # Instrumented synthetic source executes one logical row, not GPU lanes.
        source = Path(self.temp.name) / "cpu_counts.cpp"
        source.write_text(SOURCE + r'''
unsigned current_lane;
unsigned leaf() { return current_lane; }
int main() {
 int sizes[] = {0,1,31,32,65,127,128};
 for(int n:sizes) {
  int counts[128]={};
  for(current_lane=0; current_lane<32; ++current_lane) cpu_counts(counts,counts,n,1);
  for(int c=0;c<128;++c) if(counts[c] != (c<n ? 1:0)) return 1;
 }
 int bad[128]={};
 for(current_lane=0;current_lane<32;++current_lane) cpu_bad_counts(bad,bad,128,1);
 for(int c=0;c<128;++c) if(bad[c]!=1) return 0;
 return 2;
}
''')
        binary = Path(self.temp.name) / "cpu_counts"
        built = subprocess.run([CLANG, "-std=c++17", str(source), "-o", str(binary)], capture_output=True, timeout=30)
        self.assertEqual(built.returncode, 0, built.stderr.decode())
        executed = subprocess.run([str(binary)], capture_output=True, timeout=10)
        self.assertEqual(executed.returncode, 0, executed.stderr.decode())
