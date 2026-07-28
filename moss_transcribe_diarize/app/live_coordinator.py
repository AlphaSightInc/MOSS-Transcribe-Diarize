from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Protocol

from moss_transcribe_diarize.transcript_parser import parse_transcript

from .live_adapters import BoundedWavInference
from .live_arbiter import ArbiterWorkItem, InferenceArbiter
from .live_endpoint import EndpointPolicy, EndpointPolicyError, EndpointSpan, SpeechObservation
from .live_identity import unattributed_transcript
from .live_session import (
    AudioFrame,
    CanonicalResult,
    FrozenSpan,
    LIVE_SAMPLE_RATE,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    LiveSession,
    PCM16_BYTES_PER_SAMPLE,
)


class LiveCoordinatorError(RuntimeError):
    pass


class SpeechSignalProvider(Protocol):
    def observe(
        self,
        *,
        frame: AudioFrame,
        start_sample: int,
        end_sample: int,
    ) -> tuple[SpeechObservation, ...]:
        ...


class LiveIdentityPreparer(Protocol):
    def prepare(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        transcript: str,
        base_snapshot: LiveIdentitySnapshot,
    ) -> LiveIdentityPreparation:
        ...


@dataclass(frozen=True, slots=True)
class CanonicalWork:
    session_key: str
    span: FrozenSpan


@dataclass(frozen=True, slots=True)
class CoordinatorFrameResult:
    accepted_start_sample: int
    accepted_end_sample: int
    endpoint_spans: tuple[EndpointSpan, ...]
    frozen_spans: tuple[FrozenSpan, ...]
    queued_item_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CoordinatorWorkResult:
    span_id: int
    submitted: bool
    identity_status: str
    committed_samples: int
    canonical_decode_elapsed_sec: float | None = None
    frozen_span_sample_count: int | None = None
    frozen_span_duration_sec: float | None = None
    canonical_decode_rtf: float | None = None
    empty_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CoordinatorWorkInput:
    span: FrozenSpan
    pcm: bytes
    base_snapshot: LiveIdentitySnapshot


@dataclass(frozen=True, slots=True)
class CoordinatorPreparedWork:
    span: FrozenSpan
    transcript: str
    preparation: LiveIdentityPreparation | None
    decode_elapsed_sec: float | None = None
    empty_reason: str | None = None


