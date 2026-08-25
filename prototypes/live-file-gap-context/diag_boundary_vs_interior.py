#!/usr/bin/env python3
"""D1/D2/D3: where do live errors live, relative to the live span grid?

Reads the frozen paired baseline (deployed stack, 2026-08-24) and answers, per case and
in aggregate:

  D1  Reference words within +/- BAND seconds of a live span boundary vs span-interior:
      per-class WER, deletion (miss) rate, and the share of the live-minus-file gap each
      class carries.  Coverage is decomposed exactly (the TBSA coverage term is a
      time-overlap quantity, so uncovered mass can be attributed to the boundary band
      without any word clock at all).
  D2  Concrete seam cases -- the boundaries that carry the most reference-word damage,
      printed with reference / live / file text on both sides.
  D3  Per-span WER as a function of span duration (hard-capped 2.5 s spans vs shorter).

One command:

    .venv/bin/python prototypes/live-file-gap-context/diag_boundary_vs_interior.py \
      --baseline <dir> --output prototypes/live-file-gap-context/diagnosis.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.evaluation import (  # noqa: E402
    Segment,
    _segment_order,
    _tokenize,
    calculate_tbsa,
)
from moss_transcribe_diarize.app.live_span_bounds import span_segments  # noqa: E402

CASES = ("lex_bill_ackman", "lex_javier_milei", "lex_keyu_jin")
CORPUS = REPO / "prototypes/streaming-diarization/data/real/benchmark_diarization_1min/samples"
SAMPLE_RATE = 16_000
BANDS = (0.25, 0.40, 0.60)
PRIMARY_BAND = 0.40


# ---------------------------------------------------------------- loading


def load_reference(case: str) -> list[Segment]:
    path = CORPUS / case / "reference.jsonl"
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        out.append(Segment(float(item["start"]), float(item["end"]), item["speaker"], item["text"]))
    return out


def load_hypothesis(path: Path) -> list[Segment]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        out.append(Segment(float(item["start"]), float(item["end"]), item["speaker"], item["text"]))
    return out


def load_spans(trace_path: Path) -> list[dict[str, Any]]:
    terminal = None
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("kind") == "terminal":
            terminal = row
    if terminal is None:
        raise RuntimeError(f"no terminal event in {trace_path}")
    spans = []
    for item in terminal["snapshot"]["session"]["committed"]:
        start = int(item["start_sample"])
        end = int(item["end_sample"])
        transcript = item.get("revised_transcript") or item.get("transcript") or ""
        parsed = span_segments(transcript, sample_count=end - start)
        spans.append({
            "span_id": int(item["span_id"]),
            "start_sample": start,
            "end_sample": end,
            "start": start / SAMPLE_RATE,
            "end": end / SAMPLE_RATE,
            "duration": (end - start) / SAMPLE_RATE,
            "transcript": transcript,
            "text": " ".join(seg.text for seg in parsed).strip(),
            "segments": [
                {"start": s.start, "end": s.end, "speaker": s.speaker, "text": s.text} for s in parsed
            ],
        })
    return spans


# ---------------------------------------------------------------- alignment


def align(reference: list[str], hypothesis: list[str]) -> list[tuple[str, int, int]]:
    """Levenshtein backtrace -> ops as (kind, ref_index, hyp_index)."""
    n, m = len(reference), len(hypothesis)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        ref_token = reference[i - 1]
        row, prev = dp[i], dp[i - 1]
        for j in range(1, m + 1):
            row[j] = min(
                prev[j - 1] + (ref_token != hypothesis[j - 1]),
                row[j - 1] + 1,
                prev[j] + 1,
            )
    ops: list[tuple[str, int, int]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (reference[i - 1] != hypothesis[j - 1]):
            ops.append(("match" if reference[i - 1] == hypothesis[j - 1] else "sub", i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(("del", i - 1, -1))
            i -= 1
        else:
            ops.append(("ins", i, j - 1))
            j -= 1
    ops.reverse()
    return ops


def segment_token_times(segments: list[Segment]) -> list[tuple[str, float]]:
    """Tokens of `segments` (in scoring order) with char-proportional times."""
    out: list[tuple[str, float]] = []
    for seg in sorted(segments, key=_segment_order):
        tokens = _tokenize(seg.text)
        if not tokens:
            continue
        total = sum(len(t) for t in tokens)
        duration = max(seg.end - seg.start, 1e-6)
        cursor = 0
        for token in tokens:
            centre = cursor + len(token) / 2.0
            out.append((token, seg.start + duration * (centre / total)))
            cursor += len(token)
    return out


def reference_word_clock(reference: list[Segment], file_hyp: list[Segment]) -> dict[str, Any]:
    """Time every reference token.

    Clock A anchors reference tokens on matching file-mode hypothesis tokens (file mode is
    the accurate arm and its timestamps come off the same decoder clock the live span grid
    is measured on); unmatched tokens are interpolated between anchors and clamped inside
    their own reference segment.  Clock B is pure within-reference-segment interpolation and
    exists only to show the boundary/interior split does not depend on the anchor choice.
    """
    ref_rows: list[tuple[str, int, float, float]] = []  # token, ref segment index, seg start, seg end
    clock_b: list[float] = []
    for index, seg in enumerate(sorted(reference, key=_segment_order)):
        tokens = _tokenize(seg.text)
        if not tokens:
            continue
        total = sum(len(t) for t in tokens)
        duration = max(seg.end - seg.start, 1e-6)
        cursor = 0
        for token in tokens:
            centre = cursor + len(token) / 2.0
            ref_rows.append((token, index, seg.start, seg.end))
            clock_b.append(seg.start + duration * (centre / total))
            cursor += len(token)

    ref_tokens = [row[0] for row in ref_rows]
    hyp_timed = segment_token_times(file_hyp)
    hyp_tokens = [t for t, _ in hyp_timed]
    anchors: dict[int, float] = {}
    for kind, ri, hj in align(ref_tokens, hyp_tokens):
        if kind == "match":
            anchors[ri] = hyp_timed[hj][1]

    clock_a: list[float] = []
    keys = sorted(anchors)
    for index in range(len(ref_tokens)):
        if index in anchors:
            value = anchors[index]
        elif not keys:
            value = clock_b[index]
        else:
            before = [k for k in keys if k < index]
            after = [k for k in keys if k > index]
            if before and after:
                lo, hi = before[-1], after[0]
                frac = (index - lo) / (hi - lo)
                value = anchors[lo] + frac * (anchors[hi] - anchors[lo])
            elif before:
                lo = before[-1]
                value = anchors[lo] + (index - lo) * 0.30
            else:
                hi = after[0]
                value = anchors[hi] - (hi - index) * 0.30
        _, _, seg_start, seg_end = ref_rows[index]
        clock_a.append(min(max(value, seg_start), seg_end))
    # enforce monotonicity
    for index in range(1, len(clock_a)):
        clock_a[index] = max(clock_a[index], clock_a[index - 1])
    return {
        "tokens": ref_tokens,
        "clock_a": clock_a,
        "clock_b": clock_b,
        "anchored": len(anchors),
        "anchor_rate": len(anchors) / max(1, len(ref_tokens)),
    }


def arm_anchored_clock(
    ref_tokens: list[str], hyp_segments: list[Segment]
) -> tuple[list[float], list[tuple[str, float]]]:
    """Time each reference token by the arm's own aligned hypothesis token.

    The most trustworthy clock available offline: a matched or substituted reference word
    is timed by the hypothesis token that consumed it, and the hypothesis timestamps come
    straight off the decoder for spans no longer than 2.5 s (live) or ~4 s (file), so the
    interpolation error inside a segment is far below the 0.4 s seam band.  A deleted
    reference word is bracketed by its surviving neighbours and interpolated between them,
    which places words swallowed by an empty span across exactly the interval that swallowed
    them.
    """
    timed = segment_token_times(hyp_segments)
    ops = align(ref_tokens, [t for t, _ in timed])
    anchors: dict[int, float] = {}
    for kind, ri, hj in ops:
        if kind in {"match", "sub"} and 0 <= ri < len(ref_tokens):
            anchors[ri] = timed[hj][1]
    keys = sorted(anchors)
    clock: list[float] = []
    for index in range(len(ref_tokens)):
        if index in anchors:
            clock.append(anchors[index])
            continue
        before = [k for k in keys if k < index]
        after = [k for k in keys if k > index]
        if before and after:
            lo, hi = before[-1], after[0]
            clock.append(anchors[lo] + (index - lo) / (hi - lo) * (anchors[hi] - anchors[lo]))
        elif before:
            clock.append(anchors[before[-1]] + (index - before[-1]) * 0.30)
        elif after:
            clock.append(max(0.0, anchors[after[0]] - (after[0] - index) * 0.30))
        else:
            clock.append(0.0)
    for index in range(1, len(clock)):
        clock[index] = max(clock[index], clock[index - 1])
    return clock, timed


def error_times(
    ref_tokens: list[str], hyp_segments: list[Segment], clock: list[float]
) -> list[tuple[str, float]]:
    """Every scoring error with the time it happened at, on the arm's own clock."""
    timed = segment_token_times(hyp_segments)
    ops = align(ref_tokens, [t for t, _ in timed])
    out: list[tuple[str, float]] = []
    for kind, ri, hj in ops:
        if kind == "match":
            continue
        if kind == "del":
            out.append(("del", clock[ri]))
        elif kind == "sub":
            out.append(("sub", timed[hj][1]))
        else:
            out.append(("ins", timed[hj][1]))
    return out


