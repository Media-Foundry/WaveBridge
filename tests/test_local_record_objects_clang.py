"""Native local-record metadata is lexical evidence, not destruction proof."""
import os
from pathlib import Path
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect


PLUGIN = os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")


@unittest.skipUnless(PLUGIN, "requires compiler-matched native observation plugin")
class NativeLocalRecordObjectsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="wb-native-local-records-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.source = Path(cls.directory.name) / "local_record_objects.cpp"
        cls.source.write_text(r"""
struct Record {
  int value = 0;
  ~Record() { value = 1; }
};
struct Trivial { int value; };
template <typename T> struct DependentRecord { T value; };
template <typename T> void dependent_objects() {
  DependentRecord<T> dependent_local;
}

void lexical_objects() {
  Record direct;
  {
    Record ended_nested_scope;
  }
  Record enclosing_scope;
  static Record static_local;
  thread_local Record thread_local_object;
  Record& reference_alias = enclosing_scope;
  Record* pointer_alias = &enclosing_scope;
  Record array_objects[2];
  for (Record for_init; false;) {}
  if (Record if_init; false) {}
  [&]() { Record lambda_local; }();
  Trivial trivial_local{};
  (void)direct;
  (void)reference_alias;
}
""", encoding="utf-8")
        cls.report = collect(cls.source, COMPILER, Path(PLUGIN), ["-std=c++17"])
        if cls.report["status"] != "collected":
            raise AssertionError(cls.report)
        cls.payload = cls.report["payload"]
        cls.root = cls.payload["ast"]
        cls.records = cls.payload.get("local_record_objects")
        if not isinstance(cls.records, list):
            raise AssertionError("plugin payload has no local_record_objects list")
        cls.nodes = {}
        cls.parents = {}
        pending = [cls.root]
        while pending:
            node = pending.pop()
            identifier = node.get("id")
            if isinstance(identifier, str):
                cls.nodes.setdefault(identifier, []).append(node)
            for child in node.get("inner", []):
                if child:
                    cls.parents.setdefault(id(child), []).append(node)
                    pending.append(child)
        cls.variables = {
            node["name"]: node for node in _walk(cls.root)
            if node.get("kind") == "VarDecl" and node.get("name")
        }
        cls.by_variable = {row["variable_declaration_id"]: row for row in cls.records}

    def row(self, name):
        variable = self.variables[name]
        self.assertIn(variable["id"], self.by_variable)
        return variable, self.by_variable[variable["id"]]

    def direct_compound(self, variable):
        owners = self.parents[id(variable)]
        self.assertEqual(len(owners), 1)
        declaration = owners[0]
        self.assertEqual(declaration.get("kind"), "DeclStmt")
        owners = self.parents[id(declaration)]
        self.assertEqual(len(owners), 1)
        self.assertEqual(owners[0].get("kind"), "CompoundStmt")
        return owners[0]

    def test_metadata_ids_bind_to_same_ast_and_only_describe_lexical_facts(self):
        self.assertEqual(
            self.payload["local_record_object_coverage"],
            "visited_local_complete_record_variables_not_exhaustive")
        self.assertEqual(
            self.payload["local_record_object_semantics"],
            "lexical_declarations_not_runtime_destructor_events")
        required = {
            "variable_declaration_id", "declaring_compound_statement_id",
            "record_declaration_id", "destructor_declaration_id",
            "has_automatic_storage_duration", "has_nontrivial_destructor",
            "support_status",
        }
        self.assertTrue(self.records)
        self.assertEqual(len(self.by_variable), len(self.records))
        for row in self.records:
            with self.subTest(row=row):
                self.assertTrue(required.issubset(row))
                self.assertEqual(self.nodes[row["variable_declaration_id"]][0]["kind"], "VarDecl")
                self.assertEqual(self.nodes[row["record_declaration_id"]][0]["kind"], "CXXRecordDecl")
                destructor = row["destructor_declaration_id"]
                if destructor is not None:
                    self.assertEqual(self.nodes[destructor][0]["kind"], "CXXDestructorDecl")
                self.assertIs(type(row["has_automatic_storage_duration"]), bool)
                self.assertIs(type(row["has_nontrivial_destructor"]), bool)
                self.assertIn(row["support_status"], {"observed", "unsupported"})
        self.assertFalse(self.report["source_program_checked"])
        self.assertFalse(self.report["deployable"])

    def test_direct_nested_and_enclosing_automatic_records_bind_exact_compounds(self):
        direct, direct_row = self.row("direct")
        ended, ended_row = self.row("ended_nested_scope")
        enclosing, enclosing_row = self.row("enclosing_scope")
        for variable, row in ((direct, direct_row), (ended, ended_row),
                              (enclosing, enclosing_row)):
            with self.subTest(name=variable["name"]):
                self.assertEqual(row["support_status"], "observed")
                self.assertTrue(row["has_automatic_storage_duration"])
                self.assertTrue(row["has_nontrivial_destructor"])
                self.assertEqual(row["declaring_compound_statement_id"],
                                 self.direct_compound(variable)["id"])
                self.assertIsNotNone(row["destructor_declaration_id"])
        self.assertNotEqual(ended_row["declaring_compound_statement_id"],
                            enclosing_row["declaring_compound_statement_id"])
        self.assertEqual(direct_row["declaring_compound_statement_id"],
                         enclosing_row["declaring_compound_statement_id"])

    def test_static_and_thread_local_are_retained_as_unsupported(self):
        for name in ("static_local", "thread_local_object"):
            with self.subTest(name=name):
                variable, row = self.row(name)
                self.assertEqual(row["support_status"], "unsupported")
                self.assertEqual(row.get("unsupported_reason"),
                                 "non_automatic_storage_duration")
                self.assertFalse(row["has_automatic_storage_duration"])
                self.assertEqual(row["declaring_compound_statement_id"],
                                 self.direct_compound(variable)["id"])

    def test_reference_declaration_is_not_a_record_object_entry(self):
        for name in ("reference_alias", "pointer_alias", "array_objects", "dependent_local"):
            self.assertNotIn(self.variables[name]["id"], self.by_variable)

    def test_for_initializer_has_no_direct_compound_binding(self):
        for name in ("for_init", "if_init"):
            _, row = self.row(name)
            self.assertIsNone(row["declaring_compound_statement_id"])
            self.assertEqual(row["support_status"], "unsupported")
            self.assertEqual(row.get("unsupported_reason"),
                             "not_direct_compound_declaration")

    def test_lambda_body_declaration_binds_its_own_scope(self):
        variable, row = self.row("lambda_local")
        _, outer = self.row("enclosing_scope")
        self.assertEqual(row["support_status"], "observed")
        # Lambda bodies may occur more than once in the JSON AST. Bind by ID
        # and structural containment rather than the number of raw occurrences.
        matching = [node for node in _walk(self.root)
                    if node.get("kind") == "CompoundStmt"
                    and node.get("id") == row["declaring_compound_statement_id"]]
        self.assertTrue(matching)
        for scope in matching:
            self.assertTrue(any(declaration.get("id") == variable["id"]
                                for statement in scope.get("inner", [])
                                if statement.get("kind") == "DeclStmt"
                                for declaration in statement.get("inner", [])))
        self.assertNotEqual(row["declaring_compound_statement_id"],
                            outer["declaring_compound_statement_id"])

    def test_trivial_record_distinguishes_destructor_shape(self):
        variable, row = self.row("trivial_local")
        self.assertEqual(row["support_status"], "observed")
        self.assertTrue(row["has_automatic_storage_duration"])
        self.assertFalse(row["has_nontrivial_destructor"])
        self.assertEqual(row["declaring_compound_statement_id"],
                         self.direct_compound(variable)["id"])


if __name__ == "__main__":
    unittest.main()
