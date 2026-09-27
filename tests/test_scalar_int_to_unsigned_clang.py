"""Real-Clang tests for the opt-in int-to-unsigned no-write shape."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.scalar_expression_effects import check_no_memory_write


CLANG = shutil.which("clang++")
FIXTURE = Path(__file__).parent / "fixtures" / "scalar_int_to_unsigned.cpp"


@unittest.skipUnless(CLANG, "requires real clang++")
class ScalarIntToUnsignedClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(FIXTURE, CLANG, ["-std=c++17"], "from_parameter",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]

    def expressions(self, name):
        results = []
        for function in _walk(self.root):
            if (function.get("kind") != "FunctionDecl" or function.get("name") != name or
                    not any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                            for child in function.get("inner", []))):
                continue
            returns = [node for node in _walk(function) if node.get("kind") == "ReturnStmt"]
            self.assertEqual(len(returns), 1, name)
            children = [child for child in returns[0].get("inner", [])
                        if isinstance(child, dict) and child]
            self.assertEqual(len(children), 1, name)
            results.append(children[0])
        self.assertTrue(results, name)
        return results

    def check(self, name, **kwargs):
        expressions = self.expressions(name)
        self.assertEqual(len(expressions), 1, name)
        return check_no_memory_write(self.root, expressions[0]["id"], **kwargs)

    def test_default_rejects_and_opt_in_checks_parameter_and_literal(self):
        for name in ("from_parameter", "from_literal"):
            with self.subTest(name=name):
                self.assertEqual(self.check(name)["status"], "unknown")
                result = self.check(name, allow_int_to_unsigned=True)
                self.assertEqual(result["status"], "checked", result)
                self.assertTrue(result["int_to_unsigned_enabled"])
                self.assertEqual(result["value_semantics"], "not_established")
                self.assertFalse(result["numeric_contract_checked"])
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_template_literal_occurrences_are_narrowly_supported(self):
        expressions = self.expressions("template_literal")
        checked = [check_no_memory_write(
            self.root, expression["id"], allow_int_to_unsigned=True)
            for expression in expressions]
        self.assertTrue(any(result["status"] == "checked" for result in checked), checked)
        successful = [result for result in checked if result["status"] == "checked"]
        self.assertTrue(any(result["shared_literal_occurrences"] for result in successful),
                        successful)
        for result in successful:
            for occurrence in result["shared_literal_occurrences"]:
                self.assertEqual(occurrence["scope"],
                                 "direct_int_to_unsigned_literal_operand")
                self.assertTrue(occurrence["contents_equal"])

    def test_writes_calls_volatile_and_references_remain_unknown(self):
        for name in ("increment", "assignment", "call", "volatile_read", "reference_read"):
            with self.subTest(name=name):
                result = self.check(name, allow_int_to_unsigned=True)
                self.assertEqual(result["status"], "unknown", result)

    def test_other_source_types_and_explicit_cast_remain_unknown(self):
        for name in ("from_bool", "from_float", "from_short", "explicit_cast"):
            with self.subTest(name=name):
                result = self.check(name, allow_int_to_unsigned=True)
                self.assertEqual(result["status"], "unknown", result)

    def test_shared_literal_conflicts_and_duplicate_roots_fail_closed(self):
        expression = self.expressions("from_literal")[0]

        conflicting = deepcopy(self.root)
        selected = [node for node in _walk(conflicting) if node.get("id") == expression["id"]]
        self.assertEqual(len(selected), 1)
        literal = [node for node in _walk(selected[0]) if node.get("kind") == "IntegerLiteral"]
        self.assertEqual(len(literal), 1)
        duplicate_literal = deepcopy(literal[0])
        duplicate_literal["value"] = "8"
        conflicting["inner"].append(duplicate_literal)
        result = check_no_memory_write(
            conflicting, expression["id"], allow_int_to_unsigned=True)
        self.assertEqual(result["status"], "unknown", result)

        duplicate_root = deepcopy(self.root)
        duplicate_root["inner"].append(deepcopy(expression))
        result = check_no_memory_write(
            duplicate_root, expression["id"], allow_int_to_unsigned=True)
        self.assertEqual(result["status"], "unknown", result)

    def test_non_boolean_flag_is_rejected(self):
        expression = self.expressions("from_literal")[0]
        result = check_no_memory_write(
            self.root, expression["id"], allow_int_to_unsigned=1)
        self.assertEqual(result["status"], "unknown", result)


if __name__ == "__main__":
    unittest.main()