def bigram_survival(
    ref_tokens: list[str], clock: list[float], hyp_segments: list[Segment], seams: list[float]
) -> dict[str, Any]:
    """Do adjacent reference word pairs survive as adjacent hypothesis pairs?

    Split by whether the pair straddles a live span seam.  A cross-span phrase that the
    independent-span regime cannot see whole shows up here and nowhere else in TBSA.
    """
    hyp = _tokenize(" ".join(seg.text for seg in sorted(hyp_segments, key=_segment_order)))
    present = {(hyp[i], hyp[i + 1]) for i in range(len(hyp) - 1)}
    counts = {"straddling": [0, 0], "internal": [0, 0]}
    for index in range(len(ref_tokens) - 1):
        lo, hi = clock[index], clock[index + 1]
        straddles = any(lo < seam <= hi for seam in seams) or any(
            abs(seam - lo) < 1e-9 for seam in seams
        )
        key = "straddling" if straddles else "internal"
        counts[key][0] += 1
        counts[key][1] += int((ref_tokens[index], ref_tokens[index + 1]) in present)
    return {
        key: {
            "pairs": value[0],
            "survived": value[1],
            "survival_rate": value[1] / value[0] if value[0] else None,
        }
        for key, value in counts.items()
    }


# ---------------------------------------------------------------- D1


