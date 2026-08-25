"""P2 - measure every recovery policy on every discarded span.

Per policy per span: recovered oracle words, false additions, extra decode requests, extra
audio-seconds submitted, contended wall seconds. Request concurrency stays at 1.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

from common import (
    BASELINE,
    HERE,
    SECONDARY,
    SR,
    TRIO,
    load_hyp,
    load_spans,
    raw_decode,
    read_pcm,
    rms_dbfs,
    slice_pcm,
    vad_speech_ratio,
    write_wav,
)
from salvage import looks_like_refusal, salvage
from sim_spans import simulate

from moss_transcribe_diarize.transcript_parser import TranscriptSegment, parse_transcript

ALT_PROMPT = "Transcribe the audio into text with a start timestamp, speaker tag and end timestamp for each segment."


def toks(text: str) -> list[str]:
    return re.findall(r"[\w']+", (text or "").lower())


def trim_to_window(segs, w0: float, w1: float):
    """Keep the part of each segment inside [w0, w1], trimming words proportionally."""
    kept = []
    for s in segs:
        ov0, ov1 = max(s.start, w0), min(s.end, w1)
        if ov1 - ov0 <= 1e-6:
            continue
        words = s.text.split()
        dur = max(s.end - s.start, 1e-6)
        if not words:
            continue
        i0 = int(round(len(words) * (ov0 - s.start) / dur))
        i1 = int(round(len(words) * (ov1 - s.start) / dur))
        if i1 <= i0:
            i1 = min(len(words), i0 + 1)
        kept.append(TranscriptSegment(start=ov0, end=ov1, speaker=s.speaker, text=" ".join(words[i0:i1])))
    return kept


def score(oracle: str, segs) -> tuple[int, int, str]:
    hyp = toks(" ".join(s.text for s in segs))
    ref = toks(oracle)
    matcher = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
    matched = sum(b.size for b in matcher.get_matching_blocks())
    return matched, len(hyp) - matched, " ".join(hyp)


def build_inventory() -> list[dict]:
    """Every span whose decode the production parser discards, across all tiers measured."""
    inv = []
    for case in TRIO + SECONDARY:
        spans = load_spans(case)
        file_hyp = load_hyp(BASELINE / case / "file-hypothesis.jsonl")
        for i, sp in enumerate(spans):
            if sp.empty_reason is None:
                continue
            nxt = spans[i + 1] if i + 1 < len(spans) else None
            words = []
            for h in file_hyp:
                ov = max(0.0, min(sp.end_s, h.end) - max(sp.start_s, h.start))
                if ov <= 0:
                    continue
                w = h.text.split()
                if not w:
                    continue
                f0 = max(0.0, (sp.start_s - h.start) / (h.end - h.start))
                f1 = min(1.0, (sp.end_s - h.start) / (h.end - h.start))
                words.extend(w[int(round(f0 * len(w))) : int(round(f1 * len(w)))])
            inv.append(
                {
                    "case": case,
                    "tier": "trio" if case in TRIO else "secondary",
                    "span_id": sp.span_id,
                    "start_sample": sp.start_sample,
                    "end_sample": sp.end_sample,
                    "next_end_sample": nxt.end_sample if nxt else None,
                    "oracle": " ".join(words),
                }
            )
    # 3-minute tier: simulator-provoked discards (see p1_provoke_3min.py for the decode pass)
    p1 = HERE / "out/p1-lex_adam_frank.json"
    if p1.exists():
        data = json.loads(p1.read_text())
        rows = data["spans"]
        for i, r in enumerate(rows):
            if not r["live_would_be_empty"]:
                continue
            inv.append(
                {
                    "case": "lex_adam_frank",
                    "tier": "3min",
                    "span_id": r["span_id"],
                    "start_sample": int(round(r["start_s"] * SR)),
                    "end_sample": int(round(r["end_s"] * SR)),
                    "next_end_sample": int(round(rows[i + 1]["end_s"] * SR)) if i + 1 < len(rows) else None,
                    "oracle": "",  # verified digital silence: vad 0.000, rms floor
                }
            )
    return inv


def main() -> None:
    inventory = build_inventory()
    results = []
    for item in inventory:
        case, a, b = item["case"], item["start_sample"], item["end_sample"]
        pcm = read_pcm(case)
        total = len(pcm) // 2
        dur = (b - a) / SR
        spcm = slice_pcm(pcm, a, b)
        wav = HERE / "spans" / f"{case}-span{item['span_id']:02d}.wav"
        write_wav(wav, spcm)
        vad = vad_speech_ratio(spcm)
        rms, _peak = rms_dbfs(spcm)
        base = raw_decode(wav, sample_count=b - a)
        row = {
            **item,
            "dur_s": round(dur, 3),
            "vad": round(vad, 4),
            "rms_dbfs": round(rms, 2),
            "baseline_raw": base["stripped"],
            "policies": {},
        }

        def record(name, segs, extra_requests, extra_audio_s, wall_s, note=""):
            segs = [s for s in segs if s.text.strip()]
            rec_words, false_words, kept = score(item["oracle"], segs)
            row["policies"][name] = {
                "segments": [[round(s.start, 2), round(s.end, 2), s.speaker, s.text] for s in segs],
                "kept_text": kept,
                "recovered": rec_words,
                "false_additions": false_words,
                "extra_requests": extra_requests,
                "extra_audio_s": round(extra_audio_s, 3),
                "wall_s_contended": round(wall_s, 3),
                "note": note,
            }

        # --- P0 baseline -------------------------------------------------------------
        record("P0_baseline", [], 0, 0.0, 0.0, "commits empty transcript")
        # --- P1 salvage --------------------------------------------------------------
        sal = salvage(base["stripped"], duration_s=dur)
        record("P1_salvage", sal, 0, 0.0, 0.0, "no new request")
        gated = [] if vad < 0.5 else sal
        record("P1v_salvage_vad", gated, 0, 0.0, 0.0, f"vad={vad:.3f} gate=0.5")
        gated2 = [s for s in sal if not looks_like_refusal(s.text)] if vad >= 0.5 else []
        record("P1r_salvage_vad_norefusal", gated2, 0, 0.0, 0.0, "vad gate + refusal filter")

        # --- B1 leading context ------------------------------------------------------
        for label, lead in (("B1a_lead1.0", 1.0), ("B1b_lead2.5", 2.5)):
            s0 = max(0, a - int(round(lead * SR)))
            path = HERE / "spans" / f"{case}-span{item['span_id']:02d}-{label}.wav"
            write_wav(path, slice_pcm(pcm, s0, b))
            r = raw_decode(path, sample_count=b - s0)
            shift = (a - s0) / SR
            segs = [
                TranscriptSegment(s.start - shift, s.end - shift, s.speaker, s.text)
                for s in parse_transcript(r["stripped"])
            ]
            record(label, trim_to_window(segs, 0.0, dur), 1, (b - s0) / SR, r["elapsed_s"], f"lead={shift:.2f}s")
            path.unlink(missing_ok=True)

        # --- B2 prompt variant --------------------------------------------------------
        r = raw_decode(wav, sample_count=b - a, prompt=ALT_PROMPT)
        record("B2_altprompt", parse_transcript(r["stripped"]), 1, dur, r["elapsed_s"], "english instruction prompt")

        # --- B3 merge forward ----------------------------------------------------------
        if item["next_end_sample"]:
            b2 = min(total, item["next_end_sample"])
            path = HERE / "spans" / f"{case}-span{item['span_id']:02d}-B3.wav"
            write_wav(path, slice_pcm(pcm, a, b2))
            r = raw_decode(path, sample_count=b2 - a)
            segs = parse_transcript(r["stripped"])
            record("B3_mergeforward", trim_to_window(segs, 0.0, dur), 1, (b2 - a) / SR, r["elapsed_s"],
                   f"merged window {(b2-a)/SR:.2f}s")
            path.unlink(missing_ok=True)
        else:
            record("B3_mergeforward", [], 0, 0.0, 0.0, "no following span (session tail)")

        # --- B4 pad both sides ----------------------------------------------------------
        s0, s1 = max(0, a - int(0.25 * SR)), min(total, b + int(0.25 * SR))
        path = HERE / "spans" / f"{case}-span{item['span_id']:02d}-B4.wav"
        write_wav(path, slice_pcm(pcm, s0, s1))
        r = raw_decode(path, sample_count=s1 - s0)
        shift = (a - s0) / SR
        segs = [
            TranscriptSegment(s.start - shift, s.end - shift, s.speaker, s.text)
            for s in parse_transcript(r["stripped"])
        ]
        record("B4_pad0.25", trim_to_window(segs, 0.0, dur), 1, (s1 - s0) / SR, r["elapsed_s"], "+0.25s each side")
        path.unlink(missing_ok=True)

        results.append(row)
        print(
            f"{case:20s} span{item['span_id']:03d} [{a/SR:7.2f},{b/SR:7.2f}] {dur:.2f}s vad={vad:.3f} "
            f"oracle={len(toks(item['oracle']))}w"
        )
        for name, p in row["policies"].items():
            print(
                f"   {name:26s} rec={p['recovered']:2d} false={p['false_additions']:2d} "
                f"req=+{p['extra_requests']} audio=+{p['extra_audio_s']:5.2f}s -> {p['kept_text'][:72]!r}"
            )

    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out/p2.json").write_text(json.dumps(results, indent=1))

    names = list(results[0]["policies"])
    print("\n=== POLICY TOTALS ===")
    for tier in ("trio", "secondary", "3min", "ALL"):
        rows = [r for r in results if tier == "ALL" or r["tier"] == tier]
        print(f"\n-- {tier} ({len(rows)} discarded spans, oracle words={sum(len(toks(r['oracle'])) for r in rows)}) --")
        print(f"{'policy':26s} {'recovered':>9s} {'false':>6s} {'+req':>5s} {'+audio_s':>9s} {'wall_s':>8s}")
        for n in names:
            rec = sum(r["policies"][n]["recovered"] for r in rows)
            fal = sum(r["policies"][n]["false_additions"] for r in rows)
            req = sum(r["policies"][n]["extra_requests"] for r in rows)
            aud = sum(r["policies"][n]["extra_audio_s"] for r in rows)
            wall = sum(r["policies"][n]["wall_s_contended"] for r in rows)
            print(f"{n:26s} {rec:9d} {fal:6d} {req:5d} {aud:9.2f} {wall:8.2f}")


if __name__ == "__main__":
    main()
