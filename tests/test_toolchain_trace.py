from pathlib import Path
import hashlib
import shlex
import tempfile
import unittest

from wavebridge.frontend.toolchain_trace import observe


class ToolchainTraceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.compiler = self.root / "clang 23"
        self.compiler.write_bytes(b"compiler")
        self.resource = self.root / "clang-resource"
        self.resource.mkdir()
        self.ocml = self.root / "ocml.bc"
        self.ockl = self.root / "ockl file.bc"
        self.ocml.write_bytes(b"ocml")
        self.ockl.write_bytes(b"ockl")

    def tearDown(self):
        self.temporary.cleanup()

    def command(self, *extra):
        tokens = [str(self.compiler), "-cc1", "-triple", "amdgcn-amd-amdhsa",
                  "-target-cpu", "gfx1100", "-resource-dir", str(self.resource),
                  "-mlink-builtin-bitcode", str(self.ocml),
                  "-mlink-bitcode", str(self.ockl), *extra]
        return " ".join(shlex.quote(token) for token in tokens)

    def test_observes_unique_planned_job_and_hashes_files(self):
        stderr = "driver preface\n (in-process)\n" + self.command() + "\n"
        report = observe(stderr, self.root)
        self.assertEqual(report["status"], "observed", report)
        self.assertEqual(report["triple"], "amdgcn-amd-amdhsa")
        self.assertEqual(report["target_cpu"], "gfx1100")
        self.assertEqual(report["compiler"]["sha256"],
                         hashlib.sha256(b"compiler").hexdigest())
        self.assertEqual([item["flag"] for item in report["bitcode_files"]],
                         ["-mlink-builtin-bitcode", "-mlink-bitcode"])
        self.assertEqual(report["raw_stderr"], stderr)
        self.assertEqual(report["raw_stderr_sha256"],
                         hashlib.sha256(stderr.encode()).hexdigest())
        self.assertFalse(report["actual_ast_process_identity_established"])
        self.assertFalse(report["frozen_compilation_input_closure_established"])
        self.assertFalse(report["deployable"])

    def test_target_cpu_may_be_absent(self):
        tokens = shlex.split(self.command())
        position = tokens.index("-target-cpu")
        del tokens[position:position + 2]
        report = observe(" ".join(shlex.quote(token) for token in tokens), self.root)
        self.assertEqual(report["status"], "observed", report)
        self.assertIsNone(report["target_cpu"])

    def test_no_job_and_multiple_jobs_are_unknown(self):
        for stderr in ("clang version only\n", self.command() + "\n" + self.command()):
            with self.subTest(stderr=stderr):
                report = observe(stderr, self.root)
                self.assertEqual(report["status"], "unknown")
                self.assertEqual(report["reason"], "planned_cc1_job_not_unique")

    def test_relative_compiler_is_unknown(self):
        tokens = shlex.split(self.command())
        tokens[0] = "clang-23"
        report = observe(" ".join(shlex.quote(token) for token in tokens), self.root)
        self.assertEqual(report["reason"], "planned_compiler_path_not_absolute")

    def test_missing_required_and_repeated_options_are_unknown(self):
        base = shlex.split(self.command())
        cases = []
        for option in ("-triple", "-resource-dir"):
            tokens = list(base)
            position = tokens.index(option)
            del tokens[position:position + 2]
            cases.append(tokens)
        cases.append([*base, "-triple", "x86_64-unknown-linux-gnu"])
        cases.append([*base, "-target-cpu", "gfx900"])
        for tokens in cases:
            with self.subTest(tokens=tokens):
                self.assertEqual(observe(" ".join(map(shlex.quote, tokens)), self.root)["status"],
                                 "unknown")

    def test_singleton_option_cannot_consume_the_following_flag_as_its_value(self):
        base = shlex.split(self.command())
        for option in ("-triple", "-target-cpu", "-resource-dir"):
            with self.subTest(option=option):
                tokens = list(base)
                del tokens[tokens.index(option) + 1]
                report = observe(" ".join(map(shlex.quote, tokens)), self.root)
                self.assertEqual(report["status"], "unknown", report)
                self.assertEqual(report["reason"], "planned_job_option_value_missing")

    def test_missing_or_relative_toolchain_paths_are_unknown(self):
        base = shlex.split(self.command())
        cases = []
        for old, new in ((str(self.compiler), str(self.root / "missing-clang")),
                         (str(self.resource), str(self.root / "missing-resource")),
                         (str(self.ocml), str(self.root / "missing.bc")),
                         (str(self.ocml), "relative.bc")):
            tokens = list(base)
            tokens[tokens.index(old)] = new
            cases.append(tokens)
        for tokens in cases:
            with self.subTest(tokens=tokens):
                self.assertEqual(observe(" ".join(map(shlex.quote, tokens)), self.root)["status"],
                                 "unknown")

    def test_malformed_quoting_layout_and_inputs_are_unknown(self):
        malformed = '"unterminated -cc1'
        self.assertEqual(observe(malformed, self.root)["reason"],
                         "driver_trace_shell_quoting_invalid")
        tokens = shlex.split(self.command())
        tokens.insert(1, "wrapper-token")
        self.assertEqual(observe(" ".join(map(shlex.quote, tokens)), self.root)["reason"],
                         "planned_cc1_job_layout_unsupported")
        self.assertEqual(observe(None, self.root)["reason"], "invalid_inputs")
        self.assertEqual(observe(self.command(), self.root / "absent")["reason"],
                         "cwd_not_directory")


if __name__ == "__main__":
    unittest.main()