def boundaries_of(spans: list[dict[str, Any]]) -> list[float]:
    """Internal seams only -- the session start and stop are not seams."""
    return sorted({span["start"] for span in spans if span["start"] > 0.0})


def classify(times: list[float], seams: list[float], band: float) -> list[bool]:
    return [any(abs(t - s) <= band for s in seams) for t in times]


def error_profile(
    ref_tokens: list[str], hyp_segments: list[Segment], is_boundary: list[bool]
) -> dict[str, Any]:
    hyp_tokens = _tokenize(" ".join(seg.text for seg in sorted(hyp_segments, key=_segment_order)))
    ops = align(ref_tokens, hyp_tokens)
    counts = {
        True: {"n": 0, "sub": 0, "del": 0, "ins": 0, "match": 0},
        False: {"n": 0, "sub": 0, "del": 0, "ins": 0, "match": 0},
    }
    for flag in is_boundary:
        counts[flag]["n"] += 1
    for kind, ri, _hj in ops:
        if kind == "ins":
            anchor = min(max(ri - 1, 0), len(is_boundary) - 1) if is_boundary else 0
            if is_boundary:
                counts[is_boundary[anchor]]["ins"] += 1
            continue
        counts[is_boundary[ri]][kind] += 1
    out: dict[str, Any] = {}
    for flag, label in ((True, "boundary"), (False, "interior")):
        c = counts[flag]
        errors = c["sub"] + c["del"] + c["ins"]
        out[label] = {
            **c,
            "errors": errors,
            "wer": errors / c["n"] if c["n"] else 0.0,
            "miss_rate": c["del"] / c["n"] if c["n"] else 0.0,
            "sub_rate": c["sub"] / c["n"] if c["n"] else 0.0,
        }
    total_n = counts[True]["n"] + counts[False]["n"]
    total_err = out["boundary"]["errors"] + out["interior"]["errors"]
    out["overall"] = {"n": total_n, "errors": total_err, "wer": total_err / max(1, total_n)}
    return out


