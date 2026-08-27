"""P-M4-C: what should the terminal finalizer send when its proposal overlaps at a seam?

Why this exists (`PREREGISTRATION-M4-seam.md`, candidate 8e). Iteration 29 scored the M4
exit at 11 of 14 gates, and all three failures are ONE refused publication on ONE case:
`lex_adam_frank` is the only gated meeting long enough for file mode to plan two windows,
its two windows both keep a decoding of the audio around `135.0` s, and the resulting pair
`[131.19,136.29] / [133.95,136.62]` overlaps by 2.34 s. The terminal pass reproduces that
file arm exactly and `LiveSession._text_revision_refusal` refuses it
`segments_out_of_order`.

File mode may not change (PRD: file-mode outputs byte-identical), so the question is what
the finalizer -- the producer -- should send instead. Six arms, defined in the
preregistration and implemented once here.

No MOSS request, no service, no GPU: the terminal proposal IS the paired file arm (measured
at `0.000000` on five axes in iterations 25/27/29), so every arm is applied offline to the
twelve file arms the iteration-29 batch already produced, and scored on the campaign's own
clock. Admissibility is checked against the PRODUCTION refusal rule, imported, not restated.

    python measure_seam_overlap.py                 # measure, render, score the gates
    python measure_seam_overlap.py --json out.json # ... and write the record
    python measure_seam_overlap.py --selftest      # the harness reacts to a broken arm
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluator_v2 import Segment as V2Segment, score_v2, speech_regions_from_wav  # noqa: E402
from measure_m4_baseline import (  # noqa: E402
    THREE_MINUTE_CASE,
    THREE_MINUTE_ROOT,
    arm_scores,
    deployed_axes,
    load_reference_rows,
)
from moss_transcribe_diarize import live_speaker_accuracy as lsa  # noqa: E402
from moss_transcribe_diarize.app.live_session import (  # noqa: E402
    LIVE_SAMPLE_RATE,
    EffectiveTranscriptSegment,
    LiveSession,
    TextRevisionProposal,
)
from moss_transcribe_diarize.evaluation import (  # noqa: E402
    Segment,
    calculate_diarization,
    calculate_tbsa,
)

#: The batch this reads. Iteration 29's M4 exit: five gated cases plus the diagnostic one,
#: two runs each, file arms byte-identical to their checked-in comparators.
BATCH = REPO / "evidence/live-convergence-0824/M4-e4-exit/passes"
CASES_CONTRACT = Path(__file__).resolve().parent / "cases.json"
#: `cases.json` names the five-minute case by its corpus id; the drivers name it by its
#: pass id. One mapping, here, so nothing downstream has to know about it.
CONTRACT_ALIASES = {"5m-lex-keyu-jin": "keyu-5m"}

#: The comparator the M4 rows read for the three-minute case (iteration 29's `gates.json`,
#: node `three_minute_rolling`): the rolling arm of the passes that acquired the case.
THREE_MINUTE_ROLLING = {
    "wer": 0.122411,
    "content_recall": 0.951036,
    "matched_word_speaker_accuracy": 0.951036,
}
G8_WER_TOLERANCE = 0.010
TERMINAL_DER_TOLERANCE = 0.020


# ------------------------------------------------------------------ the thing under test


@dataclass(frozen=True, slots=True)
class Placed:
    """One decoded segment on the session clock, in the shape the finalizer builds."""

    speaker: str
    start_sample: int
    end_sample: int
    text: str


@dataclass(frozen=True, slots=True)
class Resolution:
    """What one arm did to one proposal."""

    segments: tuple[Placed, ...]
    dropped: int
    merged: int
    displaced_samples: int


def _ordered(segments):
    """Sorted by where a segment begins, then how far it reaches; ties keep parse order."""

    return sorted(segments, key=lambda item: (item.start_sample, item.end_sample))


def _words(text: str) -> int:
    return len(text.split())


def arm_admit(segments):
    """A1 - the surface holds the overlap verbatim, i.e. what file mode itself publishes."""

    return Resolution(tuple(_ordered(segments)), dropped=0, merged=0, displaced_samples=0)


def arm_clip_later_start(segments):
    """A2 - the later segment starts where the published frontier already reaches."""

    out: list[Placed] = []
    dropped = displaced = 0
    frontier = 0
    for segment in _ordered(segments):
        start = max(segment.start_sample, frontier)
        if segment.end_sample <= start:
            dropped += 1
            displaced += segment.end_sample - segment.start_sample
            continue
        displaced += start - segment.start_sample
        out.append(replace(segment, start_sample=start))
        frontier = segment.end_sample
    return Resolution(tuple(out), dropped=dropped, merged=0, displaced_samples=displaced)


def arm_clip_earlier_end(segments):
    """A3 - the earlier segment stops where the later one begins."""

    out: list[Placed] = []
    dropped = displaced = 0
    for segment in _ordered(segments):
        while out and out[-1].end_sample > segment.start_sample:
            previous = out[-1]
            if previous.start_sample < segment.start_sample:
                displaced += previous.end_sample - segment.start_sample
                out[-1] = replace(previous, end_sample=segment.start_sample)
                break
            # The earlier segment begins at or after this one: there is no trim that
            # leaves it advancing, so it cannot survive this resolution.
            out.pop()
            dropped += 1
            displaced += previous.end_sample - previous.start_sample
        out.append(segment)
    return Resolution(tuple(out), dropped=dropped, merged=0, displaced_samples=displaced)


def arm_merge_overlapping(segments):
    """A4 - one speaker's overlapping decodings become one segment over their union."""

    out: list[Placed] = []
    dropped = merged = displaced = 0
    for segment in _ordered(segments):
        if out and segment.start_sample < out[-1].end_sample:
            previous = out[-1]
            if previous.speaker == segment.speaker:
                out[-1] = replace(
                    previous,
                    end_sample=max(previous.end_sample, segment.end_sample),
                    # The scorer concatenates a hypothesis with `" ".join(...)` before it
                    # tokenizes (`evaluation.calculate_tbsa`), so a single space is the
                    # join that leaves the word stream exactly as it was.
                    text=f"{previous.text} {segment.text}",
                )
                merged += 1
                continue
            # Two speakers over one interval: the surface cannot say that, so the later
            # one yields the audio the earlier one already owns (A2's rule).
            start = max(segment.start_sample, previous.end_sample)
            if segment.end_sample <= start:
                dropped += 1
                displaced += segment.end_sample - segment.start_sample
                continue
            displaced += start - segment.start_sample
            segment = replace(segment, start_sample=start)
        out.append(segment)
    return Resolution(tuple(out), dropped=dropped, merged=merged, displaced_samples=displaced)


