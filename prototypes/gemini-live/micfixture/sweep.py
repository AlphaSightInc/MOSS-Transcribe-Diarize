"""Throwaway WeSpeaker echo threshold sweep on the frozen public fixture."""
from __future__ import annotations

import json
import math
from pathlib import Path

from moss_transcribe_diarize.app.live_provider_bundle import (
    LiveProviderBundleConfig, _identity_encoder,
)

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"


def spans(rows: list[dict], speaker: str, *, allowed=None, count=3):
    candidates = []
    for row in rows:
        if row["speaker"] != speaker:
            continue
        lo, hi = row["start"], row["end"]
        if allowed is not None:
            for a, b in allowed:
                begin, end = max(lo, a), min(hi, b)
                if end - begin >= 3:
                    candidates.append((begin, min(end, begin + 8)))
        elif hi - lo >= 3:
            candidates.append((lo, min(hi, lo + 8)))
    return sorted(candidates, key=lambda x: -(x[1]-x[0]))[:count]


def cosine(a, b):
    return sum(x*y for x, y in zip(a, b)) / math.sqrt(
        sum(x*x for x in a) * sum(y*y for y in b))


def main():
    ref = json.loads((OUT / "reference.json").read_text())
    encoder = _identity_encoder(LiveProviderBundleConfig.from_manifest(MANIFEST),
                                interval_workers=4)
    clean_system = {s: spans(ref["system_turns"], s) for s in ("A", "B")}
    clean_local = {s: spans(ref["local_turns"], s) for s in ("C", "D")}
    quiet = [(96.2, 139.8), (170.2, 220.8), (234.2, 299.8)]
    echo_spans = {s: spans(ref["system_turns"], s, allowed=quiet) for s in ("A", "B")}
    assert all(clean_system.values()) and all(clean_local.values()) and all(echo_spans.values())
    print(json.dumps({"system_spans": clean_system, "local_spans": clean_local,
                      "echo_spans": echo_spans}, indent=2), flush=True)
    system_vec = {s: encoder.embed(OUT / "system.wav", x) for s, x in clean_system.items()}
    local_vec = {s: encoder.embed(OUT / "headphones-mic.wav", x) for s, x in clean_local.items()}
    negatives = [{"kind": "local", "variant": "headphones", "speaker": l,
                  "system": s, "cosine": cosine(v, system_vec[s])}
                 for l, v in local_vec.items() for s in system_vec]
    positives = []
    for db in (-20, -10):
        path = OUT / f"speakers-{db}-mic.wav"
        for s, intervals in echo_spans.items():
            for interval in intervals:
                vec = encoder.embed(path, [interval])
                positives.append({"kind": "echo", "variant": f"speakers-{db}",
                                  "speaker": s, "interval": interval,
                                  "cosine": cosine(vec, system_vec[s])})
    thresholds = [.40, .45, .50, .55, .60, .65, .70, .75, .80]
    sweep = [{"threshold": t,
              "echo_detected": sum(row["cosine"] >= t for row in positives),
              "echo_total": len(positives),
              "local_false_drops": sum(row["cosine"] >= t for row in negatives),
              "local_total": len(negatives)} for t in thresholds]
    result = {"positives": positives, "negatives": negatives, "sweep": sweep,
              "min_echo_cosine": min(x["cosine"] for x in positives),
              "max_local_cosine": max(x["cosine"] for x in negatives)}
    (OUT / "sweep.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
