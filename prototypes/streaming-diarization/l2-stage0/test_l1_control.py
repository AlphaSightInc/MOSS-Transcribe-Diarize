#!/usr/bin/env python3
"""A2 behavior tests for the production L1 control runner."""

from __future__ import annotations

import json
import numpy as np
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_l1_control import (  # noqa: E402
    REPO,
    evaluate_alphabet_gate,
    production_bindings,
    replay_case,
    resolve_output_path,
    semantic_sha256,
)


RUNNER = HERE / "run_l1_control.py"


class L1ControlTest(unittest.TestCase):
    def test_cross_instrument_gate_requires_live_pair_band_on_production_frame(self) -> None:
        gate = {
            "absolute_tolerance": 0.005,
            "immutable_live_speaker_accuracy": [0.9135, 0.9144],
        }
        result = evaluate_alphabet_gate(0.916765, gate)
        self.assertTrue(result["passed"])
        self.assertEqual(result["absolute_deltas"], [0.003265, 0.002365])

    def test_relative_evidence_path_is_resolved_under_worktree(self) -> None:
        self.assertEqual(
            resolve_output_path(Path("prototypes/evidence/run.json")),
            REPO / "prototypes/evidence/run.json",
        )

    def test_holdout_case_is_refused_before_freeze_without_reading_case_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="moss-l2-a2-holdout-") as temp:
            root = Path(temp)
            corpus = root / "corpus.json"
            candidate = root / "candidate.json"
            corpus.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "acceptance_eligible": True,
                                "audio_path": str(root / "must-not-read.wav"),
                                "case_id": "sealed-case",
                                "reference_path": str(root / "must-not-read.jsonl"),
                                "split": "blind_holdout",
                                "vector_cache_path": str(root / "must-not-read.npz"),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            candidate.write_text(
                json.dumps(
                    {
                        "candidate_frozen": False,
                        "candidate_spec_sha256": "UNFROZEN",
                    }
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--corpus-manifest",
                    str(corpus),
                    "--candidate-config",
                    str(candidate),
                    "--case-id",
                    "sealed-case",
                    "--preflight-only",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
            self.assertIn("l1_holdout_before_candidate_freeze", completed.stdout)
            self.assertIn("<promise>BLOCKED</promise>", completed.stdout)

    def test_runner_is_bound_to_production_sweep_imports(self) -> None:
        bindings = production_bindings()
        self.assertEqual(
            bindings["ledger"],
            "moss_transcribe_diarize.app.live_identity_sweep.SweepLedger",
        )
        self.assertEqual(
            bindings["sweep"],
            "moss_transcribe_diarize.app.live_identity_sweep.sweep",
        )
        self.assertEqual(
            bindings["source_path"],
            "moss_transcribe_diarize/app/live_identity_sweep.py",
        )

    def test_replay_surfaces_production_revision_and_accuracy_metrics(self) -> None:
        with tempfile.TemporaryDirectory(prefix="moss-l2-a2-replay-") as temp:
            root = Path(temp)
            audio = root / "audio.wav"
            reference = root / "reference.jsonl"
            cache = root / "cache.npz"
            audio.write_bytes(b"cached-encoder-does-not-read-pcm")
            reference.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {"start": 0.0, "end": 1.2, "speaker": "Alice", "text": "one"}
                        ),
                        json.dumps(
                            {"start": 1.8, "end": 3.0, "speaker": "Alice", "text": "two"}
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            np.savez(
                cache,
                rows=np.asarray(
                    [(0, 0, 0.0, 1.2, 1.2, 1), (2, 0, 1.8, 3.0, 1.2, 1)],
                    dtype=np.float64,
                ),
                vec_idx=np.asarray([0, 1], dtype=np.int64),
                vecs=np.asarray([(1.0, 0.0), (1.0, 0.0)], dtype=np.float32),
                span_bounds=np.asarray(
                    [(0, 0, 19200), (1, 19200, 28800), (2, 28800, 48000)],
                    dtype=np.int64,
                ),
                span_reasons=np.asarray(["end_silence", "leading_silence", "flush"]),
            )
            case = {
                "audio_path": str(audio),
                "case_id": "toy-one-speaker",
                "duration_seconds": 3.0,
                "reference_path": str(reference),
                "speaker_count": 1,
                "split": "development",
                "vector_cache_path": str(cache),
            }
            config = json.loads((HERE / "l1-control-spec.json").read_text())["production_config"]
            result = replay_case(case, config, repo_root=root)
            repeated = replay_case(case, config, repo_root=root)
            self.assertEqual(result["metrics"]["speaker_accuracy"], 1.0)
            self.assertEqual(result["metrics"]["speaker_correctness"], {"Alice": 1.0})
            self.assertEqual(result["metrics"]["diarization_error_rate"], 0.0)
            self.assertEqual(result["changed_duration_fraction"], 0.0)
            self.assertGreaterEqual(len(result["revision_trace"]), 2)
            self.assertEqual(result["production_bindings"]["sweep"], bindings_name("sweep"))
            self.assertEqual(semantic_sha256(result), semantic_sha256(repeated))


def bindings_name(kind: str) -> str:
    return production_bindings()[kind]


if __name__ == "__main__":
    unittest.main()
