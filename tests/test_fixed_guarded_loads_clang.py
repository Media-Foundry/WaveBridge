"""Real source -> labels -> pointer history -> selected load, without recovery mocks."""
import copy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.column_coverage import check_fixed_guarded_loads

CLANG = shutil.which("clang++")
ABI = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False}}
SOURCE = r"""
unsigned leaf();
unsigned getter() { return leaf(); }
constexpr int BATCHES=2, ITERATIONS=4, WIDTH=32;
#define CASE(NAME, PREFIX, COUNT, INDEX, DEST, EXTRA, ELSE) \
void NAME(float* output, const float* input, int n, int stride, int rows, int first) { \
 int first_batch=first; \
 int lane=getter(); \
 int offset=first_batch*stride+lane; \
 input+=offset; PREFIX \
 float elements[BATCHES][ITERATIONS]; \
 for(int row=0; row<BATCHES; ++row) { \
  int count=COUNT; \
  for(int it=0; it<ITERATIONS; ++it) { \
   int column=lane+it*WIDTH; \
   if(column<count) { DEST=input[INDEX]; EXTRA } else { ELSE } \
  } \
 } \
 for(int row=0; row<BATCHES; ++row) \
  for(int it=0; it<ITERATIONS; ++it) \
   output[row*128+lane+it*WIDTH]=elements[row][it]; \
}
CASE(good, , row>=rows?0:n, row*n+it*WIDTH, elements[row][it], , elements[row][it]=0;)
CASE(reordered, , row>=rows?0:n, WIDTH*it+n*row, elements[row][it], , elements[row][it]=0;)
CASE(snapshot, , n, row*n+it*WIDTH, elements[row][it], , elements[row][it]=0;)
CASE(wrong_step, , row>=rows?0:n, row*n+it*31, elements[row][it], , elements[row][it]=0;)
CASE(wrong_row, , row>=rows?0:n, row*stride+it*WIDTH, elements[row][it], , elements[row][it]=0;)
CASE(shifted, , row>=rows?0:n, row*n+it*WIDTH+1, elements[row][it], , elements[row][it]=0;)
CASE(wrong_dest, , row>=rows?0:n, row*n+it*WIDTH, elements[0][it], , elements[row][it]=0;)
CASE(extra_load, , row>=rows?0:n, row*n+it*WIDTH, elements[row][it], elements[row][it]+=input[0];, elements[row][it]=0;)
CASE(else_load, , row>=rows?0:n, row*n+it*WIDTH, elements[row][it], , elements[row][it]=input[0];)
CASE(double_shift, input+=offset;, row>=rows?0:n, row*n+it*WIDTH, elements[row][it], , elements[row][it]=0;)
CASE(changed_offset, ++offset;, row>=rows?0:n, row*n+it*WIDTH, elements[row][it], , elements[row][it]=0;)
CASE(changed_count, ++n;, row>=rows?0:n, row*n+it*WIDTH, elements[row][it], , elements[row][it]=0;)
CASE(alias_count, using Ref=int&; Ref a=n; ++a;, row>=rows?0:n, row*n+it*WIDTH, elements[row][it], , elements[row][it]=0;)
CASE(inner_count, , row>=rows?0:n, row*n+it*WIDTH, elements[row][it], ++n;, elements[row][it]=0;)
CASE(wrong_count, , row>=rows?1:n, row*n+it*WIDTH, elements[row][it], , elements[row][it]=0;)
CASE(overflow, , row>=rows?0:n, (row*n+2147483647)-2147483647+it*WIDTH, elements[row][it], , elements[row][it]=0;)
CASE(unsigned_index, , row>=rows?0:n, (unsigned)(row*n+it*WIDTH), elements[row][it], , elements[row][it]=0;)
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class FixedGuardedLoadsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="wb-fixed-loads-")
        source = Path(cls.temp.name) / "loads.cpp"
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

    def inputs(self, name):
        nodes = list(_walk(self.functions[name]))
        declarations = {n["name"]: n for n in nodes if n.get("kind") in {"VarDecl", "ParmVarDecl"}}
        outer, inner = [n for n in nodes if n.get("kind") == "ForStmt"][:2]
        args = [self.payload, declarations["lane"]["id"], outer["id"], inner["id"], self.leaf, ABI, {}, {},
                declarations["input"]["id"], declarations["n"]["id"], [0, 128]]
        binding = {"offset_declaration_id": declarations["offset"]["id"],
                   "row_declaration_id": declarations["first_batch"]["id"],
                   "stride_parameter_id": declarations["stride"]["id"],
                   "row_interval": [0, 4095], "stride_interval": [0, 128]}
        return args, {"pointer_binding": binding}

    def run_case(self, name):
        args, kwargs = self.inputs(name)
        return check_fixed_guarded_loads(*args, **kwargs)

    def test_supported_source_spellings(self):
        for name in ("good", "reordered", "snapshot"):
            with self.subTest(name=name):
                r = self.run_case(name)
                self.assertEqual(r["status"], "checked", r["reason"])
                self.assertTrue(r["guarded_load_relation_checked"])
                self.assertTrue(r["entry_pointer_history_checked"])
                self.assertTrue(r["count_domain_checked_under_external_interval"])
                self.assertEqual(r["relative_index_interval"], [0, 224])
                self.assertEqual(r["guard_count_interval"], [0, 128])

    def test_wrong_addresses_destinations_and_guard_do_not_pass(self):
        for name in ("wrong_step", "wrong_row", "shifted", "wrong_dest", "extra_load", "else_load", "wrong_count"):
            with self.subTest(name=name):
                r = self.run_case(name)
                self.assertEqual(r["status"], "unknown", r["reason"])
                self.assertFalse(r["guarded_load_relation_checked"])

    def test_source_history_and_count_changes_do_not_pass(self):
        for name in ("double_shift", "changed_offset", "changed_count", "alias_count", "inner_count"):
            with self.subTest(name=name):
                r = self.run_case(name)
                self.assertEqual(r["status"], "unknown", r["reason"])
                self.assertFalse(r["guarded_load_relation_checked"])

    def test_overflow_and_unsupported_integer_cast_do_not_pass(self):
        for name in ("overflow", "unsigned_index"):
            r = self.run_case(name)
            self.assertEqual(r["status"], "unknown", r["reason"])

    def test_external_domains_budget_selection_and_input_immutability(self):
        before = copy.deepcopy(self.payload)
        for domain in ([0,129], [-1,128], [2,1], [False,128], [0], None):
            args, kwargs = self.inputs("good")
            args[-1] = domain
            self.assertEqual(check_fixed_guarded_loads(*args, **kwargs)["status"], "unknown")
        args, kwargs = self.inputs("good")
        self.assertEqual(check_fixed_guarded_loads(*args, **kwargs, max_ast_nodes=1)["status"], "unknown")
        args[8] = self.inputs("snapshot")[0][8]
        self.assertEqual(check_fixed_guarded_loads(*args, **kwargs)["status"], "unknown")
        self.assertEqual(self.payload, before)

    def test_guarantees_remain_conditional_and_stride_is_not_count(self):
        r = self.run_case("good")
        self.assertEqual(r["status"], "checked", r["reason"])
        for key in ("count_common_across_lanes_checked", "actual_thread_participation_checked", "memory_load_coverage_checked",
                    "input_contents_preserved", "source_program_checked", "deployable"):
            self.assertFalse(r[key])
        relation = r["entry_relative_offset_relation"]
        self.assertNotEqual(relation["stride_parameter_id"], relation["count_parameter_id"])
        self.assertIn("indirect stores and prior or retained aliases do not modify the selected pointer, offset, or readonly parameter storage",
                      r["assumptions"])

    def test_selected_load_hidden_slots_and_conflicting_identity(self):
        args, kwargs = self.inputs("good")
        original = next(n for n in _walk(self.functions["good"]) if n.get("kind") == "BinaryOperator" and n.get("opcode") == "=")
        targets = [n for n in _walk(original) if n.get("kind") in {"ArraySubscriptExpr", "BinaryOperator", "ImplicitCastExpr", "DeclRefExpr"}]
        for target in targets:
            mutated = copy.deepcopy(self.payload)
            node = next(n for n in _walk(mutated["ast"]) if n.get("id") == target["id"])
            node["array_filler"] = [{"id": "hidden", "kind": "GCCAsmStmt"}]
            self.assertEqual(check_fixed_guarded_loads(mutated, *args[1:], **kwargs)["status"], "unknown", target["kind"])
        mutated = copy.deepcopy(self.payload)
        mutated["ast"]["inner"].append(copy.deepcopy(original))
        self.assertEqual(check_fixed_guarded_loads(mutated, *args[1:], **kwargs)["status"], "unknown")

    def test_count_reference_hidden_slots_and_duplicate_identity(self):
        args, kwargs = self.inputs("good")
        count_ref = next(n for n in _walk(self.functions["good"]) if n.get("kind") == "DeclRefExpr" and
                         n.get("referencedDecl", {}).get("id") == args[9])
        conversion = next(n for n in _walk(self.functions["good"]) if n.get("kind") == "ImplicitCastExpr" and
                          n.get("inner") == [count_ref])
        for target in (count_ref, conversion):
            for slot in (None, [{"id": "hidden", "kind": "GCCAsmStmt"}]):
                mutated = copy.deepcopy(self.payload)
                node = next(n for n in _walk(mutated["ast"]) if n.get("id") == target["id"])
                node["array_filler"] = slot
                self.assertEqual(check_fixed_guarded_loads(mutated, *args[1:], **kwargs)["status"], "unknown")
        mutated = copy.deepcopy(self.payload)
        mutated["ast"]["inner"].append(copy.deepcopy(count_ref))
        self.assertEqual(check_fixed_guarded_loads(mutated, *args[1:], **kwargs)["status"], "unknown")

    def test_wrong_pointer_binding_and_domain_are_unknown(self):
        args, kwargs = self.inputs("good")
        for key, value in (("offset_declaration_id", args[1]), ("stride_parameter_id", args[9]),
                           ("row_declaration_id", "missing"), ("row_interval", [0, 2147483647]),
                           ("stride_interval", [-1, 128])):
            changed = copy.deepcopy(kwargs)
            changed["pointer_binding"][key] = value
            self.assertEqual(check_fixed_guarded_loads(*args, **changed)["status"], "unknown")

    def test_real_cpu_loads_have_expected_entry_relative_addresses(self):
        # Sentinel values witness actual source addresses. Synthetic CPU execution
        # is independent of AST reconstruction, not a GPU/FP-equivalence result.
        source = Path(self.temp.name) / "execute.cpp"
        source.write_text(SOURCE + r'''
unsigned current_lane;
unsigned leaf() { return current_lane; }
int main() {
 float input[1024], output[256];
 for(int j=0;j<1024;++j) input[j]=float(j+1);
 int sizes[]={0,1,31,32,65,127,128};
 for(int n:sizes) {
  for(current_lane=0;current_lane<32;++current_lane) good(output,input,n,117,2,2);
  for(int row=0;row<2;++row) for(int c=0;c<128;++c)
   if(output[row*128+c] != (c<n ? input[2*117+row*n+c] : 0)) return 1;
 }
 for(current_lane=0;current_lane<32;++current_lane) wrong_step(output,input,128,117,2,2);
 for(int row=0;row<2;++row) for(int c=0;c<128;++c)
  if(output[row*128+c]!=input[2*117+row*128+c]) return 0;
 return 2;
}
''')
        binary = Path(self.temp.name) / "execute"
        built = subprocess.run([CLANG, "-std=c++17", str(source), "-o", str(binary)], capture_output=True, timeout=30)
        self.assertEqual(built.returncode, 0, built.stderr.decode())
        run = subprocess.run([str(binary)], capture_output=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr.decode())
