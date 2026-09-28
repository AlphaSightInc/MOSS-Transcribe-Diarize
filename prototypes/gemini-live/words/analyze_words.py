"""Lexical timing audit for P52 public-corpus probes (coarse reference-time estimate)."""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from corpus import clips  # noqa: E402


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.lower())


def reference_words(ref: list[dict], oracle: list[dict] | None = None) -> list[dict]:
    result = []
    for r in ref:
        ts = tokens(r["text"])
        for i, word in enumerate(ts):
            result.append({"word": word, "time_s": float(r["start"]) +
                           (i + 0.5) / max(1, len(ts)) * (float(r["end"]) - float(r["start"]))})
    if oracle:
        batched = []
        for w in oracle:
            ts = tokens(w["text"])
            for i, word in enumerate(ts):
                batched.append((word, float(w["start"]) + (i + 0.5) / max(1, len(ts)) *
                                (float(w["end"]) - float(w["start"]))))
        matcher = difflib.SequenceMatcher(a=[x["word"] for x in result],
                                          b=[x[0] for x in batched], autojunk=False)
        for block in matcher.get_matching_blocks():
            for j in range(block.size):
                result[block.a + j]["oracle_time_s"] = batched[block.b + j][1]
    return result


def timing(clip, events: list[dict], oracle: list[dict] | None = None) -> dict:
    ref = reference_words(clip.reference_segments(), oracle)
    ref_tokens = [x["word"] for x in ref]
    final_text = ""
    interim = ""
    first: dict[int, float] = {}
    final_matched: set[int] = set()
    for e in events:
        sc = e
        if "interim_input_transcription" in sc:
            interim = sc["interim_input_transcription"].get("text", "")
        if "input_transcription" in sc:
            final_text += " " + sc["input_transcription"].get("text", "")
            interim = ""
        elif "model_text" in sc and not interim:
            interim = sc["model_text"]
        visible = tokens(final_text + " " + interim)
        if not visible:
            continue
        matcher = difflib.SequenceMatcher(a=ref_tokens, b=visible, autojunk=False)
        matched = set()
        for block in matcher.get_matching_blocks():
            for j in range(block.size):
                idx = block.a + j
                matched.add(idx)
                first.setdefault(idx, float(e["wall_s"]))
        final_matched = matched
    lat = [first[i] - ref[i]["time_s"] for i in first if i in final_matched]
    buckets: dict[int, list[int]] = {}
    for i, x in enumerate(ref):
        buckets.setdefault(int(x["time_s"]), []).append(i)
    covered = []
    uncovered = []
    for b, indexes in sorted(buckets.items()):
        if all(i in first and i in final_matched for i in indexes):
            covered.append(max(first[i] for i in indexes) - (b + 1))
        else:
            uncovered.append(b)
    anchored_lat = [first[i] - ref[i]["oracle_time_s"] for i in first if i in final_matched and "oracle_time_s" in ref[i]]
    return {"reference_words": len(ref), "final_matched_words": len(final_matched),
            "first_seen_final_words": len(lat),
            "batch_oracle_anchored_words": len(anchored_lat),
            "batch_oracle_first_appearance_p50_s": round(float(np.percentile(anchored_lat, 50)), 3) if anchored_lat else None,
            "batch_oracle_first_appearance_p90_s": round(float(np.percentile(anchored_lat, 90)), 3) if anchored_lat else None,
            "word_first_appearance_p50_s": round(float(np.percentile(lat, 50)), 3) if lat else None,
            "word_first_appearance_p90_s": round(float(np.percentile(lat, 90)), 3) if lat else None,
            "word_first_appearance_max_s": round(max(lat), 3) if lat else None,
            "covered_1s_buckets": len(covered), "reference_1s_buckets": len(buckets),
            "coverage_latency_p50_s": round(float(np.percentile(covered, 50)), 3) if covered else None,
            "coverage_latency_p90_s": round(float(np.percentile(covered, 90)), 3) if covered else None,
            "uncovered_1s_buckets": uncovered,
            "timing_note": "Reference words placed uniformly within reference turns; first appearance is lexical match, not forced alignment."}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("result", type=Path)
    p.add_argument("--oracle", type=Path)
    args = p.parse_args()
    data = json.loads(args.result.read_text())
    clip = next(c for c in clips() if c.clip_id == data["clip"])
    oracle = json.loads(args.oracle.read_text())["words"] if args.oracle else None
    print(json.dumps(timing(clip, data["events_full"], oracle), indent=2))


if __name__ == "__main__":
    main()
