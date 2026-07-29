#!/usr/bin/env python3
"""Does sweep ambiguity track REFERENCES PER REAL VOICE?  The decisive experiment iteration 4
of run 20260729-094359 named and could not run.

WHY THIS EXISTS.  Three iterations have now moved candidates 55/60/65 on the same quantity:

  * iteration 3 measured that F2's deployed sweep answers `kept_ambiguous` on every unit and
    blamed provisional STAND-INS in the sweep's reference set;
  * iteration 4 falsified that with `album-bank-shape-probe.py` -- an all-stand-in fixture
    still produced 140 corrections -- and left behind a three-point correlation instead:
    ambiguity tracks references per real voice (1.40 -> 1.1 %, 1.77 -> 11.4 %), and F2's
    shape is 16 canonical speakers for 2 real voices = 8.0;
  * iteration 4's own recommended next step was to reach F2's ratio on the real fixture, and
    it recorded that "no current knob produces that without also moving the matcher".

TWO EXPERIMENTS, because the obvious knob is confounded and the probe says so rather than
picking the flattering one.

EXPERIMENT A -- THE BIRTH LADDER.  `sweep()` takes its own `config` argument
(`live_identity_sweep.py:330`), and `tests/live_identity_accuracy.replay` happens to pass it
the *live* one.  So arm A raises the LIVE matcher's `min_match_score` -- which starves
matching and births canonical speakers up to the 16-speaker cap -- while PINNING the sweep's
matcher at the deployed 0.35/0.1.  The `following` arm keeps the harness's own behaviour
(sweep matcher = live matcher) and is printed beside it, because that is the confounded
measurement pinning exists to avoid: without it, "more references" and "stricter matcher"
cannot be told apart.  **A's own limit, stated before its numbers:** starving the live matcher
also wrecks the labels the album learns from, so A varies reference QUALITY as well as
reference COUNT and cannot attribute an effect to either alone.

EXPERIMENT B -- SHARD THE ALBUM.  B holds the entire live path at the deployed 0.35/0.1 and
changes only what the sweep matches against: each album speaker's own exemplars are
redistributed across `m` labels through the album's **public `observe`** API, so every
reference is a real vector of a real voice and the only variable is how many labels one voice
is spread over.  Two modes, and the contrast between them is the point:

  banked       every shard is admitted, so `_album_view` may merge shards back together
  provisional  every shard is held sub-admission, so it is a stand-in -- and a merge needs an
               admitted bank on BOTH sides (Phase N decision 7), so no shard can ever merge

`provisional` is F2's measured shape: 14 of its 16 canonical speakers hold nothing but the
fragment that minted them.  If `banked` stays healthy while `provisional` goes ambiguous, the
mechanism is not "stand-ins are confusable" (iteration 4 falsified that) but "stand-ins are
UNMERGEABLE, so multiplicity survives into the reference set" -- which reconciles iterations 3
and 4 instead of choosing between them.

WHAT IS REAL.  The production `FingerprintAlbum`, `WeSpeakerLiveEvidenceProvider`,
`BoundedCausalIdentityPreparer`, `SweepLedger`, `_album_view` and `sweep()`, driven by the
tracked accuracy harness over the real encoder's vectors.  `sweep` is wrapped call-through,
never replaced, and the sharded album is built by the production admission rules rather than
by writing its private state.  No product source, no test source and no fixture is modified.

WHAT NEITHER CAN SAY, recorded before the numbers so they are not over-read.  Both experiments
model F2's shape on LibriSpeech read speech; neither observes m4mbp's own vectors, which
nothing retains today.  They can show what multiplicity is sufficient to cause; they cannot
show that it is what happened on the deployed system.

rc=0 measured and printed; rc=2 a named refusal (harness or fixture unreadable).
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))


def refuse(message: str) -> int:
    print(f"REFUSED: {message}")
    return 2


try:
    import live_identity_accuracy as H
    from moss_transcribe_diarize.app.live_identity import LiveIdentityConfig
    from moss_transcribe_diarize.app.live_identity_album import FingerprintAlbum
    from moss_transcribe_diarize.app.live_identity_sweep import _album_view
except Exception as error:  # noqa: BLE001 - a named refusal, never a traceback
    print(f"REFUSED: the accuracy harness would not import ({error!r})")
    sys.exit(2)


# The live matcher scores that produce the birth ladder. 0.35 is deployed and is the probe's
# positive control -- pinned and following must agree there, and both must reproduce the
# tracked 93.44 / 99.26. The rest are deliberate extremes chosen to sweep the ratio, not
# candidate settings: nothing here proposes changing the live matcher.
LIVE_SCORES = (0.35, 0.50, 0.70, 0.85, 0.95)
# Experiment B's shard counts. m=1 is the positive control -- one shard is the album itself,
# so `banked` m=1 must reproduce the tracked deployed numbers exactly. m=8 is F2's own ratio.
SHARD_COUNTS = (1, 2, 4, 8)
# What the sweep's matcher is pinned to in the `pinned` arm: the deployed live configuration,
# read off the module that names it rather than copied.
SWEEP_SCORE = H.ADR_MIN_MATCH_SCORE
SWEEP_MARGIN = H.ADR_MIN_MATCH_MARGIN
# F1 and F2's own measured shapes, for the reader to place the fixture's points against.
REAL_MEETING_RATIOS = {"F1 (12 canonical / 2 voices)": 6.0, "F2 (16 canonical / 2 voices)": 8.0}


def measure(name: str, *, live_score: float, pin_sweep: bool) -> dict:
    """One meeting at one live matcher score, with the sweep's matcher pinned or following."""

    dispositions: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    reference_counts: list[int] = []
    real_sweep = H.sweep
    pinned_config = LiveIdentityConfig(
        max_speakers=H.MAX_SPEAKERS,
        min_match_score=SWEEP_SCORE,
        min_match_margin=SWEEP_MARGIN,
    )

    def observed_sweep(*, ledger, album, config, merge_threshold):
        revision = real_sweep(
            ledger=ledger,
            album=album,
            config=pinned_config if pin_sweep else config,
            merge_threshold=merge_threshold,
        )
        dispositions.update(dict(revision.dispositions))
        reasons.update(item.reason for item in revision.corrections)
        references, _leader_of, _merges = _album_view(album, merge_threshold)
        reference_counts.append(len(references))
        return revision

    H.sweep = observed_sweep
    try:
        result = H.replay(
            H.load_meeting(name),
            policy="album",
            min_match_score=live_score,
            min_match_margin=H.ADR_MIN_MATCH_MARGIN,
            sweep_interval=H.SWEEP_INTERVAL_SECONDS,
        )
    finally:
        H.sweep = real_sweep

    voices = H.load_meeting(name).speaker_count
    units = sum(dispositions.values())
    ambiguous = dispositions.get("kept_ambiguous", 0)
    # The final sweep's reference set is what a session-end sweep would match against, which is
    # the shape the deployed system's `finalize_identity` sees.
    references = reference_counts[-1] if reference_counts else 0
    return {
        "meeting": name,
        "voices": voices,
        "canonical": result.canonical_speaker_count,
        "references": references,
        "refs_per_voice": references / voices if voices else 0.0,
        "units": units,
        "ambiguous": ambiguous,
        "ambiguous_share": (ambiguous / units) if units else 0.0,
        "corrections": result.corrections,
        "merges": result.merges,
        "residual": result.residual_corrections,
        "abstained_spans": result.abstained_spans,
        "live_accuracy": result.live_accuracy,
        "accuracy": result.accuracy,
        "dispositions": dict(dispositions),
        "reasons": dict(reasons),
    }


