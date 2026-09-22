import hashlib
from pathlib import Path
import tempfile
import unittest

from wavebridge.frontend.dependencies import observe


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DependencyObservationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source file#.cpp"
        self.header = self.root / "header\\name$.h"
        self.source.write_text("#include \"header\\\\name$.h\"\n")
        self.header.write_text("constexpr int value = 1;\n")
        self.depfile = self.root / "temporary.d"

    def tearDown(self):
        self.temporary.cleanup()

    def write_valid(self):
        self.depfile.write_text(
            "wavebridge-inputs: source\\ file\\#.cpp \\\n header\\\\name$$.h\n")

    def test_observes_single_rule_with_make_escapes_and_continuation(self):
        self.write_valid()
        report = observe(self.depfile, self.root, self.source, digest(self.source))
        self.assertEqual(report["status"], "observed", report)
        self.assertTrue(report["source_stable"])
        self.assertEqual({item["resolved_path"] for item in report["files"]},
                         {str(self.source.resolve()), str(self.header.resolve())})
        self.assertEqual(len(report["manifest_sha256"]), 64)
        self.assertFalse(report["frozen_snapshot"])
        self.assertFalse(report["complete_dependency_closure_guaranteed"])
        self.assertEqual(report["raw_depfile_sha256"],
                         hashlib.sha256(self.depfile.read_bytes()).hexdigest())

    def test_manifest_hash_changes_with_dependency_content(self):
        self.write_valid()
        first = observe(self.depfile, self.root, self.source, digest(self.source))
        self.header.write_text("constexpr int value = 2;\n")
        second = observe(self.depfile, self.root, self.source, digest(self.source))
        self.assertEqual(first["status"], second["status"])
        self.assertNotEqual(first["manifest_sha256"], second["manifest_sha256"])

    def test_rejects_multiple_rules_and_wrong_target(self):
        for text in ("wavebridge-inputs: source\\ file\\#.cpp\nother: x\n",
                     "other: source\\ file\\#.cpp\n"):
            with self.subTest(text=text):
                self.depfile.write_text(text)
                self.assertEqual(observe(self.depfile, self.root, self.source,
                                         digest(self.source))["status"], "unknown")

    def test_rejects_ambiguous_or_unsupported_tokens(self):
        texts = (
            "wavebridge-inputs: bare#comment\n",
            "wavebridge-inputs: bare$dollar\n",
            "wavebridge-inputs: bad\\q\n",
            "wavebridge-inputs extra: source\\ file\\#.cpp\n",
            "wavebridge-inputs:\n",
        )
        for text in texts:
            with self.subTest(text=text):
                self.depfile.write_text(text)
                self.assertEqual(observe(self.depfile, self.root, self.source,
                                         digest(self.source))["status"], "unknown")

    def test_missing_unreadable_and_source_omission_are_unknown(self):
        cases = (
            "wavebridge-inputs: missing.h source\\ file\\#.cpp\n",
            "wavebridge-inputs: header\\\\name$$.h\n",
        )
        for text in cases:
            with self.subTest(text=text):
                self.depfile.write_text(text)
                self.assertEqual(observe(self.depfile, self.root, self.source,
                                         digest(self.source))["status"], "unknown")
        missing = self.root / "absent.d"
        self.assertEqual(observe(missing, self.root, self.source,
                                 digest(self.source))["reason"], "depfile_unreadable")

    def test_source_change_is_unknown(self):
        before = digest(self.source)
        self.write_valid()
        self.source.write_text("changed\n")
        report = observe(self.depfile, self.root, self.source, before)
        self.assertEqual(report["status"], "unknown")
        self.assertFalse(report["source_stable"])
        self.assertEqual(report["reason"], "source_changed_during_collection")

    def test_missing_cwd_or_source_is_unknown_not_exception(self):
        self.write_valid()
        before = digest(self.source)
        for cwd, source in ((self.root / "missing", self.source),
                            (self.root, self.root / "missing.cpp")):
            report = observe(self.depfile, cwd, source, before)
            self.assertEqual("unknown", report["status"])

    def test_invalid_hash_and_non_utf8_depfile_are_unknown(self):
        self.write_valid()
        self.assertEqual(observe(self.depfile, self.root, self.source, "bad")["status"],
                         "unknown")
        self.depfile.write_bytes(b"wavebridge-inputs: \xff")
        self.assertEqual(observe(self.depfile, self.root, self.source,
                                 digest(self.source))["reason"], "depfile_not_utf8")


if __name__ == "__main__":
    unittest.main()
