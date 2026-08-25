"""The two longer listeners over a live meeting's audio: rolling (M2) and terminal (M6).

Live mode hands MOSS one VAD-frozen span at a time -- at most 2.5 seconds -- and publishes
what comes back. File mode hands it 150 seconds. Same audio, same model, same greedy
decoding; the measured cost of the difference is roughly double the word error, and it is
concentrated at the cuts (WER `.483` within 0.25 s of a span boundary against `.082` inside
a span). The words are not lost in the audio, they are lost at the cut, so a listener with
more context gets them back. This module is that listener.

It hears a window of already-committed audio, decodes it once, and proposes those words as a
replacement for the interval it owns. It never publishes anything itself: it returns a
`TextRevisionProposal` and `LiveSession` decides. That division is ADR-0005's, which is the
decision record this module implements (two producers, one seam, seven validations, four
snapshot fields, seven events, zero silent rewrites).

**The geometry is measured, not chosen here.** Plan §10.2's twelve-arm grid ran on the
fully-referenced trio and plan §10.4's selection rule -- least expensive arm passing G1-G3 --
selected a 10-second window on a 10-second stride: trio WER `.199870` -> `.131861`, content
recall `.9135` -> `.9439`, at 1.000 added decode-audio-second per audio-second. Evidence:
`evidence/live-convergence-0824/M2-rolling-grid/`.

That selection is what makes this module small. At stride == window there is **no overlap**,
so there is no stitcher: the grid's three ownership policies produced byte-identical word
sequences on 9/9 case-runs (finding F1). A window's words replace exactly `[lo, hi)` and the
frontier advances to `hi` -- no ownership arithmetic, no lexical alignment, no word-time
interpolation. `RollingGeometry` therefore refuses a stride shorter than its window: an
overlapping geometry needs a stitcher, a stitcher needs a measured selection, and neither
exists. Widening the geometry is a new grid run, not a configuration edit.

What it hides, per plan §6 M2: bounded PCM retention, window planning, one-witness-at-a-time
admission, stale-work recognition, monotonic frontier advancement, and work accounting.

Failure behaviour is plan §5.2's, verbatim in effect:

- *rolling failure* (a window whose decode publishes nothing) -- keep the surface, record the
  failed window, and stop planning. At zero overlap no later window begins at the stalled
  frontier, so D4's monotonic prefix cannot be continued without inventing words for the gap;
  the session keeps its rolling prefix and the base suffix stays provisional and complete.
  Nothing is erased and nothing is silently skipped. Measured occurrences at the selected
  geometry: 0 of 54 window decodes (grid `decode_health`, 3 runs x 3 cases x 6 windows).
- *rolling stale result* -- refused without changing the surface.
- *retention overflow* -- the ring is bounded at `2 x window` samples (plan §6 M2). Reaching
  that bound means the base path is a whole window behind, so the audio a later window needs
  is already gone; the converger says so and stops planning rather than skipping a window.

A refused proposal needs no separate state: the next window is planned only once the
session's own `canonical_through_sample` has reached that window's start, so a proposal the
session declines simply stops the grid instead of burning GPU on revisions that cannot apply.

**The second listener is at the bottom of this file.** `TerminalTranscriptFinalizer` (plan §6
M6) hears the whole meeting once, after capture stops, through file mode's own 150/120
pipeline. The two share this module because they are the same idea at two deadlines -- more
context buys back the words a cut lost -- and because they share one seam: both return a
`TextRevisionProposal` and neither publishes anything. What separates them is what each may
own. A rolling window owns `[lo, hi)` and extends a monotonic prefix; the terminal pass owns
`[0, meeting_end)` and replaces the whole surface, exactly once (ADR-0005, D4).
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from scipy.optimize import linear_sum_assignment

from .live_adapters import (
    InferenceTranscript,
    canonical_decode_token_cap,
    write_pcm16_wav,
)
from .live_session import (
    EffectiveTranscriptSegment,
    LIVE_SAMPLE_RATE,
    PCM16_BYTES_PER_SAMPLE,
    TextRevisionProposal,
)
from .live_span_bounds import span_segments
from .live_tape import CompleteMixedTapeUnavailable

#: The arm plan §10.4 selected from the plan §10.2 grid. Named parameters, not magic numbers:
#: a different geometry is a new measured grid run (see the module docstring).
ROLLING_WINDOW_SECONDS = 10.0
ROLLING_STRIDE_SECONDS = 10.0


class UnmeasuredRollingGeometry(ValueError):
    """A window/stride pair the selection grid never measured, or that needs a stitcher."""


class RollingStatus(str, Enum):
    """Whether the converger is still planning windows, and -- when it is not -- why.

    A stalled converger is not a broken session: the base path keeps publishing and the
    surface keeps everything it had. What the status buys is that the stall is *stated*,
    so a soak sees "rolling stopped after 4 windows because one decode published nothing"
    instead of a rolling gain that quietly stopped arriving.
    """

    #: Planning windows normally.
    ROLLING = "rolling"
    #: `stop` was called; the ring is released and the terminal pass owns what is left.
    STOPPED = "stopped"
    #: A window decode published no segments (plan §5.2 "rolling failure").
    WINDOW_FAILED = "window_failed"
    #: The bounded ring reached `2 x window` samples and dropped audio a window still needed.
    PCM_EVICTED = "pcm_evicted"


@dataclass(frozen=True, slots=True)
class RollingGeometry:
    """The window and stride, in samples, and the retention bound they imply."""

    window_samples: int = int(ROLLING_WINDOW_SECONDS * LIVE_SAMPLE_RATE)
    stride_samples: int = int(ROLLING_STRIDE_SECONDS * LIVE_SAMPLE_RATE)

    def __post_init__(self) -> None:
        if self.window_samples <= 0 or self.stride_samples <= 0:
            raise UnmeasuredRollingGeometry("rolling window and stride must be positive.")
        if self.stride_samples != self.window_samples:
            raise UnmeasuredRollingGeometry(
                "an overlapping rolling geometry needs a stitcher, and plan §10.4 selected "
                "the geometry that needs none (stride == window). Re-run the §10.2 grid "
                "before shipping one."
            )

    @property
    def max_retained_samples(self) -> int:
        """Plan §6 M2's bound: one in-flight payload plus one window of newer audio."""

        return 2 * self.window_samples


