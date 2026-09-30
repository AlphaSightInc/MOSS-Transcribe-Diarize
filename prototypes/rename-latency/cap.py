"""PROTOTYPE (issue #15, decision evidence only) - how far is a bounded-speech voiceprint
from today's all-rows voiceprint?

Today's after-Stop enrollment is the normalized mean of one WeSpeaker vector per saved row
of the speaker (all of their speech). A cap would embed only rows spread evenly through the
meeting until X seconds. Prints cosine(capped, full) per speaker and the cross-speaker cosine
of the full vectors (ADR-0009 match floor is 0.46). Public long60 audio, first N minutes. $0.

Run from the worktree root:
  PYTHONDONTWRITEBYTECODE=1 <venv python> prototypes/rename-latency/cap.py --minutes 13.5
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from measure import MANIFEST, build  # noqa: E402
from moss_transcribe_diarize.app.live_identity_album import cosine_similarity  # noqa: E402
from moss_transcribe_diarize.app.live_provider_bundle import (  # noqa: E402
    LiveProviderBundleConfig, _identity_encoder)
from moss_transcribe_diarize.app.phase2_speaker_identity import _unoverlapped_speaker_rows  # noqa: E402
from moss_transcribe_diarize.app.phase2_voiceprint_match import normalized_mean  # noqa: E402


def spread(vectors, durations, cap):
    """Evenly spaced rows (by index) until their speech reaches cap seconds."""
    for count in range(1, len(vectors) + 1):
        picks = sorted({round(i * (len(vectors) - 1) / max(1, count - 1)) for i in range(count)})
        if sum(durations[i] for i in picks) >= cap:
            return [vectors[i] for i in picks], sum(durations[i] for i in picks)
    return vectors, sum(durations)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=13.5)
    args = parser.parse_args()
    config = LiveProviderBundleConfig.from_manifest(MANIFEST)
    encoder = _identity_encoder(config, interval_workers=3)
    min_seconds = config.identity_provider["min_segment_samples"] / 16000
    with tempfile.TemporaryDirectory(prefix="rename-cap-", dir=ROOT / ".wp9runtime") as tmp:
        wav, rows, ids = build(args.minutes, Path(tmp))
        full = {}
        per_speaker = {}
        for name, speaker in ids.items():
            intervals = [(r["start"], r["end"]) for r in _unoverlapped_speaker_rows(rows, speaker)
                         if r["end"] - r["start"] >= min_seconds]
            if sum(end - start for start, end in intervals) < 30:
                continue
            started = time.perf_counter()
            vectors = encoder.embed_intervals(wav, intervals)
            per_speaker[name] = (vectors, [end - start for start, end in intervals],
                                 time.perf_counter() - started)
            full[name] = normalized_mean(vectors)
        for name, (vectors, durations, seconds) in per_speaker.items():
            line = [f"{name}: {len(vectors)} rows {sum(durations)/60:.1f} min speech, embed {seconds:.1f}s"]
            for cap in (10, 30, 60, 120):
                subset, used = spread(vectors, durations, cap)
                line.append(f"cap{cap}s(rows={len(subset)},{used:.0f}s) cos={cosine_similarity(normalized_mean(subset), full[name]):.4f}")
            print(" | ".join(line), flush=True)
        names = list(full)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                print(f"cross {a} vs {b}: cos={cosine_similarity(full[a], full[b]):.4f}", flush=True)


if __name__ == "__main__":
    main()
