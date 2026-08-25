#!/usr/bin/env python3
"""PROTOTYPE — throwaway. Identity levers for the live-vs-file accuracy gap (H4).

Question and gates: `PREREGISTRATION.md` beside this file. Verdict: `NOTES.md`.

Replays the deployed live identity stack **offline** over the frozen baseline traces, using the
production modules (`assign_speakers`, `FingerprintAlbum`, `LiveIdentitySweeper`, `sweep`) and
the production encoder (`voxceleb_resnet152_LM.onnx`) re-embedding the exact published segment
intervals. No model decodes, no live session, no deployed backend.

Levers measured
    baseline   deployed policy, replayed (fidelity check against the published labels)
    C1         merged-evidence assignment over endpoint-merged windows instead of per-2.5s span
    C2a        sweep cadence 60s -> 20s
    C2b        sweep-only min_match_margin 0.10 -> 0.05
    C2c        sweep ledger records sub-floor fragments (no min_segment_samples gate)
    combos     C2b+C2c, C1+C2b

Every lever changes **labels only**; segment start/end times are never touched, so nothing here
is an extent-driven gain (see the metric-validity caveat in PREREGISTRATION.md).

Run:  .venv/bin/python prototypes/live-file-gap-identity/proto_identity_levers.py
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.live_identity import (  # noqa: E402
    LiveIdentityConfig,
    LiveIdentityError,
    LiveSpeakerEvidence,
    assign_speakers,
)
from moss_transcribe_diarize.app.live_identity_album import FingerprintAlbum  # noqa: E402
from moss_transcribe_diarize.app.live_identity_sweep import (  # noqa: E402
    SWEEP_INTERVAL_SECONDS,
    SWEEP_MERGE_THRESHOLD,
    LiveIdentitySweeper,
)
from moss_transcribe_diarize.app.live_session import display_speaker_label  # noqa: E402
from moss_transcribe_diarize.live_speaker_accuracy import (  # noqa: E402
    SpeakerActivityInterval,
    load_reference_speaker_activity_jsonl,
    score_live_speaker_accuracy,
)

# ---------------------------------------------------------------- deployed configuration
# All five values are the deployed manifest's (identity_config_hash 4b7c94ed..., combined
# 431efb3f..., matching the baseline replay-manifest descriptor).
SR = 16000
MIN_EVID_SAMPLES = 8000          # identity_provider.min_segment_samples  (0.50 s)
BIRTH_MIN_SECONDS = 1.0          # identity_provider.birth_min_seconds
ADMISSION_SECONDS = 2.0          # identity_provider.album_admission_seconds
MIN_MATCH_SCORE = 0.35           # identity_config.min_match_score
MIN_MATCH_MARGIN = 0.1           # identity_config.min_match_margin
MAX_SPEAKERS = 16                # bounds.max_identity_speakers

ONNX = REPO / "prototypes/streaming-diarization/data/voxceleb_resnet152_LM.onnx"
CORPUS = REPO / "prototypes/streaming-diarization/data/real/benchmark_diarization_1min/samples"
DEFAULT_BASELINE = Path(
    "/private/tmp/claude-501/-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize"
    "/bd3632af-da27-408f-8e03-ecd56a586e8d/scratchpad/remeasure-20260824T160130"
)
TRIO = ("lex_bill_ackman", "lex_javier_milei", "lex_keyu_jin")
CONFIG = LiveIdentityConfig(
    max_speakers=MAX_SPEAKERS, min_match_score=MIN_MATCH_SCORE, min_match_margin=MIN_MATCH_MARGIN
)

SEGMENT = re.compile(
    r"\[([0-9]+(?:\.[0-9]+)?)\]\[(S[0-9]+)\](.*?)\[([0-9]+(?:\.[0-9]+)?)\](?=\s*(?:\[|$))", re.DOTALL
)

# C1 knobs
GAP_MAX = 0.35          # merge across an inter-segment gap no larger than this (< 0.6 s endpoint split)
WINDOW_CAP = 10.0       # a merged window never spans more than this much wall time
ADOPT_GAP = 0.6         # C1' fragment adoption: neighbour must be within the endpoint silence split


# ---------------------------------------------------------------- baseline trace parsing
@dataclass
class Seg:
    start: float
    end: float
    label: str          # published label (S00/S01/...)
    text: str
    span_id: int

    @property
    def duration(self) -> float:
        return self.end - self.start


def terminal_snapshot(baseline: Path, case: str) -> dict:
    path = baseline / case / "live" / "run-001" / "trace.jsonl"
    for line in reversed(path.read_text().splitlines()):
        event = json.loads(line)
        if event.get("kind") == "terminal":
            return event
    raise SystemExit(f"no terminal event in {path}")


def committed_segments(baseline: Path, case: str) -> list[Seg]:
    """Published segments in time order, exactly as the baseline scored them."""
    out: list[Seg] = []
    session = terminal_snapshot(baseline, case)["snapshot"]["session"]
    for item in session["committed"]:
        base = item["start_sample"] / SR
        span_seconds = (item["end_sample"] - item["start_sample"]) / SR
        transcript = item.get("revised_transcript") or item.get("transcript") or ""
        for match in SEGMENT.finditer(transcript):
            start = min(max(float(match.group(1)), 0.0), span_seconds)
            end = max(min(max(float(match.group(4)), 0.0), span_seconds), start)
            if end > start:
                out.append(
                    Seg(base + start, base + end, match.group(2), match.group(3).strip(), item["span_id"])
                )
    return out


def local_groups(segments: list[Seg]) -> list[tuple[str, list[Seg]]]:
    """Reconstruct one span's decoder-local speakers from its published labels.

    The live matcher assigns a span's locals one-to-one, so a published non-`S00` label is
    exactly one local speaker. A *run* of consecutive `S00` segments is one local speaker: that
    grouping is the one that reproduces the deployed labels for all three cases (fidelity 100 %).
    """
    groups: dict[str, list[Seg]] = {}
    order: list[str] = []
    run = 0
    previous_s00 = False
    for segment in segments:
        if segment.label == "S00":
            if not previous_s00:
                run += 1
            key = f"S00#{run}"
            previous_s00 = True
        else:
            key = segment.label
            previous_s00 = False
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(segment)
    return [(key, groups[key]) for key in order]


# ---------------------------------------------------------------- encoder
def load_encoder():
    spec = importlib.util.spec_from_file_location(
        "si_prod", REPO / "moss_transcribe_diarize/app/speaker_identity.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["si_prod"] = module
    spec.loader.exec_module(module)
    adapter = module.WeSpeakerResNet152LmAdapter(ONNX)
    preflight = adapter.preflight()
    assert preflight.available, f"production encoder preflight failed: {preflight.reason}"
    return adapter


class Embedder:
    """Production encoder with a memo, keyed on the exact interval list."""

    def __init__(self, encoder):
        self.encoder = encoder
        self.cache: dict[tuple, tuple | None] = {}
        self.calls = 0
        self.failures = 0

    def __call__(self, case: str, intervals: list[tuple[float, float]]):
        if not intervals:
            return None
        key = (case, tuple((round(a, 4), round(b, 4)) for a, b in intervals))
        if key not in self.cache:
            self.calls += 1
            try:
                self.cache[key] = tuple(self.encoder.embed(CORPUS / case / "audio.wav", list(intervals)))
            except ValueError:
                # The production frontend refuses a slice too short to produce fbank frames.
                # That refusal is itself a finding: see NOTES.md, C2c.
                self.failures += 1
                self.cache[key] = None
        return self.cache[key]


def cosine(left, right) -> float:
    num = sum(x * y for x, y in zip(left, right))
    ln = math.sqrt(sum(x * x for x in left))
    rn = math.sqrt(sum(y * y for y in right))
    if ln <= 0.0 or rn <= 0.0:
        return 0.0
    return max(0.0, min(1.0, num / (ln * rn)))


# ---------------------------------------------------------------- the replay
@dataclass
class Unit:
    key: str                        # local speaker (baseline) or window id (C1)
    span_id: int                    # ledger key
    members: list[Seg]              # published segments this unit owns
    eligible: list[tuple[float, float]]
    evidence_seconds: float
    vector: tuple | None = None
    label: str = "S00"
    ledger_only: bool = False       # C2c: embedded for the sweep ledger, invisible to the live path
    ledger_seconds: float = 0.0     # seconds behind the ledger vector (== evidence_seconds normally)


@dataclass
class Result:
    name: str
    per_case: dict = field(default_factory=dict)


def build_units(case: str, segments: list[Seg], embed: Embedder, *, merged: bool,
                ledger_floor_samples: int) -> list[Unit]:
    """Baseline units (one per span-local) or C1 units (one per endpoint-merged window)."""
    units: list[Unit] = []
    if not merged:
        by_span: dict[int, list[Seg]] = {}
        for segment in segments:
            by_span.setdefault(segment.span_id, []).append(segment)
        for span_id in sorted(by_span):
            for key, members in local_groups(by_span[span_id]):
                eligible = [
                    (m.start, m.end) for m in members
                    if int(round(m.duration * SR)) >= MIN_EVID_SAMPLES
                ]
                units.append(
                    Unit(key, span_id, members, eligible, sum(b - a for a, b in eligible))
                )
    else:
        window: list[Seg] = []

        def close():
            if not window:
                return
            speech = sum(m.duration for m in window)
            # Merged evidence: every member interval feeds the one embedding, including the
            # fragments the per-span floor would have dropped. The floor now applies to the
            # window, which is the whole point of the lever.
            eligible = [(m.start, m.end) for m in window] if int(round(speech * SR)) >= MIN_EVID_SAMPLES else []
            units.append(
                Unit(f"W{len(units):03d}", window[0].span_id, list(window), eligible,
                     sum(b - a for a, b in eligible))
            )
            window.clear()

        for segment in segments:
            if window:
                previous = window[-1]
                same_local_run = not (previous.span_id == segment.span_id and previous.label != segment.label)
                gap = segment.start - previous.end
                if gap > GAP_MAX or not same_local_run or (segment.end - window[0].start) > WINDOW_CAP:
                    close()
            window.append(segment)
        close()

    for unit in units:
        if unit.eligible:
            unit.vector = embed(case, unit.eligible)
            unit.ledger_seconds = unit.evidence_seconds
        elif ledger_floor_samples <= 0 and unit.members:
            # C2c: embed the fragment anyway, purely so the sweep ledger can see it. The live
            # path stays byte-identical -- this vector never reaches the matcher or the album,
            # and `evidence_seconds` (which gates birth) stays at the deployed 0.0.
            unit.vector = embed(case, [(m.start, m.end) for m in unit.members])
            unit.ledger_seconds = sum(m.duration for m in unit.members)
            unit.ledger_only = True
    return units


def replay(case: str, segments: list[Seg], embed: Embedder, *, merged: bool = False,
           sweep_interval: float = SWEEP_INTERVAL_SECONDS, sweep_margin: float = MIN_MATCH_MARGIN,
           ledger_floor_samples: int = MIN_EVID_SAMPLES, apply_sweep: bool = True,
           adopt: str | None = None):
    """Run the identity policy over one case; return (labelled segments, telemetry)."""
    album = FingerprintAlbum(admission_seconds=ADMISSION_SECONDS)
    sweep_config = LiveIdentityConfig(
        max_speakers=MAX_SPEAKERS, min_match_score=MIN_MATCH_SCORE, min_match_margin=sweep_margin
    )
    sweeper = LiveIdentitySweeper(
        album=album, config=sweep_config, interval_seconds=sweep_interval,
        merge_threshold=SWEEP_MERGE_THRESHOLD,
    )
    canonical: list[str] = []
    units = build_units(case, segments, embed, merged=merged, ledger_floor_samples=ledger_floor_samples)
    by_unit: dict[tuple[int, str], Unit] = {}
    canonical_of: dict[tuple[int, str], str] = {}
    telemetry = {"abstains": 0, "births": 0, "deferred": 0, "unit_count": len(units),
                 "cadence_sweeps": 0, "max_close_delay": 0.0}

    # Assignment groups: the deployed path matches a span's locals **jointly** (one-to-one, which
    # is what produces `same_span_cannot_link_conflict`); a C1 window is its own group.
    groups: list[list[Unit]] = []
    if merged:
        groups = [[unit] for unit in units]
    else:
        for unit in units:
            if groups and groups[-1][0].span_id == unit.span_id:
                groups[-1].append(unit)
            else:
                groups.append([unit])

    for group in groups:
        before = sweeper.sweeps
        sweeper.maybe_sweep(meeting_seconds=group[0].members[0].start)
        telemetry["cadence_sweeps"] += sweeper.sweeps - before

        for unit in group:
            if unit.vector is None:
                continue
            sweeper.record(span_id=unit.span_id, local_speaker=unit.key, canonical_speaker=None,
                           vector=unit.vector, duration_sec=max(unit.ledger_seconds, 1e-6))
            by_unit[(unit.span_id, unit.key)] = unit
        scored = [unit for unit in group if unit.vector is not None and not unit.ledger_only]

        evidence = []
        for unit in scored:
            for speaker in canonical:
                reference = album.reference(speaker)
                if reference is None:
                    continue
                evidence.append(
                    LiveSpeakerEvidence(local_speaker=unit.key, canonical_speaker=speaker,
                                        score=cosine(unit.vector, reference))
                )
        local_names = tuple(unit.key for unit in group)
        try:
            mapping = dict(assign_speakers(local_speakers=local_names, canonical_speakers=tuple(canonical),
                                           evidence=tuple(evidence), config=CONFIG))
        except LiveIdentityError:
            telemetry["abstains"] += 1
            continue                      # the whole group publishes unattributed, as live does
        for unit in group:                # deferred births: evidence floor then birth floor
            if unit.key in mapping:
                continue
            if unit.evidence_seconds >= BIRTH_MIN_SECONDS and len(canonical) < MAX_SPEAKERS:
                born = f"speaker-{len(canonical) + 1:04d}"
                canonical.append(born)
                mapping[unit.key] = born
                telemetry["births"] += 1
            else:
                telemetry["deferred"] += 1
        for unit in group:
            speaker = mapping.get(unit.key)
            if speaker is None or unit.vector is None or unit.ledger_only:
                continue
            canonical_of[(unit.span_id, unit.key)] = speaker
            album.observe(canonical_speaker=speaker, vector=unit.vector,
                          duration_sec=max(unit.evidence_seconds, 1e-6), span_id=unit.span_id)
            sweeper.record(span_id=unit.span_id, local_speaker=unit.key, canonical_speaker=speaker,
                           vector=unit.vector, duration_sec=max(unit.ledger_seconds, 1e-6))

    final = sweeper.sweep_now()
    telemetry["sweeps"] = sweeper.sweeps
    telemetry["corrections"] = len(final.corrections)
    telemetry["merges"] = len(final.merges)
    telemetry["dispositions"] = dict(final.dispositions)
    telemetry["canonical"] = len(canonical)
    applied = 0
    if apply_sweep:
        for correction in final.corrections:
            key = (correction.span_id, correction.local_speaker)
            if key in by_unit and correction.canonical_speaker in canonical:
                canonical_of[key] = correction.canonical_speaker
                applied += 1
    telemetry["applied_corrections"] = applied

    labelled: dict[int, str] = {}
    for unit in units:
        speaker = canonical_of.get((unit.span_id, unit.key))
        label = display_speaker_label(speaker, tuple(canonical)) if speaker else "S00"
        for member in unit.members:
            labelled[id(member)] = label

    # C1' fragment adoption. Only a unit the *evidence floor* silenced -- zero embeddable
    # speech, so the album was never even asked -- may adopt a neighbour's identity. A unit that
    # had evidence and was declined (an abstention) keeps its abstention: that is a decision, not
    # a gap in the evidence.
    telemetry["adopted"] = 0
    telemetry["adoption_conflicts"] = 0
    if adopt:
        labelled_segments = [s for s in segments if labelled.get(id(s), "S00") != "S00"]
        for unit in units:
            if unit.evidence_seconds > 0.0 or not unit.members:
                continue
            if any(labelled.get(id(m), "S00") != "S00" for m in unit.members):
                continue
            start, end = unit.members[0].start, unit.members[-1].end
            previous = [s for s in labelled_segments if s.end <= start]
            following = [] if adopt == "prev" else [s for s in labelled_segments if s.start >= end]
            left = (start - previous[-1].end, labelled[id(previous[-1])]) if previous else None
            right = (following[0].start - end, labelled[id(following[0])]) if following else None
            options = [o for o in (left, right) if o is not None and o[0] <= ADOPT_GAP]
            if not options:
                continue
            options.sort(key=lambda o: o[0])
            if len(options) == 2 and options[0][1] != options[1][1] and math.isclose(options[0][0], options[1][0]):
                telemetry["adoption_conflicts"] += 1
                continue
            for member in unit.members:
                labelled[id(member)] = options[0][1]
            telemetry["adopted"] += 1

    return [SpeakerActivityInterval(s.start, s.end, labelled.get(id(s), "S00")) for s in segments], telemetry


# ---------------------------------------------------------------- scoring
def score(case: str, hypothesis) -> dict:
    reference = load_reference_speaker_activity_jsonl(CORPUS / case / "reference.jsonl")
    return score_live_speaker_accuracy(reference, list(hypothesis))


def s00_seconds(hypothesis) -> float:
    return sum(h.end - h.start for h in hypothesis if h.speaker == "S00")


def oracle_labels(case: str, segments: list[Seg]):
    """Ceiling: every segment relabelled to its overlap-optimal reference speaker.

    Label-only. Extents are the live arm's own, so the residual error this leaves is exactly
    what identity cannot reach (missed speech, and reference-boundary straddle).
    """
    reference = load_reference_speaker_activity_jsonl(CORPUS / case / "reference.jsonl")
    plain = [SpeakerActivityInterval(s.start, s.end, s.label) for s in segments]
    mapping = score_live_speaker_accuracy(reference, plain)["speaker_mapping"]
    out = []
    for segment in segments:
        owner, overlap = max(
            ((r.speaker, max(0.0, min(segment.end, r.end) - max(segment.start, r.start))) for r in reference),
            key=lambda pair: pair[1],
        )
        out.append(SpeakerActivityInterval(segment.start, segment.end,
                                           mapping[owner] if overlap > 0 else segment.label))
    return out, {"sweeps": 0, "cadence_sweeps": 0, "corrections": 0, "applied_corrections": 0,
                 "canonical": 2, "abstains": 0, "unit_count": 0, "dispositions": {},
                 "adopted": 0, "adoption_conflicts": 0}


def evaluate(name: str, baseline: Path, embed: Embedder, *, oracle: bool = False, **kwargs) -> Result:
    result = Result(name)
    for case in TRIO:
        segments = committed_segments(baseline, case)
        if oracle:
            hypothesis, telemetry = oracle_labels(case, segments)
        else:
            hypothesis, telemetry = replay(case, segments, embed, **kwargs)
        scored = score(case, hypothesis)
        result.per_case[case] = {
            "speaker_accuracy": scored["speaker_accuracy"],
            "der": scored["diarization_error_rate"],
            "confused_speaker_seconds": scored["confused_speaker_seconds"],
            "missed_speaker_seconds": scored["missed_speaker_seconds"],
            "s00_seconds": round(s00_seconds(hypothesis), 3),
            "s00_segments": sum(1 for h in hypothesis if h.speaker == "S00"),
            "hyp_speakers": len({h.speaker for h in hypothesis}),
            **{k: v for k, v in telemetry.items() if k in
               ("sweeps", "cadence_sweeps", "corrections", "applied_corrections", "canonical",
                "abstains", "unit_count", "dispositions", "adopted", "adoption_conflicts")},
        }
    return result


def trio_mean(result: Result, key: str) -> float:
    return sum(result.per_case[c][key] for c in TRIO) / len(TRIO)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--json-output", type=Path, default=Path(__file__).with_suffix(".results.json"))
    args = parser.parse_args()

    embed = Embedder(load_encoder())
    published = {case: committed_segments(args.baseline, case) for case in TRIO}

    levers = [
        ("baseline", dict()),
        ("C1-merged", dict(merged=True)),
        ("C1adopt-prev", dict(adopt="prev")),
        ("C1adopt-both", dict(adopt="both")),
        ("C2a-cadence20", dict(sweep_interval=20.0)),
        ("C2b-margin.05", dict(sweep_margin=0.05)),
        ("C2c-ledger-floor0", dict(ledger_floor_samples=0)),
        ("C2b+C2c", dict(sweep_margin=0.05, ledger_floor_samples=0)),
        ("C1+C2b", dict(merged=True, sweep_margin=0.05)),
        ("C1adopt+C2b", dict(adopt="both", sweep_margin=0.05)),
        ("C1adoptprev+C2b", dict(adopt="prev", sweep_margin=0.05)),
        ("ORACLE-labels", dict(oracle=True)),
    ]
    results = [evaluate(name, args.baseline, embed, **kwargs) for name, kwargs in levers]

    base = results[0]
    print("\n=== fidelity: replayed baseline vs the deployed run's published labels ===")
    for case in TRIO:
        replayed, _ = replay(case, published[case], embed)
        agree = sum(1 for r, p in zip(replayed, published[case]) if r.speaker == p.label)
        print(f"  {case:18s} {agree}/{len(published[case])} segment labels reproduced")

    print("\n=== levers (trio mean; every lever is label-only, extents untouched) ===")
    header = f"{'lever':20s} {'spk_acc':>8s} {'d vs base':>10s} {'DER':>7s} {'conf_s':>7s} {'S00_s':>6s} {'S00_n':>6s} {'corr':>5s}"
    print(header)
    for result in results:
        acc = trio_mean(result, "speaker_accuracy")
        print(f"{result.name:20s} {acc:8.4f} {acc - trio_mean(base, 'speaker_accuracy'):+10.4f} "
              f"{trio_mean(result, 'der'):7.4f} {trio_mean(result, 'confused_speaker_seconds'):7.2f} "
              f"{trio_mean(result, 's00_seconds'):6.2f} {trio_mean(result, 's00_segments'):6.2f} "
              f"{trio_mean(result, 'applied_corrections'):5.2f}")

    print("\n=== per case (regression check: no cell may fall below baseline) ===")
    for result in results:
        row = "  ".join(
            f"{c.split('_', 1)[1][:10]:10s} acc {result.per_case[c]['speaker_accuracy']:.4f}"
            f"{'!' if result.per_case[c]['speaker_accuracy'] < base.per_case[c]['speaker_accuracy'] - 1e-9 else ' '}"
            f" conf {result.per_case[c]['confused_speaker_seconds']:.2f}s "
            f"S00 {result.per_case[c]['s00_seconds']:.2f}s"
            for c in TRIO
        )
        regressed = any(result.per_case[c]["speaker_accuracy"] < base.per_case[c]["speaker_accuracy"] - 1e-9
                        for c in TRIO)
        print(f"{result.name:20s} {row}   {'REGRESSION' if regressed else ''}")

    print("\n=== gates ===")
    base_acc = trio_mean(base, "speaker_accuracy")
    base_s00 = trio_mean(base, "s00_seconds")
    ceiling = trio_mean(results[-1], "speaker_accuracy")
    print(f"  baseline trio acc {base_acc:.4f} | identity ceiling (ORACLE-labels) {ceiling:.4f} | "
          f"file arm .8979 | G1 bar .89")
    for result in results[1:]:
        acc = trio_mean(result, "speaker_accuracy")
        s00 = trio_mean(result, "s00_seconds")
        regressed = any(result.per_case[c]["speaker_accuracy"] < base.per_case[c]["speaker_accuracy"] - 1e-9
                        for c in TRIO)
        new_conf = any(result.per_case[c]["confused_speaker_seconds"]
                       > base.per_case[c]["confused_speaker_seconds"] + 1e-9 for c in TRIO)
        headroom = (acc - base_acc) / max(ceiling - base_acc, 1e-9)
        print(f"  {result.name:20s} G1 {'PASS' if acc >= 0.89 and not regressed else 'FAIL'} "
              f"({acc:.4f}) | G1' headroom {headroom * 100:5.1f}% "
              f"{'PASS' if headroom >= 0.5 and not regressed else 'FAIL'} | "
              f"G2 S00 {s00:.2f}s ({(1 - s00 / base_s00) * 100:5.1f}% cut) "
              f"{'PASS' if s00 <= base_s00 * 0.5 and not new_conf else 'FAIL'}"
              f"{'  [REGRESSION]' if regressed else ''}{'  [NEW CONFUSION]' if new_conf else ''}")

    print("\n=== sweep telemetry ===")
    for result in results:
        for case in TRIO:
            pc = result.per_case[case]
            print(f"{result.name:20s} {case:18s} sweeps={pc['sweeps']} cadence={pc['cadence_sweeps']} "
                  f"corrections={pc['corrections']} applied={pc['applied_corrections']} "
                  f"canonical={pc['canonical']} abstains={pc['abstains']} units={pc['unit_count']} "
                  f"dispositions={pc['dispositions']}")

    payload = {
        "baseline_dir": str(args.baseline),
        "deployed_config": {
            "min_segment_samples": MIN_EVID_SAMPLES, "birth_min_seconds": BIRTH_MIN_SECONDS,
            "album_admission_seconds": ADMISSION_SECONDS, "min_match_score": MIN_MATCH_SCORE,
            "min_match_margin": MIN_MATCH_MARGIN, "sweep_interval_seconds": SWEEP_INTERVAL_SECONDS,
            "sweep_merge_threshold": SWEEP_MERGE_THRESHOLD,
        },
        "c1_knobs": {"gap_max": GAP_MAX, "window_cap": WINDOW_CAP},
        "encoder_calls": embed.calls,
        "levers": {r.name: r.per_case for r in results},
        "trio_means": {
            r.name: {k: round(trio_mean(r, k), 4) for k in
                     ("speaker_accuracy", "der", "confused_speaker_seconds",
                      "missed_speaker_seconds", "s00_seconds", "s00_segments")}
            for r in results
        },
    }
    args.json_output.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nwrote {args.json_output}  ({embed.calls} encoder calls)")


if __name__ == "__main__":
    main()
