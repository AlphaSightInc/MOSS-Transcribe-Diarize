"""D2 - reproduce the empty decode through the exact live-path request shape.

Controls: re-decode two non-empty neighbours and diff against the transcript the baseline
trace committed. If those match verbatim, the harness request shape *is* the live path's.
Concurrency stays at 1 (shared GPU).
"""
from __future__ import annotations

import json
from pathlib import Path

from common import HERE, SECONDARY, SR, TRIO, live_decode, load_spans, read_pcm, slice_pcm, write_wav

REPEATS = 2
CONTROLS = {"lex_bill_ackman": (1, 3), "lex_javier_milei": (30,)}


def main() -> None:
    out = {"empty_spans": [], "controls": []}
    for case in TRIO + SECONDARY:
        pcm = read_pcm(case)
        spans = {s.span_id: s for s in load_spans(case)}
        for sp in spans.values():
            if sp.empty_reason is None:
                continue
            wav = HERE / "spans" / f"{case}-span{sp.span_id:02d}.wav"
            spcm = slice_pcm(pcm, sp.start_sample, sp.end_sample)
            write_wav(wav, spcm)
            attempts = []
            for _ in range(REPEATS):
                text, gen, elapsed, cap, empty = live_decode(wav, sample_count=sp.end_sample - sp.start_sample)
                attempts.append(
                    {"text": text, "generated_tokens": gen, "elapsed_s": round(elapsed, 3), "token_cap": cap,
                     "empty_error": empty}
                )
            row = {
                "case": case,
                "span_id": sp.span_id,
                "window": [round(sp.start_s, 3), round(sp.end_s, 3)],
                "dur_s": round(sp.dur_s, 3),
                "attempts": attempts,
                "deterministic_empty": all(a["text"].strip() == "" for a in attempts),
            }
            out["empty_spans"].append(row)
            print(
                f"[empty ] {case} span{sp.span_id:02d} [{sp.start_s:.2f},{sp.end_s:.2f}] cap={attempts[0]['token_cap']} "
                f"-> {['EMPTY' if not a['text'].strip() else repr(a['text'])[:70] for a in attempts]}"
            )
        for span_id in CONTROLS.get(case, ()):  # verbatim-match controls
            sp = spans[span_id]
            wav = HERE / "spans" / f"{case}-control{span_id:02d}.wav"
            write_wav(wav, slice_pcm(pcm, sp.start_sample, sp.end_sample))
            text, gen, elapsed, cap, empty = live_decode(wav, sample_count=sp.end_sample - sp.start_sample)
            match = text.strip() == sp.transcript.strip()
            out["controls"].append(
                {"case": case, "span_id": span_id, "matches_baseline": match,
                 "baseline": sp.transcript, "redecode": text, "generated_tokens": gen,
                 "elapsed_s": round(elapsed, 3), "token_cap": cap}
            )
            print(f"[control] {case} span{span_id:02d} verbatim_match={match}")
            if not match:
                print(f"          baseline={sp.transcript!r}")
                print(f"          redecode={text!r}")
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out/d2.json").write_text(json.dumps(out, indent=1))
    n_det = sum(1 for r in out["empty_spans"] if r["deterministic_empty"])
    print(f"\ndeterministically empty on re-decode: {n_det}/{len(out['empty_spans'])}")
    print(f"controls verbatim-matching baseline: {sum(1 for c in out['controls'] if c['matches_baseline'])}/{len(out['controls'])}")


if __name__ == "__main__":
    main()
