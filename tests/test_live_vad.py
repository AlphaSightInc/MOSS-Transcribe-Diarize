from __future__ import annotations

import hashlib
import wave
from pathlib import Path

import pytest

from moss_transcribe_diarize.app.live_adapters import (
    FakeBoundedWavInference,
    FakeStableIdentity,
    FakeVad,
    LiveProviderAdmissionError,
    LiveProviderConfig,
    LiveProviderError,
    OfflineAsset,
    RunnerBoundedWavInference,
    admit_live_provider,
)
from moss_transcribe_diarize.app.live_session import AudioFrame, FrozenSpan, LIVE_SAMPLE_RATE, LiveSession, LiveSessionFailed
from moss_transcribe_diarize.app.model_runner import TranscriptionResult


def pcm(samples: int) -> bytes:
    return b"\0" * samples * 2


def frame(sequence: int, samples: int) -> AudioFrame:
    return AudioFrame(sequence=sequence, pcm=pcm(samples), sample_count=samples)


def config_with_asset(asset_path: Path) -> LiveProviderConfig:
    return LiveProviderConfig(
        name="offline-test",
        assets=(
            OfflineAsset(
                name="vad-manifest",
                path=asset_path,
                sha256=hashlib.sha256(asset_path.read_bytes()).hexdigest(),
            ),
        ),
    )


def provider(asset_path: Path, *, transcript: str = "[0][S01]ok[0.25]", identity_confirmed: bool = True):
    return admit_live_provider(
        config_with_asset(asset_path),
        vad=FakeVad(freeze_after_samples=4000),
        identity=FakeStableIdentity(confirmed=identity_confirmed, reason="ambiguous identity"),
        inference=FakeBoundedWavInference(transcript=transcript, max_samples=4000),
    )


def test_provider_admission_requires_preinstalled_checksum_asset(tmp_path):
    asset = tmp_path / "vad.asset"
    asset.write_bytes(b"offline asset")

    admitted = provider(asset)

    assert admitted.config.name == "offline-test"
    bad_config = LiveProviderConfig(
        name="bad",
        assets=(OfflineAsset(name="vad-manifest", path=asset, sha256="0" * 64),),
    )
    with pytest.raises(LiveProviderAdmissionError, match="checksum mismatch"):
        admit_live_provider(
            bad_config,
            vad=FakeVad(),
            identity=FakeStableIdentity(),
            inference=FakeBoundedWavInference(transcript="[0][S01]ok[0.1]"),
        )
    with pytest.raises(LiveProviderAdmissionError, match="not preinstalled"):
        admit_live_provider(
            LiveProviderConfig(
                name="missing",
                assets=(OfflineAsset(name="vad-manifest", path=tmp_path / "missing.asset", sha256="0" * 64),),
            ),
            vad=FakeVad(),
            identity=FakeStableIdentity(),
            inference=FakeBoundedWavInference(transcript="[0][S01]ok[0.1]"),
        )


def test_vad_decision_freezes_exact_span_without_committing(tmp_path):
    asset = tmp_path / "vad.asset"
    asset.write_bytes(b"offline asset")
    live = provider(asset)
    session = LiveSession(max_retained_samples=4000)

    ack = session.accept_frame(frame(0, 4000))
    decision = live.observe_vad(start_sample=ack.start_sample, end_sample=ack.end_sample, pcm=pcm(4000))
    span = session.freeze_until(decision.end_sample, reason=decision.reason)

    snapshot = session.snapshot()
    assert (span.start_sample, span.end_sample, span.reason) == (0, 4000, "end_silence")
    assert snapshot.pending_span_ids == (span.id,)
    assert snapshot.accounted_samples == 0


def test_ambiguous_identity_fails_closed_and_preserves_unresolved_span(tmp_path):
    asset = tmp_path / "vad.asset"
    asset.write_bytes(b"offline asset")
    live = provider(asset, identity_confirmed=False)
    session = LiveSession(max_retained_samples=4000)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="end_silence")

    result = live.decode_canonical(span, pcm(4000))
    with pytest.raises(LiveSessionFailed, match="stable session identity"):
        session.submit_canonical(result)

    snapshot = session.snapshot()
    assert snapshot.status == "failed"
    assert snapshot.accepted_samples == 4000
    assert snapshot.accounted_samples == 0
    assert snapshot.pending_span_ids == (span.id,)


def test_inference_rejects_invalid_and_oversized_spans_before_state_mutation(tmp_path):
    asset = tmp_path / "vad.asset"
    asset.write_bytes(b"offline asset")
    session = LiveSession(max_retained_samples=5000)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="end_silence")

    invalid = provider(asset, transcript="plain text")
    with pytest.raises(LiveProviderError, match="zero parsed segments"):
        invalid.decode_canonical(span, pcm(4000))
    assert session.snapshot().accounted_samples == 0

    bounded = admit_live_provider(
        config_with_asset(asset),
        vad=FakeVad(),
        identity=FakeStableIdentity(),
        inference=FakeBoundedWavInference(transcript="[0][S01]ok[0.25]", max_samples=3999),
    )
    with pytest.raises(LiveProviderError, match="bounded inference capacity"):
        bounded.decode_canonical(span, pcm(4000))
    assert session.snapshot().pending_span_ids == (span.id,)


def test_runner_bounded_wav_inference_writes_complete_16khz_pcm_wav(tmp_path):
    class InspectingRunner:
        def __init__(self):
            self.params = None

        def transcribe(self, audio_path, **kwargs):
            del kwargs
            with wave.open(str(audio_path), "rb") as wav:
                self.params = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes())
            return TranscriptionResult(
                text="[0][S01]ok[0.25]",
                prompt_len=1,
                generated_tokens=2,
                elapsed_sec=0.01,
                model="fake",
                audio=str(audio_path),
                decoding="greedy",
                temperature=None,
            )

    runner = InspectingRunner()
    adapter = RunnerBoundedWavInference(runner, max_samples=4000, scratch_dir=tmp_path)
    frozen = FrozenSpan(id=7, epoch=0, start_sample=0, end_sample=4000, reason="end_silence")

    result = adapter.transcribe_pcm(span=frozen, pcm=pcm(4000))

    assert result.transcript == "[0][S01]ok[0.25]"
    assert runner.params == (1, 2, LIVE_SAMPLE_RATE, 4000)
