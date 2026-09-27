"""Mock-marked orchestration tests for the softmax builtin-effects driver.

These fixtures test profile/hash selection and checker dispatch only. They are
not native Clang captures, source recovery evidence, or GPU results.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments import softmax_builtin_effects as driver


def node(identifier, kind, **fields):
    return {"id": identifier, "kind": kind, "inner": [], **fields}


def orchestration_fixture():
    inside = node("call-inside", "CallExpr")
    outside = node("call-outside", "CallExpr")
    loop = node("loop", "ForStmt", inner=[node("break", "BreakStmt"), inside])
    entry = node("entry", "FunctionDecl", name="selected", inner=[outside, loop])
    root = node("tu", "TranslationUnitDecl", inner=[entry])
    builtins = [
        {"call_expression_id": "call-inside", "callee_declaration_id": "decl-inside",
         "builtin_id": 1, "builtin_name": "__builtin_huge_valf",
         "argument_expression_ids": []},
        {"call_expression_id": "call-outside", "callee_declaration_id": "decl-outside",
         "builtin_id": 2, "builtin_name": "__builtin_nanf",
         "argument_expression_ids": []},
    ]
    return {"status": "collected", "payload": {"ast": root, "builtin_calls": builtins}}, entry


class SoftmaxBuiltinEffectsDriverTests(unittest.TestCase):
    def test_invalid_profile_and_non_boolean_option_are_rejected_before_io(self):
        for profile, guarded in (("unknown", False), ("cuda-sm80", 1),
                                 ("hip-gfx1100", None)):
            with self.subTest(profile=profile, guarded=guarded), \
                    patch.object(driver, "sha", side_effect=AssertionError("must not hash")), \
                    self.assertRaises(ValueError):
                driver.run("missing-native", "missing-output",
                           profile=profile, guarded_work=guarded)

    def test_native_hash_cannot_be_reused_across_profiles(self):
        with tempfile.TemporaryDirectory(prefix="wb-builtin-driver-") as temporary:
            native = Path(temporary) / "native.json"
            native.write_text("{}")
            output = Path(temporary) / "report.json"
            with patch.object(driver, "sha", return_value=driver.NATIVE_SHA), \
                    self.assertRaisesRegex(ValueError, "native_input_mismatch"):
                driver.run(native, output, profile="hip-gfx1100")
            self.assertFalse(output.exists())

    def run_fixture(self, temporary, *, guarded_work):
        source, entry = orchestration_fixture()
        native = Path(temporary) / "native.json"
        native.write_text(json.dumps(source))
        output = Path(temporary) / "report.json"

        def fake_sha(path):
            path = Path(path)
            if path == native:
                return driver.HIP_NATIVE_SHA
            if path == Path(driver.__file__):
                return "driver-sha"
            if path == output:
                return "output-sha"
            raise AssertionError(f"unexpected hash target: {path}")

        default = {"status": "unknown", "loops": []}
        conditional = {"status": "unknown", "recovery": {"loops": []}}
        work_calls = []

        def fake_work(payload, loop_id, int_bits, protocols, **kwargs):
            work_calls.append((payload, loop_id, int_bits, protocols, kwargs))
            return {"status": "unknown", "reason": "mock-guarded-result",
                    "source_program_checked": False, "deployable": False}

        with patch.object(driver, "implementation_hashes", return_value={"checker.py": "fixed"}), \
                patch.object(driver, "sha", side_effect=fake_sha), \
                patch.object(driver, "select_entry", return_value=entry), \
                patch.object(driver, "recover", return_value=default) as recover_mock, \
                patch.object(driver, "recover_with_builtin_effects",
                             return_value=conditional) as conditional_mock, \
                patch.object(driver, "check_work_preservation",
                             side_effect=fake_work) as work_mock:
            driver.run(native, output, profile="hip-gfx1100", guarded_work=guarded_work)
        return json.loads(output.read_text()), recover_mock, conditional_mock, work_mock, work_calls

    def test_default_mode_never_calls_guarded_checker(self):
        with tempfile.TemporaryDirectory(prefix="wb-builtin-driver-") as temporary:
            report, recover_mock, conditional_mock, work_mock, work_calls = self.run_fixture(
                temporary, guarded_work=False)
        recover_mock.assert_called_once()
        conditional_mock.assert_called_once()
        work_mock.assert_not_called()
        self.assertEqual(work_calls, [])
        self.assertFalse(report["guarded_work_enabled"])
        self.assertEqual(report["guarded_work_checks"], [])
        self.assertFalse(report["source_program_checked"])
        self.assertFalse(report["deployable"])
        self.assertFalse(report["GPU_executed"])

    def test_guarded_mode_freshly_checks_each_break_loop_with_and_without_its_protocols(self):
        with tempfile.TemporaryDirectory(prefix="wb-builtin-driver-") as temporary:
            report, _, _, work_mock, work_calls = self.run_fixture(
                temporary, guarded_work=True)
        self.assertEqual(work_mock.call_count, 2)
        self.assertEqual(len(work_calls), 2)
        without, with_ = work_calls
        self.assertEqual(without[1:4], ("loop", 32, {}))
        self.assertEqual(set(with_[3]), {"call-inside"})
        self.assertNotIn("call-outside", with_[3])
        for call in work_calls:
            self.assertEqual(call[4], {"use_static_branches": True, "use_nested_loops": True})
        item = report["guarded_work_checks"][0]
        self.assertEqual(item["loop_id"], "loop")
        self.assertEqual(set(item["call_protocols"]), {"call-inside"})
        self.assertEqual(item["without_leaf_assumptions"]["status"], "unknown")
        self.assertEqual(item["with_leaf_assumptions"]["status"], "unknown")
        self.assertFalse(report["source_program_checked"])
        self.assertFalse(report["deployable"])
        self.assertFalse(report["GPU_executed"])


if __name__ == "__main__":
    unittest.main()
