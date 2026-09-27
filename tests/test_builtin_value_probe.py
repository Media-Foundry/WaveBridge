"""Driver boundary tests; mocked compilation is not device evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments import builtin_value_probe as probe


class BuiltinValueProbeTests(unittest.TestCase):
    def exercise(self, compilation="completed", dependencies="observed", version="completed", profile="cuda-sm80"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compiler = root / "compiler"
            compiler.write_text("fixture compiler")
            config = root / "config.json"
            config.write_text(json.dumps({"compiler": str(compiler), "compiler_args": []}))

            def invoke(command, timeout, cwd):
                if "--version" in command:
                    return {"status": version, "returncode": 0 if version == "completed" else None}
                if "-o" in command and compilation == "completed":
                    Path(command[command.index("-o") + 1]).write_text("fixture IR")
                return {"status": compilation, "returncode": 0 if compilation == "completed" else None}

            prefix = "HIP_" if profile == "hip-gfx1100" else ""
            with patch.object(probe, prefix + "CONFIG_SHA", probe.sha(config)), \
                 patch.object(probe, prefix + "COMPILER_SHA", probe.sha(compiler)), \
                 patch.object(probe.clang_ast, "invoke", side_effect=invoke), \
                 patch.object(probe.dependencies, "observe", return_value={"status": dependencies}):
                return probe.run(config, root / "output", profile=profile)

    def test_hip_profile_keeps_observation_only_boundary(self):
        report = self.exercise(profile="hip-gfx1100")
        self.assertEqual(report["profile"], "hip-gfx1100")
        self.assertEqual(report["status"], "observed")
        self.assertFalse(report["GPU_executed"])
        self.assertFalse(report["source_program_checked"])
        self.assertFalse(report["deployable"])

    def test_unknown_profile_rejected_before_input_access(self):
        with self.assertRaisesRegex(ValueError, "unsupported_probe_profile"):
            probe.run(Path("not-present.json"), Path("not-created"), profile="unknown")

    def test_profiles_do_not_share_config_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            config.write_text("{}")
            with patch.object(probe, "CONFIG_SHA", probe.sha(config)), \
                 patch.object(probe.clang_ast, "invoke") as invoke:
                with self.assertRaisesRegex(ValueError, "frozen_config_mismatch"):
                    probe.run(config, Path(tmp) / "output", profile="hip-gfx1100")
                invoke.assert_not_called()

    def test_observation_never_grants_acceptance(self):
        report = self.exercise()
        self.assertEqual(report["status"], "observed")
        self.assertEqual(len(report["jobs"]), 2)
        for field in ("GPU_executed", "source_program_checked", "deployable",
                      "full_compilation_closure_established"):
            self.assertIs(report[field], False)

    def test_timeout_is_incomplete(self):
        report = self.exercise(compilation="timeout")
        self.assertEqual(report["status"], "incomplete")
        self.assertTrue(all(job["status"] == "not_compiled" for job in report["jobs"]))

    def test_missing_dependencies_are_incomplete(self):
        self.assertEqual(self.exercise(dependencies="unknown")["status"], "incomplete")

    def test_missing_version_is_incomplete(self):
        self.assertEqual(self.exercise(version="timeout")["status"], "incomplete")

    def test_unpinned_config_rejected_before_compilation(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            config.write_text("{}")
            with patch.object(probe.clang_ast, "invoke") as invoke:
                with self.assertRaisesRegex(ValueError, "frozen_config_mismatch"):
                    probe.run(config, Path(tmp) / "output")
                invoke.assert_not_called()
