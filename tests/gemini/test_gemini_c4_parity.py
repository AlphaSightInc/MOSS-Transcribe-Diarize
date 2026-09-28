"""Zero-send C4 parity through the real LiveSession publication path.

Requires the retained P61 cache in the sibling gemini-live worktree. No provider
or encoder is called: both implementations consume its identical words/vectors.
"""
from __future__ import annotations

import hashlib
import importlib
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from moss_transcribe_diarize.app.gemini_continuity_registry import ContinuityRegistry
from moss_transcribe_diarize.app.gemini_hybrid_engine import (
    GeminiHybridEngine, GrowingContextWindowScheduler, attributed_embedding_intervals,
)
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiLiveRuntime, ScriptedGeminiEngine
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds, LiveServiceConfigHashes, LiveServiceDescriptor,
)
from moss_transcribe_diarize.app.live_session import AudioFrame


@pytest.mark.parametrize("case_id", (
    "discussion_jamie_dimon_180s", "discussion_rtfl_90s",
    "interview_adam_frank_180s", "interview_bill_ackman_60s",
    "interview_keyu_jin_60s", "mono_javier_intro_50s",
))
def test_c4_cached_case_matches_prototype_der_through_snapshot(case_id, tmp_path):
    prototype = (Path(__file__).resolve().parents[3]
                 / "MOSS-Transcribe-Diarize-wt-gemini-live/prototypes/gemini-live/continuity")
    if not (prototype / "parity.py").exists():
        pytest.skip("P61 retained C4 cache is absent")
    sys.path.insert(0, str(prototype))
    parity = importlib.import_module("parity")
    clip = next(clip for clip in parity.clips("accept6") if clip.clip_id == case_id)
    observations, baseline = parity.load(clip, False)
    for observation in observations:
        intervals = attributed_embedding_intervals(
            parity.product_words(observation), round(observation["start"] * 16000))
        for label in {word["speaker"] for word in observation["words"]}:
            prototype_intervals = parity.embedding_intervals(
                observation["start"], observation["words"], label)
            runtime_intervals = intervals.get(label, [])
            assert len(runtime_intervals) == len(prototype_intervals)
            for (start, end), (expected_start, expected_end) in zip(
                    runtime_intervals, prototype_intervals):
                assert abs(start / 16000 - expected_start) <= 2 / 16000
                assert abs(end / 16000 - expected_end) <= 2 / 16000
    duration = round(baseline["duration_s"])
    descriptor = LiveServiceDescriptor(
        source_revision="C4-parity", provider_name="gemini", provider_revision="cached",
        provider_manifest_hash=hashlib.sha256(b"C4-parity").hexdigest(),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={}, identity_config={}, decoder_config={}),
        bounds=LiveServiceBounds(max_frame_samples=16000, max_queue_depth=4,
                                 max_retained_samples=(duration + 1)*16000,
                                 max_identity_speakers=16, max_events=128,
                                 max_tape_bytes=(duration + 1)*32000),
        frame_samples=16000,
    )
    runtime = GeminiLiveRuntime(
        descriptor=descriptor, tape_storage_root=tmp_path,
        engine_factory=lambda _id, publish, _usage: ScriptedGeminiEngine(
            publish, batches=[], terminal=()),
    )
    runtime.create(session_id="parity")
    for sequence in range(duration):
        runtime.accept_frame("parity", AudioFrame(sequence=sequence,
                             pcm=bytes(32000), sample_count=16000))

    class Unused:
        def words(self, _pcm, *, deadline):
            raise AssertionError("cached parity must not call Gemini Live")
        def diarize(self, _pcm, *, deadline, kind, diarize=True):
            raise AssertionError("cached parity must not call Gemini batch")
        def transcribe(self, _tape):
            raise AssertionError("cached parity must not run final")

    cached_vectors = {}
    engine = GeminiHybridEngine(
        lambda update: runtime.publish_update("parity", update),
        word_source=Unused(),
        window_scheduler=GrowingContextWindowScheduler(max_seconds=180, stride_seconds=15),
        registry=ContinuityRegistry(embedding_threshold=.46,
                                    within_window_threshold=.6, birth_min_seconds=2),
        diarizer=Unused(), terminal=Unused(),
        embedding_source=lambda _pcm, _start, _words: cached_vectors,
    )
    try:
        for observation in observations:
            cached_vectors = {label: (tuple(vector), 2.0)
                              for label, vector in observation["embeddings"].items()}
            start = round(observation["start"] * 16000)
            end = round(observation["end"] * 16000)
            words = tuple(replace(word, start_sample=word.start_sample-start,
                                  end_sample=word.end_sample-start)
                          for word in parity.product_words(observation))
            engine._publish_window(start, end, bytes((end-start)*2), words)
        rows = runtime.snapshot("parity").to_dict()["session"]["effective_transcript"]
        segments = [{"start": row["start_sample"] / 16000,
                     "end": row["end_sample"] / 16000,
                     "speaker": parity.canonical(row["canonical_speaker"]),
                     "text": row["text"]} for row in rows]
        actual = parity.score_segments(clip, segments)
        expected = baseline["by_hold"]["H0"]["variants"]["C1_C3_local_birth2"]["first"]["metrics"]["der"]
        print(f"C4 parity {case_id}: snapshot DER {actual:.6f}; prototype DER {expected:.6f}")
        assert abs(actual - expected) <= .002, (case_id, actual, expected)
    finally:
        engine.close()
