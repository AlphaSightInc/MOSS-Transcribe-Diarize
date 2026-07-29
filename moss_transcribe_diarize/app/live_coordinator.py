from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Protocol

from moss_transcribe_diarize.transcript_parser import parse_transcript

from .live_adapters import (
    BoundedWavInference,
    InferenceTranscript,
    LiveProviderError,
    LiveProviderTransientError,
    trustworthy_duration_sec,
)
from .live_arbiter import ArbiterWorkItem, InferenceArbiter
from .live_endpoint import EndpointPolicy, EndpointPolicyError, EndpointSpan, SpeechObservation
from .live_identity import unattributed_transcript
from .live_identity_sweep import SweepRevision
from .live_session import (
    AudioFrame,
    CanonicalResult,
    CanonicalSubmission,
    FrozenSpan,
    LIVE_SAMPLE_RATE,
    LabelRevision,
    LabelRevisionOutcome,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    LiveSession,
    PCM16_BYTES_PER_SAMPLE,
)
from .live_span_bounds import span_segments


class LiveCoordinatorError(RuntimeError):
    pass


_DECODE_LOG = logging.getLogger("moss_transcribe_diarize.live.decode")


# How many times one span's audio is offered to a decoder that did not answer. The bytes are
# identical on every attempt and nothing is committed until one of them answers, so a retry
# can only add an answer -- it can never publish a span twice. Two attempts, with no delay
# between them: what this recovers is a dropped connection, which the next request
# re-establishes, and a decoder that is genuinely gone refuses immediately rather than
# spending the meeting's real time on a wait.
DECODE_ATTEMPTS_PER_SPAN = 2

# How many *consecutive* spans may go unanswered before the decoder is called gone. A blip
# costs its own spans and nothing else, because the count resets the moment one span decodes.
# An outage that never ends is not transient however it started, and a meeting that publishes
# nothing but empty spans has to say so rather than read as a room where nobody spoke. Three
# spans is at most ~7.5 s of live audio at the 2.5 s span cap.
MAX_CONSECUTIVE_UNANSWERED_SPANS = 3

# The `empty_reason` a span carries when the decoder never answered for it. It names the
# condition in the `canonical_processed` event, so a degraded span is distinguishable from a
# span in which nothing was said.
DECODER_DID_NOT_ANSWER = "decoder_did_not_answer"


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


class LiveIdentityReviser(Protocol):
    """The half of an identity stack that can change its mind about a published span.

    Optional, and asked for by name rather than required: an identity stack with no album
    has no retained evidence and therefore nothing to revise, which is every stack this
    project shipped before ADR-0002 step 3 and every stack a test builds by hand.
    """

    def take_identity_revision(self) -> SweepRevision | None:
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
    # What the decode was allowed to generate and whether it used all of it. A capped span
    # is committed with fewer words rather than abandoned, so the truncation is only
    # visible if it is reported: an 8 s runaway and a 1 s capped span look the same in the
    # transcript and mean opposite things about the decoder.
    canonical_decode_token_cap: int | None = None
    canonical_decode_capped: bool = False
    empty_reason: str | None = None
    # The two words a reader needs when a span did not publish the way it was meant to.
    # `identity_reason` is the preparer's own answer -- it is the only thing that tells an
    # abstention on ambiguous evidence apart from an evidence provider that was not there
    # -- and `submission_refusal` is the session's. Both used to die inside the process.
    identity_reason: str | None = None
    submission_refusal: str | None = None
    # What a retrospective sweep changed about *earlier* spans while this one was being
    # published. Zero on every span of a meeting the identity layer never corrected, and
    # `identity_revision_refusals` names -- rather than swallows -- every correction that did
    # not land, because a rewriter nobody can audit is worse than no rewriter.
    identity_revision_version: int = 0
    identity_revision_spans: int = 0
    identity_revision_units: int = 0
    identity_revision_merges: int = 0
    identity_revision_refusals: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class CoordinatorWorkInput:
    span: FrozenSpan
    pcm: bytes
    base_snapshot: LiveIdentitySnapshot


