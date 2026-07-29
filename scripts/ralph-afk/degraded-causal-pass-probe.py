#!/usr/bin/env python3
"""Step 4's counterfactual under an IMPERFECT causal pass -- §6(7) of the authorization request.

Iteration 17 priced the engine Phase N step 4 would replace (production `IdentityResolver`:
**80.07 % mean / 63.33 % min**) and iteration 18 priced its replacement (the production live
album engine over the *identical* windows: **100.00 % / 100.00 %**, +19.93 pp). Both numbers
were measured with a **perfect local diarization** -- `build_case` hands every window the true
speaker of every unit, rotated per window so the labels are window-arbitrary. Two limits fell
out of that and both were recorded rather than closed:

  * §6(6) -- the 100 % is a **ceiling**. It says the album stitches a separable task perfectly;
    it does not say what batch unification would score on a real one.
  * §6(7) -- the sweep half is **untested**. Production `sweep()` proposed **0** corrections and
    **0** merges on the batch path, because the causal pass was already perfect. That is
    convergence by *vacuity*, not evidence that ADR-0002 step 3's machinery helps a batch
    resolver.

This probe closes both by making the causal pass wrong on purpose, in the two ways a real local
diarizer is wrong, and handing the **identical** degraded input to **both** engines.

THE DEGRADATIONS, AND WHY THESE TWO.
  * `split` -- **over-segmentation.** One true speaker's turn inside one window is cut into two
    local labels at a contiguous boundary, which is what a diarizer does when it hears a turn
    change that is not there. This is the degradation ADR-0002's sweep **merge** exists for: the
    two halves are the same voice, so their album centroids agree far above the 0.70 merge
    threshold, and a sweep that cannot collapse them cannot repair anything.
  * `confuse` -- **label confusion.** A segment is attributed to another speaker present in the
    same window. This does not add a node; it poisons one, so an album centroid is a blend. It
    is the degradation a merge can **not** repair, and it is here so a win under `split` cannot
    be read as a win under any error.

Both are **label-only**: window geometry, unit intervals, the encoder cache and the truth array
are untouched, so nothing downstream has to re-derive a mapping and no cross-speaker overlap is
invented. That is the whole reason the degradation is applied to labels rather than to audio.

HOW ONE INPUT REACHES TWO ENGINES. `base.build_case` is monkeypatched, not copied. Both arms
call it through the same module attribute -- `resolve_meeting` as a bare global, `album_arm`
and `tier_a_component_map` through `base.` -- so the batch resolver and the album engine
provably see the same `local_results` object. The degradation is a pure function of
(meeting, mode, rate) seeded by CRC32, and memoised, so the several calls each arm makes return
the identical labels.

THE CONTROL IS THE POINT. Condition `none` must reproduce iteration 17's and iteration 18's
published numbers to the last digit through this harness. If it does not, every degraded number
below is measuring the harness instead of the engines, and the run fails.

FIDELITY LIMITS, INHERITED AND NEW.
  1. Everything in the counterfactual probe's own list still applies: LibriSpeech read speech,
     no overlap, no noise; a query vector is a duration-weighted mean of per-unit embeddings.
  2. A synthetic label error is not a real diarizer's error distribution. A real one errs where
     the audio is hard -- short turns, overlaps, low energy -- and this one errs uniformly at
     random. So the degraded scores are **optimistic about which units break** and honest about
     **how many**. Read the engine *gap* and the sweep *counts*, not the absolute accuracy.
  3. `confuse` moves a unit's label without moving its audio, so the poisoned centroid is a true
     blend of two voices. That is the right shape for a diarizer confusion and the wrong shape
     for a diarizer that mislabels *silence*.
  4. The scoring denominator is unchanged, so a unit whose local label is wrong is counted
     against the engine even though no identity engine could have recovered it. That floor is
     **shared** by both arms, which is exactly why the comparison survives it.
  5. **The degradation moves labels and never boundaries**, and Tier A links on boundaries. So
     every Tier-A-using arm keeps a boundary overlap that a real over-segmenting diarizer would
     also have got wrong, and `tier_a_album` is an **upper bound**. It is not a biased
     comparison, because the batch baseline uses the same Tier A on the same exact intervals --
     the inflation is shared and the *gap* is the comparable quantity, while `album_only`, which
     reads no boundary at all, is the conservative arm. A boundary-jitter degradation is the
     next probe, not this one.

Offline. No host, no session, no network, no product change.
"""

