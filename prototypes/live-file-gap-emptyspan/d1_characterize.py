"""D1 - locate every empty span in the baseline traces and characterize it.

Writes spans/<case>-span<NN>.wav for each empty span and out/d1.json with the numbers.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from common import (
    BASELINE,
    HERE,
    SECONDARY,
    SR,
    TRIO,
    load_hyp,
    load_reference,
    load_spans,
    read_pcm,
    rms_dbfs,
    slice_pcm,
    vad_speech_ratio,
    write_wav,
)


def toks(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def main() -> None:
    report = {"cases": {}, "totals": {}}
    all_empty = []
    for case in TRIO + SECONDARY:
        spans = load_spans(case)
        pcm = read_pcm(case)
        ref = load_reference(case)
        file_hyp = load_hyp(BASELINE / case / "file-hypothesis.jsonl")
        live_hyp = load_hyp(BASELINE / case / "live-hypothesis.jsonl")
        rows = []
        for sp in spans:
            spcm = slice_pcm(pcm, sp.start_sample, sp.end_sample)
            rms, peak = rms_dbfs(spcm)
            row = {
                "span_id": sp.span_id,
                "start_s": round(sp.start_s, 3),
                "end_s": round(sp.end_s, 3),
                "dur_s": round(sp.dur_s, 3),
                "freeze_reason": sp.reason,
                "empty_reason": sp.empty_reason,
                "rms_dbfs": round(rms, 2),
                "peak_dbfs": round(peak, 2),
                "vad_speech_ratio": round(vad_speech_ratio(spcm), 4),
                "transcript_chars": len(sp.transcript),
            }
            if sp.empty_reason is not None:
                # reference tokens the evaluator credits to this window
                lost_metric_tokens = 0.0
                ref_text_bits = []
                for r in ref:
                    ov = overlap(sp.start_s, sp.end_s, r.start, r.end)
                    if ov <= 0:
                        continue
                    lost_metric_tokens += len(toks(r.text)) * min(ov / (r.end - r.start), 1.0)
                    ref_text_bits.append(r.speaker)
                # empirical words: file-arm hypothesis words landing in the window
                file_words = []
                for h in file_hyp:
                    ov = overlap(sp.start_s, sp.end_s, h.start, h.end)
                    if ov <= 0:
                        continue
                    w = toks(h.text)
                    if not w:
                        continue
                    frac0 = max(0.0, (sp.start_s - h.start) / (h.end - h.start))
                    frac1 = min(1.0, (sp.end_s - h.start) / (h.end - h.start))
                    i0, i1 = int(round(frac0 * len(w))), int(round(frac1 * len(w)))
                    file_words.extend(w[i0:i1])
                # is the window actually a hole in the live hypothesis?
                live_cover = sum(
                    overlap(sp.start_s, sp.end_s, h.start, h.end) for h in live_hyp
                )
                row.update(
                    {
                        "lost_metric_tokens": round(lost_metric_tokens, 3),
                        "ref_speakers": sorted(set(ref_text_bits)),
                        "file_arm_words_in_window": file_words,
                        "file_arm_word_count": len(file_words),
                        "live_hyp_coverage_s": round(live_cover, 3),
                        "wav": f"spans/{case}-span{sp.span_id:02d}.wav",
                    }
                )
                write_wav(HERE / "spans" / f"{case}-span{sp.span_id:02d}.wav", spcm)
                all_empty.append((case, row))
            rows.append(row)
        nonempty = [r for r in rows if r["empty_reason"] is None]
        empty = [r for r in rows if r["empty_reason"] is not None]
        report["cases"][case] = {
            "spans": len(rows),
            "empty": len(empty),
            "freeze_reasons": {},
            "neighbor_stats": {
                "rms_dbfs_mean": round(sum(r["rms_dbfs"] for r in nonempty) / max(len(nonempty), 1), 2),
                "rms_dbfs_min": round(min((r["rms_dbfs"] for r in nonempty), default=0), 2),
                "vad_ratio_mean": round(sum(r["vad_speech_ratio"] for r in nonempty) / max(len(nonempty), 1), 4),
                "vad_ratio_min": round(min((r["vad_speech_ratio"] for r in nonempty), default=0), 4),
                "dur_s_mean": round(sum(r["dur_s"] for r in nonempty) / max(len(nonempty), 1), 3),
            },
            "rows": rows,
        }
        for r in rows:
            report["cases"][case]["freeze_reasons"][r["freeze_reason"]] = (
                report["cases"][case]["freeze_reasons"].get(r["freeze_reason"], 0) + 1
            )

    trio_empty = [(c, r) for c, r in all_empty if c in TRIO]
    report["totals"] = {
        "trio_spans": sum(report["cases"][c]["spans"] for c in TRIO),
        "trio_empty_spans": len(trio_empty),
        "trio_empty_seconds": round(sum(r["dur_s"] for _, r in trio_empty), 3),
        "trio_lost_metric_tokens": round(sum(r["lost_metric_tokens"] for _, r in trio_empty), 3),
        "trio_file_arm_words": sum(r["file_arm_word_count"] for _, r in trio_empty),
        "trio_ref_tokens": {
            c: len(toks(" ".join(s.text for s in load_reference(c)))) for c in TRIO
        },
        "secondary_empty_spans": len(all_empty) - len(trio_empty),
    }
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out/d1.json").write_text(json.dumps(report, indent=1))

    print("=== EMPTY SPANS ===")
    for case, r in all_empty:
        tier = "trio" if case in TRIO else "secondary"
        print(
            f"{case:22s} span{r['span_id']:02d} [{r['start_s']:6.2f},{r['end_s']:6.2f}] "
            f"{r['dur_s']:.2f}s freeze={r['freeze_reason']:14s} empty={r['empty_reason']} "
            f"rms={r['rms_dbfs']:7.2f}dBFS peak={r['peak_dbfs']:7.2f} vad={r['vad_speech_ratio']:.3f} "
            f"lost_metric_tok={r['lost_metric_tokens']:.2f} file_words={r['file_arm_word_count']} ({tier})"
        )
        print(f"    file-arm words: {' '.join(r['file_arm_words_in_window'])}")
    print()
    for case in TRIO + SECONDARY:
        c = report["cases"][case]
        print(
            f"{case:22s} spans={c['spans']:3d} empty={c['empty']} "
            f"neighbors rms_mean={c['neighbor_stats']['rms_dbfs_mean']:.2f} "
            f"rms_min={c['neighbor_stats']['rms_dbfs_min']:.2f} "
            f"vad_mean={c['neighbor_stats']['vad_ratio_mean']:.3f} "
            f"vad_min={c['neighbor_stats']['vad_ratio_min']:.3f} "
            f"freeze={c['freeze_reasons']}"
        )
    print()
    print(json.dumps(report["totals"], indent=1))


if __name__ == "__main__":
    main()
