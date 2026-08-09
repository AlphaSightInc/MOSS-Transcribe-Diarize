#!/usr/bin/env python3
"""Classify S06R lane-state time against the supervisor's card windows."""

from __future__ import annotations

import argparse
import json
import math
import sys
import wave
from array import array
from pathlib import Path

from capture_harness import atomic_json, read_json, sha256, utc_now
from post_session import seal_tree


def samples(path: Path) -> tuple[int, array]:
    with wave.open(str(path), "rb") as reader:
        rate = reader.getframerate()
        values = array("h", reader.readframes(reader.getnframes()))
    if sys.byteorder != "little":
        values.byteswap()
    return rate, values


def levels(path: Path) -> dict:
    rate, values = samples(path)
    peak = max((abs(value) for value in values), default=0)
    rms = math.sqrt(sum(value * value for value in values) / len(values)) if values else 0.0
    db = lambda value: -120.0 if value <= 0 else 20.0 * math.log10(value / 32768.0)
    return {
        "duration_seconds": len(values) / rate,
        "peak_dbfs": round(db(peak), 6),
        "rms_dbfs": round(db(rms), 6),
        "sha256": sha256(path),
    }


def zero_runs(path: Path, minimum_seconds: float) -> list[list[float]]:
    rate, values = samples(path)
    result = []
    start = None
    for index, value in enumerate(values):
        if value == 0 and start is None:
            start = index
        elif value != 0 and start is not None:
            if index - start >= minimum_seconds * rate:
                result.append([start / rate, index / rate])
            start = None
    if start is not None and len(values) - start >= minimum_seconds * rate:
        result.append([start / rate, len(values) / rate])
    return result


def grouped_mic_activity(segments: list[dict], cutoff: float, max_gap: float = 5.0) -> list[list[float]]:
    selected = [item for item in segments if float(item["start"]) < cutoff]
    groups: list[list[float]] = []
    for item in selected:
        start, end = float(item["start"]), float(item["end"])
        if not groups or start - groups[-1][1] > max_gap:
            groups.append([start, end])
        else:
            groups[-1][1] = max(groups[-1][1], end)
    return groups


def active(intervals: list[list[float]], point: float) -> bool:
    return any(start <= point < end for start, end in intervals)


def complement(inactive: list[list[float]], start: float, end: float) -> list[list[float]]:
    cursor = start
    result = []
    for left, right in inactive:
        left, right = max(start, left), min(end, right)
        if right <= start or left >= end:
            continue
        if left > cursor:
            result.append([cursor, left])
        cursor = max(cursor, right)
    if cursor < end:
        result.append([cursor, end])
    return result