def run_arm(pin_sweep: bool) -> list[dict]:
    arm = (
        f"PINNED   sweep matcher fixed at the deployed {SWEEP_SCORE:g}/{SWEEP_MARGIN:g}"
        if pin_sweep
        else "FOLLOWING sweep matcher moves with the live one (the confounded measurement)"
    )
    print(f"\n=== {arm} ===")
    print(
        f"{'live':>6}{'meeting':<12}{'voices':>7}{'canon':>6}{'refs':>6}{'r/voice':>9}"
        f"{'ambig':>7}{'units':>7}{'ambig%':>8}{'corr':>6}{'merge':>6}{'live%':>8}{'final%':>8}"
    )
    rows: list[dict] = []
    for live_score in LIVE_SCORES:
        for name in H.MEETINGS:
            row = measure(name, live_score=live_score, pin_sweep=pin_sweep)
            row["live_score"] = live_score
            rows.append(row)
            print(
                f"{live_score:>6.2f}{row['meeting']:<12}{row['voices']:>7}{row['canonical']:>6}"
                f"{row['references']:>6}{row['refs_per_voice']:>9.2f}"
                f"{row['ambiguous']:>7}{row['units']:>7}{row['ambiguous_share'] * 100:>8.1f}"
                f"{row['corrections']:>6}{row['merges']:>6}"
                f"{row['live_accuracy'] * 100:>8.2f}{row['accuracy'] * 100:>8.2f}"
            )
        band = [row for row in rows if row["live_score"] == live_score]
        _print_band(f"  live {live_score:.2f} TOTAL", band)
    return rows


