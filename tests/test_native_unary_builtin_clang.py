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

PLUGIN = os.environ.get("WB_UNARY_BUILTIN_PLUGIN", os.environ.get("WB_NATIVE_CAPTURE_PLUGIN"))
COMPILER = os.environ.get("WB_UNARY_BUILTIN_COMPILER", os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++"))
SOURCE = """
float external(float);
float exp_read(float x) { return __builtin_expf(x); }
float log_read(float renamed) { return __builtin_logf(renamed); }
namespace imported { using ::exp_read; }
float routed(float x) { return imported::exp_read(x); }
float increment(float x) { return __builtin_expf(x++); }
float assignment(float x) { return __builtin_expf(x = 1.0f); }
float nested(float x) { return __builtin_expf(external(x)); }
float arithmetic(float x) { return __builtin_expf(x + 1.0f); }
float reference(float& x) { return __builtin_expf(x); }
float volatile_parameter(volatile float x) { return __builtin_expf(x); }
float narrowing(double x) { return __builtin_expf(x); }
float literal() { return __builtin_expf(1.0f); }
float unsupported(float x) { return __builtin_sinf(x); }
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
