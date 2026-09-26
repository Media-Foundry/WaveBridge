from fractions import Fraction
import itertools
import unittest

from experiments.reduction_rounding_witness import model, rounded_add, witness
from wavebridge.verification.block_roundoff import compare, MAX_FINITE


def fraction(value):
    return Fraction(int(value["numerator"]), int(value["denominator"]))


def small_model(width):
    stages = [1] if width == 2 else [2, 1]
    return {"block_threads": 4, "width": width, "offsets": stages,
            "second_offsets": stages, "writer_lane": 0, "shared_slots": 4 // width,
            "load_offset": 0, "barrier": True}


def exact_simulation(values, width):
    """Independent fixed canonical routes, integer RNE, not the bound recurrence."""
    def reduce(lanes):
        for distance in ([1] if width == 2 else [2, 1]):
            old = lanes
            lanes = [rounded_add(old[i], old[(i // width) * width + ((i % width) ^ distance)])
                     for i in range(4)]
        return lanes
    first = reduce(values)
    shared = [first[g * width] for g in range(4 // width)]
    return reduce([shared[t % width] if t % width < len(shared) else 0 for t in range(4)])


class BlockRoundoffTests(unittest.TestCase):
    def test_default_routes_have_exact_conditional_bounds(self):
        result = compare(model(32), model(64), leaf_upper_bound=Fraction(16))
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["sides"]["source"]["max_addition_depth"], 10)
        self.assertEqual(result["sides"]["target"]["max_addition_depth"], 12)
        u = Fraction(1, 1 << 24)
        expected = (1 + u) ** 10 + (1 + u) ** 12 - 2
        self.assertEqual(fraction(result["difference_bound"]["relative_coefficient"]), expected)
        self.assertEqual(fraction(result["difference_bound"]["S_upper_bound"]), 4096)
        for key in ("source_program_checked", "deployable", "external_fp_model_verified",
                    "numeric_contract_checked", "leaf_bound_established_from_source"):
            self.assertFalse(result[key])

    def test_prior_rounding_witness_is_inside_bound(self):
        result = compare(model(32), model(64), leaf_upper_bound=Fraction(1))
        observed = witness()
        difference = Fraction(abs(int(observed["source_thread0_units"]) -
                                  int(observed["target_thread0_units"])), 1 << 149)
        self.assertGreater(difference, 0)
        bound = result["difference_bound"]
        total = 1 + Fraction(2, 1 << 24)
        self.assertLessEqual(difference, fraction(bound["relative_coefficient"]) * total +
                             fraction(bound["absolute_allowance"]))

    def test_small_domain_exhaustive_against_exact_rounding(self):
        report = compare(small_model(2), small_model(4), leaf_upper_bound=Fraction(1))
        self.assertEqual(report["status"], "checked")
        for inputs in itertools.product((0, 1, 1 << 23, 1 << 125, 1 << 149), repeat=4):
            total = Fraction(sum(inputs), 1 << 149)
            outputs = [exact_simulation(inputs, width) for width in (2, 4)]
            for side, actual in zip(("source", "target"), outputs):
                limits = report["sides"][side]
                allowance = fraction(limits["relative_coefficient"]) * total + fraction(limits["absolute_allowance"])
                for value in actual:
                    self.assertLessEqual(abs(Fraction(value, 1 << 149) - total), allowance)
                    self.assertLessEqual(Fraction(value, 1 << 149), fraction(limits["computed_output_upper_bound"]))
            limits = report["difference_bound"]
            allowance = fraction(limits["relative_coefficient"]) * total + fraction(limits["absolute_allowance"])
            for left, right in zip(*outputs):
                self.assertLessEqual(Fraction(abs(left - right), 1 << 149), allowance)

    def test_zero_domain_is_supported_without_claiming_tight_bound(self):
        result = compare(small_model(2), small_model(4), leaf_upper_bound=Fraction(0))
        self.assertEqual(result["status"], "checked")
        self.assertEqual(fraction(result["difference_bound"]["S_upper_bound"]), 0)
        self.assertGreater(fraction(result["difference_bound"]["absolute_allowance"]), 0)

    def test_bad_coverage_rejected_and_missing_premise_unknown(self):
        missing = model(32)
        missing["offsets"] = [8, 4, 2, 1]
        self.assertEqual(compare(missing, model(64), leaf_upper_bound=Fraction(1))["status"], "rejected")
        missing = model(32)
        missing["barrier"] = False
        self.assertEqual(compare(missing, model(64), leaf_upper_bound=Fraction(1))["status"], "unknown")

    def test_invalid_leaf_domain_and_overflow_stay_unknown(self):
        for limit in (1, 1.0, True, "1", Fraction(-1), MAX_FINITE + 1,
                      Fraction(1, 1 << 4097)):
            with self.subTest(limit_type=type(limit)):
                self.assertEqual(compare(model(32), model(64), leaf_upper_bound=limit)["status"], "unknown")
        result = compare(model(32), model(64), leaf_upper_bound=MAX_FINITE)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "finite_intermediate_bound_not_established")


if __name__ == "__main__":
    unittest.main()