from __future__ import annotations

import argparse
import importlib.util
import random
import sys
import zlib
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import live_identity_accuracy as lia  # noqa: E402  (path set above)
from moss_transcribe_diarize.app.speaker_identity import IdentityResolverConfig  # noqa: E402


def _load_module(module_name: str, filename: str):
    path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The counterfactual probe imports the baseline probe as `cf.base`, so loading it gives both
# engines' drivers from one place. Re-deriving either here is the one mistake this comparison
# cannot survive.
cf = _load_module("album_batch_counterfactual_probe", "album-batch-counterfactual-probe.py")
base = cf.base

FAILURES: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    print(f"  [{'OK' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)
    return ok


# --------------------------------------------------------------------------------------------
# The degradation


def _rng(meeting_name: str, mode: str, rate: float) -> random.Random:
    """Deterministic per (meeting, mode, rate) -- never a shared stream.

    `build_case` is called several times per arm and every call must return the same labels,
    so the seed cannot depend on call order. `hash()` is salted per process; CRC32 is not.
    """

    return random.Random(zlib.crc32(f"{meeting_name}|{mode}|{rate:.6f}".encode()))


def _split(segments: list, rng: random.Random, rate: float) -> list:
    """Over-segmentation: cut one local speaker's segments into two contiguous local labels."""

    by_local: dict[str, list[int]] = {}
    for position, segment in enumerate(segments):
        by_local.setdefault(segment.speaker, []).append(position)

    out = list(segments)
    for local in sorted(by_local):
        positions = by_local[local]
        if len(positions) < 2:
            continue  # a single segment cannot be cut without inventing an interval
        if rng.random() >= rate:
            continue
        ordered = sorted(positions, key=lambda index: float(segments[index].start))
        for index in ordered[len(ordered) // 2 :]:
            out[index] = replace(out[index], speaker=f"{local}__b")
    return out


def _confuse(segments: list, rng: random.Random, rate: float) -> list:
    """Label confusion: attribute a segment to another speaker present in the same window."""

    locals_present = sorted({segment.speaker for segment in segments})
    if len(locals_present) < 2:
        return list(segments)

    out = list(segments)
    for position, segment in enumerate(segments):
        if rng.random() >= rate:
            continue
        others = [name for name in locals_present if name != segment.speaker]
        out[position] = replace(segment, speaker=others[rng.randrange(len(others))])
    return out


DEGRADATIONS = {"none": None, "split": _split, "confuse": _confuse}

_PRISTINE_BUILD_CASE = base.build_case
_CASE_CACHE: dict[tuple[str, str, float], tuple] = {}
_CONDITION: dict[str, object] = {"mode": "none", "rate": 0.0}


def _build_case_degraded(meeting):
    mode = str(_CONDITION["mode"])
    rate = float(_CONDITION["rate"])
    key = (meeting.name, mode, rate)
    if key not in _CASE_CACHE:
        windows, window_starts, local_results, units = _PRISTINE_BUILD_CASE(meeting)
        apply = DEGRADATIONS[mode]
        if apply is not None:
            rng = _rng(meeting.name, mode, rate)
            local_results = [apply(segments, rng, rate) for segments in local_results]
        _CASE_CACHE[key] = (windows, window_starts, local_results, units)
    return _CASE_CACHE[key]


base.build_case = _build_case_degraded


# --------------------------------------------------------------------------------------------
# What the degradation actually did, measured rather than assumed


def causal_purity(meeting) -> dict[str, float]:
    """The local pass's own quality, in the three numbers that explain every score below.

    A *node* is one local speaker inside one window -- the unit both engines stitch.
      * `impure_nodes`   -- nodes holding more than one true speaker (`confuse` makes these).
      * `extra_nodes`    -- nodes beyond one per true speaker per window (`split` makes these).
      * `unit_error`     -- share of units whose node's majority true speaker is not their own,
                            i.e. the accuracy no identity engine can recover.
    """

    windows, _starts, local_results, units = base.build_case(meeting)
    row_of_start = {round(pieces[0].start * 1000): row for row, pieces in enumerate(units)}
    truth = meeting.rows[:, lia._TRUE_SPEAKER]

    nodes = 0
    impure = 0
    speakers_seen = 0
    wrong_units = 0
    total_units = 0
    for position, window in enumerate(windows):
        rows_by_local: dict[str, list[int]] = {}
        for segment in local_results[position]:
            rows_by_local.setdefault(segment.speaker, []).append(
                row_of_start[round((window.start + float(segment.start)) * 1000)]
            )
        window_truths: set[int] = set()
        for rows in rows_by_local.values():
            nodes += 1
            counts = Counter(int(truth[row]) for row in rows)
            window_truths.update(counts)
            if len(counts) > 1:
                impure += 1
            majority = counts.most_common(1)[0][0]
            wrong_units += sum(count for value, count in counts.items() if value != majority)
            total_units += sum(counts.values())
        speakers_seen += len(window_truths)

    return {
        "nodes": float(nodes),
        "impure_nodes": float(impure),
        "extra_nodes": float(nodes - speakers_seen),
        "unit_error": (wrong_units / total_units) if total_units else 0.0,
    }


# --------------------------------------------------------------------------------------------
# The three arms


def batch_arm(meeting) -> dict[str, float]:
    """`speaker_accuracy` returns a FRACTION; every number in this probe is a percent."""

    _resolution, labels, speakers, unlabelled, _encoder = base.resolve_meeting(
        meeting, IdentityResolverConfig(tier_b_enabled=True)
    )
    return {
        "accuracy": 100.0 * lia.speaker_accuracy(meeting, labels),
        "speakers": float(speakers),
        "unlabelled": float(unlabelled),
    }


def album_arm(meeting, *, swept: bool = False, use_tier_a: bool = False) -> dict[str, object]:
    row = dict(cf.album_arm(meeting, sweep_at_end=swept, use_tier_a=use_tier_a))
    row["accuracy"] = 100.0 * float(row["accuracy"])
    row["live_accuracy"] = 100.0 * float(row["live_accuracy"])
    return row


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def run_condition(meetings, mode: str, rate: float) -> dict[str, object]:
    _CONDITION["mode"] = mode
    _CONDITION["rate"] = rate

    purity = [causal_purity(meeting) for meeting in meetings]
    batch = [batch_arm(meeting) for meeting in meetings]
    album = [album_arm(meeting) for meeting in meetings]
    swept = [album_arm(meeting, swept=True) for meeting in meetings]
    tier_a = [album_arm(meeting, swept=True, use_tier_a=True) for meeting in meetings]

    batch_scores = [row["accuracy"] for row in batch]
    album_scores = [float(row["accuracy"]) for row in album]
    swept_scores = [float(row["accuracy"]) for row in swept]
    swept_live = [float(row["live_accuracy"]) for row in swept]
    tier_a_scores = [float(row["accuracy"]) for row in tier_a]

    sweeps = Counter()
    capacity = 0
    births = 0
    for row in swept:
        for field, value in dict(row["sweeps"]).items():  # type: ignore[arg-type]
            sweeps[field] += int(value)
        stats = dict(row["stats"])  # type: ignore[arg-type]
        capacity += int(stats.get("speaker_capacity_exceeded", 0))
        births += int(stats.get("births", 0))

    return {
        "mode": mode,
        "rate": rate,
        "batch_mean": _mean(batch_scores),
        "batch_min": min(batch_scores),
        "album_mean": _mean(album_scores),
        "album_min": min(album_scores),
        "swept_mean": _mean(swept_scores),
        "swept_min": min(swept_scores),
        "swept_live_mean": _mean(swept_live),
        "tier_a_mean": _mean(tier_a_scores),
        "tier_a_min": min(tier_a_scores),
        "album_speakers": sum(int(row["speakers"]) for row in album),  # type: ignore[arg-type]
        "batch_speakers": sum(int(row["speakers"]) for row in batch),
        "births": births,
        "corrections": sweeps["corrections"],
        "merges": sweeps["merges"],
        "residual": sweeps["residual"],
        "capacity_exceeded": capacity,
        "nodes": sum(int(row["nodes"]) for row in purity),
        "impure_nodes": sum(int(row["impure_nodes"]) for row in purity),
        "extra_nodes": sum(int(row["extra_nodes"]) for row in purity),
        "unit_error": _mean([row["unit_error"] for row in purity]),
        "per_meeting": [
            {
                "name": meeting.name,
                "batch": batch_scores[index],
                "album": album_scores[index],
                "swept": swept_scores[index],
                "tier_a": tier_a_scores[index],
            }
            for index, meeting in enumerate(meetings)
        ],
    }


# Iteration 17's and iteration 18's published numbers, which the `none` control reproduces.
PUBLISHED = {
    "batch_mean": 80.07,
    "batch_min": 63.33,
    "album_mean": 100.00,
    "album_min": 100.00,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meetings", nargs="*", default=list(lia.MEETINGS))
    parser.add_argument(
        "--split-rates",
        nargs="*",
        type=float,
        default=[0.30, 0.60],
        help="per (window, local speaker) probability that a turn is cut in two",
    )
    parser.add_argument(
        "--confuse-rates",
        nargs="*",
        type=float,
        default=[0.10, 0.25],
        help="per segment probability of attribution to another speaker in the same window",
    )
    args = parser.parse_args()

    print("[1] THE CORPUS, AND ONE BUILD_CASE FOR TWO ENGINES")
    meetings = [lia.load_meeting(name) for name in args.meetings]
    for meeting in meetings:
        lia.assert_fixture_matches_production(meeting)
    check(
        base.build_case is _build_case_degraded and cf.base is base,
        "both engines resolve `build_case` through the patched module attribute",
        f"{len(meetings)} meetings, {sum(len(m.rows) for m in meetings)} units",
    )

    conditions = [("none", 0.0)]
    conditions += [("split", rate) for rate in args.split_rates]
    conditions += [("confuse", rate) for rate in args.confuse_rates]

    results: list[dict[str, object]] = []
    for mode, rate in conditions:
        print(f"\n[2.{len(results)}] CONDITION {mode} @ {rate:.2f}")
        result = run_condition(meetings, mode, rate)
        results.append(result)
        print(
            f"      causal pass : {result['nodes']} nodes, {result['impure_nodes']} impure, "
            f"{result['extra_nodes']} extra, unit error {float(result['unit_error']) * 100:.2f} %"
        )
        print(
            f"      batch       : {float(result['batch_mean']):6.2f} % mean / "
            f"{float(result['batch_min']):6.2f} % min, {result['batch_speakers']} canonicals"
        )
        print(
            f"      album       : {float(result['album_mean']):6.2f} % mean / "
            f"{float(result['album_min']):6.2f} % min, {result['album_speakers']} canonicals"
        )
        print(
            f"      album+sweep : {float(result['swept_mean']):6.2f} % mean / "
            f"{float(result['swept_min']):6.2f} % min "
            f"(pre-sweep {float(result['swept_live_mean']):6.2f} %), "
            f"{result['corrections']} corrections, {result['merges']} merges, "
            f"{result['residual']} residual, {result['births']} births"
        )
        print(
            f"      tierA+album : {float(result['tier_a_mean']):6.2f} % mean / "
            f"{float(result['tier_a_min']):6.2f} % min"
        )

    control = results[0]

    print("\n[3] THE CONTROL REPRODUCES THE PUBLISHED NUMBERS")
    for field, published in PUBLISHED.items():
        measured = float(control[field])
        check(
            abs(measured - published) < 0.005,
            f"control {field} reproduces the published {published:.2f} %",
            f"measured {measured:.4f} %",
        )
    check(
        int(control["corrections"]) == 0 and int(control["merges"]) == 0,
        "the control's sweep is vacuous, exactly as §6(7) records",
        f"{control['corrections']} corrections, {control['merges']} merges",
    )
    check(
        int(control["impure_nodes"]) == 0 and int(control["extra_nodes"]) == 0,
        "the control's causal pass is perfect, which is what §6(6) calls a ceiling",
        f"{control['nodes']} nodes, unit error {float(control['unit_error']) * 100:.2f} %",
    )

    print("\n[4] THE DEGRADATIONS ARE REAL, NOT NOMINAL")
    for result in results[1:]:
        mode = str(result["mode"])
        if mode == "split":
            moved = int(result["extra_nodes"])
            check(
                moved > 0,
                f"{mode} @ {float(result['rate']):.2f} adds nodes the causal pass did not have",
                f"{moved} extra nodes over {result['nodes']}",
            )
        else:
            moved = int(result["impure_nodes"])
            check(
                moved > 0,
                f"{mode} @ {float(result['rate']):.2f} poisons nodes the causal pass held pure",
                f"{moved} impure nodes over {result['nodes']}, "
                f"unit error {float(result['unit_error']) * 100:.2f} %",
            )

    print("\n[5] §6(7) -- IS THE SWEEP STILL VACUOUS WHEN THE CAUSAL PASS IS NOT PERFECT?")
    split_results = [row for row in results if row["mode"] == "split"]
    non_vacuous = [row for row in split_results if int(row["merges"]) + int(row["corrections"]) > 0]
    check(
        bool(non_vacuous),
        "production sweep() proposes something once over-segmentation exists",
        ", ".join(
            f"split@{float(row['rate']):.2f}: {row['corrections']} corrections / "
            f"{row['merges']} merges"
            for row in split_results
        ),
    )
    for row in split_results:
        delta = float(row["swept_mean"]) - float(row["swept_live_mean"])
        print(
            f"      split@{float(row['rate']):.2f}: sweep moves the mean "
            f"{float(row['swept_live_mean']):.2f} % -> {float(row['swept_mean']):.2f} % "
            f"({delta:+.2f} pp), residual {row['residual']}"
        )
    for row in split_results:
        check(
            int(row["residual"]) == 0,
            f"split@{float(row['rate']):.2f} reaches a sweep fixpoint",
            f"residual {row['residual']}",
        )

    print("\n[6] §6(6) -- DOES THE ALBUM STILL WIN WHEN THE CEILING IS REMOVED?")
    print("      (a MEASUREMENT, not a contract: no check below fails on which engine wins)")
    print(
        "      condition        batch    album      gap    +sweep      gap    tierA      gap"
    )
    for result in results:
        batch_mean = float(result["batch_mean"])
        album_mean = float(result["album_mean"])
        swept_mean = float(result["swept_mean"])
        tier_a_mean = float(result["tier_a_mean"])
        print(
            f"      {str(result['mode']):7s}@{float(result['rate']):.2f}  "
            f"{batch_mean:6.2f} %  {album_mean:6.2f} %  {album_mean - batch_mean:+6.2f}  "
            f"{swept_mean:6.2f} %  {swept_mean - batch_mean:+6.2f}  "
            f"{tier_a_mean:6.2f} %  {tier_a_mean - batch_mean:+6.2f}"
        )
    print("\n      THE FINDING, per condition, in the sign of the best album arm's gap:")
    for result in results:
        batch_mean = float(result["batch_mean"])
        best = max(
            ("album", float(result["album_mean"])),
            ("album+sweep", float(result["swept_mean"])),
            ("tierA+album", float(result["tier_a_mean"])),
            key=lambda pair: pair[1],
        )
        verdict = "ALBUM WINS" if best[1] > batch_mean else "BATCH WINS"
        print(
            f"      {str(result['mode']):7s}@{float(result['rate']):.2f}  {verdict:10s}  "
            f"best arm {best[0]} at {best[1]:.2f} % vs batch {batch_mean:.2f} % "
            f"({best[1] - batch_mean:+.2f} pp)"
        )
    control_births = int(control["births"])
    for result in results[1:]:
        if str(result["mode"]) != "split":
            continue
        extra = int(result["extra_nodes"])
        absorbed = extra - (int(result["births"]) - control_births)
        print(
            f"\n      WHERE split@{float(result['rate']):.2f} GOES: {extra} extra nodes, "
            f"{int(result['births']) - control_births} extra births, so **{absorbed} split halves "
            f"were matched onto an EXISTING canonical**"
        )
        print(
            "      -- `assign_speakers` is one-to-one within a span, so the second half of a cut "
            "turn\n         cannot take its own speaker's canonical and is pushed onto another "
            "speaker's."
        )

    print("\n[7] PER-MEETING, SO A MEAN CANNOT HIDE A COLLAPSE (best album arm)")
    header = "      meeting              " + "".join(
        f"{str(row['mode'])[:3]}@{float(row['rate']):.2f}  " for row in results
    )
    print(header)
    for index, meeting in enumerate(meetings):
        cells = "".join(
            f"{max(float(row['per_meeting'][index]['swept']), float(row['per_meeting'][index]['tier_a'])):9.2f}  "  # type: ignore[index]
            for row in results
        )
        print(f"      {meeting.name:20s}{cells}")

    print("\n[8] VERDICT")
    if FAILURES:
        print(f"  {len(FAILURES)} FAILED: " + "; ".join(FAILURES))
        return 1
    print("  all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
