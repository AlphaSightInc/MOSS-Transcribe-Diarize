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
import logging
import time
import urllib.error
import urllib.request
from dataclasses import replace
from unittest import mock

import pytest

from moss_transcribe_diarize.app.live_adapters import (
    LIVE_DECODE_TOKEN_MARGIN,
    FakeBoundedWavInference,
    FakeStableIdentity,
    FakeVad,
    InferenceTranscript,
    LiveProviderConfig,
    LiveProviderError,
    LiveProviderTransientError,
    RunnerBoundedWavInference,
    admit_live_provider,
    canonical_decode_token_cap,
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
from moss_transcribe_diarize.app.live_helper_failure import LiveHelperFailureCoordinator
from moss_transcribe_diarize.app.live_helper_presence import (
    HELPER_HEALTH_SCHEMA,
    HelperHeartbeat,
    HelperPresenceRegistry,
)
from moss_transcribe_diarize.app.live_identity import (
    BoundedCausalIdentityPreparer,
    LiveIdentityConfig,
    unattributed_transcript,
)
from moss_transcribe_diarize.app.live_identity_album import FingerprintAlbum
from moss_transcribe_diarize.app.live_identity_sweep import LiveIdentitySweeper
from moss_transcribe_diarize.app.live_provider_bundle import (
    LiveProviderBundleAdmissionError,
    WebRtcSpeechProvider,
    WeSpeakerLiveEvidenceProvider,
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
    CanonicalSubmission,
    FrozenSpan,
    LabelRevision,
    LiveIdentitySnapshot,
    LiveSession,
)
from moss_transcribe_diarize.app.live_span_bounds import span_segments
from moss_transcribe_diarize.app.live_lane_contract import LiveLane, LiveV2Frame
from moss_transcribe_diarize.app.live_v2_session import LiveV2SessionRegistry
from moss_transcribe_diarize.app import vllm_runner
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
        # The request the product built, kept so a node can assert what the decoder was
        # actually told rather than what the caller meant to tell it.
        self.request_fields: list[dict] = []

    def _post_multipart(self, url, *, file_bytes, **kwargs):
        self.decoded_wav_bytes.append(len(file_bytes))
        self.request_fields.append(dict(kwargs.get("fields") or {}))
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
    speech_provider=None,
    prepared_by=None,
    runner=None,
) -> tuple[LiveServiceRuntime, StubbedTransportVllmRunner]:
    runner = StubbedTransportVllmRunner(responses) if runner is None else runner

    def identity_preparer():
        preparer = BoundedCausalIdentityPreparer(
            config=LiveIdentityConfig(max_speakers=max_speakers, min_match_score=0.5, min_match_margin=0.1),
            evidence_provider=evidence_provider,
        )
        # `prepared_by` wraps the real preparer rather than replacing it, so a test about
        # what the session does with a preparation still gets one the real preparer built.
        return preparer if prepared_by is None else prepared_by(preparer)

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
            speech_provider_factory=lambda: speech_provider or ScriptedSpeech(speech),
            decoder_factory=lambda: RunnerBoundedWavInference(runner, max_samples=DEPLOYED_DECODER_MAX_SAMPLES),
            identity_preparer_factory=identity_preparer,
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
# The timing seam: a wall clock is not a duration.
#
# Measured on ga0-alienware-rtx4070ti on 2026-07-29, 90 s of paired time.time()/
# time.monotonic() sampling at 20 ms: three backward steps of -1.523 / -1.504 / -1.503 s at
# ~32.3 s intervals, on a host whose `timedatectl` reports NTP active and synchronised. A
# decode brackets ~0.33 s of wall time and spans freeze every 2.5 s, so ~13 % of steps land
# inside a decode -- which is why live meetings died at t+18.1 s, t+31.5 s and t+32.1 s and
# why two longer probe runs survived untouched. Nothing in the audio explains it, and five
# audio hypotheses were eliminated before the clock was measured.
#
# No node in this repo had ever put a runner's own duration measurement under the live
# coordinator, which is why a subtraction of two wall-clock readings shipped.
# --------------------------------------------------------------------------------------

WALL_CLOCK_BACKWARD_STEP_SEC = 1.523


class SteppingWallClock:
    """A `time` stand-in whose wall clock steps backwards between two readings.

    `monotonic` delegates to the real one -- that is the whole point of the distinction, and
    a fake that stepped both would prove nothing about which clock the product reads.
    """

    def __init__(self, *, step_sec: float = WALL_CLOCK_BACKWARD_STEP_SEC):
        self.step_sec = step_sec
        self.wall_calls = 0

    def time(self) -> float:
        # Odd-numbered readings are the "after" of a bracket, and every bracket spans a step.
        self.wall_calls += 1
        return 1_800_000.0 - (self.step_sec if self.wall_calls % 2 == 0 else 0.0)

    def monotonic(self) -> float:
        return time.monotonic()


class ClockSteppingRunner(StubbedTransportVllmRunner):
    """The real runner, decoding across a backward wall-clock step every time."""

    def __init__(self, responses):
        super().__init__(responses)
        self.clock = SteppingWallClock()
        self.reported_elapsed_sec: list[float] = []

    def transcribe(self, *args, **kwargs):
        with mock.patch.object(vllm_runner, "time", self.clock):
            result = super().transcribe(*args, **kwargs)
        self.reported_elapsed_sec.append(result.elapsed_sec)
        return result


