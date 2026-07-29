from __future__ import annotations

import asyncio
import hashlib
import json
from collections import deque
from dataclasses import dataclass, replace
from typing import Any, Sequence

from .live_span_bounds import LIVE_SAMPLE_RATE, render_segments, span_segments


PCM16_BYTES_PER_SAMPLE = 2

# The speaker label a span carries when the session never established who spoke it. The
# wire grammar admits only `S` followed by digits, and canonical display labels are
# `S{index + 1:02d}`, so this marker is the one such token a canonical mapping can never
# produce. It exists because the alternative to publishing an honest "nobody attributed"
# is publishing the decoder's *local* labels as if they were canonical -- `S01` in one span
# and `S01` in the next are not the same person until identity says so.
UNATTRIBUTED_SPEAKER = "S00"


def display_speaker_label(canonical_speaker: str, canonical_speakers: Sequence[str]) -> str:
    """The `Sxx` token a canonical speaker is published as.

    One rule, in one place, because two readers now depend on it: the identity preparer
    writes the label when a span is first published, and `revise_labels` rewrites it when a
    retrospective sweep moves that speech onto a different speaker. The mapping is positional
    and the canonical list only ever grows by appending, which is what makes a label written
    in minute one still name the same speaker in minute seventeen.

    Raises `ValueError` for a speaker the session has never established; the caller decides
    what that means, and both callers refuse rather than invent a label.
    """

    return f"S{tuple(canonical_speakers).index(canonical_speaker) + 1:02d}"


class LiveSessionError(RuntimeError):
    pass


class LiveSessionBackpressure(LiveSessionError):
    pass


class LiveSessionClosed(LiveSessionError):
    pass


class LiveSessionFailed(LiveSessionError):
    pass


@dataclass(frozen=True, slots=True)
class AudioFrame:
    sequence: int
    pcm: bytes
    sample_count: int
    sample_rate: int = LIVE_SAMPLE_RATE


@dataclass(frozen=True, slots=True)
class FrameAck:
    sequence: int
    start_sample: int
    end_sample: int
    accepted_samples: int
    retained_samples: int
    frozen_span_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class FrozenSpan:
    id: int
    epoch: int
    start_sample: int
    end_sample: int
    reason: str

    @property
    def sample_count(self) -> int:
        return self.end_sample - self.start_sample


@dataclass(frozen=True, slots=True)
class LiveIdentitySnapshot:
    version: int = 0
    canonical_speakers: tuple[str, ...] = ()
    diagnostics: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class LiveIdentityPreparation:
    span_id: int
    epoch: int
    start_sample: int
    end_sample: int
    base_snapshot_version: int
    proposed_snapshot: LiveIdentitySnapshot
    relabeled_transcript: str
    status: str = "prepared"
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalResult:
    span_id: int
    epoch: int
    start_sample: int
    end_sample: int
    transcript: str
    identity_confirmed: bool = True
    identity_preparation: LiveIdentityPreparation | None = None
    # The decoder's local speaker per published segment, in segment order -- the address a
    # later correction is written to. Empty means "this span is not revisable", which is the
    # honest state for every caller that does not carry the decoder's own transcript.
    local_speakers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CanonicalSubmission:
    """Whether a canonical submission published, and -- when it did not -- the word for why.

    Every refusal on this path used to be a bare `False`. Six distinct conditions arrived
    at the runtime as one code, so a session that stopped on a stale preparation and one
    that stopped on a span-order violation were indistinguishable from outside the
    process; that is why H4d had to build a host-side probe to learn a single word. The
    invariant below makes the silent refusal unwritable: a submission that did not publish
    must name the condition that refused it.
    """

    submitted: bool
    refusal: str | None = None

    def __post_init__(self) -> None:
        if self.submitted and self.refusal is not None:
            raise ValueError("a published canonical submission has no refusal.")
        if not self.submitted and not self.refusal:
            raise ValueError("a refused canonical submission must name its refusal.")


