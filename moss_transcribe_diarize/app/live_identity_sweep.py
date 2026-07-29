"""ADR-0002 step 3: the retrospective sweep, which is what makes live identity *converge*.

ADR-0002 classifies the album alone as "a terminal-state failure if shipped alone": a sibling
project reached <80 % speaker accuracy precisely because its live labels used only the evidence
available at time T and history was never revisited, so live accuracy **diverged** from
whole-file accuracy. The album fixes what a label is matched *against*; only a sweep fixes the
labels already written down.

**What a sweep re-reads, decided here rather than inherited.** ADR-0002's prose says the sweep
"re-embed[s]/re-cluster[s] the assembled tape". Its *measured* gate B says a sweep costs ~0.1 ms
at 600 s and under 10 ms extrapolated to three hours -- which cannot include embedding, measured
in the same document at 332-343 ms **per unit**. So the run that passed gate B re-matched the
embeddings the live path had already computed, against the album as it stood at sweep time. This
module implements the measured thing, not the prose: **a sweep re-matches retained evidence; it
never re-hears audio.** That is also what the album's own thesis says out loud -- "the album is
the compressed context handed forward: later processing never re-hears earlier audio".

The honest cost of that choice, stated because it bounds what any convergence number can mean: a
sweep can repair an *assignment* (this voice was labelled as the wrong speaker) and cannot repair
a *segmentation* (the span's local diarization split two voices wrongly, or the evidence floor
skipped a unit entirely). ADR-0002 §7 carries the identical caveat -- "in-span local diarization
assumed correct" -- so gate B's convergence was measured under the same limit. Re-VAD from the
tape is a later, separately-measured refinement, and it is the thing the tape's audio is for.

**What a sweep may change.** Three rules, each of which exists to keep a correction from being
worse than the mistake:

* It never invents a speaker. Births are a live decision under the 16-speaker cap; a sweep that
  could birth would put labels in the transcript that no live reader ever saw.
* It never removes a label it cannot replace. Identity answers *who*, never *whether* (J2), and
  an erasure is not a correction -- it is a second failure wearing a first one's clothes.
* It only moves a unit when the new match beats the incumbent's own score by the deployed match
  margin. Without that, two near-equal candidates would trade a unit back and forth on every
  cadence, and each trade is a visible transcript revision. At the deployed 0.35 / 0.1 the
  production matcher already guarantees this and the guard never fires -- it refuses to assign
  at all unless the winner beats every rival by the margin, and the incumbent is a rival. The
  guard is kept for a deployment that states a margin above its own match floor, where that
  guarantee stops covering the incumbent, and `KEPT_BELOW_MARGIN` is what names it.

**Merging is a stronger claim than matching, so it needs stronger evidence.** Two canonical
speakers whose album centroids sit at or above `SWEEP_MERGE_THRESHOLD` are one voice that was
born twice. Merging them is the first mechanism in this repository that can *reduce* the
canonical speaker count, which is what candidate 55's fragmentation costs 4.5 pp of accuracy for.
It does not stop the births -- that is candidate 55's own fix -- but it can heal them
retrospectively. A merge therefore requires an admitted exemplar bank on **both** sides: a
provisional stand-in is one sub-admission fragment, and letting a fragment collapse two speakers
would re-open the very door the album closed.

Nothing here raises on the live path. `sweep()` returns a revision; every unit it declined to
touch is counted under a name that says why. Applying a revision is the caller's job -- this
module proposes state exactly as `BoundedCausalIdentityPreparer` does, and for the same reason.
"""

from __future__ import annotations

import logging
import math
from array import array
from dataclasses import dataclass
from typing import Iterator, Mapping, Sequence

import numpy

from .live_identity import (
    LiveIdentityConfig,
    LiveIdentityError,
    LiveSpeakerEvidence,
    assign_speakers,
)
from .live_identity_album import (
    REJECTED_INVALID_DURATION,
    REJECTED_INVALID_VECTOR,
    AlbumExemplar,
    FingerprintAlbum,
    cosine_similarity,
    duration_weighted_centroid,
)

