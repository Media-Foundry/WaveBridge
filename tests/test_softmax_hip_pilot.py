"""Offline patch and metadata selection regressions; no GPU jobs."""
import unittest
import copy
import json

from experiments.softmax_hip_pilot import REPLACEMENTS, INTAKE, adapt, validate_protocol
from runtime.probes.probe import kernel_metadata_widths


class SoftmaxHipPilotTests(unittest.TestCase):
    def test_empty_or_changed_panel_cannot_pass(self):
        protocol = json.loads((INTAKE / "pytorch-softmax-hip-protocol.json").read_text())
        validate_protocol(protocol)
        changed = copy.deepcopy(protocol)
        changed["cases"]["rows"] = []
        with self.assertRaises(ValueError):
            validate_protocol(changed)
        changed = copy.deepcopy(protocol)
        changed["reference"]["absolute_tolerance"] = 1.0
        with self.assertRaises(ValueError):
            validate_protocol(changed)

    def test_patch_only_changes_declared_sites(self):
        source = "\n".join(old for old, _, count in REPLACEMENTS for _ in range(count))
        source += "\nint quantization_group = 32;\n"
        changed = adapt(source)
        for old, new, count in REPLACEMENTS:
            self.assertNotIn(old, changed)
            self.assertEqual(changed.count(new), count)
        self.assertTrue(changed.endswith("int quantization_group = 32;\n"))
        with self.assertRaises(ValueError):
            adapt(changed)
        with self.assertRaises(ValueError):
            adapt(source + REPLACEMENTS[0][0])

    def test_metadata_uses_exact_explicit_names(self):
        text = """amdhsa.kernels:
  - .name: selected
    .wavefront_size: 32
  - .name: selected_other
    .wavefront_size: 64
  - .name: wavebridge_probe
    .wavefront_size: 64
amdhsa.version: [1, 2]
"""
        self.assertEqual(kernel_metadata_widths(text, {"selected"}), {32})
        self.assertEqual(kernel_metadata_widths(text, {"selected_other"}), {64})
        self.assertEqual(kernel_metadata_widths(text, {"missing"}), set())
        self.assertEqual(kernel_metadata_widths(text, set()), set())
        self.assertEqual(kernel_metadata_widths(text), {64})
