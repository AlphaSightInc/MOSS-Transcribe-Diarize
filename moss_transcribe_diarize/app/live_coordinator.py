from __future__ import annotations

import logging
from collections import deque
from copy import deepcopy
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
from .live_arbiter import ArbiterWorkItem, InferenceArbiter, InferenceArbiterBackpressure
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
from .live_tape import CompleteMixedTape, CompleteMixedTapeAccounting
from .live_transcript_convergence import (
    DEFAULT_ROLLING_GEOMETRY,
    RollingDecodeRequest,
    RollingGeometry,
    RollingStatus,
    RollingTranscriptConverger,
    TerminalDecodePlan,
)
from .transcription_outcome import EmptyTranscriptCause


class LiveCoordinatorError(RuntimeError):
    pass


_DECODE_LOG = logging.getLogger("moss_transcribe_diarize.live.decode")
_IDENTITY_LOG = logging.getLogger("moss_transcribe_diarize.live.identity")


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

# The named refusal a session-end finalize records when the identity stack could not settle
# itself. It travels in the same `identity_revision_refusals` map every other refusal does,
# because "the last sweep never ran" and "the last sweep found nothing to correct" are
# opposite facts that would otherwise both read as zero corrections.
IDENTITY_FINALIZE_FAILED = "identity_finalize_failed"


# The freeze reason a rolling window's decode carries into the decode seam. A window is a
# fixed ten-second cut of already-committed audio, not a VAD freeze, so it is deliberately
# *not* `hard_cap`: the M1 salvage gate reads this name, bounded salvage was measured on
# 2.5 s hard-cap spans (plan §9.1), and extending it to a ten-second witness would be an
# unmeasured policy change. A window whose decode the grammar rejects therefore publishes
# nothing, which is exactly plan §5.2's "rolling failure".
ROLLING_WINDOW_REASON = "rolling_window"

# What the coordinator reports when a rolling decode never got an answer. The base path
# retries a span and then degrades it; a witness is not retried at all, because the audio it
# was going to improve is already published and the next window covers the audio after it.
ROLLING_DECODE_DID_NOT_ANSWER = "rolling_decode_did_not_answer"