def arm_drop_later(segments):
    """A5 - the later overlapping segment is discarded whole."""

    out: list[Placed] = []
    dropped = displaced = 0
    for segment in _ordered(segments):
        if out and segment.start_sample < out[-1].end_sample:
            dropped += 1
            displaced += segment.end_sample - segment.start_sample
            continue
        out.append(segment)
    return Resolution(tuple(out), dropped=dropped, merged=0, displaced_samples=displaced)


#: A0 (`refuse`) has no resolution: it is the absence of a proposal.
ARMS = {
    "admit": arm_admit,
    "clip_later_start": arm_clip_later_start,
    "clip_earlier_end": arm_clip_earlier_end,
    "merge_overlapping": arm_merge_overlapping,
    "drop_later": arm_drop_later,
}
#: `admit` is priced, never selected: it is a change to the session's contract, not a
#: finalizer policy (preregistration, Arms).
CANDIDATES = ("clip_later_start", "clip_earlier_end", "merge_overlapping", "drop_later")


# ------------------------------------------------------------------ admissibility


def refusal_of(segments, *, end_sample: int) -> str | None:
    """What the PRODUCTION session would say about this proposal, or `None` if it may publish.

    `LiveSession._text_revision_refusal` reads five attributes of the session and nothing
    else, so it is called here on a stand-in carrying exactly those five in the state a
    terminal pass meets: epoch 0, no revision yet, not finalized, the rolling frontier
    wherever it got to, and the meeting's committed audio. The rule itself is imported --
    a restatement of it here could drift from the one that actually refuses.
    """

    session = SimpleNamespace(
        _epoch=0,
        _text_revision_version=0,
        _finalization_status="running",
        _canonical_through_sample=end_sample,
        _committed_samples=end_sample,
        _text_revision_refusals={},
    )
    proposal = TextRevisionProposal(
        epoch=0,
        base_text_revision_version=0,
        source="terminal",
        start_sample=0,
        end_sample=end_sample,
        segments=tuple(
            EffectiveTranscriptSegment(
                start_sample=item.start_sample,
                end_sample=item.end_sample,
                text=item.text,
                canonical_speaker=None,
                authority="terminal",
            )
            for item in segments
        ),
    )
    return LiveSession._text_revision_refusal(session, proposal)


def structure_faults(segments, *, end_sample: int) -> list[str]:
    """G-S4 stated as the properties a published surface has, checked one at a time."""

    faults: list[str] = []
    frontier = 0
    for index, segment in enumerate(segments):
        if segment.end_sample <= segment.start_sample:
            faults.append(f"segment {index} does not advance")
        if segment.start_sample < frontier:
            faults.append(f"segment {index} overlaps its predecessor")
        if segment.start_sample < 0 or segment.end_sample > end_sample:
            faults.append(f"segment {index} leaves [0, {end_sample}]")
        frontier = max(frontier, segment.end_sample)
    return faults


def invented_boundaries(before, after) -> list[int]:
    """G-S3: a boundary an arm emits that no input segment ever claimed."""

    known = {item.start_sample for item in before} | {item.end_sample for item in before}
    emitted = {item.start_sample for item in after} | {item.end_sample for item in after}
    return sorted(emitted - known)


# ------------------------------------------------------------------ reading the batch


