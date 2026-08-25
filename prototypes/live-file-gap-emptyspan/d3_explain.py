"""D3 - what distinguishes an empty span from a decodable neighbour.

Two probes:
  (a) raw decode -- bypass the runner's empty-transcript validation so we can see whether the
      model emitted nothing, emitted text with no words, or emitted something unparseable.
  (b) bounds sweep -- widen / shift / shrink the window around each empty span and re-decode.
"""
from __future__ import annotations

import json

from common import HERE, SECONDARY, SR, TRIO, load_spans, raw_decode, read_pcm, slice_pcm, write_wav

# (label, lead_seconds, trail_seconds) relative to the frozen span bounds
SWEEP = [
    ("exact", 0.00, 0.00),
    ("pad+0.10", 0.10, 0.10),
    ("pad+0.25", 0.25, 0.25),
    ("pad+0.50", 0.50, 0.50),
    ("lead+0.25", 0.25, 0.00),
    ("trail+0.25", 0.00, 0.25),
    ("shift-0.25", 0.25, -0.25),
    ("shift+0.25", -0.25, 0.25),
    ("shrink-0.25", -0.25, -0.25),
]


def main() -> None:
    out = {"raw": [], "sweep": []}
    for case in TRIO + SECONDARY:
        pcm = read_pcm(case)
        total = len(pcm) // 2
        for sp in load_spans(case):
            if sp.empty_reason is None:
                continue
            wav = HERE / "spans" / f"{case}-span{sp.span_id:02d}.wav"
            r = raw_decode(wav, sample_count=sp.end_sample - sp.start_sample)
            r.update({"case": case, "span_id": sp.span_id, "window": [round(sp.start_s, 3), round(sp.end_s, 3)]})
            out["raw"].append(r)
            print(
                f"[raw] {case} span{sp.span_id:02d} gen_tok={r['generated_tokens']:3d} "
                f"parsed={r['parsed_segments']} empty={r['live_would_be_empty']} text={r['stripped']!r}"
            )

            for label, lead, trail in SWEEP:
                s0 = max(0, sp.start_sample - int(round(lead * SR)))
                s1 = min(total, sp.end_sample + int(round(trail * SR)))
                if s1 - s0 < int(0.05 * SR):
                    continue
                path = HERE / "spans" / f"{case}-span{sp.span_id:02d}-{label}.wav"
                write_wav(path, slice_pcm(pcm, s0, s1))
                rr = raw_decode(path, sample_count=s1 - s0)
                row = {
                    "case": case,
                    "span_id": sp.span_id,
                    "variant": label,
                    "window": [round(s0 / SR, 3), round(s1 / SR, 3)],
                    "dur_s": round((s1 - s0) / SR, 3),
                    **rr,
                }
                out["sweep"].append(row)
                print(
                    f"    {label:12s} [{s0/SR:6.2f},{s1/SR:6.2f}] {row['dur_s']:.2f}s "
                    f"gen={rr['generated_tokens']:3d} empty={rr['live_would_be_empty']} -> {rr['stripped']!r}"
                )
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out/d3.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
