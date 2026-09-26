"""Real-Clang coverage for direct references to static C++ methods.

These tests establish only exact syntactic call edges.  In particular, an
external leaf is not treated as pure and no return-value meaning is inferred
from any spelling used below.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.analysis.reduction_discovery import discover
from wavebridge.frontend.clang_ast import _walk, collect


CLANG = shutil.which("clang++")

SOURCE = r"""
int external_leaf(int);

namespace renamed_space {
struct RenamedOps {
  static int transformed(int value) { return external_leaf(value); }
  static int transformed(double value) { return static_cast<int>(value) + 70; }
  int instance(int value) { return value + 1; }
  virtual int dynamic(int value) { return value + 2; }
};

struct SimilarButUncalled {
  static int transformed(int value) { return value + 90; }
};
}

int selected_entry(int value) {
  renamed_space::RenamedOps object;
  int first = renamed_space::RenamedOps::transformed(value);
  int second = object.instance(value);
  int third = object.dynamic(value);
  return first + second + third;
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class StaticMethodDeclRefClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.source = Path(cls.temporary.name) / "static_method_declref.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "selected_entry",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        definitions = [node for node in _walk(cls.root)
                       if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"} and
                       any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                           for child in node.get("inner", []))]
        cls.entry = next(node for node in definitions
                         if node.get("kind") == "FunctionDecl" and
                         node.get("name") == "selected_entry")
        cls.methods = [node for node in definitions if node.get("kind") == "CXXMethodDecl"]
        cls.report = discover(cls.root, cls.entry["id"], 32)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def method(self, owner, name, parameter_type):
        matches = []
        for node in self.methods:
            if node.get("name") != name:
                continue
            parameters = [child for child in node.get("inner", [])
                          if isinstance(child, dict) and child.get("kind") == "ParmVarDecl"]
            if len(parameters) != 1 or parameters[0].get("type", {}).get("qualType") != parameter_type:
                continue
            # Parent ownership is checked from the full AST rather than from a
            # method name, which deliberately collides in this fixture.
            for record in _walk(self.root):
                if record.get("kind") == "CXXRecordDecl" and record.get("name") == owner:
                    if any(child is node for child in record.get("inner", [])):
                        matches.append(node)
        self.assertEqual(len(matches), 1, (owner, name, parameter_type))
        return matches[0]

    def test_qualified_static_overload_is_exact_direct_edge(self):
        selected = self.method("RenamedOps", "transformed", "int")
        overload = self.method("RenamedOps", "transformed", "double")
        similar = self.method("SimilarButUncalled", "transformed", "int")
        edges = [edge for edge in self.report["call_edges"]
                 if edge["dispatch"] == "static_method_exact_declref"]
        self.assertEqual([edge["callee_id"] for edge in edges], [selected["id"]])
        self.assertNotEqual(selected["id"], overload["id"])
        self.assertNotEqual(selected["id"], similar["id"])
        self.assertIn(selected["id"], self.report["reachable_function_ids"])
        self.assertNotIn(overload["id"], self.report["reachable_function_ids"])
        self.assertNotIn(similar["id"], self.report["reachable_function_ids"])

    def test_external_leaf_remains_unresolved_and_has_no_purity_claim(self):
        selected = self.method("RenamedOps", "transformed", "int")
        outgoing = [edge for edge in self.report["call_edges"]
                    if edge["caller_id"] == selected["id"]]
        self.assertEqual(len(outgoing), 1, outgoing)
        leaf_id = outgoing[0]["callee_id"]
        self.assertEqual(outgoing[0]["dispatch"], "direct_free_function")
        unresolved = [item for item in self.report["unresolved_calls"]
                      if item.get("callee_id") == leaf_id]
        self.assertEqual(len(unresolved), 1, self.report["unresolved_calls"])
        self.assertEqual(unresolved[0]["reason"], "callee_unique_definition_not_found")
        self.assertFalse(self.report["analysis_complete"])
        self.assertEqual(self.report["external_call_semantics"], "not_established")
        self.assertFalse(self.report["checked"])
        self.assertFalse(self.report["deployable"])

    def test_instance_and_virtual_calls_do_not_use_static_declref_dispatch(self):
        instance = self.method("RenamedOps", "instance", "int")
        dynamic = self.method("RenamedOps", "dynamic", "int")
        static_ids = {edge["callee_id"] for edge in self.report["call_edges"]
                      if edge["dispatch"] == "static_method_exact_declref"}
        self.assertNotIn(instance["id"], static_ids)
        self.assertNotIn(dynamic["id"], static_ids)
        reasons = {item.get("reason") for item in self.report["unresolved_calls"]}
        self.assertIn("member_dispatch_not_proven_static", reasons)
        self.assertIn("dynamic_virtual_member_call", reasons)


if __name__ == "__main__":
    unittest.main()