# ADR-0002 §7's measured starting parameters for the sweep half of the design.
SWEEP_MERGE_THRESHOLD = 0.70
# The cadence, named here beside the policy it paces for the same reason the album names the
# matcher thresholds it does not read: whoever schedules a sweep must be pacing *this* design.
SWEEP_INTERVAL_SECONDS = 60.0

# The ledger's bound, in evidence units. Memory is measured, not estimated: one 256-dimensional
# float32 vector costs 1104 bytes here (the same values as a Python tuple cost 8232), so this cap
# holds the ledger at ~22 MB. F3's real 17-minute soak committed 443 spans in 1029 s, i.e. 0.43
# spans/s, so three hours is ~4650 spans and -- at the two-speaker spans that meeting produced --
# under 10 000 units. The cap is therefore ~2x a three-hour meeting.
SWEEP_LEDGER_MAX_UNITS = 20000

# Ledger dispositions. `REJECTED_INVALID_VECTOR` and `REJECTED_INVALID_DURATION` are the album's
# own words, imported rather than restated: an observation the album would refuse to enrol is
# refused here for the identical reason, and one vocabulary is what lets a log line be read once.
RECORDED = "recorded"
REPLACED = "replaced"
REJECTED_LEDGER_FULL = "rejected_ledger_full"

# Sweep dispositions, one per unit, every one of them naming why the unit was left alone.
KEPT = "kept"
KEPT_AMBIGUOUS = "kept_ambiguous"
KEPT_BELOW_MARGIN = "kept_below_margin"
KEPT_UNMATCHED = "kept_unmatched"
KEPT_UNSCORED = "kept_unscored"
NO_REFERENCE = "no_reference"

# Why a correction was made. A revision that only said "changed" would make a merge and a
# rescored reassignment indistinguishable in a revision log a human has to read.
REASSIGNED = "reassigned"
LABELLED = "labelled"
MERGED = "merged"

_SWEEP_LOG = logging.getLogger("moss_transcribe_diarize.live.identity")


@dataclass(frozen=True, slots=True)
class SweepUnit:
    """One evidence unit as the live path saw it: one speaker's speech inside one span.

    `vector` is whatever sequence the ledger holds -- an `array("f")` in practice, so a long
    meeting's retained evidence costs a seventh of what the equivalent tuples would.
    """

    span_id: int
    local_speaker: str
    canonical_speaker: str | None
    vector: Sequence[float]
    duration_sec: float


@dataclass(frozen=True, slots=True)
class SweepMerge:
    """Two canonical speakers ruled to be one voice, and the similarity that ruled it."""

    kept: str
    absorbed: str
    score: float

    def to_dict(self) -> dict[str, object]:
        return {"kept": self.kept, "absorbed": self.absorbed, "score": round(self.score, 6)}


@dataclass(frozen=True, slots=True)
class SweepCorrection:
    """One historical unit's label, rewritten, with the evidence that justified rewriting it."""

    span_id: int
    local_speaker: str
    previous_speaker: str | None
    canonical_speaker: str
    reason: str
    score: float

    def to_dict(self) -> dict[str, object]:
        return {
            "span_id": self.span_id,
            "local_speaker": self.local_speaker,
            "previous_speaker": self.previous_speaker,
            "canonical_speaker": self.canonical_speaker,
            "reason": self.reason,
            "score": round(self.score, 6),
        }