def test_a_wall_clock_step_backwards_mid_decode_does_not_end_the_meeting():
    """The production failure, reproduced through the seam that produced it.

    Before this cycle the adapter took the runner's wall-clock `elapsed_sec`, rejected the
    negative one as a non-retryable `LiveProviderError`, and the coordinator turned that into
    a terminal failure: the session left `VIEWABLE_SESSION_STATUSES`, every view poll answered
    401 and every frame answered the closed-session 409, mid-meeting, with the reason recorded
    nowhere. The transcript was never in doubt -- only the number used to compute RTF.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    runner = ClockSteppingRunner([GOOD_RESPONSE])
    runtime, _ = _decode_seam_runtime(
        responses=None,
        speech=ALTERNATING_SPEECH,
        scheduler=scheduler,
        runner=runner,
    )
    created = runtime.create()

    for sequence in range(len(ALTERNATING_SPEECH)):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    scheduler.drain()

    snapshot = runtime.snapshot(created.session_id)
    assert snapshot.terminal_failure is None
    # Every decode brackets a step, so this is the worst case rather than a sampled one.
    assert len(runner.decoded_wav_bytes) == 6
    processed = _events(runtime, created.session_id, "canonical_processed")
    assert len(processed) == 6
    assert all(event["submitted"] for event in processed)
    assert all("hello there" in item.transcript for item in snapshot.session.committed)
    # And the measurement survives too: the span is timed on a clock that cannot step, so
    # the PRD's decoder-RTF clause is answerable rather than merely non-fatal.
    assert all(event["canonical_decode_elapsed_sec"] >= 0.0 for event in processed)
    assert all(0.0 <= event["canonical_decode_rtf"] < 1.0 for event in processed)
    assert snapshot.session.committed_samples == snapshot.session.accounted_samples


def test_the_real_runner_reports_a_duration_a_stepping_wall_clock_cannot_make_negative():
    """The other half, stated where the wrong clock was read.

    The live path no longer reads this field, so this node is what keeps the runner honest
    for the batch path -- which computes its own RTF from the same number and has been doing
    it on a stepping clock for as long as this host has been deployed.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    runner = ClockSteppingRunner([GOOD_RESPONSE])
    runtime, _ = _decode_seam_runtime(
        responses=None,
        speech=(False, True, False),
        scheduler=scheduler,
        runner=runner,
    )
    created = runtime.create()
    for sequence in range(3):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    scheduler.drain()

    assert runner.reported_elapsed_sec
    assert all(elapsed >= 0.0 for elapsed in runner.reported_elapsed_sec)


def test_a_runner_result_whose_elapsed_sec_is_negative_never_reaches_the_span():
    """The rule stated on the adapter, so it holds for a runner with any clock at all.

    A runner reports whatever clock it happens to hold. The live decode's duration is the
    adapter's own measurement, taken on the monotonic clock it already reads for the
    empty-transcript branch twelve lines away -- and which it used to throw away here.
    """

    class NegativeElapsedResult:
        text = "[0.00][S01]hello there[1.10]"
        prompt_len = 3
        generated_tokens = 9
        elapsed_sec = -WALL_CLOCK_BACKWARD_STEP_SEC

    class NegativeElapsedRunner:
        def transcribe(self, *args, **kwargs):
            del args, kwargs
            return NegativeElapsedResult()

    decoder = RunnerBoundedWavInference(NegativeElapsedRunner(), max_samples=DEPLOYED_DECODER_MAX_SAMPLES)

    inferred = decoder.transcribe_pcm(span=_span(0, 8000), pcm=b"\x00\x00" * 8000)

    assert "hello there" in inferred.transcript
    assert inferred.elapsed_sec is not None and inferred.elapsed_sec >= 0.0
    assert inferred.elapsed_sec != NegativeElapsedResult.elapsed_sec
    # And the type says the same thing about any value it cannot trust: unknown, not fatal.
    assert InferenceTranscript("[0][S01]x[1]", elapsed_sec=-1.0).elapsed_sec is None
    assert InferenceTranscript("[0][S01]x[1]", elapsed_sec=float("nan")).elapsed_sec is None
    assert InferenceTranscript("[0][S01]x[1]", elapsed_sec=0.25).elapsed_sec == 0.25