class LiveCoordinator:
    """Connect ordered live PCM to endpointing, canonical decode, and atomic publish."""

    def __init__(
        self,
        *,
        session_key: str,
        session: LiveSession,
        endpoint_policy: EndpointPolicy,
        speech_provider: SpeechSignalProvider,
        decoder: BoundedWavInference,
        identity_preparer: LiveIdentityPreparer,
        arbiter: InferenceArbiter,
    ):
        if not session_key:
            raise ValueError("session_key must be non-empty.")
        self.session_key = session_key
        self.session = session
        self.endpoint_policy = endpoint_policy
        self.speech_provider = speech_provider
        self.decoder = decoder
        self.identity_preparer = identity_preparer
        self.arbiter = arbiter
        self._pcm = _PcmRetention()

    def accept_frame(self, frame: AudioFrame) -> CoordinatorFrameResult:
        ack = self.session.accept_frame(frame)
        self._pcm.append(ack.start_sample, ack.end_sample, frame.pcm)
        observations = self.speech_provider.observe(
            frame=frame,
            start_sample=ack.start_sample,
            end_sample=ack.end_sample,
        )
        endpoint_spans = self._observe_endpoint(observations, ack.start_sample, ack.end_sample)
        frozen_spans = tuple(self.session.freeze_until(span.end_sample, reason=span.reason) for span in endpoint_spans)
        queued = tuple(self._queue_canonical(span) for span in frozen_spans)
        return CoordinatorFrameResult(
            accepted_start_sample=ack.start_sample,
            accepted_end_sample=ack.end_sample,
            endpoint_spans=endpoint_spans,
            frozen_spans=frozen_spans,
            queued_item_ids=queued,
        )

    def flush_endpoint(self) -> tuple[int, ...]:
        return self._freeze_and_queue(self.endpoint_policy.flush())

    def reset_endpoint(self) -> tuple[int, ...]:
        return self._freeze_and_queue(self.endpoint_policy.reset())

    def stop_endpoint(self) -> tuple[int, ...]:
        return self._freeze_and_queue(self.endpoint_policy.stop())

    def capture_work_item(self, item: ArbiterWorkItem) -> CoordinatorWorkInput:
        if item.kind != InferenceArbiter.LIVE_CANONICAL or not isinstance(item.payload, CanonicalWork):
            raise LiveCoordinatorError("work item is not live canonical coordinator work.")
        work = item.payload
        if work.session_key != self.session_key:
            raise LiveCoordinatorError("canonical work belongs to a different live session.")

        span = work.span
        pcm = self._pcm.extract(span.start_sample, span.end_sample)
        base_snapshot = self.session.snapshot().identity_snapshot
        return CoordinatorWorkInput(span=span, pcm=pcm, base_snapshot=base_snapshot)

    def prepare_work_item(self, work: CoordinatorWorkInput) -> CoordinatorPreparedWork:
        span = work.span
        pcm = work.pcm
        inferred = self.decoder.transcribe_pcm(span=span, pcm=pcm)
        transcript = inferred.transcript
        empty_reason = _empty_transcript_reason(transcript)
        if empty_reason is not None:
            # No identity work: there is no transcript to relabel and no speaker to link.
            return CoordinatorPreparedWork(
                span=span,
                transcript="",
                preparation=None,
                decode_elapsed_sec=inferred.elapsed_sec,
                empty_reason=empty_reason,
            )
        preparation = self.identity_preparer.prepare(
            span=span,
            pcm=pcm,
            transcript=transcript,
            base_snapshot=work.base_snapshot,
        )
        return CoordinatorPreparedWork(
            span=span,
            transcript=transcript,
            preparation=preparation,
            decode_elapsed_sec=inferred.elapsed_sec,
        )

    def submit_prepared_work(self, work: CoordinatorPreparedWork) -> CoordinatorWorkResult:
        span = work.span
        preparation = work.preparation
        empty_reason = work.empty_reason
        if empty_reason is not None:
            submitted = self._submit_empty(span)
            identity_status = "empty_span"
        elif preparation is None:
            raise LiveCoordinatorError("prepared work carries neither an identity preparation nor an empty span.")
        elif preparation.status == "prepared":
            result = CanonicalResult(
                span_id=span.id,
                epoch=span.epoch,
                start_sample=span.start_sample,
                end_sample=span.end_sample,
                transcript=preparation.relabeled_transcript,
                identity_preparation=preparation,
            )
            submitted = self.session.submit_prepared_canonical(result)
            identity_status = preparation.status
        else:
            # The span published its words without a speaker. Identity answered a question
            # about *who*, and every answer it can give -- an abstention on ambiguity or on
            # speaker capacity, a preparer that could not obtain evidence -- leaves the
            # words intact and the meeting able to continue. Only the claim is dropped, and
            # the label is rebuilt from the decoder's own transcript rather than taken from
            # the preparation, so a preparer cannot publish local labels as canonical by
            # leaving them in a field it did not relabel.
            identity_status = preparation.status
            unattributed = unattributed_transcript(work.transcript, sample_count=span.sample_count)
            empty_reason = _empty_transcript_reason(unattributed)
            if empty_reason is not None:
                submitted = self._submit_empty(span)
            else:
                submitted = self.session.submit_unlabeled_canonical(
                    span_id=span.id,
                    epoch=span.epoch,
                    start_sample=span.start_sample,
                    end_sample=span.end_sample,
                    transcript=unattributed,
                )
        snapshot = self.session.snapshot()
        if submitted:
            self._pcm.prune_before(snapshot.committed_samples)
        measurement = _canonical_decode_measurement(span, work.decode_elapsed_sec)
        return CoordinatorWorkResult(
            span_id=span.id,
            submitted=submitted,
            identity_status=identity_status,
            committed_samples=snapshot.committed_samples,
            canonical_decode_elapsed_sec=measurement["canonical_decode_elapsed_sec"],
            frozen_span_sample_count=measurement["frozen_span_sample_count"],
            frozen_span_duration_sec=measurement["frozen_span_duration_sec"],
            canonical_decode_rtf=measurement["canonical_decode_rtf"],
            empty_reason=empty_reason,
        )

    def _submit_empty(self, span: FrozenSpan) -> bool:
        return self.session.submit_empty_canonical(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
        )

    def process_work_item(self, item: ArbiterWorkItem) -> CoordinatorWorkResult:
        work = self.capture_work_item(item)
        prepared = self.prepare_work_item(work)
        return self.submit_prepared_work(prepared)

    def _observe_endpoint(
        self,
        observations: tuple[SpeechObservation, ...],
        start_sample: int,
        end_sample: int,
    ) -> tuple[EndpointSpan, ...]:
        expected = start_sample
        spans: list[EndpointSpan] = []
        if not observations:
            raise LiveCoordinatorError("speech provider emitted no observation for accepted PCM.")
        for observation in observations:
            if observation.start_sample != expected:
                raise LiveCoordinatorError("speech observations must cover accepted PCM without gaps.")
            if observation.end_sample > end_sample:
                raise LiveCoordinatorError("speech observation exceeds accepted PCM.")
            spans.extend(self.endpoint_policy.observe(observation))
            expected = observation.end_sample
        if expected != end_sample:
            raise LiveCoordinatorError("speech observations did not cover accepted PCM.")
        return tuple(spans)

    def _freeze_and_queue(self, endpoint_spans: tuple[EndpointSpan, ...]) -> tuple[int, ...]:
        frozen = tuple(self.session.freeze_until(span.end_sample, reason=span.reason) for span in endpoint_spans)
        return tuple(self._queue_canonical(span) for span in frozen)

    def _queue_canonical(self, span: FrozenSpan) -> int:
        admission = self.arbiter.submit_live_canonical(
            key=f"{self.session_key}:span-{span.id}",
            payload=CanonicalWork(session_key=self.session_key, span=span),
        )
        assert admission.item_id is not None
        return admission.item_id


