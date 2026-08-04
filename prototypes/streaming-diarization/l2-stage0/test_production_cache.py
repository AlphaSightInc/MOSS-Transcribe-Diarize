#!/usr/bin/env python3
"""A1.2 derived-cache fidelity contract."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from production_cache import (  # noqa: E402
    PlannerConfig,
    build_cache,
    plan_reference,
    production_planner_bindings,
    validate_cache,
)
from rebuild_caches import select_scope  # noqa: E402


CONFIG = PlannerConfig(
    sample_rate=16000,
    min_speech_samples=1600,
    min_silence_samples=8000,
    pre_speech_padding_samples=0,
    post_speech_padding_samples=0,
    hard_cap_samples=40000,
    min_evidence_samples=8000,
)


class FakeEmbedder:
    def embed(self, _audio_path: Path, intervals: list[tuple[float, float]]) -> list[float]:
        return [sum(end - start for start, end in intervals), 1.0]


class ProductionCacheTest(unittest.TestCase):
    def test_planner_is_bound_to_production_endpoint_policy(self) -> None:
        bindings = production_planner_bindings()
        self.assertEqual(
            bindings["policy"],
            "moss_transcribe_diarize.app.live_endpoint.EndpointPolicy",
        )
        self.assertEqual(
            bindings["source_path"],
            "moss_transcribe_diarize/app/live_endpoint.py",
        )

    def test_exact_endpoint_plan_preserves_silence_span_ids_and_hard_caps(self) -> None:
        rows = [(0.0, 3.0, "speaker-a", "one"), (3.6, 4.6, "speaker-a", "two")]
        plan = plan_reference(rows, total_samples=5 * 16000, config=CONFIG)
        self.assertEqual(
            [(span.span_id, span.start_sample, span.end_sample, span.reason) for span in plan.spans],
            [
                (0, 0, 40000, "hard_cap"),
                (1, 40000, 48000, "end_silence"),
                (2, 48000, 57600, "leading_silence"),
                (3, 57600, 80000, "flush"),
            ],
        )
        self.assertEqual([(unit.span_id, unit.true_speaker) for unit in plan.units], [(0, 0), (1, 0), (3, 0)])

    def test_built_cache_matches_its_own_production_replan(self) -> None:
        rows = [(0.0, 1.2, "speaker-a", "one"), (1.8, 3.0, "speaker-a", "two")]
        plan = plan_reference(rows, total_samples=3 * 16000, config=CONFIG)
        with tempfile.TemporaryDirectory(prefix="moss-l2-cache-test-") as temp:
            root = Path(temp)
            target = root / "harness_cache.npz"
            audio = root / "audio.wav"
            audio.write_bytes(b"fake-embedder-does-not-read-audio")
            stats = build_cache(
                plan,
                audio_path=audio,
                output_path=target,
                embedder=FakeEmbedder(),
                config=CONFIG,
            )
            fidelity = validate_cache(target, plan, config=CONFIG)
        self.assertEqual(stats["unit_count"], 2)
        self.assertEqual(stats["vector_count"], 2)
        self.assertEqual(fidelity["self_replan"], "PASS")

    def test_non_holdout_scope_never_resolves_holdout_paths(self) -> None:
        corpus = {
            "cases": [
                {"case_id": "dev", "split": "development", "reference_path": "dev.jsonl"},
                {
                    "case_id": "sealed",
                    "split": "blind_holdout",
                    "audio_path": "must-not-read.wav",
                    "reference_path": "must-not-read.jsonl",
                    "vector_cache_path": "must-not-read.npz",
                },
            ]
        }
        selected, excluded = select_scope(corpus, "non-holdout", candidate={"candidate_frozen": False})
        self.assertEqual([case["case_id"] for case in selected], ["dev"])
        self.assertEqual(excluded, ["sealed"])

    def test_holdout_rebuild_refuses_before_a5_opening(self) -> None:
        corpus = {"cases": [{"case_id": "sealed", "split": "blind_holdout"}]}
        with self.assertRaisesRegex(RuntimeError, "cache_holdout_before_a5_opening"):
            select_scope(corpus, "holdout", candidate={"candidate_frozen": False})


if __name__ == "__main__":
    unittest.main()
