"""Composition gates, not source recovery or device execution evidence."""
import unittest
from unittest.mock import patch

from wavebridge.shared_index_check import check
from tests.test_shared_indexing import BINDINGS


class SharedIndexCompositionTests(unittest.TestCase):
    def test_coordinate_failure_prevents_index_check(self):
        for status in ("unknown", "rejected"):
            with patch("wavebridge.shared_index_check.check_coordinates", return_value={"status": status}), \
                    patch("wavebridge.shared_index_check.check_indexing") as indexing:
                result = check({}, {}, {}, {})
            self.assertEqual(result["status"], status)
            indexing.assert_not_called()

    def test_fresh_coordinates_bind_helper_and_forward_all_raw_expressions(self):
        expressions, bindings, abi = {"raw": "expressions"}, dict(BINDINGS), {"int": "abi"}
        coordinate = {"status": "checked", "helper_declaration_id": "helper",
                      "input_sha256": {"root": "hash"},
                      "helper_recovery": {"function_id": "helper", "shared_access_asts": expressions,
                                          "bindings": dict(bindings, value_parameter_id="value", shared_parameter_id="shared"),
                                          "width": 32, "block_threads": 256}}
        for status in ("checked", "unknown", "rejected"):
            with patch("wavebridge.shared_index_check.check_coordinates", return_value=coordinate) as upstream, \
                    patch("wavebridge.shared_index_check.check_indexing",
                          return_value={"status": status, "reason": None}) as indexing:
                result = check({"ast": 1}, {"thread": 2}, abi, {"binding": 3})
            upstream.assert_called_once_with({"ast": 1}, {"thread": 2}, abi, {"binding": 3})
            indexing.assert_called_once_with(expressions, bindings, 32, 256, abi)
            self.assertEqual(result["status"], status)
            self.assertFalse(result["source_program_checked"])
            self.assertFalse(result["deployable"])

    def test_disconnected_helper_is_unknown(self):
        with patch("wavebridge.shared_index_check.check_coordinates", return_value={
                "status": "checked", "helper_declaration_id": "a", "helper_recovery": {"function_id": "b"}}):
            self.assertEqual(check({}, {}, {}, {})["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
