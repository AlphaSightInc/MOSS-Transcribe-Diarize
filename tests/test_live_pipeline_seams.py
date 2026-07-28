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
import io
import json
import urllib.error
import urllib.request
from unittest import mock

import pytest

from moss_transcribe_diarize.app.live_adapters import (
    FakeBoundedWavInference,
    FakeStableIdentity,
    FakeVad,
    InferenceTranscript,
    LiveProviderConfig,
    LiveProviderError,
    LiveProviderTransientError,
    RunnerBoundedWavInference,
    admit_live_provider,
)
from moss_transcribe_diarize.app.live_arbiter import InferenceArbiter
from moss_transcribe_diarize.app.live_coordinator import (
    DECODE_ATTEMPTS_PER_SPAN,
    DECODER_DID_NOT_ANSWER,
    MAX_CONSECUTIVE_UNANSWERED_SPANS,
    LiveCoordinator,
)
from moss_transcribe_diarize.app.live_endpoint import (
    EndpointPolicy,
    EndpointPolicyConfig,
    SpeechObservation,
)
from moss_transcribe_diarize.app.live_identity import (
    BoundedCausalIdentityPreparer,
    LiveIdentityConfig,
    unattributed_transcript,
)
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
    UNATTRIBUTED_SPEAKER,
    AudioFrame,
    CanonicalResult,
    FrozenSpan,
    LiveIdentitySnapshot,
    LiveSession,
)
from moss_transcribe_diarize.app.live_span_bounds import span_segments
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


class CannedHttpResponse:
    """What `urlopen` hands back, with the model's answer already in it."""

    def __init__(self, payload: dict):
        self.headers = {"Content-Type": "application/json"}
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self) -> bytes:
        return self._body


class FailingTransport:
    """The socket refusing, the way the network and the backend actually refuse.

    A factory rather than one exception instance, so every attempt raises a fresh one: a
    retried span must not pass merely because an earlier attempt already read the error body.
    """

    def __init__(self, factory):
        self.factory = factory

    def __call__(self):
        raise self.factory()


class StubbedTransportVllmRunner(VllmRunner):
    """The product runner with only its *socket* replaced.

    Everything the live path actually runs stays real: the wav the coordinator wrote is
    read back through `_media_to_wav_bytes`, `_post_multipart` builds the request, unpacks
    the response and classifies transport failures, and `_validate_transcription_response`
    -- the seam F0 caught -- decides. Only what is on the other side of the socket is a
    stand-in. Replacing `_post_multipart` instead would put the stub exactly where the
    status code is turned into a typed outcome, i.e. it would test the stub.
    """

    def __init__(self, responses):
        super().__init__(base_url="http://vllm.seam.test:8000", model="moss-seam")
        self.responses = list(responses)
        self.decoded_wav_bytes: list[int] = []

    def _post_multipart(self, url, *, file_bytes, **kwargs):
        self.decoded_wav_bytes.append(len(file_bytes))
        answer = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]

        def urlopen(request, timeout=None):
            del request, timeout
            if callable(answer):
                return answer()
            return CannedHttpResponse(answer)

        with mock.patch.object(urllib.request, "urlopen", urlopen):
            return super()._post_multipart(url, file_bytes=file_bytes, **kwargs)


def _http_error(code: int, detail: bytes = b"backend is busy") -> FailingTransport:
    return FailingTransport(
        lambda: urllib.error.HTTPError(
            "http://vllm.seam.test:8000/v1/audio/transcriptions",
            code,
            "error",
            {},
            io.BytesIO(detail),
        )
    )


def _connection_reset() -> FailingTransport:
    return FailingTransport(lambda: urllib.error.URLError(ConnectionResetError(104, "Connection reset by peer")))


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


