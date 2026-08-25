"""Evaluator v2 (plan A0.3): lexical-first scoring for the live-convergence campaign.

Why this exists (plan §3.4): the deployed TBSA formula credits *time overlap*, not words.
A single 60-second segment whose only word is "xx" scores text coverage 1.0 and mean TBSA
.6817 against the trio -- so an arm that merely widens its timestamps looks better without
transcribing anything better.  Every quality axis here is decided by comparing words to
words; the time-extent metrics are reported beside, never instead.

The six required reports (plan A0.3):

  wer                    WER with substitution / deletion / insertion counts
  content_recall         LCS(reference, hypothesis) / reference words
  seam_profile           WER split by distance to the hypothesis span grid's seams
  matched_word_speaker   lexically aligned matched-word speaker accuracy
  der_reference_speech   DER scored only inside real reference speech regions
  legacy                 the current TBSA / diarization numbers, unchanged, beside

This module is scoring only: no corpus layout, no CLI.  `compare_evaluators.py` drives it.
"""

from __future__ import annotations

import math
import sys
import wave
from pathlib import Path
from typing import Any, Sequence

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.evaluation import (  # noqa: E402
    Segment,
    _maximum_weight_assignment,
    _round_metric,
    _segment_order,
    _tokenize,
    calculate_diarization,
    calculate_tbsa,
)

#: Deployed live VAD instrument -- webrtcvad mode 1 over 10 ms frames at 16 kHz.
#: Same settings as `prototypes/live-file-gap-emptyspan/common.py:vad_speech_ratio`, so the
#: speech regions this evaluator scores inside are the ones the live endpoint itself sees.
#: No smoothing, no padding: an added knob would be an added way to move the number.
SAMPLE_RATE = 16_000
VAD_MODE = 1
VAD_FRAME_SAMPLES = 160

#: Band around a seam, in seconds, that counts as "at the seam".  Not a new threshold: it is
#: the primary band of the measured boundary-vs-interior split
#: (`prototypes/live-file-gap-context/diag_boundary_vs_interior.py:PRIMARY_BAND`).
DEFAULT_SEAM_BAND_SEC = 0.40

#: Interpolation slope, in seconds per word, used only to extrapolate reference words that
#: fall outside every alignment anchor.  Same value as the measured diagnostic.
EXTRAPOLATION_SEC_PER_WORD = 0.30

Interval = tuple[float, float]


# ----------------------------------------------------------------- word rows and alignment


def segment_word_times(segments: Sequence[Segment]) -> list[tuple[str, str, float]]:
    """Words of `segments` in scoring order as (token, speaker, char-proportional time)."""
    rows: list[tuple[str, str, float]] = []
    for segment in sorted(segments, key=_segment_order):
        tokens = _tokenize(segment.text)
        if not tokens:
            continue
        total_chars = sum(len(token) for token in tokens)
        duration = max(segment.end - segment.start, 1e-6)
        cursor = 0
        for token in tokens:
            centre = cursor + len(token) / 2.0
            rows.append((token, segment.speaker, segment.start + duration * (centre / total_chars)))
            cursor += len(token)
    return rows


def align(reference: Sequence[str], hypothesis: Sequence[str]) -> list[tuple[str, int, int]]:
    """Levenshtein backtrace as ops `(kind, reference_index, hypothesis_index)`.

    `kind` is one of match / sub / del / ins.  For `del` the hypothesis index is -1; for
    `ins` the reference index is the position the insertion sits before.
    """
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
        if (
            i > 0
            and j > 0
            and dp[i][j] == dp[i - 1][j - 1] + (reference[i - 1] != hypothesis[j - 1])
        ):
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


def longest_common_subsequence(reference: Sequence[str], hypothesis: Sequence[str]) -> int:
    previous = [0] * (len(hypothesis) + 1)
    for ref_token in reference:
        current = [0]
        for index, hyp_token in enumerate(hypothesis, start=1):
            current.append(
                previous[index - 1] + 1
                if ref_token == hyp_token
                else max(previous[index], current[-1])
            )
        previous = current
    return previous[-1]


