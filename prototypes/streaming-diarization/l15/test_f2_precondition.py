#!/usr/bin/env python3

from __future__ import annotations

import unittest

from f2_candidate import (
    F2Config,
    apply_lane_prior,
    audit_f2_chain,
    measure_lane_prior,
    semantic_hash,
)


class F2PreconditionTests(unittest.TestCase):
    @staticmethod
    def units() -> list[dict[str, object]]:
        return [
            {"unit_id": "l0", "capture_lane": "local-mic", "duration_seconds": 1.0, "vector": [1.0, 0.0]},
            {"unit_id": "l1", "capture_lane": "local-mic", "duration_seconds": 2.0, "vector": [0.9, 0.1]},
            {"unit_id": "r0", "capture_lane": "remote-system", "duration_seconds": 1.0, "vector": [0.0, 1.0]},
            {"unit_id": "r1", "capture_lane": "remote-system", "duration_seconds": 2.0, "vector": [0.1, 0.9]},
        ]

    def test_full_chain_has_no_golden_access(self) -> None:
        audit = audit_f2_chain()
        self.assertTrue(audit["passed"], audit)

    def test_label_perturbation_cannot_change_runtime_shape_or_decision(self) -> None:
        truth_ab = [(0.0, 1.0, "A"), (1.0, 2.0, "B")]
        truth_aa = [(0.0, 1.0, "A"), (1.0, 2.0, "A")]
        first = measure_lane_prior(self.units(), F2Config(0.1))
        second = measure_lane_prior(self.units(), F2Config(0.1))
        self.assertNotEqual(truth_ab, truth_aa)
        self.assertEqual(semantic_hash(first), semantic_hash(second))

    def test_soft_prior_changes_margin_without_changing_runtime_shape(self) -> None:
        control = measure_lane_prior(self.units(), F2Config(0.0))
        candidate = measure_lane_prior(self.units(), F2Config(0.2))
        self.assertEqual(control["unit_count"], candidate["unit_count"])
        self.assertGreater(candidate["margin"]["weighted_mean_delta"], 0.0)
        self.assertFalse(candidate["identity_accuracy_claim"])

    def test_unknown_lane_is_exactly_neutral(self) -> None:
        scores = {"speaker-0001": 0.7, "speaker-0002": 0.6}
        self.assertEqual(
            scores,
            apply_lane_prior(
                scores,
                unit_lane="unknown",
                canonical_lanes={"speaker-0001": "local-mic", "speaker-0002": "remote-system"},
                prior_strength=0.2,
            ),
        )

    def test_cross_lane_is_soft_not_hard(self) -> None:
        adjusted = apply_lane_prior(
            {"speaker-0001": 0.7, "speaker-0002": 0.6},
            unit_lane="local-mic",
            canonical_lanes={"speaker-0001": "local-mic", "speaker-0002": "remote-system"},
            prior_strength=0.2,
        )
        self.assertEqual(0.7, adjusted["speaker-0001"])
        self.assertAlmostEqual(0.48, adjusted["speaker-0002"])
        self.assertGreater(adjusted["speaker-0002"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
