"""Real native unary builtin observations; mutation cases are explicit fixtures."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest

from wavebridge.frontend.native_captures import collect
from wavebridge.frontend.clang_ast import _walk
from wavebridge.verification.builtin_calls import inspect_structure, check_no_memory_write
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.scalar_forwarding import inspect_builtin_structure
from wavebridge.verification.scalar_call_effects import inspect_native_call

PLUGIN = os.environ.get("WB_UNARY_BUILTIN_PLUGIN", os.environ.get("WB_NATIVE_CAPTURE_PLUGIN"))
COMPILER = os.environ.get("WB_UNARY_BUILTIN_COMPILER", os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++"))
SOURCE = """
float external(float);
float exp_read(float x) { return __builtin_expf(x); }
float log_read(float renamed) { return __builtin_logf(renamed); }
namespace imported { using ::exp_read; }
float routed(float x) { return imported::exp_read(x); }
float alternate(float x) { return __builtin_expf(x); }
float writing_wrapper(float x) { x += 1.0f; return exp_read(x); }
float changed_argument(float x) { return exp_read(x + 1.0f); }
float increment(float x) { return __builtin_expf(x++); }
float assignment(float x) { return __builtin_expf(x = 1.0f); }
float nested(float x) { return __builtin_expf(external(x)); }
float arithmetic(float x) { return __builtin_expf(x + 1.0f); }
float reference(float& x) { return __builtin_expf(x); }
float volatile_parameter(volatile float x) { return __builtin_expf(x); }
float narrowing(double x) { return __builtin_expf(x); }
float literal() { return __builtin_expf(1.0f); }
float unsupported(float x) { return __builtin_sinf(x); }
float outer_read(float x) { return routed(x); }
float outer_array(int i, float x) { float a[4] = {}; return routed(a[i] - x); }
float outer_pointer_array(float* a, int i) { return routed(a[i]); }
float outer_log(float x) { return log_read(x); }
float outer_increment(float x) { return routed(x++); }
float outer_assignment(float x) { return routed(x = 1.0f); }
float outer_nested(float x) { return routed(external(x)); }
float outer_comma(float x) { return (x++, routed)(x); }
float outer_pointer(float x, float (*p)(float)) { return p(x); }
float outer_writing(float x) { return writing_wrapper(x); }
"""


@unittest.skipUnless(PLUGIN, "requires compiler-matched native plugin")
class NativeUnaryBuiltinClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-unary-native-")
        source = Path(cls.temporary.name) / "unary.cpp"
        source.write_text(SOURCE)
        report = collect(source, COMPILER, Path(PLUGIN), ["-std=c++17"])
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.payload = report["payload"]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def call(self, name, payload=None):
        payload = self.payload if payload is None else payload
        function = next(node for node in payload["ast"]["inner"]
                        if node.get("kind") == "FunctionDecl" and node.get("name") == name)
        return next(node for node in _walk(function) if node.get("kind") == "CallExpr")

    def inspect(self, name, payload=None, **kwargs):
        payload = self.payload if payload is None else payload
        return inspect_structure(payload, self.call(name, payload)["id"], **kwargs)

    def forward(self, start="routed", leaf="exp_read", payload=None, **kwargs):
        payload = self.payload if payload is None else payload
        declaration = next(n for n in payload["ast"]["inner"]
                           if n.get("kind") == "FunctionDecl" and n.get("name") == start)
        return inspect_builtin_structure(payload, declaration["id"], self.call(leaf, payload)["id"],
                                         allow_using_shadows=True, **kwargs)

    def test_wrapper_chain_freshly_binds_native_terminal_and_parameter_flow(self):
        before = _hash(self.payload)
        result = self.forward()
        self.assertEqual(result["status"], "checked", result)
        edges = result["forwarding_check"]["call_edges"]
        self.assertEqual(len(edges), 2)
        self.assertEqual(edges[-1]["call_expression_id"], self.call("exp_read")["id"])
        self.assertEqual(edges[-1]["source_parameter_id"],
                         result["native_leaf_structure"]["argument_read_declaration_id"])
        self.assertFalse(result["outer_argument_effects_checked"])
        self.assertFalse(result["deployable"])
        self.assertEqual(result["effect_semantics"], "not_established")
        child = result["forwarding_check"]
        self.assertEqual(child["terminal_mode"], "native_builtin")
        self.assertEqual(child["schema_version"], "scalar-native-forwarding-chain/v1")
        for key in ("native_envelope", "native_leaf_call", "builtin_structure_policy"):
            self.assertEqual(child["input_sha256"][key], result["input_sha256"][key])
        self.assertTrue(result["assumptions"])
        self.assertTrue(result["limitations"])
        self.assertEqual(before, _hash(self.payload))

    def test_other_native_call_with_same_builtin_cannot_close_chain(self):
        result = self.forward(leaf="alternate")
        self.assertEqual(result["native_leaf_structure"]["status"], "checked")
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(self.forward(leaf="log_read")["status"], "unknown")

    def test_wrapper_mutation_or_changed_forwarded_expression_stays_unknown(self):
        for start in ("writing_wrapper", "changed_argument"):
            with self.subTest(start=start):
                self.assertEqual(self.forward(start=start)["status"], "unknown")

    def test_native_read_of_another_parameter_cannot_be_spliced_into_wrapper(self):
        payload = deepcopy(self.payload)
        other = self.call("log_read", payload)["inner"][1]["inner"][0]["referencedDecl"]
        call_id = self.call("exp_read", payload)["id"]
        # Mutate all repeated representations consistently: identity matching is
        # not the property under test; current-wrapper parameter binding is.
        for node in _walk(payload["ast"]):
            if node.get("id") == call_id:
                node["inner"][1]["inner"][0]["referencedDecl"] = deepcopy(other)
        result = self.forward(payload=payload)
        self.assertEqual(result["native_leaf_structure"]["status"], "checked", result)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "native_argument_not_current_parameter")

    def test_native_forwarding_rejects_bad_budget_and_missing_id(self):
        self.assertEqual(self.forward(max_ast_nodes=1)["status"], "unknown")
        result = inspect_builtin_structure(self.payload, "missing", self.call("exp_read")["id"],
                                           allow_using_shadows=True)
        self.assertEqual(result["status"], "unknown")

    def protocol(self, name, payload=None):
        payload = self.payload if payload is None else payload
        call = self.call(name, payload)
        record = next(r for r in payload["builtin_calls"] if r["call_expression_id"] == call["id"])
        return {"schema_version": "builtin-leaf-effect-assumption/v1",
                "native_envelope_sha256": _hash(payload), "call_expression_id": call["id"],
                "callee_declaration_id": record["callee_declaration_id"],
                "builtin_no_memory_write_assumed": True,
                "valid_call_and_normal_return_assumed": True,
                "evidence_reference": "test assumption; not compiler or runtime certification"}

    def outer(self, name="outer_read", leaf="exp_read", payload=None, **kwargs):
        payload = self.payload if payload is None else payload
        return inspect_native_call(payload, self.call(name, payload)["id"],
                                   self.call(leaf, payload)["id"], **kwargs)

    def test_outer_argument_and_native_chain_are_freshly_bound_not_callee_effects(self):
        before = _hash(self.payload)
        for name in ("outer_read", "outer_array"):
            result = self.outer(name, allow_using_shadows=True)
            self.assertEqual(result["status"], "checked", result)
            self.assertTrue(result["argument_evaluation_no_memory_write_checked"])
            self.assertEqual(result["argument_check"]["status"], "checked")
            self.assertEqual(result["forwarding_check"]["status"], "checked")
            self.assertEqual(result["call_binding"]["call_expression_id"], self.call(name)["id"])
            for flag in ("callee_effects_checked", "whole_call_no_memory_write_checked",
                         "numeric_contract_checked", "source_program_checked", "deployable"):
                self.assertFalse(result[flag])
            self.assertEqual(result["value_semantics"], "not_established")
            self.assertEqual(result["input_sha256"]["outer_call_expression_id"],
                             _hash(self.call(name)["id"]))
            self.assertEqual(result["input_sha256"]["outer_argument_expression_id"],
                             _hash(self.call(name)["inner"][1]["id"]))
            for key, value in result["forwarding_check"]["input_sha256"].items():
                self.assertEqual(result["input_sha256"][key], value)
        self.assertEqual(before, _hash(self.payload))

    def test_outer_side_effects_and_unsupported_callees_are_unknown(self):
        for name in ("outer_increment", "outer_assignment", "outer_nested",
                     "outer_comma", "outer_pointer", "outer_pointer_array"):
            with self.subTest(name=name):
                result = self.outer(name, allow_using_shadows=True)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["argument_evaluation_no_memory_write_checked"])

    def test_outer_safe_argument_does_not_certify_bad_wrapper_or_wrong_native_leaf(self):
        for options in ({"name": "outer_writing"}, {"leaf": "alternate"}, {"leaf": "log_read"}):
            result = self.outer(**options, allow_using_shadows=True)
            self.assertEqual(result["status"], "unknown", result)
            self.assertTrue(result["argument_evaluation_no_memory_write_checked"])
            self.assertFalse(result["whole_call_no_memory_write_checked"])

    def test_outer_duplicate_or_missing_identity_and_bad_options_stay_unknown(self):
        payload = deepcopy(self.payload)
        payload["ast"]["inner"].append(deepcopy(self.call("outer_read", payload)))
        self.assertEqual(self.outer(payload=payload, allow_using_shadows=True)["status"], "unknown")
        for options in ({"max_ast_nodes": 1}, {"max_ast_nodes": True}, {"allow_using_shadows": 1}):
            self.assertEqual(self.outer(**options)["status"], "unknown")
        self.assertEqual(inspect_native_call(self.payload, "missing", "missing")["status"], "unknown")

    def test_outer_rechecks_native_record_and_binds_identity_policy(self):
        payload = deepcopy(self.payload)
        record = next(r for r in payload["builtin_calls"]
                      if r["call_expression_id"] == self.call("exp_read")["id"])
        record["callee_declaration_id"] = "wrong"
        self.assertEqual(self.outer(payload=payload, allow_using_shadows=True)["status"], "unknown")
        # log_read has no using declaration, so both policies can check it.
        strict = self.outer("outer_log", leaf="log_read")
        enabled = self.outer("outer_log", leaf="log_read", allow_using_shadows=True)
        self.assertEqual(strict["status"], "checked", strict)
        self.assertEqual(enabled["status"], "checked", enabled)
        self.assertNotEqual(strict["input_sha256"]["outer_identity_policy"],
                            enabled["input_sha256"]["outer_identity_policy"])
        self.assertEqual(strict["input_sha256"]["outer_identity_policy"], _hash(strict["identity_policy"]))

    def test_exact_native_identity_and_plain_parameter_read_are_opt_in(self):
        before = _hash(self.payload)
        for name in ("exp_read", "log_read"):
            with self.subTest(name=name):
                self.assertEqual(self.inspect(name)["status"], "unknown")
                result = self.inspect(name, allow_unary_float=True, allow_using_shadows=True)
                self.assertEqual(result["status"], "checked", result)
                self.assertEqual(result["argument_structure"], "plain_float_parameter_read")
                self.assertEqual(result["effect_semantics"], "not_established")
                self.assertEqual(result["value_semantics"], "not_established")
                self.assertFalse(result["deployable"])
        self.assertEqual(before, _hash(self.payload))

    def test_writing_and_unsupported_argument_shapes_remain_unknown(self):
        for name in ("increment", "assignment", "nested", "arithmetic", "reference",
                     "volatile_parameter", "narrowing", "literal", "unsupported"):
            with self.subTest(name=name):
                result = self.inspect(name, allow_unary_float=True, allow_using_shadows=True)
                self.assertEqual(result["status"], "unknown", result)

    def test_effect_requires_exact_external_protocol_and_does_not_hide_argument_writes(self):
        for name in ("log_read", "increment"):
            result = check_no_memory_write(self.payload, self.call(name)["id"], self.protocol(name),
                                           allow_unary_float=True, allow_using_shadows=True)
            self.assertEqual(result["status"], "checked" if name == "log_read" else "unknown", result)
            self.assertFalse(result["external_leaf_effect_verified"])
            self.assertFalse(result["deployable"])
        for replacement in (None, {}, {**self.protocol("log_read"), "builtin_no_memory_write_assumed": 1}):
            result = check_no_memory_write(self.payload, self.call("log_read")["id"], replacement,
                                           allow_unary_float=True, allow_using_shadows=True)
            self.assertEqual(result["status"], "unknown")

    def test_native_metadata_misbindings_and_duplicate_records_are_unknown(self):
        for field in ("callee_declaration_id", "argument_expression_ids", "builtin_id", "duplicate"):
            payload = deepcopy(self.payload)
            record = next(r for r in payload["builtin_calls"] if r["call_expression_id"] == self.call("log_read")["id"])
            if field == "duplicate":
                payload["builtin_calls"].append(deepcopy(record))
            else:
                record[field] = [] if field == "argument_expression_ids" else True if field == "builtin_id" else "wrong"
            with self.subTest(field=field):
                self.assertEqual(self.inspect("log_read", payload, allow_unary_float=True)["status"], "unknown")

    def test_parameter_and_reference_type_conflicts_are_unknown(self):
        for target in ("declaration", "reference"):
            payload = deepcopy(self.payload)
            argument = self.call("log_read", payload)["inner"][1]
            reference = argument["inner"][0]["referencedDecl"]
            if target == "reference":
                reference["type"] = {"qualType": "float &"}
            else:
                declaration = next(n for n in _walk(payload["ast"]) if n.get("id") == reference["id"])
                declaration["type"] = {"qualType": "float &"}
            self.assertEqual(self.inspect("log_read", payload, allow_unary_float=True)["status"], "unknown")

    def test_policy_hash_and_option_budget_boundaries(self):
        strict = self.inspect("log_read", allow_unary_float=True)
        shadow = self.inspect("log_read", allow_unary_float=True, allow_using_shadows=True)
        self.assertEqual(strict["status"], "checked", strict)
        self.assertNotEqual(strict["input_sha256"]["structure_policy"], shadow["input_sha256"]["structure_policy"])
        for options in ({"allow_unary_float": 1}, {"allow_unary_float": True, "allow_using_shadows": 1},
                        {"allow_unary_float": True, "max_ast_nodes": 1}):
            self.assertEqual(self.inspect("log_read", **options)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
