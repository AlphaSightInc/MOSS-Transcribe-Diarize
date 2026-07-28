"""Seams where the live pipeline's real components meet, driven together.

Every blocker the F0 host probe found lives in a seam the suite has never assembled: a
real speech provider under the real coordinator, or the real decoder validation under the
real adapter. Each node here therefore uses the *product* class on both sides of the seam
and stubs only what is genuinely off-host (the native `webrtcvad` wheel, the GPU runner).

Provenance of the configuration values: the live provider manifest deployed on
ga0-alienware-rtx4070ti on 2026-07-28 -- `speech_provider {kind: webrtc, frame_samples:
160, mode: 1}`, `bounds_config.frame_samples 8000`, `hard_cap_samples 40000` in both
sections, `min_silence_samples 8000`.
"""

from __future__ import annotations

import pytest

from moss_transcribe_diarize.app.live_arbiter import InferenceArbiter
from moss_transcribe_diarize.app.live_coordinator import LiveCoordinator
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig
from moss_transcribe_diarize.app.live_provider_bundle import (
    LiveProviderBundleAdmissionError,
    WebRtcSpeechProvider,
)
from moss_transcribe_diarize.app.live_session import LIVE_SAMPLE_RATE, AudioFrame, LiveSession

DEPLOYED_VAD_FRAME_SAMPLES = 160
DEPLOYED_MIXED_FRAME_SAMPLES = 8000


