#!/usr/bin/env python3
"""Red-first behavior contract for candidate family v3."""

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
    propose_span_local_weak_rescue_from_windows,
)


class SpanLocalCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = CandidateConfig(
            canonical_min_score=0.35,
            canonical_min_margin=0.10,
            incumbent_improvement_margin=0.10,
            max_changed_duration_fraction=0.50,
            minimum_unit_cluster_vote_fraction=0.50,
            minimum_unit_cluster_vote_margin=0.20,
            cluster_distance_threshold=0.30,
        )

    def test_one_overlapping_window_can_rescue_weak_unattributed_unit(self) -> None:
        units = (
            RuntimeUnit(0, "S01", 0.0, 2.0, ((0.0, 2.0),), "speaker-0001", 2.0, (1.0, 0.0)),
            RuntimeUnit(1, "S01", 2.0, 4.0, ((2.0, 4.0),), None, 2.0, (0.1, 0.9)),
            RuntimeUnit(2, "S01", 4.0, 6.0, ((4.0, 6.0),), "speaker-0002", 2.0, (0.0, 1.0)),
        )
        windows = (WindowEvidence(2.0, 3.5, (0.0, 1.0)),)
        proposal = propose_span_local_weak_rescue_from_windows(units, windows, self.config)
        self.assertEqual(1, len(proposal.revision.corrections))
        self.assertEqual("speaker-0002", proposal.revision.corrections[0].canonical_speaker)

    def test_sub_floor_and_attributed_units_are_immutable(self) -> None:
        units = (
            RuntimeUnit(0, "S01", 0.0, 2.0, ((0.0, 2.0),), "speaker-0001", 2.0, (1.0, 0.0)),
            RuntimeUnit(1, "S01", 2.0, 4.0, ((2.0, 4.0),), None, 2.0, None),
            RuntimeUnit(2, "S01", 4.0, 6.0, ((4.0, 6.0),), "speaker-0002", 2.0, (0.0, 1.0)),
        )
        windows = (WindowEvidence(2.0, 3.5, (0.0, 1.0)),)
        proposal = propose_span_local_weak_rescue_from_windows(units, windows, self.config)
        self.assertEqual((), proposal.revision.corrections)


if __name__ == "__main__":
    unittest.main(verbosity=2)
