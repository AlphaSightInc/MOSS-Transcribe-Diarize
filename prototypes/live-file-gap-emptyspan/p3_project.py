"""P3 - project each policy onto the trio's published metrics (gate G5).

Substitutes the policy's recovered segments into the baseline live hypothesis, writes the
modified JSONL, and rescores it with the production evaluator.
"""
from __future__ import annotations

import json

from common import BASELINE, HERE, TRIO, dump_hyp, load_hyp, tbsa

from moss_transcribe_diarize.evaluation import Segment

KEYS = ("composite", "text_speaker_accuracy", "text_coverage", "wer")


def speaker_for(start: float, live_hyp) -> str:
    return min(live_hyp, key=lambda h: abs(h.start - start)).speaker


def trio_mean(per_case: dict) -> dict:
    return {k: round(sum(per_case[c][k] for c in TRIO) / len(TRIO), 6) for k in KEYS}


def main() -> None:
    rows = json.loads((HERE / "out/p2.json").read_text())
    trio_rows = [r for r in rows if r["tier"] == "trio"]
    policies = list(trio_rows[0]["policies"])

    live_hyp = {c: load_hyp(BASELINE / c / "live-hypothesis.jsonl") for c in TRIO}
    file_hyp = {c: load_hyp(BASELINE / c / "file-hypothesis.jsonl") for c in TRIO}
    base_live = {c: tbsa(c, live_hyp[c]) for c in TRIO}
    base_file = {c: tbsa(c, file_hyp[c]) for c in TRIO}
    live_agg, file_agg = trio_mean(base_live), trio_mean(base_file)
    gaps = {
        "text_coverage": file_agg["text_coverage"] - live_agg["text_coverage"],
        "wer": live_agg["wer"] - file_agg["wer"],
        "composite": file_agg["composite"] - live_agg["composite"],
        "text_speaker_accuracy": file_agg["text_speaker_accuracy"] - live_agg["text_speaker_accuracy"],
    }

    out = {"file": file_agg, "live": live_agg, "gaps": gaps, "policies": {}}
    print(f"{'arm/policy':28s} {'composite':>10s} {'tsa':>8s} {'coverage':>9s} {'wer':>8s}   {'closes cov':>10s} {'closes wer':>10s}")
    print(f"{'file (target)':28s} {file_agg['composite']:10.4f} {file_agg['text_speaker_accuracy']:8.4f} {file_agg['text_coverage']:9.4f} {file_agg['wer']:8.4f}")
    print(f"{'live (baseline)':28s} {live_agg['composite']:10.4f} {live_agg['text_speaker_accuracy']:8.4f} {live_agg['text_coverage']:9.4f} {live_agg['wer']:8.4f}")

    for name in policies:
        per_case = {}
        for case in TRIO:
            segs = list(live_hyp[case])
            for r in trio_rows:
                if r["case"] != case:
                    continue
                offset = r["start_sample"] / 16000.0
                for s0, s1, _spk, text in r["policies"][name]["segments"]:
                    if not text.strip():
                        continue
                    start, end = offset + s0, offset + s1
                    segs.append(Segment(round(start, 2), round(end, 2), speaker_for(start, live_hyp[case]), text))
            dump_hyp(HERE / f"out/hyp/{name}/{case}-live-hypothesis.jsonl", segs)
            per_case[case] = tbsa(case, segs)
        agg = trio_mean(per_case)
        cov = agg["text_coverage"] - live_agg["text_coverage"]
        wer = live_agg["wer"] - agg["wer"]
        comp = agg["composite"] - live_agg["composite"]
        out["policies"][name] = {
            "trio": agg,
            "per_case": per_case,
            "delta": {"text_coverage": cov, "wer": wer, "composite": comp},
            "gap_closed_pct": {
                "text_coverage": 100 * cov / gaps["text_coverage"],
                "wer": 100 * wer / gaps["wer"],
                "composite": 100 * comp / gaps["composite"],
            },
            "extra_requests": sum(r["policies"][name]["extra_requests"] for r in trio_rows),
            "extra_audio_s": round(sum(r["policies"][name]["extra_audio_s"] for r in trio_rows), 2),
        }
        print(
            f"{name:28s} {agg['composite']:10.4f} {agg['text_speaker_accuracy']:8.4f} {agg['text_coverage']:9.4f} "
            f"{agg['wer']:8.4f}   {100*cov/gaps['text_coverage']:9.1f}% {100*wer/gaps['wer']:9.1f}%"
        )

    (HERE / "out/p3.json").write_text(json.dumps(out, indent=1))
    print(f"\ntrio gaps: coverage {gaps['text_coverage']:.4f}  wer {gaps['wer']:.4f}  composite {gaps['composite']:.4f}")


if __name__ == "__main__":
    main()
