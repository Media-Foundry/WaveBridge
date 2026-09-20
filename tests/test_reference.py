from dataclasses import replace
import unittest

from wavebridge.ir.model import Domain, Launch, example_source
from wavebridge.pipeline import adapt_model
from wavebridge.transforms.qdot import retile
from wavebridge.verification.qdot import Limits, check, output_polynomials
from wavebridge.verification.report import Verdict


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.source = example_source()
        self.target = retile(self.source, 64)

    def mutate_kernel(self, **changes):
        return replace(self.target, kernel=replace(self.target.kernel, **changes))

    def test_retile_accepts_and_preserves_data_format(self):
        self.assertEqual(check(self.source, self.target).verdict, Verdict.CHECKED)
        self.assertEqual(self.target.kernel.quantization_group, 32)
        self.assertEqual(self.target.launch.grid_blocks, 3)
        self.assertEqual(self.source.launch.grid_blocks, 2)

    def test_reverse_retile_accepts(self):
        self.assertEqual(check(self.target, retile(self.target, 32)).verdict, Verdict.CHECKED)

    def test_tail_shapes_and_blocks_accept(self):
        for rows in (1, 3, 4, 5, 7):
            for columns in (1, 31, 32, 33, 63, 64, 65, 127):
                with self.subTest(rows=rows, columns=columns):
                    source = replace(self.source, domain=Domain(rows, columns),
                                     launch=Launch(128, (rows + 3) // 4))
                    self.assertEqual(check(source, retile(source, 64)).verdict, Verdict.CHECKED)

    def test_symbolic_interpreter_matches_independent_scalar_oracle(self):
        def q(row, column):
            return (row + 2) * (column - 19)

        def scale(row, group):
            return 3 * group - row + 2

        def x(column):
            return (column % 7) - 3

        for program in (self.source, self.target):
            outputs = output_polynomials(program, Limits())
            for row, polynomial in outputs.items():
                actual = sum(count * q(r, c) * scale(r, g) * x(c)
                             for (r, c, g), count in polynomial.items())
                expected = sum(q(row, c) * scale(row, c // 32) * x(c)
                               for c in range(program.domain.columns))
                self.assertEqual(actual, expected)

    def test_changed_quantization_rejected(self):
        report = check(self.source, self.mutate_kernel(quantization_group=64))
        self.assertEqual(report.verdict, Verdict.REJECTED)
        self.assertIn("monomial", report.diagnostic)

    def test_scope_is_fixed_shape_not_general_program_equivalence(self):
        source = replace(self.source, domain=Domain(5, 31))
        target = retile(source, 64)
        target = replace(target, kernel=replace(target.kernel, quantization_group=64))
        report = check(source, target)
        self.assertEqual(report.verdict, Verdict.CHECKED)
        self.assertEqual(report.domain["columns"], 31)
        # Crossing the data-format boundary exposes the same rewrite error.
        self.assertEqual(check(self.source, self.mutate_kernel(quantization_group=64)).verdict,
                         Verdict.REJECTED)

    def test_stale_launch_rejected(self):
        target = replace(self.target, launch=self.source.launch)
        self.assertEqual(check(self.source, target).verdict, Verdict.REJECTED)

    def test_duplicate_contributions_rejected(self):
        report = check(self.source, self.mutate_kernel(column_stride=32))
        self.assertEqual(report.verdict, Verdict.REJECTED)
        self.assertGreater(report.diagnostic["target_coefficient"], 1)

    def test_missing_reduction_stage_rejected(self):
        target = self.mutate_kernel(reduction_offsets=(16, 8, 4, 2, 1))
        self.assertEqual(check(self.source, target).verdict, Verdict.REJECTED)

    def test_repeated_reduction_stage_rejected(self):
        target = self.mutate_kernel(reduction_offsets=(32, 16, 8, 4, 2, 1, 1))
        self.assertEqual(check(self.source, target).verdict, Verdict.REJECTED)

    def test_wrong_writer_rejected(self):
        self.assertEqual(check(self.source, self.mutate_kernel(writer_lane=1)).verdict,
                         Verdict.REJECTED)

    def test_out_of_group_writer_rejected(self):
        self.assertEqual(check(self.source, self.mutate_kernel(writer_lane=64)).verdict,
                         Verdict.REJECTED)

    def test_mismatched_route_width_rejected(self):
        target = self.mutate_kernel(reduction_width=32, reduction_offsets=(16, 8, 4, 2, 1))
        self.assertEqual(check(self.source, target).verdict, Verdict.REJECTED)

    def test_cross_group_route_rejected_when_all_lanes_active(self):
        source = replace(self.source, domain=Domain(4, 65), launch=Launch(128, 1))
        target = replace(source, kernel=replace(source.kernel, reduction_width=64,
                                               reduction_offsets=(32, 16, 8, 4, 2, 1)))
        self.assertEqual(check(source, target).verdict, Verdict.REJECTED)

    def test_inactive_collective_member_unknown(self):
        target = replace(self.source, kernel=replace(self.source.kernel, reduction_width=64,
                                                     reduction_offsets=(32, 16, 8, 4, 2, 1)))
        self.assertEqual(check(self.source, target).verdict, Verdict.UNKNOWN)

    def test_floating_point_contract_unknown(self):
        source = replace(self.source, numeric_contract="float32")
        self.assertEqual(check(source, retile(source, 64)).verdict, Verdict.UNKNOWN)

    def test_different_external_domains_unknown(self):
        target = replace(self.target, domain=Domain(5, 64))
        self.assertEqual(check(self.source, target).verdict, Verdict.UNKNOWN)

    def test_invalid_source_does_not_authorize_adaptation(self):
        source = replace(self.source, launch=Launch(128, 1))
        self.assertEqual(check(source, self.target).verdict, Verdict.UNKNOWN)
        self.assertEqual(adapt_model(source, 64)["decision"], "refuse_adaptation")

    def test_relative_equivalence_does_not_assert_algorithm_intent(self):
        source = replace(self.source, kernel=replace(self.source.kernel, reduction_offsets=()))
        self.assertEqual(check(source, source).verdict, Verdict.CHECKED)
        self.assertEqual(check(source, self.target).verdict, Verdict.REJECTED)

    def test_budget_exhaustion_unknown(self):
        report = check(self.source, self.target, Limits(max_expansion=1))
        self.assertEqual(report.verdict, Verdict.UNKNOWN)
        self.assertEqual(report.limits["max_expansion"], 1)

    def test_shape_limit_unknown(self):
        self.assertEqual(check(self.source, self.target, Limits(max_rows=4)).verdict,
                         Verdict.UNKNOWN)

    def test_unsupported_width_unknown(self):
        self.assertEqual(check(self.source, self.mutate_kernel(cooperation_width=16)).verdict,
                         Verdict.UNKNOWN)

    def test_partial_block_group_unknown(self):
        target = replace(self.target, launch=Launch(96, 5))
        self.assertEqual(check(self.source, target).verdict, Verdict.UNKNOWN)

    def test_reports_bind_models_and_guarantee_scope(self):
        report = check(self.source, self.target)
        self.assertEqual(report.source_sha256, self.source.fingerprint())
        self.assertEqual(report.target_sha256, self.target.fingerprint())
        self.assertNotEqual(report.source_sha256, report.target_sha256)
        self.assertIn("unbounded_integer", report.scope)
        self.assertIn("HIP/CUDA source correspondence", report.not_established)
        result = adapt_model(self.source, 64)
        self.assertEqual(result["decision"], "accept_model_candidate")
        self.assertFalse(result["deployable_gpu_artifact"])

    def test_invalid_budget_rejected(self):
        for value in (0, -1, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Limits(max_expansion=value)

    def test_invalid_retile_width_rejected(self):
        with self.assertRaises(ValueError):
            retile(self.source, 16)

    def test_retile_partial_block_rejected(self):
        with self.assertRaises(ValueError):
            retile(replace(self.source, launch=Launch(96, 2)), 64)
