"""Score first-visible 0.5 s preview buckets from the paced HTTP long60 run."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

RATE = 16000
STEP = RATE // 2


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
    first: dict[int, dict] = {}
    for row in sorted(rows, key=lambda item: item["observed_wall_s"]):
        if row["source_lane"] != "system":
            continue
        for bucket in range(row["start_sample"] // STEP,
                            (row["end_sample"] - 1) // STEP + 1):
            middle = bucket * STEP + STEP // 2
            if row["start_sample"] <= middle < row["end_sample"]:
                first.setdefault(bucket, row)

    eligible = shown = correct = 0
    unobserved_reference_buckets = 0
    for bucket, row in first.items():
        middle_s = (bucket + .5) * .5
        speakers = {ref["speaker"] for ref in refs if ref["start"] <= middle_s < ref["end"]}
        if len(speakers) != 1:
            continue
        truth = next(iter(speakers))
        eligible += 1
        guess = row["tentative_speaker"]
        if guess is not None:
            shown += 1
            correct += mapping.get(guess) == truth
    max_bucket = round(json.loads((run / "summary.json").read_text())["duration_seconds"] * 2)
    for bucket in range(max_bucket):
        middle_s = (bucket + .5) * .5
        if bucket not in first and any(ref["start"] <= middle_s < ref["end"] for ref in refs):
            unobserved_reference_buckets += 1
    diagnostics = json.loads((run / "engine-diagnostics.json").read_text())
    duration = json.loads((run / "summary.json").read_text())["duration_seconds"]
    result = {"schema": "wp4-tentative-long60.v1", "pace": 1.0,
              "first_seen_provisional_rows": len(rows),
              "eligible_speaker_tbd_buckets": eligible,
              "shown_buckets": shown, "correct_buckets": correct,
              "eligible_speaker_tbd_s": eligible * .5,
              "shown_s": shown * .5, "correct_s": correct * .5,
              "unobserved_reference_speech_buckets": unobserved_reference_buckets,
              "coverage": shown / eligible if eligible else None,
              "accuracy_when_shown": correct / shown if shown else None,
              "canonical_to_reference": mapping,
              "tentative_embed_p50_ms": diagnostics.get("tentative_embed_p50_ms"),
              "tentative_embed_p95_ms": diagnostics.get("tentative_embed_p95_ms"),
              "tentative_busy_ticks": diagnostics.get("tentative_busy_ticks"),
              "tentative_embed_wall_s": diagnostics.get("tentative_embed_wall_s"),
              "embed_wall_share_of_audio": diagnostics.get("tentative_embed_wall_s", 0) / duration,
              "cost_usd": diagnostics.get("cost_usd"), "audio_seconds": duration}
    (run / "tentative-score.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