DEFAULT_ROLLING_GEOMETRY = RollingGeometry()


class BaseTranscriptSurface(Protocol):
    """What the converger reads from the session's snapshot, and nothing else.

    `LiveSnapshot` satisfies this once M3 adds the plan §7.3 fields; the converger is wired
    to the runtime in plan §10.5 step 4, after that. Stated as the four attributes rather
    than as the whole snapshot because they are the whole dependency: how much audio the base
    has committed, how far the rolling authority has been accepted, which text revision is
    current, and which session all three belong to.
    """

    epoch: int
    committed_samples: int
    canonical_through_sample: int
    text_revision_version: int


@dataclass(frozen=True, slots=True)
class RollingDecodeRequest:
    """One window of audio to decode, complete with the payload. Immutable by construction."""

    id: int
    epoch: int
    window_index: int
    start_sample: int
    end_sample: int
    pcm: bytes
    token_cap: int
    coalesce_key: str

    @property
    def sample_count(self) -> int:
        return self.end_sample - self.start_sample


@dataclass(frozen=True, slots=True)
class TerminalDecodePlan:
    """What the terminal finalizer inherits when the session stops (plan §6 M6).

    It states the extent to finalize and how far rolling authority actually reached. The
    150/120 windowing itself stays `WindowedRunner`'s -- E4 reuses that pipeline through a
    small adapter rather than restating its planning here.
    """

    epoch: int
    end_sample: int
    rolling_through_sample: int
    rolling_status: RollingStatus
    windows_completed: int
    windows_failed: int


@dataclass(frozen=True, slots=True)
class RollingConvergerAccounting:
    """Counts and timing for the plan §7.4 events and the §10.6 resource gate.

    No transcript text, by contract. The high-water mark is here because plan §6 M2 bounds
    retention at `2 x window` samples and the soak fails if that bound is exceeded -- a bound
    nobody measures is a bound nobody has.
    """

    status: RollingStatus
    windows_planned: int
    windows_completed: int
    windows_failed: int
    stale_completions: int
    decoded_audio_samples: int
    accepted_samples: int
    observed_frontier_sample: int
    retained_samples: int
    retained_high_water_samples: int
    max_retained_samples: int
    in_flight_request_id: int | None


