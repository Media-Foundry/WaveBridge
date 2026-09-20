import unittest

from wavebridge.analysis.launch_facts import inspect


def ref(identifier):
    return {"kind": "DeclRefExpr", "referencedDecl": {"id": identifier, "kind": "FunctionDecl"}}


def launch(identifier="kernel"):
    return {"kind": "CUDAKernelCallExpr", "inner": [ref(identifier),
            {"kind": "CallExpr", "inner": [ref("configure"), *[
                {"kind": "IntegerLiteral", "value": str(index)} for index in range(4)]]},
            {"kind": "DeclRefExpr", "referencedDecl": {"id": "input", "kind": "VarDecl"}}]}


class LaunchFactTests(unittest.TestCase):
    def test_retains_configuration_and_kernel_arguments_without_values(self):
        report = inspect({"inner": [launch(), launch("unrelated")]}, "kernel")
        self.assertEqual(report["status"], "evidence")
        self.assertEqual(report["other_kernel_sites"], 1)
        self.assertEqual(len(report["sites"][0]["configuration_arguments"]), 4)
        self.assertEqual(len(report["sites"][0]["kernel_arguments"]), 1)
        self.assertEqual(report["sites"][0]["argument_values"], "not_evaluated")
        self.assertFalse(report["checked"])

    def test_indirect_and_casted_targets_do_not_match_by_argument_name(self):
        node = launch()
        node["inner"][0] = {"kind": "DeclRefExpr", "referencedDecl": {"id": "pointer", "kind": "VarDecl"}}
        node["inner"].append(ref("kernel"))
        report = inspect({"inner": [node]}, "kernel")
        self.assertFalse(report["sites"])
        self.assertEqual(report["unresolved_sites"][0]["reason"], "kernel_not_exact_declref")
        node["inner"][0] = {"kind": "ImplicitCastExpr", "castKind": "BitCast", "inner": [ref("kernel")]}
        self.assertFalse(inspect({"inner": [node]}, "kernel")["sites"])

    def test_incomplete_configuration_remains_unknown(self):
        node = launch()
        node["inner"][1]["inner"].pop()
        report = inspect({"inner": [node]}, "kernel")
        self.assertEqual(report["unresolved_sites"][0]["reason"], "unsupported_configuration_call")
        self.assertEqual(inspect([], "kernel")["reason"], "invalid_input")
        node["inner"][1]["inner"] = None
        self.assertEqual(inspect({"inner": [node]}, "kernel")["status"], "unknown")
        node["inner"] = None
        self.assertEqual(inspect({"inner": [node]}, "kernel")["status"], "unknown")

    def test_formal_parameters_bind_by_exact_definition_and_position(self):
        definition = {"kind": "FunctionDecl", "id": "kernel", "inner": [
            {"kind": "ParmVarDecl", "id": "formal", "type": {"qualType": "float *"}},
            {"kind": "CompoundStmt", "inner": []}]}
        tree = {"inner": [definition, launch()]}
        site = inspect(tree, "kernel")["sites"][0]
        self.assertEqual(site["parameter_binding_status"], "bound_by_position")
        self.assertEqual(site["parameter_bindings"][0]["parameter_declaration_id"], "formal")
        tree["inner"][1]["inner"].append(ref("extra"))
        self.assertEqual(inspect(tree, "kernel")["sites"][0]["parameter_binding_reason"],
                         "kernel_argument_count_mismatch")
        tree["inner"].append(definition)
        self.assertEqual(inspect(tree, "kernel")["sites"][0]["parameter_binding_reason"],
                         "unique_kernel_definition_not_found")


if __name__ == "__main__":
    unittest.main()