def profile_by_own_clock(
    ref_tokens: list[str], hyp_segments: list[Segment], seams: list[float], band: float
) -> dict[str, Any]:
    """Primary D1 view: reference words and errors both timed on the arm's own clock."""
    clock, _ = arm_anchored_clock(ref_tokens, hyp_segments)
    flags = classify(clock, seams, band)
    counts = {
        "boundary": {"n": sum(flags), "sub": 0, "del": 0, "ins": 0},
        "interior": {"n": len(flags) - sum(flags), "sub": 0, "del": 0, "ins": 0},
    }
    for kind, when in error_times(ref_tokens, hyp_segments, clock):
        key = "boundary" if any(abs(when - seam) <= band for seam in seams) else "interior"
        counts[key][kind] += 1
    for key, value in counts.items():
        value["errors"] = value["sub"] + value["del"] + value["ins"]
        value["wer"] = value["errors"] / value["n"] if value["n"] else 0.0
        value["miss_rate"] = value["del"] / value["n"] if value["n"] else 0.0
    return counts


def distance_histogram(
    ref_tokens: list[str], hyp_segments: list[Segment], seams: list[float], step: float = 0.25
) -> dict[str, Any]:
    """Errors and reference words bucketed by distance to the nearest seam."""
    clock, _ = arm_anchored_clock(ref_tokens, hyp_segments)

    def bucket(value: float) -> str:
        if not seams:
            return "no-seam"
        distance = min(abs(value - seam) for seam in seams)
        index = int(distance / step)
        return f"{index * step:.2f}-{(index + 1) * step:.2f}"

    words: dict[str, int] = {}
    errors: dict[str, int] = {}
    for when in clock:
        words[bucket(when)] = words.get(bucket(when), 0) + 1
    for _kind, when in error_times(ref_tokens, hyp_segments, clock):
        errors[bucket(when)] = errors.get(bucket(when), 0) + 1
    return {"words": words, "errors": errors}


def uncovered_intervals(ref: Segment, hyp_segments: list[Segment]) -> list[tuple[float, float]]:
    covered = sorted(
        (max(ref.start, h.start), min(ref.end, h.end))
        for h in hyp_segments
        if min(ref.end, h.end) > max(ref.start, h.start)
    )
    merged: list[list[float]] = []
    for start, end in covered:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    gaps: list[tuple[float, float]] = []
    cursor = ref.start
    for start, end in merged:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < ref.end:
        gaps.append((cursor, ref.end))
    return gaps


def band_split(interval: tuple[float, float], seams: list[float], band: float) -> tuple[float, float]:
    """Seconds of `interval` inside the seam band vs outside it."""
    start, end = interval
    spans = []
    for seam in seams:
        lo, hi = max(start, seam - band), min(end, seam + band)
        if hi > lo:
            spans.append([lo, hi])
    spans.sort()
    merged: list[list[float]] = []
    for lo, hi in spans:
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    inside = sum(hi - lo for lo, hi in merged)
    return inside, max(0.0, (end - start) - inside)


