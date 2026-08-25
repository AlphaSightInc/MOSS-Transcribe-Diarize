"""Provoke discarded spans on the 3-minute tier (lex_adam_frank).

The deployed backend is read-only, so no live session is run. Instead the gated span
simulator (sim_spans.py, gate G2) partitions the audio exactly as the live endpoint policy
would, and every span is decoded once through the live request shape. A span whose decode
would be dropped by `parse_transcript` is a discard -- the same failure H3 names.
"""
from __future__ import annotations

import json
import sys

from common import HERE, SR, case_dir, raw_decode, read_pcm, slice_pcm, vad_speech_ratio, write_wav
from sim_spans import simulate

CASE = sys.argv[1] if len(sys.argv) > 1 else "lex_adam_frank"


def main() -> None:
    pcm = read_pcm(CASE)
    spans = simulate(pcm)
    print(f"{CASE}: {len(spans)} simulated spans over {len(pcm)/2/SR:.1f}s")
    rows = []
    discards = 0
    for i, (a, b, reason) in enumerate(spans):
        spcm = slice_pcm(pcm, a, b)
        wav = HERE / "spans" / f"{CASE}-sim{i:03d}.wav"
        write_wav(wav, spcm)
        r = raw_decode(wav, sample_count=b - a)
        row = {
            "span_id": i,
            "start_s": round(a / SR, 3),
            "end_s": round(b / SR, 3),
            "dur_s": round((b - a) / SR, 3),
            "reason": reason,
            "vad_speech_ratio": round(vad_speech_ratio(spcm), 4),
            **r,
        }
        rows.append(row)
        if r["live_would_be_empty"]:
            discards += 1
            print(
                f"  DISCARD span{i:03d} [{a/SR:7.2f},{b/SR:7.2f}] {row['dur_s']:.2f}s "
                f"reason={reason:15s} vad={row['vad_speech_ratio']:.3f} gen={r['generated_tokens']:3d} "
                f"text={r['stripped']!r}"
            )
        if not wav.name.endswith("000.wav"):
            wav.unlink(missing_ok=True)
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / f"out/p1-{CASE}.json").write_text(json.dumps({"case": CASE, "spans": rows}, indent=1))
    words = sum(len(r["stripped"].split()) for r in rows if r["live_would_be_empty"])
    print(
        f"\n{CASE}: spans={len(rows)} discards={discards} "
        f"({100*discards/len(rows):.1f}%) discarded_audio_s={sum(r['dur_s'] for r in rows if r['live_would_be_empty']):.2f} "
        f"tokens_thrown_away={sum(r['generated_tokens'] for r in rows if r['live_would_be_empty'])}"
    )


if __name__ == "__main__":
    main()
