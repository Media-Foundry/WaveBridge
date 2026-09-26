"""Real Clang typed-template comparison, not numerical or GPU equivalence."""
import copy
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.local_structure import compare


SOURCE = """
float consume(float, float *);
float alternate(float, float *);
constexpr int stride = 256;
float entry(const float *input, const float *other, int count, int limit, const int start, const int offset) {
  float partial = 0.0f;
  for (int col = start; col < count; col += stride) {
    const float value = input[col];
    partial += value * value;
  }
  float scratch[32];
  const float total = consume(partial, scratch);
  return total;
}
"""


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class LocalStructureClangTests(unittest.TestCase):
    def parse(self, source):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.cpp"
            path.write_text(source)
            artifact = collect(path, shutil.which("clang++"), ["-std=c++17"], "entry",
                               full_translation_unit=True)
        self.assertEqual("collected", artifact["status"], artifact.get("execution"))
        root, = artifact["ast_roots"]
        kernel, = [n["id"] for n in _walk(root) if n.get("kind") == "FunctionDecl" and n.get("name") == "entry"]
        return root, kernel

    def test_independent_parse_and_renaming_keep_types_order_and_boundaries(self):
        left = self.parse(SOURCE)
        renamed = SOURCE.replace("partial", "state").replace("value", "element").replace("stride", "step")
        result = compare(*left, *self.parse(renamed))
        self.assertEqual("evidence", result["status"], result)
        self.assertTrue(result["local_structure_equal"])
        for field in ("entry_value_correspondence", "consumer_correspondence", "leaf_value_correspondence"):
            self.assertEqual("not_established", result[field])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        self.assertTrue(result["checks"]["source"]["constants"])

    def test_another_parameter_cannot_disappear_under_role_renaming(self):
        source = self.parse(SOURCE)
        for old, new, role in (("input[col]", "other[col]", "input"),
                               ("col = start", "col = offset", "start"),
                               ("col < count", "col < limit", "bound")):
            result = compare(*source, *self.parse(SOURCE.replace(old, new)))
            self.assertEqual("rejected", result["status"], result)
            bindings = [result["checks"][side]["role_bindings"][role] for side in ("source", "target")]
            self.assertNotEqual(bindings[0]["parameter_position"], bindings[1]["parameter_position"])
            self.assertEqual("not_established", result["leaf_value_correspondence"])

    def test_constant_changes_not_hidden_by_declref_names(self):
        left = self.parse(SOURCE)
        changed = SOURCE.replace("stride = 256", "stride = 128")
        result = compare(*left, *self.parse(changed))
        self.assertEqual("rejected", result["status"], result)
        self.assertFalse(result["local_structure_equal"])

    def test_indirect_constant_dependency_must_also_have_unique_identity(self):
        source = SOURCE.replace("constexpr int stride = 256;",
                                "constexpr int base = 256; constexpr int stride = base;")
        left = self.parse(source)
        right, kernel = copy.deepcopy(left)
        base = next(n for n in _walk(right) if n.get("kind") == "VarDecl" and n.get("name") == "base")
        conflict = copy.deepcopy(base)
        next(n for n in _walk(conflict) if n.get("kind") == "IntegerLiteral")["value"] = "128"
        right["inner"].insert(0, conflict)
        result = compare(*left, right, kernel)
        self.assertEqual("unknown", result["status"], result)

    def test_prefix_and_consumer_changes_remain_explicitly_outside_scope(self):
        left = self.parse(SOURCE)
        for changed in (SOURCE.replace("float partial", "input += 1; float partial"),
                        SOURCE.replace("total = consume", "total = alternate")):
            result = compare(*left, *self.parse(changed))
            self.assertEqual("evidence", result["status"], result)
            self.assertEqual("not_established", result["entry_value_correspondence"])
            self.assertEqual("not_established", result["consumer_correspondence"])
            self.assertFalse(result["source_program_checked"])

    def test_real_unsupported_storage_and_operation_do_not_get_a_template(self):
        left = self.parse(SOURCE)
        for old, new in (("float partial =", "static float partial ="),
                         ("const float value", "static const float value"),
                         ("value * value", "value + value"),
                         ("float scratch[32]", "float scratch[(partial = 7, 32)]")):
            result = compare(*left, *self.parse(SOURCE.replace(old, new)))
            self.assertEqual("unknown", result["status"], result)
            self.assertIsNone(result["local_structure_equal"])

    def test_computation_types_and_fp_options_are_not_discarded(self):
        left = self.parse(SOURCE)
        for key, value in (("computeResultType", {"qualType": "double"}),
                           ("fpoptions", {"AllowFPContract": True})):
            right, kernel = copy.deepcopy(left)
            update = next(n for n in _walk(right) if n.get("kind") == "CompoundAssignOperator"
                          and n.get("type", {}).get("qualType") == "float")
            update[key] = value
            result = compare(*left, right, kernel)
            self.assertEqual("rejected", result["status"], result)

    def test_unknown_fields_missing_types_duplicate_ids_and_budgets_fail_closed(self):
        left = self.parse(SOURCE)
        for mutation in ("unknown_field", "missing_type", "duplicate", "stub"):
            right, kernel = copy.deepcopy(left)
            node = next(n for n in _walk(right) if n.get("kind") == "VarDecl" and n.get("name") == "partial")
            if mutation == "unknown_field":
                node["unmodeled_semantics"] = True
            elif mutation == "missing_type":
                expr = next(n for n in _walk(node) if n.get("kind") == "FloatingLiteral")
                del expr["type"]
            elif mutation == "duplicate":
                right["inner"].append(copy.deepcopy(node))
            else:
                ref = next(n for n in _walk(right) if n.get("kind") == "DeclRefExpr" and
                           n.get("referencedDecl", {}).get("id") == node["id"])
                ref["referencedDecl"]["type"] = {"qualType": "double"}
            self.assertEqual("unknown", compare(*left, right, kernel)["status"], mutation)
        self.assertEqual("unknown", compare(*left, *left, max_ast_nodes=1)["status"])
        self.assertEqual("unknown", compare(*left, *left, max_ast_nodes=True)["status"])


if __name__ == "__main__":
    unittest.main()