def corpus_paths() -> dict[str, dict]:
    """Audio and reference for every case the batch holds a file arm for."""

    contract = json.loads(CASES_CONTRACT.read_text())
    paths = {}
    for case in contract["cases"]:
        entry = {
            "audio": REPO / case["audio"],
            "reference": REPO / case["reference"],
            "tier": case.get("tier"),
        }
        # Both names are reachable: `cases.json` calls the five-minute case by its corpus
        # id, its driver's `results.json` by its pass id, and this reads both.
        paths[case["case_id"]] = entry
        paths[CONTRACT_ALIASES.get(case["case_id"], case["case_id"])] = entry
    sample = THREE_MINUTE_ROOT / "samples" / THREE_MINUTE_CASE
    paths[THREE_MINUTE_CASE] = {
        "audio": sample / "audio.wav",
        "reference": sample / "reference.jsonl",
        "tier": "primary",
    }
    return paths


def batch_arms(root: Path) -> list[dict]:
    """Every file arm on disk under one batch, with the case and run it belongs to.

    Discovered rather than listed: the batch layout differs per driver (the trio writes one
    `results.json` for four cases, the single-case drivers write one each), and a listing
    here would have to be edited every time a driver is added.
    """

    found = []
    for hypothesis in sorted(root.rglob("file-hypothesis.jsonl")):
        results = hypothesis.parent / "results.json"
        case = hypothesis.parent.name
        if results.exists():
            data = json.loads(results.read_text())
            case = data.get("case", case)
        else:  # the trio driver writes one results.json above its four case directories
            results = hypothesis.parent.parent / "results.json"
        run = next(
            (
                part.rsplit("-", 1)[-1]
                for part in reversed(hypothesis.relative_to(root).parts)
                if part.rsplit("-", 1)[-1] in {"A", "B"}
            ),
            "?",
        )
        found.append({"case": case, "run": run, "hypothesis": hypothesis, "results": results})
    return found


def placed_of(hypothesis: Path) -> tuple[Placed, ...]:
    """A file arm read into the shape the finalizer builds, on the session sample clock."""

    rows = [json.loads(line) for line in hypothesis.read_text().splitlines() if line.strip()]
    return tuple(
        Placed(
            speaker=str(row["speaker"]),
            start_sample=int(round(float(row["start"]) * LIVE_SAMPLE_RATE)),
            end_sample=int(round(float(row["end"]) * LIVE_SAMPLE_RATE)),
            text=str(row["text"]),
        )
        for row in rows
    )


def overlapping_pairs(segments) -> list[dict]:
    ordered = _ordered(segments)
    pairs = []
    for index in range(1, len(ordered)):
        earlier, later = ordered[index - 1], ordered[index]
        if later.start_sample < earlier.end_sample:
            pairs.append(
                {
                    "index": index,
                    "earlier": [earlier.start_sample, earlier.end_sample, earlier.speaker],
                    "later": [later.start_sample, later.end_sample, later.speaker],
                    "overlap_sec": round(
                        (earlier.end_sample - later.start_sample) / LIVE_SAMPLE_RATE, 6
                    ),
                    "same_speaker": earlier.speaker == later.speaker,
                }
            )
    return pairs


# ------------------------------------------------------------------ scoring


def to_eval(segments) -> list[Segment]:
    return [
        Segment(
            start=item.start_sample / LIVE_SAMPLE_RATE,
            end=item.end_sample / LIVE_SAMPLE_RATE,
            speaker=item.speaker,
            text=item.text,
        )
        for item in segments
    ]


def score_surface(segments, *, reference_transcript, reference_activity, reference_v2, regions):
    """The campaign's clock, and evaluator v2 beside it, for one candidate surface."""

    evaluated = to_eval(segments)
    tbsa = calculate_tbsa(reference_transcript, evaluated)
    diarization = calculate_diarization(reference_transcript, evaluated)
    speaker = lsa.score_live_speaker_accuracy(
        list(reference_activity),
        [lsa.SpeakerActivityInterval(item.start, item.end, item.speaker) for item in evaluated],
    )
    v2 = score_v2(
        reference_v2,
        [
            V2Segment(start=item.start, end=item.end, speaker=item.speaker, text=item.text)
            for item in evaluated
        ],
        speech_regions=regions,
        speech_regions_source="webrtcvad_mode1_10ms" if regions else "reference_intervals",
    )
    return {
        "wer": tbsa["wer"],
        "text_coverage": tbsa["text_coverage"],
        "der": diarization["der"],
        "miss": diarization["miss"],
        "false_alarm": diarization["false_alarm"],
        "speaker_confusion": diarization["speaker_confusion"],
        "speaker_accuracy": speaker["speaker_accuracy"],
        "segments": len(evaluated),
        "v2": {
            "wer": v2["wer"]["wer"],
            "content_recall": v2["content_recall"],
            "matched_word_speaker_accuracy": v2["matched_word_speaker"][
                "matched_word_speaker_accuracy"
            ],
            "der_reference_speech": v2["der_reference_speech"]["der"],
        },
    }


def recorded_file_axes(results: Path, case: str) -> dict | None:
    arms = arm_scores(results, case) if results.exists() else {}
    return deployed_axes(arms["file"]) if "file" in arms else None


# ------------------------------------------------------------------ the measurement


