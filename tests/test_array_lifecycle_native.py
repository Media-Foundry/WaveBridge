"""Native lifecycle evidence for a restricted array-helper functor."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk
from wavebridge.frontend.native_captures import collect
from wavebridge.verification.array_call_effects import check


PLUGIN = os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")

SOURCE = r"""
int global_counter;

template <typename T> struct Max {
  T operator()(T a, T b) const { return a < b ? b : a; }
};
struct UserConstructor {
  UserConstructor() { ++global_counter; }
  float operator()(float a, float b) const { return a < b ? b : a; }
};
struct UserDestructor {
  ~UserDestructor() { ++global_counter; }
  float operator()(float a, float b) const { return a < b ? b : a; }
};
struct HasField {
  int state;
  float operator()(float a, float b) const { return a < b ? b : a; }
};
struct EmptyBase {};
struct HasBase : EmptyBase {
  float operator()(float a, float b) const { return a < b ? b : a; }
};

void max_helper(float *data) {
  Max<float> operation;
  data[0] = operation(data[0], 1.0f);
}
void constructor_helper(float *data) {
  UserConstructor operation;
  data[0] = operation(data[0], 1.0f);
}
void destructor_helper(float *data) {
  UserDestructor operation;
  data[0] = operation(data[0], 1.0f);
}
void field_helper(float *data) {
  HasField operation{};
  data[0] = operation(data[0], 1.0f);
}
void base_helper(float *data) {
  HasBase operation;
  data[0] = operation(data[0], 1.0f);
}