class LengthContractVad:
    """A stand-in for `webrtcvad.Vad` that enforces only its documented length contract.

    WebRTC's VAD accepts exactly 10, 20 or 30 ms of 16-bit mono PCM and raises
    `webrtcvad.Error: Error while processing frame` for anything else. That single rule is
    the whole of the blocker this file guards, and enforcing it here keeps the node
    runnable on hosts with no native `webrtcvad` wheel -- which is part of why the defect
    reached production in the first place.
    """

    def __init__(self, *, voiced: bool = False, sample_rate: int = LIVE_SAMPLE_RATE):
        self.valid_lengths = {sample_rate * ms // 1000 for ms in (10, 20, 30)}
        self.voiced = voiced
        self.calls: list[int] = []

    def __call__(self, pcm: bytes, sample_rate: int) -> bool:
        del sample_rate
        samples = len(pcm) // 2
        self.calls.append(samples)
        if samples not in self.valid_lengths:
            raise RuntimeError(
                "Error while processing frame (webrtcvad accepts only "
                f"{sorted(self.valid_lengths)} samples, got {samples})"
            )
        return self.voiced


class UnusedDecoder:
    def transcribe(self, *args, **kwargs):  # pragma: no cover - no node decodes
        raise AssertionError("this seam fails, or passes, before any decode")


class UnusedIdentityPreparer:
    def prepare(self, *args, **kwargs):  # pragma: no cover - no node prepares identity
        raise AssertionError("this seam fails, or passes, before any identity work")


def _coordinator(provider: WebRtcSpeechProvider) -> LiveCoordinator:
    return LiveCoordinator(
        session_key="seam",
        session=LiveSession(max_retained_samples=960000, hard_cap_samples=None),
        endpoint_policy=EndpointPolicy(
            EndpointPolicyConfig(
                min_speech_samples=1600,
                min_silence_samples=8000,
                pre_speech_padding_samples=1600,
                post_speech_padding_samples=1600,
                hard_cap_samples=None,
            )
        ),
        speech_provider=provider,
        decoder=UnusedDecoder(),
        identity_preparer=UnusedIdentityPreparer(),
        arbiter=InferenceArbiter(),
    )


def _frame(sequence: int, sample_count: int) -> AudioFrame:
    return AudioFrame(
        sequence=sequence,
        pcm=b"\x11\x22" * sample_count,
        sample_count=sample_count,
        sample_rate=LIVE_SAMPLE_RATE,
    )


def test_unaligned_mixed_frames_never_hand_webrtcvad_an_illegal_frame_length():
    """The lanes are not aligned, so the mixer's sample counts are arbitrary integers.

    `LiveMixer._stage` computes `floor((safe_end_ns - cursor_ns) * 16000 / 1e9)`; two real
    capture devices never start on the same instant, so that count is a multiple of the
    VAD frame only by accident. 5808 is the count measured on the deployed host with the
    lanes 137 ms apart, and 5808 = 36 * 160 + 48 -- the 48-sample remainder is what raised
    `webrtcvad.Error` and made the session terminal after 1.1 s.
    """
    vad = LengthContractVad()
    coordinator = _coordinator(WebRtcSpeechProvider(vad=vad, frame_samples=DEPLOYED_VAD_FRAME_SAMPLES))

    counts = (5808, 8000, 4137, 159, 1, 7999)
    accepted = 0
    for sequence, sample_count in enumerate(counts):
        result = coordinator.accept_frame(_frame(sequence, sample_count))
        assert result.accepted_start_sample == accepted
        accepted += sample_count
        assert result.accepted_end_sample == accepted

    assert set(vad.calls) == {DEPLOYED_VAD_FRAME_SAMPLES}
    # No real audio is skipped: every whole VAD frame the stream contains was decided.
    assert len(vad.calls) == accepted // DEPLOYED_VAD_FRAME_SAMPLES


def test_the_carried_tail_is_decided_for_real_once_its_vad_frame_completes():
    """A tail that cannot fill a VAD frame is carried, not padded and not dropped."""
    vad = LengthContractVad(voiced=True)
    provider = WebRtcSpeechProvider(vad=vad, frame_samples=DEPLOYED_VAD_FRAME_SAMPLES)

    first = provider.observe(frame=_frame(0, 200), start_sample=0, end_sample=200)
    assert [(item.start_sample, item.end_sample, item.speech_present) for item in first] == [
        (0, 160, True),
        (160, 200, True),
    ]
    # The carried 40 samples say what was last decided and admit they are not a decision.
    assert first[-1].confidence is None
    assert first[-1].provider_reason == "webrtc_observation_carried"
    assert vad.calls == [160]

    second = provider.observe(frame=_frame(1, 200), start_sample=200, end_sample=400)
    assert [(item.start_sample, item.end_sample, item.speech_present) for item in second] == [
        (200, 320, True),
        (320, 400, True),
    ]
    # 120 samples completed the frame the previous call left open; the 80-sample tail of
    # this call is the new carry.
    assert vad.calls == [160, 160]
    assert second[0].confidence == 1.0
    assert second[-1].confidence is None


def test_a_sub_vad_frame_accepted_range_carries_instead_of_calling_the_vad():
    """The mixer may stage a single sample; that must not reach webrtcvad."""
    vad = LengthContractVad()
    provider = WebRtcSpeechProvider(vad=vad, frame_samples=DEPLOYED_VAD_FRAME_SAMPLES)

    observations = provider.observe(frame=_frame(0, 1), start_sample=0, end_sample=1)

    assert vad.calls == []
    assert [(item.start_sample, item.end_sample) for item in observations] == [(0, 1)]
    assert observations[0].speech_present is False


def test_aligned_frames_still_produce_one_observation_per_vad_frame():
    """The shipped 8000-sample mixed frame is 50 whole VAD frames and must not change."""
    vad = LengthContractVad()
    provider = WebRtcSpeechProvider(vad=vad, frame_samples=DEPLOYED_VAD_FRAME_SAMPLES)

    observations = provider.observe(
        frame=_frame(0, DEPLOYED_MIXED_FRAME_SAMPLES),
        start_sample=0,
        end_sample=DEPLOYED_MIXED_FRAME_SAMPLES,
    )

    assert len(observations) == DEPLOYED_MIXED_FRAME_SAMPLES // DEPLOYED_VAD_FRAME_SAMPLES
    assert vad.calls == [DEPLOYED_VAD_FRAME_SAMPLES] * len(observations)
    assert all(item.provider_reason == "webrtc_observation" for item in observations)
    assert all(item.confidence == 0.0 for item in observations)


def test_a_manifest_frame_length_webrtcvad_cannot_accept_is_refused_at_admission():
    """A manifest that configures an illegal frame length would raise on every frame."""
    with pytest.raises(LiveProviderBundleAdmissionError, match="frame_samples must be one of"):
        WebRtcSpeechProvider(vad=LengthContractVad(), frame_samples=200)

    for legal in (160, 320, 480):
        WebRtcSpeechProvider(vad=LengthContractVad(), frame_samples=legal)