def measure(root: Path = BATCH, arms=None) -> dict:
    arms = arms or ARMS
    paths = corpus_paths()
    report: dict = {"batch": str(root.relative_to(REPO)), "arms": sorted(arms), "cases": []}
    cache: dict[str, dict] = {}
    for entry in batch_arms(root):
        case = entry["case"]
        if case not in paths:
            raise SystemExit(f"REFUSED: no corpus contract for case {case!r}")
        if case not in cache:
            reference_rows = load_reference_rows(paths[case]["reference"])
            cache[case] = {
                "transcript": [
                    Segment(
                        start=float(row["start"]),
                        end=float(row["end"]),
                        speaker=str(row["speaker"]),
                        text=str(row["text"]),
                    )
                    for row in reference_rows
                ],
                "activity": lsa.load_reference_speaker_activity_jsonl(paths[case]["reference"]),
                "v2": [V2Segment(**row) for row in reference_rows],
                "regions": (
                    speech_regions_from_wav(paths[case]["audio"])
                    if paths[case]["audio"].exists()
                    else None
                ),
            }
        reference = cache[case]
        segments = placed_of(entry["hypothesis"])
        end_sample = max((item.end_sample for item in segments), default=0)
        node = {
            "case": case,
            "run": entry["run"],
            "tier": paths[case]["tier"],
            "hypothesis": str(entry["hypothesis"].relative_to(REPO)),
            "input_segments": len(segments),
            "input_words": sum(_words(item.text) for item in segments),
            "end_sample": end_sample,
            "overlaps": overlapping_pairs(segments),
            "input_refusal": refusal_of(_ordered(segments), end_sample=end_sample),
            "recorded_file_axes": recorded_file_axes(entry["results"], case),
            "resolutions": {},
        }
        for name, arm in sorted(arms.items()):
            resolution = arm(segments)
            scored = score_surface(
                resolution.segments,
                reference_transcript=reference["transcript"],
                reference_activity=reference["activity"],
                reference_v2=reference["v2"],
                regions=reference["regions"],
            )
            node["resolutions"][name] = {
                "segments": len(resolution.segments),
                "words": sum(_words(item.text) for item in resolution.segments),
                "words_lost": node["input_words"]
                - sum(_words(item.text) for item in resolution.segments),
                "dropped": resolution.dropped,
                "merged": resolution.merged,
                "displaced_sec": round(resolution.displaced_samples / LIVE_SAMPLE_RATE, 6),
                "refusal": refusal_of(resolution.segments, end_sample=end_sample),
                "structure_faults": structure_faults(resolution.segments, end_sample=end_sample),
                "invented_boundaries": invented_boundaries(segments, resolution.segments),
                "identity": resolution.segments == tuple(_ordered(segments)),
                "scores": scored,
            }
        report["cases"].append(node)
    report["synthetic"] = synthetic_shapes(arms)
    return report


# ------------------------------------------------------------------ synthetic shapes


def _shape(*rows) -> tuple[Placed, ...]:
    return tuple(
        Placed(speaker=speaker, start_sample=start, end_sample=end, text=text)
        for speaker, start, end, text in rows
    )


def _synthetic_inputs() -> dict:
    """The overlap shapes, as inputs -- shared by the arm sweep and the production check."""

    return {
        "disjoint": _shape(("A", 0, 100, "one"), ("A", 100, 200, "two")),
        "touching": _shape(("A", 0, 100, "one"), ("A", 100, 200, "two"), ("A", 200, 300, "three")),
        "pair_same_speaker": _shape(("A", 0, 160, "one"), ("A", 120, 200, "two")),
        "pair_cross_speaker": _shape(("A", 0, 160, "one"), ("B", 120, 200, "two")),
        "contained": _shape(("A", 0, 200, "one"), ("A", 50, 100, "two")),
        "contained_cross_speaker": _shape(("A", 0, 200, "one"), ("B", 50, 100, "two")),
        "identical": _shape(("A", 0, 100, "one"), ("A", 0, 100, "two")),
        "chain_of_three": _shape(("A", 0, 150, "one"), ("A", 100, 250, "two"), ("A", 200, 300, "three")),
        "chain_mixed_speakers": _shape(("A", 0, 150, "one"), ("B", 100, 250, "two"), ("A", 200, 300, "three")),
        "later_ends_earlier": _shape(("A", 0, 200, "one"), ("A", 100, 150, "two"), ("A", 220, 300, "three")),
        "unsorted_input": _shape(("A", 200, 300, "three"), ("A", 0, 100, "one"), ("A", 100, 200, "two")),
        "single": _shape(("A", 0, 100, "one")),
    }


