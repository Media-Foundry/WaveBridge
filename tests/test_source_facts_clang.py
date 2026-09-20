"""Optional real-compiler regressions; no GPU, HIP SDK or corpus oracle needed."""

from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect
from wavebridge.analysis.source_facts import extract


COMPILER = shutil.which("clang++")
SOURCE = Path(__file__).parent / "fixtures" / "source_calls.cpp"


@unittest.skipUnless(COMPILER, "real Clang integration requires clang++")
class SourceFactsClangTests(unittest.TestCase):
    def facts(self, symbol):
        report = collect(SOURCE, COMPILER, ["-std=c++17"], symbol)
        self.assertEqual(report["status"], "collected", report.get("execution"))
        return extract(report)["facts"]

    def test_function_rename_preserves_direct_targets(self):
        for name in ("arbitrary_entry", "renamed_entry"):
            with self.subTest(name=name):
                facts = self.facts(name)
                calls = facts["calls"]
                self.assertEqual(len(calls), 2)
                self.assertEqual([call["resolution"] for call in calls],
                                 ["direct", "direct"])
                self.assertEqual([call["callee"]["name"] for call in calls],
                                 ["leaf", "apply"])

    def test_nested_argument_call_does_not_resolve_callback(self):
        calls = self.facts("indirect_entry")["calls"]
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["resolution"], "unknown")
        self.assertNotIn("callee", calls[0])
        self.assertEqual(calls[1]["resolution"], "direct")
        self.assertEqual(calls[1]["callee"]["name"], "leaf")


if __name__ == "__main__":
    unittest.main()