_PUBLISHED = CanonicalSubmission(submitted=True)


def _refused(refusal: str) -> CanonicalSubmission:
    return CanonicalSubmission(submitted=False, refusal=refusal)


@dataclass(frozen=True, slots=True)
class _CanonicalValidationError:
    refusal: str
    failure_reason: str
    exception_reason: str


@dataclass(frozen=True, slots=True)
class CanonicalCommit:
    span_id: int
    start_sample: int
    end_sample: int
    transcript: str
    prefix_hash: str
    identity_snapshot_version: int
    # What this span's words are labelled with *now*, when a retrospective sweep has moved
    # any of them onto a different speaker; `None` while the span still reads as committed.
    # It is a second field rather than an edit to `transcript` because `prefix_hash` chains
    # the committed transcripts: the chain records what was **said**, and a living document's
    # corrections are a different fact about the same words. A reader is shown this when it
    # is present, and the hash a client verifies is unaffected by every correction.
    revised_transcript: str | None = None


@dataclass(frozen=True, slots=True)
class LabelRevision:
    """One unit's corrected speaker: a span, a local speaker inside it, and who it now is.

    The unit of a correction is `(span, local speaker)` and not `(span, displayed label)`
    because an unattributed span displays `S00` for every one of its local speakers -- and an
    abstained span is precisely the one a later album has the most to say about. The session
    is deliberately told nothing about *why*: a sweep's reasoning belongs to the sweep, and
    what arrives here is only the claim it is willing to publish.
    """

    span_id: int
    local_speaker: str
    canonical_speaker: str


@dataclass(frozen=True, slots=True)
class LabelRevisionOutcome:
    """What one `revise_labels` call changed, and -- by name -- what it declined to change."""

    version: int
    revised_spans: int
    revised_units: int
    refusals: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class ProvisionalSuffix:
    generation: int
    start_sample: int
    end_sample: int
    transcript: str


@dataclass(frozen=True, slots=True)
class LiveSnapshot:
    status: str
    epoch: int
    version: int
    accepted_samples: int
    accounted_samples: int
    retained_samples: int
    committed_samples: int
    committed_prefix_hash: str
    identity_snapshot: LiveIdentitySnapshot
    committed: tuple[CanonicalCommit, ...]
    provisional: ProvisionalSuffix | None
    next_frame_sequence: int
    frozen_until_sample: int
    pending_span_ids: tuple[int, ...]
    failure_reason: str | None = None
    # How many revisions have changed a label a reader had already been shown. Zero for the
    # whole of a meeting whose live labels were never corrected, so a client can tell "this
    # transcript is settled" from "this transcript is still being repaired" without diffing.
    label_revision_version: int = 0


@dataclass(frozen=True, slots=True)
class _RetainedFrame:
    sequence: int
    start_sample: int
    end_sample: int