def synthetic_shapes(arms=None) -> dict:
    """Every overlap shape the seam rule must be total on, not only the one the corpus has.

    The corpus holds exactly one overlapping pair, same speaker, later-ends-later. A rule
    validated on that alone is a rule validated on one sample, so the shapes below are the
    ones a two-window seam can produce in general: containment, identical extents, chains,
    a later segment that ends earlier, and the cross-speaker case the corpus never shows.
    """

    arms = arms or ARMS
    shapes = _synthetic_inputs()
    out: dict = {}
    for name, segments in shapes.items():
        end_sample = max(item.end_sample for item in segments)
        node = {
            "input_segments": len(segments),
            "input_words": sum(_words(item.text) for item in segments),
            "overlaps": len(overlapping_pairs(segments)),
            "arms": {},
        }
        for arm_name, arm in sorted(arms.items()):
            resolution = arm(segments)
            node["arms"][arm_name] = {
                "segments": len(resolution.segments),
                "words_lost": node["input_words"]
                - sum(_words(item.text) for item in resolution.segments),
                "displaced_sec": round(resolution.displaced_samples / LIVE_SAMPLE_RATE, 6),
                "refusal": refusal_of(resolution.segments, end_sample=end_sample),
                "structure_faults": structure_faults(resolution.segments, end_sample=end_sample),
                "invented_boundaries": invented_boundaries(segments, resolution.segments),
                "extents": [[item.start_sample, item.end_sample, item.speaker] for item in resolution.segments],
            }
        out[name] = node
    return out


# ------------------------------------------------------------------ gates


def _fmt(value, places: int = 6) -> str:
    return "-" if value is None else f"{value:.{places}f}"


def gates(report: dict) -> dict:
    rows: list[dict] = []

    def gate(gid, title, ok, detail):
        rows.append({"id": gid, "title": title, "pass": bool(ok), "detail": detail})

    candidates = [name for name in report["arms"] if name in CANDIDATES]

    # G-S1 admissible
    refused = [
        f"{node['case']}/{node['run']}:{name}={node['resolutions'][name]['refusal']}"
        for node in report["cases"]
        for name in candidates
        if node["resolutions"][name]["refusal"] is not None
    ]
    refused += [
        f"synthetic {shape}:{name}={node['arms'][name]['refusal']}"
        for shape, node in report["synthetic"].items()
        for name in candidates
        if node["arms"][name]["refusal"] is not None
    ]
    gate(
        "G-S1",
        "every candidate arm yields a proposal the production rule accepts",
        not refused,
        f"{len(report['cases']) * len(candidates)} file arms + "
        f"{len(report['synthetic']) * len(candidates)} synthetic; refused: {refused or 'none'}",
    )

    # G-S2 identity off the seam
    clean = [node for node in report["cases"] if not node["overlaps"]]
    broken = [
        f"{node['case']}/{node['run']}:{name}"
        for node in clean
        for name in candidates
        if not node["resolutions"][name]["identity"]
    ]
    gate(
        "G-S2",
        "on a file arm with no overlapping pair every candidate is the identity",
        clean and not broken,
        f"{len(clean)} of {len(report['cases'])} arms have no overlap; changed: {broken or 'none'}",
    )

    # G-S3 no invented boundary
    invented = [
        f"{node['case']}/{node['run']}:{name}={node['resolutions'][name]['invented_boundaries']}"
        for node in report["cases"]
        for name in sorted(report["arms"])
        if node["resolutions"][name]["invented_boundaries"]
    ]
    invented += [
        f"synthetic {shape}:{name}={node['arms'][name]['invented_boundaries']}"
        for shape, node in report["synthetic"].items()
        for name in sorted(report["arms"])
        if node["arms"][name]["invented_boundaries"]
    ]
    gate("G-S3", "no arm emits a boundary the input never claimed", not invented, invented or "none")

    # G-S4 total and sorted
    faults = [
        f"synthetic {shape}:{name}={node['arms'][name]['structure_faults']}"
        for shape, node in report["synthetic"].items()
        for name in candidates
        if node["arms"][name]["structure_faults"]
    ]
    faults += [
        f"{node['case']}/{node['run']}:{name}={node['resolutions'][name]['structure_faults']}"
        for node in report["cases"]
        for name in candidates
        if node["resolutions"][name]["structure_faults"]
    ]
    gate(
        "G-S4",
        "every candidate is total: sorted, advancing, non-overlapping, inside the meeting",
        not faults,
        f"{len(report['synthetic'])} shapes x {len(candidates)} arms; faults: {faults or 'none'}",
    )

    # G-S5 clock identity
    mismatch = []
    compared = 0
    for node in report["cases"]:
        recorded = node["recorded_file_axes"]
        if not recorded or "admit" not in node["resolutions"]:
            continue
        scored = node["resolutions"]["admit"]["scores"]
        for axis in ("wer", "der", "text_coverage", "speaker_accuracy"):
            if recorded.get(axis) is None:
                continue
            compared += 1
            if round(float(recorded[axis]), 6) != round(float(scored[axis]), 6):
                mismatch.append(
                    f"{node['case']}/{node['run']}.{axis}: recorded {recorded[axis]} vs {scored[axis]}"
                )
    gate(
        "G-S5",
        "the reference arm reproduces the shipped batch's own file-arm scores",
        compared and not mismatch,
        f"{compared} axis comparisons; mismatched: {mismatch or 'none'}",
    )

    # G-S6 word conservation
    conserving = [name for name in candidates if name != "drop_later"]
    lost = [
        f"{node['case']}/{node['run']}:{name}={node['resolutions'][name]['words_lost']}"
        for node in report["cases"]
        for name in conserving
        if node["resolutions"][name]["words_lost"]
    ]
    gate(
        "G-S6",
        "the word-conserving candidates lose no word of the meeting",
        conserving and not lost,
        f"{conserving}; lost: {lost or 'none'}",
    )

    return {"rows": rows, "passed": sum(1 for row in rows if row["pass"]), "total": len(rows)}


