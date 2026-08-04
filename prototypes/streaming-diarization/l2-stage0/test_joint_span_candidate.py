#!/usr/bin/env python3
"""Red-first behavior contract for the final candidate family v4."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from candidate_engine import (
    CandidateConfig,
    RuntimeUnit,
    WindowEvidence,
    propose_joint_span_rescue_from_windows,
)


def config(max_fraction: float = 0.50) -> CandidateConfig:
    return CandidateConfig(
        canonical_min_score=0.35,
        canonical_min_margin=0.10,
        incumbent_improvement_margin=0.10,
        max_changed_duration_fraction=max_fraction,
        minimum_unit_cluster_vote_fraction=0.50,
        minimum_unit_cluster_vote_margin=0.20,
        cluster_distance_threshold=0.30,
    )


class JointSpanCandidateTests(unittest.TestCase):
    def test_joint_identity_prior_resolves_same_window_label_collision(self) -> None:
        units = (
            RuntimeUnit(0, "S01", 0.0, 2.0, ((0.0, 2.0),), "speaker-0001", 2.0, (1.0, 0.0)),
            RuntimeUnit(1, "S01", 4.0, 6.0, ((4.0, 6.0),), "speaker-0002", 2.0, (0.0, 1.0)),
            RuntimeUnit(2, "S01", 2.0, 4.0, ((2.0, 3.0),), None, 1.0, (0.95, 0.05)),
            RuntimeUnit(2, "S02", 2.0, 4.0, ((3.0, 4.0),), None, 1.0, (0.05, 0.95)),
        )
        windows = (
            WindowEvidence(2.0, 3.0, (0.1, 0.9)),
            WindowEvidence(3.0, 4.0, (0.1, 0.9)),
        )
        proposal = propose_joint_span_rescue_from_windows(units, windows, config())
        labels = {
            correction.local_speaker: correction.canonical_speaker
            for correction in proposal.revision.corrections
            if correction.span_id == 2
        }
        self.assertEqual({"S01": "speaker-0001", "S02": "speaker-0002"}, labels)

    def test_budget_prioritizes_full_span_before_higher_score_tail(self) -> None:
        units = (
            RuntimeUnit(0, "S01", 0.0, 2.0, ((0.0, 2.0),), "speaker-0001", 2.0, (1.0, 0.0)),
            RuntimeUnit(1, "S01", 6.0, 8.0, ((6.0, 8.0),), "speaker-0002", 2.0, (0.0, 1.0)),
            RuntimeUnit(2, "S01", 2.0, 3.0, ((2.0, 3.0),), None, 1.0, (0.60, 0.40)),
            RuntimeUnit(3, "S01", 3.0, 5.0, ((4.0, 5.0),), None, 1.0, (0.99, 0.01)),
        )
        windows = (
            WindowEvidence(2.0, 3.0, (0.60, 0.40)),
            WindowEvidence(4.0, 5.0, (0.99, 0.01)),
        )
        proposal = propose_joint_span_rescue_from_windows(units, windows, config(0.17))
        self.assertEqual(1, len(proposal.revision.corrections))
        self.assertEqual(2, proposal.revision.corrections[0].span_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
