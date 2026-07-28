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

import asyncio
import hashlib

import pytest

from moss_transcribe_diarize.app.live_adapters import (
    InferenceTranscript,
    LiveProviderError,
    RunnerBoundedWavInference,
)
from moss_transcribe_diarize.app.live_arbiter import InferenceArbiter
from moss_transcribe_diarize.app.live_coordinator import LiveCoordinator
from moss_transcribe_diarize.app.live_endpoint import (
    EndpointPolicy,
    EndpointPolicyConfig,
    SpeechObservation,
)
from moss_transcribe_diarize.app.live_identity import BoundedCausalIdentityPreparer, LiveIdentityConfig
from moss_transcribe_diarize.app.live_provider_bundle import (
    LiveProviderBundleAdmissionError,
    WebRtcSpeechProvider,
)
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceRuntime,
    _ManualCanonicalPumpScheduler,
)
from moss_transcribe_diarize.app.live_session import (
    LIVE_SAMPLE_RATE,
    AudioFrame,
    FrozenSpan,
    LiveSession,
)
from moss_transcribe_diarize.app.vllm_runner import VllmRunner

DEPLOYED_VAD_FRAME_SAMPLES = 160
DEPLOYED_MIXED_FRAME_SAMPLES = 8000

# The deployed endpoint configuration, from the same manifest as the values above.
DEPLOYED_MIN_SPEECH_SAMPLES = 1600
DEPLOYED_MIN_SILENCE_SAMPLES = 8000
DEPLOYED_PADDING_SAMPLES = 1600
DEPLOYED_HARD_CAP_SAMPLES = 40000
DEPLOYED_DECODER_MAX_SAMPLES = 120000


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


