#!/usr/bin/env python3
"""Red-first public contracts for the irreversible A5 holdout opening."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from run_a5_holdout import (
    HoldoutRunError,
    create_opening_marker,
    evaluate_l1_repeatability,
    pin_corpus_contract,
    validate_frozen_candidate,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HoldoutRunnerTests(unittest.TestCase):
    def test_corpus_rebuild_and_launcher_pin_cannot_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus = root / "corpus-manifest.json"
            contract = root / "contract.json"
            corpus.write_text('{"version": 2}\n', encoding="utf-8")
            contract.write_text(
                json.dumps(
                    {
                        "corpus_manifest_hash": "old",
                        "corpus_manifest_path": "corpus-manifest.json",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            actual = pin_corpus_contract(contract, corpus)
            self.assertEqual(actual, sha(corpus))
            self.assertEqual(
                actual,
                json.loads(contract.read_text(encoding="utf-8"))["corpus_manifest_hash"],
            )

    def test_l1_repeatability_enforces_point_one_percentage_point_band(self) -> None:
        inside = evaluate_l1_repeatability(
            {"metrics": {"speaker_accuracy": 0.9000}},
            {"metrics": {"speaker_accuracy": 0.9009}},
        )
        outside = evaluate_l1_repeatability(
            {"metrics": {"speaker_accuracy": 0.9000}},
            {"metrics": {"speaker_accuracy": 0.9011}},
        )
        self.assertTrue(inside["pass"])
        self.assertFalse(outside["pass"])
        self.assertEqual(0.1, outside["limit_pp"])

    def test_opening_marker_is_exclusive_and_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "opening-start.json"
            create_opening_marker(marker, {"opening": 1})
            original = marker.read_bytes()
            with self.assertRaisesRegex(HoldoutRunError, "holdout_already_opened"):
                create_opening_marker(marker, {"opening": 2})
            self.assertEqual(original, marker.read_bytes())

    def test_frozen_candidate_refuses_any_pinned_byte_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = root / "spec.json"
            implementation = root / "candidate.py"
            runner = root / "runner.py"
            dev_manifest = root / "dev.sha256"
            family = {
                "candidate_family": {
                    "change_evidence": {"canonical_min_score": 0.35},
                    "energy_vad": {"frame_seconds": 0.02},
                    "family_id": "frozen-v4",
                    "grouping": {"uses_ahc": False},
                    "tape_windows": {"hard_cap_samples": 40000},
                }
            }
            spec.write_text(json.dumps(family), encoding="utf-8")
            implementation.write_text("candidate-v4\n", encoding="utf-8")
            runner.write_text("runner-v4\n", encoding="utf-8")
            dev_manifest.write_text("sealed\n", encoding="utf-8")
            config = {
                "candidate_family": "frozen-v4",
                "candidate_frozen": True,
                "candidate_implementation_path": implementation.name,
                "candidate_implementation_sha256": sha(implementation),
                "candidate_runner_path": runner.name,
                "candidate_runner_sha256": sha(runner),
                "candidate_spec_path": spec.name,
                "candidate_spec_sha256": sha(spec),
                "dev_evidence_manifest_sha256": sha(dev_manifest),
                "thresholds": {
                    key: family["candidate_family"][key]
                    for key in ("change_evidence", "energy_vad", "grouping", "tape_windows")
                },
            }
            validate_frozen_candidate(config, family, root=root, dev_manifest=dev_manifest)
            runner.write_text("mutated\n", encoding="utf-8")
            with self.assertRaisesRegex(HoldoutRunError, "holdout_candidate_runner_hash_mismatch"):
                validate_frozen_candidate(config, family, root=root, dev_manifest=dev_manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
