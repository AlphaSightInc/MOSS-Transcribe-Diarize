"""One command: python prototypes/gemini-live/tentative/new_speaker_probe.py.

Question: can a new settled speaker without GeminiRolling.observations seed a
same-window tentative centroid? Falsifier: speaker-0002 already appears.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/gemini"))
from test_gemini_live_runtime import descriptor  # noqa: E402
from moss_transcribe_diarize.app.gemini_live_runtime import (  # noqa: E402
    GeminiBase, GeminiLiveRuntime, GeminiRolling, GeminiSegment, ScriptedGeminiEngine,
)
from moss_transcribe_diarize.app.live_provider_bundle import LiveSpeakerJournalObservation  # noqa: E402
from moss_transcribe_diarize.app.live_session import AudioFrame  # noqa: E402

RATE = 16000

class Encoder:
    spec = type("Spec", (), {"provider": "probe", "revision": "one",
                             "embedding_dimension": 2, "state_sha256": "0" * 64})()
    def embed(self, path, intervals):
        return (0.0, 1.0)

first = LiveSpeakerJournalObservation(
    speaker_label="speaker-0001", centroid=(1.0, 0.0), sample_seconds=2.0,
    exemplar_count=1, provisional=False, embedder_id="probe:one",
    embedder_state_sha="0" * 64,
)
with tempfile.TemporaryDirectory() as scratch:
    runtime = GeminiLiveRuntime(descriptor=descriptor(), tape_storage_root=scratch,
        engine_factory=lambda _sid, publish, _usage: ScriptedGeminiEngine(
            publish, batches=[], terminal=()), voiceprint_encoder=Encoder())
    runtime.create(session_id="probe")
    for sequence in range(4):
        runtime.accept_frame("probe", AudioFrame(sequence, b"\x01\x00" * RATE, RATE))
    runtime.publish_update("probe", GeminiBase(2 * RATE, ()))
    runtime.publish_update("probe", GeminiRolling(0, 2 * RATE,
        (GeminiSegment(0, 2 * RATE, "one", "speaker-0001", "system"),), (first,),
        ("system",)))
    runtime.publish_update("probe", GeminiBase(4 * RATE, ()))
    runtime.publish_update("probe", GeminiRolling(2 * RATE, 4 * RATE,
        (GeminiSegment(2 * RATE, 4 * RATE, "two", "speaker-0002", "system"),), (),
        ("system",)))
    state = runtime._sessions["probe"]
    print(json.dumps({
        "question": "Does a later settled speaker seed the tentative centroid in one window?",
        "hypothesis": "Both canonical speakers become available without a second rolling observation",
        "falsifier": "speaker-0002 is missing from system centroid IDs",
        "settled_ids": sorted({row.canonical_speaker for row in state.session.snapshot().effective_transcript}),
        "voice_observation_ids": sorted(state.voice_observations),
        "tentative_centroid_ids": sorted(state.tentative._centroids.get("system", {})),
    }, indent=2))
    state.tentative.close()
