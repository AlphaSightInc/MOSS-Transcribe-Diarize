"""Zero-send common.score replay with canonical real-reference EXCLUDE masking.

Run from worktree: python prototypes/gemini-live/continuity/score_support.py --tier gold9
"""
from __future__ import annotations

import argparse
import json
import sys

from measure import EVIDENCE, HERE, cached_embeddings, evaluate, measured_score, note, segmentize, windows

sys.path.insert(0, str(HERE.parent))
from common.corpus import clips  # noqa: E402
from common.gemini_common import diarize_window, read_wav  # noqa: E402


def subtract(start: float, end: float, masks: list[tuple[float, float]]):
    pieces = [(start, end)]
    for mask_start, mask_end in masks:
        next_pieces = []
        for a, b in pieces:
            if mask_end <= a or mask_start >= b:
                next_pieces.append((a, b))
            else:
                if a < mask_start:
                    next_pieces.append((a, min(b, mask_start)))
                if mask_end < b:
                    next_pieces.append((max(a, mask_end), b))
        pieces = next_pieces
    return [(a, b) for a, b in pieces if b > a]


def mask_words(words: list[dict], masks: list[tuple[float, float]]):
    retained = []
    removed = 0
    zero = 0
    for word in words:
        if word["end"] <= word["start"]:
            zero += 1
            continue
        parts = subtract(word["start"], word["end"], masks)
        if not parts:
            removed += 1
        for index, (start, end) in enumerate(parts):
            retained.append({**word, "start": start, "end": end,
                             "text": word["text"] if index == max(
                                 range(len(parts)), key=lambda j: parts[j][1]-parts[j][0]) else ""})
    return retained, removed, zero


def score_clip(clip):
    obs = []
    for start, end, part in windows(read_wav(clip.audio), 10, 30):
        result = diarize_window(part, max_attempts=0)
        obs.append({"start": start, "end": end,
                    "words": [vars(word) for word in result.words],
                    "api_latency_s": result.latency_s})
    _, cached = cached_embeddings(clip, obs, 10, 30, False, None)
    if not cached:
        raise RuntimeError(f"missing span2s vectors for {clip.clip_id}")
    reference = clip.reference_segments()
    # Synthetic reference segments have intentionally empty text but valid
    # diarization truth; only real-corpus empty/<EXCLUDE> rows denote masks.
    excluded = [row for row in reference if clip.tier != "synth" and
                (row["speaker"] == "<EXCLUDE>" or not row["text"].strip())]
    masks = [(row["start"], row["end"]) for row in excluded]
    reference = [row for row in reference if row not in excluded]
    variants = {
        "pure_C1": evaluate([], obs, 0, .3, include_segments=True),
        "C1_C3_local": evaluate([], obs, 0, .3, .46, .6, include_segments=True),
    }
    scored = {}
    for name, variant in variants.items():
        views = {}
        for view, words in (("first_committed", variant["first_words"]),
                            ("last_revised", variant["last_revised_words"])):
            filtered, removed, zero = mask_words(words, masks)
            segments = segmentize(filtered)
            views[view] = {"metrics": measured_score(reference, segments),
                           "speaker_count": len({word["speaker"] for word in filtered}),
                           "masked_words": removed, "zero_duration_words": zero,
                           "segments": segments}
        scored[name] = views
    return {"case": clip.clip_id, "tier": clip.tier,
            "score_path": "common.score with polynomial exact optimizer when needed",
            "synthetic_text_metrics": "unmeasured" if clip.tier == "synth" else "scored",
            "excluded_reference_rows": excluded, "excluded_intervals": masks,
            "windows": len(obs), "variants": scored}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", required=True,
                        choices=("gold9", "bench5m", "long30m", "synth"))
    parser.add_argument("--case", default="")
    args = parser.parse_args()
    selected = [clip for clip in clips(args.tier)
                if (not args.case or args.case in clip.clip_id)
                and (args.tier != "gold9" or clip.clip_id != "benchmark:acquired_jamie_dimon")
                and (args.tier not in ("bench5m", "long30m") or "lex_" in clip.clip_id)]
    note(f"Start zero-send common.score support replay {args.tier}, {len(selected)} cases, "
         "real <EXCLUDE>/empty reference rows masked")
    for clip in selected:
        result = score_clip(clip)
        path = EVIDENCE / f"support-score-{clip.tier}-{clip.clip_id}-S10-L30-H0.json"
        path.write_text(json.dumps(result, indent=2))
        print(json.dumps({"case": clip.clip_id, "excluded_intervals": result["excluded_intervals"],
                          "first": {name: value["first_committed"]["metrics"]
                                    for name, value in result["variants"].items()}}), flush=True)
        note(f"support-score {clip.clip_id}: pure DER "
             f"{result['variants']['pure_C1']['first_committed']['metrics']['der']:.6f}, "
             f"C3 DER {result['variants']['C1_C3_local']['first_committed']['metrics']['der']:.6f}, "
             f"masked {result['excluded_intervals']}, receipt {path.name}")