void max_caller() {
  int protected_value = 7; float buffer[8] = {}; max_helper(buffer);
  (void)protected_value;
}
void constructor_caller() {
  int protected_value = 7; float buffer[8] = {}; constructor_helper(buffer);
}
void destructor_caller() {
  int protected_value = 7; float buffer[8] = {}; destructor_helper(buffer);
}
void field_caller() {
  int protected_value = 7; float buffer[8] = {}; field_helper(buffer);
}
void base_caller() {
  int protected_value = 7; float buffer[8] = {}; base_helper(buffer);
}
"""


@unittest.skipUnless(PLUGIN, "requires compiler-matched native observation plugin")
class ArrayLifecycleNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-array-lifecycle-")
        cls.source = Path(cls.temporary.name) / "array_lifecycle.cpp"
        cls.source.write_text(SOURCE, encoding="utf-8")
        report = collect(cls.source, COMPILER, Path(PLUGIN), ["-std=c++17"])
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.payload = report["payload"]
        cls.root = cls.payload["ast"]
        for field in ("local_record_objects", "constructor_calls"):
            if not isinstance(cls.payload.get(field), list):
                raise AssertionError(f"native payload has no {field} list")
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def function(self, name):
        matches = [node for node in self.functions if node.get("name") == name and
                   any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                       for child in node.get("inner", []))]
        self.assertEqual(len(matches), 1, name)
        return matches[0]

    def inputs(self, caller):
        function = self.function(caller)
        calls = [node for node in _walk(function) if node.get("kind") == "CallExpr"]
        protected = [node for node in _walk(function)
                     if node.get("kind") == "VarDecl" and
                     node.get("name") == "protected_value"]
        self.assertEqual(len(calls), 1, caller)
        self.assertEqual(len(protected), 1, caller)
        return calls[0]["id"], protected[0]["id"]

    def run_check(self, caller, payload=None):
        selected = self.payload if payload is None else payload
        call_id, protected_id = self.inputs(caller)
        return check(selected["ast"], call_id, protected_id,
                     use_scalar_operators=True, native_payload=selected)

    def operation(self, helper="max_helper"):
        matches = [node for node in _walk(self.function(helper))
                   if node.get("kind") == "VarDecl" and node.get("name") == "operation"]
        self.assertEqual(len(matches), 1, helper)
        return matches[0]

    def observations(self, helper="max_helper"):
        variable = self.operation(helper)
        locals_ = [row for row in self.payload["local_record_objects"]
                   if row.get("variable_declaration_id") == variable["id"]]
        constructors = [node for node in _walk(variable)
                        if node.get("kind") == "CXXConstructExpr"]
        self.assertEqual(len(locals_), 1, (helper, locals_))
        self.assertEqual(len(constructors), 1, (helper, constructors))
        calls = [row for row in self.payload["constructor_calls"]
                 if row.get("expression_id") == constructors[0]["id"]]
        self.assertEqual(len(calls), 1, (helper, calls))
        return variable, locals_[0], calls[0]

    def test_empty_template_functor_closes_operator_and_lifecycle_effects(self):
        result = self.run_check("max_caller")
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["explicit_write_targets_checked"])
        self.assertTrue(result["protected_storage_preserved"])
        self.assertEqual(result["pending_effects"], [])
        self.assertEqual(len(result["scalar_operator_checks"]), 1)
        self.assertEqual(len(result["local_lifecycle_checks"]), 1)
        lifecycle = result["local_lifecycle_checks"][0]
        self.assertEqual(lifecycle["status"], "checked")
        self.assertEqual(lifecycle["scope"],
                         "own_trivial_empty_object_ctor_and_dtor_effects")
        self.assertFalse(lifecycle["lifetime_history_checked"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_user_constructor_destructor_field_and_base_remain_unknown(self):
        for caller in ("constructor_caller", "destructor_caller", "field_caller",
                       "base_caller"):
            with self.subTest(caller=caller):
                result = self.run_check(caller)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["protected_storage_preserved"])

    def test_missing_or_duplicate_local_and_constructor_observations_fail_closed(self):
        variable, local, constructor = self.observations()
        cases = []
        missing_local = deepcopy(self.payload)
        missing_local["local_record_objects"] = [
            row for row in missing_local["local_record_objects"]
            if row.get("variable_declaration_id") != variable["id"]]
        cases.append(("missing_local", missing_local))
        duplicate_local = deepcopy(self.payload)
        duplicate_local["local_record_objects"].append(deepcopy(local))
        cases.append(("duplicate_local", duplicate_local))
        missing_constructor = deepcopy(self.payload)
        missing_constructor["constructor_calls"] = [
            row for row in missing_constructor["constructor_calls"]
            if row.get("expression_id") != constructor["expression_id"]]
        cases.append(("missing_constructor", missing_constructor))
        duplicate_constructor = deepcopy(self.payload)
        duplicate_constructor["constructor_calls"].append(deepcopy(constructor))
        cases.append(("duplicate_constructor", duplicate_constructor))
        for name, payload in cases:
            with self.subTest(name=name):
                result = self.run_check("max_caller", payload)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["protected_storage_preserved"])

    def test_misbound_record_constructor_and_triviality_flags_fail_closed(self):
        variable, local, constructor = self.observations()
        field_variable = self.operation("field_helper")
        field_rows = [row for row in self.payload["local_record_objects"]
                      if row.get("variable_declaration_id") == field_variable["id"]]
        self.assertEqual(len(field_rows), 1)
        other_local = field_rows[0]
        _, _, other_constructor = self.observations("constructor_helper")
        cases = []
        wrong_record = deepcopy(self.payload)
        next(row for row in wrong_record["local_record_objects"]
             if row.get("variable_declaration_id") == variable["id"])["record_declaration_id"] = (
                 other_local["record_declaration_id"])
        cases.append(("wrong_record", wrong_record))
        wrong_constructor = deepcopy(self.payload)
        next(row for row in wrong_constructor["constructor_calls"]
             if row.get("expression_id") == constructor["expression_id"])[
                 "constructor_declaration_id"] = other_constructor["constructor_declaration_id"]
        cases.append(("wrong_constructor", wrong_constructor))
        nontrivial_constructor = deepcopy(self.payload)
        next(row for row in nontrivial_constructor["constructor_calls"]
             if row.get("expression_id") == constructor["expression_id"])["is_trivial"] = False
        cases.append(("nontrivial_constructor", nontrivial_constructor))
        nontrivial_destructor = deepcopy(self.payload)
        next(row for row in nontrivial_destructor["local_record_objects"]
             if row.get("variable_declaration_id") == variable["id"])[
                 "has_nontrivial_destructor"] = True
        cases.append(("nontrivial_destructor", nontrivial_destructor))
        for name, payload in cases:
            with self.subTest(name=name):
                result = self.run_check("max_caller", payload)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["protected_storage_preserved"])

    def test_without_native_payload_old_unknown_behavior_is_preserved(self):
        call_id, protected_id = self.inputs("max_caller")
        result = check(self.root, call_id, protected_id, use_scalar_operators=True)
        self.assertEqual(result["status"], "unknown", result)
        self.assertFalse(result["protected_storage_preserved"])


if __name__ == "__main__":
    unittest.main()
