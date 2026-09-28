"""Offline W4 overlap-stitch falsifier on saved public window responses."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from corpus import clips  # noqa: E402
from score import score  # noqa: E402
from proto_words import dropped_passages, mono, percentile  # noqa: E402


def norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def replay(windows: list[dict], *, dedupe_s: float = 0.0, mature_s: float = 0.0):
    accepted = []
    watermark = 0.0
    duration = max(w["window_end_s"] for w in windows)
    for w in sorted(windows, key=lambda x: x["arrival_s"]):
        eligible_end = duration if w["window_end_s"] >= duration else w["window_end_s"] - mature_s
        new = []
        for word in sorted(w["words"], key=lambda x: x["start"]):
            if word["end"] > eligible_end + 1e-6:
                continue
            if word["end"] <= watermark + 0.05 or word["start"] < watermark - 0.15:
                continue
            if dedupe_s and any(norm(old["text"]) == norm(word["text"]) and
                                abs((old["start"] + old["end"]) / 2 -
                                    (word["start"] + word["end"]) / 2) <= dedupe_s
                                for old in accepted[-20:]):
                continue
            new.append({**word, "arrival_s": w["arrival_s"]})
        if new:
            watermark = max(x["end"] for x in new)
            accepted.extend(new)
    return accepted


def evaluate(path: Path):
    d = json.loads(path.read_text())
    clip = next(c for c in clips() if c.clip_id == d["clip"])
    ref = mono(clip.reference_segments())
    out = []
    for name, dedupe_s, mature_s in (("baseline", 0, 0), ("near_time_dedupe", .5, 0),
                                     ("mature_2s", 0, 2)):
        words = replay(d["windows_full"], dedupe_s=dedupe_s, mature_s=mature_s)
        hyp = [{"start": w["start"], "end": max(w["start"] + .001, w["end"]),
                "speaker": "one", "text": w["text"]} for w in words]
        lat = [w["arrival_s"] - w["end"] for w in words]
        drop = dropped_passages(ref, hyp)
        out.append({"variant": name, "clip": clip.clip_id, "words": len(words),
                    "wer": score(ref, hyp)["wer"], "latency_p50_s": percentile(lat, 50),
                    "dropped_reference_seconds": sum(x["end"] - x["start"] for x in drop)})
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("receipts", nargs="+", type=Path)
    args = p.parse_args()
    all_rows = [row for path in args.receipts for row in evaluate(path)]
    print(json.dumps(all_rows, indent=2))


if __name__ == "__main__":
    main()
