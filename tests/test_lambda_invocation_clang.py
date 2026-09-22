"""Real lambda receiver binding; deliberately not a body-effect guarantee."""
import copy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.lambda_invocation import check

FIXTURE = Path(__file__).parent / "fixtures/lambda_invocation.cpp"


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class LambdaInvocationClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(FIXTURE, shutil.which("clang++"), ["-std=c++17"], "direct",
                         full_translation_unit=True, dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]

    def lambdas(self, name, root=None):
        root = self.root if root is None else root
        function = next(n for n in _walk(root) if n.get("kind") == "FunctionDecl"
                        and n.get("name") == name)
        # Lambda bodies also appear under their closure method. Keep one ID
        # for each real expression, without changing the AST checker input.
        return list({n["id"]: n for n in _walk(function)
                     if n.get("kind") == "LambdaExpr"}.values())

    def test_direct_parenthesized_mutable_and_nested_receivers(self):
        for name in ("direct", "parens", "mutable_direct", "nested", "trailing_return", "trailing_void"):
            for node in self.lambdas(name):
                with self.subTest(name=name, lambda_id=node["id"]):
                    report = check(self.root, node["id"])
                    self.assertEqual(report["status"], "checked", report)
                    self.assertFalse(report["source_program_checked"])
                    self.assertFalse(report["deployable"])
                    for obligation in ("reachability", "execution_count", "normal_return",
                                       "body_effects", "capture_or_value_preservation",
                                       "closure_escape_from_body"):
                        self.assertEqual(report[obligation], "not_established")

    def test_named_returned_passed_and_argument_shapes_are_unknown(self):
        for name in ("named", "returned", "passed", "explicit_argument", "default_argument",
                     "generic", "explicit_member"):
            for node in self.lambdas(name):
                with self.subTest(name=name):
                    self.assertEqual(check(self.root, node["id"])["status"], "unknown")

    def test_wrong_callee_and_unsupported_receiver_cannot_check(self):
        for mutation in ("callee_id", "callee_kind", "callee_type", "receiver_cast", "argument"):
            root = copy.deepcopy(self.root)
            node = self.lambdas("direct", root)[0]
            function = next(n for n in _walk(root) if n.get("kind") == "FunctionDecl"
                            and n.get("name") == "direct")
            call = next(n for n in _walk(function) if n.get("kind") == "CXXOperatorCallExpr")
            reference = next(n for n in _walk(call["inner"][0]) if n.get("kind") == "DeclRefExpr")
            if mutation == "callee_id":
                reference["referencedDecl"]["id"] = "not_the_closure_method"
            elif mutation == "callee_kind":
                reference["referencedDecl"]["kind"] = "FunctionDecl"
            elif mutation == "callee_type":
                reference["referencedDecl"]["type"] = {"qualType": "int (int)"}
            elif mutation == "receiver_cast":
                call["inner"][1]["castKind"] = "BitCast"
            else:
                call["inner"].append({"kind": "IntegerLiteral", "value": "7"})
            with self.subTest(mutation=mutation):
                self.assertEqual(check(root, node["id"])["status"], "unknown")

    def test_method_body_conflict_and_unknown_attribute(self):
        for mutation in ("body", "attribute"):
            root = copy.deepcopy(self.root)
            node = self.lambdas("direct", root)[0]
            closure = next(n for n in node["inner"] if n.get("kind") == "CXXRecordDecl")
            method = next(n for n in closure["inner"] if n.get("kind") == "CXXMethodDecl"
                          and n.get("name") == "operator()")
            if mutation == "body":
                body = next(n for n in method["inner"] if n.get("kind") == "CompoundStmt")
                body["inner"].append({"kind": "UnknownEffectStmt"})
            else:
                method["inner"].append({"kind": "UnknownEffectAttr"})
            with self.subTest(mutation=mutation):
                self.assertEqual(check(root, node["id"])["status"], "unknown")

    def test_nested_duplicate_body_conflict_cannot_be_skipped(self):
        root = copy.deepcopy(self.root)
        candidates = self.lambdas("nested", root)
        repeated = [(node, [item for item in _walk(root) if item.get("id") == node["id"]])
                    for node in candidates]
        node, occurrences = next(pair for pair in repeated if len(pair[1]) > 1)
        occurrences[0]["valueCategory"] = "lvalue"
        self.assertEqual(check(root, node["id"])["status"], "unknown")

    def test_display_line_omission_is_not_a_semantic_body_conflict(self):
        for mutation in ("display_line", "offset", "nonlocation_line"):
            root = copy.deepcopy(self.root)
            node = self.lambdas("direct", root)[0]
            closure = next(n for n in node["inner"] if n.get("kind") == "CXXRecordDecl")
            method = next(n for n in closure["inner"] if n.get("name") == "operator()")
            body = next(n for n in method["inner"] if n.get("kind") == "CompoundStmt")
            direct_body = next(n for n in node["inner"] if n.get("kind") == "CompoundStmt")
            if mutation == "display_line":
                body["range"]["begin"]["line"] = 6
                direct_body["range"]["begin"].pop("line", None)
            elif mutation == "offset":
                body["range"]["begin"]["offset"] += 1
            else:
                body["line"] = 6  # Not source-location metadata: must remain strict.
            with self.subTest(mutation=mutation):
                self.assertEqual(check(root, node["id"])["status"],
                                 "checked" if mutation == "display_line" else "unknown")

    def test_binding_does_not_prove_value_preservation_or_reachability(self):
        for name in ("mutating_body", "unreachable"):
            self.assertEqual(check(self.root, self.lambdas(name)[0]["id"])["status"], "checked")
        with tempfile.TemporaryDirectory(prefix="wb-invocation-") as tmp:
            executable = Path(tmp) / "witness"
            compiled = subprocess.run([shutil.which("clang++"), "-std=c++17",
                                       "-DWAVEBRIDGE_INVOCATION_EXECUTION", str(FIXTURE),
                                       "-o", str(executable)], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
            self.assertEqual(executed.returncode, 0, executed.stderr)

    def test_input_immutability_missing_id_and_budget(self):
        before = copy.deepcopy(self.root)
        identifier = self.lambdas("direct")[0]["id"]
        self.assertEqual(check(self.root, identifier)["status"], "checked")
        self.assertEqual(self.root, before)
        for budget in (0, True, 1, 10_000_001):
            self.assertEqual(check(self.root, identifier, max_ast_nodes=budget)["status"], "unknown")
        self.assertEqual(check(self.root, "missing")["status"], "unknown")

    @unittest.skipUnless(os.environ.get("WB_NATIVE_CAPTURE_PLUGIN"), "requires matched native plugin")
    def test_initialization_identity_and_invocation_still_do_not_prove_history(self):
        from wavebridge.frontend.native_captures import collect as native_collect
        from wavebridge.verification.object_initialization import check as initialize
        from wavebridge.capture_source_check import check as capture
        from wavebridge.verification.integer_selection import _hash

        collection = native_collect(FIXTURE, os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++"),
                                    Path(os.environ["WB_NATIVE_CAPTURE_PLUGIN"]), ["-std=c++17"])
        self.assertEqual(collection["status"], "collected", collection)
        payload = collection["payload"]
        root = payload["ast"]
        function = next(n for n in _walk(root) if n.get("kind") == "FunctionDecl"
                        and n.get("name") == "mutating_body")
        source = next(n for n in _walk(function) if n.get("kind") == "VarDecl"
                      and n.get("name") == "source")
        target = next(n for n in _walk(function) if n.get("kind") == "VarDecl"
                      and n.get("name") == "target")
        expression = next(n for n in _walk(target) if n.get("kind") == "CXXConstructExpr")
        abi = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False}}
        initial = initialize(payload, source["id"], abi, {})
        self.assertEqual(initial["status"], "checked", initial)
        self.assertEqual(initial["fields"][0]["value"], 3)
        protocol = {
            "schema_version": "capture-source-assumptions/v1", "root_sha256": _hash(root),
            "copy_expression_id": expression["id"], "source_declaration_id": source["id"],
            "source_initialized_alive_assumed": True,
            "closure_instances_from_recorded_lambdas_assumed": True,
            "source_and_closures_share_recorded_activation_assumed": True,
            "source_program_valid_assumed": True,
            "evidence_reference": "explicit test assumptions; not a checked dynamic history",
        }
        identity = capture(payload, expression["id"], abi, protocol)
        self.assertEqual(identity["status"], "checked", identity)
        self.assertEqual(identity["source_object_preservation"], "not_established")
        invocation = check(root, self.lambdas("mutating_body", root)[0]["id"])
        self.assertEqual(invocation["status"], "checked", invocation)
        self.assertEqual(invocation["capture_or_value_preservation"], "not_established")
        # The CPU witness in the adjacent test returns 99, not initial value 3.
        # Three local checks cannot be composed into an unproved history claim.