def _print_band(label: str, rows: list[dict]) -> None:
    units = sum(row["units"] for row in rows)
    ambiguous = sum(row["ambiguous"] for row in rows)
    references = sum(row["references"] for row in rows)
    voices = sum(row["voices"] for row in rows)
    print(
        f"{label}: refs {references}/{voices} voices = {references / voices:.2f} per voice, "
        f"kept_ambiguous {ambiguous}/{units} ({(ambiguous / units * 100) if units else 0:.1f} %), "
        f"corrections {sum(row['corrections'] for row in rows)}, "
        f"merges {sum(row['merges'] for row in rows)}, "
        f"live {sum(row['live_accuracy'] for row in rows) / len(rows) * 100:.2f} % -> "
        f"final {sum(row['accuracy'] for row in rows) / len(rows) * 100:.2f} %"
    )


def _curve(rows: list[dict]) -> None:
    """Ambiguity against references per real voice, binned over every (meeting, score) point.

    Binned rather than fitted: the question is whether the share rises across the range that
    contains F1's 6.0 and F2's 8.0, and a slope through 40 points would claim more precision
    than eight meetings can carry.
    """

    edges = ((0.0, 1.5), (1.5, 2.5), (2.5, 4.0), (4.0, 6.0), (6.0, 100.0))
    print(f"\n{'refs per real voice':<22}{'points':>7}{'units':>8}{'ambiguous':>11}{'share':>8}")
    for low, high in edges:
        band = [row for row in rows if low <= row["refs_per_voice"] < high]
        if not band:
            continue
        units = sum(row["units"] for row in band)
        ambiguous = sum(row["ambiguous"] for row in band)
        label = f"[{low:g}, {high:g})" if high < 100 else f"[{low:g}, inf)"
        print(
            f"{label:<22}{len(band):>7}{units:>8}{ambiguous:>11}"
            f"{(ambiguous / units * 100) if units else 0:>7.1f}%"
        )


def _shard(album: FingerprintAlbum, *, shards: int, banked: bool) -> FingerprintAlbum:
    """A copy of `album` with every speaker's own exemplars spread over `shards` labels.

    Built through the production `observe`, so the copy is an album the production admission
    rules could have produced: nothing writes `_exemplars` or `_provisional` directly, and the
    admitted/provisional distinction is decided by the same duration gate the live path uses.

    Shard 0 keeps the speaker's own name, so a ledger unit's incumbent label still resolves.
    A speaker holding only a stand-in has one vector and cannot be split; it is copied through
    unchanged and counted, because pretending it sharded would inflate the ratio under test.
    """

    copy = FingerprintAlbum(
        admission_seconds=album.admission_seconds,
        exemplars_per_speaker=album.exemplars_per_speaker,
    )
    # Half the admission gate: a duration the production `observe` must route to the stand-in
    # branch, chosen from the album's own gate rather than as a constant so the two stay tied.
    below_admission = album.admission_seconds / 2.0
    for speaker in album.speakers():
        bank = album.exemplars(speaker)
        if not bank:
            reference = album.reference(speaker)
            if reference is not None:
                copy.observe(
                    canonical_speaker=speaker,
                    vector=reference,
                    duration_sec=below_admission,
                    span_id=0,
                )
            continue
        for position, exemplar in enumerate(bank):
            index = position % shards
            label = speaker if index == 0 else f"{speaker}~{index}"
            copy.observe(
                canonical_speaker=label,
                vector=exemplar.vector,
                duration_sec=(
                    exemplar.duration_sec if banked else min(exemplar.duration_sec, below_admission)
                ),
                span_id=exemplar.span_id,
            )
    return copy


