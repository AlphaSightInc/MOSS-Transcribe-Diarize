#!/usr/bin/env python3
"""Non-gating production-scheduler probe with real PCM and controlled collaborators."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import wave
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_arbiter import InferenceArbiterBackpressure
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig, SpeechObservation
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceError,
    LiveServiceRuntime,
    _ManualCanonicalPumpScheduler,
    hash_config,
)
from moss_transcribe_diarize.app.live_transport import _failure_status
from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    FrozenSpan,
    LIVE_SAMPLE_RATE,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
)


PREREGISTRATION = Path(__file__).with_name("preregistration.json")
PREREGISTRATION_SHA256 = "b6fbe1f5dc60c0f0a20128026eefa8bc369a456927fe267cf94aa2a8b2865d52"
AUDIO = ROOT / "prototypes/streaming-diarization/l15/data/dual_lane_diarization/cases/pending_source_separation_001/remote.wav"
AUDIO_SHA256 = "5299e742325fa9d3c58946222262a8262bd7e47863c97d0f0a772956050c1c1d"
FRAME_SAMPLES = 8_000
SPAN_SAMPLES = 40_000
QUEUE_BOUND = 16


class ForcedSpeechObservation:
    """Controlled endpoint input; PCM remains the hash-pinned human-speech recording."""

    def observe(self, *, frame: AudioFrame, start_sample: int, end_sample: int) -> tuple[SpeechObservation, ...]:
        del frame
        return (SpeechObservation(start_sample=start_sample, end_sample=end_sample, speech_present=True),)


class MarkerIdentity:
    def prepare(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        transcript: str,
        base_snapshot: LiveIdentitySnapshot,
    ) -> LiveIdentityPreparation:
        del pcm
        return LiveIdentityPreparation(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            base_snapshot_version=base_snapshot.version,
            proposed_snapshot=LiveIdentitySnapshot(
                version=base_snapshot.version + 1,
                canonical_speakers=base_snapshot.canonical_speakers or ("speaker-0001",),
            ),
            relabeled_transcript=transcript,
        )


class MarkerDecoder:
    max_samples = SPAN_SAMPLES

    def __init__(self, session_id: str, ledger: list[dict[str, Any]]):
        self.session_id = session_id
        self.ledger = ledger

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        pcm_sha256 = hashlib.sha256(pcm).hexdigest()
        marker = f"marker-{self.session_id}-span-{span.id}"
        self.ledger.append(
            {
                "session_id": self.session_id,
                "span_id": span.id,
                "pcm_sha256": pcm_sha256,
                "marker": marker,
            }
        )
        return InferenceTranscript(f"[0][S01]{marker}[{span.sample_count / LIVE_SAMPLE_RATE:g}]", elapsed_sec=0.0)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_audio() -> tuple[bytes, int]:
    if _sha256(PREREGISTRATION) != PREREGISTRATION_SHA256:
        raise RuntimeError("preregistration hash drifted; refuse to measure against changed gates")
    if _sha256(AUDIO) != AUDIO_SHA256:
        raise RuntimeError("real-speech fixture hash drifted")
    with wave.open(str(AUDIO), "rb") as stream:
        shape = (stream.getnchannels(), stream.getsampwidth(), stream.getframerate())
        if shape != (1, 2, LIVE_SAMPLE_RATE):
            raise RuntimeError(f"audio shape must be mono PCM16 at 16 kHz, got {shape}")
        pcm = stream.readframes(stream.getnframes())
        return pcm, stream.getnframes()


def _slice_wrapped(pcm: bytes, *, start_sample: int, sample_count: int) -> bytes:
    total_samples = len(pcm) // 2
    pieces: list[bytes] = []
    cursor = start_sample % total_samples
    remaining = sample_count
    while remaining:
        take = min(remaining, total_samples - cursor)
        pieces.append(pcm[cursor * 2 : (cursor + take) * 2])
        remaining -= take
        cursor = 0
    return b"".join(pieces)


def _runtime(
    session_ids: list[str],
    *,
    ledger: list[dict[str, Any]],
    scheduler: _ManualCanonicalPumpScheduler,
    max_queue_depth: int,
) -> LiveServiceRuntime:
    ids = iter(session_ids)
    decoder_ids = iter(session_ids)
    descriptor = LiveServiceDescriptor(
        source_revision="controlled-dispatcher-prototype",
        provider_name="controlled-marker-decoder",
        provider_revision="v1",
        provider_manifest_hash=hash_config({"prototype": "controlled-dispatcher"}),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={"hard_cap_samples": SPAN_SAMPLES},
            identity_config={"kind": "marker-pass-through"},
            decoder_config={"kind": "controlled-marker"},
        ),
        bounds=LiveServiceBounds(
            max_frame_samples=FRAME_SAMPLES,
            max_queue_depth=max_queue_depth,
            max_retained_samples=SPAN_SAMPLES * (QUEUE_BOUND + 2),
            max_identity_speakers=1,
            max_events=4_096,
            hard_cap_samples=SPAN_SAMPLES,
        ),
        frame_samples=FRAME_SAMPLES,
    )
    return LiveServiceRuntime(
        descriptor=descriptor,
        endpoint_policy_factory=lambda: EndpointPolicy(
            EndpointPolicyConfig(min_speech_samples=1, min_silence_samples=1, hard_cap_samples=SPAN_SAMPLES)
        ),
        speech_provider_factory=ForcedSpeechObservation,
        decoder_factory=lambda: MarkerDecoder(next(decoder_ids), ledger),
        identity_preparer_factory=MarkerIdentity,
        session_id_factory=lambda: next(ids),
        _canonical_scheduler=scheduler,
    )


def _frame(pcm: bytes, *, session_index: int, sequence: int) -> AudioFrame:
    offset = (session_index * FRAME_SAMPLES * 3) + (sequence * FRAME_SAMPLES)
    frame_pcm = _slice_wrapped(pcm, start_sample=offset, sample_count=FRAME_SAMPLES)
    return AudioFrame(sequence=sequence, pcm=frame_pcm, sample_count=FRAME_SAMPLES)


def _prefix_skew(order: list[str], session_ids: list[str]) -> int:
    counts = Counter({session_id: 0 for session_id in session_ids})
    maximum = 0
    for session_id in order:
        counts[session_id] += 1
        maximum = max(maximum, max(counts.values()) - min(counts.values()))
    return maximum


def _fairness_case(pcm: bytes, meetings: int, pace_seconds: float) -> dict[str, Any]:
    session_ids = [f"fairness-{meetings}-{index}" for index in range(meetings)]
    ledger: list[dict[str, Any]] = []
    scheduler = _ManualCanonicalPumpScheduler()
    runtime = _runtime(session_ids, ledger=ledger, scheduler=scheduler, max_queue_depth=QUEUE_BOUND)
    created = [runtime.create() for _ in session_ids]
    frame_count = 4 * (SPAN_SAMPLES // FRAME_SAMPLES)
    maximum_queue_depth = {session_id: 0 for session_id in session_ids}
    started = time.monotonic()
    for sequence in range(frame_count):
        for index, result in enumerate(created):
            accepted = runtime.accept_frame(result.session_id, _frame(pcm, session_index=index, sequence=sequence))
            maximum_queue_depth[result.session_id] = max(
                maximum_queue_depth[result.session_id], accepted.snapshot.pending_work_items
            )
        target = started + ((sequence + 1) * pace_seconds)
        if pace_seconds:
            time.sleep(max(0.0, target - time.monotonic()))
    scheduler.drain()

    order = [item["session_id"] for item in ledger]
    commits = {
        session_id: [commit.transcript for commit in runtime.snapshot(session_id).session.committed]
        for session_id in session_ids
    }
    marker_isolation = all(
        all(f"marker-{session_id}-" in transcript for transcript in transcripts)
        and all(
            f"marker-{other_id}-" not in transcript
            for transcript in transcripts
            for other_id in session_ids
            if other_id != session_id
        )
        for session_id, transcripts in commits.items()
    )
    return {
        "meetings": meetings,
        "ingress_cadence_seconds": pace_seconds,
        "real_pcm_frame_seconds": FRAME_SAMPLES / LIVE_SAMPLE_RATE,
        "spans_per_session": 4,
        "maximum_queue_depth_by_session": maximum_queue_depth,
        "completed_dispatches_by_session": dict(Counter(order)),
        "maximum_prefix_dispatch_skew": _prefix_skew(order, session_ids),
        "dispatch_order": order,
        "marker_isolation": marker_isolation,
        "all_work_drained": all(runtime.snapshot(session_id).pending_work_items == 0 for session_id in session_ids),
    }


def _queue_isolation_case(pcm: bytes) -> dict[str, Any]:
    session_ids = ["saturated-session", "peer-session"]
    ledger: list[dict[str, Any]] = []
    scheduler = _ManualCanonicalPumpScheduler()
    runtime = _runtime(session_ids, ledger=ledger, scheduler=scheduler, max_queue_depth=QUEUE_BOUND)
    saturated, peer = runtime.create(), runtime.create()
    frames_per_span = SPAN_SAMPLES // FRAME_SAMPLES
    first_overflow: Exception | None = None
    for sequence in range((QUEUE_BOUND + 1) * frames_per_span):
        try:
            runtime.accept_frame(saturated.session_id, _frame(pcm, session_index=0, sequence=sequence))
        except Exception as exc:
            first_overflow = exc
            break
    retry: Exception | None = None
    try:
        runtime.accept_frame(
            saturated.session_id,
            _frame(pcm, session_index=0, sequence=(QUEUE_BOUND + 1) * frames_per_span),
        )
    except Exception as exc:
        retry = exc
    peer_result = runtime.accept_frame(peer.session_id, _frame(pcm, session_index=1, sequence=0))
    saturated_snapshot = runtime.snapshot(saturated.session_id)
    peer_snapshot = runtime.snapshot(peer.session_id)
    return {
        "configured_queue_bound": QUEUE_BOUND,
        "saturated_pending_work_items": saturated_snapshot.pending_work_items,
        "peer_pending_work_items": peer_snapshot.pending_work_items,
        "peer_frame_accepted": peer_result.ack.sequence == 0,
        "first_overflow_exception": None if first_overflow is None else type(first_overflow).__name__,
        "first_overflow_is_raw_arbiter_backpressure": isinstance(first_overflow, InferenceArbiterBackpressure),
        "retry_exception": None if retry is None else type(retry).__name__,
        "retry_failure_kind": getattr(getattr(retry, "failure", None), "kind", None),
        "retry_http_status": _failure_status(retry) if isinstance(retry, LiveServiceError) else None,
        "saturated_session_terminal": saturated_snapshot.terminal_failure is not None,
        "peer_session_terminal": peer_snapshot.terminal_failure is not None,
        "correct_nonterminal_429_semantics_observed": False,
    }


def _reconnect_marker_case(pcm: bytes) -> dict[str, Any]:
    session_ids = ["original-session", "replacement-session"]
    ledger: list[dict[str, Any]] = []
    scheduler = _ManualCanonicalPumpScheduler()
    runtime = _runtime(session_ids, ledger=ledger, scheduler=scheduler, max_queue_depth=QUEUE_BOUND)
    transcripts: dict[str, list[str]] = {}
    for index, session_id in enumerate(session_ids):
        created = runtime.create()
        for sequence in range(SPAN_SAMPLES // FRAME_SAMPLES):
            runtime.accept_frame(created.session_id, _frame(pcm, session_index=index, sequence=sequence))
        scheduler.drain()
        transcripts[session_id] = [commit.transcript for commit in runtime.snapshot(session_id).session.committed]
    return {
        "session_ids": session_ids,
        "transcripts": transcripts,
        "replacement_excludes_original_marker": all(
            "marker-original-session-" not in transcript for transcript in transcripts["replacement-session"]
        ),
        "original_excludes_replacement_marker": all(
            "marker-replacement-session-" not in transcript for transcript in transcripts["original-session"]
        ),
        "scope": "replacement runtime session only; no HTTP reconnect or resumable transport",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pace-seconds", type=float, default=0.5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.pace_seconds < 0:
        parser.error("--pace-seconds must be non-negative")
    pcm, audio_samples = _load_audio()
    cases = [_fairness_case(pcm, meetings, args.pace_seconds) for meetings in (1, 2, 4, 8)]
    result = {
        "schema": "moss-controlled-dispatcher-prototype.v1",
        "qualifies_g4_or_g5": False,
        "non_gating_reasons": [
            "controlled marker decoder, not the real MOSS decoder",
            "forced speech observations, not the production VAD",
            "manual scheduler release, not a locally started HTTP service",
            "no vLLM active/queued or GPU-cache metrics",
            "queue-isolation phase is accelerated rather than wall-clock paced",
        ],
        "preregistration_sha256": PREREGISTRATION_SHA256,
        "audio": {
            "path": str(AUDIO.relative_to(ROOT)),
            "sha256": AUDIO_SHA256,
            "sample_rate": LIVE_SAMPLE_RATE,
            "sample_count": audio_samples,
            "duration_seconds": audio_samples / LIVE_SAMPLE_RATE,
        },
        "fairness_cases": cases,
        "queue_isolation": _queue_isolation_case(pcm),
        "reconnect_marker_isolation": _reconnect_marker_case(pcm),
        "verdict": {
            "fairness_skew_within_frozen_gate": all(case["maximum_prefix_dispatch_skew"] <= 1 for case in cases),
            "all_markers_isolated": all(case["marker_isolation"] for case in cases),
            "queue_capacity_is_session_local": False,
            "correct_nonterminal_429_semantics_observed": False,
        },
    }
    result["verdict"]["queue_capacity_is_session_local"] = (
        result["queue_isolation"]["saturated_pending_work_items"] == QUEUE_BOUND
        and result["queue_isolation"]["peer_frame_accepted"]
        and not result["queue_isolation"]["peer_session_terminal"]
    )
    result["verdict"]["all_markers_isolated"] = (
        result["verdict"]["all_markers_isolated"]
        and result["reconnect_marker_isolation"]["replacement_excludes_original_marker"]
        and result["reconnect_marker_isolation"]["original_excludes_replacement_marker"]
    )
    rendered = json.dumps(result, indent=2, sort_keys=True, default=str) + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
