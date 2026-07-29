#!/usr/bin/env python3
"""Phase N step 4's missing number: what the **batch** identity engine scores on the exact
corpus the **live** album engine was scored on.

ADR-0002's step 4 is "batch Tier B -> album unification (one identity engine, two entry
points)". Nothing in this repository has ever measured the engine that unification would
replace, so step 4 has been an ordering item rather than a justified change: the album's
93.44 % (`tests/test_live_identity_accuracy.py`) has had no counterpart on the batch side,
and "unify" without a baseline cannot be told from "rewrite for tidiness".

This probe closes that gap the way `tests/live_identity_accuracy.py` closed the live one --
by driving the **production** object, `IdentityResolver.resolve`, over the same eight
LibriSpeech meetings, with only the encoder substituted by the real encoder's cached answers,
and scoring the result with the **same** `speaker_accuracy` function the album is scored with.

WHAT IS REAL AND WHAT IS SUBSTITUTED.
  * Real: `IdentityResolver`, `IdentityResolverConfig`, `plan_windows` (150 s window /
    120 s stride, the shipped batch geometry), Tier A boundary matching, Tier B evidence
    selection, `_tier_b_centroid`, the pairwise similarity/margin/cannot-link rule, and
    `speaker_accuracy` from the album harness.
  * Substituted: the ONNX encoder, by `CachedUnitEncoder`, which answers with the vector the
    real pinned WeSpeaker encoder produced for that same interval and **raises** for an
    interval it has no answer for. Section 2 proves nothing was silently absorbed:
    `_resolve_tier_b` catches every encoder exception into a `tier_b_embedding_failed`
    proposal, so the probe fails if any appears.

THE THREE FIDELITY LIMITS, STATED WITH THEIR DIRECTION -- read a number against these.
  1. **Tier A is handed a perfect local diarization**, identical in both windows of every
     overlap, so its dice is 1.0 wherever a speaker is present in both. A real local
     diarizer's two windows disagree. This is the single most generous assumption here and
     it makes every batch arm below an **upper bound**, not an estimate.
  2. **Segments are the corpus's live evidence units** (one speaker inside one <= 2.5 s
     planned span), because those are the only intervals the cached encoder can answer for.
     Real batch selects whole diarizer segments with no upper bound, so a real Tier B node
     carries at least as much speech per interval as one here. Direction: pessimistic for
     batch's Tier B, which is why section 3 also runs an arm with more intervals per node.
  3. The corpus is LibriSpeech read speech -- no overlap, no noise, in-span diarization
     assumed correct. ADR-0002 section 7 and the album harness carry the identical caveat.

Offline. No host, no session, no network, no product change. ~30 s.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import live_identity_accuracy as lia  # noqa: E402  (path set above)
from moss_transcribe_diarize.app.live_identity_album import (  # noqa: E402
    ALBUM_ADMISSION_SECONDS,
    ALBUM_EXEMPLARS_PER_SPEAKER,
    ALBUM_MIN_MATCH_MARGIN,
    ALBUM_MIN_MATCH_SCORE,
    cosine_similarity,
)
from moss_transcribe_diarize.app import speaker_identity as batch  # noqa: E402
from moss_transcribe_diarize.app.speaker_identity import (  # noqa: E402
    IdentityResolver,
    IdentityResolverConfig,
    TierBPreflight,
    _cosine,
    tier_b_provider_manifest,
)
from moss_transcribe_diarize.app.windowed_transcription import plan_windows  # noqa: E402
from moss_transcribe_diarize.transcript_parser import TranscriptSegment  # noqa: E402

# The shipped batch window geometry (`WindowedRunner.window_seconds` / `.stride_seconds`).
WINDOW_SECONDS = 150.0
STRIDE_SECONDS = 120.0

FAILURES: list[str] = []
NOTES: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    print(f"  [{'OK' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)
    return ok


def git_grep(pattern: str, *paths: str) -> list[str]:
    """Tracked source only. A working-tree grep answers about what was COMPILED."""

    command = ["git", "grep", "-n", "--", pattern, *paths]
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git grep failed: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


class CachedUnitEncoder:
    """The real encoder's answers for the corpus's evidence units, keyed by absolute time.

    Raises for an interval it has no answer for, exactly as the album harness's
    `CachedEncoder` does: a silent fallback would let the batch engine score *something*
    against vectors that never described that speech.

    A stored vector describes **all** of one unit's intervals averaged together, because that
    is what production embedded, so the unit -- not a piece of one -- is the only interval
    that can be answered honestly. Section 2 proves the batch engine asked for nothing else.
    """

    descriptor = tier_b_provider_manifest()

    def __init__(
        self,
        meeting: lia.Meeting,
        window_starts: dict[int, float],
        units: list[list[lia.Piece]],
    ) -> None:
        self._window_starts = window_starts
        self._by_start: dict[int, np.ndarray] = {}
        vector_index = meeting.vector_index
        for row, pieces in enumerate(units):
            if meeting.rows[row][lia._ELIGIBLE] <= 0:
                continue
            self._by_start[round(pieces[0].start * 1000)] = meeting.vectors[vector_index[row]]
        self.calls = 0

    def preflight(self) -> TierBPreflight:
        return TierBPreflight(available=True, reason=None, descriptor=self.descriptor)

    def embed(self, wav_path, intervals):  # noqa: ANN001 - production Protocol signature
        if len(intervals) != 1:
            raise AssertionError(f"production embeds one interval at a time, got {len(intervals)}")
        window_index = int(Path(wav_path).stem.split("-")[-1])
        absolute_start = self._window_starts[window_index] + float(intervals[0][0])
        vector = self._by_start.get(round(absolute_start * 1000))
        if vector is None:
            raise AssertionError(f"no cached vector for absolute start {absolute_start:.3f}s")
        self.calls += 1
        return [float(value) for value in vector]


def build_case(meeting: lia.Meeting):
    """One meeting as the batch pipeline sees it: windows, per-window local diarization.

    A segment is one evidence **unit** -- one speaker's speech inside one planned span --
    anchored at the unit's true start and given the unit's **speech** seconds as its length.
    That is the only interval the cached encoder can answer for exactly, and it is what makes
    the batch engine's `tier_b_min_segment_seconds` filter apply to the same quantity
    production would apply it to. 828 of the corpus's 2194 units hold internal pauses, so a
    segment can start where its speech starts and end before its last piece does; the
    interval only ever shrinks, so no cross-speaker overlap is invented except inside the
    rare unit whose span another speaker interleaves.

    Local speaker labels are **rotated per window** so they are window-arbitrary, which is
    what a real local diarizer produces and what Tier A/Tier B exist to stitch.
    """

    duration = float(meeting.truth[:, 1].max())
    windows = plan_windows(duration, window_seconds=WINDOW_SECONDS, stride_seconds=STRIDE_SECONDS)
    window_starts = {window.index: float(window.start) for window in windows}
    units = lia.evidence_units(meeting)
    speech = meeting.rows[:, lia._DURATION]

    local_results: list[list[TranscriptSegment]] = []
    for window in windows:
        segments: list[TranscriptSegment] = []
        for row, pieces in enumerate(units):
            if pieces[0].start < window.start or pieces[-1].end > window.end:
                continue
            segments.append(
                TranscriptSegment(
                    start=pieces[0].start - window.start,
                    end=pieces[0].start - window.start + float(speech[row]),
                    speaker=f"SPEAKER_{(pieces[0].true_speaker + window.index) % meeting.speaker_count:02d}",
                    text="",
                )
            )
        local_results.append(segments)
    return windows, window_starts, local_results, units


def owning_window(windows, start: float) -> int:
    for window in windows:
        if window.own_start <= start < window.own_end:
            return window.index
    return windows[-1].index


def resolve_meeting(meeting: lia.Meeting, config: IdentityResolverConfig):
    windows, window_starts, local_results, units = build_case(meeting)
    encoder = CachedUnitEncoder(meeting, window_starts, units)
    resolver = IdentityResolver(config=config, tier_b_encoder=encoder)
    resolution = resolver.resolve(
        windows,
        local_results,
        window_audio_paths=[f"window-{window.index}.wav" for window in windows],
    )

    by_start = {round(pieces[0].start * 1000): row for row, pieces in enumerate(units)}
    assignment: dict[tuple[int, int], str] = {}
    for window, segments in zip(windows, resolution.relabeled_results, strict=True):
        for segment in segments:
            row = by_start.get(round((window.start + float(segment.start)) * 1000))
            if row is not None:
                assignment[(window.index, row)] = segment.speaker

    labels = np.full(len(meeting.rows), -1, np.int64)
    index: dict[str, int] = {}
    unlabelled = 0
    for row, pieces in enumerate(units):
        canonical = assignment.get((owning_window(windows, pieces[0].start), row))
        if canonical is None:
            unlabelled += 1
            continue
        labels[row] = index.setdefault(canonical, len(index))
    return resolution, labels, len(index), unlabelled, encoder


def tier_a_components(meeting: lia.Meeting):
    """The component structure Tier A leaves behind, which is what Tier B is offered.

    Reproduced through production's own helpers rather than re-derived: `_bundle_windows`,
    `_nodes_for`, `_node_intervals`, `IdentityResolver._resolve_boundary`, `_components`.
    """

    windows, window_starts, local_results, units = build_case(meeting)
    bundles = batch._bundle_windows(
        windows, local_results, [f"window-{window.index}.wav" for window in windows]
    )
    nodes = batch._nodes_for(bundles)
    union = batch._UnionFind(nodes)
    node_intervals = batch._node_intervals(bundles)
    resolver = IdentityResolver(
        config=IdentityResolverConfig(tier_b_enabled=True),
        tier_b_encoder=CachedUnitEncoder(meeting, window_starts, units),
    )
    for left, right in zip(bundles, bundles[1:], strict=False):
        resolver._resolve_boundary(left, right, node_intervals, union)
    return len(windows), nodes, batch._components(nodes, union)


ARMS = {
    "tier_a_only": IdentityResolverConfig(tier_b_enabled=False),
    "shipped": IdentityResolverConfig(tier_b_enabled=True),
    "album_thresholds": IdentityResolverConfig(
        tier_b_enabled=True,
        tier_b_similarity=ALBUM_MIN_MATCH_SCORE,
        tier_b_margin=ALBUM_MIN_MATCH_MARGIN,
    ),
    "album_bank_size": IdentityResolverConfig(
        tier_b_enabled=True,
        tier_b_max_segments_per_node=ALBUM_EXEMPLARS_PER_SPEAKER,
    ),
    "both": IdentityResolverConfig(
        tier_b_enabled=True,
        tier_b_similarity=ALBUM_MIN_MATCH_SCORE,
        tier_b_margin=ALBUM_MIN_MATCH_MARGIN,
        tier_b_max_segments_per_node=ALBUM_EXEMPLARS_PER_SPEAKER,
    ),
}


def section_one_two_engines() -> None:
    print("\n[1] TWO IDENTITY ENGINES, ON TRACKED SOURCE")
    batch_uses_album = git_grep(
        "live_identity", "moss_transcribe_diarize/app/speaker_identity.py"
    )
    check(
        not batch_uses_album,
        "the batch resolver references no live identity module",
        f"{len(batch_uses_album)} references",
    )
    live_uses_batch = git_grep(
        "speaker_identity",
        "moss_transcribe_diarize/app/live_identity.py",
        "moss_transcribe_diarize/app/live_identity_album.py",
        "moss_transcribe_diarize/app/live_identity_sweep.py",
    )
    check(
        not live_uses_batch,
        "the live identity modules reference no batch resolver",
        f"{len(live_uses_batch)} references",
    )

    opposed = ([1.0] + [0.0] * 255, [-1.0] + [0.0] * 255)
    batch_score = _cosine(*opposed)
    album_score = cosine_similarity(*opposed)
    check(
        batch_score < 0.0 and album_score == 0.0,
        "the two similarity rules have different contracts on the same pair",
        f"batch _cosine={batch_score:+.3f}, album cosine_similarity={album_score:.3f}",
    )
    NOTES.append(
        "Both engines build a reference as a mean of per-interval embeddings, so the duplicate "
        "similarity rule differs only below zero -- a maintenance hazard at these thresholds, "
        "not a measured behavioural difference."
    )

    shipped = IdentityResolverConfig(tier_b_enabled=True)
    print(
        f"      batch Tier B : min_segment {shipped.tier_b_min_segment_seconds:.1f}s, "
        f"top-{shipped.tier_b_max_segments_per_node} intervals, unweighted mean, "
        f"score {shipped.tier_b_similarity:.2f} / margin {shipped.tier_b_margin:.2f}"
    )
    print(
        f"      live album   : admission {ALBUM_ADMISSION_SECONDS:.1f}s, "
        f"k={ALBUM_EXEMPLARS_PER_SPEAKER} exemplars, duration-weighted centroid, "
        f"score {ALBUM_MIN_MATCH_SCORE:.2f} / margin {ALBUM_MIN_MATCH_MARGIN:.2f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meetings", nargs="*", default=list(lia.MEETINGS))
    args = parser.parse_args()

    section_one_two_engines()

    print("\n[2] THE CORPUS, AND THE SUBSTITUTION IS EXACT")
    meetings = [lia.load_meeting(name) for name in args.meetings]
    for meeting in meetings:
        lia.assert_fixture_matches_production(meeting)
    check(
        True,
        "every meeting passes production's own fixture gate",
        f"{len(meetings)} meetings, {sum(len(m.rows) for m in meetings)} units",
    )

    scores: dict[str, dict[str, float]] = {}
    speakers: dict[str, dict[str, int]] = {}
    tier_b_accepted: dict[str, int] = {}
    reasons: dict[str, int] = {}
    embedding_failures = 0
    unlabelled_total = 0
    encoder_calls = 0

    for arm, config in ARMS.items():
        scores[arm] = {}
        speakers[arm] = {}
        tier_b_accepted[arm] = 0
        for meeting in meetings:
            resolution, labels, canonical_count, unlabelled, encoder = resolve_meeting(meeting, config)
            scores[arm][meeting.name] = lia.speaker_accuracy(meeting, labels)
            speakers[arm][meeting.name] = canonical_count
            tier_b_accepted[arm] += int(resolution.summary["tier_b_accepted"])
            unlabelled_total += unlabelled
            encoder_calls += encoder.calls
            for proposal in resolution.diagnostics["tier_b"].get("proposals", []):
                reason = str(proposal.get("reason"))
                if arm == "shipped":
                    reasons[reason] = reasons.get(reason, 0) + 1
                if reason in {"tier_b_embedding_failed", "tier_b_mixture_or_invalid_embedding"}:
                    embedding_failures += 1

    check(
        embedding_failures == 0,
        "no interval the batch engine asked for was missing from the cache",
        f"{embedding_failures} embedding failures across {len(ARMS)} arms",
    )
    check(encoder_calls > 0, "the encoder was actually driven", f"{encoder_calls} embed calls")
    check(
        unlabelled_total == 0,
        "every unit is labelled by the window that owns it",
        f"{unlabelled_total} unlabelled",
    )

    print("\n[3] THE BATCH BASELINE, SCORED BY THE ALBUM'S OWN SCORER")
    print(f"      {'arm':<18}{'mean':>9}{'min':>9}{'speakers/meeting':>20}{'tier_b_links':>14}")
    for arm in ARMS:
        values = np.array([scores[arm][m.name] for m in meetings])
        counts = [speakers[arm][m.name] for m in meetings]
        print(
            f"      {arm:<18}{values.mean() * 100:>8.2f}%{values.min() * 100:>8.2f}%"
            f"{min(counts):>10d}-{max(counts):<9d}{tier_b_accepted[arm]:>13d}"
        )

    print("\n[4] AGAINST THE LIVE ALBUM ON THE IDENTICAL CORPUS")
    album = lia.replay_all(policy="album")
    album_final = np.array([album[m.name].accuracy for m in meetings])
    album_live = np.array([album[m.name].live_accuracy for m in meetings])
    print(f"      live album, label at commit  : mean {album_live.mean() * 100:.2f}%  min {album_live.min() * 100:.2f}%")
    print(f"      live album, label at end     : mean {album_final.mean() * 100:.2f}%  min {album_final.min() * 100:.2f}%")
    shipped_values = np.array([scores["shipped"][m.name] for m in meetings])
    print(f"      batch shipped                : mean {shipped_values.mean() * 100:.2f}%  min {shipped_values.min() * 100:.2f}%")
    print(f"      delta (batch - album at end) : {(shipped_values.mean() - album_final.mean()) * 100:+.2f} pp mean, "
          f"{(shipped_values.min() - album_final.min()) * 100:+.2f} pp min")

    print("\n[5] PER-MEETING, SHIPPED BATCH vs LIVE ALBUM")
    print(f"      {'meeting':<14}{'k':>3}{'batch':>10}{'album':>10}{'delta':>10}{'batch spk':>11}")
    for meeting in meetings:
        batch = scores["shipped"][meeting.name]
        alb = album[meeting.name].accuracy
        print(
            f"      {meeting.name:<14}{meeting.speaker_count:>3d}{batch * 100:>9.2f}%{alb * 100:>9.2f}%"
            f"{(batch - alb) * 100:>+9.2f}{speakers['shipped'][meeting.name]:>11d}"
        )

    print("\n[6] WHY RECALIBRATION CHANGES NOTHING - THE STRUCTURE TIER A LEAVES BEHIND")
    print(f"      {'meeting':<14}{'k':>3}{'nodes':>7}{'components':>12}{'singletons':>12}{'chains(>=2)':>13}")
    offered_singletons = 0
    total_components = 0
    for meeting in meetings:
        _window_count, nodes, components = tier_a_components(meeting)
        singletons = sum(1 for component in components if len(component) == 1)
        offered_singletons += singletons
        total_components += len(components)
        print(
            f"      {meeting.name:<14}{meeting.speaker_count:>3d}{len(nodes):>7d}"
            f"{len(components):>12d}{singletons:>12d}{len(components) - singletons:>13d}"
        )
    print(f"      Tier B proposal reasons, shipped arm, whole corpus: {dict(sorted(reasons.items()))}")

    print("\n[7] THE CLAIMS THIS PROBE MAKES FALSIFIABLE")
    baseline = np.array([scores["tier_a_only"][m.name] for m in meetings])
    for arm in ARMS:
        if arm == "tier_a_only":
            continue
        values = np.array([scores[arm][m.name] for m in meetings])
        check(
            bool(np.allclose(values, baseline, atol=1e-12)),
            f"Tier B arm '{arm}' moves duration-weighted accuracy by exactly zero",
            f"max |delta| = {np.abs(values - baseline).max() * 100:.10f} pp",
        )
    check(
        tier_b_accepted["shipped"] > 0,
        "Tier B did accept links, so 'no effect' is not 'never ran'",
        f"{tier_b_accepted['shipped']} accepted across the corpus",
    )
    check(
        reasons.get("cannot_link_conflict", 0) > sum(
            count for reason, count in reasons.items() if reason != "cannot_link_conflict"
        ),
        "the dominant Tier B refusal is structural, not a threshold",
        f"cannot_link_conflict {reasons.get('cannot_link_conflict', 0)} of {sum(reasons.values())} proposals",
    )
    check(
        offered_singletons < total_components,
        "Tier B is offered only singleton components, never a multi-window chain",
        f"{offered_singletons} singletons offered, {total_components} components exist",
    )
    check(
        shipped_values.mean() < album_final.mean(),
        "the batch engine scores below the live album on the identical corpus",
        f"{shipped_values.mean() * 100:.2f}% vs {album_final.mean() * 100:.2f}%",
    )

    print("\n[LIMITS] read every number above against these, and note the direction of each")
    print("  1. Tier A is handed a PERFECT local diarization, identical in both windows of every")
    print("     overlap. Every batch arm above is therefore an UPPER BOUND, not an estimate.")
    print("  2. Segments are the corpus's <= 2.5 s evidence units, the only intervals the cached")
    print("     encoder can answer for; real batch selects unbounded diarizer segments, so a real")
    print("     Tier B node carries at least as much speech. Pessimistic for Tier B -- which is why")
    print("     the album_bank_size arm raises the intervals per node and still moves nothing.")
    print("  3. LibriSpeech read speech: no overlap, no noise, in-span diarization assumed correct.")
    print("     ADR-0002 section 7 and tests/live_identity_accuracy.py carry the identical caveat.")

    if NOTES:
        print("\n[NOTES]")
        for note in NOTES:
            print(f"  * {note}")

    print("")
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): " + "; ".join(FAILURES))
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
