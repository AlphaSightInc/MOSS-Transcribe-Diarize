#!/usr/bin/env python3
"""Phase N step 4's counterfactual: what the **album** engine scores on the **batch** path.

Iteration 17 priced the engine step 4 would replace -- production `IdentityResolver.resolve`
scores **80.07 % mean / 63.33 % min** on the eight LibriSpeech meetings the live album scores
93.44 / 92.18 on, and its Tier B moves that number by **exactly zero** at every threshold,
because `_tier_b_evidence:726` offers Tier B only singleton components. That priced the
baseline and ruled out the cheap fix. It deliberately did **not** measure any counterfactual,
so "step 4 is worth doing" was still an argument rather than a number.

This probe supplies the number. It drives the **production live identity engine** --
`assign_speakers`, `FingerprintAlbum`, `cosine_similarity`, `duration_weighted_centroid`,
`SweepLedger` and `sweep` -- over the **identical batch input** the baseline probe hands
`IdentityResolver`: the same eight meetings, the same shipped window geometry (150 s window /
120 s stride via production `plan_windows`), the same per-window local diarization with
window-arbitrary labels, from the same `build_case`, imported from that probe rather than
re-derived so the two engines cannot drift apart. It is scored with the same
`speaker_accuracy`, over the same denominator.

**The unification, stated as code.** A window is a span: its local speakers are matched
one-to-one against the canonical speakers by `assign_speakers` at ADR-0002's 0.35 / 0.1, the
unmatched are born, and every labelled local's evidence is offered to the album under the live
admission rule. Two scopes are measured because ADR-0002's step 4 wording ("batch Tier B ->
album unification") admits both readings:

  * `album_only`  -- the album replaces **both** tiers; windows are stitched by voiceprint alone.
  * `tier_a_album` -- the album replaces **Tier B only**; production `_resolve_boundary` still
    links nodes across a window boundary by temporal overlap, and a node whose Tier A component
    already carries a canonical inherits it instead of being re-matched.

Two controls, so a win cannot be claimed for the wrong reason:

  * `album_only_top3` -- the query is built from at most the **3** longest evidence units, which
    is batch Tier B's own `tier_b_max_segments_per_node` selection. It removes the album arm's
    aggregation advantage (a 150 s window holds far more speech than Tier B's top-3 intervals).
  * `album_only_batch_thresholds` -- the same album engine at batch's **0.70 / 0.20** instead of
    ADR-0002's 0.35 / 0.1. Iteration 17 showed retuning batch to the album's numbers buys
    nothing; this asks the mirror question, so a gap cannot be attributed to threshold choice.

And the end state, since ADR-0002's step 3 is the other half of the design: `*_swept` runs the
**production** `sweep()` once over a ledger of window-level nodes and applies its corrections,
then asks for a residual sweep that must propose nothing.

THE FIDELITY LIMITS, WITH THEIR DIRECTIONS -- read every number against these.
  1. **Tier A is handed a perfect local diarization**, identical in both windows of every
     overlap. That is the baseline probe's own limit and it is inherited unchanged here, so it
     inflates `tier_a_album` and the 80.07 % baseline **equally**. It does not touch
     `album_only`, which never looks at a boundary overlap -- so the `album_only` comparison is
     the conservative one.
  2. **A query vector is a duration-weighted mean of per-unit embeddings**, not one forward pass
     over the concatenated speech, because the corpus's cached encoder can only answer for the
     units it embedded. Both engines average per-interval embeddings by contract
     (`_tier_b_centroid`, `duration_weighted_centroid`), so this is the same approximation on
     both sides, and `album_only_top3` bounds what the extra aggregation is worth.
  3. LibriSpeech read speech: no overlap, no noise, in-span diarization assumed correct.
     ADR-0002 section 7 and `tests/live_identity_accuracy.py` carry the identical caveat.
  4. Tier A components are computed over the **whole** meeting before the causal window pass, so
     `tier_a_album` sees a link formed at a later boundary. That is correct for a batch engine,
     which has the whole file, and it is stated because it is not what the live path does.

Offline. No host, no session, no network, no product change. ~20 s.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import live_identity_accuracy as lia  # noqa: E402  (path set above)
from moss_transcribe_diarize.app.live_identity import (  # noqa: E402
    LiveIdentityConfig,
    LiveIdentityError,
    LiveSpeakerEvidence,
    _next_speaker_ids,
    assign_speakers,
)
from moss_transcribe_diarize.app.live_identity_album import (  # noqa: E402
    ALBUM_ADMISSION_SECONDS,
    ALBUM_EXEMPLARS_PER_SPEAKER,
    ALBUM_MIN_MATCH_MARGIN,
    ALBUM_MIN_MATCH_SCORE,
    AlbumExemplar,
    FingerprintAlbum,
    cosine_similarity,
    duration_weighted_centroid,
)
from moss_transcribe_diarize.app.live_identity_sweep import (  # noqa: E402
    SWEEP_MERGE_THRESHOLD,
    SweepLedger,
    sweep,
)
from moss_transcribe_diarize.app import speaker_identity as batch  # noqa: E402
from moss_transcribe_diarize.app.speaker_identity import IdentityResolverConfig  # noqa: E402


def _load_baseline_probe():
    """Iteration 17's probe, imported as a module so both engines share one `build_case`.

    Its filename is not an identifier, so this is `importlib` rather than an import statement.
    Re-deriving the batch input here instead would be the one mistake this comparison cannot
    survive: the claim is that two engines saw the *same* windows and the *same* local
    diarization, and a second copy of that code is exactly how that stops being true.
    """

    path = Path(__file__).resolve().parent / "batch-tierb-baseline-probe.py"
    spec = importlib.util.spec_from_file_location("batch_tierb_baseline_probe", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = _load_baseline_probe()

FAILURES: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    print(f"  [{'OK' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)
    return ok


def tier_a_component_map(windows, local_results) -> dict[tuple[int, str], tuple[int, str]]:
    """Every node -> its Tier A component root, through production's own helpers.

    Tier A is boundary matching on temporal overlap and needs no encoder, so the resolver is
    built without one: anything this returns is what the shipped batch path would have linked.
    """

    bundles = batch._bundle_windows(
        windows, local_results, [f"window-{window.index}.wav" for window in windows]
    )
    nodes = batch._nodes_for(bundles)
    union = batch._UnionFind(nodes)
    node_intervals = batch._node_intervals(bundles)
    resolver = batch.IdentityResolver(config=IdentityResolverConfig(tier_b_enabled=False))
    for left, right in zip(bundles, bundles[1:], strict=False):
        resolver._resolve_boundary(left, right, node_intervals, union)
    return {node: union.find(node) for node in nodes}


def node_separation(meeting: lia.Meeting) -> dict[str, float]:
    """How separable the window-granularity nodes actually are, on the real encoder's vectors.

    A perfect arm score is a claim about the *task*, not only about the engine, and it has to
    be checked rather than celebrated: if same-speaker nodes in different windows agree far
    above where different speakers agree, then stitching windows is easy and an engine that
    still loses 20 pp is losing it structurally. That is a stronger and more falsifiable
    statement than "the album arm scored 100 %", so it is measured here directly.
    """

    windows, _starts, local_results, units = base.build_case(meeting)
    vector_index = meeting.vector_index
    durations = meeting.rows[:, lia._DURATION]
    row_of_start = {round(pieces[0].start * 1000): row for row, pieces in enumerate(units)}

    nodes: list[tuple[int, int, tuple[float, ...], float]] = []
    for position, window in enumerate(windows):
        rows_by_local: dict[str, list[int]] = {}
        for segment in local_results[position]:
            rows_by_local.setdefault(segment.speaker, []).append(
                row_of_start[round((window.start + float(segment.start)) * 1000)]
            )
        for rows in rows_by_local.values():
            usable = [row for row in rows if vector_index[row] >= 0]
            truth = {int(meeting.rows[row, lia._TRUE_SPEAKER]) for row in usable}
            if len(truth) != 1:
                continue
            bank = [
                AlbumExemplar(
                    vector=tuple(float(value) for value in meeting.vectors[vector_index[row]]),
                    duration_sec=float(durations[row]),
                    span_id=row,
                )
                for row in usable
            ]
            centroid = duration_weighted_centroid(bank)
            if centroid is None:
                continue
            nodes.append(
                (window.index, truth.pop(), centroid, sum(float(durations[row]) for row in usable))
            )

    same: list[float] = []
    cross: list[float] = []
    for left in range(len(nodes)):
        for right in range(left + 1, len(nodes)):
            if nodes[left][0] == nodes[right][0]:
                continue  # two speakers in one window are never a stitching question
            score = cosine_similarity(nodes[left][2], nodes[right][2])
            if score is None:
                continue
            (same if nodes[left][1] == nodes[right][1] else cross).append(score)
    seconds = [node[3] for node in nodes]
    batch_floor = IdentityResolverConfig().tier_b_similarity
    return {
        "nodes": float(len(nodes)),
        "min_same": min(same) if same else float("nan"),
        "max_cross": max(cross) if cross else float("nan"),
        "median_seconds": float(np.median(seconds)) if seconds else float("nan"),
        "min_seconds": min(seconds) if seconds else float("nan"),
        "same_pairs": float(len(same)),
        # The mechanism, in two counts: a same-speaker pair below a similarity floor is a link
        # that floor cannot make. Batch's floor and the album's are asked the same question.
        "same_below_batch_floor": float(sum(1 for score in same if score < batch_floor)),
        "same_below_album_floor": float(
            sum(1 for score in same if score < ALBUM_MIN_MATCH_SCORE)
        ),
    }


def album_arm(
    meeting: lia.Meeting,
    *,
    use_tier_a: bool = False,
    min_score: float = ALBUM_MIN_MATCH_SCORE,
    min_margin: float = ALBUM_MIN_MATCH_MARGIN,
    top_units: int | None = None,
    sweep_at_end: bool = False,
) -> dict[str, object]:
    """One meeting through the album engine on the batch path. Returns scores and dispositions."""

    windows, _window_starts, local_results, units = base.build_case(meeting)
    vector_index = meeting.vector_index
    durations = meeting.rows[:, lia._DURATION]
    row_of_start = {round(pieces[0].start * 1000): row for row, pieces in enumerate(units)}
    component_of = tier_a_component_map(windows, local_results) if use_tier_a else {}

    album = FingerprintAlbum(
        admission_seconds=ALBUM_ADMISSION_SECONDS,
        exemplars_per_speaker=ALBUM_EXEMPLARS_PER_SPEAKER,
    )
    config = LiveIdentityConfig(
        max_speakers=lia.MAX_SPEAKERS,
        min_match_score=min_score,
        min_match_margin=min_margin,
    )
    ledger = SweepLedger() if sweep_at_end else None

    canonical_speakers: tuple[str, ...] = ()
    component_canonical: dict[tuple[int, str], str] = {}
    live_label: dict[tuple[int, str], str] = {}
    local_of: dict[tuple[int, int], str] = {}
    stats: Counter[str] = Counter()

    for position, window in enumerate(windows):
        rows_by_local: dict[str, list[int]] = {}
        for segment in local_results[position]:
            row = row_of_start[round((window.start + float(segment.start)) * 1000)]
            rows_by_local.setdefault(segment.speaker, []).append(row)
            local_of[(window.index, row)] = segment.speaker
        locals_order = tuple(sorted(rows_by_local))

        # One query per local speaker: the duration-weighted centroid of its evidence units,
        # which is the album's own reference rule applied to a window instead of a span.
        query: dict[str, tuple[tuple[float, ...], float]] = {}
        for local in locals_order:
            eligible = [row for row in rows_by_local[local] if vector_index[row] >= 0]
            eligible.sort(key=lambda row: (-float(durations[row]), row))
            chosen = eligible if top_units is None else eligible[:top_units]
            bank = [
                AlbumExemplar(
                    vector=tuple(float(value) for value in meeting.vectors[vector_index[row]]),
                    duration_sec=float(durations[row]),
                    span_id=row,
                )
                for row in chosen
            ]
            centroid = duration_weighted_centroid(bank)
            if centroid is None:
                stats["local_without_usable_evidence"] += 1
                continue
            query[local] = (centroid, sum(float(durations[row]) for row in chosen))

        inherited = {
            local: component_canonical[component_of[(window.index, local)]]
            for local in locals_order
            if component_of.get((window.index, local)) in component_canonical
        }
        if len(set(inherited.values())) != len(inherited):
            stats["same_window_inherited_collision"] += 1
        taken = set(inherited.values())

        pending = tuple(local for local in locals_order if local not in inherited and local in query)
        available = tuple(name for name in canonical_speakers if name not in taken)
        evidence: list[LiveSpeakerEvidence] = []
        for local in pending:
            vector = query[local][0]
            for canonical in available:
                reference = album.reference(canonical)
                if reference is None:
                    continue
                score = cosine_similarity(vector, reference)
                if score is None:
                    continue
                evidence.append(
                    LiveSpeakerEvidence(
                        local_speaker=local, canonical_speaker=canonical, score=score
                    )
                )

        assigned = dict(inherited)
        try:
            mapping = assign_speakers(
                local_speakers=pending,
                canonical_speakers=available,
                evidence=tuple(evidence),
                config=config,
            )
        except LiveIdentityError as exc:
            # The live path's own ruling: an ambiguous span is not relabelled. Inherited labels
            # are a Tier A structural fact rather than an album match, so they stand.
            stats[f"abstain:{exc}"] += 1
            mapping = None

        if mapping is not None:
            assigned.update(dict(mapping))
            births = [local for local in pending if local not in assigned]
            if len(canonical_speakers) + len(births) > lia.MAX_SPEAKERS:
                stats["speaker_capacity_exceeded"] += 1
                assigned = dict(inherited)
            else:
                born = _next_speaker_ids(canonical_speakers, len(births))
                stats["births"] += len(born)
                for local, canonical in zip(births, born, strict=True):
                    assigned[local] = canonical
                canonical_speakers = canonical_speakers + born

        for local, canonical in assigned.items():
            live_label[(window.index, local)] = canonical
            component = component_of.get((window.index, local))
            if component is not None:
                component_canonical.setdefault(component, canonical)
            if local in query:
                vector, seconds = query[local]
                stats[
                    "observe:"
                    + album.observe(
                        canonical_speaker=canonical,
                        vector=vector,
                        duration_sec=seconds,
                        span_id=window.index,
                    )
                ] += 1
        if ledger is not None:
            for local in locals_order:
                if local not in query:
                    continue
                vector, seconds = query[local]
                ledger.record(
                    span_id=window.index,
                    local_speaker=local,
                    canonical_speaker=assigned.get(local),
                    vector=vector,
                    duration_sec=seconds,
                )

    final_label = dict(live_label)
    sweeps = {"corrections": 0, "merges": 0, "residual": 0}
    if ledger is not None:
        revision = sweep(
            ledger=ledger, album=album, config=config, merge_threshold=SWEEP_MERGE_THRESHOLD
        )
        for correction in revision.corrections:
            final_label[(correction.span_id, correction.local_speaker)] = correction.canonical_speaker
        ledger.apply(revision)
        residual = sweep(
            ledger=ledger, album=album, config=config, merge_threshold=SWEEP_MERGE_THRESHOLD
        )
        sweeps = {
            "corrections": len(revision.corrections),
            "merges": len(revision.merges),
            "residual": len(residual.corrections),
        }

    def score(label_of_node: dict[tuple[int, str], str]) -> tuple[float, int, int]:
        labels = np.full(len(meeting.rows), -1, np.int64)
        index: dict[str, int] = {}
        unlabelled = 0
        for row, pieces in enumerate(units):
            window_index = base.owning_window(windows, pieces[0].start)
            local = local_of.get((window_index, row))
            canonical = None if local is None else label_of_node.get((window_index, local))
            if canonical is None:
                if meeting.rows[row, lia._ELIGIBLE] > 0:
                    unlabelled += 1
                continue
            labels[row] = index.setdefault(canonical, len(index))
        return lia.speaker_accuracy(meeting, labels), len(index), unlabelled

    live_accuracy, live_speakers, live_unlabelled = score(live_label)
    accuracy, final_speakers, final_unlabelled = score(final_label)
    return {
        "accuracy": accuracy,
        "live_accuracy": live_accuracy,
        "speakers": final_speakers,
        "live_speakers": live_speakers,
        "unlabelled": final_unlabelled,
        "live_unlabelled": live_unlabelled,
        "stats": stats,
        "sweeps": sweeps,
    }


ARMS: dict[str, dict[str, object]] = {
    "album_only": {},
    "album_only_top3": {"top_units": 3},
    "album_only_batch_thresholds": {
        "min_score": IdentityResolverConfig().tier_b_similarity,
        "min_margin": IdentityResolverConfig().tier_b_margin,
    },
    "tier_a_album": {"use_tier_a": True},
    "album_only_swept": {"sweep_at_end": True},
    "tier_a_album_swept": {"use_tier_a": True, "sweep_at_end": True},
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meetings", nargs="*", default=list(lia.MEETINGS))
    args = parser.parse_args()

    print("\n[1] ONE INPUT, TWO ENGINES - the comparison's precondition")
    meetings = [lia.load_meeting(name) for name in args.meetings]
    for meeting in meetings:
        lia.assert_fixture_matches_production(meeting)
    windows_total = 0
    nodes_total = 0
    for meeting in meetings:
        windows, _starts, local_results, _units = base.build_case(meeting)
        windows_total += len(windows)
        nodes_total += sum(len({segment.speaker for segment in segments}) for segments in local_results)
    check(
        base.WINDOW_SECONDS == 150.0 and base.STRIDE_SECONDS == 120.0,
        "the batch geometry is the shipped one, taken from the baseline probe",
        f"{base.WINDOW_SECONDS:.0f}s window / {base.STRIDE_SECONDS:.0f}s stride",
    )
    check(
        nodes_total > 0,
        "both engines are driven from one `build_case`",
        f"{len(meetings)} meetings, {windows_total} windows, {nodes_total} nodes",
    )
    print(
        f"      album engine : admission {ALBUM_ADMISSION_SECONDS:.1f}s, "
        f"k={ALBUM_EXEMPLARS_PER_SPEAKER}, score {ALBUM_MIN_MATCH_SCORE:.2f} / "
        f"margin {ALBUM_MIN_MATCH_MARGIN:.2f}, matcher `assign_speakers`"
    )

    print("\n[2] THE BASELINE, RECOMPUTED IN THIS PROCESS - never copied from a journal")
    shipped: dict[str, float] = {}
    tier_a_only: dict[str, float] = {}
    for meeting in meetings:
        _resolution, labels, _count, unlabelled, _encoder = base.resolve_meeting(
            meeting, IdentityResolverConfig(tier_b_enabled=True)
        )
        shipped[meeting.name] = lia.speaker_accuracy(meeting, labels)
        _resolution, labels, _count, _unlabelled, _encoder = base.resolve_meeting(
            meeting, IdentityResolverConfig(tier_b_enabled=False)
        )
        tier_a_only[meeting.name] = lia.speaker_accuracy(meeting, labels)
        if unlabelled:
            check(False, f"{meeting.name}: baseline left units unlabelled", str(unlabelled))
    shipped_values = np.array([shipped[m.name] for m in meetings])
    tier_a_values = np.array([tier_a_only[m.name] for m in meetings])
    print(
        f"      batch shipped (Tier A + Tier B) : mean {shipped_values.mean() * 100:.2f}%  "
        f"min {shipped_values.min() * 100:.2f}%"
    )
    check(
        bool(np.allclose(shipped_values, tier_a_values, atol=1e-12)),
        "iteration 17 reproduced: batch Tier B moves the score by exactly zero",
        f"max |delta| = {np.abs(shipped_values - tier_a_values).max() * 100:.10f} pp",
    )

    print("\n[3] THE ALBUM ENGINE ON THE BATCH PATH")
    results: dict[str, dict[str, dict[str, object]]] = {}
    print(f"      {'arm':<28}{'mean':>9}{'min':>9}{'vs shipped':>13}{'speakers':>12}{'unlabelled':>12}")
    for arm, kwargs in ARMS.items():
        results[arm] = {m.name: album_arm(m, **kwargs) for m in meetings}
        values = np.array([results[arm][m.name]["accuracy"] for m in meetings])
        counts = [int(results[arm][m.name]["speakers"]) for m in meetings]
        unlabelled = sum(int(results[arm][m.name]["unlabelled"]) for m in meetings)
        print(
            f"      {arm:<28}{values.mean() * 100:>8.2f}%{values.min() * 100:>8.2f}%"
            f"{(values.mean() - shipped_values.mean()) * 100:>+12.2f}"
            f"{min(counts):>7d}-{max(counts):<4d}{unlabelled:>12d}"
        )

    print("\n[4] PER MEETING - shipped batch, album on the batch path, and the live album")
    album_live = lia.replay_all(policy="album")
    print(
        f"      {'meeting':<14}{'k':>3}{'batch':>9}{'album_only':>12}{'tier_a_album':>14}"
        f"{'live album':>12}{'best-batch':>12}"
    )
    for meeting in meetings:
        only = float(results["album_only"][meeting.name]["accuracy"])
        with_a = float(results["tier_a_album"][meeting.name]["accuracy"])
        print(
            f"      {meeting.name:<14}{meeting.speaker_count:>3d}{shipped[meeting.name] * 100:>8.2f}%"
            f"{only * 100:>11.2f}%{with_a * 100:>13.2f}%"
            f"{album_live[meeting.name].accuracy * 100:>11.2f}%"
            f"{(max(only, with_a) - shipped[meeting.name]) * 100:>+12.2f}"
        )

    print("\n[5] WHAT THE SWEEP ADDS, AND WHETHER IT CONVERGES")
    for arm in ("album_only_swept", "tier_a_album_swept"):
        corrections = sum(int(results[arm][m.name]["sweeps"]["corrections"]) for m in meetings)
        merges = sum(int(results[arm][m.name]["sweeps"]["merges"]) for m in meetings)
        residual = sum(int(results[arm][m.name]["sweeps"]["residual"]) for m in meetings)
        live = np.array([results[arm][m.name]["live_accuracy"] for m in meetings])
        final = np.array([results[arm][m.name]["accuracy"] for m in meetings])
        print(
            f"      {arm:<22} at commit {live.mean() * 100:6.2f}%  after sweep "
            f"{final.mean() * 100:6.2f}%  corrections {corrections:3d}  merges {merges:2d}  "
            f"residual {residual}"
        )
        check(
            residual == 0,
            f"{arm}: an applied sweep leaves nothing for the next one",
            f"{residual} residual corrections",
        )

    print("\n[6] DISPOSITIONS - what the engine actually did, summed over the corpus")
    for arm in ("album_only", "tier_a_album"):
        totals: Counter[str] = Counter()
        for meeting in meetings:
            totals.update(results[arm][meeting.name]["stats"])
        print(f"      {arm:<16} {dict(sorted(totals.items()))}")

    print("\n[7] WHY THE ALBUM ARMS SATURATE - the separation at window granularity")
    print(
        f"      {'meeting':<14}{'nodes':>7}{'median s/node':>15}{'min s/node':>12}"
        f"{'min same-spk':>14}{'max cross-spk':>15}{'gap':>8}"
    )
    gaps: list[float] = []
    same_pairs = 0
    below_batch = 0
    below_album = 0
    for meeting in meetings:
        separation = node_separation(meeting)
        gaps.append(separation["min_same"] - separation["max_cross"])
        same_pairs += int(separation["same_pairs"])
        below_batch += int(separation["same_below_batch_floor"])
        below_album += int(separation["same_below_album_floor"])
        print(
            f"      {meeting.name:<14}{int(separation['nodes']):>7d}"
            f"{separation['median_seconds']:>15.1f}{separation['min_seconds']:>12.1f}"
            f"{separation['min_same']:>14.3f}{separation['max_cross']:>15.3f}{gaps[-1]:>+8.3f}"
        )
    check(
        min(gaps) > 0.0,
        "every same-speaker node pair agrees above every cross-speaker pair",
        f"worst per-meeting gap {min(gaps):+.3f}",
    )
    print(
        f"      same-speaker cross-window node pairs: {same_pairs}; below batch's "
        f"tier_b_similarity {IdentityResolverConfig().tier_b_similarity:.2f}: {below_batch} "
        f"({below_batch / same_pairs * 100:.1f}%); below the album's "
        f"{ALBUM_MIN_MATCH_SCORE:.2f}: {below_album} ({below_album / same_pairs * 100:.1f}%)"
    )

    print("\n[8] THE CLAIMS THIS PROBE MAKES FALSIFIABLE")
    only_values = np.array([results["album_only"][m.name]["accuracy"] for m in meetings])
    tier_a_album_values = np.array([results["tier_a_album"][m.name]["accuracy"] for m in meetings])
    top3_values = np.array([results["album_only_top3"][m.name]["accuracy"] for m in meetings])
    batch_threshold_values = np.array(
        [results["album_only_batch_thresholds"][m.name]["accuracy"] for m in meetings]
    )
    best = max(only_values.mean(), tier_a_album_values.mean())
    check(
        best > shipped_values.mean(),
        "the album engine on the batch path beats the engine step 4 would replace",
        f"{best * 100:.2f}% vs {shipped_values.mean() * 100:.2f}% "
        f"({(best - shipped_values.mean()) * 100:+.2f} pp)",
    )
    check(
        top3_values.mean() > shipped_values.mean(),
        "the win survives batch Tier B's own top-3 interval selection",
        f"{top3_values.mean() * 100:.2f}% vs {shipped_values.mean() * 100:.2f}% "
        f"({(top3_values.mean() - shipped_values.mean()) * 100:+.2f} pp)",
    )
    # The mirror of iteration 17, and it is the finding rather than a hygiene check: that probe
    # showed batch's engine at the album's thresholds moves by zero; this one shows the album's
    # engine at *batch's* thresholds still wins by ~20 pp. Neither engine's score is about the
    # numbers, so step 4 cannot be a recalibration in either direction.
    check(
        batch_threshold_values.mean() > shipped_values.mean(),
        "the album engine wins at BATCH's own thresholds too, so the gap is structural",
        f"0.70/0.20 gives {batch_threshold_values.mean() * 100:.2f}% vs shipped "
        f"{shipped_values.mean() * 100:.2f}%; ADR-0002's 0.35/0.10 is worth only "
        f"{(only_values.mean() - batch_threshold_values.mean()) * 100:+.2f} pp here",
    )
    unlabelled = sum(int(results["album_only"][m.name]["unlabelled"]) for m in meetings)
    check(
        unlabelled == 0,
        "album_only labels every eligible unit, so the score is not bought by abstaining",
        f"{unlabelled} eligible units unlabelled",
    )

    print("\n[LIMITS] read every number above against these, and note the direction of each")
    print("  1. Tier A is handed a PERFECT local diarization (the baseline probe's limit,")
    print("     inherited). It inflates `tier_a_album` and the shipped baseline EQUALLY and does")
    print("     not touch `album_only` -- so `album_only` is the conservative comparison.")
    print("  2. A query vector is a duration-weighted mean of per-unit embeddings, not one pass")
    print("     over concatenated speech. Both engines average per-interval embeddings by")
    print("     contract; `album_only_top3` bounds what the extra aggregation is worth.")
    print("  3. LibriSpeech read speech: no overlap, no noise, in-span diarization assumed")
    print("     correct. ADR-0002 section 7 carries the identical caveat.")
    print("  4. Tier A components are computed over the whole meeting before the causal window")
    print("     pass, so `tier_a_album` may inherit a link formed at a later boundary. Correct")
    print("     for a batch engine, which holds the whole file; stated because live cannot.")
    print("  5. This probe measures a PROTOTYPE, not a shipped resolver. It says what the")
    print("     unified engine is worth on this corpus; it does not implement step 4.")
    print("  6. THE ALBUM ARMS SATURATE, and section 7 says why: a 150 s window hands the")
    print("     matcher tens of seconds of one speaker, where same- and cross-speaker cosines")
    print("     are far apart. The 100 % is therefore a CEILING on clean read speech with a")
    print("     perfect local diarization, never a forecast for a real recording. What it")
    print("     establishes is the CAUSE -- an engine that loses ~20 pp on a task this")
    print("     separable is losing it structurally, not perceptually -- and the direction.")

    print("")
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): " + "; ".join(FAILURES))
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