# ... and when it answered with a failure the decode seam could not classify. Both names ride
# on the refinement result rather than raising, because ADR-0005's whole point is that the
# second listener may not end the meeting the first one is publishing.
ROLLING_DECODE_FAILED = "rolling_decode_failed"


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
    project shipped before ADR-0002 step 3 and every stack a test builds by hand. Both
    methods arrive together or not at all -- they are the two halves of one collaborator --
    but each is still asked for separately, because a stack that answers one and not the
    other must degrade rather than raise on a teardown path.
    """

    def take_identity_revision(self) -> SweepRevision | None:
        ...

    def finalize_identity(self, *, base_snapshot: LiveIdentitySnapshot) -> None:
        ...


@dataclass(frozen=True, slots=True)
class CanonicalWork:
    session_key: str
    spans: tuple[FrozenSpan, ...]


@dataclass(frozen=True, slots=True)
class RefinementWork:
    """One rolling window, addressed to the session that planned it.

    Shaped like `CanonicalWork` and for its reason: the arbiter is a queue of opaque
    payloads, and a work item that did not name its session could be handed to the wrong
    coordinator by a shared arbiter without anything noticing.
    """

    session_key: str
    request: RollingDecodeRequest


@dataclass(frozen=True, slots=True)
class RollingWindowPlan:
    """One window the converger planned, and what the arbiter did with it.

    `item_id=None` is an admission the arbiter refused. It is reported rather than dropped
    because a refusal from this producer is a defect (the converger plans one window at a
    time and the arbiter allows one per key), and a defect that only increments a private
    counter is a defect nobody can see from a trace -- which is what plan §7.4's
    `rolling_decode_queued` exists to fix.
    """

    item_id: int | None
    window_index: int
    start_sample: int
    end_sample: int

    @property
    def sample_count(self) -> int:
        return self.end_sample - self.start_sample


@dataclass(frozen=True, slots=True)
class RefinementDecode:
    """What came back for one window, and -- if nothing did -- the name for that.

    `outcome` is always an `InferenceTranscript` so the converger is always completed: a
    witness that is never completed holds the converger's one in-flight slot forever and
    rolling stops without saying so.
    """

    request: RollingDecodeRequest
    outcome: InferenceTranscript
    failure: str | None = None


@dataclass(frozen=True, slots=True)
class CoordinatorRefinementResult:
    """What one rolling window did to the surface a reader is shown, and what it cost.

    No transcript text, exactly as `CoordinatorWorkResult` carries none: this is the record
    of a decision (which interval was revised, whether the session accepted it, how far the
    rolling authority now reaches), and plan §7.4's events serialize it.
    """

    window_index: int
    start_sample: int
    end_sample: int
    decode_elapsed_sec: float | None
    decode_failure: str | None
    applied: bool
    refusal: str | None
    revised_segments: int
    text_revision_version: int
    canonical_through_sample: int
    rolling_status: str
    windows_planned: int
    windows_completed: int
    windows_failed: int
    stale_completions: int
    decoded_audio_samples: int
    retained_samples: int
    retained_high_water_samples: int
    admission_refusals: int
    # Whether the window produced a proposal at all. Without it an applied=False result
    # cannot say whether the session refused a revision or there was never one to refuse --
    # two facts that plan §7.4 gives two different events.
    proposed: bool = False
    # The interval the proposal claimed, which is the "owned samples" §7.4 asks a completion
    # event to record. `None` when nothing was proposed; at the selected geometry it equals
    # the window, and a geometry with overlap would not.
    owned_start_sample: int | None = None
    owned_end_sample: int | None = None
    # The rest of §7.4's completion record: what the decoder was allowed to emit, what it
    # emitted, whether it ran out, and the witness's own real-time factor when the elapsed
    # time is trustworthy. The base path reports the same four for a span.
    decode_token_cap: int | None = None
    decode_capped: bool = False
    decode_generated_tokens: int | None = None
    decode_rtf: float | None = None
    # The windows this completion made plannable, if any.
    rolling_windows: tuple[RollingWindowPlan, ...] = ()


@dataclass(frozen=True, slots=True)
class CoordinatorFrameResult:
    accepted_start_sample: int
    accepted_end_sample: int
    endpoint_spans: tuple[EndpointSpan, ...]
    frozen_spans: tuple[FrozenSpan, ...]
    queued_item_ids: tuple[int, ...]
    # Kept apart from `queued_item_ids` on purpose: that field is the canonical batch the
    # frame admitted, and a reader that conflates the two would count a witness as base work.
    rolling_windows: tuple[RollingWindowPlan, ...] = ()


@dataclass(frozen=True, slots=True)
class _StagedFrame:
    frame: AudioFrame
    observations: tuple[SpeechObservation, ...]
    endpoint_spans: tuple[EndpointSpan, ...]


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
    # What the decoder actually emitted for this span. On a span with nothing to publish it is
    # the difference between a model that stayed silent and one that spoke unparseably, which
    # `empty_reason` alone cannot express: both of the silent endings share one reason name.
    canonical_decode_generated_tokens: int | None = None
    empty_reason: str | None = None
    # What the salvage policy decided for a span whose decode the grammar rejected, `None`
    # on every span that never reached it. Reported beside `empty_reason` because the two
    # together are the whole story of an unparseable decode: what came back, and what this
    # build chose to publish for it. Without it a salvaged span is indistinguishable from
    # one the decoder wrote correctly, and a refused one from a span that was never
    # repairable at all.
    canonical_decode_salvage: str | None = None
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
    # What this commit did for the second listener. A base commit is the event that makes a
    # window ownable, so it is where a newly planned window is announced; and `rolling_status`
    # rides here because a converger that stops while planning nothing -- an evicted ring, a
    # failed window -- emits no rolling event of its own, and would otherwise be visible only
    # in the process log.
    rolling_windows: tuple[RollingWindowPlan, ...] = ()
    rolling_status: str | None = None


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
class CoordinatorFinalizeResult:
    """What the meeting's last sweep changed, reported in the same five fields a span is.

    Deliberately the same vocabulary as `CoordinatorWorkResult`'s revision half: the final
    sweep is not a different kind of correction, it is the one that had no next span to
    carry it, so a reducer that already reads a span's revision counts reads this one too.
    """

    identity_revision_version: int = 0
    identity_revision_spans: int = 0
    identity_revision_units: int = 0
    identity_revision_merges: int = 0
    identity_revision_refusals: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class CoordinatorPreparedWork:
    span: FrozenSpan
    transcript: str
    preparation: LiveIdentityPreparation | None
    decode_elapsed_sec: float | None = None
    decode_token_cap: int | None = None
    decode_capped: bool = False
    decode_generated_tokens: int | None = None
    empty_reason: str | None = None
    decode_salvage: str | None = None


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
        rolling_decoder: BoundedWavInference | None = None,
        rolling_geometry: RollingGeometry = DEFAULT_ROLLING_GEOMETRY,
        tape_capacity_bytes: int | None = None,
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
        self._staged_frame: _StagedFrame | None = None
        self._consecutive_unanswered_spans = 0
        # The rolling witness is asked for by name, like the identity reviser above it: a
        # decoder able to hear a whole window is what the second listener needs and the base
        # path does not have, because the deployed span decoder is bounded at the span cap.
        # No decoder, no converger, and the coordinator behaves exactly as it did before E2.
        self.rolling_decoder = rolling_decoder
        self.converger = (
            None
            if rolling_decoder is None
            else RollingTranscriptConverger(epoch=session.epoch, geometry=rolling_geometry)
        )
        self._rolling_admission_refusals = 0
        # The third retention, and the only one that outlives its listener. The base keeps a
        # span until it commits and the witness keeps a bounded ring of the newest window;
        # neither can answer "what did this whole meeting sound like", which is the only
        # question a terminal 150/120 pass asks. Declared by the deployment or absent
        # entirely (ADR-0003 D2), so a service that declares no capacity retains exactly
        # what it retains today and reports terminal convergence unavailable rather than
        # running one over a partial meeting.
        self.tape = (
            None
            if tape_capacity_bytes is None
            else CompleteMixedTape(epoch=session.epoch, capacity_bytes=tape_capacity_bytes)
        )

    def preview_frame_work_items(self, frame: AudioFrame) -> int:
        if self._staged_frame is not None:
            if self._staged_frame.frame != frame:
                raise LiveCoordinatorError("a different frame arrived while canonical admission was staged.")
            return len(self._staged_frame.endpoint_spans)
        snapshot = self.session.snapshot()
        if frame.sequence != snapshot.next_frame_sequence:
            raise ValueError(f"expected frame sequence {snapshot.next_frame_sequence}, got {frame.sequence}.")
        start_sample = snapshot.accepted_samples
        end_sample = start_sample + frame.sample_count
        observations = self.speech_provider.observe(
            frame=frame,
            start_sample=start_sample,
            end_sample=end_sample,
        )
        preview_policy = deepcopy(self.endpoint_policy)
        endpoint_spans = self._observe_endpoint_with_policy(
            preview_policy,
            observations,
            start_sample,
            end_sample,
        )
        self._staged_frame = _StagedFrame(frame, observations, endpoint_spans)
        return len(endpoint_spans)

    def preview_stop_work_items(self) -> int:
        preview_policy = deepcopy(self.endpoint_policy)
        return len(preview_policy.stop())

    def accept_frame(self, frame: AudioFrame) -> CoordinatorFrameResult:
        ack = self.session.accept_frame(frame)
        self._pcm.append(ack.start_sample, ack.end_sample, frame.pcm)
        staged = self._staged_frame
        if staged is not None:
            if staged.frame != frame:
                raise LiveCoordinatorError("accepted frame does not match staged canonical admission.")
            observations = staged.observations
            self._staged_frame = None
        else:
            observations = self.speech_provider.observe(
                frame=frame,
                start_sample=ack.start_sample,
                end_sample=ack.end_sample,
            )
        endpoint_spans = self._observe_endpoint(observations, ack.start_sample, ack.end_sample)
        frozen_spans = tuple(self.session.freeze_until(span.end_sample, reason=span.reason) for span in endpoint_spans)
        queued = self._queue_canonical_batch(frozen_spans)
        # The witness hears the same audio the base does, at the moment the base accepts it.
        # It is retained separately because the two listen over different extents: the base
        # keeps a span until it commits, the witness keeps a bounded ring of the newest
        # window. Planning is gated on committed audio, so this rarely emits a window on its
        # own -- but it can, when a frame arrives after the commit that completed one.
        rolling_windows = self._accept_rolling_pcm(ack.start_sample, frame.pcm)
        if self.tape is not None:
            # Never checked, never raised on: ADR-0003 D5 makes a tape that cannot keep up
            # degrade itself, and a frame acknowledged by the session is published whether
            # or not a terminal pass will ever be possible.
            self.tape.append(start_sample=ack.start_sample, pcm=frame.pcm)
        return CoordinatorFrameResult(
            accepted_start_sample=ack.start_sample,
            accepted_end_sample=ack.end_sample,
            endpoint_spans=endpoint_spans,
            frozen_spans=frozen_spans,
            queued_item_ids=queued,
            rolling_windows=rolling_windows,
        )

    def flush_endpoint(self) -> tuple[int, ...]:
        return self._freeze_and_queue(self.endpoint_policy.flush())

    def reset_endpoint(self) -> tuple[int, ...]:
        return self._freeze_and_queue(self.endpoint_policy.reset())

    def stop_endpoint(self) -> tuple[int, ...]:
        return self._freeze_and_queue(self.endpoint_policy.stop())

    def work_item_span_count(self, item: ArbiterWorkItem) -> int:
        work = self._canonical_work(item)
        return len(work.spans)

    def capture_work_item(self, item: ArbiterWorkItem, *, span_index: int = 0) -> CoordinatorWorkInput:
        work = self._canonical_work(item)
        try:
            span = work.spans[span_index]
        except IndexError as exc:
            raise LiveCoordinatorError("canonical work span index is out of range.") from exc
        pcm = self._pcm.extract(span.start_sample, span.end_sample)
        base_snapshot = self.session.snapshot().identity_snapshot
        return CoordinatorWorkInput(span=span, pcm=pcm, base_snapshot=base_snapshot)

    def _canonical_work(self, item: ArbiterWorkItem) -> CanonicalWork:
        if item.kind != InferenceArbiter.LIVE_CANONICAL or not isinstance(item.payload, CanonicalWork):
            raise LiveCoordinatorError("work item is not live canonical coordinator work.")
        work = item.payload
        if work.session_key != self.session_key:
            raise LiveCoordinatorError("canonical work belongs to a different live session.")
        if not work.spans:
            raise LiveCoordinatorError("canonical work batch must contain at least one span.")
        return work

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
        empty_reason = _decode_empty_reason(inferred)
        if empty_reason is not None:
            # No identity work: there is no transcript to relabel and no speaker to link.
            return CoordinatorPreparedWork(
                span=span,
                transcript="",
                preparation=None,
                decode_elapsed_sec=inferred.elapsed_sec,
                decode_token_cap=inferred.token_cap,
                decode_capped=inferred.capped,
                decode_generated_tokens=_decode_generated_tokens(inferred),
                empty_reason=empty_reason,
                decode_salvage=_decode_salvage(inferred),
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
            decode_generated_tokens=_decode_generated_tokens(inferred),
            decode_salvage=_decode_salvage(inferred),
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
        # A base commit is the event that makes a window ownable: the witness may only revise
        # audio the session has already committed. This is one of the two `observe_base`
        # calls the converger needs; the other is after an applied revision, which is what
        # moves the frontier the next window must start at.
        rolling_windows = self._observe_base_and_queue()
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
            canonical_decode_generated_tokens=work.decode_generated_tokens,
            empty_reason=empty_reason,
            canonical_decode_salvage=work.decode_salvage,
            identity_reason=None if preparation is None else preparation.reason,
            submission_refusal=submission.refusal,
            identity_revision_version=revision.outcome.version,
            identity_revision_spans=revision.outcome.revised_spans,
            identity_revision_units=revision.outcome.revised_units,
            identity_revision_merges=revision.merges,
            identity_revision_refusals=revision.outcome.refusals,
            rolling_windows=rolling_windows,
            rolling_status=self._rolling_status(),
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

    def finalize_identity(self) -> CoordinatorFinalizeResult:
        """Settle the identity stack once the meeting's last span has published.

        ADR-0002's final sweep, and the reason it cannot be a cadence: the cadence is paced
        by the *next* span's start, so the last interval of every meeting is never swept --
        and the accuracy harness (`tests/live_identity_accuracy.py`) measures essentially all
        of the sweep's gain in the sweep that runs once the last span is in.
        Two things therefore happen here, in this order and only this order. The identity
        stack reconciles the meeting's last preparation, because a span's vectors are
        labelled when the *following* span's preparation arrives and the last one has no
        follower; then it sweeps unconditionally. Reversed, that final sweep would propose a
        `labelled` correction for a span the live path had already labelled correctly.

        Whoever ends the meeting calls this after the drain and before the session closes,
        so the stop response carries the corrected transcript. A closed session is revisable
        too (`LiveSession.revise_labels`), so the ordering is a courtesy to a reader rather
        than a constraint.

        **Nothing here is terminal.** A meeting that reached a clean stop has ended
        successfully; an identity layer that cannot settle costs the transcript its last
        correction and nothing else, and says so by name rather than by silence.
        """

        extra: tuple[tuple[str, int], ...] = ()
        finalize = getattr(self.identity_preparer, "finalize_identity", None)
        if finalize is not None:
            try:
                finalize(base_snapshot=self.session.snapshot().identity_snapshot)
            except Exception:
                # Counts and the name only -- a span's words are the meeting, and they are no
                # more loggable at the end of one than they were during it.
                _IDENTITY_LOG.warning("live identity finalize failed", exc_info=True)
                extra = ((IDENTITY_FINALIZE_FAILED, 1),)
        revision = self._publish_identity_revision()
        return CoordinatorFinalizeResult(
            identity_revision_version=revision.outcome.version,
            identity_revision_spans=revision.outcome.revised_spans,
            identity_revision_units=revision.outcome.revised_units,
            identity_revision_merges=revision.merges,
            identity_revision_refusals=_merged_refusals(revision.outcome.refusals, extra),
        )

    def journal_observations(self):
        observations = getattr(self.identity_preparer, "journal_observations", None)
        return () if observations is None else tuple(observations())

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
        result: CoordinatorWorkResult | None = None
        for span_index in range(self.work_item_span_count(item)):
            work = self.capture_work_item(item, span_index=span_index)
            prepared = self.prepare_work_item(work)
            result = self.submit_prepared_work(prepared)
        assert result is not None
        return result

    # ------------------------------------------------------------ the rolling witness

    def capture_refinement_item(self, item: ArbiterWorkItem) -> RollingDecodeRequest | None:
        """The window this work item carries, or `None` if nobody is waiting for it.

        `None` is not an error and is the reason this is a separate step: a witness admitted
        before the meeting stopped can be dispatched after it, and decoding ten seconds of a
        finished meeting to propose a revision the converger will refuse as stale spends GPU
        on nothing. The caller releases it and moves on.
        """

        if item.kind != InferenceArbiter.LIVE_REFINEMENT or not isinstance(item.payload, RefinementWork):
            raise LiveCoordinatorError("work item is not live refinement coordinator work.")
        work = item.payload
        if work.session_key != self.session_key:
            raise LiveCoordinatorError("refinement work belongs to a different live session.")
        converger = self.converger
        if converger is None or converger.accounting().status is not RollingStatus.ROLLING:
            return None
        return work.request

    def decode_refinement(self, request: RollingDecodeRequest) -> RefinementDecode:
        """Hand one window to the decoder, and name a failure instead of raising it.

        Every ending arrives as an `InferenceTranscript`, because the converger must be
        completed whatever happened: a request that is never completed keeps the one
        in-flight slot forever, and rolling would stop with no status saying so. A decode
        that produced nothing publishes nothing and stalls planning -- plan §5.2's rolling
        failure -- which is a strictly better outcome than a second listener ending a meeting
        the first one is publishing correctly.
        """

        if self.rolling_decoder is None:
            raise LiveCoordinatorError("no rolling decoder is configured for this session.")
        span = FrozenSpan(
            id=request.id,
            epoch=request.epoch,
            start_sample=request.start_sample,
            end_sample=request.end_sample,
            reason=ROLLING_WINDOW_REASON,
        )
        try:
            outcome = self.rolling_decoder.transcribe_pcm(span=span, pcm=request.pcm)
        except LiveProviderTransientError:
            return RefinementDecode(
                request=request,
                outcome=InferenceTranscript(transcript=""),
                failure=ROLLING_DECODE_DID_NOT_ANSWER,
            )
        except LiveProviderError:
            return RefinementDecode(
                request=request,
                outcome=InferenceTranscript(transcript=""),
                failure=ROLLING_DECODE_FAILED,
            )
        return RefinementDecode(request=request, outcome=outcome)

    def submit_refinement(
        self, decode: RefinementDecode, item: ArbiterWorkItem
    ) -> CoordinatorRefinementResult:
        """Complete the window, offer what it said to the session, and plan the next one.

        The release comes first, and the order is load-bearing rather than tidy. A witness
        stops being a running MOSS request the moment its answer is back, and the arbiter
        refuses a newer witness while one is *running* for the same key -- so planning the
        next window before saying this one is finished loses that window permanently. It only
        bites when the base is already far enough ahead that the next window is ownable the
        instant this one lands, which is exactly what a replay client or a post-hiccup burst
        produces, and never what an unhurried real-time meeting does.
        """

        converger = self.converger
        if converger is None:
            raise LiveCoordinatorError("no rolling converger is configured for this session.")
        self.release_refinement(item)
        proposal = converger.complete(decode.request.id, decode.outcome)
        applied = False
        refusal: str | None = None
        revised_segments = 0
        if proposal is not None:
            outcome = self.session.apply_text_revision(proposal)
            applied = outcome.applied
            refusal = outcome.refusal
            revised_segments = outcome.revised_segments
        # The second `observe_base`: an applied revision is what advances the frontier the
        # next window must begin at, so without this call the converger never plans again.
        rolling_windows = self._observe_base_and_queue()
        snapshot = self.session.snapshot()
        accounting = converger.accounting()
        elapsed_sec = trustworthy_duration_sec(decode.outcome.elapsed_sec)
        duration_sec = decode.request.sample_count / float(LIVE_SAMPLE_RATE)
        return CoordinatorRefinementResult(
            window_index=decode.request.window_index,
            start_sample=decode.request.start_sample,
            end_sample=decode.request.end_sample,
            decode_elapsed_sec=elapsed_sec,
            decode_failure=decode.failure,
            applied=applied,
            refusal=refusal,
            revised_segments=revised_segments,
            proposed=proposal is not None,
            owned_start_sample=None if proposal is None else proposal.start_sample,
            owned_end_sample=None if proposal is None else proposal.end_sample,
            decode_token_cap=decode.outcome.token_cap,
            decode_capped=decode.outcome.capped,
            decode_generated_tokens=_decode_generated_tokens(decode.outcome),
            decode_rtf=None if elapsed_sec is None or duration_sec <= 0 else elapsed_sec / duration_sec,
            rolling_windows=rolling_windows,
            text_revision_version=snapshot.text_revision_version,
            canonical_through_sample=snapshot.canonical_through_sample,
            rolling_status=accounting.status.value,
            windows_planned=accounting.windows_planned,
            windows_completed=accounting.windows_completed,
            windows_failed=accounting.windows_failed,
            stale_completions=accounting.stale_completions,
            decoded_audio_samples=accounting.decoded_audio_samples,
            retained_samples=accounting.retained_samples,
            retained_high_water_samples=accounting.retained_high_water_samples,
            admission_refusals=self._rolling_admission_refusals,
        )

    def release_refinement(self, item: ArbiterWorkItem) -> bool:
        """Tell the arbiter this witness is no longer a running MOSS request.

        Owed for every dispatched item, on every path including a failed one: the coalesce
        key stays blocked until its own release arrives, so a skipped release silently ends
        rolling for the session. Idempotent by construction -- a second call for the same
        item answers `False` and changes nothing -- so a caller may release at the natural
        moment *and* keep a release in its teardown without the two colliding.
        """

        return self.arbiter.release_live_refinement(item_id=item.id)

    def stop_rolling(self) -> TerminalDecodePlan | None:
        """End rolling convergence and state what the terminal pass inherits (plan §6 M6).

        Called once the meeting has stopped accepting audio. A window still in flight is not
        waited for -- it completes into a converger that is no longer expecting it and is
        refused as a stale result, changing nothing.

        A converger that already ended answers with the same plan rather than with nothing:
        rolling can die mid-meeting (a witness defect stops it and keeps the meeting going),
        and the terminal pass inherits the meeting either way. The converger owns that
        idempotence, so this stays one call.
        """

        converger = self.converger
        if converger is None:
            return None
        return converger.stop(self.session.snapshot().accepted_samples)

    def rolling_accounting(self):
        """The converger's own counters, or `None` when no witness is configured."""

        return None if self.converger is None else self.converger.accounting()

    def tape_accounting(self) -> CompleteMixedTapeAccounting | None:
        """What the complete tape holds, against what the session accepted.

        Asked against `accepted_samples` rather than against the tape's own count, because
        the question a terminal pass has is not "how much did you keep" but "did you keep
        the meeting" -- and the difference between those two is exactly the gap manifest.
        """

        if self.tape is None:
            return None
        return self.tape.accounting(through_sample=self.session.snapshot().accepted_samples)

    def release_tape(self) -> CompleteMixedTapeAccounting | None:
        """Drop the meeting's audio and keep its accounting (ADR-0003 D3's zero TTL).

        Reported *after* the release, on purpose: everything that makes the tape checkable
        -- its sample count, its digest, its byte high-water and its gap manifest -- outlives
        the samples, so the answer carries `retained_bytes = 0` and is itself the evidence
        that no tape survived the meeting.
        """

        if self.tape is None:
            return None
        self.tape.release()
        return self.tape_accounting()

    def _rolling_status(self) -> str | None:
        converger = self.converger
        return None if converger is None else converger.accounting().status.value

    def _accept_rolling_pcm(self, start_sample: int, pcm: bytes) -> tuple[RollingWindowPlan, ...]:
        converger = self.converger
        if converger is None or converger.accounting().status is not RollingStatus.ROLLING:
            return ()
        return self._queue_refinement(converger.accept_pcm(start_sample, pcm))

    def _observe_base_and_queue(self) -> tuple[RollingWindowPlan, ...]:
        converger = self.converger
        if converger is None or converger.accounting().status is not RollingStatus.ROLLING:
            return ()
        return self._queue_refinement(converger.observe_base(self.session.snapshot()))

    def _queue_refinement(
        self, requests: tuple[RollingDecodeRequest, ...]
    ) -> tuple[RollingWindowPlan, ...]:
        """Admit each planned window under a key that names this session, not just its epoch.

        The converger emits `rolling:<epoch>` and every session starts at epoch 0, so the key
        it produces identifies a session only as long as no two sessions share an arbiter.
        The session key is what actually distinguishes them, and it is held here.

        A refusal cannot happen from this producer -- the converger plans one window at a
        time and the arbiter allows one per key -- so it is counted rather than raised: the
        two enforcers of the same rule disagreeing is a defect, and a defect in the second
        listener may not end the meeting the first one is publishing. Rolling simply stops,
        because the converger keeps holding the in-flight slot of the window that was lost.
        """

        plans: list[RollingWindowPlan] = []
        for request in requests:
            admission = self.arbiter.submit_live_refinement(
                coalesce_key=f"{self.session_key}:{request.coalesce_key}",
                payload=RefinementWork(session_key=self.session_key, request=request),
            )
            if admission.item_id is None:
                self._rolling_admission_refusals += 1
            plans.append(
                RollingWindowPlan(
                    item_id=admission.item_id,
                    window_index=request.window_index,
                    start_sample=request.start_sample,
                    end_sample=request.end_sample,
                )
            )
        return tuple(plans)

    def _observe_endpoint(
        self,
        observations: tuple[SpeechObservation, ...],
        start_sample: int,
        end_sample: int,
    ) -> tuple[EndpointSpan, ...]:
        return self._observe_endpoint_with_policy(
            self.endpoint_policy,
            observations,
            start_sample,
            end_sample,
        )

    @staticmethod
    def _observe_endpoint_with_policy(
        endpoint_policy: EndpointPolicy,
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
            spans.extend(endpoint_policy.observe(observation))
            expected = observation.end_sample
        if expected != end_sample:
            raise LiveCoordinatorError("speech observations did not cover accepted PCM.")
        return tuple(spans)

    def _freeze_and_queue(self, endpoint_spans: tuple[EndpointSpan, ...]) -> tuple[int, ...]:
        frozen = tuple(self.session.freeze_until(span.end_sample, reason=span.reason) for span in endpoint_spans)
        return self._queue_canonical_batch(frozen)

    def _queue_canonical_batch(self, spans: tuple[FrozenSpan, ...]) -> tuple[int, ...]:
        if not spans:
            return ()
        admission = self.arbiter.submit_live_canonical(
            key=f"{self.session_key}:spans-{spans[0].id}-{spans[-1].id}",
            payload=CanonicalWork(session_key=self.session_key, spans=spans),
            weight=len(spans),
        )
        assert admission.item_id is not None
        return (admission.item_id,)


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


def _merged_refusals(
    *groups: tuple[tuple[str, int], ...],
) -> tuple[tuple[str, int], ...]:
    """One sorted count per refusal name, summed across the sources that reported it.

    The session names why a correction did not land and the coordinator names why the
    correction never arrived; both are refusals of the same request, and a reader that had
    to know which layer answered would be reading an implementation detail.
    """

    counts: dict[str, int] = {}
    for group in groups:
        for name, count in group:
            counts[name] = counts.get(name, 0) + int(count)
    return tuple(sorted(counts.items()))


# What the trace calls each observed cause. Two causes share one name on purpose: a decoder
# that emitted no tokens and one that emitted only whitespace both returned no transcript, and
# `canonical_decode_generated_tokens` on the same event is what tells those two apart. The
# third is a different fact and has always had its own name -- it was simply unreachable while
# the adapter flattened every empty outcome into "".
_EMPTY_REASON_BY_CAUSE: dict[EmptyTranscriptCause, str] = {
    EmptyTranscriptCause.NO_GENERATED_TOKENS: "decoder_returned_no_transcript",
    EmptyTranscriptCause.EMPTY_TEXT: "decoder_returned_no_transcript",
    EmptyTranscriptCause.UNPARSEABLE_TEXT: "decoder_returned_unparseable_transcript",
}


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


def _decode_empty_reason(inferred: InferenceTranscript) -> str | None:
    """The same question asked of a decode rather than of a string.

    A decoder that reports *why* it had nothing is believed over the text it returned, because
    the text it returned is "" for all three reasons. A decoder that reports nothing is read
    the old way, off its transcript -- so the answer is the same for a scripted adapter, a
    replayed session, and the deployed runner. `RunnerBoundedWavInference` is not the only
    implementation of `BoundedWavInference`, so the fields it adds are read as optional facts,
    exactly as the adapter itself reads a runner's result.
    """

    cause = getattr(inferred, "empty_cause", None)
    if cause is not None:
        return _EMPTY_REASON_BY_CAUSE[cause]
    return _empty_transcript_reason(inferred.transcript)


def _decode_salvage(inferred: InferenceTranscript) -> str | None:
    """The salvage policy's decision for this decode, or `None` from a decoder that had none.

    Read as an optional fact for the same reason `empty_cause` is: `RunnerBoundedWavInference`
    is not the only `BoundedWavInference`, and a scripted or replayed decoder that returns its
    transcript directly never consults the policy at all.
    """

    disposition = getattr(inferred, "salvage_disposition", None)
    return None if disposition is None else disposition.value


def _decode_generated_tokens(inferred: InferenceTranscript) -> int | None:
    """How many tokens the decode emitted, or `None` from a decoder that does not say.

    Reported rather than assumed: on a span that published nothing it is what separates a
    decode that emitted no tokens at all from one that emitted words the parser rejected --
    two facts that share the trace name `decoder_returned_no_transcript` until the count is
    read beside it.
    """

    tokens = getattr(inferred, "generated_tokens", None)
    return None if tokens is None else int(tokens)


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