def _coordinator(provider: WebRtcSpeechProvider, *, hard_cap_samples: int | None = None) -> LiveCoordinator:
    return LiveCoordinator(
        session_key="seam",
        session=LiveSession(max_retained_samples=960000),
        endpoint_policy=EndpointPolicy(
            EndpointPolicyConfig(
                min_speech_samples=DEPLOYED_MIN_SPEECH_SAMPLES,
                min_silence_samples=DEPLOYED_MIN_SILENCE_SAMPLES,
                pre_speech_padding_samples=DEPLOYED_PADDING_SAMPLES,
                post_speech_padding_samples=DEPLOYED_PADDING_SAMPLES,
                hard_cap_samples=hard_cap_samples,
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


# --------------------------------------------------------------------------------------
# The span-cap seam: one real session and one real endpoint policy, same hard cap.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("voiced", [True, False], ids=["continuous_speech", "opening_silence"])
def test_the_deployed_hard_cap_closes_one_span_and_the_meeting_continues(voiced):
    """The H2 blocker: the shape no harness in the repo had ever assembled.

    Every other harness gives the endpoint policy a hard cap and the session none, so the
    two never coexisted outside production -- where the manifest finalizer *requires* them
    to be equal. With both set, `LiveSession.accept_frame` froze its own `hard_cap` span at
    40000 before the policy ever ran, and the policy's identical span was then refused with
    `ValueError: frozen span end must advance.` at 2.5 s: any 2.5 s of continuous speech,
    or of opening silence, ended the meeting.

    Both directions are exercised because F0 measured both dying at the same sample.
    """
    vad = LengthContractVad(voiced=voiced)
    coordinator = _coordinator(
        WebRtcSpeechProvider(vad=vad, frame_samples=DEPLOYED_VAD_FRAME_SAMPLES),
        hard_cap_samples=DEPLOYED_HARD_CAP_SAMPLES,
    )

    frozen: list[tuple[int, int, str]] = []
    queued: list[int] = []
    frames = 2 * DEPLOYED_HARD_CAP_SAMPLES // DEPLOYED_MIXED_FRAME_SAMPLES
    for sequence in range(frames):
        result = coordinator.accept_frame(_frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
        frozen.extend((span.start_sample, span.end_sample, span.reason) for span in result.frozen_spans)
        queued.extend(result.queued_item_ids)
        # The lockstep invariant that makes one authority true: the only boundary the
        # session knows is the one the policy just emitted.
        assert (
            coordinator.session.snapshot().frozen_until_sample
            == coordinator.endpoint_policy.snapshot().open_start_sample
        )

    assert frozen == [
        (0, DEPLOYED_HARD_CAP_SAMPLES, "hard_cap"),
        (DEPLOYED_HARD_CAP_SAMPLES, 2 * DEPLOYED_HARD_CAP_SAMPLES, "hard_cap"),
    ]
    # Every frozen span is queued for decode. A span the session froze by itself was not,
    # so that audio would never have been transcribed even without the collision.
    assert len(queued) == len(frozen)
    assert coordinator.session.snapshot().pending_span_ids == (0, 1)
    assert set(vad.calls) == {DEPLOYED_VAD_FRAME_SAMPLES}


def test_a_provider_config_that_declares_two_different_span_caps_is_refused():
    """`bounds_config.hard_cap_samples` is a declaration, not a second mechanism.

    C2's finalizer enforces the equality when it writes a manifest; the runtime enforces it
    when it opens a session, so a manifest that arrived by any other route cannot run with
    an uncapped policy while claiming a cap.
    """
    runtime, _ = _decode_seam_runtime(responses=[NO_SPEECH_RESPONSES["zero parsed segments"]], speech=(False,))
    runtime._endpoint_policy_factory = lambda: EndpointPolicy(
        EndpointPolicyConfig(
            min_speech_samples=DEPLOYED_MIN_SPEECH_SAMPLES,
            min_silence_samples=DEPLOYED_MIN_SILENCE_SAMPLES,
            hard_cap_samples=None,
        )
    )

    with pytest.raises(ValueError, match="two different span caps"):
        runtime.create()


# --------------------------------------------------------------------------------------
# The decoder seam: the real vLLM response validation under the real live coordinator.
# --------------------------------------------------------------------------------------


class StubbedTransportVllmRunner(VllmRunner):
    """The product runner with only its HTTP hop replaced by a canned answer.

    Everything the live path actually runs stays real: the wav the coordinator wrote is
    read back through `_media_to_wav_bytes`, the response is unpacked by the product's own
    code, and `_validate_transcription_response` -- the seam F0 caught -- decides. Only the
    GPU on the other side of the socket is a stand-in.
    """

    def __init__(self, responses):
        super().__init__(base_url="http://vllm.seam.test:8000", model="moss-seam")
        self.responses = list(responses)
        self.decoded_wav_bytes: list[int] = []

    def _post_multipart(self, url, *, file_bytes, **kwargs):
        del url, kwargs
        self.decoded_wav_bytes.append(len(file_bytes))
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


# The three answers that mean "the model produced nothing for this audio". The third is the
# one the deployed service returned for the first span of every F0 probe run.
NO_SPEECH_RESPONSES = {
    "zero generated tokens": {"text": "[0][S01]hello[1]", "usage": {"prompt_tokens": 3, "completion_tokens": 0}},
    "empty transcript text": {"text": "   ", "usage": {"prompt_tokens": 3, "completion_tokens": 4}},
    "zero parsed segments": {"text": "silence", "usage": {"prompt_tokens": 3, "completion_tokens": 4}},
}


class ScriptedSpeech:
    """One observation per accepted range, from a per-frame speech/silence script."""

    def __init__(self, speech: tuple[bool, ...]):
        self.speech = list(speech)

    def observe(self, *, frame: AudioFrame, start_sample: int, end_sample: int):
        del frame
        return (
            SpeechObservation(
                start_sample=start_sample,
                end_sample=end_sample,
                speech_present=self.speech.pop(0) if self.speech else False,
            ),
        )


def _deployed_descriptor() -> LiveServiceDescriptor:
    return LiveServiceDescriptor(
        source_revision="0" * 40,
        provider_name="seam-vllm",
        provider_revision="seam-revision",
        provider_manifest_hash=hashlib.sha256(b"seam").hexdigest(),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={"hard_cap_samples": DEPLOYED_HARD_CAP_SAMPLES},
            identity_config={"max_speakers": 16},
            decoder_config={"max_samples": DEPLOYED_DECODER_MAX_SAMPLES},
        ),
        bounds=LiveServiceBounds(
            max_frame_samples=LIVE_SAMPLE_RATE,
            max_queue_depth=16,
            max_retained_samples=960000,
            max_identity_speakers=16,
            max_events=1000,
            # The deployed manifest declares the same cap in both sections, which the
            # runtime now requires: there is one span cap and the endpoint policy owns it.
            hard_cap_samples=DEPLOYED_HARD_CAP_SAMPLES,
            stop_drain_deadline_seconds=5.0,
        ),
        frame_samples=DEPLOYED_MIXED_FRAME_SAMPLES,
    )


def _decode_seam_runtime(*, responses, speech, scheduler=None) -> tuple[LiveServiceRuntime, StubbedTransportVllmRunner]:
    runner = StubbedTransportVllmRunner(responses)
    return (
        LiveServiceRuntime(
            descriptor=_deployed_descriptor(),
            endpoint_policy_factory=lambda: EndpointPolicy(
                EndpointPolicyConfig(
                    min_speech_samples=DEPLOYED_MIN_SPEECH_SAMPLES,
                    min_silence_samples=DEPLOYED_MIN_SILENCE_SAMPLES,
                    pre_speech_padding_samples=DEPLOYED_PADDING_SAMPLES,
                    post_speech_padding_samples=DEPLOYED_PADDING_SAMPLES,
                    hard_cap_samples=DEPLOYED_HARD_CAP_SAMPLES,
                )
            ),
            speech_provider_factory=lambda: ScriptedSpeech(speech),
            decoder_factory=lambda: RunnerBoundedWavInference(runner, max_samples=DEPLOYED_DECODER_MAX_SAMPLES),
            identity_preparer_factory=lambda: BoundedCausalIdentityPreparer(
                config=LiveIdentityConfig(max_speakers=16, min_match_score=0.5, min_match_margin=0.1)
            ),
            session_id_factory=lambda: "seam-session",
            _canonical_scheduler=scheduler,
        ),
        runner,
    )


def _events(runtime: LiveServiceRuntime, session_id: str, kind: str) -> list[dict]:
    return [dict(event.payload) for event in runtime.events(session_id) if event.kind == kind]


def test_a_leading_silence_span_commits_empty_instead_of_ending_the_meeting():
    """The F0 blocker, reproduced through the seam that produced it.

    Every meeting opens with silence, and the endpoint policy turns that opening into its
    own span: when speech is confirmed it emits `leading_silence` over everything before
    the padded speech start. That span holds no speech by construction, so the decoder
    returns nothing parseable for it -- on the deployed host, span-0000, `frozen_until_sample
    14400` against a first utterance at 16000, exactly `16000 - pre_speech_padding_samples`.
    Before this fix the bare `RuntimeError` from `_validate_transcription_response` made the
    session terminal (`kind=integrity, retryable=false`) about three seconds into the run.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    speech_transcript = "[0.00][S01]hello there[1.10]"
    runtime, runner = _decode_seam_runtime(
        responses=[
            NO_SPEECH_RESPONSES["zero parsed segments"],
            {"text": speech_transcript, "usage": {"prompt_tokens": 3, "completion_tokens": 9}},
        ],
        speech=(False, False, True, True, False),
        scheduler=scheduler,
    )
    created = runtime.create()

    for sequence in range(5):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    scheduler.drain()

    snapshot = runtime.snapshot(created.session_id)
    assert snapshot.terminal_failure is None
    spans = [(event["start_sample"], event["end_sample"], event["reason"]) for event in _events(runtime, created.session_id, "span_frozen")]
    assert spans == [(0, 14400, "leading_silence"), (14400, 33600, "end_silence")]

    committed = [(item.start_sample, item.end_sample, item.transcript) for item in snapshot.session.committed]
    assert committed[0] == (0, 14400, "")
    assert committed[1][:2] == (14400, 33600)
    assert "hello there" in committed[1][2]
    # No audio is lost to the empty span: the committed prefix runs through both.
    assert snapshot.session.committed_samples == 33600
    assert snapshot.session.accounted_samples == 33600

    processed = _events(runtime, created.session_id, "canonical_processed")
    assert [event["empty_reason"] for event in processed] == ["decoder_returned_no_transcript", None]
    assert [event["submitted"] for event in processed] == [True, True]
    assert [event["identity_status"] for event in processed] == ["empty_span", "prepared"]
    # The empty span cost real decode time and it is still measured, not reported as unknown.
    assert processed[0]["canonical_decode_rtf"] is not None

    # The session is still live: the meeting continues after the span that used to end it.
    runtime.accept_frame(created.session_id, _frame(5, DEPLOYED_MIXED_FRAME_SAMPLES))
    assert runtime.snapshot(created.session_id).terminal_failure is None
    assert len(runner.decoded_wav_bytes) == 2


def test_a_meeting_of_pure_silence_stops_with_exact_accounting():
    """Why the policy is *commit empty* rather than *drop the span*.

    `LiveSession.stop` waits for `committed_samples == accepted_samples` and the runtime
    fails a stop whose accepted and accounted totals differ, so a dropped span strands the
    session exactly as surely as a terminal failure does -- it just does it at the end of the
    meeting instead of the beginning. Committing the span empty is what keeps the PRD's
    zero-loss accounting true when nobody said anything.
    """
    runtime, runner = _decode_seam_runtime(
        responses=[NO_SPEECH_RESPONSES["zero parsed segments"]],
        speech=(False, False, False),
    )
    created = runtime.create()
    for sequence in range(3):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))

    snapshot = asyncio.run(runtime.stop(created.session_id, deadline=5.0))

    assert snapshot.terminal_failure is None
    assert snapshot.session.status == "closed"
    assert snapshot.session.accepted_samples == snapshot.session.accounted_samples == 24000
    assert snapshot.session.pending_span_ids == ()
    assert snapshot.pending_work_items == 0
    # One stop_flush span over the whole silent meeting, committed with nothing in it.
    assert [item.transcript for item in snapshot.session.committed] == [""]
    assert len(runner.decoded_wav_bytes) == 1


def test_every_no_speech_answer_from_the_real_runner_reaches_the_coordinator_as_no_transcript():
    """All three of `_validate_transcription_response`'s conditions mean the same thing."""
    for label, response in NO_SPEECH_RESPONSES.items():
        runner = StubbedTransportVllmRunner([response])
        decoder = RunnerBoundedWavInference(runner, max_samples=DEPLOYED_DECODER_MAX_SAMPLES)
        span = _span(0, DEPLOYED_MIXED_FRAME_SAMPLES)

        inferred = decoder.transcribe_pcm(span=span, pcm=b"\x00\x00" * DEPLOYED_MIXED_FRAME_SAMPLES)

        assert inferred.transcript == "", label
        assert inferred.generated_tokens == 0, label
        # The wall time is still reported, so an empty span cannot hide from the RTF gate.
        assert inferred.elapsed_sec is not None and inferred.elapsed_sec >= 0.0, label


def test_a_decoder_that_returns_unparseable_text_without_raising_is_also_an_empty_span():
    """The rule is stated on the transcript, so it does not depend on one runner's error type.

    `VllmRunner` raises for this; another runner may simply return the text. Both are spans
    with nothing publishable, and both must be committed empty rather than end the meeting.
    """

    class TalkativeButUnparseableDecoder:
        max_samples = DEPLOYED_DECODER_MAX_SAMPLES

        def transcribe_pcm(self, *, span, pcm):
            del span, pcm
            return InferenceTranscript(transcript="I could not hear anything.", generated_tokens=6)

    coordinator = LiveCoordinator(
        session_key="seam",
        session=LiveSession(max_retained_samples=960000),
        endpoint_policy=EndpointPolicy(
            EndpointPolicyConfig(min_speech_samples=1600, min_silence_samples=8000, hard_cap_samples=None)
        ),
        speech_provider=ScriptedSpeech((False,)),
        decoder=TalkativeButUnparseableDecoder(),
        identity_preparer=UnusedIdentityPreparer(),
        arbiter=InferenceArbiter(),
    )
    coordinator.accept_frame(_frame(0, DEPLOYED_MIXED_FRAME_SAMPLES))
    item_ids = coordinator.flush_endpoint()
    assert len(item_ids) == 1

    work = coordinator.capture_work_item(coordinator.arbiter.next_work())
    prepared = coordinator.prepare_work_item(work)
    result = coordinator.submit_prepared_work(prepared)

    assert prepared.empty_reason == "decoder_returned_unparseable_transcript"
    assert prepared.preparation is None
    assert result.submitted is True
    assert result.committed_samples == DEPLOYED_MIXED_FRAME_SAMPLES


def test_a_decoder_that_failed_is_not_a_span_with_nothing_to_say():
    """The classification seam, stated as the distinction that matters.

    Nothing leaves the decode seam unclassified -- that is what made the bare `RuntimeError`
    fatal -- but a decoder that *failed* must not be silently committed as silence either,
    or a dead GPU would render as a blank meeting. It is named, and it stays terminal.
    """

    class FailingRunner:
        def transcribe(self, *args, **kwargs):
            raise ConnectionResetError("vLLM socket closed")

    decoder = RunnerBoundedWavInference(FailingRunner(), max_samples=DEPLOYED_DECODER_MAX_SAMPLES)

    with pytest.raises(LiveProviderError) as caught:
        decoder.transcribe_pcm(span=_span(0, 8000), pcm=b"\x00\x00" * 8000)

    assert "ConnectionResetError" in str(caught.value)
    assert isinstance(caught.value.__cause__, ConnectionResetError)


def _span(span_id: int, sample_count: int) -> FrozenSpan:
    return FrozenSpan(id=span_id, epoch=0, start_sample=0, end_sample=sample_count, reason="hard_cap")