class RollingTranscriptConverger:
    """One session's rolling witness. Plan §6 M2; governed by ADR-0005.

    Constructed per session epoch. The four methods are the whole interface: audio in
    (`accept_pcm`), the base surface in (`observe_base`), a decode back (`complete`), and the
    session's end (`stop`). Stitch policy is not exposed because the selected geometry has
    none, and the caller never learns which window owns which words -- that is the point of
    the module.
    """

    def __init__(
        self,
        *,
        epoch: int,
        geometry: RollingGeometry = DEFAULT_ROLLING_GEOMETRY,
    ):
        self.epoch = int(epoch)
        self.geometry = geometry
        self._status = RollingStatus.ROLLING
        self._buffer = bytearray()
        self._buffer_start_sample = 0
        self._accepted_samples = 0
        self._committed_samples = 0
        self._observed_frontier_sample = 0
        self._text_revision_version = 0
        self._next_window_index = 0
        self._next_request_id = 0
        self._in_flight: RollingDecodeRequest | None = None
        self._windows_planned = 0
        self._windows_completed = 0
        self._windows_failed = 0
        self._stale_completions = 0
        self._decoded_audio_samples = 0
        self._retained_high_water = 0

    # ---------------------------------------------------------------- audio in

    def accept_pcm(self, start_sample: int, pcm: bytes) -> tuple[RollingDecodeRequest, ...]:
        """Retain the session's newest audio and plan whatever it makes eligible.

        `start_sample` is the session clock, not a buffer offset, and it must continue
        exactly where the last call ended: a converger that guessed at a gap would own audio
        it never heard.
        """

        if start_sample != self._accepted_samples:
            raise ValueError(
                f"rolling PCM must be contiguous: expected sample {self._accepted_samples}, "
                f"got {start_sample}."
            )
        if len(pcm) % PCM16_BYTES_PER_SAMPLE:
            raise ValueError("rolling PCM must be whole 16-bit samples.")
        if self._status is RollingStatus.STOPPED:
            raise ValueError("a stopped converger accepts no further audio.")

        self._buffer.extend(pcm)
        self._accepted_samples += len(pcm) // PCM16_BYTES_PER_SAMPLE
        self._trim()
        return self._plan()

    # ---------------------------------------------------------------- base surface in

    def observe_base(self, snapshot: BaseTranscriptSurface) -> tuple[RollingDecodeRequest, ...]:
        """Learn how far the base has committed and how far rolling authority was accepted.

        This is also the only feedback channel a proposal has. A window is planned only once
        the session's own `canonical_through_sample` reaches its start, so a refused proposal
        stops the grid instead of producing revisions the session must keep declining.
        """

        if snapshot.epoch != self.epoch:
            raise ValueError(
                f"snapshot epoch {snapshot.epoch} is not this converger's session {self.epoch}."
            )
        if snapshot.committed_samples < self._committed_samples:
            raise ValueError("committed audio may not move backwards.")
        if snapshot.canonical_through_sample < self._observed_frontier_sample:
            raise ValueError("the rolling frontier may not move backwards.")
        self._committed_samples = int(snapshot.committed_samples)
        self._observed_frontier_sample = int(snapshot.canonical_through_sample)
        self._text_revision_version = int(snapshot.text_revision_version)
        return self._plan()

    # ---------------------------------------------------------------- decode back

    def complete(
        self, request_id: int, outcome: InferenceTranscript
    ) -> TextRevisionProposal | None:
        """Turn one window's decode into the revision it proposes, or refuse it by name.

        `None` means the surface does not change: either the decode belongs to a request this
        converger is no longer waiting on (plan §5.2 "rolling stale result"), or it published
        no words at all (plan §5.2 "rolling failure"), which stalls planning rather than
        advancing a frontier over an interval with nothing in it.
        """

        request = self._in_flight
        if request is None or request.id != request_id:
            self._stale_completions += 1
            return None
        self._in_flight = None
        self._decoded_audio_samples += request.sample_count

        segments = self._segments_of(request, outcome)
        if not segments:
            self._windows_failed += 1
            self._status = RollingStatus.WINDOW_FAILED
            return None

        self._windows_completed += 1
        return TextRevisionProposal(
            epoch=self.epoch,
            base_text_revision_version=self._text_revision_version,
            source="rolling",
            start_sample=request.start_sample,
            end_sample=request.end_sample,
            segments=segments,
            decode_elapsed_sec=outcome.elapsed_sec,
        )

    # ---------------------------------------------------------------- session end

    def stop(self, end_sample: int) -> TerminalDecodePlan:
        """End rolling convergence and state what the terminal pass inherits.

        The ring is released here: the terminal pass reads the retained session tape, which is
        separate, explicitly authorized storage, so holding a second copy of the last twenty
        seconds past the end of the meeting buys nothing.
        """

        if end_sample < self._accepted_samples:
            raise ValueError(
                f"session ended at sample {end_sample}, behind the {self._accepted_samples} "
                "samples the converger was given."
            )
        plan = TerminalDecodePlan(
            epoch=self.epoch,
            end_sample=int(end_sample),
            rolling_through_sample=self._observed_frontier_sample,
            rolling_status=self._status,
            windows_completed=self._windows_completed,
            windows_failed=self._windows_failed,
        )
        self._status = RollingStatus.STOPPED
        self._in_flight = None
        self._buffer = bytearray()
        self._buffer_start_sample = self._accepted_samples
        return plan

    # ---------------------------------------------------------------- accounting

    def accounting(self) -> RollingConvergerAccounting:
        return RollingConvergerAccounting(
            status=self._status,
            windows_planned=self._windows_planned,
            windows_completed=self._windows_completed,
            windows_failed=self._windows_failed,
            stale_completions=self._stale_completions,
            decoded_audio_samples=self._decoded_audio_samples,
            accepted_samples=self._accepted_samples,
            observed_frontier_sample=self._observed_frontier_sample,
            retained_samples=self._retained_samples,
            retained_high_water_samples=self._retained_high_water,
            max_retained_samples=self.geometry.max_retained_samples,
            in_flight_request_id=None if self._in_flight is None else self._in_flight.id,
        )

    # ---------------------------------------------------------------- internals

    @property
    def _retained_samples(self) -> int:
        return len(self._buffer) // PCM16_BYTES_PER_SAMPLE

    def _plan(self) -> tuple[RollingDecodeRequest, ...]:
        """Emit the next window if every condition for owning it holds.

        Four conditions, and each one is a thing the converger would otherwise have to
        pretend about: no witness is already in flight (plan §6 M5 allows one per session);
        the session has accepted rolling authority right up to this window's start (D4's
        monotonic prefix); the base has committed the whole window (a revision may not end
        past committed audio); and the ring still holds the window's audio.
        """

        if self._status is not RollingStatus.ROLLING or self._in_flight is not None:
            return ()
        start_sample = self._next_window_index * self.geometry.stride_samples
        end_sample = start_sample + self.geometry.window_samples
        if self._observed_frontier_sample != start_sample:
            return ()
        if end_sample > self._committed_samples or end_sample > self._accepted_samples:
            return ()
        if start_sample < self._buffer_start_sample:
            self._status = RollingStatus.PCM_EVICTED
            return ()

        offset = (start_sample - self._buffer_start_sample) * PCM16_BYTES_PER_SAMPLE
        payload = bytes(
            self._buffer[offset : offset + self.geometry.window_samples * PCM16_BYTES_PER_SAMPLE]
        )
        request = RollingDecodeRequest(
            id=self._next_request_id,
            epoch=self.epoch,
            window_index=self._next_window_index,
            start_sample=start_sample,
            end_sample=end_sample,
            pcm=payload,
            token_cap=canonical_decode_token_cap(sample_count=self.geometry.window_samples),
            coalesce_key=f"rolling:{self.epoch}",
        )
        self._next_request_id += 1
        self._next_window_index += 1
        self._windows_planned += 1
        self._in_flight = request
        self._trim()
        return (request,)

    def _trim(self) -> None:
        """Hold exactly the audio a future window can still own, and no more than the bound.

        The ring starts at the next unplanned window's first sample: everything before it is
        either already inside an in-flight request's immutable payload or behind the frontier,
        so no future window can ask for it. What remains is the newest audio, and plan §6 M2
        bounds that at `2 x window` samples.

        The bound is enforced by dropping, not by refusing audio: the session's own retention
        is the authority on what the meeting keeps, and a converger that pushed back on
        `accept_pcm` would let a rolling experiment stall the base path. What it may not do is
        drop audio and stay silent about it, so the eviction names itself and planning stops.
        """

        window_start = self._next_window_index * self.geometry.stride_samples
        keep_from = max(self._buffer_start_sample, min(window_start, self._accepted_samples))
        drop = (keep_from - self._buffer_start_sample) * PCM16_BYTES_PER_SAMPLE
        if drop > 0:
            del self._buffer[:drop]
            self._buffer_start_sample = keep_from
        excess = self._retained_samples - self.geometry.max_retained_samples
        if excess > 0:
            del self._buffer[: excess * PCM16_BYTES_PER_SAMPLE]
            self._buffer_start_sample += excess
            if self._status is RollingStatus.ROLLING:
                self._status = RollingStatus.PCM_EVICTED
        self._retained_high_water = max(self._retained_high_water, self._retained_samples)

    def _segments_of(
        self, request: RollingDecodeRequest, outcome: InferenceTranscript
    ) -> tuple[EffectiveTranscriptSegment, ...]:
        """The window's words on the session clock, owned by exactly this window.

        `span_segments` is the one reader of the transcript grammar in this codebase and it
        clamps a timestamp into the audio it was given, so a window's segments cannot reach
        outside `[start_sample, end_sample)` and no ownership filter is needed at stride ==
        window. `canonical_speaker` is `None` because a decoder's local `S01` is not a meeting
        identity: attribution is the session's label projection, and witness-owned speaker
        evidence is E3's (plan D5).
        """

        segments: list[EffectiveTranscriptSegment] = []
        for parsed in span_segments(outcome.transcript, sample_count=request.sample_count):
            start = request.start_sample + int(round(parsed.start * LIVE_SAMPLE_RATE))
            end = request.start_sample + int(round(parsed.end * LIVE_SAMPLE_RATE))
            if end <= start or not parsed.text.strip():
                continue
            segments.append(
                EffectiveTranscriptSegment(
                    start_sample=start,
                    end_sample=end,
                    text=parsed.text,
                    canonical_speaker=None,
                    authority="rolling",
                )
            )
        return tuple(segments)


