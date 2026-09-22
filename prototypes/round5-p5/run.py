"""THROWAWAY P5 logic prototype: score the retained F1 alternation surface."""
from __future__ import annotations

import json
from pathlib import Path

from moss_transcribe_diarize.lane_word_oracle import normalize_segment, score_lanes
from moss_transcribe_diarize.phase2_acceptance import QUALITY_BOUNDS


RETAINED = Path("/private/tmp/moss-r4-10-20260921T103418Z/preterm/alternation")
L1_EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-22/moss-round5/evidence")
LANES = ("system", "microphone")


def reference_for(lane: str) -> str:
    return json.loads((RETAINED / lane / f"reference-{lane}.jsonl").read_text().splitlines()[0])["text"]


def main() -> None:
    layers = [json.loads((RETAINED / lane / f"published-{lane}.json").read_text()) for lane in LANES]
    assert layers[0] == layers[1], "F1 retained copies diverge"
    segments = layers[0]
    normalized = [normalize_segment(segment) for segment in segments]
    abstentions = [segment for segment in normalized if segment["speaker"] in {"", "S00"}]
    identified = [segment for segment in normalized if segment["speaker"] not in {"", "S00"}]
    lane_sets = {}
    for segment in identified:
        lane_sets.setdefault(segment["speaker"], set()).add(segment["source_lane"])
    result = score_lanes(
        segments,
        {lane: reference_for(lane) for lane in LANES},
        max_wer=QUALITY_BOUNDS["immediate_wer"][1],
        lane_switches=(29,),
    )
    l1_receipts = []
    for receipt_path in sorted(L1_EVIDENCE.glob("r5-l1-*/run/*/alternation/receipt.json")):
        receipt = json.loads(receipt_path.read_text())
        score = receipt["pre"]["score"]
        l1_receipts.append({
            "case": receipt_path.parent.parent.name,
            "rescore": "UNMEASURED",
            "missing_inputs": ["published segment text and identity", "reference text"],
            "recorded_pre_score": {
                "passed": score["passed"],
                "speaker_lane_conflicts": score["speaker_lane_conflicts"],
                "wer": {lane: score["lanes"][lane]["wer"] for lane in LANES},
            },
        })
    report = {
        "prototype": "P5 retained F1 alternation; content-free",
        "input": {
            "published_segment_count": len(segments),
            "reference_word_counts": {lane: len(reference_for(lane).split()) for lane in LANES},
            "published_copies_equal": layers[0] == layers[1],
        },
        "normalization": {
            "canonical_none_normalizes_to": abstentions[0]["speaker"] if abstentions else None,
            "persisted_s00_normalizes_to": normalize_segment(
                {"speaker_entity_id": "S00", "start": 0, "end": 1, "text": ""}
            )["speaker"],
            "abstention_segment_count": len(abstentions),
            "abstention_lanes": sorted({segment["source_lane"] for segment in abstentions}),
            "abstention_sample_ranges": [[segment["start_sample"], segment["end_sample"]] for segment in abstentions],
            "identified_speaker_count": len(lane_sets),
            "identified_speakers_in_both_lanes": sum(len(lanes) > 1 for lanes in lane_sets.values()),
        },
        "production_score": {
            "passed": result["passed"],
            "speaker_lane_conflicts": result["speaker_lane_conflicts"],
            "unattributed_segment_count": result["unattributed_segment_count"],
            "unattributed_word_count": result["unattributed_word_count"],
            "identity_unqualified": result["identity_unqualified"],
            "attribution_errors": result["attribution_errors"],
            "duplication_count": result["duplication_count"],
            "unresolved_words": result["unresolved_words"],
            "wer": {lane: result["lanes"][lane]["wer"] for lane in LANES},
            "max_wer": result["max_wer"],
        },
        "r5_l1_pre_rescores": l1_receipts,
        "falsifier": "identified speaker in both lanes must remain a conflict",
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