@dataclass(frozen=True, slots=True)
class _AppliedRevision:
    outcome: LabelRevisionOutcome
    merges: int


@dataclass(frozen=True, slots=True)
class CoordinatorPreparedWork:
    span: FrozenSpan
    transcript: str
    preparation: LiveIdentityPreparation | None
    decode_elapsed_sec: float | None = None
    decode_token_cap: int | None = None
    decode_capped: bool = False
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
        self._consecutive_unanswered_spans = 0

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
        try:
            inferred = self._decode(span, pcm)
        except LiveProviderTransientError as exc:
            # The decoder blinked. The meeting does not end for it; this span does.
            return self._unanswered_span(span, exc)
        self._consecutive_unanswered_spans = 0
        transcript = inferred.transcript
        empty_reason = _empty_transcript_reason(transcript)
        if empty_reason is not None:
            # No identity work: there is no transcript to relabel and no speaker to link.
            return CoordinatorPreparedWork(
                span=span,
                transcript="",
                preparation=None,
                decode_elapsed_sec=inferred.elapsed_sec,
                decode_token_cap=inferred.token_cap,
                decode_capped=inferred.capped,
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
            decode_token_cap=inferred.token_cap,
            decode_capped=inferred.capped,
        )

    def submit_prepared_work(self, work: CoordinatorPreparedWork) -> CoordinatorWorkResult:
        span = work.span
        preparation = work.preparation
        empty_reason = work.empty_reason
        if empty_reason is not None:
            submission = self._submit_empty(span)
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
                local_speakers=self._local_speakers(span, work.transcript),
            )
            submission = self.session.submit_prepared_canonical(result)
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
                submission = self._submit_empty(span)
            else:
                submission = self.session.submit_unlabeled_canonical(
                    span_id=span.id,
                    epoch=span.epoch,
                    start_sample=span.start_sample,
                    end_sample=span.end_sample,
                    transcript=unattributed,
                    local_speakers=self._local_speakers(span, work.transcript),
                )
        snapshot = self.session.snapshot()
        if submission.submitted:
            self._pcm.prune_before(snapshot.committed_samples)
        revision = self._publish_identity_revision()
        measurement = _canonical_decode_measurement(span, work.decode_elapsed_sec)
        return CoordinatorWorkResult(
            span_id=span.id,
            submitted=submission.submitted,
            identity_status=identity_status,
            committed_samples=snapshot.committed_samples,
            canonical_decode_elapsed_sec=measurement["canonical_decode_elapsed_sec"],
            frozen_span_sample_count=measurement["frozen_span_sample_count"],
            frozen_span_duration_sec=measurement["frozen_span_duration_sec"],
            canonical_decode_rtf=measurement["canonical_decode_rtf"],
            canonical_decode_token_cap=work.decode_token_cap,
            canonical_decode_capped=work.decode_capped,
            empty_reason=empty_reason,
            identity_reason=None if preparation is None else preparation.reason,
            submission_refusal=submission.refusal,
            identity_revision_version=revision.outcome.version,
            identity_revision_spans=revision.outcome.revised_spans,
            identity_revision_units=revision.outcome.revised_units,
            identity_revision_merges=revision.merges,
            identity_revision_refusals=revision.outcome.refusals,
        )

    def _local_speakers(self, span: FrozenSpan, transcript: str) -> tuple[str, ...]:
        """The decoder's own speaker for each segment this span publishes, in order.

        Read from the decoder's transcript rather than from the published one because that is
        the only place a *local* speaker still exists: a prepared span publishes canonical
        labels and an abstained span publishes none at all. Every published rendering --
        `_render_transcript` and `unattributed_transcript` alike -- walks `span_segments` of
        this same string, so position `i` here is position `i` there by construction, and the
        session refuses a track whose length disagrees rather than trusting that sentence.
        """

        return tuple(
            segment.speaker for segment in span_segments(transcript, sample_count=span.sample_count)
        )

    def _publish_identity_revision(self) -> _AppliedRevision:
        """Apply any retrospective correction to the transcript a reader is being shown.

        The coordinator is where this belongs because it is the only object that holds both
        halves: the identity stack, which knows a past minute was labelled wrong, and the
        session, which owns the words that were published. It runs *after* the span above is
        published -- the meeting advances first, then the corrections land -- and it is
        unconditional, because a correction is about earlier spans and is no less true when
        the current one was refused.
        """

        take = getattr(self.identity_preparer, "take_identity_revision", None)
        revision = None if take is None else take()
        corrections = () if revision is None else revision.corrections
        # An empty revision is passed through rather than skipped: `revise_labels` answers a
        # meeting that has nothing to correct with the version it already has, so the reported
        # number is the session's own state on every span, not a zero standing in for it.
        outcome = self.session.revise_labels(
            tuple(
                LabelRevision(
                    span_id=correction.span_id,
                    local_speaker=correction.local_speaker,
                    canonical_speaker=correction.canonical_speaker,
                )
                for correction in corrections
            )
        )
        return _AppliedRevision(outcome=outcome, merges=0 if revision is None else len(revision.merges))

    def _decode(self, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        attempt = 1
        while True:
            try:
                return self.decoder.transcribe_pcm(span=span, pcm=pcm)
            except LiveProviderTransientError:
                if attempt >= DECODE_ATTEMPTS_PER_SPAN:
                    raise
                attempt += 1

    def _unanswered_span(self, span: FrozenSpan, exc: LiveProviderTransientError) -> CoordinatorPreparedWork:
        """Degrade one span, or -- once the outage has outlived transience -- end the meeting.

        A span nobody could decode is published empty and named, exactly as a span in which
        nothing was said is: the audio stays accounted for, the committed prefix advances,
        and the meeting continues past a decoder that blinked. What must not happen is a
        dead decoder rendering as a blank meeting, so the *consecutive* count is the line
        between the two. It is reset by any span that decodes, so an occasional outage never
        accumulates into a terminal one across a long meeting.
        """

        self._consecutive_unanswered_spans += 1
        if self._consecutive_unanswered_spans >= MAX_CONSECUTIVE_UNANSWERED_SPANS:
            raise LiveProviderError(
                "canonical decode did not answer for "
                f"{self._consecutive_unanswered_spans} consecutive spans: {exc}",
                # The count is the fact that ended the meeting, so it travels as a number
                # rather than only inside the sentence; the span's own detail says what the
                # decoder was doing when it stopped answering.
                detail={
                    **exc.detail,
                    "span_id": span.id,
                    "consecutive_unanswered_spans": self._consecutive_unanswered_spans,
                },
            ) from exc
        return CoordinatorPreparedWork(
            span=span,
            transcript="",
            preparation=None,
            empty_reason=DECODER_DID_NOT_ANSWER,
        )

    def _submit_empty(self, span: FrozenSpan) -> CanonicalSubmission:
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
    answer. A decoder that *failed* raises instead: a permanent failure stays terminal, and a
    transient one is answered by `_unanswered_span`, which names its own empty reason.
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
    # The same rule the adapter states, applied where every span passes: a duration that
    # cannot be trusted is reported as unknown -- elapsed and RTF both null on
    # `canonical_processed` -- and the span still commits. It is logged rather than only
    # nulled, because a measurement that silently disappears is how four cycles were spent
    # not knowing why a meeting stopped.
    trustworthy = trustworthy_duration_sec(elapsed_sec)
    if elapsed_sec is not None and trustworthy is None:
        _DECODE_LOG.warning(
            "live canonical decode timing untrustworthy: span_id=%s field=elapsed_sec value=%r",
            span.id,
            elapsed_sec,
        )
    elapsed_sec = trustworthy
    rtf = None if elapsed_sec is None else elapsed_sec / duration_sec
    return {
        "canonical_decode_elapsed_sec": elapsed_sec,
        "frozen_span_sample_count": sample_count,
        "frozen_span_duration_sec": duration_sec,
        "canonical_decode_rtf": rtf,
    }