class LiveSession:
    """Default-off live session state machine for ordered 16 kHz PCM.

    The session records a partition; it does not decide one. Every span boundary arrives
    through `freeze_until`, which the coordinator calls with what the endpoint policy
    emitted, so the policy is the single authority for where a span ends. A session that
    also closed spans on its own would fight that authority — it froze its own `hard_cap`
    span inside `accept_frame`, before any observation existed, and the policy's identical
    span was then refused as "frozen span end must advance"; worse, the span the session
    froze by itself was never queued for decode, so that audio was never transcribed.
    The only boundary the session still draws is `stop`'s tail flush, which fires solely
    when nothing else closed the tail and therefore cannot collide with anything.
    """

    def __init__(
        self,
        *,
        max_retained_samples: int,
        session_epoch: int = 0,
    ):
        if max_retained_samples <= 0:
            raise ValueError("max_retained_samples must be positive.")
        self.max_retained_samples = int(max_retained_samples)
        self._epoch = int(session_epoch)
        self._version = 0
        self._status = "active"
        self._failure_reason: str | None = None
        self._next_frame_sequence = 0
        self._accepted_samples = 0
        self._committed_samples = 0
        self._frozen_until_sample = 0
        self._next_span_id = 0
        self._frames: deque[_RetainedFrame] = deque()
        self._retained_samples = 0
        self._frozen_spans: dict[int, FrozenSpan] = {}
        self._span_order: list[int] = []
        self._pending_results: dict[int, CanonicalResult] = {}
        self._committed: list[CanonicalCommit] = []
        # Per committed span, the decoder's own local speaker for each published segment, in
        # segment order. It is the only thing that survives publication which a correction can
        # be addressed to: the words carry a *canonical* label (or `S00`), and the local
        # speaker that produced them is otherwise gone by the time a sweep has an opinion.
        # One short tuple per span, so a three-hour meeting costs a few thousand small
        # strings against a committed list that is already O(meeting).
        self._label_tracks: dict[int, tuple[str, ...]] = {}
        self._label_revision_version = 0
        self._prefix_hash = _hash_payload({"schema_version": 1, "prefix": []})
        self._identity_snapshot = LiveIdentitySnapshot()
        self._provisional_generation = 0
        self._provisional: ProvisionalSuffix | None = None
        self._waiters: list[asyncio.Event] = []

    @property
    def epoch(self) -> int:
        return self._epoch

    def accept_frame(self, frame: AudioFrame) -> FrameAck:
        self._ensure_accepting()
        _validate_frame(frame)
        if frame.sequence != self._next_frame_sequence:
            raise ValueError(f"expected frame sequence {self._next_frame_sequence}, got {frame.sequence}.")

        self._prune_committed_frames()
        if frame.sample_count > self.max_retained_samples:
            raise LiveSessionBackpressure("frame exceeds live retention capacity.")
        if self._retained_samples + frame.sample_count > self.max_retained_samples:
            raise LiveSessionBackpressure("live retention capacity reached.")

        start_sample = self._accepted_samples
        end_sample = start_sample + frame.sample_count
        self._frames.append(_RetainedFrame(frame.sequence, start_sample, end_sample))
        self._retained_samples += frame.sample_count
        self._accepted_samples = end_sample
        self._next_frame_sequence += 1
        self._bump()
        return FrameAck(
            sequence=frame.sequence,
            start_sample=start_sample,
            end_sample=end_sample,
            accepted_samples=self._accepted_samples,
            retained_samples=self._retained_samples,
            # Accepting audio never freezes a span: the caller decides boundaries and then
            # calls `freeze_until`. The ack the client receives carries those spans instead.
            frozen_span_ids=(),
        )

    def begin_provisional(self) -> tuple[int, int, int]:
        self._ensure_accepting_or_closing()
        self._provisional_generation += 1
        return (self._epoch, self._provisional_generation, self._committed_samples)

    def publish_provisional(
        self,
        *,
        epoch: int,
        generation: int,
        start_sample: int,
        end_sample: int,
        transcript: str,
    ) -> bool:
        if epoch != self._epoch or generation != self._provisional_generation:
            return False
        self._ensure_accepting_or_closing()
        if start_sample != self._committed_samples:
            raise ValueError("provisional suffix must start at the committed prefix.")
        if end_sample < start_sample or end_sample > self._accepted_samples:
            raise ValueError("provisional suffix must stay within accepted audio.")
        self._provisional = ProvisionalSuffix(generation, start_sample, end_sample, transcript)
        self._bump()
        return True

    def freeze_until(self, end_sample: int, *, reason: str) -> FrozenSpan:
        self._ensure_accepting_or_closing()
        if end_sample <= self._frozen_until_sample:
            raise ValueError("frozen span end must advance.")
        if end_sample > self._accepted_samples:
            raise ValueError("cannot freeze samples that have not been accepted.")
        return self._freeze_span(end_sample, reason=reason)

    def submit_canonical(self, result: CanonicalResult) -> bool:
        if result.epoch != self._epoch:
            return False
        self._ensure_accepting_or_closing()
        span = self._frozen_spans.get(result.span_id)
        if span is None:
            return False
        if result.start_sample != span.start_sample or result.end_sample != span.end_sample:
            self._fail(f"canonical result does not match frozen span {result.span_id}.")
            raise LiveSessionFailed(self._failure_reason or "canonical result mismatch.")
        self._validate_canonical(result, span)
        self._pending_results[result.span_id] = result
        self._publish_ready_prefix()
        self._bump()
        self._notify_waiters()
        return True

    def submit_prepared_canonical(self, result: CanonicalResult) -> CanonicalSubmission:
        """Atomically publish the next canonical span and identity snapshot."""

        if result.epoch != self._epoch:
            return _refused("stale_epoch")
        self._ensure_accepting_or_closing()
        span = self._frozen_spans.get(result.span_id)
        if span is None:
            return _refused("unknown_span")
        if not self._span_order or self._span_order[0] != result.span_id:
            return _refused("span_out_of_order")
        if result.start_sample != span.start_sample or result.end_sample != span.end_sample:
            return _refused("span_sample_mismatch")
        preparation_refusal = self._identity_preparation_refusal(result, span)
        if preparation_refusal is not None:
            return _refused(preparation_refusal)
        validation_error = self._canonical_validation_error(result, span)
        if validation_error is not None:
            return _refused(validation_error.refusal)

        assert result.identity_preparation is not None
        self._publish_span(span, result, identity_snapshot=result.identity_preparation.proposed_snapshot)
        self._bump()
        self._notify_waiters()
        return _PUBLISHED

    def submit_unlabeled_canonical(
        self,
        *,
        span_id: int,
        epoch: int,
        start_sample: int,
        end_sample: int,
        transcript: str,
        local_speakers: tuple[str, ...] = (),
    ) -> CanonicalSubmission:
        """Publish a frozen span's words without asserting who spoke them.

        An identity preparation answers *who*, not *whether the meeting can continue*. An
        `abstain` is the designed answer to ambiguous identity or exhausted speaker
        capacity, and a preparer that could not obtain evidence has answered the same
        question with the same word. Neither makes the words unusable, and `stop` waits for
        `committed_samples == accepted_samples`, so refusing the span would strand the
        session exactly as dropping an empty one would.

        Publishing therefore keeps the audio and drops only the claim: the identity
        snapshot is left byte-identical -- no speaker is born, no version advances, so the
        next span still prepares against the state this one saw -- and every segment must
        name `UNATTRIBUTED_SPEAKER`. A transcript that still carries the decoder's local
        labels is refused, because publishing those as canonical would assert an identity
        the session declined to establish.

        `local_speakers` is how the dropped claim stays *addressable*: the labels are gone
        from the words, but a later sweep still has something to say about this span, and it
        says it about the decoder's local speakers. Passing nothing keeps today's behaviour
        exactly -- the span publishes unattributed and stays that way.
        """

        if epoch != self._epoch:
            return _refused("stale_epoch")
        self._ensure_accepting_or_closing()
        span = self._frozen_spans.get(span_id)
        if span is None:
            return _refused("unknown_span")
        if not self._span_order or self._span_order[0] != span_id:
            return _refused("span_out_of_order")
        if start_sample != span.start_sample or end_sample != span.end_sample:
            return _refused("span_sample_mismatch")
        segments = span_segments(transcript, sample_count=span.sample_count)
        if not segments:
            return _refused("unattributed_transcript_unparseable")
        if any(segment.speaker != UNATTRIBUTED_SPEAKER for segment in segments):
            return _refused("unattributed_transcript_names_a_speaker")

        self._publish_span(
            span,
            CanonicalResult(
                span_id=span.id,
                epoch=span.epoch,
                start_sample=span.start_sample,
                end_sample=span.end_sample,
                transcript=transcript,
                local_speakers=local_speakers,
            ),
            identity_snapshot=self._identity_snapshot,
        )
        self._bump()
        self._notify_waiters()
        return _PUBLISHED

    def submit_empty_canonical(
        self,
        *,
        span_id: int,
        epoch: int,
        start_sample: int,
        end_sample: int,
    ) -> CanonicalSubmission:
        """Publish a frozen span that carries no transcript, advancing the committed prefix.

        A span the decoder cannot parse must be accounted for rather than lost: `stop` waits
        for `committed_samples == accepted_samples`, so a span that is merely dropped strands
        the session forever. Every meeting opens with silence and holds silence between turns,
        so this is the ordinary case, not an error path. The identity snapshot is left exactly
        as it was, because a span with no transcript observed nothing about who spoke.
        """

        if epoch != self._epoch:
            return _refused("stale_epoch")
        self._ensure_accepting_or_closing()
        span = self._frozen_spans.get(span_id)
        if span is None:
            return _refused("unknown_span")
        if not self._span_order or self._span_order[0] != span_id:
            return _refused("span_out_of_order")
        if start_sample != span.start_sample or end_sample != span.end_sample:
            return _refused("span_sample_mismatch")

        self._publish_span(
            span,
            CanonicalResult(
                span_id=span.id,
                epoch=span.epoch,
                start_sample=span.start_sample,
                end_sample=span.end_sample,
                transcript="",
            ),
            identity_snapshot=self._identity_snapshot,
        )
        self._bump()
        self._notify_waiters()
        return _PUBLISHED

    def revise_labels(self, revisions: Sequence[LabelRevision]) -> LabelRevisionOutcome:
        """Relabel already-published speech, leaving every published word exactly as it was.

        This is ADR-0002's living document, and it is the only place a committed span changes
        after it is committed. Three rules make that safe rather than alarming:

        * **The words are never rewritten.** A span is revised only if re-rendering its own
          committed segments with their own committed labels reproduces the committed string
          byte for byte. A transcript that does not round-trip keeps everything it has, and
          says so by name -- a correction is worth having only if it cannot cost a word.
        * **`transcript` and `prefix_hash` never move.** The corrected labelling is published
          beside them, so the chain a client verifies still records what was said and a reader
          is still shown who is now believed to have said it.
        * **Nothing here raises and nothing here is terminal.** Every way a correction can fail
          to land -- a span that never committed, a local speaker that span never had, a
          canonical speaker this session never established, a rewrite that would put two of one
          span's own speakers on one identity -- is counted by name and returned. A meeting does
          not end because its identity layer changed its mind about an earlier minute.

        Revising a *closed* session is deliberately allowed: the session-end sweep is where
        ADR-0002 measured essentially all of the accuracy, and it necessarily arrives after the
        last span. The version bump is what tells a still-polling reader to come back for it.
        """

        refusals: dict[str, int] = {}
        by_span: dict[int, dict[str, str]] = {}
        for revision in revisions:
            by_span.setdefault(int(revision.span_id), {})[revision.local_speaker] = (
                revision.canonical_speaker
            )
        if not by_span:
            return LabelRevisionOutcome(version=self._label_revision_version, revised_spans=0, revised_units=0)

        index_of = {commit.span_id: index for index, commit in enumerate(self._committed)}
        revised_spans = 0
        revised_units = 0
        for span_id in sorted(by_span):
            corrections = by_span[span_id]
            index = index_of.get(span_id)
            if index is None:
                _count_refusal(refusals, "span_not_committed", len(corrections))
                continue
            revised = self._revised_span(self._committed[index], corrections, refusals)
            if revised is None:
                continue
            transcript, applied = revised
            self._committed[index] = replace(self._committed[index], revised_transcript=transcript)
            revised_spans += 1
            revised_units += applied

        if revised_spans:
            self._label_revision_version += 1
            self._bump()
            self._notify_waiters()
        return LabelRevisionOutcome(
            version=self._label_revision_version,
            revised_spans=revised_spans,
            revised_units=revised_units,
            refusals=tuple(sorted(refusals.items())),
        )

    def _revised_span(
        self,
        commit: CanonicalCommit,
        corrections: dict[str, str],
        refusals: dict[str, int],
    ) -> tuple[str, int] | None:
        """This span's corrected transcript and how many of its units moved, or `None`."""

        track = self._label_tracks.get(commit.span_id)
        if not track:
            _count_refusal(refusals, "span_has_no_label_track", len(corrections))
            return None
        published = commit.revised_transcript if commit.revised_transcript is not None else commit.transcript
        segments = span_segments(published, sample_count=commit.end_sample - commit.start_sample)
        if len(segments) != len(track):
            _count_refusal(refusals, "span_has_no_label_track", len(corrections))
            return None
        if render_segments(segments, lambda segment: segment.speaker) != published:
            _count_refusal(refusals, "span_does_not_re_render", len(corrections))
            return None

        canonical_speakers = self._identity_snapshot.canonical_speakers
        labels: list[str] = []
        label_of_local: dict[str, str] = {}
        applied = 0
        for position, segment in enumerate(segments):
            local_speaker = track[position]
            canonical_speaker = corrections.get(local_speaker)
            label = segment.speaker
            if canonical_speaker is not None:
                if canonical_speaker in canonical_speakers:
                    label = display_speaker_label(canonical_speaker, canonical_speakers)
                    if label != segment.speaker:
                        applied += 1
                else:
                    _count_refusal(refusals, "canonical_speaker_unknown", 1)
            labels.append(label)
            label_of_local.setdefault(local_speaker, label)

        for local_speaker in corrections:
            if local_speaker not in track:
                _count_refusal(refusals, "local_speaker_not_in_span", 1)
        # The live matcher assigns a span's local speakers one to one, so two of them sharing
        # an identity would be a claim no live span could have made. A sweep re-matches unit
        # by unit and can reach that state across dispositions, so the span keeps what it has
        # rather than publishing it. `UNATTRIBUTED_SPEAKER` is exempt: several of one span's
        # speakers being nobody in particular is the honest state an abstention publishes.
        attributed = [label for label in label_of_local.values() if label != UNATTRIBUTED_SPEAKER]
        if len(set(attributed)) != len(attributed):
            _count_refusal(refusals, "span_labels_would_collide", len(corrections))
            return None
        if not applied:
            _count_refusal(refusals, "label_unchanged", len(corrections))
            return None
        relabelled = tuple(
            replace(segment, speaker=label) for segment, label in zip(segments, labels, strict=True)
        )
        return render_segments(relabelled, lambda segment: segment.speaker), applied

    def snapshot(self) -> LiveSnapshot:
        return LiveSnapshot(
            status=self._status,
            epoch=self._epoch,
            version=self._version,
            accepted_samples=self._accepted_samples,
            accounted_samples=self._committed_samples,
            retained_samples=self._retained_samples,
            committed_samples=self._committed_samples,
            committed_prefix_hash=self._prefix_hash,
            identity_snapshot=self._identity_snapshot,
            committed=tuple(self._committed),
            provisional=self._provisional,
            next_frame_sequence=self._next_frame_sequence,
            frozen_until_sample=self._frozen_until_sample,
            pending_span_ids=tuple(self._span_order),
            failure_reason=self._failure_reason,
            label_revision_version=self._label_revision_version,
        )

    async def stop(self, deadline: float) -> LiveSnapshot:
        self._ensure_accepting_or_closing()
        self._status = "closing"
        if self._accepted_samples > self._frozen_until_sample:
            self._freeze_span(self._accepted_samples, reason="stop_flush")
        self._bump()
        self._notify_waiters()

        loop = asyncio.get_running_loop()
        end_time = loop.time() + max(0.0, float(deadline))
        while self._committed_samples != self._accepted_samples:
            if self._status == "failed":
                raise LiveSessionFailed(self._failure_reason or "live session failed.")
            remaining = end_time - loop.time()
            if remaining <= 0:
                raise TimeoutError("live session stop deadline expired with unresolved samples.")
            waiter = asyncio.Event()
            self._waiters.append(waiter)
            try:
                await asyncio.wait_for(waiter.wait(), timeout=remaining)
            except asyncio.TimeoutError as exc:
                raise TimeoutError("live session stop deadline expired with unresolved samples.") from exc
            finally:
                if waiter in self._waiters:
                    self._waiters.remove(waiter)

        self._status = "closed"
        self._provisional = None
        self._prune_committed_frames(force=True)
        self._bump()
        return self.snapshot()

    async def abort(self, reason: str) -> LiveSnapshot:
        if self._status in {"closed", "aborted", "failed"}:
            return self.snapshot()
        self._status = "aborted"
        self._failure_reason = reason
        self._provisional = None
        self._pending_results.clear()
        self._bump()
        self._notify_waiters()
        return self.snapshot()

    def _ensure_accepting(self) -> None:
        if self._status != "active":
            raise LiveSessionClosed(f"live session is {self._status}.")

    def _ensure_accepting_or_closing(self) -> None:
        if self._status not in {"active", "closing"}:
            raise LiveSessionClosed(f"live session is {self._status}.")

    def _freeze_span(self, end_sample: int, *, reason: str) -> FrozenSpan:
        span = FrozenSpan(
            id=self._next_span_id,
            epoch=self._epoch,
            start_sample=self._frozen_until_sample,
            end_sample=end_sample,
            reason=reason,
        )
        self._next_span_id += 1
        self._frozen_until_sample = end_sample
        self._frozen_spans[span.id] = span
        self._span_order.append(span.id)
        return span

    def _validate_canonical(self, result: CanonicalResult, span: FrozenSpan) -> None:
        error = self._canonical_validation_error(result, span)
        if error is not None:
            self._fail(error.failure_reason)
            raise LiveSessionFailed(self._failure_reason or error.exception_reason)

    def _canonical_validation_error(
        self,
        result: CanonicalResult,
        span: FrozenSpan,
    ) -> _CanonicalValidationError | None:
        if not result.identity_confirmed:
            return _CanonicalValidationError(
                "canonical_missing_identity",
                f"canonical span {span.id} is missing stable session identity.",
                "missing stable session identity.",
            )
        if not result.transcript.strip():
            return _CanonicalValidationError(
                "canonical_empty_transcript",
                f"canonical span {span.id} returned empty transcript.",
                "empty canonical transcript.",
            )
        # Timestamps outside the span are clamped into it rather than refused -- see
        # `live_span_bounds`. The bound is answered in one place because this copy and the
        # identity preparer's both sit on the same submission path.
        if not span_segments(result.transcript, sample_count=span.sample_count):
            return _CanonicalValidationError(
                "canonical_unparseable_transcript",
                f"canonical span {span.id} returned zero parsed segments.",
                "unparseable canonical transcript.",
            )
        return None

    def _identity_preparation_refusal(self, result: CanonicalResult, span: FrozenSpan) -> str | None:
        """Name the way a preparation is not the one this span is waiting for, or `None`.

        Each condition is its own word because they mean different things about the
        session: a preparation built against identity state the session has moved past is
        a race, while one whose transcript does not match the result it arrived with is a
        coordinator defect. Reporting both as "not current" leaves the reader guessing.
        """

        preparation = result.identity_preparation
        if preparation is None:
            return "identity_preparation_missing"
        if preparation.status != "prepared":
            return "identity_preparation_not_prepared"
        if preparation.reason is not None:
            return "identity_preparation_carries_a_reason"
        if preparation.epoch != self._epoch:
            return "identity_preparation_stale_epoch"
        if preparation.span_id != span.id:
            return "identity_preparation_span_mismatch"
        if preparation.start_sample != span.start_sample or preparation.end_sample != span.end_sample:
            return "identity_preparation_sample_mismatch"
        if preparation.base_snapshot_version != self._identity_snapshot.version:
            return "identity_preparation_stale_base_version"
        if preparation.proposed_snapshot.version != self._identity_snapshot.version + 1:
            return "identity_preparation_snapshot_not_successor"
        if preparation.relabeled_transcript != result.transcript:
            return "identity_preparation_transcript_mismatch"
        return None

    def _publish_ready_prefix(self) -> None:
        while self._span_order:
            span_id = self._span_order[0]
            result = self._pending_results.get(span_id)
            if result is None:
                return
            span = self._frozen_spans[span_id]
            if span.start_sample != self._committed_samples:
                return
            self._pending_results.pop(span_id)
            self._publish_span(span, result, identity_snapshot=self._identity_snapshot)

    def _publish_span(
        self,
        span: FrozenSpan,
        result: CanonicalResult,
        *,
        identity_snapshot: LiveIdentitySnapshot,
    ) -> None:
        self._span_order.pop(0)
        self._frozen_spans.pop(span.id)
        prefix_hash = _hash_payload(
            {
                "previous": self._prefix_hash,
                "span_id": span.id,
                "start_sample": span.start_sample,
                "end_sample": span.end_sample,
                "transcript": result.transcript,
                "identity_snapshot": _identity_snapshot_payload(identity_snapshot),
            }
        )
        commit = CanonicalCommit(
            span_id=span.id,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            transcript=result.transcript,
            prefix_hash=prefix_hash,
            identity_snapshot_version=identity_snapshot.version,
        )
        self._committed.append(commit)
        self._retain_label_track(span, result)
        self._committed_samples = span.end_sample
        self._prefix_hash = prefix_hash
        self._identity_snapshot = identity_snapshot
        if self._provisional is not None and self._provisional.start_sample < self._committed_samples:
            self._provisional = None
        self._prune_committed_frames()

    def _retain_label_track(self, span: FrozenSpan, result: CanonicalResult) -> None:
        """Remember which local speaker produced each published segment, when that is known.

        Retained only when it matches the words that were actually published: a track of a
        different length than the committed segments is a caller defect, and a span whose
        address cannot be trusted must be unrevisable rather than revisable at the wrong
        position. Refusing here -- silently, and leaving the span published -- is deliberate:
        publishing is the meeting and an address book is not, so a broken track costs a later
        correction and nothing else.
        """

        track = tuple(result.local_speakers)
        if not track:
            return
        segments = span_segments(result.transcript, sample_count=span.sample_count)
        if len(segments) != len(track):
            return
        self._label_tracks[span.id] = track

    def _prune_committed_frames(self, *, force: bool = False) -> None:
        while self._frames and self._frames[0].end_sample <= self._committed_samples:
            frame = self._frames.popleft()
            self._retained_samples -= frame.end_sample - frame.start_sample
            if not force and self._retained_samples <= self.max_retained_samples:
                continue

    def _fail(self, reason: str) -> None:
        self._status = "failed"
        self._failure_reason = reason
        self._provisional = None
        self._notify_waiters()

    def _bump(self) -> None:
        self._version += 1

    def _notify_waiters(self) -> None:
        for waiter in list(self._waiters):
            waiter.set()


def _count_refusal(refusals: dict[str, int], reason: str, amount: int) -> None:
    refusals[reason] = refusals.get(reason, 0) + amount


def _validate_frame(frame: AudioFrame) -> None:
    if frame.sequence < 0:
        raise ValueError("frame sequence must be non-negative.")
    if frame.sample_rate != LIVE_SAMPLE_RATE:
        raise ValueError(f"live audio must be {LIVE_SAMPLE_RATE} Hz PCM.")
    if frame.sample_count <= 0:
        raise ValueError("frame sample_count must be positive.")
    if len(frame.pcm) != frame.sample_count * PCM16_BYTES_PER_SAMPLE:
        raise ValueError("frame pcm length must match 16-bit mono sample_count.")


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _identity_snapshot_payload(snapshot: LiveIdentitySnapshot) -> dict[str, Any]:
    return {
        "version": snapshot.version,
        "canonical_speakers": list(snapshot.canonical_speakers),
        "diagnostics": [list(item) for item in snapshot.diagnostics],
    }
