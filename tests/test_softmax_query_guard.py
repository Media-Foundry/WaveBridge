import tempfile
from pathlib import Path
import unittest

from experiments.softmax_query_guard import ANCHOR, add_guard, prepare


class GuardCandidateTests(unittest.TestCase):
    def test_only_one_precise_insertion_not_global_width_replacement(self):
        source = ANCHOR + 'scale[j/32];\n' + ANCHOR
        result = add_guard(source, 64)
        self.assertEqual(result, ANCHOR + '        if (warp_size != 64) std::abort();\nscale[j/32];\n' + ANCHOR)

    def test_context_and_integer_width_fail_closed(self):
        for width in (0, -1, True, 2**31):
            with self.assertRaises(ValueError): add_guard(ANCHOR * 2, width)
        for source in ('', ANCHOR, ANCHOR * 3):
            with self.assertRaises(ValueError): add_guard(source, 32)

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'out'
            output.mkdir()
            with self.assertRaisesRegex(ValueError, 'output_must_not_exist'):
                prepare(Path(directory) / 'missing', output)
