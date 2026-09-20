"""Source recovery and independent route checking on actual Clang ASTs."""

from pathlib import Path
import shutil
import json
import tempfile
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.analysis.xor_reduction import recover, main
from wavebridge.verification.xor_routes import check


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class XorReductionClangTests(unittest.TestCase):
    def test_source_width_changes_flow_into_independent_checker(self):
        report = collect(Path(__file__).parent / "fixtures/xor_reduction.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "original",
                         full_translation_unit=True)
        self.assertEqual(report["status"], "collected", report.get("execution"))
        root = report["ast_roots"][0]
        declarations = {n["name"]: n["id"] for n in _walk(root)
                        if n.get("kind") == "FunctionDecl"}
        for name, width in (("original", 32), ("renamed", 64)):
            with self.subTest(name=name):
                result = recover(root, declarations[name], declarations["exchange"], int_bits=32)
                self.assertEqual(result["status"], "recovered", result)
                self.assertEqual(result["width"], width)
                self.assertEqual(result["offsets"], [width >> shift for shift in range(1, width.bit_length())])
                self.assertEqual(check(result["width"], result["offsets"])["status"], "checked")
                self.assertFalse(result["checked"])
        changed = recover(root, declarations["changed_condition"], declarations["exchange"], int_bits=32)
        self.assertEqual(changed["status"], "unknown")
        with tempfile.TemporaryDirectory() as temp:
            ast_path, output = Path(temp) / "ast.json", Path(temp) / "result.json"
            ast_path.write_text(json.dumps(report))
            command = [str(ast_path), "--root-index", "0", "--function-id", declarations["original"],
                       "--shuffle-id", declarations["exchange"], "--int-bits", "32",
                       "--output", str(output)]
            self.assertEqual(main(command), 0)
            evidence = json.loads(output.read_text())
            self.assertFalse(evidence["source_program_checked"])
            self.assertEqual(evidence["conditional_route_check"]["status"], "checked")
            with self.assertRaises(SystemExit):
                main(command)


if __name__ == "__main__":
    unittest.main()
