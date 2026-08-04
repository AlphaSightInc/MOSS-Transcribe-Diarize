#!/usr/bin/env python3
"""Red-first behavior contract for candidate family v2."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import wave


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from candidate_engine import (
    CandidateConfig,
    RuntimeUnit,
    WindowEvidence,
    propose_continuity_rescue_from_windows,
)
from run_candidates import pcm_chunks


class ContinuityCandidateTests(unittest.TestCase):
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

    def test_independent_continuity_evidence_rescues_unattributed_unit(self) -> None:
        units = (
            RuntimeUnit(0, "S01", 0.0, 2.0, ((0.0, 2.0),), "speaker-0001", 2.0, (1.0, 0.0)),
            RuntimeUnit(1, "S01", 2.0, 4.0, ((2.0, 4.0),), None, 2.0, None),
            RuntimeUnit(2, "S01", 4.0, 6.0, ((4.0, 6.0),), "speaker-0002", 2.0, (0.0, 1.0)),
        )
        windows = (
            WindowEvidence(0.0, 1.5, (1.0, 0.0)),
            WindowEvidence(2.0, 3.5, (0.0, 1.0)),
            WindowEvidence(2.5, 4.0, (0.01, 0.99)),
            WindowEvidence(4.0, 5.5, (0.0, 1.0)),
        )
        proposal = propose_continuity_rescue_from_windows(units, windows, self.config)
        self.assertEqual(1, len(proposal.revision.corrections))
        self.assertEqual("speaker-0002", proposal.revision.corrections[0].canonical_speaker)

    def test_attributed_l1_unit_is_never_rewritten(self) -> None:
        units = (
            RuntimeUnit(0, "S01", 0.0, 2.0, ((0.0, 2.0),), "speaker-0001", 2.0, (1.0, 0.0)),
            RuntimeUnit(1, "S01", 2.0, 4.0, ((2.0, 4.0),), "speaker-0001", 2.0, (1.0, 0.0)),
            RuntimeUnit(2, "S01", 4.0, 6.0, ((4.0, 6.0),), "speaker-0002", 2.0, (0.0, 1.0)),
        )
        windows = (
            WindowEvidence(0.0, 1.5, (1.0, 0.0)),
            WindowEvidence(2.0, 3.5, (0.0, 1.0)),
            WindowEvidence(4.0, 5.5, (0.0, 1.0)),
        )
        proposal = propose_continuity_rescue_from_windows(units, windows, self.config)
        self.assertEqual((), proposal.revision.corrections)

    def test_tape_reader_is_lazy_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "bounded.wav"
            with wave.open(str(audio_path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                output.writeframes(b"\x00\x00" * 80001)
            chunks = pcm_chunks(audio_path, hard_cap_samples=40000)
            self.assertNotIsInstance(chunks, tuple)
            iterator = iter(chunks)
            self.assertEqual(40000, len(next(iterator).samples))
            self.assertEqual(40000, len(next(iterator).samples))
            self.assertEqual(1, len(next(iterator).samples))
            with self.assertRaises(StopIteration):
                next(iterator)


if __name__ == "__main__":
    unittest.main(verbosity=2)
