#!/usr/bin/env python3
"""Classify recovered S05 card content and trailing dead air."""

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
    return {"duration_seconds": len(values) / rate, "peak_dbfs": round(db(peak), 6), "rms_dbfs": round(db(rms), 6), "sha256": sha256(path)}


def zero_runs(path: Path, minimum_seconds: float) -> list[list[float]]:
    rate, values = samples(path)
    result, start = [], None
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


def groups(segments: list[dict], start: float, end: float, max_gap: float = 5.0) -> list[list[float]]:
    selected = [item for item in segments if float(item["end"]) > start and float(item["start"]) < end]
    output: list[list[float]] = []
    for item in selected:
        left, right = max(start, float(item["start"])), min(end, float(item["end"]))
        if not output or left - output[-1][1] > max_gap:
            output.append([left, right])
        else:
            output[-1][1] = max(output[-1][1], right)
    return output


def complement(inactive: list[list[float]], start: float, end: float) -> list[list[float]]:
    cursor, output = start, []
    for left, right in inactive:
        left, right = max(start, left), min(end, right)
        if right <= start or left >= end:
            continue
        if left > cursor:
            output.append([cursor, left])
        cursor = max(cursor, right)
    if cursor < end:
        output.append([cursor, end])
    return output


def active(intervals: list[list[float]], point: float) -> bool:
    return any(left <= point < right for left, right in intervals)


def partition(system: list[list[float]], mic: list[list[float]], start: float, end: float) -> list[dict]:
    points = {start, end}
    for intervals in (system, mic):
        for left, right in intervals:
            if start < left < end:
                points.add(left)
            if start < right < end:
                points.add(right)
    output = []
    ordered = sorted(points)
    for left, right in zip(ordered, ordered[1:]):
        middle = (left + right) / 2.0
        s, m = active(system, middle), active(mic, middle)
        state = "both" if s and m else "remote_only" if s else "solo" if m else "neither"
        if output and output[-1]["type"] == state:
            output[-1]["end"] = right
            output[-1]["duration_seconds"] = round(right - output[-1]["start"], 6)
        else:
            output.append({"start": left, "end": right, "duration_seconds": round(right - left, 6), "type": state})
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir", type=Path)
    args = parser.parse_args()
    root = args.session_dir.resolve()
    manifest_path = root / "session-manifest.json"
    manifest = read_json(manifest_path)
    transcripts = {lane: read_json(root / "derived/asr" / lane / "asr-transcript.json")["segments"] for lane in ("system", "microphone", "mixed")}
    card_t0 = float(transcripts["microphone"][0]["start"])
    closing_end = max(float(item["end"]) for item in transcripts["microphone"])
    mic = groups(transcripts["microphone"], card_t0, closing_end)
    system_zero = zero_runs(root / "audio/system.wav", 0.25)
    system = complement(system_zero, card_t0, closing_end)
    schedule = [
        ("solo_planned", 0.0, 45.0, "solo"),
        ("remote_only_planned", 45.0, 90.0, "remote_only"),
        ("overlap_30_plus_20_planned", 90.0, 140.0, "both"),
        ("closing", 140.0, closing_end - card_t0, None),
    ]
    all_pieces = partition(system, mic, card_t0, closing_end)
    types = ("solo", "remote_only", "both", "neither")
    totals = {kind: 0.0 for kind in types}
    longest = dict(totals)
    for piece in all_pieces:
        totals[piece["type"]] += piece["duration_seconds"]
        longest[piece["type"]] = max(longest[piece["type"]], piece["duration_seconds"])
    table = []
    for name, relative_start, relative_end, expected in schedule:
        left, right = card_t0 + relative_start, card_t0 + relative_end
        pieces = partition(system, mic, left, right)
        durations = {kind: 0.0 for kind in types}
        for piece in pieces:
            durations[piece["type"]] += piece["duration_seconds"]
            piece["card_relative_start"] = round(piece["start"] - card_t0, 6)
            piece["card_relative_end"] = round(piece["end"] - card_t0, 6)
        table.append({
            "window": name,
            "card_relative_seconds": [relative_start, round(relative_end, 6)],
            "expected_type": expected,
            "dominant_type": max(durations, key=durations.get),
            "type_durations_seconds": {key: round(value, 6) for key, value in durations.items()},
            "pieces": pieces,
        })
    required = ("solo", "remote_only", "both")
    passes = all(totals[kind] >= 15.0 for kind in required)
    output = root / "derived/s05-verdict"
    output.mkdir(parents=True, exist_ok=False)
    tape_durations = {lane: levels(root / "audio" / f"{lane}.wav")["duration_seconds"] for lane in transcripts}
    verdict = {
        "schema": "moss-dl2-s05-timeline-verdict.v1",
        "session_id": manifest["session_id"],
        "evaluated_at_utc": utc_now(),
        "card_t0_tape_seconds": card_t0,
        "card_t0_basis": "first blind microphone ASR cue: S05 Pilot Microphone Lane",
        "card_end_tape_seconds": closing_end,
        "card_duration_seconds": round(closing_end - card_t0, 6),
        "operator_timing_note": "supervisor card timing was approximate; blind ASR cue/content plus PCM state provide tape alignment",
        "activity_method": {
            "system": "playback-active except contiguous exact-zero PCM runs of at least 0.25s",
            "microphone": "blind ASR speech segments grouped across gaps no greater than 5s",
            "duration_gate_accounting": "cumulative content within the card; longest contiguous duration also reported",
        },
        "system_exact_zero_runs_tape_seconds": system_zero,
        "microphone_activity_groups_tape_seconds": mic,
        "window_table": table,
        "type_totals_seconds": {key: round(value, 6) for key, value in totals.items()},
        "longest_contiguous_seconds": {key: round(value, 6) for key, value in longest.items()},
        "gate": {"minimum_seconds_each": 15.0, "required_types": list(required), "passes": passes},
        "trailing_dead_air": {
            "starts_after_card_tape_seconds": closing_end,
            "ends_at_external_stop_by_lane_seconds": tape_durations,
            "excluded_from_content_gate": True,
        },
        "per_lane": {
            lane: {
                "segment_count": len(transcripts[lane]),
                "speaker_labels": sorted({str(item.get("speaker")) for item in transcripts[lane]}),
                "levels": levels(root / "audio" / f"{lane}.wav"),
                "transcript_sha256": sha256(root / "derived/asr" / lane / "asr-transcript.json"),
            }
            for lane in transcripts
        },
        "verdict": "USABLE_AS_IS" if passes else "INVALID_FOR_SAME_GENDER_PURPOSE",
    }
    atomic_json(output / "S05_TIMELINE_VERDICT.json", verdict)
    seal_tree(output, output / "S05_VERDICT_EVIDENCE.sha256")
    manifest["s05_verdict"] = {
        "verdict": verdict["verdict"],
        "path": "derived/s05-verdict/S05_TIMELINE_VERDICT.json",
        "sha256": sha256(output / "S05_TIMELINE_VERDICT.json"),
        "seal_path": "derived/s05-verdict/S05_VERDICT_EVIDENCE.sha256",
        "seal_sha256": sha256(output / "S05_VERDICT_EVIDENCE.sha256"),
    }
    atomic_json(manifest_path, manifest)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0 if passes else 2


if __name__ == "__main__":
    raise SystemExit(main())