def coverage_profile(
    reference: list[Segment], hyp_segments: list[Segment], seams: list[float], band: float
) -> dict[str, Any]:
    """Decompose the TBSA text_coverage shortfall into seam-band and interior mass.

    text_coverage credits each reference segment's tokens by the fraction of its duration any
    hypothesis segment overlaps, so the shortfall is exactly the token-weighted uncovered
    time -- attributable without a word clock.
    """
    total_tokens = sum(len(_tokenize(seg.text)) for seg in reference)
    loss = {"boundary": 0.0, "interior": 0.0}
    seconds = {"boundary": 0.0, "interior": 0.0}
    for ref in reference:
        tokens = len(_tokenize(ref.text))
        duration = max(ref.end - ref.start, 1e-6)
        for gap in uncovered_intervals(ref, hyp_segments):
            inside, outside = band_split(gap, seams, band)
            seconds["boundary"] += inside
            seconds["interior"] += outside
            loss["boundary"] += tokens * inside / duration
            loss["interior"] += tokens * outside / duration
    return {
        "reference_tokens": total_tokens,
        "coverage_loss_tokens": loss,
        "uncovered_seconds": seconds,
        "coverage_loss_fraction": {
            key: value / max(1, total_tokens) for key, value in loss.items()
        },
    }


# ---------------------------------------------------------------- D2


def seam_cases(
    case: str,
    reference: list[Segment],
    clock: list[float],
    ref_tokens: list[str],
    spans: list[dict[str, Any]],
    live_hyp: list[Segment],
    file_hyp: list[Segment],
    window: float = 0.75,
) -> list[dict[str, Any]]:
    seams = boundaries_of(spans)
    hyp_tokens = _tokenize(" ".join(seg.text for seg in sorted(live_hyp, key=_segment_order)))
    ops = align(ref_tokens, hyp_tokens)
    damage = [0] * len(ref_tokens)
    for kind, ri, _hj in ops:
        if kind in {"sub", "del"}:
            damage[ri] += 1
        elif kind == "ins" and ref_tokens:
            damage[min(max(ri - 1, 0), len(ref_tokens) - 1)] += 1
    rows = []
    for seam in seams:
        idx = [i for i, t in enumerate(clock) if abs(t - seam) <= window]
        if not idx:
            continue
        left = next((s for s in spans if abs(s["end"] - seam) < 1e-6), None)
        right = next((s for s in spans if abs(s["start"] - seam) < 1e-6), None)
        rows.append({
            "case": case,
            "seam_seconds": seam,
            "damaged_words": sum(damage[i] for i in idx),
            "words_in_window": len(idx),
            "reference_window": " ".join(ref_tokens[i] for i in idx),
            "left_span": None if left is None else {
                "span_id": left["span_id"], "range": [left["start"], left["end"]], "text": left["text"],
            },
            "right_span": None if right is None else {
                "span_id": right["span_id"], "range": [right["start"], right["end"]], "text": right["text"],
            },
            "file_window_text": " ".join(
                seg.text for seg in sorted(file_hyp, key=_segment_order)
                if seg.end > seam - window - 1.0 and seg.start < seam + window + 1.0
            ),
        })
    rows.sort(key=lambda row: (-row["damaged_words"], row["seam_seconds"]))
    return rows


# ---------------------------------------------------------------- D3