def reference_word_clock(
    ops: Sequence[tuple[str, int, int]],
    reference_count: int,
    hypothesis_times: Sequence[float],
) -> list[float]:
    """Time every reference word on the *arm's own* clock.

    A matched or substituted reference word is timed by the hypothesis word that consumed
    it, whose timestamp comes straight off the decoder.  A deleted reference word has no
    hypothesis word, so it is interpolated between its surviving neighbours -- which places
    words swallowed by an empty or truncated span across exactly the interval that swallowed
    them, the property the seam profile depends on.
    """
    anchors: dict[int, float] = {}
    for kind, ref_index, hyp_index in ops:
        if kind in {"match", "sub"} and 0 <= ref_index < reference_count:
            anchors[ref_index] = hypothesis_times[hyp_index]
    keys = sorted(anchors)
    clock: list[float] = []
    for index in range(reference_count):
        if index in anchors:
            clock.append(anchors[index])
            continue
        before = [key for key in keys if key < index]
        after = [key for key in keys if key > index]
        if before and after:
            low, high = before[-1], after[0]
            span = anchors[high] - anchors[low]
            clock.append(anchors[low] + (index - low) / (high - low) * span)
        elif before:
            low = before[-1]
            clock.append(anchors[low] + (index - low) * EXTRAPOLATION_SEC_PER_WORD)
        elif after:
            high = after[0]
            clock.append(max(0.0, anchors[high] - (high - index) * EXTRAPOLATION_SEC_PER_WORD))
        else:
            clock.append(0.0)
    for index in range(1, len(clock)):
        clock[index] = max(clock[index], clock[index - 1])
    return clock


def seam_times(segments: Sequence[Segment]) -> list[float]:
    """Interior boundaries of the hypothesis span grid.

    Every start and end except the outermost two: a gap between spans contributes both of
    its edges, because words can be lost on either side of it.
    """
    ordered = sorted(segments, key=_segment_order)
    if len(ordered) < 2:
        return []
    edges: set[float] = set()
    first_start = ordered[0].start
    last_end = max(segment.end for segment in ordered)
    for segment in ordered:
        for edge in (segment.start, segment.end):
            if edge > first_start and edge < last_end:
                edges.add(round(edge, 6))
    return sorted(edges)


# ----------------------------------------------------------------- speech regions