# ======================================================================================
# M6 -- the terminal finalizer: the meeting's last listener, and the longest one.
#
# The rolling witness above hears ten seconds at a time because it has to answer while the
# meeting is still running. Once capture stops that constraint is gone: the whole meeting is
# on the tape, and the pipeline that decodes a whole meeting already exists and is the one
# every file-mode job runs -- `WindowedRunner`, 150-second windows on a 120-second stride.
# Plan §6 M6's instruction is therefore not "write a terminal decoder" but "reuse that one
# through a small live adapter", and small is the point: the adapter owns four things the
# file pipeline has no reason to know about -- where the audio comes from (the tape seam),
# what clock the words land on (session samples), who the decoder's local speakers are on
# this meeting's album, and what to publish when any of that fails.
#
# Everything else is deliberately NOT here. The windowing is `WindowedRunner`'s and is not
# restated; the runner is injected so the deployment hands over the very object file mode
# uses, which makes "terminal == file on identical bytes" an identity rather than a claim
# two configurations have to keep agreeing on. The publication rules are `LiveSession`'s
# seven validations (ADR-0005), including the one this producer exists for: a terminal
# revision replaces the whole surface from sample 0, exactly once, and a second is refused
# `already_finalized`. This module returns a proposal and never touches the session.
# ======================================================================================