def test_a_decode_whose_timing_cannot_be_trusted_commits_the_span_with_no_rtf(caplog):
    """The general rule, at the one place every span passes through.

    Untrustworthy timing *metadata* degrades: elapsed and RTF are recorded null on
    `canonical_processed` and the meeting continues. This is the fifth condition of that
    shape -- after an unparseable span, an abstained preparation, a transient decoder failure
    and a timestamp a hair past the span -- so it is answered as a rule and not as a guard on
    one field. The null is logged, because a measurement that silently disappears is exactly
    the "known but not shown" defect that cost this project four diagnostic cycles.
    """

    class UntrustworthyTimingDecoder:
        max_samples = DEPLOYED_DECODER_MAX_SAMPLES

        def transcribe_pcm(self, *, span, pcm):
            del span, pcm
            # Not an `InferenceTranscript`: the adapter is not the only implementation of
            # `BoundedWavInference`, and the coordinator must hold the line on its own.
            class Result:
                transcript = "[0.00][S01]hello there[0.50]"
                elapsed_sec = float("-inf")
                token_cap = None
                capped = False

            return Result()

    coordinator = LiveCoordinator(
        session_key="seam",
        session=LiveSession(max_retained_samples=960000),
        endpoint_policy=EndpointPolicy(
            EndpointPolicyConfig(min_speech_samples=1600, min_silence_samples=8000, hard_cap_samples=None)
        ),
        speech_provider=ScriptedSpeech((False,)),
        decoder=UntrustworthyTimingDecoder(),
        identity_preparer=BoundedCausalIdentityPreparer(
            config=LiveIdentityConfig(max_speakers=16, min_match_score=0.5, min_match_margin=0.1)
        ),
        arbiter=InferenceArbiter(),
    )
    coordinator.accept_frame(_frame(0, DEPLOYED_MIXED_FRAME_SAMPLES))
    assert len(coordinator.flush_endpoint()) == 1

    with caplog.at_level(logging.WARNING, logger="moss_transcribe_diarize.live.decode"):
        result = coordinator.process_work_item(coordinator.arbiter.next_work())

    assert result.submitted is True
    assert result.committed_samples == DEPLOYED_MIXED_FRAME_SAMPLES
    assert result.canonical_decode_elapsed_sec is None
    assert result.canonical_decode_rtf is None
    # The span's own duration is still reported -- only the measurement of it is unknown.
    assert result.frozen_span_sample_count == DEPLOYED_MIXED_FRAME_SAMPLES
    assert caplog.messages == [
        "live canonical decode timing untrustworthy: span_id=0 field=elapsed_sec value=-inf"
    ]


# --------------------------------------------------------------------------------------
# The runaway-decode seam: a decode that answers, but too slowly to be part of a meeting.
#
# F1 measured 42 spans, 40 of which decoded in 0.10-0.54 s. The other two ran for 8.49 s
# and 8.29 s on 2.5 s of audio -- degenerate repeat loops -- and because the decode queue is
# serial each one delayed every span behind it by up to 8.3 s. That is the whole latency
# tail: committed p95 9053 ms against a median lag of ~0 s. Neither of the plan's ordered
# remedies (a 2.0 s span cap, then a 0.5 s poll interval) touches this term, because the
# floor was never binding.
# --------------------------------------------------------------------------------------

# The tokenised evidence the cap is derived from: (what it is, span seconds, tokens the
# deployed decoder generated). Measured 2026-07-28 by tokenising the committed spans of two
# independent live runs -- the F1 canary and the echo-free canary -- with the deployed
# decoder's own tokenizer through the vLLM `/tokenize` endpoint on the host. The first two
# rows are the maxima over 76 spans of real speech; the third is F1's own runaway, which
# ran to `VllmRunner.transcribe`'s 2048-token default because nothing else bounded it.
MEASURED_MAX_REAL_SPEECH_SPANS = (
    ("the densest full span, c51 span 45", 2.5, 54),
    ("the densest short span, F1 span 28", 0.17, 17),
)
MEASURED_RUNAWAY_SPAN_TOKENS = 2024


def test_the_token_cap_covers_the_measured_speech_and_still_bounds_a_runaway():
    """The derivation, held in place by the evidence it came from.

    A bound chosen against a measurement is only as good as the measurement staying in the
    repository: without this node the two constants are a pair of numbers somebody can tune
    until a gate goes green, which is exactly what the PRD forbids. So the same spans that
    produced them are asserted here -- real speech must fit under the cap with the margin
    the constants claim, and the runaway must not.
    """
    for label, duration_sec, tokens in MEASURED_MAX_REAL_SPEECH_SPANS:
        cap = canonical_decode_token_cap(sample_count=round(duration_sec * LIVE_SAMPLE_RATE))
        assert cap > tokens, label
        # The margin is explicit, so it is asserted rather than described. Every one of the
        # 76 measured spans sits at least 4.8x under its cap; the two maxima are the tight
        # ones, and if either stops clearing the declared margin the constants are stale.
        assert cap >= LIVE_DECODE_TOKEN_MARGIN * tokens, label

    hard_cap_cap = canonical_decode_token_cap(sample_count=DEPLOYED_HARD_CAP_SAMPLES)
    assert hard_cap_cap < MEASURED_RUNAWAY_SPAN_TOKENS / 7
    # A shorter span gets a smaller budget: the cap is a statement about the audio, not a
    # single constant that happens to sit above the longest span.
    assert canonical_decode_token_cap(sample_count=DEPLOYED_MIXED_FRAME_SAMPLES) < hard_cap_cap
    with pytest.raises(LiveProviderError):
        canonical_decode_token_cap(sample_count=0)