@dataclass(frozen=True, slots=True)
class SweepRevision:
    """What one sweep proposes. Nothing is applied until a caller applies it.

    `dispositions` counts what the *re-match* decided for each unit; `corrections` records what
    a *label* did. The two are deliberately not the same tally: a merged unit is counted `kept`
    -- the matcher put it back where it was -- and still carries a `merged` correction, because
    the speaker it was put back onto is no longer called what it was called.
    """

    corrections: tuple[SweepCorrection, ...] = ()
    merges: tuple[SweepMerge, ...] = ()
    swept_spans: int = 0
    swept_units: int = 0
    dispositions: tuple[tuple[str, int], ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.corrections and not self.merges

    def to_dict(self) -> dict[str, object]:
        return {
            "corrections": [item.to_dict() for item in self.corrections],
            "merges": [item.to_dict() for item in self.merges],
            "swept_spans": self.swept_spans,
            "swept_units": self.swept_units,
            "dispositions": dict(self.dispositions),
        }


@dataclass(slots=True)
class _Entry:
    canonical_speaker: str | None
    vector: array
    duration_sec: float


class SweepLedger:
    """The retained evidence a sweep re-matches: one entry per `(span, local speaker)`.

    Bounded, because it is the only structure in the live identity path that grows with meeting
    length. When the bound is reached the ledger refuses **new** units rather than evicting old
    ones, which is the opposite of a cache and deliberately so: a sweep's value is correcting the
    *early*, low-quality decisions against a *later*, better album, so the oldest units are the
    ones with the most left to gain. It is also the tape's rule (`live_tape`), and a project that
    answers "what does a cap do" two different ways has two contracts to keep in step.
    """

    def __init__(self, *, max_units: int = SWEEP_LEDGER_MAX_UNITS):
        if max_units <= 0:
            raise ValueError("sweep ledger max_units must be positive.")
        self.max_units = int(max_units)
        self._spans: dict[int, dict[str, _Entry]] = {}
        self._unit_count = 0
        self._refused_units = 0

    @property
    def unit_count(self) -> int:
        return self._unit_count

    @property
    def span_count(self) -> int:
        return len(self._spans)

    @property
    def refused_units(self) -> int:
        """Units the cap turned away. Non-zero means this meeting's tail is unrevisable."""

        return self._refused_units

    def record(
        self,
        *,
        span_id: int,
        local_speaker: str,
        canonical_speaker: str | None,
        vector: Sequence[float],
        duration_sec: float,
    ) -> str:
        """Retain one span's evidence for one speaker; return the disposition.

        `canonical_speaker` is `None` for a unit the live path left unlabelled -- an abstained
        span, or one whose match missed the bar. Recording it is what lets a later sweep *rescue*
        it, which is where the accuracy an abstain costs is won back; the alternative, recording
        only what was already labelled, would make the sweep unable to improve exactly the spans
        the live path found hardest.
        """

        values = _finite_float32(vector)
        if values is None:
            return REJECTED_INVALID_VECTOR
        try:
            duration = float(duration_sec)
        except (TypeError, ValueError):
            return REJECTED_INVALID_DURATION
        if not math.isfinite(duration) or duration <= 0.0:
            return REJECTED_INVALID_DURATION

        span = self._spans.get(int(span_id))
        replacing = span is not None and local_speaker in span
        if not replacing and self._unit_count >= self.max_units:
            self._refused_units += 1
            return REJECTED_LEDGER_FULL
        if span is None:
            span = self._spans.setdefault(int(span_id), {})
        entry = _Entry(
            canonical_speaker=canonical_speaker,
            vector=values,
            duration_sec=duration,
        )
        span[local_speaker] = entry
        if replacing:
            return REPLACED
        self._unit_count += 1
        return RECORDED

    def spans(self) -> Iterator[tuple[int, tuple[SweepUnit, ...]]]:
        """Every span in span order, its units in local-speaker order.

        An iterator rather than a list: materialising a three-hour meeting's units at once would
        cost the very memory the `array("f")` storage exists to save.
        """

        for span_id in sorted(self._spans):
            members = self._spans[span_id]
            yield span_id, tuple(
                SweepUnit(
                    span_id=span_id,
                    local_speaker=local,
                    canonical_speaker=members[local].canonical_speaker,
                    vector=members[local].vector,
                    duration_sec=members[local].duration_sec,
                )
                for local in sorted(members)
            )

    def canonical_speaker(self, span_id: int, local_speaker: str) -> str | None:
        members = self._spans.get(int(span_id))
        if members is None:
            return None
        entry = members.get(local_speaker)
        return entry.canonical_speaker if entry is not None else None

    def apply(self, revision: SweepRevision) -> int:
        """Move the ledger's incumbents onto a revision's corrections; return how many moved.

        The corrections are the whole revision as far as the ledger is concerned -- a merge is
        the *reason* a unit moved, and every unit a merge moves carries its own correction. What
        a merge additionally implies for the album and for the session's canonical speaker list
        belongs to whoever applies the revision to those, not here.
        """

        applied = 0
        for correction in revision.corrections:
            members = self._spans.get(correction.span_id)
            if members is None:
                continue
            entry = members.get(correction.local_speaker)
            if entry is None:
                continue
            entry.canonical_speaker = correction.canonical_speaker
            applied += 1
        return applied


def sweep(
    *,
    ledger: SweepLedger,
    album: FingerprintAlbum,
    config: LiveIdentityConfig,
    merge_threshold: float = SWEEP_MERGE_THRESHOLD,
) -> SweepRevision:
    """Re-match every retained unit against the album as it stands now.

    Deterministic: the same ledger and album produce the same revision, every time. And once a
    revision is applied, sweeping again proposes no further corrections -- a sweep that kept
    finding new work on unchanged evidence would be an oscillation, not a convergence. Merges are
    the one thing a second sweep repeats, because the album still holds both speakers until
    something applies the merge *to the album*; that is the caller's step, and the repetition is
    the revision honestly saying the claim still stands.
    """

    references, leader_of, merges = _album_view(album, merge_threshold)
    dispositions: dict[str, int] = {}
    corrections: list[SweepCorrection] = []
    merge_score = {item.absorbed: item.score for item in merges}
    reference_speakers = tuple(sorted(references))
    # Once, not once per span: the album does not move during a sweep, and rebuilding this for
    # every span is the difference between a sweep that fits inside a live meeting and one that
    # does not. Measured on F3's own shape below.
    reference_matrix = _reference_matrix(references, reference_speakers)
    swept_spans = 0
    swept_units = 0

    for span_id, units in ledger.spans():
        swept_spans += 1
        swept_units += len(units)
        if not reference_speakers:
            # No speaker has a reference at all, so there is nothing to re-match against and no
            # merge could have been proposed either. Every unit keeps what it has, by name.
            _count(dispositions, NO_REFERENCE, len(units))
            continue

        local_speakers = tuple(unit.local_speaker for unit in units)
        evidence, score_by_pair, unscored = _score_span(
            units, references, reference_speakers, reference_matrix
        )
        ambiguous = False
        mapping: dict[str, str] = {}
        try:
            mapping = dict(
                assign_speakers(
                    local_speakers=local_speakers,
                    canonical_speakers=reference_speakers,
                    evidence=evidence,
                    config=config,
                )
            )
        except LiveIdentityError:
            # The live path abstains for the whole span here; a sweep keeps the whole span's
            # labels. Same ruling, taken later. A merge still applies -- it is not an assignment
            # question, and leaving a unit pointing at a speaker that is no longer separate would
            # be a stale label rather than a preserved one.
            ambiguous = True

        for unit in units:
            original = unit.canonical_speaker
            incumbent = leader_of.get(original, original) if original is not None else None
            proposed = None if ambiguous else mapping.get(unit.local_speaker)
            disposition: str | None
            if unit.local_speaker in unscored:
                final, disposition = incumbent, KEPT_UNSCORED
            elif ambiguous:
                final, disposition = incumbent, KEPT_AMBIGUOUS
            elif proposed is None:
                final, disposition = incumbent, KEPT_UNMATCHED
            elif proposed == incumbent:
                final, disposition = incumbent, KEPT
            else:
                incumbent_score = score_by_pair.get((unit.local_speaker, incumbent), 0.0)
                proposed_score = score_by_pair.get((unit.local_speaker, proposed), 0.0)
                if proposed_score - incumbent_score < config.min_match_margin:
                    final, disposition = incumbent, KEPT_BELOW_MARGIN
                else:
                    final, disposition = proposed, None

            if disposition is not None:
                _count(dispositions, disposition, 1)
            if final is None or final == original:
                continue
            if disposition is None:
                reason = REASSIGNED if original is not None else LABELLED
                score = score_by_pair.get((unit.local_speaker, final), 0.0)
            else:
                # The label moved without the assignment moving, which is a merge and nothing
                # else: `incumbent` differs from `original` only where `leader_of` mapped it.
                reason = MERGED
                score = merge_score.get(original, 0.0)
            corrections.append(
                SweepCorrection(
                    span_id=span_id,
                    local_speaker=unit.local_speaker,
                    previous_speaker=original,
                    canonical_speaker=final,
                    reason=reason,
                    score=score,
                )
            )

    return SweepRevision(
        corrections=tuple(corrections),
        merges=merges,
        swept_spans=swept_spans,
        swept_units=swept_units,
        dispositions=tuple(sorted(dispositions.items())),
    )


class LiveIdentitySweeper:
    """One meeting's step-3 state: the retained evidence, the cadence, and what has been swept.

    `sweep()` above is a pure function of a ledger and an album; this is the thing a live
    session owns. It exists so that the two questions a running meeting has to answer -- *what
    do I retain* and *when do I re-match it* -- have one owner rather than being spread over
    whichever collaborator happened to be holding a vector at the time.

    **The ledger is fed where the album is fed, and it is deliberately not the same event.**
    The album only ever hears an assignment the live path *made*; the ledger hears every unit
    the encoder embedded, labelled or not, because rescuing an abstained span is where a sweep
    wins back the accuracy an abstention costs (J2 keeps the words and drops the claim; a sweep
    is what can put the claim back later). So a unit arrives here twice in the ordinary case --
    once unlabelled when its vector is computed, once carrying its canonical speaker when the
    next span's preparation reconciles it -- and `SweepLedger.record` answers `replaced` for the
    second, which is what that disposition is for.

    **Meeting time paces the cadence, not wall time.** `SWEEP_INTERVAL_SECONDS` is a distance
    along the transcript, so a meeting that arrives in a burst after a network outage is swept
    the same number of times as one that arrived smoothly -- and, unlike a wall clock, it cannot
    step backwards (the *Duration vs timestamp* contract, and candidate 56's whole cause).

    Nothing here raises for a frame's worth of evidence: `record` returns the ledger's
    disposition and `maybe_sweep` returns `None` when the cadence has not come round. A meeting
    does not end because its identity layer had nothing useful to say.
    """

    def __init__(
        self,
        *,
        album: FingerprintAlbum,
        config: LiveIdentityConfig,
        ledger: SweepLedger | None = None,
        interval_seconds: float = SWEEP_INTERVAL_SECONDS,
        merge_threshold: float = SWEEP_MERGE_THRESHOLD,
    ):
        interval = float(interval_seconds)
        if not math.isfinite(interval) or interval <= 0.0:
            raise ValueError("sweep interval_seconds must be positive and finite.")
        self.album = album
        self.config = config
        self.ledger = SweepLedger() if ledger is None else ledger
        self.interval_seconds = interval
        self.merge_threshold = float(merge_threshold)
        self._next_sweep_at = interval
        self._sweeps = 0
        self._corrections = 0
        self._merges = 0
        self._latest: SweepRevision | None = None
        self._unconsumed: SweepRevision | None = None

    @property
    def sweeps(self) -> int:
        return self._sweeps

    @property
    def corrections(self) -> int:
        """Every correction this meeting's sweeps have proposed, cumulative.

        Cumulative rather than "outstanding" because a correction is a *fact about a span* the
        moment it is proposed; whoever rewrites the transcript consumes revisions, and a counter
        that shrank when they did would make "how much of this meeting has been rewritten"
        unanswerable after the fact.
        """

        return self._corrections

    @property
    def merges(self) -> int:
        return self._merges

    @property
    def latest_revision(self) -> SweepRevision | None:
        return self._latest

    def take_revision(self) -> SweepRevision | None:
        """Hand the newest unconsumed revision to whoever publishes it, once.

        Separate from `latest_revision`, which is diagnosis and never empties: this is the
        *consumption* half, so a caller that reads it in a loop cannot re-publish a correction
        it has already published. `None` means there is nothing outstanding -- either no sweep
        has run, or the last one proposed nothing, or its proposal has already been taken.

        Only the newest is kept. A sweep re-matches the whole ledger against the album as it
        stands, so a revision it produces supersedes every earlier one rather than adding to
        it; queueing them would replay the meeting's corrections in order for no gain.
        """

        revision = self._unconsumed
        self._unconsumed = None
        return revision

    def record(
        self,
        *,
        span_id: int,
        local_speaker: str,
        canonical_speaker: str | None,
        vector: Sequence[float],
        duration_sec: float,
    ) -> str:
        return self.ledger.record(
            span_id=span_id,
            local_speaker=local_speaker,
            canonical_speaker=canonical_speaker,
            vector=vector,
            duration_sec=duration_sec,
        )

    def maybe_sweep(self, *, meeting_seconds: float) -> SweepRevision | None:
        """Sweep if this much committed meeting has gone by since the last one.

        The next deadline is computed from the meeting time reached, not by adding an interval
        to the previous deadline: a span that arrives after a long gap should schedule the next
        sweep an interval from *now*, not fire a burst of them catching up on time in which no
        evidence was retained.
        """

        try:
            reached = float(meeting_seconds)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(reached) or reached < self._next_sweep_at:
            return None
        self._next_sweep_at = (int(reached // self.interval_seconds) + 1) * self.interval_seconds
        return self.sweep_now()

    def sweep_now(self) -> SweepRevision:
        """Re-match everything retained, apply the result to the ledger, and return it.

        Applying to the ledger is what makes the *next* sweep converge -- an incumbent that was
        not moved is proposed again forever. Applying to the transcript is a different question
        with a different owner, and this returns the revision so that owner has it.
        """

        revision = sweep(
            ledger=self.ledger,
            album=self.album,
            config=self.config,
            merge_threshold=self.merge_threshold,
        )
        self._sweeps += 1
        self._corrections += len(revision.corrections)
        self._merges += len(revision.merges)
        self.ledger.apply(revision)
        self._latest = revision
        if not revision.is_empty:
            self._unconsumed = revision
            # Counts and speaker ids only. A revision names which spans changed speaker, and a
            # span's words are the meeting -- they do not belong in a log line any more than a
            # token does.
            _SWEEP_LOG.info(
                "live identity sweep: spans=%d units=%d corrections=%d merges=%d",
                revision.swept_spans,
                revision.swept_units,
                len(revision.corrections),
                len(revision.merges),
            )
        return revision


def _album_view(
    album: FingerprintAlbum,
    merge_threshold: float,
) -> tuple[dict[str, tuple[float, ...]], dict[str, str], tuple[SweepMerge, ...]]:
    """The album as a sweep sees it: one reference per surviving speaker, plus who absorbed whom.

    A merged group's reference is the duration-weighted centroid over the **union** of its
    members' exemplars, not the average of their centroids: the exemplars carry the seconds that
    weight them, and a speaker with one 8 s exemplar should not be outvoted by one with a single
    1 s one just because both banks reduce to a unit vector.
    """

    banks = {speaker: album.exemplars(speaker) for speaker in album.speakers()}
    centroids: dict[str, tuple[float, ...]] = {}
    for speaker, bank in banks.items():
        centroid = duration_weighted_centroid(bank)
        if centroid is not None:
            centroids[speaker] = centroid

    parent = {speaker: speaker for speaker in centroids}
    pair_score: dict[tuple[str, str], float] = {}
    mergeable = sorted(centroids)
    for index, left in enumerate(mergeable):
        for right in mergeable[index + 1 :]:
            score = cosine_similarity(centroids[left], centroids[right])
            if score is None or score < merge_threshold:
                continue
            pair_score[(left, right)] = score
            _union(parent, left, right)

    groups: dict[str, list[str]] = {}
    for speaker in mergeable:
        groups.setdefault(_find(parent, speaker), []).append(speaker)

    references: dict[str, tuple[float, ...]] = {}
    leader_of: dict[str, str] = {}
    merges: list[SweepMerge] = []
    for members in groups.values():
        # The best-established voice keeps its id: most admitted speech first, then the lowest id
        # so the choice cannot depend on dictionary order.
        totals = {speaker: sum(item.duration_sec for item in banks[speaker]) for speaker in members}
        leader = min(members, key=lambda speaker: (-totals[speaker], speaker))
        union: list[AlbumExemplar] = []
        for speaker in sorted(members):
            union.extend(banks[speaker])
            leader_of[speaker] = leader
            if speaker != leader:
                score = pair_score.get(_ordered(speaker, leader))
                if score is None:
                    score = cosine_similarity(centroids[speaker], centroids[leader]) or 0.0
                merges.append(SweepMerge(kept=leader, absorbed=speaker, score=score))
        centroid = duration_weighted_centroid(union)
        if centroid is not None:
            references[leader] = centroid

    for speaker in album.speakers():
        # A speaker with no admitted bank is un-mergeable but still matchable: its provisional
        # stand-in is what the live path is matching against right now, so a sweep that ignored it
        # would answer a different question than the meeting is asking.
        if speaker in leader_of:
            continue
        leader_of[speaker] = speaker
        reference = album.reference(speaker)
        if reference is not None:
            references[speaker] = reference

    merges.sort(key=lambda item: (item.kept, item.absorbed))
    return references, leader_of, tuple(merges)


def _reference_matrix(
    references: Mapping[str, tuple[float, ...]],
    reference_speakers: Sequence[str],
):
    """Every reference as one unit-normalised matrix, or `None` if they are not all comparable.

    Built once per sweep rather than once per span, because it is the same matrix for all of
    them and rebuilding it 443 times is most of what a sweep would otherwise cost.

    `None` is not a failure: it means at least one reference has a different dimension or no
    length, and the scalar path -- `cosine_similarity`, the identity layer's one similarity rule
    -- answers each pair on its own and names the unscorable ones. Falling back for the whole
    sweep rather than per pair is what keeps the two paths from ever disagreeing about an edge.
    """

    if not reference_speakers:
        return None
    dimension = len(references[reference_speakers[0]])
    if dimension == 0 or any(len(references[speaker]) != dimension for speaker in reference_speakers):
        return None
    matrix = numpy.asarray(
        [references[speaker] for speaker in reference_speakers],
        dtype=numpy.float64,
    )
    return _unit_rows(matrix)


def _unit_rows(matrix):
    """Rows scaled to unit length, or `None` if any row has no usable length.

    The same three refusals `cosine_similarity` makes -- a non-finite norm, a zero norm, a
    non-finite result -- taken over a whole matrix at once, because a batch that answered where
    the scalar rule refuses would make a sweep's score depend on how many spans were in flight.
    """

    if not numpy.isfinite(matrix).all():
        return None
    norms = numpy.sqrt((matrix * matrix).sum(axis=1))
    if not numpy.isfinite(norms).all() or bool((norms <= 0.0).any()):
        return None
    return matrix / norms[:, None]


def _score_span(
    units: Sequence[SweepUnit],
    references: Mapping[str, tuple[float, ...]],
    reference_speakers: Sequence[str],
    reference_matrix=None,
) -> tuple[tuple[LiveSpeakerEvidence, ...], dict[tuple[str, str], float], set[str]]:
    scores = _batch_scores(units, reference_matrix)
    evidence: list[LiveSpeakerEvidence] = []
    score_by_pair: dict[tuple[str, str], float] = {}
    unscored: set[str] = set()
    for row, unit in enumerate(units):
        scored = False
        for column, canonical in enumerate(reference_speakers):
            score = (
                cosine_similarity(unit.vector, references[canonical])
                if scores is None
                else float(scores[row, column])
            )
            if score is None:
                continue
            scored = True
            score_by_pair[(unit.local_speaker, canonical)] = score
            evidence.append(
                LiveSpeakerEvidence(
                    local_speaker=unit.local_speaker,
                    canonical_speaker=canonical,
                    score=score,
                    evidence_id=f"sweep:{unit.span_id}:{unit.local_speaker}:{canonical}",
                )
            )
        if not scored:
            # A vector no reference can be compared with -- a dimension change across a manifest
            # rotation is the realistic way this happens. Named, so it cannot read as "matched
            # nothing", which is a statement about voices rather than about arithmetic.
            unscored.add(unit.local_speaker)
    return tuple(evidence), score_by_pair, unscored


def _batch_scores(units: Sequence[SweepUnit], reference_matrix):
    """This span's units against every reference at once, clamped exactly as the scalar rule is.

    `None` means "score this span the scalar way", and the two conditions that produce it are
    the same ones `cosine_similarity` refuses on: a unit whose dimension does not match the
    references, and a unit with no usable length. Both are decided for the whole span, so a
    span is never scored half one way and half the other.
    """

    if reference_matrix is None or not units:
        return None
    dimension = reference_matrix.shape[1]
    if any(len(unit.vector) != dimension for unit in units):
        return None
    rows = _unit_rows(numpy.asarray([tuple(unit.vector) for unit in units], dtype=numpy.float64))
    if rows is None:
        return None
    scores = rows @ reference_matrix.T
    if not numpy.isfinite(scores).all():
        return None
    return numpy.clip(scores, 0.0, 1.0)


def _finite_float32(vector: Sequence[float]) -> array | None:
    try:
        values = array("f", (float(item) for item in vector))
    except (TypeError, ValueError, OverflowError):
        return None
    if not values:
        return None
    if any(not math.isfinite(item) for item in values):
        return None
    return values


def _ordered(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def _find(parent: dict[str, str], speaker: str) -> str:
    root = speaker
    while parent[root] != root:
        root = parent[root]
    while parent[speaker] != root:
        parent[speaker], speaker = root, parent[speaker]
    return root


def _union(parent: dict[str, str], left: str, right: str) -> None:
    left_root, right_root = _find(parent, left), _find(parent, right)
    if left_root == right_root:
        return
    # Lowest id becomes the root purely for determinism; the group's leader is chosen by
    # admitted duration afterwards, so this ordering never decides which speaker survives.
    if right_root < left_root:
        left_root, right_root = right_root, left_root
    parent[right_root] = left_root


def _count(counts: dict[str, int], name: str, amount: int) -> None:
    counts[name] = counts.get(name, 0) + amount


__all__ = [
    "KEPT",
    "KEPT_AMBIGUOUS",
    "KEPT_BELOW_MARGIN",
    "KEPT_UNMATCHED",
    "KEPT_UNSCORED",
    "LABELLED",
    "MERGED",
    "LiveIdentitySweeper",
    "NO_REFERENCE",
    "REASSIGNED",
    "RECORDED",
    "REJECTED_LEDGER_FULL",
    "REPLACED",
    "SWEEP_INTERVAL_SECONDS",
    "SWEEP_LEDGER_MAX_UNITS",
    "SWEEP_MERGE_THRESHOLD",
    "SweepCorrection",
    "SweepLedger",
    "SweepMerge",
    "SweepRevision",
    "SweepUnit",
    "sweep",
]
