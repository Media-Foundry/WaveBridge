"""Profile orchestration fixtures, not semantic launch evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments import softmax_launch_native as driver


class SoftmaxLaunchDriverTests(unittest.TestCase):
    def test_host_dimensions_select_by_identity_and_keep_child_unknown(self):
        def ref(identifier):
            return {"kind": "DeclRefExpr", "referencedDecl": {"kind": "VarDecl", "id": identifier}}
        constructor = {"kind": "CXXConstructExpr", "id": "ctor", "inner": [ref("a"), ref("b"), {}]}
        assignment = {"kind": "BinaryOperator", "opcode": "=", "id": "update", "inner": [ref("a"), {}]}
        owner = {"kind": "FunctionDecl", "id": "owner", "inner": [
            {"kind": "VarDecl", "id": "a", "name": "not_warp_size"},
            {"kind": "VarDecl", "id": "b", "name": "not_warps_per_block"}, assignment,
            {"kind": "DeclStmt", "id": "target", "inner": [
                {"kind": "VarDecl", "id": "object", "inner": [constructor]}]}]}
        root = {"kind": "TranslationUnitDecl", "inner": [owner]}
        binding = {"status": "checked", "configuration_slots": [{"position": 1,
            "expression_ast": {"kind": "CXXConstructExpr", "inner": [ref("object")]}}]}
        prefix = "wavebridge.verification.integer_selection."
        with patch(prefix + "check_local_minimum_update", return_value={"status": "unknown"}) as minimum, \
                patch(prefix + "check_minimum_to_statement", return_value={"status": "unknown"}) as history, \
                patch(prefix + "check_minimum_quotient", return_value={"status": "unknown"}) as quotient, \
                patch(prefix + "check_quotient_to_statement", return_value={"status": "unknown"}) as qhistory:
            result = driver.check_host_dimensions(root, binding)
        self.assertEqual(result["status"], "observed")
        self.assertEqual(minimum.call_args.args[:2], (root, "update"))
        self.assertEqual(history.call_args.args[:3], (root, "update", "target"))
        self.assertEqual(quotient.call_args.args[:3], (root, "update", "b"))
        self.assertEqual(qhistory.call_args.args[:4], (root, "update", "b", "target"))
        self.assertTrue(all(c["status"] == "unknown" for c in result["checks"].values()))
        self.assertFalse(result["numeric_domains_established"])
        owner["inner"][0]["inner"] = [{"kind": "CallExpr", "id": "api-call", "inner": [
            {"kind": "ImplicitCastExpr", "inner": [{"kind": "DeclRefExpr",
             "referencedDecl": {"id": "api"}}]}]}]
        with patch(prefix + "check_local_minimum_update", return_value={"status": "checked", "operand_declaration_ids": ["a", "b"]}), \
                patch(prefix + "check_minimum_to_statement", return_value={"status": "unknown"}), \
                patch(prefix + "check_minimum_quotient", return_value={"status": "unknown"}), \
                patch(prefix + "check_quotient_to_statement", return_value={"status": "unknown"}), \
                patch("wavebridge.analysis.integer_constants.evaluate", return_value={"status": "unknown"}) as constants, \
                patch("experiments.softmax_host_api_evidence.observe_call", return_value={"status": "observed"}) as api:
            origins = driver.check_host_dimensions(root, binding)
        api.assert_called_once_with(root, "api-call", "api", "a")
        self.assertEqual([c.args for c in constants.call_args_list], [(root, "a", 32), (root, "b", 32)])
        self.assertEqual(len(origins["operand_initializers"]), 2)
        self.assertEqual(origins["operand_initializers"][0]["declaration_ast"], owner["inner"][0])
        self.assertTrue(all(o["runtime_return_interval"] is None and
                            not o["initial_value_preserved_to_update"] and not o["api_effects_established"]
                            for o in origins["operand_initializers"]))
        self.assertFalse(origins["source_program_checked"])
        duplicate = copy.deepcopy(root)
        duplicate["inner"][0]["inner"].append(copy.deepcopy(assignment))
        rejected = driver.check_host_dimensions(duplicate, binding)
        self.assertEqual(rejected["status"], "unknown")
        self.assertEqual(rejected["reason"], "host_minimum_assignment_not_unique")
        self.assertEqual(rejected["checks"], {})

    def test_copy_source_selection_preserves_exact_identity(self):
        ref = {"kind": "DeclRefExpr", "referencedDecl": {"kind": "VarDecl", "id": "renamed"}}
        binding = {"status": "checked", "configuration_slots": [{"position": 1,
            "expression_ast": {"kind": "CXXConstructExpr", "inner": [
                {"kind": "ImplicitCastExpr", "castKind": "NoOp", "inner": [ref]}]}}]}
        self.assertEqual(driver.selected_copy_source(binding, 1), "renamed")
        bad = copy.deepcopy(binding); bad["status"] = "unknown"
        duplicate = copy.deepcopy(binding); duplicate["configuration_slots"] *= 2
        cast = copy.deepcopy(binding)
        cast["configuration_slots"][0]["expression_ast"]["inner"][0]["castKind"] = "BitCast"
        call = copy.deepcopy(binding)
        call["configuration_slots"][0]["expression_ast"]["inner"] = [{"kind": "CallExpr"}]
        for value in (bad, duplicate, cast, call):
            with self.subTest(value=value), self.assertRaises(ValueError):
                driver.selected_copy_source(value, 1)

    def test_hip_object_check_uses_fresh_slot_and_exact_owner(self):
        root = {"kind": "TranslationUnitDecl", "inner": [{"kind": "FunctionDecl", "id": "owner",
                "inner": [{"kind": "VarDecl", "id": "hip-object"}]}]}
        slot = {"position": 1, "expression_ast": {"kind": "CXXConstructExpr", "inner": [
            {"kind": "DeclRefExpr", "referencedDecl": {"kind": "VarDecl", "id": "hip-object"}}]}}
        binding = {"status": "checked", "configuration_slots": [slot]}
        site = {"launch_id": "launch", "configuration_declaration_id": "config",
                "configuration_arguments": [{"id": str(i)} for i in range(4)]}
        with tempfile.TemporaryDirectory() as directory:
            native, output = Path(directory) / "native", Path(directory) / "report"
            payload = {"ast": root}
            native.write_text(json.dumps({"status": "collected", "payload": payload}))
            with patch.object(driver, "sha", return_value=driver.HIP_NATIVE_SHA), \
                    patch.object(driver, "implementation_hashes", return_value={}), \
                    patch.object(driver, "select_entry", return_value={"id": driver.HIP_KERNEL_ID}), \
                    patch.object(driver, "inspect", return_value={"sites": [site], "unresolved_sites": []}), \
                    patch.object(driver, "check", return_value=binding), \
                    patch("wavebridge.verification.object_use_closure.inspect_structure",
                          return_value={"status": "unknown", "reason": "fixture"}) as fresh:
                result = driver.run(native, output, profile="hip", threads_object=True)
            self.assertEqual(fresh.call_args.args[:2], (payload, "hip-object"))
            self.assertEqual(fresh.call_args.kwargs["instantiated_function_id"], "owner")
            self.assertEqual(result["threads_object_check"]["status"], "unknown")
            self.assertFalse(result["configuration_values_established"])
            self.assertFalse(result["deployable"])

    def test_hip_cannot_use_cuda_only_selections(self):
        options = ("host_minimum_update", "host_minimum_history",
                   "host_minimum_quotient", "host_quotient_history",
                   "constructor_argument_effects", "constructor_field_forwarding")
        for option in options:
            with self.subTest(option=option), self.assertRaisesRegex(ValueError, "cuda_only"):
                driver.run("missing", "unused", profile="hip", **{option: True})

    def test_profile_and_hash_mismatch_stop_before_read(self):
        with self.assertRaisesRegex(ValueError, "unsupported_input_profile"):
            driver.run("missing", "unused", profile="other")
        with patch.object(driver, "sha", return_value=driver.NATIVE_SHA):
            with self.assertRaisesRegex(ValueError, "native_mismatch"):
                driver.run("missing", "unused", profile="hip")

    def test_profiles_bind_their_own_kernel_and_propagate_unknown(self):
        for profile, digest, kernel in (("cuda", driver.NATIVE_SHA, driver.KERNEL_ID),
                                       ("hip", driver.HIP_NATIVE_SHA, driver.HIP_KERNEL_ID)):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as directory:
                native, output = Path(directory) / "native", Path(directory) / "nested/report"
                root = {"kind": "TranslationUnitDecl"}
                native.write_text(json.dumps({"status": "collected", "payload": {"ast": root}}))
                site = {"launch_id": "launch", "configuration_declaration_id": "config",
                        "configuration_arguments": [{"id": str(i)} for i in range(4)]}
                facts = {"sites": [site], "unresolved_sites": [{"reason": "unrelated"}]}
                with patch.object(driver, "sha", return_value=digest), \
                        patch.object(driver, "implementation_hashes", return_value={}), \
                        patch.object(driver, "select_entry", return_value={"id": kernel}), \
                        patch.object(driver, "inspect", return_value=facts) as inspect, \
                        patch.object(driver, "check", return_value={"status": "unknown", "reason": "fixture"}) as check:
                    result = driver.run(native, output, profile=profile)
                inspect.assert_called_once_with(root, kernel)
                self.assertEqual(check.call_args.args[0], root)
                self.assertEqual(check.call_args.args[1]["kernel_declaration_id"], kernel)
                self.assertEqual(result["native_sha256"], digest)
                self.assertEqual(result["check"]["status"], "unknown")
                self.assertEqual(result["launch_discovery"]["unresolved_sites"], facts["unresolved_sites"])
                self.assertFalse(result["configuration_values_established"])
                self.assertFalse(result["lane_family_established"])
                self.assertFalse(result["deployable"])
                self.assertTrue(output.exists())
