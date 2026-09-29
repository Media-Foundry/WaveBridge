"""Profile orchestration fixtures, not semantic launch evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments import softmax_launch_native as driver


class SoftmaxLaunchDriverTests(unittest.TestCase):
    def test_hip_cannot_use_cuda_only_selections(self):
        options = ("threads_object", "host_minimum_update", "host_minimum_history",
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