def _decode_seam_runtime(
    *,
    responses,
    speech,
    scheduler=None,
    max_speakers: int = 16,
    evidence_provider=None,
) -> tuple[LiveServiceRuntime, StubbedTransportVllmRunner]:
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
                config=LiveIdentityConfig(max_speakers=max_speakers, min_match_score=0.5, min_match_margin=0.1),
                evidence_provider=evidence_provider,
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

    The example here is a decoder that cannot work at all. A decoder that merely did not
    answer is the other half of the same seam and answers differently; see the transient
    nodes below.
    """

    class BrokenRunner:
        def transcribe(self, *args, **kwargs):
            raise ValueError("model weights are not loaded")

    decoder = RunnerBoundedWavInference(BrokenRunner(), max_samples=DEPLOYED_DECODER_MAX_SAMPLES)

    with pytest.raises(LiveProviderError) as caught:
        decoder.transcribe_pcm(span=_span(0, 8000), pcm=b"\x00\x00" * 8000)

    assert not isinstance(caught.value, LiveProviderTransientError)
    assert "ValueError" in str(caught.value)
    assert isinstance(caught.value.__cause__, ValueError)


# --------------------------------------------------------------------------------------
# The transient-decoder seam: a decoder that did not answer is not a decoder that failed.
# The classification is made from the exception the runner raises -- never from its message
# -- and only the coordinator, which owns the span, acts on it.
# --------------------------------------------------------------------------------------

GOOD_RESPONSE = {"text": "[0.00][S01]hello there[1.10]", "usage": {"prompt_tokens": 3, "completion_tokens": 9}}

# Frames alternating silence and speech, which the deployed endpoint policy cuts into one
# span per transition. Six spans is enough to blink through, recover, and blink again.
ALTERNATING_SPEECH = (False, True, False, True, False, True, False)


@pytest.mark.parametrize(
    "answer, transient",
    [
        (_connection_reset(), True),
        (_http_error(503), True),
        (_http_error(429), True),
        (_http_error(500), True),
        (FailingTransport(lambda: TimeoutError("timed out")), True),
        (_http_error(400, b"malformed multipart"), False),
        (_http_error(401, b"no"), False),
        (_http_error(404, b"no such route"), False),
    ],
)
def test_the_real_runner_decides_which_transport_failures_a_later_attempt_could_answer(answer, transient):
    """One table, drawn where the status code is still in hand.

    Every one of these left `VllmRunner` as the same bare `RuntimeError` carrying only a
    message, so the live path could not tell "the socket dropped" from "the request is
    wrong" without parsing English. The status decides, and it decides at the source.
    """
    decoder = RunnerBoundedWavInference(
        StubbedTransportVllmRunner([answer]),
        max_samples=DEPLOYED_DECODER_MAX_SAMPLES,
    )

    with pytest.raises(LiveProviderError) as caught:
        decoder.transcribe_pcm(span=_span(0, 8000), pcm=b"\x00\x00" * 8000)

    assert isinstance(caught.value, LiveProviderTransientError) is transient


def test_a_decoder_that_blinks_costs_one_retry_and_not_the_meeting():
    """The ordinary case this whole node exists for: one dropped connection mid-meeting.

    The span's bytes are unchanged and nothing has been committed, so offering them again
    is free of consequence -- and it is the only thing that keeps the words. Before this,
    a single `ConnectionResetError` from the vLLM socket ended the meeting.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    runtime, runner = _decode_seam_runtime(
        responses=[_connection_reset(), GOOD_RESPONSE],
        speech=(False, False, True, True, False),
        scheduler=scheduler,
    )
    created = runtime.create()

    for sequence in range(5):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    scheduler.drain()

    snapshot = runtime.snapshot(created.session_id)
    assert snapshot.terminal_failure is None
    # Two spans, both published with their words -- and three transport attempts for them,
    # because the first span was offered twice.
    assert len(runner.decoded_wav_bytes) == 3
    assert len(snapshot.session.committed) == 2
    assert all("hello there" in item.transcript for item in snapshot.session.committed)
    processed = _events(runtime, created.session_id, "canonical_processed")
    assert [event["empty_reason"] for event in processed] == [None, None]
    assert snapshot.session.committed_samples == snapshot.session.accounted_samples == 33600


