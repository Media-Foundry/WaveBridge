"""Transparent report fixtures and real-Clang rejection tests for load indices."""

import copy
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.device_evidence import _load_index_relation
from wavebridge.source import run


def comparison_fixture(*, step=4):
    """Build explicit child reports; this is not source-recovery evidence."""
    checks = {"local_structure": {"checks": {}}, "local_entry_binding": {"signatures": {}},
              "coordinate_effects": {}}
    comparison = {"checks": checks}
    for side in ("source", "target"):
        ids = {role: f"{side}_{role}" for role in
               ("input", "bound", "start", "induction", "accumulator", "loaded_value")}
        loop = {
            "status": "recovered", "range": {"begin": side, "end": side}, "step": step,
            "header_recurrence_observed": True,
            "body_preserves_induction": "established_in_supported_effect_subset",
            "body_preserves_bound": "established_in_supported_effect_subset",
            "start": {"declaration_id": ids["start"]},
            "bound": {"declaration_id": ids["bound"]},
            "induction": {"declaration_id": ids["induction"]},
        }
        local = {"status": "recovered", "operation": "sum_of_squares", "loop": loop,
                 "input_parameter_id": ids["input"]}
        roles = {role: {"declaration_id": ids[role]} for role in
                 ("input", "bound", "start", "induction")}
        checks["local_structure"]["checks"][side] = {
            "local_recovery": local, "role_bindings": roles,
        }
        checks["local_entry_binding"]["signatures"][side] = {
            "source_offset": {"symbolic_relation": {
                "coefficient": 1, "row_power": 1, "count_power": 1}},
            "row_interval": {"lower": 0, "upper": 2},
            "count_interval": {"lower": 0, "upper": 9},
            "start_interval": {"lower": 0, "upper": step - 1},
        }
        columns = {
            "status": "checked", "column_recovery": {"loops": [loop]},
            "loops": [{"loop_range": loop["range"],
                       "parameter_declaration_id": ids["bound"],
                       "coverage": {"status": "checked"}}],
        }
        integer_checks = {
            "columns": columns,
            "thread": {
                "recovery": {"chain": {"block_threads": step}},
                "checks": {"block": {"dimensions": {"x": step, "y": 1, "z": 1}}},
                "coordinate_conclusion":
                    "column_start_equals_local_x_under_explicit_API_and_launch_premises",
            },
            "row": {"conclusion": "row_initializer_equals_workgroup_x_under_explicit_protocol"},
            "source_offset": {"status": "checked"},
        }
        checks[side] = {"checks": {"integers": {"checks": {
            "row_offsets": {"checks": integer_checks},
        }}}}
        checks["coordinate_effects"][side] = {"status": "checked"}
    return comparison


class LoadIndexRelationTests(unittest.TestCase):
    def test_matching_relations_are_conditional_only(self):
        result = _load_index_relation(comparison_fixture())
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["conclusion"],
                         "same_ordered_element_indices_under_common_r_n_t")
        self.assertFalse(result["runtime_pairing_verified"])
        self.assertEqual(result["input_contents_correspondence"], "not_established")
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_step_offset_role_and_coverage_mismatches_are_unknown(self):
        cases = []
        changed = comparison_fixture()
        changed["checks"]["target"]["checks"]["integers"]["checks"]["row_offsets"] \
            ["checks"]["thread"]["recovery"]["chain"]["block_threads"] = 8
        cases.append(changed)
        changed = comparison_fixture()
        changed["checks"]["local_structure"]["checks"]["target"]["local_recovery"]["loop"]["step"] = 8
        thread = changed["checks"]["target"]["checks"]["integers"]["checks"]["row_offsets"]["checks"]["thread"]
        thread["recovery"]["chain"]["block_threads"] = 8
        thread["checks"]["block"]["dimensions"]["x"] = 8
        cases.append(changed)
        changed = comparison_fixture()
        changed["checks"]["local_entry_binding"]["signatures"]["target"] \
            ["source_offset"]["symbolic_relation"]["coefficient"] = 2
        cases.append(changed)
        changed = comparison_fixture()
        changed["checks"]["local_structure"]["checks"]["target"] \
            ["role_bindings"]["input"]["declaration_id"] = "other_input"
        cases.append(changed)
        changed = comparison_fixture()
        changed["checks"]["target"]["checks"]["integers"]["checks"]["row_offsets"] \
            ["checks"]["columns"]["loops"][0]["coverage"]["status"] = "unknown"
        cases.append(changed)
        for index, candidate in enumerate(cases):
            with self.subTest(index=index):
                result = _load_index_relation(candidate)
                self.assertEqual(result["status"], "unknown", result)
                self.assertNotIn("conclusion", result)

    def test_different_domains_are_not_reported_as_same_relation(self):
        comparison = comparison_fixture()
        comparison["checks"]["local_entry_binding"]["signatures"]["target"] \
            ["count_interval"]["upper"] = 8
        result = _load_index_relation(comparison)
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["reason"], "different_ordered_index_relations_not_supported")

    def test_normal_form_matches_direct_loop_enumeration_on_small_domain(self):
        result = _load_index_relation(comparison_fixture(step=4))
        self.assertEqual(result["status"], "checked", result)
        normal = result["sides"]["source"]["normal_form"]
        self.assertEqual(normal["iteration"], "k_integer_ge_0_and_column_lt_n")
        domains = result["sides"]["source"]["domains"]
        for row in range(domains["r"]["lower"], domains["r"]["upper"] + 1):
            for count in range(domains["n"]["lower"], domains["n"]["upper"] + 1):
                for start in range(domains["t"]["lower"], domains["t"]["upper"] + 1):
                    direct, column = [], start
                    while column < count:
                        direct.append(row * count + column)
                        column += 4  # Independent reference: the fixture's declared block step.
                    coefficients = normal["element_index"]
                    normalized = [coefficients["r*n"] * row * count + coefficients["t"] * start
                                  + coefficients["k"] * iteration
                                  for iteration in range(20)
                                  if normal["column"]["t"] * start + normal["column"]["k"] * iteration < count]
                    self.assertEqual(normalized, direct)


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class LoadIndexRelationClangTests(unittest.TestCase):
    def test_shifted_load_and_shifted_row_offset_are_not_recovered(self):
        fixture = (Path(__file__).parent / "fixtures/row_prefix.cpp").read_text()
        variants = {
            "shifted_load": fixture.replace("input[col]", "input[col + 1]"),
            "shifted_row": fixture.replace(
                "static_cast<long long>(row) * count",
                "(static_cast<long long>(row) + 1) * count"),
        }
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            for name, source_text in variants.items():
                with self.subTest(name=name):
                    source = temporary_path / f"{name}.cpp"
                    source.write_text(source_text)
                    report = run(source, shutil.which("clang++"), ["-std=c++17"], "entry", 32,
                                 temporary_path / f"{name}-evidence")
                    self.assertEqual(report["row_prefix"]["status"], "unknown",
                                     report["row_prefix"])


if __name__ == "__main__":
    unittest.main()
