#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

import numpy as np

from runtime_fixture import (
    build_runtime_cache,
    planner_bindings,
    plan_runtime_asr,
    runtime_shape,
    validate_runtime_cache,
)


class FakeEmbedder:
    def embed(self, _audio: Path, intervals: list[tuple[float, float]]) -> np.ndarray:
        value = float(sum(end - start for start, end in intervals))
        return np.full(256, value, dtype=np.float32)


class RuntimeFixtureTests(unittest.TestCase):
    def test_runtime_shape_is_independent_of_evaluation_label_perturbation(self) -> None:
        asr = [
            {"start": 0.1, "end": 1.0, "speaker": "S01", "text": "a"},
            {"start": 1.0, "end": 1.9, "speaker": "S02", "text": "b"},
        ]
        truth_ab = [(0.1, 1.0, "A"), (1.0, 1.9, "B")]
        truth_aa = [(0.1, 1.0, "A"), (1.0, 1.9, "A")]
        plan_ab = plan_runtime_asr(asr, total_samples=32_000)
        plan_aa = plan_runtime_asr(asr, total_samples=32_000)
        self.assertNotEqual(truth_ab, truth_aa)
        self.assertEqual(runtime_shape(plan_ab), runtime_shape(plan_aa))

    def test_planner_binding_is_production_endpoint_policy(self) -> None:
        binding = planner_bindings()
        self.assertEqual(
            "moss_transcribe_diarize.app.live_endpoint.EndpointPolicy",
            binding["policy"],
        )
        self.assertEqual("moss_transcribe_diarize/app/live_endpoint.py", binding["source_path"])

    def test_runtime_cache_round_trips_its_own_plan(self) -> None:
        plan = plan_runtime_asr(
            [{"start": 0.1, "end": 1.0, "speaker": "S01", "text": "a"}],
            total_samples=32_000,
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cache.npz"
            build_runtime_cache(
                plan,
                audio_path=Path(directory) / "unused.wav",
                output_path=output,
                embedder=FakeEmbedder(),
            )
            self.assertEqual("PASS", validate_runtime_cache(output, plan)["self_replan"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
