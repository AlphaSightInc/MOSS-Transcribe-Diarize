"""D4 - how much of the live-vs-file gap could an empty-span fix possibly close?

Gate first: recompute TBSA from the baseline hypothesis JSONL and check it reproduces
results.json exactly. Then substitute recovered text into the live hypothesis and recompute.

Ceilings reported:
  C1 speech-only oracle : only the empty spans that actually contain speech get their true
                          words back (the silent ones stay silent, which is correct).
  C2 metric-max         : every empty window gets a covering hypothesis segment, even the
                          digitally-silent ones. Upper bound of what the *metric* can pay,
                          not a defensible behaviour.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from common import BASELINE, HERE, TRIO, load_hyp, load_reference, load_spans, tbsa

from moss_transcribe_diarize.evaluation import Segment

# Words a perfect decoder would return for each empty window, taken from the file arm's own
# decode of the same audio (the file arm is the accuracy reference for this investigation).
ORACLE_TEXT = {
    ("lex_bill_ackman", 2): "the difference between you said the stock market in the",
    ("lex_javier_milei", 3): "",
    ("lex_javier_milei", 5): "",
    ("lex_javier_milei", 13): "",
    ("lex_javier_milei", 31): "and down",
}


def speaker_for(case: str, start: float, live_hyp) -> str:
    best, best_gap = "S01", 1e9
    for h in live_hyp:
        gap = abs(h.start - start)
        if gap < best_gap:
            best, best_gap = h.speaker, gap
    return best


def summarize(rows: dict[str, dict]) -> dict[str, float]:
    keys = ("composite", "text_speaker_accuracy", "text_coverage", "wer")
    return {k: round(sum(rows[c][k] for c in TRIO) / len(TRIO), 6) for k in keys}


def main() -> None:
    baseline = json.load(open(BASELINE / "results.json"))
    published = {c["case_id"]: c["arms"] for c in baseline["cases"]}

    live, file_, gate = {}, {}, []
    for case in TRIO:
        lh = load_hyp(BASELINE / case / "live-hypothesis.jsonl")
        fh = load_hyp(BASELINE / case / "file-hypothesis.jsonl")
        live[case] = tbsa(case, lh)
        file_[case] = tbsa(case, fh)
        for arm, mine in (("live", live[case]), ("file", file_[case])):
            pub = published[case][arm]["scores"]["tbsa"]
            ok = all(abs(mine[k] - pub[k]) < 1e-6 for k in ("composite", "text_coverage", "wer"))
            gate.append(ok)
            print(f"[gate] {case:20s} {arm:4s} recompute==published: {ok}")
    assert all(gate), "metric recomputation does not reproduce the baseline"

    variants = {"C1_speech_only": {}, "C2_metric_max": {}}
    detail = {}
    for case in TRIO:
        lh = load_hyp(BASELINE / case / "live-hypothesis.jsonl")
        spans = [s for s in load_spans(case) if s.empty_reason is not None]
        for name in variants:
            segs = list(lh)
            for sp in spans:
                text = ORACLE_TEXT.get((case, sp.span_id), "")
                if name == "C1_speech_only" and not text:
                    continue
                segs.append(Segment(sp.start_s, sp.end_s, speaker_for(case, sp.start_s, lh), text))
            variants[name][case] = tbsa(case, segs)
        detail[case] = {
            "empty_spans": [(s.span_id, round(s.start_s, 2), round(s.end_s, 2)) for s in spans],
        }

    rows = {"file": file_, "live": live, **variants}
    print()
    hdr = f"{'arm':16s} {'composite':>10s} {'tsa':>8s} {'coverage':>9s} {'wer':>8s}"
    print(hdr)
    out = {}
    for name, per_case in rows.items():
        agg = summarize(per_case)
        out[name] = {"trio": agg, "per_case": per_case}
        print(
            f"{name:16s} {agg['composite']:10.4f} {agg['text_speaker_accuracy']:8.4f} "
            f"{agg['text_coverage']:9.4f} {agg['wer']:8.4f}"
        )
    base_gap_cov = out["file"]["trio"]["text_coverage"] - out["live"]["trio"]["text_coverage"]
    base_gap_wer = out["live"]["trio"]["wer"] - out["file"]["trio"]["wer"]
    base_gap_comp = out["file"]["trio"]["composite"] - out["live"]["trio"]["composite"]
    print(f"\nbaseline trio gaps: coverage {base_gap_cov:.4f}  wer {base_gap_wer:.4f}  composite {base_gap_comp:.4f}")
    for name in variants:
        cov = out[name]["trio"]["text_coverage"] - out["live"]["trio"]["text_coverage"]
        wer = out["live"]["trio"]["wer"] - out[name]["trio"]["wer"]
        comp = out[name]["trio"]["composite"] - out["live"]["trio"]["composite"]
        print(
            f"{name:16s} closes coverage {cov:+.4f} ({100*cov/base_gap_cov:5.1f}% of gap)  "
            f"wer {wer:+.4f} ({100*wer/base_gap_wer:5.1f}%)  composite {comp:+.4f} ({100*comp/base_gap_comp:5.1f}%)"
        )
    out["gaps"] = {"coverage": base_gap_cov, "wer": base_gap_wer, "composite": base_gap_comp}
    out["detail"] = detail
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out/d4.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
