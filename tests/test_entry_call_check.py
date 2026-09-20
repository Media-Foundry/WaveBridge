"""Mock recovery plus real getter checks; not whole-program reachability."""
import copy
import unittest
from unittest.mock import patch

from wavebridge.entry_call_check import check
from wavebridge.verification.getter_returns import _hash
from tests.test_getter_returns import fixture, ABI


class EntryCallCheckTests(unittest.TestCase):
    def setUp(self):
        self.root, self.leaf = fixture()
        self.protocol = {"schema_version": "getter-completion-assumptions/v1",
                         "ast_root_sha256": _hash(self.root), "kernel_declaration_id": "kernel",
                         "external_normal_return_assumed": True, "getters": {"start": self.leaf}}
        self.entry = {"status": "recovered", "function_id": "kernel",
                      "call_obligations": [{"declaration_id": "start", "normal_return": "not_established"}]}
        self.chain = {"status": "recovered", "function_id": "kernel", "entry_control": self.entry}

    def run_check(self):
        with patch("wavebridge.entry_call_check.recover_chain", return_value=self.chain):
            return check(self.root, "kernel", 32, ABI, self.protocol)

    def test_real_body_checker_without_claiming_callsite_completion(self):
        result = self.run_check()
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["checks"][0]["getter"]["completion"]["maximum_call_edges"], 2)
        self.assertEqual(result["participation"], "not_established")
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_missing_one_contract_preserves_partial_checks(self):
        self.entry["call_obligations"].insert(0, {"declaration_id": "unbound"})
        result = self.run_check()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual([item["status"] for item in result["checks"]], ["unknown", "checked"])

    def test_stale_root_wrong_kernel_and_no_explicit_return_assumption(self):
        original = copy.deepcopy(self.protocol)
        for key, value in (("ast_root_sha256", "other"), ("kernel_declaration_id", "other"),
                           ("external_normal_return_assumed", 1), ("external_normal_return_assumed", False)):
            self.protocol = {**original, key: value}
            self.assertEqual(self.run_check()["status"], "unknown")

    def test_narrowing_does_not_get_reported_as_nontermination(self):
        self.leaf["upper"] = 1 << 32
        result = self.run_check()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["checks"][0]["getter"]["status"], "rejected")

    def test_no_calls_or_unknown_entry_not_vacuously_checked(self):
        self.entry["call_obligations"] = []
        self.assertEqual(self.run_check()["status"], "unknown")
        self.entry["status"] = "unknown"
        self.assertEqual(self.run_check()["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