class TerminalOutcome(str, Enum):
    """What one terminal pass did, and -- when it published nothing -- which failure it was.

    Plan §5.2 draws the line that matters: a tape that cannot serve the meeting and a model
    that could not decode it are different meetings. The first says the audio to converge on
    was never retained (`unavailable`); the second says it was, and the pass failed
    (`failed`). Both keep the rolling surface, and neither ends the meeting -- capture
    already succeeded.
    """

    #: One proposal covering `[0, meeting_end)` is ready for the session to accept.
    FINALIZED = "finalized"
    #: The tape does not hold `[0, meeting_end)`: short, holed, degraded, or already released.
    TAPE_UNAVAILABLE = "tape_unavailable"
    #: The runner did not answer for this meeting.
    DECODE_FAILED = "decode_failed"
    #: The runner answered, and nothing in the answer parses to words on this clock.
    NO_TRANSCRIPT = "no_transcript"

    @property
    def finalization_status(self) -> str:
        """The plan §7.3 word a caller publishes for this outcome.

        Here rather than at the caller because `finalization_status` is a contract with
        readers and the mapping from "what happened" to "what a reader is told" must have
        exactly one author -- the HTTP surface, the replay trace and the portal all read it.
        `FINALIZED` maps to `running` on purpose: producing a proposal is not publishing it,
        and only `LiveSession.apply_text_revision` may say `final`.
        """

        if self is TerminalOutcome.FINALIZED:
            return "running"
        if self is TerminalOutcome.TAPE_UNAVAILABLE:
            return "unavailable"
        return "failed"


