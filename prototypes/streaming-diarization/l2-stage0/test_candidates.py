#!/usr/bin/env python3
"""Red-first behavior contract for the A5 three-arm prototype."""

from __future__ import annotations

import inspect
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from candidate_engine import (
    CandidateConfig,
    CandidateError,
    RuntimeSpan,
    RuntimeUnit,
    WindowEvidence,
    group_windows,
    propose_tape_from_windows,
)
from run_candidates import (
    CandidateRunError,
    audit_candidate_source,
    publish_runtime_revision,
    select_dev_cases,
)


class CandidateEngineContractTests(unittest.TestCase):
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

    def test_adversarial_padding_outside_committed_span_is_rejected(self) -> None:
        with self.assertRaisesRegex(CandidateError, "candidate_interval_outside_committed_span"):
            RuntimeUnit(
                span_id=7,
                local_speaker="S01",
                span_start=10.0,
                span_end=12.5,
                intervals=((9.9, 11.0),),
                current_speaker="speaker-0001",
                duration_seconds=1.1,
                vector=(1.0, 0.0),
            )

    def test_grouping_is_independent_of_current_canonical_label(self) -> None:
        signature = inspect.signature(group_windows)
        self.assertNotIn("current_speaker", signature.parameters)
        windows = (
            WindowEvidence(0.0, 1.5, (1.0, 0.0)),
            WindowEvidence(0.4, 1.9, (0.99, 0.01)),
            WindowEvidence(2.0, 3.5, (0.0, 1.0)),
            WindowEvidence(2.4, 3.9, (0.01, 0.99)),
        )
        clusters = group_windows(windows, self.config)
        self.assertEqual(2, len(set(clusters)))

    def test_tape_proposal_reports_score_delta_and_changed_fraction(self) -> None:
        units = (
            RuntimeUnit(0, "S01", 0.0, 2.0, ((0.0, 2.0),), "speaker-0001", 2.0, (1.0, 0.0)),
            RuntimeUnit(1, "S01", 2.0, 4.0, ((2.0, 4.0),), None, 2.0, None),
            RuntimeUnit(2, "S01", 4.0, 6.0, ((4.0, 6.0),), "speaker-0002", 2.0, (0.0, 1.0)),
        )
        windows = (
            WindowEvidence(0.0, 1.5, (1.0, 0.0)),
            WindowEvidence(2.0, 3.5, (0.0, 1.0)),
            WindowEvidence(4.0, 5.5, (0.0, 1.0)),
        )
        proposal = propose_tape_from_windows(units, windows, self.config)
        self.assertGreaterEqual(len(proposal.revision.corrections), 1)
        self.assertGreater(proposal.changed_duration_fraction, 0.0)
        for evidence in proposal.correction_evidence:
            self.assertIn("score_delta", evidence)
            self.assertIn("changed_duration_fraction", evidence)
            self.assertEqual({"span_id", "local_speaker", "canonical_speaker"}, set(evidence["address"]))


class CandidateRunnerContractTests(unittest.TestCase):
    def test_candidate_source_has_no_reference_or_golden_path(self) -> None:
        result = audit_candidate_source()
        self.assertEqual("PASS", result["overall"])
        self.assertEqual([], result["violations"])

    def test_golden_path_source_mutation_is_refused(self) -> None:
        source = (HERE / "candidate_engine.py").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            mutated = Path(directory) / "candidate_engine.py"
            mutated.write_text(source + "\nimport json\nGOLDEN_PATH = 'forbidden'\n", encoding="utf-8")
            result = audit_candidate_source(mutated)
        self.assertEqual("FAIL", result["overall"])
        self.assertIn("forbidden_import:json", result["violations"])
        self.assertIn("forbidden_source_fragment:golden", result["violations"])

    def test_blind_holdout_is_refused_before_freeze(self) -> None:
        cases = [{"case_id": "sealed", "split": "blind_holdout", "acceptance_eligible": True}]
        with self.assertRaisesRegex(CandidateRunError, "candidate_holdout_before_freeze"):
            select_dev_cases(cases, ["sealed"], candidate_frozen=False)

    def test_production_publisher_changes_only_labels(self) -> None:
        from moss_transcribe_diarize.app.live_identity_sweep import SweepCorrection, SweepRevision

        spans = (
            RuntimeSpan(0, 0.0, 2.0, "hard_cap"),
            RuntimeSpan(1, 2.0, 4.0, "hard_cap"),
        )
        units = (
            RuntimeUnit(0, "S01", 0.0, 2.0, ((0.0, 2.0),), "speaker-0001", 2.0, (1.0, 0.0)),
            RuntimeUnit(1, "S01", 2.0, 4.0, ((2.0, 4.0),), "speaker-0001", 2.0, (0.0, 1.0)),
        )
        revision = SweepRevision(
            corrections=(
                SweepCorrection(1, "S01", "speaker-0001", "speaker-0002", "reassigned", 0.9),
            ),
            swept_spans=2,
            swept_units=2,
        )
        published = publish_runtime_revision(spans, units, revision, sample_rate=16000)
        self.assertEqual(["speaker-0001", "speaker-0002"], published["final_unit_labels"])
        self.assertTrue(published["immutability"]["words_unchanged"])
        self.assertTrue(published["immutability"]["span_bounds_unchanged"])
        self.assertTrue(published["immutability"]["word_timings_unchanged"])
        self.assertTrue(published["immutability"]["prefix_hashes_unchanged"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