def measure_sharded(name: str, *, shards: int, banked: bool) -> dict:
    """One meeting at the deployed configuration, swept against a sharded album."""

    dispositions: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    reference_counts: list[int] = []
    real_sweep = H.sweep

    def observed_sweep(*, ledger, album, config, merge_threshold):
        sharded = _shard(album, shards=shards, banked=banked) if shards > 1 or not banked else album
        revision = real_sweep(
            ledger=ledger, album=sharded, config=config, merge_threshold=merge_threshold
        )
        dispositions.update(dict(revision.dispositions))
        reasons.update(item.reason for item in revision.corrections)
        references, _leader_of, _merges = _album_view(sharded, merge_threshold)
        reference_counts.append(len(references))
        return revision

    H.sweep = observed_sweep
    try:
        result = H.replay(
            H.load_meeting(name), policy="album", sweep_interval=H.SWEEP_INTERVAL_SECONDS
        )
    finally:
        H.sweep = real_sweep

    voices = H.load_meeting(name).speaker_count
    units = sum(dispositions.values())
    ambiguous = dispositions.get("kept_ambiguous", 0)
    references = reference_counts[-1] if reference_counts else 0
    return {
        "meeting": name,
        "voices": voices,
        "canonical": result.canonical_speaker_count,
        "references": references,
        "refs_per_voice": references / voices if voices else 0.0,
        "units": units,
        "ambiguous": ambiguous,
        "ambiguous_share": (ambiguous / units) if units else 0.0,
        "corrections": result.corrections,
        "merges": result.merges,
        "residual": result.residual_corrections,
        "live_accuracy": result.live_accuracy,
        "accuracy": result.accuracy,
        "dispositions": dict(dispositions),
        "reasons": dict(reasons),
    }


def run_shard_arm(banked: bool) -> list[dict]:
    mode = (
        "BANKED      every shard is admitted, so `_album_view` may merge shards back together"
        if banked
        else "PROVISIONAL every shard is a sub-admission stand-in, so no shard can ever merge"
        " -- F2's shape"
    )
    print(f"\n=== shard the album: {mode} ===")
    print(
        f"{'m':>4}{'meeting':<12}{'voices':>7}{'canon':>6}{'refs':>6}{'r/voice':>9}"
        f"{'ambig':>7}{'units':>7}{'ambig%':>8}{'corr':>6}{'merge':>6}{'live%':>8}{'final%':>8}"
    )
    rows: list[dict] = []
    for shards in SHARD_COUNTS:
        for name in H.MEETINGS:
            row = measure_sharded(name, shards=shards, banked=banked)
            row["shards"] = shards
            rows.append(row)
            print(
                f"{shards:>4}{row['meeting']:<12}{row['voices']:>7}{row['canonical']:>6}"
                f"{row['references']:>6}{row['refs_per_voice']:>9.2f}"
                f"{row['ambiguous']:>7}{row['units']:>7}{row['ambiguous_share'] * 100:>8.1f}"
                f"{row['corrections']:>6}{row['merges']:>6}"
                f"{row['live_accuracy'] * 100:>8.2f}{row['accuracy'] * 100:>8.2f}"
            )
        _print_band(f"  m={shards} TOTAL", [row for row in rows if row["shards"] == shards])
    return rows