@dataclass(frozen=True, slots=True)
class TerminalFinalizationAccounting:
    """Counts, samples and timing for the plan §7.4 terminal events. No transcript text.

    The speaker fields are here because plan §12.3 step 5 is a step this adapter performs
    and a step that can partly fail: a local speaker the meeting's album has no counterpart
    for is published unattributed, and a reader who is told only "terminal finalized" cannot
    see that. `mapped_speakers` against `local_speakers` is that difference, per meeting.
    """

    outcome: TerminalOutcome
    epoch: int
    end_sample: int
    reason: str | None
    tape_samples: int
    tape_gaps: int
    window_count: int
    completed_windows: int
    decoded_audio_samples: int
    generated_tokens: int
    prompt_tokens: int
    decode_elapsed_sec: float | None
    possibly_truncated: bool
    segments: int
    local_speakers: int
    mapped_speakers: int
    unattributed_segments: int
    rolling_through_sample: int
    rolling_status: str
    window_seconds: float | None
    stride_seconds: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "finalization_status": self.outcome.finalization_status,
            "epoch": self.epoch,
            "end_sample": self.end_sample,
            "reason": self.reason,
            "tape_samples": self.tape_samples,
            "tape_gaps": self.tape_gaps,
            "window_count": self.window_count,
            "completed_windows": self.completed_windows,
            "decoded_audio_samples": self.decoded_audio_samples,
            "generated_tokens": self.generated_tokens,
            "prompt_tokens": self.prompt_tokens,
            "decode_elapsed_sec": self.decode_elapsed_sec,
            "possibly_truncated": self.possibly_truncated,
            "segments": self.segments,
            "local_speakers": self.local_speakers,
            "mapped_speakers": self.mapped_speakers,
            "unattributed_segments": self.unattributed_segments,
            "rolling_through_sample": self.rolling_through_sample,
            "rolling_status": self.rolling_status,
            "window_seconds": self.window_seconds,
            "stride_seconds": self.stride_seconds,
        }


@dataclass(frozen=True, slots=True)
class TerminalFinalization:
    """One terminal pass: the proposal it produced, or the named reason it produced none."""

    proposal: TextRevisionProposal | None
    accounting: TerminalFinalizationAccounting

    @property
    def outcome(self) -> TerminalOutcome:
        return self.accounting.outcome


class CompleteAudioTape(Protocol):
    """The whole seam between a meeting's retained audio and its last listener.

    Two methods, and the finalizer knows nothing else about where the audio lives -- memory
    (ADR-0003 D8) or a declared disk root (ADR-0003 D2) are the same tape from here. `read`
    refuses rather than returning short, which is why the adapter has no completeness check
    of its own; `gaps` is what turns that refusal into evidence a reader can act on.
    """

    def gaps(self, through_sample: int) -> tuple[Any, ...]:
        ...

    def read(self, *, start_sample: int = 0, end_sample: int | None = None) -> bytes:
        ...


class WholeMeetingRunner(Protocol):
    """What the finalizer needs from the file-mode pipeline: one call, on a path.

    Stated as a protocol rather than imported as `WindowedRunner` for two reasons. The live
    service must not pull the file pipeline's own dependencies (ffmpeg detection, the
    identity resolver's encoder) into its import graph merely to describe a seam. And the
    object the deployment passes IS file mode's runner, so the type that matters is the one
    contract both sides already meet -- `transcribe(path, **kwargs) -> TranscriptionResult`.
    """

    def transcribe(self, audio_path: Any, **kwargs: Any) -> Any:
        ...