def selection(report: dict) -> dict:
    """The preregistered selection rule, applied to the arms that passed the gates."""

    seam = [node for node in report["cases"] if node["overlaps"]]
    ranked = []
    for name in CANDIDATES:
        if name not in report["arms"]:
            continue
        eligible = all(
            node["resolutions"][name]["refusal"] is None
            and not node["resolutions"][name]["structure_faults"]
            and not node["resolutions"][name]["invented_boundaries"]
            for node in report["cases"]
        )
        words_lost = sum(node["resolutions"][name]["words_lost"] for node in report["cases"])
        displaced = sum(node["resolutions"][name]["displaced_sec"] for node in report["cases"])
        deltas = {}
        for node in seam:
            scored = node["resolutions"][name]["scores"]
            reference = node["resolutions"]["admit"]["scores"] if "admit" in node["resolutions"] else scored
            for axis, value, target in (
                ("wer", scored["wer"], reference["wer"]),
                ("der", scored["der"], reference["der"]),
                ("v2_content_recall", scored["v2"]["content_recall"], reference["v2"]["content_recall"]),
                (
                    "v2_matched_word_speaker_accuracy",
                    scored["v2"]["matched_word_speaker_accuracy"],
                    reference["v2"]["matched_word_speaker_accuracy"],
                ),
            ):
                deltas[axis] = max(deltas.get(axis, 0.0), abs(value - target))
        ranked.append(
            {
                "arm": name,
                "eligible": eligible,
                "words_lost": words_lost,
                "displaced_sec": round(displaced, 6),
                "max_delta_vs_file": round(max(deltas.values()), 6) if deltas else 0.0,
                "deltas_vs_file": {axis: round(value, 6) for axis, value in sorted(deltas.items())},
            }
        )
    ranked.sort(
        key=lambda row: (
            not row["eligible"],
            row["words_lost"],
            row["displaced_sec"],
            row["max_delta_vs_file"],
        )
    )
    return {"ranked": ranked, "selected": ranked[0]["arm"] if ranked and ranked[0]["eligible"] else None}


def m4_arithmetic(report: dict) -> dict:
    """What each arm would do to the four M4 rows the refusal is currently failing."""

    out: dict = {}
    for node in report["cases"]:
        if node["case"] != THREE_MINUTE_CASE:
            continue
        file_axes = node["resolutions"].get("admit", {}).get("scores")
        rows = {}
        for name in sorted(report["arms"]):
            scored = node["resolutions"][name]["scores"]
            rows[name] = {
                "wer": scored["wer"],
                "der": scored["der"],
                "v2_content_recall": scored["v2"]["content_recall"],
                "v2_matched_word_speaker_accuracy": scored["v2"]["matched_word_speaker_accuracy"],
                "G-M4-1": abs(scored["wer"] - file_axes["wer"]) <= G8_WER_TOLERANCE,
                "G-M4-2": abs(scored["der"] - file_axes["der"]) <= TERMINAL_DER_TOLERANCE,
                "G-M4-3": scored["wer"] <= THREE_MINUTE_ROLLING["wer"],
                "G-M4-4": (
                    scored["v2"]["content_recall"] >= THREE_MINUTE_ROLLING["content_recall"]
                    and scored["v2"]["matched_word_speaker_accuracy"]
                    >= THREE_MINUTE_ROLLING["matched_word_speaker_accuracy"]
                ),
            }
        # A0: the meeting keeps the rolling surface it already published.
        rows["refuse"] = {
            "wer": THREE_MINUTE_ROLLING["wer"],
            "der": None,
            "v2_content_recall": THREE_MINUTE_ROLLING["content_recall"],
            "v2_matched_word_speaker_accuracy": THREE_MINUTE_ROLLING["matched_word_speaker_accuracy"],
            "G-M4-1": abs(THREE_MINUTE_ROLLING["wer"] - file_axes["wer"]) <= G8_WER_TOLERANCE,
            "G-M4-2": False,
            "G-M4-3": True,
            "G-M4-4": True,
        }
        out[f"{node['case']}/{node['run']}"] = rows
    return out


# ------------------------------------------------------------------ rendering


