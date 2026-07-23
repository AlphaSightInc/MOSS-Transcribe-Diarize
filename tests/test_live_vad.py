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
    silero_vad_manifest,
    webrtc_vad_manifest,
    wespeaker_identity_manifest,
)
from moss_transcribe_diarize.app.live_arbiter import InferenceArbiter, InferenceArbiterBackpressure
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


def asset_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def test_optional_live_provider_manifests_are_explicit_offline_and_pinned(tmp_path):
    silero = tmp_path / "silero.onnx"
    webrtc = tmp_path / "webrtc.wheel"
    wespeaker = tmp_path / "wespeaker.pt"
    silero.write_bytes(b"silero")
    webrtc.write_bytes(b"webrtc")
    wespeaker.write_bytes(b"wespeaker")
    config = LiveProviderConfig(
        name="offline-trials",
        assets=(),
        offline_providers=(
            silero_vad_manifest(model_path=silero, sha256=asset_sha(silero), revision="6.2.1"),
            webrtc_vad_manifest(asset_path=webrtc, sha256=asset_sha(webrtc), revision="control-1"),
            wespeaker_identity_manifest(state_path=wespeaker, sha256=asset_sha(wespeaker), revision="resnet152-lm"),
        ),
    )

    admitted = admit_live_provider(
        config,
        vad=FakeVad(),
        identity=FakeStableIdentity(),
        inference=FakeBoundedWavInference(transcript="[0][S01]ok[0.1]"),
    )

    assert [manifest.kind for manifest in admitted.config.offline_providers] == [
        "silero_vad",
        "webrtc_vad",
        "wespeaker_identity",
    ]


def test_optional_live_provider_admission_fails_closed_without_asset_or_package(tmp_path):
    asset = tmp_path / "silero.onnx"
    asset.write_bytes(b"silero")
    base_kwargs = dict(
        vad=FakeVad(),
        identity=FakeStableIdentity(),
        inference=FakeBoundedWavInference(transcript="[0][S01]ok[0.1]"),
    )

    with pytest.raises(LiveProviderAdmissionError, match="checksum mismatch"):
        admit_live_provider(
            LiveProviderConfig(
                name="bad-silero",
                assets=(),
                offline_providers=(
                    silero_vad_manifest(model_path=asset, sha256="0" * 64, revision="6.2.1"),
                ),
            ),
            **base_kwargs,
        )
    with pytest.raises(LiveProviderAdmissionError, match="not preinstalled"):
        admit_live_provider(
            LiveProviderConfig(
                name="missing-wespeaker",
                assets=(),
                offline_providers=(
                    wespeaker_identity_manifest(
                        state_path=tmp_path / "missing.pt",
                        sha256="0" * 64,
                        revision="resnet152-lm",
                    ),
                ),
            ),
            **base_kwargs,
        )
    with pytest.raises(LiveProviderAdmissionError, match="package is not preinstalled"):
        admit_live_provider(
            LiveProviderConfig(
                name="missing-package",
                assets=(),
                offline_providers=(
                    webrtc_vad_manifest(
                        asset_path=asset,
                        sha256=asset_sha(asset),
                        revision="control-1",
                        package_name="moss-definitely-missing-live-provider",
                        package_version="1.0.0",
                    ),
                ),
            ),
            **base_kwargs,
        )
    with pytest.raises(LiveProviderAdmissionError, match="module is not importable"):
        admit_live_provider(
            LiveProviderConfig(
                name="missing-module",
                assets=(),
                offline_providers=(
                    webrtc_vad_manifest(
                        asset_path=asset,
                        sha256=asset_sha(asset),
                        revision="control-1",
                        import_name="moss_definitely_missing_live_provider",
                    ),
                ),
            ),
            **base_kwargs,
        )


def test_optional_provider_admission_rejects_duplicates_and_adapter_failures(tmp_path):
    asset = tmp_path / "silero.onnx"
    asset.write_bytes(b"silero")
    manifest = silero_vad_manifest(model_path=asset, sha256=asset_sha(asset), revision="6.2.1")

    with pytest.raises(LiveProviderAdmissionError, match="duplicate optional provider"):
        admit_live_provider(
            LiveProviderConfig(name="duplicate", assets=(), offline_providers=(manifest, manifest)),
            vad=FakeVad(),
            identity=FakeStableIdentity(),
            inference=FakeBoundedWavInference(transcript="[0][S01]ok[0.1]"),
        )
    with pytest.raises(LiveProviderAdmissionError, match="vad provider unavailable"):
        admit_live_provider(
            LiveProviderConfig(name="adapter-failure", assets=(), offline_providers=(manifest,)),
            vad=FakeVad(available=False),
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


def test_inference_arbiter_preserves_batch_canonical_provisional_priority():
    arbiter = InferenceArbiter()

    provisional = arbiter.submit_live_provisional(coalesce_key="session-a", payload="provisional")
    canonical = arbiter.submit_live_canonical(key="session-a:span-1", payload="canonical")
    batch = arbiter.submit_batch(key="job-a", payload="batch")

    assert provisional.accepted
    assert canonical.accepted
    assert batch.accepted
    assert [arbiter.next_work().payload, arbiter.next_work().payload, arbiter.next_work().payload] == [
        "batch",
        "canonical",
        "provisional",
    ]
    assert arbiter.next_work() is None


def test_inference_arbiter_coalesces_and_suppresses_provisional_before_canonical():
    arbiter = InferenceArbiter(max_live_canonical_items=1, max_live_provisional_items=1)

    first = arbiter.submit_live_provisional(coalesce_key="session-a", payload="old provisional")
    replacement = arbiter.submit_live_provisional(coalesce_key="session-a", payload="new provisional")
    saturated = arbiter.submit_live_provisional(coalesce_key="session-b", payload="suppressed provisional")
    canonical = arbiter.submit_live_canonical(key="session-a:span-1", payload="canonical")

    assert first.accepted
    assert replacement.accepted
    assert replacement.replaced_item_id == first.item_id
    assert not saturated.accepted
    assert saturated.reason == "live provisional queue suppressed"
    assert canonical.accepted
    assert arbiter.snapshot().live_canonical == 1
    assert arbiter.snapshot().live_provisional == 1
    assert arbiter.next_work().payload == "canonical"
    assert arbiter.next_work().payload == "new provisional"

    with pytest.raises(InferenceArbiterBackpressure, match="live canonical queue is full"):
        full = InferenceArbiter(max_live_canonical_items=0)
        full.submit_live_canonical(key="session-c:span-1", payload="canonical")
