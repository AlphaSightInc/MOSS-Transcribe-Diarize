"""Synthetic runtime inputs shared by API and optional browser reachability checks."""
from __future__ import annotations
import base64
import tempfile

from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_endpoint import (
    EndpointPolicy,
    EndpointPolicyConfig,
    SpeechObservation,
)
from moss_transcribe_diarize.app.live_helper_presence import HELPER_HEALTH_SCHEMA
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceRuntime,
    hash_config,
)
from moss_transcribe_diarize.app.live_session import (
    LIVE_SAMPLE_RATE,
    AudioFrame,
    FrozenSpan,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
)
class _SpeechProvider:
    def __init__(self):
        self._speech = [True, False]

    def observe(
        self,
        *,
        frame: AudioFrame,
        start_sample: int,
        end_sample: int,
    ) -> tuple[SpeechObservation, ...]:
        del frame
        return (
            SpeechObservation(
                start_sample=start_sample,
                end_sample=end_sample,
                speech_present=self._speech.pop(0) if self._speech else False,
            ),
        )


class _Decoder:
    max_samples = 4_000

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        del pcm
        return InferenceTranscript(
            f"[0][S01]Observed live words[{span.sample_count / LIVE_SAMPLE_RATE:g}]"
        )


class _Identity:
    def fork_lane(self):
        return _Identity()

    def prepare(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        transcript: str,
        base_snapshot: LiveIdentitySnapshot,
        allowed_speakers: tuple[str, ...] | None = None,
    ) -> LiveIdentityPreparation:
        del pcm, transcript
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
            relabeled_transcript=(
                f"[0][S01]Observed live words[{span.sample_count / LIVE_SAMPLE_RATE:g}]"
            ),
        )


def _runtime() -> LiveServiceRuntime:
    descriptor = LiveServiceDescriptor(
        source_revision="a" * 40,
        provider_name="phase2-history-browser-test",
        provider_revision="test",
        provider_manifest_hash=hash_config({"provider": "phase2-history-browser-test"}),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={"min_speech_samples": 1, "min_silence_samples": 1},
            identity_config={"max_speakers": 2},
            decoder_config={"max_samples": 4_000},
        ),
        bounds=LiveServiceBounds(
            max_frame_samples=4_000,
            max_queue_depth=4,
            max_retained_samples=16_000,
            max_identity_speakers=2,
            max_events=128,
            hard_cap_samples=4_000,
            max_tape_bytes=32_000,
        ),
        frame_samples=2,
    )
    storage_owner = tempfile.TemporaryDirectory()
    runtime = LiveServiceRuntime(
        descriptor=descriptor,
        endpoint_policy_factory=lambda: EndpointPolicy(
            EndpointPolicyConfig(
                min_speech_samples=1,
                min_silence_samples=1,
                hard_cap_samples=4_000,
            )
        ),
        speech_provider_factory=_SpeechProvider,
        decoder_factory=_Decoder,
        rolling_decoder_factory=None,
        identity_preparer_factory=_Identity,
        tape_storage_root=storage_owner.name,
    )
    runtime._test_tape_storage_owner = storage_owner
    return runtime


def _v2_frame(sequence: int, lane: str) -> dict[str, object]:
    samples = 2
    return {
        "lane": lane,
        "sequence": sequence,
        "capture_timestamp_ns": sequence * samples * 1_000_000_000 // LIVE_SAMPLE_RATE,
        "device_epoch": 0,
        # One real decoder input; the other lane is deliberately digital silence.
        "pcm_base64": base64.b64encode((b"\x01\x00" if lane == "system" else b"\0\0") * samples).decode("ascii"),
        "sample_count": samples,
        "sample_rate": LIVE_SAMPLE_RATE,
        "silent": False,
        "discontinuity": False,
    }


def _heartbeat() -> dict[str, object]:
    lane = {
        "state": "capturing",
        "device_epoch": 0,
        "dropped_frames": 0,
        "discontinuities": 0,
        "failure_code": None,
    }
    return {
        "schema": HELPER_HEALTH_SCHEMA,
        "instance_id": "browser-history-test",
        "sequence": 0,
        "sent_monotonic_ns": 1,
        "helper_version": "test",
        "state": "capturing",
        "lanes": {"system": dict(lane), "microphone": dict(lane)},
    }