def test_an_outage_that_outlives_transience_ends_the_meeting_and_says_so():
    """The line H1 drew, kept: a dead decoder may not render as a blank meeting.

    Each unanswered span degrades on its own -- committed empty, named, accounting intact --
    but a decoder that answers nothing is not transient however it started. The
    *consecutive* count is what separates the two, and the terminal failure names the
    condition rather than reporting some span as unsubmittable.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    runtime, runner = _decode_seam_runtime(
        responses=[_http_error(503)],
        speech=ALTERNATING_SPEECH,
        scheduler=scheduler,
    )
    created = runtime.create()

    for sequence in range(len(ALTERNATING_SPEECH)):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    scheduler.drain()

    snapshot = runtime.snapshot(created.session_id)
    processed = _events(runtime, created.session_id, "canonical_processed")
    # The spans before the last one degraded: empty, named, and accounted for.
    assert [event["empty_reason"] for event in processed] == [DECODER_DID_NOT_ANSWER] * (
        MAX_CONSECUTIVE_UNANSWERED_SPANS - 1
    )
    assert [event["submitted"] for event in processed] == [True] * (MAX_CONSECUTIVE_UNANSWERED_SPANS - 1)
    assert [item.transcript for item in snapshot.session.committed] == [""] * (
        MAX_CONSECUTIVE_UNANSWERED_SPANS - 1
    )

    assert snapshot.terminal_failure is not None
    assert "consecutive spans" in snapshot.terminal_failure.message
    assert "503" in snapshot.terminal_failure.message
    # Every span was offered the full number of attempts, and the meeting ended on the
    # first span that could not be degraded any further -- not on the first failure.
    assert len(runner.decoded_wav_bytes) == MAX_CONSECUTIVE_UNANSWERED_SPANS * DECODE_ATTEMPTS_PER_SPAN


def test_a_span_that_decodes_resets_the_outage_count():
    """Blinking is not an outage, however often the decoder blinks.

    A count that only ever rose would turn a long meeting with an occasional hiccup into a
    terminal failure with no outage anywhere in it. Five unanswered spans here, never three
    in a row, and the meeting keeps every word it was given.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    blink = _connection_reset()
    runtime, runner = _decode_seam_runtime(
        responses=[blink, blink, blink, blink, GOOD_RESPONSE, blink, blink, blink, blink, GOOD_RESPONSE],
        speech=ALTERNATING_SPEECH,
        scheduler=scheduler,
    )
    created = runtime.create()

    for sequence in range(len(ALTERNATING_SPEECH)):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    scheduler.drain()

    snapshot = runtime.snapshot(created.session_id)
    assert snapshot.terminal_failure is None
    processed = _events(runtime, created.session_id, "canonical_processed")
    assert [event["empty_reason"] for event in processed] == [
        DECODER_DID_NOT_ANSWER,
        DECODER_DID_NOT_ANSWER,
        None,
        DECODER_DID_NOT_ANSWER,
        DECODER_DID_NOT_ANSWER,
        None,
    ]
    assert all(event["submitted"] for event in processed)
    # Nothing is lost to a degraded span: the committed prefix still covers every sample
    # the session accepted, which is what lets `stop` drain.
    assert snapshot.session.committed_samples == snapshot.session.accounted_samples
    assert sum("hello there" in item.transcript for item in snapshot.session.committed) == 2


