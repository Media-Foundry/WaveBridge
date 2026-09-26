"""Explicit route models only; no source or GPU equivalence is asserted."""
import copy
import itertools
import unittest

from wavebridge.verification.block_routes import compare


def model(width=32, block=256):
    stages = []
    offset = width // 2
    while offset:
        stages.append(offset)
        offset //= 2
    return dict(block_threads=block, width=width, offsets=stages,
                second_offsets=list(stages), writer_lane=0, shared_slots=32,
                barrier=True, load_offset=0)


class BlockRouteComparisonTests(unittest.TestCase):
    def test_same_model_has_identical_order_without_claiming_fp(self):
        result = compare(model(), model())
        self.assertEqual("evidence", result["status"])
        self.assertTrue(result["contribution_multisets_equal"])
        self.assertTrue(result["ordered_add_dags_equal"])
        self.assertEqual([], result["differing_output_threads"])
        self.assertEqual("not_checked", result["floating_point_equivalence"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_width_change_preserves_counts_but_not_order(self):
        result = compare(model(), model(64))
        self.assertEqual("evidence", result["status"])
        self.assertTrue(result["contribution_multisets_equal"])
        self.assertFalse(result["ordered_add_dags_equal"])
        self.assertEqual(list(range(256)), result["differing_output_threads"])
        self.assertNotEqual(result["input_sha256"]["source"], result["input_sha256"]["target"])

    def test_stage_order_and_writer_operand_order_are_not_normalized(self):
        for key, value in (("offsets", [1, 2, 4, 8, 16]),
                           ("second_offsets", [1, 2, 4, 8, 16]), ("writer_lane", 1)):
            changed = model()
            changed[key] = value
            result = compare(model(), changed)
            self.assertTrue(result["contribution_multisets_equal"])
            self.assertFalse(result["ordered_add_dags_equal"])

    def test_capacity_change_is_not_an_arithmetic_change_or_memory_proof(self):
        target = {**model(), "shared_slots": 64}
        result = compare(model(), target)
        self.assertTrue(result["ordered_add_dags_equal"])
        self.assertNotEqual(result["input_sha256"]["source"], result["input_sha256"]["target"])
        self.assertEqual("not_checked", result["checks"]["target"]["runtime_shared_capacity"])
        self.assertFalse(result["deployable"])

    def test_bad_multiplicity_capacity_and_missing_barrier_are_not_evidence(self):
        for key, value, status in (("offsets", [16, 8, 4, 2, 2], "rejected"),
                                   ("second_offsets", [16, 8, 4, 2, 1, 1], "rejected"),
                                   ("shared_slots", 0, "rejected"),
                                   ("load_offset", 1, "rejected"),
                                   ("barrier", False, "unknown")):
            for side in (0, 1):
                models = [model(), model()]
                models[side][key] = value
                result = compare(*models)
                self.assertEqual(status, result["status"], result)
                self.assertIsNone(result["contribution_multisets_equal"])

    def test_missing_fields_defaults_and_different_blocks_are_unknown(self):
        variants = [None, {}, {**model(), "extra": 0}]
        for key in model():
            missing = model()
            del missing[key]
            variants.append(missing)
        variants.extend([{**model(), "second_offsets": None}, {**model(), "shared_slots": None}])
        for variant in variants:
            for sides in ((model(), variant), (variant, model())):
                self.assertEqual("unknown", compare(*sides)["status"])
        result = compare(model(), model(block=128))
        self.assertEqual("different_block_input_mapping_not_established", result["reason"])

    def test_input_is_not_mutated_and_dag_size_is_bounded(self):
        left, right = model(32, 1024), model(64, 1024)
        before = copy.deepcopy((left, right))
        result = compare(left, right)
        self.assertEqual(before, (left, right))
        self.assertEqual("evidence", result["status"])
        self.assertLessEqual(result["interned_nodes"], 1024 * (1 + 2 * 5 + 2 * 6) + 1)

    def test_small_models_match_independent_expanded_ordered_trees(self):
        def expanded(configuration):
            block, width = configuration["block_threads"], configuration["width"]

            def reduce_groups(values, offsets):
                for distance in offsets:
                    updated = []
                    for start in range(0, block, width):
                        group = values[start:start + width]
                        updated.extend(("+", group[lane], group[lane ^ distance])
                                       for lane in range(width))
                    values = updated
                return values

            first = reduce_groups([("x", tid) for tid in range(block)], configuration["offsets"])
            partials = first[configuration["writer_lane"]::width]
            group = partials + [("zero",)] * (width - len(partials))
            return reduce_groups(group * (block // width), configuration["second_offsets"])

        # Expanded tuples are intentionally independent of the interned-DAG implementation.
        for block in (4, 8):
            models = []
            for width in (4, 8):
                if width > block:
                    continue
                original = model(width, block)
                for stages in itertools.permutations(original["offsets"]):
                    for writer in range(width):
                        models.append({**original, "offsets": list(stages), "writer_lane": writer})
            reference = models[0]
            left = expanded(reference)
            for target in models:
                right = expanded(target)
                expected = [tid for tid in range(block) if left[tid] != right[tid]]
                result = compare(reference, target)
                self.assertEqual("evidence", result["status"])
                self.assertEqual(expected, result["differing_output_threads"])
                self.assertEqual(not expected, result["ordered_add_dags_equal"])


if __name__ == "__main__":
    unittest.main()