def span_dose_response(
    reference: list[Segment], clock: list[float], ref_tokens: list[str], spans: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for span in spans:
        idx = [i for i, t in enumerate(clock) if span["start"] <= t < span["end"]]
        local_ref = [ref_tokens[i] for i in idx]
        local_hyp = _tokenize(span["text"])
        if not local_ref:
            continue
        ops = align(local_ref, local_hyp)
        errors = sum(1 for kind, _r, _h in ops if kind != "match")
        rows.append({
            "span_id": span["span_id"],
            "start": span["start"],
            "duration": span["duration"],
            "hard_capped": abs(span["duration"] - 2.5) < 1e-6,
            "ref_words": len(local_ref),
            "hyp_words": len(local_hyp),
            "errors": errors,
            "wer": errors / len(local_ref),
            "empty": span["text"] == "",
        })
    return rows


# ---------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    cli = parser.parse_args()

    document: dict[str, Any] = {
        "schema": "moss-live-gap-boundary-diagnosis.v1",
        "baseline": str(cli.baseline),
        "primary_band_seconds": PRIMARY_BAND,
        "cases": {},
    }

    for case in CASES:
        reference = load_reference(case)
        live_hyp = load_hypothesis(cli.baseline / case / "live-hypothesis.jsonl")
        file_hyp = load_hypothesis(cli.baseline / case / "file-hypothesis.jsonl")
        spans = load_spans(cli.baseline / case / "live" / "run-001" / "trace.jsonl")
        seams = boundaries_of(spans)
        clocks = reference_word_clock(reference, file_hyp)
        ref_tokens = clocks["tokens"]

        entry: dict[str, Any] = {
            "reference_tokens": len(ref_tokens),
            "span_count": len(spans),
            "empty_spans": sum(1 for s in spans if s["text"] == ""),
            "hard_capped_spans": sum(1 for s in spans if abs(s["duration"] - 2.5) < 1e-6),
            "seam_count": len(seams),
            "anchor_rate": clocks["anchor_rate"],
            "tbsa": {
                "live": calculate_tbsa(reference, live_hyp),
                "file": calculate_tbsa(reference, file_hyp),
            },
            "bands": {},
        }
        for band in BANDS:
            slot = entry["bands"].setdefault(f"{band:g}", {})
            for clock_name in ("clock_a", "clock_b"):
                flags = classify(clocks[clock_name], seams, band)
                slot[clock_name] = {
                    "boundary_share_of_words": sum(flags) / max(1, len(flags)),
                    "live": error_profile(ref_tokens, live_hyp, flags),
                    "file": error_profile(ref_tokens, file_hyp, flags),
                }
            slot["clock_own"] = {
                "live": profile_by_own_clock(ref_tokens, live_hyp, seams, band),
                "file": profile_by_own_clock(ref_tokens, file_hyp, seams, band),
            }
            slot["coverage"] = {
                "live": coverage_profile(reference, live_hyp, seams, band),
                "file": coverage_profile(reference, file_hyp, seams, band),
            }
        entry["distance_histogram"] = {
            "live": distance_histogram(ref_tokens, live_hyp, seams),
            "file": distance_histogram(ref_tokens, file_hyp, seams),
        }
        live_clock, _ = arm_anchored_clock(ref_tokens, live_hyp)
        file_clock, _ = arm_anchored_clock(ref_tokens, file_hyp)
        entry["bigram_survival"] = {
            "live": bigram_survival(ref_tokens, live_clock, live_hyp, seams),
            "file": bigram_survival(ref_tokens, file_clock, file_hyp, seams),
            "file_on_live_clock": bigram_survival(ref_tokens, live_clock, file_hyp, seams),
        }
        entry["seam_cases"] = seam_cases(
            case, reference, live_clock, ref_tokens, spans, live_hyp, file_hyp
        )
        entry["spans"] = span_dose_response(reference, live_clock, ref_tokens, spans)
        entry["span_duration_histogram"] = {
            label: sum(1 for s in spans if label == (
                "<=1.0s" if s["duration"] <= 1.0
                else "1.0-1.8s" if s["duration"] <= 1.8
                else "1.8-2.49s" if s["duration"] < 2.5 else "2.5s(cap)"))
            for label in ("<=1.0s", "1.0-1.8s", "1.8-2.49s", "2.5s(cap)")
        }
        document["cases"][case] = entry

    # ---- aggregate D1 over the primary trio
    key = f"{PRIMARY_BAND:g}"
    agg: dict[str, Any] = {}

    own: dict[str, Any] = {}
    for arm in ("live", "file"):
        totals = {cls: {"n": 0, "sub": 0, "del": 0, "ins": 0, "errors": 0} for cls in ("boundary", "interior")}
        for case in CASES:
            band = document["cases"][case]["bands"][key]["clock_own"][arm]
            for cls in ("boundary", "interior"):
                for field in ("n", "sub", "del", "ins", "errors"):
                    totals[cls][field] += band[cls][field]
        own[arm] = {
            cls: {
                **totals[cls],
                "wer": totals[cls]["errors"] / max(1, totals[cls]["n"]),
                "miss_rate": totals[cls]["del"] / max(1, totals[cls]["n"]),
            }
            for cls in ("boundary", "interior")
        }
    gap_b = own["live"]["boundary"]["errors"] - own["file"]["boundary"]["errors"]
    gap_i = own["live"]["interior"]["errors"] - own["file"]["interior"]["errors"]
    own["gap_words"] = {
        "boundary": gap_b,
        "interior": gap_i,
        "total": gap_b + gap_i,
        "boundary_share": gap_b / (gap_b + gap_i) if (gap_b + gap_i) else 0.0,
    }
    own["word_share_boundary"] = own["live"]["boundary"]["n"] / max(
        1, own["live"]["boundary"]["n"] + own["live"]["interior"]["n"]
    )
    own["error_density_ratio"] = {
        arm: (
            own[arm]["boundary"]["wer"] / own[arm]["interior"]["wer"]
            if own[arm]["interior"]["wer"] else None
        )
        for arm in ("live", "file")
    }
    agg["clock_own"] = own

    hist: dict[str, dict[str, dict[str, int]]] = {"live": {"words": {}, "errors": {}}, "file": {"words": {}, "errors": {}}}
    for case in CASES:
        for arm in ("live", "file"):
            for field in ("words", "errors"):
                for bucket, value in document["cases"][case]["distance_histogram"][arm][field].items():
                    hist[arm][field][bucket] = hist[arm][field].get(bucket, 0) + value
    agg["distance_histogram"] = {
        arm: {
            bucket: {
                "words": hist[arm]["words"].get(bucket, 0),
                "errors": hist[arm]["errors"].get(bucket, 0),
                "wer": hist[arm]["errors"].get(bucket, 0) / max(1, hist[arm]["words"].get(bucket, 0)),
            }
            for bucket in sorted(set(hist[arm]["words"]) | set(hist[arm]["errors"]))
        }
        for arm in ("live", "file")
    }

    bigrams: dict[str, Any] = {}
    for view in ("live", "file", "file_on_live_clock"):
        totals = {cls: [0, 0] for cls in ("straddling", "internal")}
        for case in CASES:
            row = document["cases"][case]["bigram_survival"][view]
            for cls in ("straddling", "internal"):
                totals[cls][0] += row[cls]["pairs"]
                totals[cls][1] += row[cls]["survived"]
        bigrams[view] = {
            cls: {
                "pairs": totals[cls][0],
                "survived": totals[cls][1],
                "survival_rate": totals[cls][1] / max(1, totals[cls][0]),
            }
            for cls in ("straddling", "internal")
        }
    agg["bigram_survival"] = bigrams

    for clock_name in ("clock_a", "clock_b"):
        totals = {
            arm: {cls: {"n": 0, "errors": 0, "del": 0, "sub": 0, "ins": 0} for cls in ("boundary", "interior")}
            for arm in ("live", "file")
        }
        for case in CASES:
            band = document["cases"][case]["bands"][key][clock_name]
            for arm in ("live", "file"):
                for cls in ("boundary", "interior"):
                    for field in ("n", "errors", "del", "sub", "ins"):
                        totals[arm][cls][field] += band[arm][cls][field]
        summary: dict[str, Any] = {}
        for arm in ("live", "file"):
            summary[arm] = {
                cls: {
                    **totals[arm][cls],
                    "wer": totals[arm][cls]["errors"] / max(1, totals[arm][cls]["n"]),
                    "miss_rate": totals[arm][cls]["del"] / max(1, totals[arm][cls]["n"]),
                }
                for cls in ("boundary", "interior")
            }
        gap_boundary = totals["live"]["boundary"]["errors"] - totals["file"]["boundary"]["errors"]
        gap_interior = totals["live"]["interior"]["errors"] - totals["file"]["interior"]["errors"]
        total_gap = gap_boundary + gap_interior
        summary["gap_words"] = {
            "boundary": gap_boundary,
            "interior": gap_interior,
            "total": total_gap,
            "boundary_share": gap_boundary / total_gap if total_gap else 0.0,
        }
        summary["word_share"] = {
            "boundary": totals["live"]["boundary"]["n"] / max(1, totals["live"]["boundary"]["n"] + totals["live"]["interior"]["n"]),
        }
        agg[clock_name] = summary

    cov_totals = {
        arm: {"boundary": 0.0, "interior": 0.0, "tokens": 0}
        for arm in ("live", "file")
    }
    for case in CASES:
        cov = document["cases"][case]["bands"][key]["coverage"]
        for arm in ("live", "file"):
            cov_totals[arm]["boundary"] += cov[arm]["coverage_loss_tokens"]["boundary"]
            cov_totals[arm]["interior"] += cov[arm]["coverage_loss_tokens"]["interior"]
            cov_totals[arm]["tokens"] += cov[arm]["reference_tokens"]
    cov_gap_b = cov_totals["live"]["boundary"] - cov_totals["file"]["boundary"]
    cov_gap_i = cov_totals["live"]["interior"] - cov_totals["file"]["interior"]
    agg["coverage"] = {
        "totals": cov_totals,
        "gap_tokens": {"boundary": cov_gap_b, "interior": cov_gap_i, "total": cov_gap_b + cov_gap_i},
        "boundary_share": cov_gap_b / (cov_gap_b + cov_gap_i) if (cov_gap_b + cov_gap_i) else 0.0,
    }

    all_spans = [row for case in CASES for row in document["cases"][case]["spans"]]
    capped = [row for row in all_spans if row["hard_capped"]]
    short = [row for row in all_spans if not row["hard_capped"]]
    def pooled(rows: list[dict[str, Any]]) -> dict[str, Any]:
        words = sum(row["ref_words"] for row in rows)
        errors = sum(row["errors"] for row in rows)
        return {
            "spans": len(rows),
            "ref_words": words,
            "errors": errors,
            "pooled_wer": errors / max(1, words),
            "mean_span_wer": statistics.fmean([row["wer"] for row in rows]) if rows else None,
            "median_duration": statistics.median([row["duration"] for row in rows]) if rows else None,
            "empty_spans": sum(1 for row in rows if row["empty"]),
        }
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in all_spans:
        d = row["duration"]
        label = "<=1.0s" if d <= 1.0 else "1.0-1.8s" if d <= 1.8 else "1.8-2.49s" if d < 2.5 else "2.5s(cap)"
        buckets.setdefault(label, []).append(row)
    document["aggregate"] = {
        "d1": agg,
        "d3": {
            "hard_capped": pooled(capped),
            "shorter": pooled(short),
            "buckets": {label: pooled(rows) for label, rows in sorted(buckets.items())},
            "javier_only": {
                "hard_capped": pooled([r for r in document["cases"]["lex_javier_milei"]["spans"] if r["hard_capped"]]),
                "shorter": pooled([r for r in document["cases"]["lex_javier_milei"]["spans"] if not r["hard_capped"]]),
            },
        },
        "d2_top_seams": sorted(
            [row for case in CASES for row in document["cases"][case]["seam_cases"]],
            key=lambda row: -row["damaged_words"],
        )[:12],
    }

    cli.output.parent.mkdir(parents=True, exist_ok=True)
    cli.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(document["aggregate"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
