"""Real multi-launch TU: exact selection is not complete launch discovery."""
import copy
from pathlib import Path
import shutil
import unittest

from wavebridge.analysis.launch_facts import inspect
from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.launch_binding import check


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class SelectedLaunchClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/selected_launch.cu", shutil.which("clang++"),
                         ["-std=c++17", "--cuda-host-only", "-nocudainc", "-nocudalib"],
                         "target", full_translation_unit=True, dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]
        cls.kernel = report["function_locations"][0]["id"]
        cls.facts = inspect(cls.root, cls.kernel)
        cls.site = cls.facts["sites"][0]
        resolved = {site["launch_id"] for site in cls.facts["sites"]}
        cls.dependent = next(node for node in _walk(cls.root)
                             if node.get("kind") == "CUDAKernelCallExpr" and node["id"] not in resolved)
        cls.selection = {"schema_version": "launch-selection/v1", "ast_root_sha256": _hash(cls.root),
                         "kernel_declaration_id": cls.kernel, "launch_id": cls.site["launch_id"],
                         "configuration_declaration_id": cls.site["configuration_declaration_id"],
                         "configuration_expression_ids": [node["id"] for node in cls.site["configuration_arguments"]]}

    def test_selected_exact_sites_bind_despite_distinct_dependent_site(self):
        self.assertEqual(2, len(self.facts["sites"]))
        self.assertEqual(1, len(self.facts["unresolved_sites"]))
        self.assertEqual("kernel_not_exact_declref", self.facts["unresolved_sites"][0]["reason"])
        for site in self.facts["sites"]:
            selection = {**self.selection, "launch_id": site["launch_id"],
                         "configuration_expression_ids": [node["id"] for node in site["configuration_arguments"]]}
            result = check(self.root, selection)
            self.assertEqual("checked", result["status"], result)
            self.assertEqual("not_established", result["launch_discovery"]["complete_launch_resolution"])
            self.assertEqual(self.facts["unresolved_sites"], result["launch_discovery"]["unresolved_sites"])
            self.assertFalse(result["deployable"])

    def test_selecting_dependent_site_remains_unknown(self):
        result = check(self.root, {**self.selection, "launch_id": self.dependent["id"]})
        self.assertEqual("unknown", result["status"])
        self.assertEqual("selected_launch_not_uniquely_bound_to_kernel", result["reason"])

    def test_configuration_slots_from_another_real_launch_do_not_bind(self):
        other = self.facts["sites"][1]
        result = check(self.root, {**self.selection, "configuration_expression_ids":
                                  [node["id"] for node in other["configuration_arguments"]]})
        self.assertEqual("configuration_expression_position_mismatch", result["reason"])

    def test_unresolved_launch_identity_conflict_is_not_ignored(self):
        for collide_with_selected in (True, False):
            root = copy.deepcopy(self.root)
            conflicting = copy.deepcopy(self.dependent)
            if collide_with_selected:
                conflicting["id"] = self.site["launch_id"]
            else:
                conflicting["range"] = {}
            root["inner"].append(conflicting)
            result = check(root, {**self.selection, "ast_root_sha256": _hash(root)})
            self.assertEqual("conflicting_launch_id_occurrences", result["reason"])
            self.assertEqual("unknown", result["status"])

    def test_missing_dependent_identity_cannot_be_assumed_distinct(self):
        root = copy.deepcopy(self.root)
        for node in _walk(root):
            if node.get("id") == self.dependent["id"]:
                del node["id"]
        result = check(root, {**self.selection, "ast_root_sha256": _hash(root)})
        self.assertEqual("launch_occurrence_identity_missing", result["reason"])


if __name__ == "__main__":
    unittest.main()
