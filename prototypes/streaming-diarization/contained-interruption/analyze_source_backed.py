"""Adjudicate the retained decoder matrix and run both normalizers on its exact spans."""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from moss_transcribe_diarize.app.live_transcript_convergence import resolve_segment_overlaps

from probe import candidate


HERE = Path(__file__).resolve().parent
TARGET_WORDS = ("how", "long", "do", "we", "think", "each", "one", "will", "take")


def words(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[\w']+", text.casefold()))


def contains_target(text: str) -> bool:
    tokens = words(text)
    width = len(TARGET_WORDS)
    return any(tokens[index : index + width] == TARGET_WORDS for index in range(len(tokens) - width + 1))


def main() -> None:
    source = json.loads((HERE / "source-backed/results.json").read_text())
    cases = {}
    for row in source["decoded"]:
        if row.get("segments") is None:
            cases[row["case"]] = {"outcome": row["outcome"], "adjudicable": False}
            continue
        placed = tuple(
            (item["speaker"], round(item["start"] * 16_000), round(item["end"] * 16_000), item["text"])
            for item in row["segments"]
        )
        current = resolve_segment_overlaps(placed)
        proposed = candidate(placed)
        cases[row["case"]] = {
            "adjudicable": True,
            "local_speakers": sorted({item[0] for item in placed}),
            "target_phrase_segments": sum(contains_target(item[3]) for item in placed),
            "segments_over_source_interval_20_00_21_44": [
                item for item in placed if item[1] < round(21.44 * 16_000) and round(20.0 * 16_000) < item[2]
            ],
            "current_normalizer": asdict(current),
            "candidate_normalizer": asdict(proposed),
        }
    overlap_names = [name for name in cases if name.startswith("overlap_")]
    assertions = {
        "sequential_control_emits_target_as_second_speaker": (
            cases["sequential_control"]["target_phrase_segments"] == 1
            and len(cases["sequential_control"]["local_speakers"]) == 2
        ),
        "all_overlap_mixtures_omit_target_words": all(
            cases[name]["target_phrase_segments"] == 0 for name in overlap_names
        ),
        "all_overlap_mixtures_emit_one_local_speaker": all(
            len(cases[name]["local_speakers"]) == 1 for name in overlap_names
        ),
        "normalizer_has_no_overlapped_second_segment_to_recover": all(
            cases[name]["current_normalizer"] == cases[name]["candidate_normalizer"]
            for name in overlap_names
        ),
    }
    output = {"cases": cases, "assertions": assertions}
    (HERE / "source-backed-analysis.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
    if not all(assertions.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
