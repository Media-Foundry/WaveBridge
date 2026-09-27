"""Unit input-binding checks, not source-recovery or GPU evidence."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from experiments.softmax_hip_relations import AST_SHA, validate_intake


class HipRelationsBindingTests(unittest.TestCase):
    def setUp(self):
        self.root = {"kind": "TranslationUnitDecl"}
        self.frontend = {"status": "collected", "ast_roots": [self.root]}
        self.intake = {"ast_report_sha256": AST_SHA, "status": "analyzed",
                       "executed_source_files_bound": True, "inputs_unchanged": True,
                       "selected_entry": {"id": "selected"}}

    def test_bound_inputs_keep_original_root(self):
        with patch("experiments.softmax_hip_relations.select_entry", return_value={"id": "selected"}):
            root, entry = validate_intake(self.frontend, self.intake)
        self.assertIs(root, self.root)
        self.assertEqual(entry["id"], "selected")

    def test_incomplete_or_mismatched_intake_rejected_before_selection(self):
        for key, value in (("ast_report_sha256", "different"), ("status", "inputs_changed"),
                           ("executed_source_files_bound", 1), ("inputs_unchanged", False)):
            with self.subTest(key=key):
                intake = dict(self.intake, **{key: value})
                with patch("experiments.softmax_hip_relations.select_entry") as selector:
                    with self.assertRaises(ValueError):
                        validate_intake(self.frontend, intake)
                    selector.assert_not_called()

    def test_failed_or_ambiguous_frontend_rejected(self):
        for frontend in ({"status": "failed", "ast_roots": [self.root]},
                         {"status": "collected", "ast_roots": []},
                         {"status": "collected", "ast_roots": [self.root, deepcopy(self.root)]}):
            with self.subTest(frontend=frontend), self.assertRaises(ValueError):
                validate_intake(frontend, self.intake)

    def test_changed_entry_rejected(self):
        with patch("experiments.softmax_hip_relations.select_entry", return_value={"id": "other"}):
            with self.assertRaisesRegex(ValueError, "selected_entry_changed"):
                validate_intake(self.frontend, self.intake)