def test_the_live_decode_carries_its_duration_derived_cap_onto_the_wire():
    """The real runner builds the real request, and the cap is in it.

    `RunnerBoundedWavInference` passed no `max_new_tokens` at all, so every live span was
    decoded under `VllmRunner.transcribe`'s 2048-token default -- the bound the two runaway
    spans actually hit. The assertion is made on `max_completion_tokens`, the field the
    product's own `_build_fields` puts on the wire, because that is what the decoder obeys.
    """
    runner = StubbedTransportVllmRunner([GOOD_RESPONSE])
    decoder = RunnerBoundedWavInference(runner, max_samples=DEPLOYED_DECODER_MAX_SAMPLES)

    for sample_count in (DEPLOYED_HARD_CAP_SAMPLES, DEPLOYED_MIXED_FRAME_SAMPLES):
        inferred = decoder.transcribe_pcm(span=_span(0, sample_count), pcm=b"\x00\x00" * sample_count)
        expected = canonical_decode_token_cap(sample_count=sample_count)
        assert inferred.token_cap == expected
        assert inferred.capped is False
        assert runner.request_fields[-1]["max_completion_tokens"] == str(expected)

    # A configured ceiling may only tighten the derived one -- a deployment cannot opt out
    # of the bound, and it can still ask for less.
    tight = RunnerBoundedWavInference(runner, max_samples=DEPLOYED_DECODER_MAX_SAMPLES, max_new_tokens=32)
    tight.transcribe_pcm(span=_span(0, DEPLOYED_HARD_CAP_SAMPLES), pcm=b"\x00\x00" * DEPLOYED_HARD_CAP_SAMPLES)
    assert runner.request_fields[-1]["max_completion_tokens"] == "32"

    loose = RunnerBoundedWavInference(runner, max_samples=DEPLOYED_DECODER_MAX_SAMPLES, max_new_tokens=2048)
    inferred = loose.transcribe_pcm(span=_span(0, DEPLOYED_HARD_CAP_SAMPLES), pcm=b"\x00\x00" * DEPLOYED_HARD_CAP_SAMPLES)
    assert inferred.token_cap == canonical_decode_token_cap(sample_count=DEPLOYED_HARD_CAP_SAMPLES)
    assert runner.request_fields[-1]["max_completion_tokens"] != "2048"