def speech_regions_from_wav(path: str | Path) -> tuple[Interval, ...]:
    """Union of voiced 10 ms frames under the deployed live VAD settings."""
    import webrtcvad

    with wave.open(str(path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise ValueError(f"{path}: speech regions need mono 16-bit PCM")
        if handle.getframerate() != SAMPLE_RATE:
            raise ValueError(f"{path}: speech regions need {SAMPLE_RATE} Hz audio")
        pcm = handle.readframes(handle.getnframes())

    vad = webrtcvad.Vad(VAD_MODE)
    frame_bytes = VAD_FRAME_SAMPLES * 2
    frame_seconds = VAD_FRAME_SAMPLES / float(SAMPLE_RATE)
    regions: list[list[float]] = []
    for index in range(len(pcm) // frame_bytes):
        frame = pcm[index * frame_bytes : (index + 1) * frame_bytes]
        if not vad.is_speech(frame, SAMPLE_RATE):
            continue
        start = index * frame_seconds
        end = start + frame_seconds
        if regions and math.isclose(regions[-1][1], start, rel_tol=0.0, abs_tol=1e-9):
            regions[-1][1] = end
        else:
            regions.append([start, end])
    return tuple((start, end) for start, end in regions)


def segments_to_intervals(segments: Sequence[Segment]) -> tuple[Interval, ...]:
    return union_intervals((segment.start, segment.end) for segment in segments)


def union_intervals(intervals) -> tuple[Interval, ...]:
    ordered = sorted((start, end) for start, end in intervals if end > start)
    if not ordered:
        return ()
    merged: list[list[float]] = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return tuple((start, end) for start, end in merged)


def intersect_intervals(left: Sequence[Interval], right: Sequence[Interval]) -> tuple[Interval, ...]:
    out: list[Interval] = []
    i = j = 0
    while i < len(left) and j < len(right):
        start = max(left[i][0], right[j][0])
        end = min(left[i][1], right[j][1])
        if end > start:
            out.append((start, end))
        if left[i][1] <= right[j][1]:
            i += 1
        else:
            j += 1
    return tuple(out)


def total_seconds(intervals: Sequence[Interval]) -> float:
    return sum(end - start for start, end in intervals)


# ----------------------------------------------------------------- the axes


def _wer_axis(ops: Sequence[tuple[str, int, int]], reference_words: int, hypothesis_words: int):
    counts = {"match": 0, "sub": 0, "del": 0, "ins": 0}
    for kind, _ref_index, _hyp_index in ops:
        counts[kind] += 1
    errors = counts["sub"] + counts["del"] + counts["ins"]
    return {
        "wer": _round_metric(errors / reference_words) if reference_words else 0.0,
        "errors": errors,
        "substitutions": counts["sub"],
        "deletions": counts["del"],
        "insertions": counts["ins"],
        "matched_words": counts["match"],
        "reference_words": reference_words,
        "hypothesis_words": hypothesis_words,
    }


def _seam_axis(
    ops: Sequence[tuple[str, int, int]],
    clock: Sequence[float],
    hypothesis_times: Sequence[float],
    seams: Sequence[float],
    band: float,
) -> dict[str, Any]:
    def at_seam(time: float) -> bool:
        return any(abs(time - seam) <= band for seam in seams)

    classes = {
        "boundary": {"reference_words": 0, "sub": 0, "del": 0, "ins": 0},
        "interior": {"reference_words": 0, "sub": 0, "del": 0, "ins": 0},
    }
    for index, time in enumerate(clock):
        classes["boundary" if at_seam(time) else "interior"]["reference_words"] += 1
    for kind, ref_index, hyp_index in ops:
        if kind == "match":
            continue
        if kind == "del":
            bucket = "boundary" if at_seam(clock[ref_index]) else "interior"
        else:
            bucket = "boundary" if at_seam(hypothesis_times[hyp_index]) else "interior"
        classes[bucket][kind] += 1

    out: dict[str, Any] = {"band_seconds": band, "seams": len(seams)}
    for name, row in classes.items():
        errors = row["sub"] + row["del"] + row["ins"]
        out[name] = {
            **row,
            "errors": errors,
            "wer": _round_metric(errors / row["reference_words"]) if row["reference_words"] else 0.0,
        }
    out["boundary_reference_share"] = _round_metric(
        classes["boundary"]["reference_words"] / max(1, len(clock))
    )
    return out


def _matched_word_speaker_axis(
    ops: Sequence[tuple[str, int, int]],
    reference_speakers: Sequence[str],
    hypothesis_speakers: Sequence[str],
    reference_words: int,
) -> dict[str, Any]:
    ref_labels = sorted(set(reference_speakers))
    hyp_labels = sorted(set(hypothesis_speakers))
    weights = {(ref, hyp): 0.0 for ref in ref_labels for hyp in hyp_labels}
    matched_pairs: list[tuple[str, str]] = []
    for kind, ref_index, hyp_index in ops:
        if kind != "match":
            continue
        pair = (reference_speakers[ref_index], hypothesis_speakers[hyp_index])
        matched_pairs.append(pair)
        weights[pair] += 1.0
    mapping, credited = _maximum_weight_assignment(ref_labels, hyp_labels, weights)
    matched = len(matched_pairs)
    per_speaker_reference = {
        label: sum(1 for speaker in reference_speakers if speaker == label) for label in ref_labels
    }
    per_speaker_credit = {label: 0 for label in ref_labels}
    for ref_label, hyp_label in matched_pairs:
        if mapping.get(ref_label) == hyp_label:
            per_speaker_credit[ref_label] += 1
    return {
        # Denominator is every reference word: a word the arm never recovered earns no
        # speaker credit, which is what makes this axis unreachable by widening timestamps.
        "matched_word_speaker_accuracy": _round_metric(credited / reference_words)
        if reference_words
        else 0.0,
        "speaker_precision_on_matched": _round_metric(credited / matched) if matched else 0.0,
        "credited_words": int(credited),
        "matched_words": matched,
        "reference_words": reference_words,
        "speaker_mapping": mapping,
        "speaker_correctness": {
            label: _round_metric(per_speaker_credit[label] / per_speaker_reference[label])
            if per_speaker_reference[label]
            else 0.0
            for label in ref_labels
        },
    }


def _der_reference_speech_axis(
    reference: Sequence[Segment],
    hypothesis: Sequence[Segment],
    speech_regions: Sequence[Interval],
) -> dict[str, Any]:
    """DER scored only where the reference audio actually contains speech.

    The corpus references are gapless turn intervals, so the deployed DER charges an arm for
    every pause inside a turn and rewards it for covering them.  Restricting the scored
    region to real speech removes that; what remains -- miss, false alarm, confusion -- is
    measured on time an arm could actually have transcribed.
    """
    ref_labels = sorted({segment.speaker for segment in reference})
    hyp_labels = sorted({segment.speaker for segment in hypothesis})
    ref_speech = {
        label: intersect_intervals(
            segments_to_intervals([s for s in reference if s.speaker == label]), speech_regions
        )
        for label in ref_labels
    }
    hyp_speech = {
        label: intersect_intervals(
            segments_to_intervals([s for s in hypothesis if s.speaker == label]), speech_regions
        )
        for label in hyp_labels
    }
    weights = {
        (ref, hyp): total_seconds(intersect_intervals(ref_speech[ref], hyp_speech[hyp]))
        for ref in ref_labels
        for hyp in hyp_labels
    }
    mapping, _matched = _maximum_weight_assignment(ref_labels, hyp_labels, weights)

    hypothesis_all = intersect_intervals(segments_to_intervals(hypothesis), speech_regions)
    reference_all = union_intervals(
        interval for label in ref_labels for interval in ref_speech[label]
    )
    scored = total_seconds(reference_all)
    covered = 0.0
    correct = 0.0
    for label in ref_labels:
        covered += total_seconds(intersect_intervals(ref_speech[label], hypothesis_all))
        mapped = mapping.get(label)
        if mapped in hyp_speech:
            correct += total_seconds(intersect_intervals(ref_speech[label], hyp_speech[mapped]))
    miss = max(scored - covered, 0.0)
    confusion = max(covered - correct, 0.0)
    false_alarm = max(total_seconds(hypothesis_all) - total_seconds(
        intersect_intervals(hypothesis_all, reference_all)
    ), 0.0)
    der = (miss + confusion + false_alarm) / scored if scored > 0 else 0.0
    return {
        "der": _round_metric(der),
        "miss": _round_metric(miss / scored) if scored else 0.0,
        "false_alarm": _round_metric(false_alarm / scored) if scored else 0.0,
        "speaker_confusion": _round_metric(confusion / scored) if scored else 0.0,
        "scored_speech_seconds": round(scored, 3),
        "speech_region_seconds": round(total_seconds(speech_regions), 3),
        "speech_regions": len(speech_regions),
        "speaker_mapping": mapping,
    }


def score_v2(
    reference: Sequence[Segment],
    hypothesis: Sequence[Segment],
    *,
    speech_regions: Sequence[Interval] | None = None,
    speech_regions_source: str = "reference_intervals",
    seam_band_sec: float = DEFAULT_SEAM_BAND_SEC,
) -> dict[str, Any]:
    """Score one hypothesis against one reference on every plan A0.3 axis."""
    if not reference:
        raise ValueError("reference must contain at least one segment")
    ref_rows = segment_word_times(reference)
    hyp_rows = segment_word_times(hypothesis)
    ref_tokens = [row[0] for row in ref_rows]
    hyp_tokens = [row[0] for row in hyp_rows]
    if not ref_tokens:
        raise ValueError("reference must contain at least one word")
    hyp_times = [row[2] for row in hyp_rows]

    ops = align(ref_tokens, hyp_tokens)
    clock = reference_word_clock(ops, len(ref_tokens), hyp_times)
    regions = tuple(speech_regions) if speech_regions is not None else segments_to_intervals(reference)

    wer = _wer_axis(ops, len(ref_tokens), len(hyp_tokens))
    seam = _seam_axis(ops, clock, hyp_times, seam_times(hypothesis), seam_band_sec)
    # The seam profile is a *partition* of the same WER, not a second opinion about it: every
    # reference word and every error lands in exactly one class.  Splitting a span moves the
    # partition (that is what it describes) but must never change these totals.
    if (
        seam["boundary"]["reference_words"] + seam["interior"]["reference_words"]
        != wer["reference_words"]
        or seam["boundary"]["errors"] + seam["interior"]["errors"] != wer["errors"]
    ):
        raise AssertionError("seam profile does not partition the WER it decomposes")
    speaker = _matched_word_speaker_axis(
        ops, [row[1] for row in ref_rows], [row[1] for row in hyp_rows], len(ref_tokens)
    )
    recovered = longest_common_subsequence(ref_tokens, hyp_tokens)
    hypothesis_seconds = sum(segment.end - segment.start for segment in hypothesis)
    return {
        "wer": wer,
        "content_recall": _round_metric(recovered / len(ref_tokens)),
        "recovered_words": recovered,
        "seam_profile": seam,
        "matched_word_speaker": speaker,
        "der_reference_speech": {
            **_der_reference_speech_axis(reference, hypothesis, regions),
            "speech_regions_source": speech_regions_source,
        },
        "extent": {
            "hypothesis_segments": len(hypothesis),
            "hypothesis_seconds": round(hypothesis_seconds, 3),
            "mean_segment_seconds": round(hypothesis_seconds / max(1, len(hypothesis)), 3),
        },
        "legacy": {
            "tbsa": calculate_tbsa(list(reference), list(hypothesis)),
            "diarization": calculate_diarization(list(reference), list(hypothesis)),
        },
    }
