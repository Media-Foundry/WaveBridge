"""Driver-only fixtures; real upstream observation is recorded separately."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments import pytorch_softmax_intake as intake


def entry(identity="kernel", size=7, scalar="float"):
    return {"kind": "FunctionDecl", "name": "softmax_warp_forward", "id": identity,
            "inner": [{"kind": "TemplateArgument", "type": {"qualType": scalar}}
                      for _ in range(3)] +
                     [{"kind": "TemplateArgument", "value": value} for value in (size, 0, 0)] +
                     [{"kind": "CompoundStmt", "inner": []}]}


class SoftmaxIntakeTests(unittest.TestCase):
    def test_exact_specialization_not_first_or_success_based(self):
        selected = entry()
        root = {"inner": [entry("other", 6), entry("half", scalar="half"), selected]}
        self.assertEqual(intake.select_entry(root), selected)

    def test_missing_ambiguous_or_conflicting_entry_rejected(self):
        changed = entry()
        changed["inner"][-1]["inner"] = [{"kind": "NullStmt"}]
        for values in ([entry(size=6)], [entry(), entry("duplicate")], [entry(), changed]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                intake.select_entry({"inner": values})

    def test_identical_clang_identity_duplicate_is_one_entry(self):
        value = entry()
        self.assertEqual(intake.select_entry({"inner": [value, deepcopy(value)]}), value)

    def fixture_run(self, *, frontend_status="collected", dependency="observed", changed=False,
                    missing_header=False, mutate_config=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        header = root / intake.HEADER
        header.parent.mkdir(parents=True)
        header.write_bytes(b"source fixture, not actual upstream")
        config = root / "config.json"
        config.write_text(json.dumps({"torch_include": str(root), "compiler": "fake",
                                      "compiler_args": []}))
        header_sha = hashlib.sha256(header.read_bytes()).hexdigest()
        observed_files = [] if missing_header else [{"resolved_path": str(header.resolve()),
                                                     "sha256": header_sha}]
        observation = {"status": frontend_status, "reason": "diagnostic if failed",
                       "dependency_binding": {"status": dependency, "files": observed_files},
                       "toolchain_trace": {"status": "observed"},
                       "ast_roots": [{"inner": [entry()]}]}

        def collect(*args, **kwargs):
            if mutate_config:
                config.write_text("{}")
            return observation

        hashes = [{"analysis.py": "fixed"}, {"analysis.py": "changed" if changed else "fixed"}]
        with patch.object(intake, "HEADER_SHA", hashlib.sha256(header.read_bytes()).hexdigest()), \
                patch.object(intake, "implementation_hashes", side_effect=hashes), \
                patch.object(intake, "require_frozen_implementation"), \
                patch.object(intake, "collect", side_effect=collect), \
                patch.object(intake, "recover", return_value={"status": "unknown", "loops": [
                    {"status": "unknown", "reason": "unsupported_header"}]}), \
                patch.object(intake, "discover", return_value={"status": "unknown"}), \
                patch.object(intake, "inspect_launch", return_value={"status": "unknown"}):
            return intake.run(config, root / "run")

    def test_analyzed_unknown_is_not_success_or_holdout(self):
        result = self.fixture_run()
        self.assertEqual(result["status"], "analyzed")
        self.assertEqual(result["loop_counts"], {"unknown": 1})
        self.assertEqual(result["loop_reasons"], {"unsupported_header": 1})
        for flag in ("source_program_checked", "deployable", "GPU_executed",
                     "full_production_TU", "strict_lineage_holdout_established"):
            self.assertFalse(result[flag])

    def test_frontend_failure_not_semantic_rejection(self):
        result = self.fixture_run(frontend_status="compile_failed")
        self.assertEqual(result["status"], "frontend_unavailable")
        self.assertIsNone(result["analysis"])

    def test_missing_dependencies_prevent_relation_analysis(self):
        result = self.fixture_run(dependency="missing")
        self.assertEqual(result["status"], "dependency_evidence_unavailable")
        self.assertIsNone(result["analysis"])

    def test_implementation_change_invalidates_observation(self):
        result = self.fixture_run(changed=True)
        self.assertEqual(result["status"], "inputs_changed")
        self.assertFalse(result["implementation_hashes_stable"])

    def test_configured_copy_must_be_actual_compiler_dependency(self):
        result = self.fixture_run(missing_header=True)
        self.assertEqual(result["status"], "selected_header_not_bound_to_compilation")
        self.assertIsNone(result["analysis"])

    def test_configuration_change_invalidates_observation(self):
        result = self.fixture_run(mutate_config=True)
        self.assertEqual(result["status"], "inputs_changed")
        self.assertFalse(result["config_unchanged"])

    def test_freeze_requires_original_files_and_revision(self):
        with patch.object(intake.subprocess, "check_output", return_value="src/wavebridge/a.py\n"), \
                patch.object(intake.subprocess, "run") as git_diff:
            with self.assertRaisesRegex(ValueError, "file_set"):
                intake.require_frozen_implementation({"other.py": "sha"})
            git_diff.assert_not_called()
            git_diff.return_value.returncode = 1
            with self.assertRaisesRegex(ValueError, "differs"):
                intake.require_frozen_implementation({"src/wavebridge/a.py": "sha"})


if __name__ == "__main__":
    unittest.main()