class TerminalTranscriptFinalizer:
    """The meeting's terminal pass (plan §6 M6, §12.3 steps 4-6). Governed by ADR-0005.

    Constructed once per deployment, not per session: it holds no meeting state, and
    `finalize` is a function of the plan, the tape and the surface it is handed.

    `runner` is file mode's own `WindowedRunner`; `transcribe_kwargs` are file mode's own
    inference arguments (prompt, decoding, token bounds). Nothing here overrides either --
    a terminal pass that decoded with different arguments than the file arm it is measured
    against would make every convergence number a comparison of two configurations.
    """

    def __init__(
        self,
        *,
        runner: WholeMeetingRunner,
        transcribe_kwargs: Mapping[str, Any] | None = None,
        scratch_dir: str | Path | None = None,
    ):
        self.runner = runner
        self.transcribe_kwargs = dict(transcribe_kwargs or {})
        self.scratch_dir = None if scratch_dir is None else Path(scratch_dir)

    def finalize(
        self,
        *,
        plan: TerminalDecodePlan,
        tape: CompleteAudioTape,
        base_text_revision_version: int,
        base_surface: Sequence[EffectiveTranscriptSegment] = (),
        canonical_speakers: Sequence[str] = (),
    ) -> TerminalFinalization:
        """Decode the whole meeting once and propose it as the surface, or refuse by name.

        The three failures are the ones plan §5.2 names and they are ordered by what they
        cost to discover: audio that was never kept is free to detect, a decode that did not
        answer costs the pass, and an answer with no words in it costs the pass and a parse.
        None of them raises. A meeting that was captured is a meeting that succeeded, and the
        rolling surface it already published stays exactly where it is.
        """

        gaps = tuple(tape.gaps(plan.end_sample))
        try:
            pcm = tape.read(start_sample=0, end_sample=plan.end_sample)
        except CompleteMixedTapeUnavailable as exc:
            return self._refused(plan, TerminalOutcome.TAPE_UNAVAILABLE, str(exc), gaps=gaps)

        tape_samples = len(pcm) // PCM16_BYTES_PER_SAMPLE
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="mtd-terminal-", dir=self.scratch_dir) as scratch:
            wav_path = Path(scratch) / f"terminal-{plan.epoch:04d}.wav"
            write_pcm16_wav(wav_path, pcm)
            del pcm
            try:
                result = self.runner.transcribe(wav_path, **self.transcribe_kwargs)
            except Exception as exc:
                # Only the exception's *type* is recorded. A runner's message may quote the
                # answer it rejected, and plan §7.4 says terminal events carry counts and
                # names -- never a word of the meeting.
                return self._refused(
                    plan,
                    TerminalOutcome.DECODE_FAILED,
                    exc.__class__.__name__,
                    gaps=gaps,
                    tape_samples=tape_samples,
                    decode_elapsed_sec=time.monotonic() - started,
                )
            elapsed_sec = time.monotonic() - started

        segments, local_speakers, mapping = self._segments_of(
            result, end_sample=plan.end_sample, base_surface=base_surface,
            canonical_speakers=canonical_speakers,
        )
        accounting = self._accounting(
            plan,
            TerminalOutcome.FINALIZED if segments else TerminalOutcome.NO_TRANSCRIPT,
            None,
            gaps=gaps,
            tape_samples=tape_samples,
            result=result,
            decode_elapsed_sec=elapsed_sec,
            segments=segments,
            local_speakers=local_speakers,
            mapping=mapping,
        )
        if not segments:
            return TerminalFinalization(proposal=None, accounting=accounting)
        return TerminalFinalization(
            proposal=TextRevisionProposal(
                epoch=plan.epoch,
                base_text_revision_version=int(base_text_revision_version),
                source="terminal",
                start_sample=0,
                end_sample=plan.end_sample,
                segments=segments,
                decode_elapsed_sec=elapsed_sec,
            ),
            accounting=accounting,
        )

    # ---------------------------------------------------------------- internals

    def _segments_of(
        self,
        result: Any,
        *,
        end_sample: int,
        base_surface: Sequence[EffectiveTranscriptSegment],
        canonical_speakers: Sequence[str],
    ) -> tuple[tuple[EffectiveTranscriptSegment, ...], tuple[str, ...], dict[str, str]]:
        """The whole meeting's words on the session clock, attributed to the meeting's people.

        `span_segments` is this codebase's one reader of the transcript grammar and clamps
        every timestamp into the audio it was given, so a terminal segment cannot reach past
        `[0, meeting_end)` however the decoder rounded its last marker.
        """

        parsed = [
            item
            for item in span_segments(str(getattr(result, "text", "") or ""), sample_count=end_sample)
            if item.text.strip()
        ]
        placed: list[tuple[str, int, int, str]] = []
        for item in parsed:
            start = int(round(item.start * LIVE_SAMPLE_RATE))
            end = int(round(item.end * LIVE_SAMPLE_RATE))
            if end <= start:
                continue
            placed.append((item.speaker, start, end, item.text))
        local_speakers = tuple(sorted({speaker for speaker, _, _, _ in placed}))
        mapping = terminal_speaker_mapping(
            placed, base_surface=base_surface, canonical_speakers=canonical_speakers
        )
        return (
            tuple(
                EffectiveTranscriptSegment(
                    start_sample=start,
                    end_sample=end,
                    text=text,
                    canonical_speaker=mapping.get(speaker),
                    authority="terminal",
                )
                for speaker, start, end, text in placed
            ),
            local_speakers,
            mapping,
        )

    def _refused(
        self,
        plan: TerminalDecodePlan,
        outcome: TerminalOutcome,
        reason: str,
        *,
        gaps: tuple[Any, ...],
        tape_samples: int = 0,
        decode_elapsed_sec: float | None = None,
    ) -> TerminalFinalization:
        return TerminalFinalization(
            proposal=None,
            accounting=self._accounting(
                plan,
                outcome,
                reason,
                gaps=gaps,
                tape_samples=tape_samples,
                result=None,
                decode_elapsed_sec=decode_elapsed_sec,
                segments=(),
                local_speakers=(),
                mapping={},
            ),
        )

    def _accounting(
        self,
        plan: TerminalDecodePlan,
        outcome: TerminalOutcome,
        reason: str | None,
        *,
        gaps: tuple[Any, ...],
        tape_samples: int,
        result: Any,
        decode_elapsed_sec: float | None,
        segments: tuple[EffectiveTranscriptSegment, ...],
        local_speakers: tuple[str, ...],
        mapping: Mapping[str, str],
    ) -> TerminalFinalizationAccounting:
        window_count = int(getattr(result, "window_count", 0) or 0)
        return TerminalFinalizationAccounting(
            outcome=outcome,
            epoch=plan.epoch,
            end_sample=plan.end_sample,
            reason=reason,
            tape_samples=tape_samples,
            tape_gaps=len(gaps),
            window_count=window_count,
            completed_windows=int(getattr(result, "completed_windows", 0) or 0),
            decoded_audio_samples=tape_samples if window_count else 0,
            generated_tokens=int(getattr(result, "generated_tokens", 0) or 0),
            prompt_tokens=int(getattr(result, "prompt_len", 0) or 0),
            decode_elapsed_sec=decode_elapsed_sec,
            possibly_truncated=bool(getattr(result, "possibly_truncated", False)),
            segments=len(segments),
            local_speakers=len(local_speakers),
            mapped_speakers=len(mapping),
            unattributed_segments=sum(
                1 for segment in segments if segment.canonical_speaker is None
            ),
            rolling_through_sample=plan.rolling_through_sample,
            rolling_status=plan.rolling_status.value,
            window_seconds=_optional_float(getattr(self.runner, "window_seconds", None)),
            stride_seconds=_optional_float(getattr(self.runner, "stride_seconds", None)),
        )