def render(report: dict, gate_report: dict, chosen: dict, arithmetic: dict) -> str:
    lines = ["P-M4-C - the seam refusal, six arms over one batch", ""]
    lines.append(f"batch: {report['batch']}")
    lines.append("")
    lines.append("WHERE THE OVERLAP IS")
    for node in report["cases"]:
        mark = "OVERLAP" if node["overlaps"] else "clean  "
        detail = ""
        if node["overlaps"]:
            pair = node["overlaps"][0]
            detail = (
                f"  {pair['overlap_sec']:.2f}s at "
                f"[{pair['earlier'][0] / LIVE_SAMPLE_RATE:.2f},{pair['earlier'][1] / LIVE_SAMPLE_RATE:.2f}]"
                f"/[{pair['later'][0] / LIVE_SAMPLE_RATE:.2f},{pair['later'][1] / LIVE_SAMPLE_RATE:.2f}]"
                f"  same_speaker={pair['same_speaker']}"
            )
        lines.append(
            f"  {mark}  {node['case']:<22} {node['run']}  {node['input_segments']:>3} segments  "
            f"input refusal={node['input_refusal']}{detail}"
        )
    lines.append("")

    lines.append("WHAT EACH ARM COSTS, ON THE ARM THAT OVERLAPS")
    header = f"  {'arm':<20}{'segs':>6}{'words lost':>12}{'displaced s':>13}{'wer':>10}{'der':>10}{'v2 recall':>11}{'v2 mw-spk':>11}  refusal"
    for node in report["cases"]:
        if not node["overlaps"]:
            continue
        lines.append(f"  {node['case']}/{node['run']}  ({node['input_words']} words in)")
        lines.append(header)
        for name in sorted(report["arms"]):
            row = node["resolutions"][name]
            scored = row["scores"]
            lines.append(
                f"  {name:<20}{row['segments']:>6}{row['words_lost']:>12}{row['displaced_sec']:>13.2f}"
                f"{scored['wer']:>10.6f}{scored['der']:>10.6f}{scored['v2']['content_recall']:>11.6f}"
                f"{scored['v2']['matched_word_speaker_accuracy']:>11.6f}  {row['refusal']}"
            )
    lines.append("")

    lines.append("THE FOUR M4 ROWS THIS CASE IS FAILING, UNDER EACH ARM")
    for key, rows in arithmetic.items():
        lines.append(f"  {key}")
        lines.append(
            f"  {'arm':<20}{'wer':>10}{'der':>10}{'G-M4-1':>9}{'G-M4-2':>9}{'G-M4-3':>9}{'G-M4-4':>9}"
        )
        for name, row in rows.items():
            lines.append(
                f"  {name:<20}{_fmt(row['wer'])!s:>10}{_fmt(row['der'])!s:>10}"
                f"{('PASS' if row['G-M4-1'] else 'FAIL'):>9}{('PASS' if row['G-M4-2'] else 'FAIL'):>9}"
                f"{('PASS' if row['G-M4-3'] else 'FAIL'):>9}{('PASS' if row['G-M4-4'] else 'FAIL'):>9}"
            )
    lines.append("")

    lines.append("SYNTHETIC SHAPES (totality)")
    lines.append(f"  {'shape':<26}{'overlaps':>9}  " + "  ".join(f"{name[:16]:<16}" for name in CANDIDATES))
    for shape, node in report["synthetic"].items():
        cells = []
        for name in CANDIDATES:
            arm = node["arms"][name]
            state = "ok" if arm["refusal"] is None and not arm["structure_faults"] else "BAD"
            cells.append(f"{state} {arm['segments']}seg -{arm['words_lost']}w".ljust(16))
        lines.append(f"  {shape:<26}{node['overlaps']:>9}  " + "  ".join(cells))
    lines.append("")

    lines.append("SELECTION (preregistered order: words lost, displaced seconds, max delta, simplicity)")
    lines.append(f"  {'arm':<20}{'eligible':>9}{'words lost':>12}{'displaced s':>13}{'max |d| vs file':>17}")
    for row in chosen["ranked"]:
        lines.append(
            f"  {row['arm']:<20}{str(row['eligible']):>9}{row['words_lost']:>12}"
            f"{row['displaced_sec']:>13.2f}{row['max_delta_vs_file']:>17.6f}"
        )
    lines.append(f"  SELECTED: {chosen['selected']}")
    lines.append("")

    lines.append("GATES")
    for row in gate_report["rows"]:
        lines.append(f"  {'PASS' if row['pass'] else 'FAIL'}  {row['id']:<6} {row['title']}")
        lines.append(f"          {row['detail']}")
    lines.append("")
    lines.append(f"  {gate_report['passed']} of {gate_report['total']} gates pass")
    return "\n".join(lines)


# ------------------------------------------------------------------ selftest