def test_a_capped_span_commits_its_words_and_says_that_it_was_capped():
    """D-c, at the seam that has to honour it: cap the decode, commit what came back.

    Abandoning the span, or committing it empty, would remove accepted audio from the
    transcript -- the loss the PRD's zero-loss clause forbids -- and would break the identity
    preparer's timeline as well. So the span publishes its words with fewer of them, and the
    event says so: a capped span and a quiet one are otherwise indistinguishable downstream.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    # The span this speech script produces: 14400 samples of leading silence, then 19200 of
    # speech. Its cap follows from that duration and nothing else.
    speech_span_samples = 19200
    cap = canonical_decode_token_cap(sample_count=speech_span_samples)
    runaway = "".join("[0.99][S06]uh[1.21]" for _ in range(40))
    runtime, runner = _decode_seam_runtime(
        responses=[
            NO_SPEECH_RESPONSES["zero parsed segments"],
            {"text": runaway, "usage": {"prompt_tokens": 3, "completion_tokens": cap}},
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
    processed = _events(runtime, created.session_id, "canonical_processed")
    assert [event["frozen_span_sample_count"] for event in processed] == [14400, speech_span_samples]
    assert [event["canonical_decode_token_cap"] for event in processed] == [
        canonical_decode_token_cap(sample_count=14400),
        cap,
    ]
    # Only the span that used its whole budget is reported as capped.
    assert [event["canonical_decode_capped"] for event in processed] == [False, True]
    assert [event["submitted"] for event in processed] == [True, True]
    # The words came back and stayed: the capped span is committed, not dropped.
    assert snapshot.session.committed[1].transcript.count("uh") > 0
    assert snapshot.session.committed_samples == snapshot.session.accounted_samples == 33600


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


class UnavailableEvidence:
    """The evidence provider the host actually runs, on a day it cannot start."""

    def score(self, **kwargs):
        del kwargs
        raise RuntimeError("onnxruntime session is not available")


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
    def submit(transcript: str) -> CanonicalSubmission:
        return session.submit_unlabeled_canonical(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            transcript=transcript,
        )

    # Each refusal names itself: the two ways this guard can refuse are different facts
    # about the transcript, and a reader downstream gets to know which one happened.
    assert submit("[0][S01]local label[0.5]").refusal == "unattributed_transcript_names_a_speaker"
    assert submit("nothing parses here").refusal == "unattributed_transcript_unparseable"
    assert session.snapshot().committed_samples == 0
    assert session.snapshot().status == "active"

    assert submit(f"[0][{UNATTRIBUTED_SPEAKER}]unattributed[0.5]").submitted is True
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

# --------------------------------------------------------------------------------------
# The diagnosability seam: a refusal must carry the word that names it, out of the
# process. Every fix in this file was found by reading a failure; blocker 4 was the one
# that could not be, because the process classified the refusal correctly and then
# discarded the single word that said which refusal it was.
# --------------------------------------------------------------------------------------


class StaleBaseVersionPreparer:
    """The real preparer, answering against identity state the session has moved past.

    After J2 this is the only way a canonical submission still refuses, and it is a
    statement about the session's timing rather than about who spoke -- so it is the one
    refusal an operator can still be shown, and it had better say which one it is.
    """

    def __init__(self, inner):
        self.inner = inner

    def prepare(self, **kwargs):
        preparation = self.inner.prepare(**kwargs)
        return replace(preparation, base_snapshot_version=preparation.base_snapshot_version - 1)


class SpeechThatFailsWithoutAWord:
    """A collaborator that raises an exception carrying no message at all."""

    def observe(self, **kwargs):
        del kwargs
        raise ValueError()


@pytest.mark.parametrize(
    ("runtime_kwargs", "identity_status", "identity_reason"),
    [
        pytest.param(
            {"max_speakers": 1},
            "abstain",
            "speaker_capacity_exceeded",
            id="identity_declined_to_decide",
        ),
        pytest.param(
            {"evidence_provider": UnavailableEvidence()},
            "failed",
            "evidence_provider_failed:RuntimeError",
            id="identity_never_got_the_evidence",
        ),
    ],
)
def test_an_unresolved_span_says_why_identity_did_not_resolve(runtime_kwargs, identity_status, identity_reason):
    """The preparer's `reason` leaves the process, on the event that reports the span.

    Both spans below publish unattributed and both keep the meeting alive -- J2's ruling --
    so from outside they are the same span. They are not the same fact: one is identity
    working correctly against audio it cannot resolve, the other is a provider outage that
    needs an operator. The `reason` was already computed and was written into a proposed
    snapshot the session never commits, which is to say it was computed and thrown away.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    runtime, _runner = _abstaining_runtime(scheduler, **runtime_kwargs)
    created = runtime.create()

    for sequence in range(DEPLOYED_HARD_CAP_SAMPLES // DEPLOYED_MIXED_FRAME_SAMPLES):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    scheduler.drain()

    processed = _events(runtime, created.session_id, "canonical_processed")
    assert [(event["identity_status"], event["identity_reason"]) for event in processed] == [
        (identity_status, identity_reason)
    ]
    # The span still published and the meeting still runs: naming the reason is not a
    # reason to refuse the span.
    assert [event["submitted"] for event in processed] == [True]
    assert [event["submission_refusal"] for event in processed] == [None]
    assert runtime.snapshot(created.session_id).terminal_failure is None


def test_a_span_the_session_refuses_names_the_refusal_and_not_only_the_status():
    """The failure H4d's probe received, with the word it was missing.

    The probe read `{code: canonical_not_submitted, identity_status: "failed"}` and could
    get no further: `submit_prepared_canonical` returned a bare `False` for six distinct
    conditions and the runtime reported all six identically. Here the preparation is
    `prepared` and perfectly well formed -- only its base version is stale -- so
    `identity_status` says nothing at all about why the session refused it.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    runtime, _runner = _abstaining_runtime(scheduler, prepared_by=StaleBaseVersionPreparer)
    created = runtime.create()

    for sequence in range(DEPLOYED_HARD_CAP_SAMPLES // DEPLOYED_MIXED_FRAME_SAMPLES):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    scheduler.drain()

    failure = runtime.snapshot(created.session_id).terminal_failure
    assert failure is not None
    assert failure.code == "canonical_not_submitted"
    assert failure.detail == {
        "span_id": 0,
        "identity_status": "prepared",
        "identity_reason": None,
        "submission_refusal": "identity_preparation_stale_base_version",
    }
    assert "identity_preparation_stale_base_version" in failure.message
    # The event that reported the span carries the same word, so a reader following the
    # event stream does not have to wait for the terminal record to learn it.
    processed = _events(runtime, created.session_id, "canonical_processed")
    assert [(event["submitted"], event["submission_refusal"]) for event in processed] == [
        (False, "identity_preparation_stale_base_version")
    ]


def test_a_decoder_outage_reports_its_facts_as_fields_and_not_only_as_prose():
    """J3's own terminal failure, made readable by something other than a human.

    It arrived as `code='LiveProviderError'` -- the exception's class name standing in for
    a code, so adding a subclass would have renamed it -- with `detail=None`, which put the
    span, the cause and the count that ended the meeting inside an English sentence and
    nowhere else.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    runtime, _runner = _decode_seam_runtime(
        responses=[_http_error(503)],
        speech=ALTERNATING_SPEECH,
        scheduler=scheduler,
    )
    created = runtime.create()

    for sequence in range(len(ALTERNATING_SPEECH)):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    scheduler.drain()

    failure = runtime.snapshot(created.session_id).terminal_failure
    assert failure is not None
    assert failure.code == "canonical_decode_failed"
    assert failure.detail == {
        "error_type": "LiveProviderError",
        "cause": "TransientTranscriptionError",
        "span_id": MAX_CONSECUTIVE_UNANSWERED_SPANS - 1,
        "consecutive_unanswered_spans": MAX_CONSECUTIVE_UNANSWERED_SPANS,
    }
    # The sentence still says everything it said before; it is no longer the only copy.
    assert "consecutive spans" in failure.message and "503" in failure.message


def test_a_span_the_backend_refuses_on_its_merits_is_named_the_same_way():
    """The discriminator: the same code, and a detail that tells the two apart.

    A 400 and an outage are both decode failures and both terminal, so they share a code.
    What distinguishes them is that one span was refused once on its merits and the other
    was offered repeatedly and never answered -- which is a field, not a judgement call.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    runtime, _runner = _decode_seam_runtime(
        responses=[_http_error(400, b"malformed multipart")],
        speech=ALTERNATING_SPEECH,
        scheduler=scheduler,
    )
    created = runtime.create()

    for sequence in range(len(ALTERNATING_SPEECH)):
        runtime.accept_frame(created.session_id, _frame(sequence, DEPLOYED_MIXED_FRAME_SAMPLES))
    scheduler.drain()

    failure = runtime.snapshot(created.session_id).terminal_failure
    assert failure is not None
    assert failure.code == "canonical_decode_failed"
    assert failure.detail == {"error_type": "LiveProviderError", "cause": "RuntimeError", "span_id": 0}
    assert "consecutive_unanswered_spans" not in failure.detail


def test_an_exception_that_names_nothing_is_still_reported_as_a_failure():
    """The failure path may not fail on the failure.

    `LiveServiceFailureRecord` refuses an empty message, so an exception raised with no
    arguments used to make `_failure_from_exception` raise *while handling* it: the session
    was left with no terminal record, and the caller got a complaint about failure messages
    in place of the thing that went wrong. A type is a poor name and a much better answer
    than none.
    """
    scheduler = _ManualCanonicalPumpScheduler()
    runtime, _runner = _decode_seam_runtime(
        responses=[GOOD_RESPONSE],
        speech=ALTERNATING_SPEECH,
        scheduler=scheduler,
        speech_provider=SpeechThatFailsWithoutAWord(),
    )
    created = runtime.create()

    with pytest.raises(ValueError) as raised:
        runtime.accept_frame(created.session_id, _frame(0, DEPLOYED_MIXED_FRAME_SAMPLES))
    # The caller sees the original exception, not a complaint about the failure record.
    assert str(raised.value) == ""

    failure = runtime.snapshot(created.session_id).terminal_failure
    assert failure is not None
    assert (failure.code, failure.message) == ("integrity_error", "ValueError")
    assert failure.detail == {"error_type": "ValueError"}


# --------------------------------------------------------------------------------------
# The helper-terminal seam: the real lease coordinator over the real v2 registry and the
# real runtime. Every part of the teardown is a product class, because the defect was that
# the teardown discarded what the client had already said.
# --------------------------------------------------------------------------------------


def _helper_heartbeat(
    *,
    lane_codes: dict[str, str],
    sequence: int = 0,
    state: str = "capturing",
    lane_state: str = "failed",
    dropped_frames: int = 0,
) -> HelperHeartbeat:
    """A heartbeat in the shape the shipped Swift client sends.

    `state` stays `capturing` for a failed lane: `CaptureHTTPTransport` reports the
    top-level state as `running ? "capturing" : "stopped"` and never sends `"failed"`, so
    all-lanes-failed is the only way this client can turn a session terminal.

    `lane_state` is a parameter because since D-a the client has two ways to name a lane
    that hit trouble, and only one of them may close it.
    """

    def lane(name: str) -> dict:
        code = lane_codes.get(name)
        return {
            "state": lane_state if code else "capturing",
            "device_epoch": 0,
            "dropped_frames": dropped_frames if code else 0,
            "discontinuities": 0,
            "failure_code": code,
        }

    return HelperHeartbeat.from_dict(
        {
            "schema": HELPER_HEALTH_SCHEMA,
            "instance_id": "helper-a",
            "sequence": sequence,
            "sent_monotonic_ns": 10 + sequence,
            "helper_version": "0.1.0",
            "state": state,
            "lanes": {"system": lane("system"), "microphone": lane("microphone")},
        }
    )


def _helper_seam(runtime: LiveServiceRuntime, session_id: str):
    v2_sessions = LiveV2SessionRegistry(max_retained_samples=960000)
    v2_sessions.create(session_id)
    presence = HelperPresenceRegistry(monotonic_ns=lambda: 100)
    coordinator = LiveHelperFailureCoordinator(
        live_helper_lease_seconds=30.0,
        v2_sessions=v2_sessions,
        helper_presence=presence,
        abort_mono=runtime.abort,
    )
    return coordinator, v2_sessions, presence


def test_a_helper_that_reports_both_lanes_failed_leaves_the_reason_in_both_journals(caplog):
    """The Phase K failure, assembled from the products that produced it.

    Observed on m4mbp after both TCC grants were recorded: `start` returned
    `ok:true, running:true`, one heartbeat returned 200, and every later request 403'd
    because the session had been released. Both lanes had reported `failed` -- the only
    terminal condition this client can express -- and the codes it sent reached no surface
    at all: the terminal path expired the v2 session with a generic reason and skipped the
    per-lane recording that the surviving path does. Nothing in this repo assembled the
    coordinator, the v2 registry and the runtime together, so no test could see it.
    """

    runtime, _runner = _decode_seam_runtime(responses=[], speech=(False,))
    created = runtime.create()
    coordinator, v2_sessions, presence = _helper_seam(runtime, created.session_id)
    snapshot = presence.observe(
        created.session_id,
        _helper_heartbeat(
            lane_codes={"system": "device_unavailable", "microphone": "permission_denied"}
        ),
    )

    with caplog.at_level(logging.NOTSET, logger="moss_transcribe_diarize.live.helper"):
        lease = asyncio.run(coordinator.observe(created.session_id, snapshot))

    assert lease is None
    # 1. The runtime journal, which outlives every registry the teardown releases.
    aborted = _events(runtime, created.session_id, "session_aborted")
    assert [event["failure"]["message"] for event in aborted] == ["helper_all_lanes_failed"]
    assert aborted[0]["failure"]["detail"] == {
        "session_id": created.session_id,
        "reason": "helper_all_lanes_failed",
        "lane_failures": {
            "system": "device_unavailable",
            "microphone": "permission_denied",
        },
    }
    # 2. The session's own terminal record, which is what a later request is refused with.
    failure = runtime.snapshot(created.session_id).terminal_failure
    assert failure is not None
    assert failure.detail["lane_failures"]["microphone"] == "permission_denied"
    # 3. The host journal, for the operator who cannot ask the service anything anymore.
    assert [record.getMessage() for record in caplog.records] == [
        "live helper terminal: session=%s reason=helper_all_lanes_failed "
        "lane.system=device_unavailable lane.microphone=permission_denied" % created.session_id
    ]
    # The v2 session is gone, as it was before: expiry is the last moment its lane codes
    # exist, which is why they are stamped on the way out rather than read afterwards.
    assert created.session_id not in v2_sessions


def test_one_failed_lane_is_recorded_without_ending_the_meeting():
    """The mic-granted / system-audio-denied run the PRD certifies still has to work.

    One failed lane is not terminal, so nothing is aborted, nothing is released, and the
    lane's typed code is recorded on the live session itself -- the surviving path already
    did this, and the terminal path is what had to be brought up to it.
    """

    runtime, _runner = _decode_seam_runtime(responses=[], speech=(False,))
    created = runtime.create()
    coordinator, v2_sessions, presence = _helper_seam(runtime, created.session_id)
    snapshot = presence.observe(
        created.session_id,
        _helper_heartbeat(lane_codes={"system": "permission_denied"}),
    )

    lease = asyncio.run(coordinator.observe(created.session_id, snapshot))

    assert lease is not None
    assert runtime.snapshot(created.session_id).terminal_failure is None
    assert _events(runtime, created.session_id, "session_aborted") == []
    lanes = v2_sessions.get(created.session_id).snapshot().to_dict()["lanes"]
    assert (lanes["system"]["health"], lanes["system"]["failure_code"]) == (
        "failed",
        "permission_denied",
    )
    assert (lanes["microphone"]["health"], lanes["microphone"]["failure_code"]) == ("active", None)


def test_a_degraded_lane_keeps_publishing_and_never_reaches_the_lane_failure_path():
    """The chain that ended F1 and F3, refused at the link the client now controls.

    A dropped capture buffer used to reach here as `state: "failed"`, which is the one
    word `_failed_lanes` reads: the coordinator called `fail_lane`, the lane's retained
    audio moved to `failed_samples`, and every later frame on it answered 409 --
    permanently, because a v2 lane has no un-fail path. D-a makes the client say
    `degraded` instead, and this asserts what that buys against the *real* coordinator,
    registry and runtime rather than against the reading of them: the lease is renewed,
    the lane is untouched, and the next frame on the lane that dropped audio is accepted.

    The negative control is the node directly above -- same seam, same code, `failed`
    instead of `degraded` -- so what is being tested is the state word and nothing else.
    """

    runtime, _runner = _decode_seam_runtime(responses=[], speech=(False,))
    created = runtime.create()
    coordinator, v2_sessions, presence = _helper_seam(runtime, created.session_id)
    snapshot = presence.observe(
        created.session_id,
        _helper_heartbeat(
            lane_codes={"system": "macos_buffer_overrun"},
            lane_state="degraded",
            dropped_frames=149,
        ),
    )

    lease = asyncio.run(coordinator.observe(created.session_id, snapshot))

    assert lease is not None
    assert runtime.snapshot(created.session_id).terminal_failure is None
    assert _events(runtime, created.session_id, "session_aborted") == []
    lanes = v2_sessions.get(created.session_id).snapshot().to_dict()["lanes"]
    assert (lanes["system"]["health"], lanes["system"]["failure_code"]) == ("active", None)
    assert lanes["system"]["failed_samples"] == 0
    # The meeting continues on the lane that lost audio, which is the whole point: the
    # publish that used to throw a 409 here is what stopped the heartbeat.
    ack = v2_sessions.get(created.session_id).accept(
        LiveV2Frame(
            lane=LiveLane.SYSTEM,
            sequence=0,
            capture_timestamp_ns=0,
            device_epoch=0,
            silent=False,
            discontinuity=False,
            sample_rate=16000,
            sample_count=8000,
            pcm=b"\x00" * 16000,
        )
    )
    assert (ack.lane, ack.sequence, ack.accepted_samples) == (LiveLane.SYSTEM, 0, 8000)


# --------------------------------------------------------------------------------------
# ADR-0002 step 3, end to end: a sweep's correction reaching the transcript a reader holds.
#
# Nothing else in the suite puts the real album, the real sweeper, the real matcher and the
# real session in one process. Each half has been measured alone -- the album at 93.4 %
# against overwrite's 72.0 %, the swept transcript at 99.26 % -- and neither measurement can
# see whether a correction ever reaches a reader, which is the whole of what step 3 promises.
# --------------------------------------------------------------------------------------


class _ScriptedSpanEncoder:
    """One vector per `embed` call, so each span's voiceprint is the test's choice."""

    def __init__(self, vectors):
        self.vectors = list(vectors)
        self.calls = 0

    def embed(self, wav_path, intervals):
        del wav_path, intervals
        self.calls += 1
        return self.vectors[self.calls - 1]


class _ScriptedSpanDecoder:
    max_samples = DEPLOYED_DECODER_MAX_SAMPLES

    def __init__(self, transcripts):
        self.transcripts = list(transcripts)
        self.calls = 0

    def transcribe_pcm(self, *, span, pcm):
        del span, pcm
        self.calls += 1
        return InferenceTranscript(self.transcripts[self.calls - 1], elapsed_sec=0.1)


def _drive_span(coordinator: LiveCoordinator, *, first_sequence: int, frames: int = 4):
    for offset in range(frames):
        coordinator.accept_frame(_frame(first_sequence + offset, DEPLOYED_MIXED_FRAME_SAMPLES))
    queued = coordinator.flush_endpoint()
    assert len(queued) == 1
    return coordinator.process_work_item(coordinator.arbiter.next_work())


def test_a_sweep_relabels_an_abstained_span_in_the_transcript_a_reader_is_holding():
    """The living document, assembled from production parts only.

    Span 2 is genuinely ambiguous when it is decoded -- two canonical speakers sit at the
    same distance from it -- so J2 publishes its words under `S00` and drops the claim. Two
    spans later the album has heard more of the first speaker, the retained evidence
    re-matches decisively, and the words the reader has already read acquire the speaker
    they always had. The live path never revisits a published span, so without this seam
    that recovery is a number in an offline harness and nothing else.
    """

    config = LiveIdentityConfig(max_speakers=16, min_match_score=0.35, min_match_margin=0.1)
    album = FingerprintAlbum()
    provider = WeSpeakerLiveEvidenceProvider(
        encoder=_ScriptedSpanEncoder(
            [
                [1.0, 0.0],  # span 0 -- births speaker-0001
                [0.0, 1.0],  # span 1 -- births speaker-0002
                [0.7071, 0.7071],  # span 2 -- equidistant, so identity abstains
                [0.9, 0.4359],  # span 3 -- the first speaker again, off-centre
                [1.0, 0.0],  # span 4 -- the sweep that sees span 3's contribution
            ]
        ),
        album=album,
        # Meeting-time cadence: five two-second spans, so a one-second interval is what puts
        # more than one sweep inside a test rather than a change to the shipped default.
        sweeper=LiveIdentitySweeper(album=album, config=config, interval_seconds=1.0),
    )
    coordinator = LiveCoordinator(
        session_key="seam",
        session=LiveSession(max_retained_samples=960000),
        endpoint_policy=EndpointPolicy(
            EndpointPolicyConfig(min_speech_samples=1600, min_silence_samples=8000, hard_cap_samples=None)
        ),
        speech_provider=ScriptedSpeech((True,) * 20),
        decoder=_ScriptedSpanDecoder(
            [
                "[0][S01]first voice[2]",
                "[0][S01]second voice[2]",
                "[0][S01]who is this[2]",
                "[0][S01]first voice again[2]",
                "[0][S01]more of the first[2]",
            ]
        ),
        identity_preparer=BoundedCausalIdentityPreparer(config=config, evidence_provider=provider),
        arbiter=InferenceArbiter(),
    )

    results = [_drive_span(coordinator, first_sequence=index * 4) for index in range(5)]

    assert [item.submitted for item in results] == [True] * 5
    assert results[2].identity_status == "abstain"
    assert results[2].identity_reason == "ambiguous_identity"
    # Nothing is corrected until the album has heard enough to disagree with the live path.
    assert [item.identity_revision_units for item in results] == [0, 0, 0, 0, 1]
    assert results[4].identity_revision_spans == 1
    assert results[4].identity_revision_version == 1
    assert results[4].identity_revision_merges == 0

    committed = coordinator.session.snapshot().committed
    # What was published, and is still published: the words, unattributed, hash-chained.
    assert committed[2].transcript == f"[0][{UNATTRIBUTED_SPEAKER}]who is this[2]"
    # What the reader is shown now.
    assert committed[2].revised_transcript == "[0][S01]who is this[2]"
    assert coordinator.session.snapshot().label_revision_version == 1
    # And no other span moved: a sweep that churned labels would show up here first.
    assert [item.revised_transcript for item in committed] == [
        None,
        None,
        "[0][S01]who is this[2]",
        None,
        None,
    ]

    # A span identity *did* answer is addressable too. The sweep had no reason to move span 0
    # here, so the claim is made directly: the coordinator carries every published span's
    # local speakers, not only the ones an abstention left without a label.
    outcome = coordinator.session.revise_labels(
        (LabelRevision(span_id=0, local_speaker="S01", canonical_speaker="speaker-0002"),)
    )
    assert (outcome.revised_spans, outcome.revised_units) == (1, 1)
    assert coordinator.session.snapshot().committed[0].revised_transcript == "[0][S02]first voice[2]"