def partition(system: list[list[float]], mic: list[list[float]], start: float, end: float) -> list[dict]:
    points = {start, end}
    for intervals in (system, mic):
        for left, right in intervals:
            if start < left < end:
                points.add(left)
            if start < right < end:
                points.add(right)
    ordered = sorted(points)
    pieces = []
    for left, right in zip(ordered, ordered[1:]):
        midpoint = (left + right) / 2.0
        s, m = active(system, midpoint), active(mic, midpoint)
        state = "both" if s and m else "recording_only" if s else "live_only" if m else "neither"
        if pieces and pieces[-1]["type"] == state:
            pieces[-1]["end"] = right
            pieces[-1]["duration_seconds"] = round(right - pieces[-1]["start"], 6)
        else:
            pieces.append({"start": left, "end": right, "duration_seconds": round(right - left, 6), "type": state})
    return pieces


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir", type=Path)
    args = parser.parse_args()
    root = args.session_dir.resolve()
    transcripts = {
        lane: read_json(root / "derived/asr" / lane / "asr-transcript.json")["segments"]
        for lane in ("system", "microphone", "mixed")
    }
    card_t0 = float(transcripts["microphone"][0]["start"])
    card_cutoff = card_t0 + 150.0
    mic_intervals = grouped_mic_activity(transcripts["microphone"], card_cutoff)
    closing_end = mic_intervals[-1][1]
    system_zero = zero_runs(root / "audio/system.wav", 0.25)
    system_intervals = complement(system_zero, card_t0, closing_end)
    windows = [
        ("initial", 0.0, 20.0),
        ("recording_only_planned", 20.0, 55.0),
        ("live_only_planned", 55.0, 85.0),
        ("both_planned", 85.0, 125.0),
        ("closing", 125.0, closing_end - card_t0),
    ]
    table = []
    all_pieces = partition(system_intervals, mic_intervals, card_t0, closing_end)
    totals = {name: 0.0 for name in ("recording_only", "live_only", "both", "neither")}
    longest = dict(totals)
    for piece in all_pieces:
        totals[piece["type"]] += piece["duration_seconds"]
        longest[piece["type"]] = max(longest[piece["type"]], piece["duration_seconds"])
    for name, relative_start, relative_end in windows:
        absolute_start, absolute_end = card_t0 + relative_start, card_t0 + relative_end
        pieces = partition(system_intervals, mic_intervals, absolute_start, absolute_end)
        durations = {kind: 0.0 for kind in totals}
        for piece in pieces:
            durations[piece["type"]] += piece["duration_seconds"]
            piece["card_relative_start"] = round(piece["start"] - card_t0, 6)
            piece["card_relative_end"] = round(piece["end"] - card_t0, 6)
        dominant = max(durations, key=durations.get)
        table.append(
            {
                "window": name,
                "card_relative_seconds": [relative_start, round(relative_end, 6)],
                "dominant_type": dominant,
                "type_durations_seconds": {key: round(value, 6) for key, value in durations.items()},
                "pieces": pieces,
            }
        )
    required = ("recording_only", "live_only", "both")
    passes = all(totals[kind] >= 15.0 for kind in required)
    output = root / "derived/s06r-verdict"
    output.mkdir(parents=True, exist_ok=False)
    verdict = {
        "schema": "moss-dl2-s06r-timeline-verdict.v1",
        "session_id": read_json(root / "session-manifest.json")["session_id"],
        "evaluated_at_utc": utc_now(),
        "card_t0_tape_seconds": card_t0,
        "card_t0_basis": "first microphone ASR cue: S zero six R cross lane counter example",
        "activity_method": {
            "system": "playback-active except contiguous exact-zero PCM runs of at least 0.25s",
            "microphone": "ASR speech segments grouped across gaps no greater than 5s; isolated post-card segment excluded by 150s cutoff",
            "duration_gate_accounting": "cumulative duration within the card; longest contiguous duration also reported",
        },
        "system_exact_zero_runs_tape_seconds": system_zero,
        "microphone_activity_groups_tape_seconds": mic_intervals,
        "window_table": table,
        "type_totals_seconds": {key: round(value, 6) for key, value in totals.items()},
        "longest_contiguous_seconds": {key: round(value, 6) for key, value in longest.items()},
        "gate": {
            "minimum_seconds_each": 15.0,
            "required_types": list(required),
            "contiguity_required": False,
            "passes": passes,
        },
        "per_lane": {
            lane: {
                "segment_count": len(transcripts[lane]),
                "speaker_labels": sorted({item.get("speaker") for item in transcripts[lane]}),
                "levels": levels(root / "audio" / (lane + ".wav")),
                "transcript_sha256": sha256(root / "derived/asr" / lane / "asr-transcript.json"),
            }
            for lane in ("system", "microphone", "mixed")
        },
        "microphone_post_card_note": "one isolated S02 segment at 220.451-220.901s is outside the card cutoff and is not counted as live activity",
        "verdict": "USABLE_AS_IS" if passes else "RETAKE_REQUIRED",
    }
    atomic_json(output / "S06R_TIMELINE_VERDICT.json", verdict)
    seal_tree(output, output / "S06R_VERDICT_EVIDENCE.sha256")
    manifest_path = root / "session-manifest.json"
    manifest = read_json(manifest_path)
    manifest["s06r_verdict"] = {
        "verdict": verdict["verdict"],
        "path": "derived/s06r-verdict/S06R_TIMELINE_VERDICT.json",
        "sha256": sha256(output / "S06R_TIMELINE_VERDICT.json"),
        "seal_path": "derived/s06r-verdict/S06R_VERDICT_EVIDENCE.sha256",
        "seal_sha256": sha256(output / "S06R_VERDICT_EVIDENCE.sha256"),
    }
    atomic_json(manifest_path, manifest)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0 if passes else 2


if __name__ == "__main__":
    raise SystemExit(main())
