"""Score first-seen preview guesses from http_long60.py against long60's public reference."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

RATE = 16000


def overlap(start: float, end: float, reference: dict) -> float:
    return max(0.0, min(end, reference["end"]) - max(start, reference["start"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir
    refs = [row for row in json.loads((run / "timed-segments.json").read_text())["reference"]
            if row["speaker"] not in (None, "", "<EXCLUDE>")]
    settled = json.loads((run / "pre_stop_settled.json").read_text())[
        "session"]["effective_transcript"]
    votes: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in settled:
        speaker = row["canonical_speaker"]
        if speaker is None or row.get("source_lane") != "system":
            continue
        start, end = row["start_sample"] / RATE, row["end_sample"] / RATE
        for ref in refs:
            votes[speaker][ref["speaker"]] += overlap(start, end, ref)
    mapping = {speaker: max(counts, key=counts.get) for speaker, counts in votes.items()}
    rows = [json.loads(line) for line in (run / "tentative-first-seen.jsonl").read_text().splitlines()]
    eligible = shown = correct = 0.0
    eligible_rows = shown_rows = 0
    for row in rows:
        if row["source_lane"] != "system":
            continue
        start, end = row["start_sample"] / RATE, row["end_sample"] / RATE
        truth = [(ref["speaker"], overlap(start, end, ref)) for ref in refs]
        speech = sum(seconds for _, seconds in truth)
        if speech <= 0:
            continue
        eligible_rows += 1
        eligible += speech
        guess = row["tentative_speaker"]
        if guess is None:
            continue
        shown_rows += 1
        shown += speech
        correct += sum(seconds for speaker, seconds in truth if mapping.get(guess) == speaker)
    diagnostics = json.loads((run / "engine-diagnostics.json").read_text())
    duration = json.loads((run / "summary.json").read_text())["duration_seconds"]
    result = {"schema": "wp4-tentative-long60.v1", "pace": 1.0,
              "first_seen_provisional_rows": len(rows), "eligible_system_rows": eligible_rows,
              "shown_system_rows": shown_rows, "eligible_reference_speech_s": eligible,
              "shown_reference_speech_s": shown, "correct_reference_speech_s": correct,
              "coverage": shown / eligible if eligible else None,
              "accuracy_when_shown": correct / shown if shown else None,
              "canonical_to_reference": mapping,
              "tentative_embed_p50_ms": diagnostics.get("tentative_embed_p50_ms"),
              "tentative_embed_p95_ms": diagnostics.get("tentative_embed_p95_ms"),
              "tentative_busy_ticks": diagnostics.get("tentative_busy_ticks"),
              "tentative_embed_wall_s": diagnostics.get("tentative_embed_wall_s"),
              "embed_wall_share_of_audio": diagnostics.get("tentative_embed_wall_s", 0) / duration,
              "cost_usd": diagnostics.get("cost_usd"),
              "audio_seconds": duration}
    (run / "tentative-score.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