def terminal_speaker_mapping(
    placed: Sequence[tuple[str, int, int, str]],
    *,
    base_surface: Sequence[EffectiveTranscriptSegment],
    canonical_speakers: Sequence[str],
) -> dict[str, str]:
    """Plan §12.3 step 5: who the terminal decoder's local speakers are on this album.

    The rule is one-to-one **per speaker**, not per segment, and that distinction is the
    whole reason this function exists. The session's own projection
    (`live_session._project_canonical_speaker`) attributes a revised stretch of audio segment
    by segment, which is right for a rolling window -- ten seconds of one decode's local `S01`
    means nothing across windows, so each stretch is best answered on its own. A terminal pass
    is the opposite case: it heard the entire meeting in one pass, so its local labels are a
    *partition of the whole meeting*, and answering segment by segment would let two segments
    of one terminal speaker land on two different people. That does not merely mislabel
    words; it destroys the diarization the terminal pass just produced, which is the surface
    the campaign is trying to converge on.

    So the terminal partition is preserved and only its names are decided. Evidence is
    overlap in samples with the surface the meeting published, and the assignment maximises
    total overlap under a one-to-one constraint -- `linear_sum_assignment`, which is already
    this codebase's answer to "match local speakers onto canonical ones"
    (`live_identity.assign_speakers`). Its thresholds do not travel here: those are cosine
    margins between voice embeddings, and this evidence is seconds of agreement on a clock.

    A local speaker with no overlap at all is left out, and its words publish unattributed --
    the same honest `S00` the base path publishes wherever identity abstained. Inventing a
    name for a voice the meeting never established is the one thing this may not do.
    """

    speakers = tuple(canonical_speakers)
    locals_ = tuple(sorted({speaker for speaker, _, _, _ in placed}))
    if not speakers or not locals_ or not base_surface:
        return {}
    overlap = {(local, canonical): 0 for local in locals_ for canonical in speakers}
    for local, start, end, _text in placed:
        for segment in base_surface:
            if segment.canonical_speaker is None:
                continue
            key = (local, segment.canonical_speaker)
            if key not in overlap:
                continue
            shared = min(end, segment.end_sample) - max(start, segment.start_sample)
            if shared > 0:
                overlap[key] += shared
    matrix = [[-overlap[(local, canonical)] for canonical in speakers] for local in locals_]
    rows, columns = linear_sum_assignment(matrix)
    return {
        locals_[row]: speakers[column]
        for row, column in zip(rows, columns, strict=True)
        if overlap[(locals_[row], speakers[column])] > 0
    }


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