def selftest() -> int:
    """Does the harness react? A broken arm must be caught by the gate that OWNS it.

    Each mutant is otherwise a working arm, so that the gate it trips is the gate that
    names its defect rather than a side effect of leaving the seam unresolved. The one
    deliberate exception is `no resolution at all`, which trips two gates because two of
    them genuinely answer it: the production rule refuses an overlapping proposal (G-S1)
    and the harness's own structural reading calls it overlapping (G-S4).
    """

    def arm_invent_midpoint(segments):
        """Resolves at a boundary no input claimed - and is otherwise total. G-S3."""

        out: list[Placed] = []
        for segment in _ordered(segments):
            if out and segment.start_sample < out[-1].end_sample:
                previous = out[-1]
                midpoint = (previous.end_sample + segment.start_sample) // 2
                if previous.start_sample < midpoint < segment.end_sample:
                    out[-1] = replace(previous, end_sample=midpoint)
                    out.append(replace(segment, start_sample=midpoint))
                    continue
                return arm_clip_later_start(segments)  # shapes a midpoint cannot resolve
            out.append(segment)
        return Resolution(tuple(out), dropped=0, merged=0, displaced_samples=0)

    def arm_leave_overlap(segments):
        """Resolves nothing - G-S1 and G-S4, both of which are correct about it."""

        return Resolution(tuple(_ordered(segments)), dropped=0, merged=0, displaced_samples=0)

    def arm_touch_clean(segments):
        """Resolves correctly, then rewrites arms it had no business touching. G-S2."""

        resolved = arm_merge_overlapping(segments)
        return replace(
            resolved,
            segments=tuple(replace(item, text=item.text.upper()) for item in resolved.segments),
        )

    def arm_drop_words(segments):
        """Resolves correctly, then keeps only one side's words at the seam. G-S6."""

        resolved = arm_merge_overlapping(segments)
        if resolved.merged == 0:
            return resolved
        index = next(
            position
            for position, item in enumerate(resolved.segments)
            if " " in item.text and item.text != _ordered(segments)[position].text
        )
        kept = resolved.segments[index]
        return replace(
            resolved,
            segments=resolved.segments[:index]
            + (replace(kept, text=kept.text.split(" ", 1)[0]),)
            + resolved.segments[index + 1 :],
        )

    baseline = measure()
    base_gates = gates(baseline)
    failures = []
    if base_gates["passed"] != base_gates["total"]:
        failures.append(
            "the unmutated harness does not pass its own gates: "
            + ", ".join(row["id"] for row in base_gates["rows"] if not row["pass"])
        )

    mutations = {
        "invented boundary": ("clip_later_start", arm_invent_midpoint, {"G-S3"}),
        "no resolution at all": ("clip_later_start", arm_leave_overlap, {"G-S1", "G-S4"}),
        "touches a clean arm": ("clip_later_start", arm_touch_clean, {"G-S2"}),
        "loses words": ("merge_overlapping", arm_drop_words, {"G-S6"}),
    }
    reactions = []
    for label, (target, mutant, expected) in mutations.items():
        arms = dict(ARMS)
        arms[target] = mutant
        mutated = gates(measure(arms=arms))
        broke = {row["id"] for row in mutated["rows"] if not row["pass"]}
        reactions.append({"mutation": label, "broke": sorted(broke), "expected": sorted(expected)})
        if not expected & broke:
            failures.append(f"{label!r} broke {sorted(broke) or 'nothing'}, expected one of {sorted(expected)}")

    print("selftest - does a gate notice when its arm is wrong?")
    for row in reactions:
        print(f"  {row['mutation']:<24} broke {row['broke']}  (expected {row['expected']})")
    print()
    for failure in failures:
        print(f"  FAIL {failure}")
    print(f"  {len(failures)} failures over {len(mutations)} mutations")
    return 1 if failures else 0


def verify_production(root: Path = BATCH) -> int:
    """Does the rule that SHIPPED do what the selected arm was measured doing?

    The arm was chosen here, in this file; production carries its own implementation
    (`resolve_segment_overlaps`, candidate 8e-2). Two implementations of one rule are two
    rules until someone compares them, and if they disagree then every number in
    `evidence/live-convergence-0824/M4-seam-overlap/` describes something that never shipped.
    So: same inputs -- every file arm in the batch, plus every synthetic shape -- segment for
    segment, text for text.
    """

    from moss_transcribe_diarize.app.live_transcript_convergence import resolve_segment_overlaps

    def as_tuples(segments):
        return tuple((item.speaker, item.start_sample, item.end_sample, item.text) for item in segments)

    inputs = [(f"{entry['case']}-{entry['run']}", placed_of(entry["hypothesis"])) for entry in batch_arms(root)]
    inputs += [(f"synthetic:{name}", shape) for name, shape in _synthetic_inputs().items()]
    failures = []
    for name, segments in inputs:
        measured = arm_merge_overlapping(segments)
        shipped = resolve_segment_overlaps(as_tuples(segments))
        if as_tuples(measured.segments) != shipped.segments:
            failures.append(f"{name}: segments differ")
        elif (measured.merged, measured.dropped, measured.displaced_samples) != (
            shipped.merged, shipped.dropped, shipped.displaced_samples
        ):
            failures.append(f"{name}: counts differ")
    print("does production do what the selected arm was measured doing?")
    print(f"  inputs: {len(inputs)} ({len(inputs) - len(_synthetic_inputs())} file arms, "
          f"{len(_synthetic_inputs())} synthetic shapes)")
    for failure in failures:
        print(f"  FAIL {failure}")
    print("  " + ("IDENTICAL" if not failures else f"{len(failures)} disagreements"))
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=BATCH)
    parser.add_argument("--json", type=Path, help="write the full record here")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument(
        "--verify-production",
        action="store_true",
        help="compare the shipped `resolve_segment_overlaps` against the selected arm",
    )
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.verify_production:
        return verify_production(args.batch)

    report = measure(args.batch)
    gate_report = gates(report)
    chosen = selection(report)
    arithmetic = m4_arithmetic(report)
    report["gates"] = gate_report
    report["selection"] = chosen
    report["m4_arithmetic"] = arithmetic
    print(render(report, gate_report, chosen, arithmetic))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    return 0 if gate_report["passed"] == gate_report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