@dataclass(frozen=True, slots=True)
class _PcmSlice:
    start_sample: int
    end_sample: int
    pcm: bytes


class _PcmRetention:
    def __init__(self):
        self._slices: deque[_PcmSlice] = deque()

    def append(self, start_sample: int, end_sample: int, pcm: bytes) -> None:
        if end_sample <= start_sample:
            raise LiveCoordinatorError("PCM slice must advance.")
        if len(pcm) != (end_sample - start_sample) * PCM16_BYTES_PER_SAMPLE:
            raise LiveCoordinatorError("PCM slice length does not match sample range.")
        if self._slices and self._slices[-1].end_sample != start_sample:
            raise LiveCoordinatorError("PCM slices must be retained in order without gaps.")
        self._slices.append(_PcmSlice(start_sample, end_sample, pcm))

    def extract(self, start_sample: int, end_sample: int) -> bytes:
        if end_sample <= start_sample:
            raise LiveCoordinatorError("requested PCM range must advance.")
        pieces: list[bytes] = []
        cursor = start_sample
        for item in self._slices:
            if item.end_sample <= cursor:
                continue
            if item.start_sample > cursor:
                break
            take_start = max(cursor, item.start_sample)
            take_end = min(end_sample, item.end_sample)
            if take_end > take_start:
                byte_start = (take_start - item.start_sample) * PCM16_BYTES_PER_SAMPLE
                byte_end = (take_end - item.start_sample) * PCM16_BYTES_PER_SAMPLE
                pieces.append(item.pcm[byte_start:byte_end])
                cursor = take_end
            if cursor == end_sample:
                return b"".join(pieces)
        raise LiveCoordinatorError("requested frozen PCM is no longer retained.")

    def prune_before(self, sample: int) -> None:
        while self._slices and self._slices[0].end_sample <= sample:
            self._slices.popleft()
        if self._slices and self._slices[0].start_sample < sample:
            item = self._slices.popleft()
            byte_offset = (sample - item.start_sample) * PCM16_BYTES_PER_SAMPLE
            self._slices.appendleft(_PcmSlice(sample, item.end_sample, item.pcm[byte_offset:]))


def _empty_transcript_reason(transcript: str) -> str | None:
    """Name the condition under which a span has nothing to publish, or `None`.

    A span the decoder cannot parse is committed empty, never made terminal. This rule is
    stated on the transcript rather than on an exception type so it holds for every decoder:
    one that raises the typed empty outcome and one that simply returns nothing get the same
    answer. A decoder that *failed* raises instead, and that stays terminal.
    """

    if not transcript.strip():
        return "decoder_returned_no_transcript"
    if not parse_transcript(transcript):
        return "decoder_returned_unparseable_transcript"
    return None


def _canonical_decode_measurement(span: FrozenSpan, elapsed_sec: float | None) -> dict[str, float | int | None]:
    sample_count = span.sample_count
    if sample_count <= 0:
        raise LiveCoordinatorError("canonical span sample count must be positive.")
    duration_sec = sample_count / float(LIVE_SAMPLE_RATE)
    if elapsed_sec is None:
        rtf = None
    else:
        elapsed_sec = float(elapsed_sec)
        if not math.isfinite(elapsed_sec) or elapsed_sec < 0:
            raise LiveCoordinatorError("canonical decode elapsed_sec must be finite and non-negative.")
        rtf = elapsed_sec / duration_sec
    return {
        "canonical_decode_elapsed_sec": elapsed_sec,
        "frozen_span_sample_count": sample_count,
        "frozen_span_duration_sec": duration_sec,
        "canonical_decode_rtf": rtf,
    }
