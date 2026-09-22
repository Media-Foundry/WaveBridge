"""Opt-in hashing must change cost, never canonical bytes or acceptance rules."""
import copy
import hashlib
import json
import math
import os
import random
import unittest
from unittest.mock import patch

from wavebridge.verification.integer_selection import _hash

MODE = "WAVEBRIDGE_JSON_HASH_MODE"


class CanonicalHashModeTests(unittest.TestCase):
    def hash_in_mode(self, value, mode):
        with patch.dict(os.environ, {MODE: mode}):
            return _hash(value)

    def test_streaming_is_the_default_and_does_not_call_dumps(self):
        with patch.dict(os.environ):
            os.environ.pop(MODE, None)
            with patch("wavebridge.verification.integer_selection.json.dumps",
                       side_effect=AssertionError("default must remain streaming")):
                self.assertEqual(_hash({"x": 1}), hashlib.sha256(b'{"x":1}').hexdigest())

    def test_one_shot_explicitly_routes_to_the_standard_encoder(self):
        original = json.dumps
        with patch.dict(os.environ, {MODE: "one-shot"}):
            with patch("wavebridge.verification.integer_selection.json.dumps", wraps=original) as encode:
                self.assertEqual(_hash({"x": 1}), hashlib.sha256(b'{"x":1}').hexdigest())
                encode.assert_called_once_with({"x": 1}, sort_keys=True,
                                               separators=(",", ":"), allow_nan=False)

    def test_explicit_streaming_does_not_call_dumps(self):
        with patch("wavebridge.verification.integer_selection.json.dumps",
                   side_effect=AssertionError("streaming must not call dumps")):
            self.assertEqual(self.hash_in_mode({"x": 1}, "streaming"),
                             hashlib.sha256(b'{"x":1}').hexdigest())

    def test_one_shot_memory_error_does_not_fall_back(self):
        with patch("wavebridge.verification.integer_selection.json.dumps",
                   side_effect=MemoryError("explicit allocation failure")):
            with self.assertRaises(MemoryError):
                self.hash_in_mode({}, "one-shot")

    def test_exact_canonical_digest_and_input_immutability(self):
        value = {"z": "中", "a": [True, None, -0.0]}
        before = copy.deepcopy(value)
        expected = hashlib.sha256(b'{"a":[true,null,-0.0],"z":"\\u4e2d"}').hexdigest()
        for mode in ("streaming", "one-shot"):
            self.assertEqual(self.hash_in_mode(value, mode), expected)
            self.assertEqual(value, before)

    def test_unicode_integer_and_floating_boundaries(self):
        values = [None, True, False, "", "\x00\n\t\\\"", "中文😀", "\ud800",
                  0, -1, 2**4096, -(2**4096), -0.0, 5e-324, -5e-324,
                  float.fromhex("0x1.fffffffffffffp+1023"), 1e-300, 1e300,
                  0.1, [1, 2], (1, 2), {"a": 1, "aa": 2, "中": 3}]
        for value in values:
            with self.subTest(value_type=type(value).__name__):
                self.assertEqual(self.hash_in_mode(value, "streaming"),
                                 self.hash_in_mode(value, "one-shot"))

    def test_seeded_nested_json_values_have_equal_digests(self):
        random_source = random.Random(1739)
        atoms = [None, False, True, 0, -1, 1.0, -0.0, 5e-324, 1e300, "", "中😀", "\ud800"]

        def value(depth):
            if depth == 0 or random_source.randrange(3) == 0:
                return random_source.choice(atoms)
            if random_source.randrange(2):
                return [value(depth-1) for _ in range(random_source.randrange(5))]
            return {str(key): value(depth-1) for key in range(random_source.randrange(5))}

        for _ in range(2048):
            item = value(4)
            self.assertEqual(self.hash_in_mode(item, "streaming"),
                             self.hash_in_mode(item, "one-shot"))

    def test_invalid_json_inputs_remain_errors_in_both_modes(self):
        cycle = []
        cycle.append(cycle)
        cases = [(math.nan, ValueError), (math.inf, ValueError), (-math.inf, ValueError),
                 (cycle, ValueError), ({"x": object()}, TypeError), (b"bytes", TypeError),
                 ({1: 0, "one": 1}, TypeError)]
        for mode in ("streaming", "one-shot"):
            for item, error in cases:
                with self.subTest(mode=mode, error=error.__name__):
                    with self.assertRaises(error):
                        self.hash_in_mode(item, mode)

    def test_unknown_mode_never_silently_falls_back(self):
        for mode in ("", "unknown", "STREAMING", "one_shot"):
            with self.subTest(mode=mode):
                with self.assertRaises(ValueError):
                    self.hash_in_mode({}, mode)
