from copy import deepcopy
import unittest

from wavebridge.analysis.reduction_discovery import _callee, discover


def fixture():
    info = {"qualType": "float () noexcept"}
    method = {"kind": "CXXMethodDecl", "id": "method", "storageClass": "static",
              "type": info, "inner": [{"kind": "CompoundStmt", "inner": []}]}
    reference = {"kind": "DeclRefExpr", "valueCategory": "lvalue", "type": info,
                 "referencedDecl": {"kind": "CXXMethodDecl", "id": "method", "type": info}}
    return {"kind": "CallExpr", "inner": [reference]}, {"method": [method]}


class StaticMethodDeclrefTests(unittest.TestCase):
    def test_exact_typed_static_identity_is_not_effect_proof(self):
        call, declarations = fixture()
        result = _callee(call, declarations)
        self.assertEqual(result["callee_id"], "method")
        self.assertEqual(result["dispatch"], "static_method_exact_declref")
        self.assertEqual(result["receiver_semantics"], "not_applicable")

    def test_reference_metadata_and_hidden_children_fail_closed(self):
        for key, value in (("inner", [{"kind": "CallExpr"}]), ("inner", None),
                           ("valueCategory", "prvalue"), ("type", {"qualType": "int ()"})):
            call, declarations = fixture()
            call["inner"][0][key] = value
            self.assertIsNone(_callee(call, declarations)["callee_id"])
        for info in ({}, {"qualType": "float () noexcept", "desugaredQualType": None}):
            call, declarations = fixture()
            call["inner"][0]["referencedDecl"]["type"] = info
            self.assertIsNone(_callee(call, declarations)["callee_id"])

    def test_conflicting_declarations_nonstatic_and_virtual_rejected(self):
        for key, value in (("kind", "FunctionDecl"), ("storageClass", None),
                           ("virtual", True), ("type", {"qualType": "int ()"})):
            call, declarations = fixture()
            conflict = deepcopy(declarations["method"][0])
            conflict[key] = value
            declarations["method"].append(conflict)
            self.assertIsNone(_callee(call, declarations)["callee_id"])
        call, _ = fixture()
        self.assertIsNone(_callee(call, {})["callee_id"])

    def test_identity_does_not_select_between_duplicate_bodies(self):
        call, declarations = fixture()
        method = declarations["method"][0]
        root = {"inner": [{"kind": "FunctionDecl", "id": "entry", "inner": [
                {"kind": "CompoundStmt", "inner": [call]}]}, method, deepcopy(method)]}
        report = discover(root, "entry", 32)
        self.assertEqual(report["reachable_function_ids"], ["entry"])
        self.assertEqual(report["unresolved_calls"][0]["reason"], "callee_unique_definition_not_found")
        self.assertFalse(report["checked"])
        self.assertFalse(report["deployable"])


if __name__ == "__main__":
    unittest.main()