def main() -> int:
    try:
        H.load_meeting(H.MEETINGS[0])
    except Exception as error:  # noqa: BLE001
        return refuse(f"the accuracy fixture would not load ({error!r})")

    print(
        "Does sweep ambiguity track REFERENCE MULTIPLICITY? -- production code, real encoder\n"
        "geometry, 8 LibriSpeech meetings. The live matcher's score is raised to force births\n"
        f"up to the {H.MAX_SPEAKERS}-speaker cap; the sweep's matcher is held at the deployed "
        f"{SWEEP_SCORE:g}/{SWEEP_MARGIN:g}.\n"
        "Real meetings for scale: "
        + ", ".join(f"{name} = {ratio:.1f}" for name, ratio in REAL_MEETING_RATIOS.items())
    )

    print("\n\n##### EXPERIMENT A -- the birth ladder (varies count AND quality) #####")
    pinned = run_arm(pin_sweep=True)
    following = run_arm(pin_sweep=False)

    print("\n=== the curve: ambiguity vs references per real voice (PINNED arm) ===")
    _curve(pinned)
    print("\n=== the same curve when the sweep matcher is NOT pinned (FOLLOWING arm) ===")
    _curve(following)

    print("\n\n##### EXPERIMENT B -- shard the album (varies count ALONE) #####")
    print(
        "The live path is the deployed 0.35/0.1 in every row here; only the reference set the\n"
        "sweep matches against changes, and every reference is a real vector of a real voice."
    )
    banked = run_shard_arm(banked=True)
    provisional = run_shard_arm(banked=False)

    print("\n=== the curve: ambiguity vs references per real voice (BANKED shards) ===")
    _curve(banked)
    print("\n=== the curve: ambiguity vs references per real voice (PROVISIONAL shards) ===")
    _curve(provisional)

    print("\n=== what this decides ===")
    control = [row for row in pinned if row["live_score"] == LIVE_SCORES[0]]
    print(
        "Positive control -- at the deployed live 0.35 A's two arms are the same configuration:\n"
        f"  refs/voice {sum(r['references'] for r in control) / sum(r['voices'] for r in control):.2f}, "
        f"corrections {sum(r['corrections'] for r in control)}, "
        f"live {sum(r['live_accuracy'] for r in control) / len(control) * 100:.2f} % -> "
        f"final {sum(r['accuracy'] for r in control) / len(control) * 100:.2f} % "
        "(iteration 4 measured 1.40, 116, 93.44 -> 99.26)"
    )
    _decide_high("A pinned", [row for row in pinned if row["refs_per_voice"] >= 6.0])
    for label, rows in (("B banked", banked), ("B provisional", provisional)):
        for shards in SHARD_COUNTS:
            _decide_band(f"{label} m={shards}", [row for row in rows if row["shards"] == shards])
    return 0


def _decide_band(label: str, rows: list[dict]) -> None:
    if not rows:
        return
    units = sum(row["units"] for row in rows)
    ambiguous = sum(row["ambiguous"] for row in rows)
    references = sum(row["references"] for row in rows)
    voices = sum(row["voices"] for row in rows)
    print(
        f"  {label:<18} refs/voice {references / voices:>5.2f}  "
        f"kept_ambiguous {(ambiguous / units * 100) if units else 0:>5.1f} %  "
        f"corrections {sum(row['corrections'] for row in rows):>4}  "
        f"merges {sum(row['merges'] for row in rows):>3}  "
        f"final {sum(row['accuracy'] for row in rows) / len(rows) * 100:>6.2f} %"
    )


def _decide_high(label: str, rows: list[dict]) -> None:
    if not rows:
        print(
            f"  {label}: NO point reached F1's 6.0 references per real voice, so this arm "
            "cannot speak to F2's 8.0."
        )
        return
    units = sum(row["units"] for row in rows)
    ambiguous = sum(row["ambiguous"] for row in rows)
    print(
        f"  {label:<18} at >= 6.0 refs/voice ({len(rows)} meeting points): "
        f"kept_ambiguous {(ambiguous / units * 100) if units else 0:.1f} %, "
        f"corrections {sum(row['corrections'] for row in rows)}"
    )


if __name__ == "__main__":
    sys.exit(main())
