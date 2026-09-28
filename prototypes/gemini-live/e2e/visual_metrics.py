"""Reduce rendered live DOM filmstrips to comparable, content-free visual metrics.

One command: python prototypes/gemini-live/e2e/visual_metrics.py --run RUN --out summary.json
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


UNMEASURED = "UNMEASURED"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def percentile(values: list[float], fraction: float) -> float | str:
    if not values:
        return UNMEASURED
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lo, hi = math.floor(position), math.ceil(position)
    return round(values[lo] + (values[hi] - values[lo]) * (position - lo), 3)


def audio_origin(run: Path, events: list[dict]) -> tuple[int | None, str]:
    clock = run / "audio-start.json"
    if clock.exists():
        return json.loads(clock.read_text())["monotonic_ns"], "paced_sender_exact"
    for item in events:
        event = item.get("event") or {}
        if event.get("kind") == "frame_accepted" and event.get("payload", {}).get("sequence") == 0:
            return item["observed_monotonic_ns"], "first_frame_accepted_poll_approximate"
    return None, UNMEASURED


def final_segments(saved: dict) -> list[dict]:
    transcript = saved.get("transcript") or {}
    return transcript.get("segments") or []


def compute(run: Path, seconds: float | None = None) -> dict:
    film = read_jsonl(run / "filmstrip.jsonl")
    events = read_jsonl(run / "events.jsonl")
    saved = json.loads((run / "saved-meeting.json").read_text()) if (run / "saved-meeting.json").exists() else {}
    final = final_segments(saved)
    origin_ns, origin_source = audio_origin(run, events)
    if seconds is None:
        raw = json.loads((run / "summary.json").read_text()) if (run / "summary.json").exists() else {}
        seconds = raw.get("seconds")
    stop_ns = next((item["observed_monotonic_ns"] for item in events
                    if (item.get("event") or {}).get("kind") == "stop_requested"), None)
    pre_stop = [f for f in film if stop_ns is None or f["observed_monotonic_ns"] < stop_ns]
    last = pre_stop[-1]["rows"] if pre_stop else []
    all_labels, labels_over_time = set(), []
    first_text: dict[int, float] = {}
    first_label: dict[int, float] = {}
    live_keys, visible_keys = set(), set()
    first_key_at: dict[tuple, float] = {}
    prior_label: dict[str, str] = {}
    flip_count = 0
    uncertain_row_samples = 0
    uncertain_peak_rows = 0
    uncertain_keys = set()
    for frame in pre_stop:
        seen_ns = frame["observed_monotonic_ns"]
        elapsed = (seen_ns - origin_ns) / 1e9 if origin_ns is not None else None
        uncertain_peak_rows = max(uncertain_peak_rows, sum(
            bool(r.get("uncertain") or r.get("label") == "Speaker uncertain") for r in frame["rows"]))
        frame_labels = {r.get("label") for r in frame["rows"] if r.get("label") and not r.get("uncertain")}
        all_labels.update(frame_labels)
        labels_over_time.append({"audio_s": round(elapsed, 2) if elapsed is not None else UNMEASURED,
                                 "distinct_labels": len(frame_labels)})
        for row in frame["rows"]:
            label = row.get("label") or ""
            uncertain = bool(row.get("uncertain") or label == "Speaker uncertain")
            uncertain_row_samples += uncertain
            target = row.get("target_keys")
            if target:
                if uncertain:
                    uncertain_keys.add(target)
                if target in prior_label and prior_label[target] != label:
                    flip_count += 1
                prior_label[target] = label
            for segment in row.get("segments") or [row]:
                value = (segment.get("text") or "").strip()
                if not value:
                    continue
                try:
                    start, end = float(segment.get("start")), float(segment.get("end"))
                except (ValueError, TypeError):
                    continue
                if end <= start:
                    continue
                lane = row.get("lane")
                visible_key = (lane, start, end, value)
                visible_keys.add(visible_key)
                live_keys.add((lane, value))
                if elapsed is not None:
                    first_key_at.setdefault(visible_key, elapsed)
                    for second in range(max(0, math.floor(start)), math.ceil(end)):
                        if seconds is not None and second >= seconds:
                            continue
                        if start < second + 1 and end > second:
                            delay = max(0.0, elapsed - second - 1)
                            first_text.setdefault(second, delay)
                            if label and not uncertain and row.get("speaker_id") not in (None, "S00"):
                                first_label.setdefault(second, delay)
    duration_min = seconds / 60 if seconds else UNMEASURED
    last_segments = [s for r in last for s in (r.get("segments") or [r]) if (s.get("text") or "").strip()]
    last_labels = {r.get("label") for r in last if r.get("label") and not r.get("uncertain")}
    final_keys = {(s.get("source_lane"), (s.get("text") or "").strip()) for s in final if (s.get("text") or "").strip()}
    gaps = [(b["observed_monotonic_ns"] - a["observed_monotonic_ns"]) / 1e9 for a, b in zip(film, film[1:])]
    per_minute = {}
    if seconds:
        for minute in range(math.ceil(seconds / 60)):
            starts = [k for k, t in first_key_at.items() if minute * 60 <= t < (minute + 1) * 60]
            per_minute[str(minute)] = len(starts)
    return {
        "audio_seconds": seconds if seconds is not None else UNMEASURED,
        "audio_clock_source": origin_source,
        "audio_start_exact_ns": origin_ns if origin_source == "paced_sender_exact" else UNMEASURED,
        "latency_precision": "exact sender clock" if origin_source == "paced_sender_exact"
            else "approximate: first polled accepted frame" if origin_ns is not None else UNMEASURED,
        "filmstrip_frames": len(film), "pre_stop_frames": len(pre_stop),
        "pre_stop_boundary": "stop_requested_poll" if stop_ns else UNMEASURED,
        "filmstrip_median_gap_s": percentile(gaps, .5),
        "filmstrip_max_gap_s": round(max(gaps), 3) if gaps else UNMEASURED,
        "visible_slice_boundaries_per_min": round(max(0, len(last) - 1) / duration_min, 3)
            if isinstance(duration_min, float) else UNMEASURED,
        "visible_slice_boundary_definition": "adjacent rendered rows at last pre-Stop frame per audio minute",
        "visible_segment_births_by_minute": per_minute if seconds and origin_ns else UNMEASURED,
        "last_live_rows": len(last), "last_live_segments": len(last_segments),
        "distinct_speaker_labels_ever": len(all_labels),
        "distinct_speaker_labels_at_stop": len(last_labels),
        "distinct_speaker_labels_peak_concurrent": max((x["distinct_labels"] for x in labels_over_time), default=0),
        "distinct_speaker_labels_over_time": labels_over_time,
        "uncertain_row_samples": uncertain_row_samples,
        "uncertain_peak_rows": uncertain_peak_rows,
        "uncertain_rows_at_stop": sum(bool(r.get("uncertain") or r.get("label") == "Speaker uncertain")
                                      for r in last),
        "uncertain_distinct_target_keys": len(uncertain_keys) if uncertain_keys else 0,
        "first_text_on_screen_latency_s": {
            "p50": percentile(list(first_text.values()), .5), "p90": percentile(list(first_text.values()), .9),
            "observed_audio_seconds": len(first_text), "total_audio_seconds": math.ceil(seconds) if seconds else UNMEASURED},
        "label_on_screen_latency_s": {
            "p50": percentile(list(first_label.values()), .5), "p90": percentile(list(first_label.values()), .9),
            "observed_audio_seconds": len(first_label), "total_audio_seconds": math.ceil(seconds) if seconds else UNMEASURED},
        "relabel_events": flip_count, "relabel_events_per_min": round(flip_count / duration_min, 3)
            if isinstance(duration_min, float) else UNMEASURED,
        "relabel_identity": "same DOM target_keys only",
        "live_to_final_text_survival": {
            "surviving_lane_text_keys": len(live_keys & final_keys) if saved else UNMEASURED,
            "distinct_live_lane_text_keys": len(live_keys),
            "definition": "exact lane and stripped text, no semantic alignment"},
        "final_segment_count": len(final) if saved else UNMEASURED,
        "saved_status": saved.get("status", UNMEASURED),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seconds", type=float)
    args = parser.parse_args()
    result = compute(args.run, args.seconds)
    summary = {
        "mode": "recorded_dom_reduction",
        "status": "RECORDED_REDUCED",
        "max_pacing_lag_s": UNMEASURED,
        "screenshots": UNMEASURED,
        "provider_spend_usd": UNMEASURED,
        "gemini_timing_anomalies": {"calls": 0, "clamped": 0, "dropped": 0,
                                    "clamped_per_call": "NOT_APPLICABLE",
                                    "dropped_per_call": "NOT_APPLICABLE"},
        "visual_metrics": result,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "distinct_speaker_labels_over_time"}, indent=2))


if __name__ == "__main__":
    main()