def test_a_request_the_backend_refuses_on_its_merits_is_terminal_without_a_retry():
    """The other half of the ruling, and the discriminator that proves it is not a retry-all.

    A 400 would be a 400 forever, so offering the span again would only spend the meeting's
    time to learn the same thing. Exactly one transport attempt, and the session is terminal
    at the first span.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    runtime, runner = _decode_seam_runtime(
        responses=[_http_error(400, b"malformed multipart")],
        speech=ALTERNATING_SPEECH,
        scheduler=scheduler,
    )
    created = runtime.create()

    for sequence in range(len(ALTERNATING_SPEECH)):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    scheduler.drain()

    snapshot = runtime.snapshot(created.session_id)
    assert snapshot.terminal_failure is not None
    assert "400" in snapshot.terminal_failure.message
    assert "consecutive" not in snapshot.terminal_failure.message
    assert len(runner.decoded_wav_bytes) == 1
    assert snapshot.session.committed == ()


def _span(span_id: int, sample_count: int) -> FrozenSpan:
    return FrozenSpan(id=span_id, epoch=0, start_sample=0, end_sample=sample_count, reason="hard_cap")


# --------------------------------------------------------------------------------------
# The span-bound seam: the real decoder's timestamps under the real identity preparer.
# --------------------------------------------------------------------------------------

# What the deployed vLLM endpoint returned for span 1 of the H4d probe run, rebuilt
# sample-for-sample on the host: a closing marker 0.01 s past the 2.50 s hard-cap span it
# was decoded from. The 33-span sweep that followed measured this on 2 of 33 spans, at
# +0.01 s and +0.02 s, and never at any other value.
HARD_CAP_OVERSHOOT_TRANSCRIPT = "[0.11][S01]Good morning everyone. This is the microphone.[2.51]"


def test_a_hard_cap_span_whose_speech_reaches_its_end_still_publishes():
    """The H4d blocker: the ordinary case, not an edge case.

    A hard-cap span is 2.5 s of unbroken speech *by construction* -- it exists precisely
    because no endpoint was found -- and the decoder puts its closing marker at ~= the end
    of whatever audio it is handed. So a span that ends inside speech reports an end at or
    just past its own duration, `BoundedCausalIdentityPreparer.prepare` refused it with
    `timestamp_outside_span`, and `live_service_runtime` turned the resulting `False` into a
    non-retryable terminal failure: any speaker who talked for 2.5 s without pausing ended
    the meeting.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    runtime, runner = _decode_seam_runtime(
        responses=[{"text": HARD_CAP_OVERSHOOT_TRANSCRIPT, "usage": {"prompt_tokens": 3, "completion_tokens": 11}}],
        speech=(True,) * 6,
        scheduler=scheduler,
    )
    created = runtime.create()

    for sequence in range(DEPLOYED_HARD_CAP_SAMPLES // DEPLOYED_MIXED_FRAME_SAMPLES):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    scheduler.drain()

    snapshot = runtime.snapshot(created.session_id)
    assert snapshot.terminal_failure is None
    committed = [(item.start_sample, item.end_sample, item.transcript) for item in snapshot.session.committed]
    assert [item[:2] for item in committed] == [(0, DEPLOYED_HARD_CAP_SAMPLES)]
    assert "Good morning everyone." in committed[0][2]
    # The published timestamps are inside the span: the overshoot is clamped, not carried
    # through into a committed prefix that claims audio the span does not hold.
    assert "[2.5]" in committed[0][2]
    assert "2.51" not in committed[0][2]

    processed = _events(runtime, created.session_id, "canonical_processed")
    assert [event["identity_status"] for event in processed] == ["prepared"]
    assert [event["submitted"] for event in processed] == [True]
    # Identity work ran rather than being skipped: the span carries a speaker label.
    assert snapshot.session.identity_snapshot.canonical_speakers == ("speaker-0001",)
    assert "[S01]" in committed[0][2]

    # The meeting continues past the span that used to end it.
    runtime.accept_frame(created.session_id, _frame(5, DEPLOYED_MIXED_FRAME_SAMPLES))
    assert runtime.snapshot(created.session_id).terminal_failure is None
    assert len(runner.decoded_wav_bytes) == 1


def test_the_session_answers_the_span_bound_the_same_way_the_preparer_does():
    """Fixing one copy of the bound relocates the failure instead of removing it.

    `LiveSession._canonical_validation_error` carries its own copy, and it is reached from
    both submission paths -- so a preparer that clamps while the session still refuses would
    turn a `prepared` span into `LiveSessionFailed` one call later.
    """
    session = LiveSession(max_retained_samples=960000)
    for sequence in range(DEPLOYED_HARD_CAP_SAMPLES // DEPLOYED_MIXED_FRAME_SAMPLES):
        session.accept_frame(_frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    span = session.freeze_until(DEPLOYED_HARD_CAP_SAMPLES, reason="hard_cap")

    submitted = session.submit_canonical(
        CanonicalResult(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            transcript=HARD_CAP_OVERSHOOT_TRANSCRIPT,
        )
    )

    assert submitted is True
    snapshot = session.snapshot()
    assert snapshot.status == "active"
    assert snapshot.committed_samples == DEPLOYED_HARD_CAP_SAMPLES


def test_the_provider_decode_path_answers_the_span_bound_the_same_way():
    """The third copy of the bound, in `live_adapters._validated_segments`.

    Nothing in the product constructs a `LiveProvider` today -- the coordinator calls
    `decoder.transcribe_pcm` directly -- so this copy is unreachable on the live path and
    was a fourth divergence waiting for whoever wires it up. It now answers through the same
    helper as the other two.
    """
    provider = admit_live_provider(
        LiveProviderConfig(name="seam-overshoot", assets=()),
        vad=FakeVad(),
        identity=FakeStableIdentity(confirmed=True),
        inference=FakeBoundedWavInference(
            transcript=HARD_CAP_OVERSHOOT_TRANSCRIPT,
            max_samples=DEPLOYED_DECODER_MAX_SAMPLES,
        ),
    )
    span = _span(0, DEPLOYED_HARD_CAP_SAMPLES)

    result = provider.decode_canonical(span, b"\x00\x00" * DEPLOYED_HARD_CAP_SAMPLES)

    assert result.identity_confirmed is True
    assert result.transcript == HARD_CAP_OVERSHOOT_TRANSCRIPT


@pytest.mark.parametrize(
    ("transcript", "expected"),
    [
        pytest.param("[0.11][S01]x[2.51]", ((0.11, 2.5),), id="measured_one_tick_overshoot"),
        pytest.param("[0.11][S01]x[2.52]", ((0.11, 2.5),), id="measured_two_tick_overshoot"),
        pytest.param("[0][S01]x[2.5]", ((0.0, 2.5),), id="ends_exactly_at_the_span_end"),
        pytest.param("[0.5][S01]x[1.25]", ((0.5, 1.25),), id="wholly_inside_the_span"),
        pytest.param("[9][S01]x[12]", ((2.5, 2.5),), id="wholly_after_the_span"),
        pytest.param("[0][S01]a[1][1][S02]b[9]", ((0.0, 1.0), (1.0, 2.5)), id="only_the_offending_segment_moves"),
    ],
)
def test_a_timestamp_outside_the_span_is_clamped_into_it(transcript, expected):
    """The tolerance question, answered once and by measurement rather than by taste.

    The sweep's larger overshoot is *two* quantisation ticks, so the obvious "allow one
    tick" would still have killed one of the two known-failing spans; any fixed epsilon is a
    guess about a tail that was sampled 44 times. A clamp cannot be exceeded by a number
    nobody has drawn yet, it keeps the committed prefix honest about what the span holds,
    and it is the answer the evidence provider already gives these same segments one call
    later (`live_provider_bundle._speaker_intervals_by_label`).
    """
    segments = span_segments(transcript, sample_count=DEPLOYED_HARD_CAP_SAMPLES)

    assert tuple((segment.start, segment.end) for segment in segments) == expected
    # The text is never touched: clamping is a statement about the span, not the words.
    assert all(segment.text for segment in segments)


def test_a_negative_timestamp_never_reaches_the_bound_at_all():
    """Why the low half of the clamp is defensive rather than the other half of the defect.

    The refused bound had two halves, `start < 0` and `end > duration`, and the 33-span
    sweep never saw a start below 0.00 in 44 decodes. This is the structural reason: the
    transcript parser does not accept a negative timestamp token, so a decoder that emitted
    one produces no segments at all and the caller classifies *that* instead. The clamp
    still covers it, because a future parser or a non-vLLM decoder may express one.
    """
    assert span_segments("[-0.4][S01]x[1.0]", sample_count=DEPLOYED_HARD_CAP_SAMPLES) == ()


def test_an_unparseable_transcript_is_still_not_a_set_of_segments():
    """The clamp answers only the bound question; "nothing parsed" stays the caller's call.

    Each caller classifies it differently -- H1's empty-span commit, an abstention, a
    provider error -- so the shared helper must not decide it for them.
    """
    assert span_segments("silence", sample_count=DEPLOYED_MIXED_FRAME_SAMPLES) == ()
    assert span_segments("   ", sample_count=DEPLOYED_MIXED_FRAME_SAMPLES) == ()


# --------------------------------------------------------------------------------------
# The identity-outcome seam: the real preparer's non-`prepared` answers under the real
# runtime. An identity preparation answers *who spoke*; nothing it can answer makes the
# session unable to continue, so no answer it gives may end the meeting.
# --------------------------------------------------------------------------------------

TWO_SPEAKER_TRANSCRIPT = "[0][S01]who said this[1.2][1.3][S02]and who said that[2.4]"


def _abstaining_runtime(scheduler, **kwargs):
    return _decode_seam_runtime(
        responses=[{"text": TWO_SPEAKER_TRANSCRIPT, "usage": {"prompt_tokens": 3, "completion_tokens": 11}}],
        speech=(True,) * 8,
        scheduler=scheduler,
        **kwargs,
    )


def test_an_abstaining_identity_publishes_the_span_without_a_speaker():
    """The second input class of H4d's blocker, and the same shape as the first.

    `abstain` is what the preparer returns when identity is genuinely undecidable -- two
    local speakers against exhausted speaker capacity here, ambiguous evidence or a
    same-span link conflict elsewhere. The design says "do not relabel"; `live_session`
    admitted only `status == "prepared"`, so the runtime turned the resulting `False` into
    a non-retryable terminal failure and the design said one thing while the code did
    another. The span now commits its words with no speaker attributed, and the identity
    snapshot does not move -- an abstention adds no speaker and burns no capacity.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    runtime, runner = _abstaining_runtime(scheduler, max_speakers=1)
    created = runtime.create()

    for sequence in range(DEPLOYED_HARD_CAP_SAMPLES // DEPLOYED_MIXED_FRAME_SAMPLES):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    scheduler.drain()

    snapshot = runtime.snapshot(created.session_id)
    assert snapshot.terminal_failure is None
    committed = [(item.start_sample, item.end_sample, item.transcript) for item in snapshot.session.committed]
    assert [item[:2] for item in committed] == [(0, DEPLOYED_HARD_CAP_SAMPLES)]
    # The words survive; only the claim about who spoke them is withheld.
    assert "who said this" in committed[0][2] and "and who said that" in committed[0][2]
    assert "[S00]" in committed[0][2]
    assert "[S01]" not in committed[0][2] and "[S02]" not in committed[0][2]
    assert snapshot.session.identity_snapshot.canonical_speakers == ()
    assert snapshot.session.identity_snapshot.version == 0
    # The audio is accounted for, so `stop` can still drain -- the same constraint that
    # decided H1's empty-span commit.
    assert snapshot.session.committed_samples == snapshot.session.accounted_samples == DEPLOYED_HARD_CAP_SAMPLES

    processed = _events(runtime, created.session_id, "canonical_processed")
    assert [event["identity_status"] for event in processed] == ["abstain"]
    assert [event["submitted"] for event in processed] == [True]

    # The meeting continues past the span that used to end it.
    runtime.accept_frame(created.session_id, _frame(5, DEPLOYED_MIXED_FRAME_SAMPLES))
    assert runtime.snapshot(created.session_id).terminal_failure is None
    assert len(runner.decoded_wav_bytes) == 1


def test_an_identity_preparer_that_could_not_get_evidence_publishes_the_span_too():
    """The `failed` half of the same ruling, through the real evidence seam.

    `prepare` catches every exception the evidence provider raises and returns
    `status="failed", reason="evidence_provider_failed:<type>"` -- it was already designed
    not to propagate, and then the admission rule downstream made it fatal anyway. The
    wespeaker ONNX provider is the real occupant of this seam on the host; a meeting must
    not end because one span's embedding could not be scored.
    """

    class UnavailableEvidence:
        def score(self, **kwargs):
            del kwargs
            raise RuntimeError("onnxruntime session is not available")

    scheduler = _ManualCanonicalPumpScheduler()
    runtime, _runner = _abstaining_runtime(scheduler, evidence_provider=UnavailableEvidence())
    created = runtime.create()

    for sequence in range(DEPLOYED_HARD_CAP_SAMPLES // DEPLOYED_MIXED_FRAME_SAMPLES):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    scheduler.drain()

    snapshot = runtime.snapshot(created.session_id)
    assert snapshot.terminal_failure is None
    assert [event["identity_status"] for event in _events(runtime, created.session_id, "canonical_processed")] == [
        "failed"
    ]
    committed = snapshot.session.committed
    assert "[S00]" in committed[0].transcript
    assert snapshot.session.identity_snapshot.canonical_speakers == ()
    assert snapshot.session.committed_samples == DEPLOYED_HARD_CAP_SAMPLES


def test_an_unresolved_span_stops_with_exact_accounting():
    """Why the policy is *publish unattributed* rather than *drop the span*.

    The same accounting constraint that decided H1: `stop` waits for
    `committed_samples == accepted_samples`, so a span withheld because identity did not
    resolve would strand the session until the drain deadline expired.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    runtime, _runner = _abstaining_runtime(scheduler, max_speakers=1)
    created = runtime.create()

    for sequence in range(DEPLOYED_HARD_CAP_SAMPLES // DEPLOYED_MIXED_FRAME_SAMPLES):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    scheduler.drain()
    stopped = asyncio.run(runtime.stop(created.session_id, deadline=1.0))

    assert stopped.session.status == "closed"
    assert stopped.session.accepted_samples == stopped.session.accounted_samples == DEPLOYED_HARD_CAP_SAMPLES
    assert stopped.terminal_failure is None


def test_a_span_published_without_identity_may_not_carry_the_decoder_s_own_labels():
    """The guard that keeps "unattributed" honest at the session boundary.

    `S01` in one span and `S01` in the next are the decoder's local labels and are not the
    same person until identity says so; publishing them as canonical would assert exactly
    the link the abstention declined to make. The session therefore refuses a transcript on
    this path that names anything but the unattributed marker, which no canonical display
    label (`S01`, `S02`, ...) can ever be.
    """
    session = LiveSession(max_retained_samples=960000)
    session.accept_frame(_frame(0, DEPLOYED_MIXED_FRAME_SAMPLES))
    span = session.freeze_until(DEPLOYED_MIXED_FRAME_SAMPLES, reason="hard_cap")
    def submit(transcript: str) -> bool:
        return session.submit_unlabeled_canonical(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            transcript=transcript,
        )

    assert submit("[0][S01]local label[0.5]") is False
    assert submit("nothing parses here") is False
    assert session.snapshot().committed_samples == 0
    assert session.snapshot().status == "active"

    assert submit(f"[0][{UNATTRIBUTED_SPEAKER}]unattributed[0.5]") is True
    snapshot = session.snapshot()
    assert snapshot.committed_samples == DEPLOYED_MIXED_FRAME_SAMPLES
    assert snapshot.identity_snapshot == LiveIdentitySnapshot()


@pytest.mark.parametrize(
    ("transcript", "expected"),
    [
        pytest.param("[0][S01]one[1]", f"[0][{UNATTRIBUTED_SPEAKER}]one[1]", id="the_only_speaker"),
        pytest.param(
            "[0][S01]one[1][1.2][S02]two[2]",
            f"[0][{UNATTRIBUTED_SPEAKER}]one[1][1.2][{UNATTRIBUTED_SPEAKER}]two[2]",
            id="every_speaker_including_a_repeat",
        ),
        pytest.param("[0.11][S01]x[2.51]", f"[0.11][{UNATTRIBUTED_SPEAKER}]x[2.5]", id="still_clamped_into_the_span"),
        pytest.param("silence", "", id="nothing_to_publish"),
    ],
)
def test_an_unattributed_rendering_keeps_the_words_and_drops_only_the_speaker(transcript, expected):
    """One rule for what an unresolved span publishes, driven from the decoder's transcript.

    It is rebuilt from what the decoder said rather than read out of the preparation, so a
    preparer that leaves local labels in a field it never relabeled cannot publish them.
    The span bound applies here exactly as it does to a prepared span: an unattributed span
    is no less honest about the audio it holds.
    """
    assert unattributed_transcript(transcript, sample_count=DEPLOYED_HARD_CAP_SAMPLES) == expected
