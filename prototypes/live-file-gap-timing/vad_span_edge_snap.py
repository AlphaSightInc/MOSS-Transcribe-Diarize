"""PROTOTYPE -- THROWAWAY. H5 phase 2: span-edge timestamp correction for live mode.

Question: live mode emits per-span model timestamps from ~2.5s isolated decodes.
Those segments under-cover their span (trio mean 51.2s emitted of 60.0s of span time,
vs 54.6s for the file arm). Does snapping segment edges to webrtcvad speech boundaries
inside each span recover the live-vs-file TBSA/TSA/DER gap -- WITHOUT touching the text?

Method: for every committed span, run webrtcvad over that span's PCM, then re-lay the
span's emitted segments so they tile exactly the span's VAD speech, in order,
proportional to their original emitted durations. Text, speaker labels and token order
are untouched, so WER is invariant by construction (asserted below).

Arms compared (trio mean):
  live_baseline   as scored today
  live_vadsnap    this prototype, per webrtcvad aggressiveness 0..3
  live_spanfill   naive ceiling: tile the WHOLE span, ignoring silence
  file_baseline   the arm we are trying to catch
  degenerate      one segment [0,60] labelled S01 with the text "xx" -- the metric floor

Run:  .venv/bin/python prototypes/live-file-gap-timing/vad_span_edge_snap.py
"""
from __future__ import annotations

import json
import statistics
import sys
import wave
from pathlib import Path

import webrtcvad

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize import live_speaker_accuracy as lsa  # noqa: E402
from moss_transcribe_diarize.evaluation import (  # noqa: E402
    Segment,
    _segment_order,
    calculate_diarization,
    calculate_tbsa,
)

ARTIFACTS = Path(
    "/private/tmp/claude-501/-Users-gao-Desktop-AI-Projects-Github-Projects-"
    "MOSS-Transcribe-Diarize/bd3632af-da27-408f-8e03-ecd56a586e8d/scratchpad/"
    "remeasure-20260824T160130"
)
SAMPLES = REPO / "prototypes/streaming-diarization/data/real/benchmark_diarization_1min/samples"
TRIO = ["lex_bill_ackman", "lex_javier_milei", "lex_keyu_jin"]
SR = 16000
FRAME_MS = 30
FRAME_SAMPLES = SR * FRAME_MS // 1000
MIN_SILENCE_MS = 200  # bridge shorter silences (intra-word / plosive gaps)
MIN_SPEECH_MS = 90    # drop shorter blips
CORPUS = 60.0


# ------------------------------------------------------------------ loading
def load_jsonl(path: Path) -> list[Segment]:
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            out.append(Segment(float(r["start"]), float(r["end"]), r["speaker"], r["text"]))
    return out


def load_spans(case: str) -> list[dict]:
    trace = ARTIFACTS / case / "live/run-001/trace.jsonl"
    snap = None
    for line in trace.read_text().splitlines():
        e = json.loads(line)
        if e.get("kind") == "terminal":
            snap = e["snapshot"]
    spans = []
    for c in snap["session"]["committed"]:
        ss, es = int(c["start_sample"]), int(c["end_sample"])
        txt = c.get("revised_transcript") if c.get("revised_transcript") is not None else c.get("transcript")
        segs = list(lsa._span_segments(txt, sample_count=es - ss)) if (txt or "").strip() else []
        spans.append(
            {
                "span_id": c["span_id"],
                "s0": ss,
                "s1": es,
                "base": ss / SR,
                "dur": (es - ss) / SR,
                "segs": [s for s in segs if s.end > s.start],
            }
        )
    return spans


def load_pcm(case: str) -> bytes:
    with wave.open(str(SAMPLES / case / "audio.wav")) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, SR)
        return w.readframes(w.getnframes())


# ---------------------------------------------------------------------- VAD
def vad_speech(pcm: bytes, aggressiveness: int) -> list[tuple[float, float]]:
    """Speech intervals over the whole corpus, in seconds."""
    vad = webrtcvad.Vad(aggressiveness)
    flags = []
    step = FRAME_SAMPLES * 2
    for i in range(0, len(pcm) - step + 1, step):
        flags.append(vad.is_speech(pcm[i : i + step], SR))
    raw = []
    run = None
    for i, f in enumerate(flags):
        if f and run is None:
            run = i
        elif not f and run is not None:
            raw.append((run, i))
            run = None
    if run is not None:
        raw.append((run, len(flags)))
    fr = FRAME_MS / 1000.0
    iv = [(a * fr, b * fr) for a, b in raw]
    # bridge short silences
    merged: list[list[float]] = []
    for s, e in iv:
        if merged and s - merged[-1][1] <= MIN_SILENCE_MS / 1000.0:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged if (e - s) >= MIN_SPEECH_MS / 1000.0]


def clip(intervals: list[tuple[float, float]], lo: float, hi: float) -> list[tuple[float, float]]:
    out = []
    for s, e in intervals:
        a, b = max(s, lo), min(e, hi)
        if b > a:
            out.append((a, b))
    return out


def lay_over(intervals: list[tuple[float, float]], weights: list[float]) -> list[tuple[float, float]]:
    """Tile `intervals` (disjoint, ascending) with len(weights) consecutive slices whose
    lengths are proportional to `weights`."""
    total_iv = sum(e - s for s, e in intervals)
    total_w = sum(weights)
    if total_iv <= 0 or total_w <= 0:
        return []
    want = [total_iv * w / total_w for w in weights]
    out: list[tuple[float, float]] = []
    idx, cur = 0, intervals[0][0] if intervals else 0.0
    for w in want:
        need = w
        seg_lo, seg_hi = None, None
        while need > 1e-9 and idx < len(intervals):
            s, e = intervals[idx]
            cur = max(cur, s)
            take = min(need, e - cur)
            if take <= 1e-9:
                idx += 1
                if idx < len(intervals):
                    cur = intervals[idx][0]
                continue
            if seg_lo is None:
                seg_lo = cur
            cur += take
            seg_hi = cur
            need -= take
            if cur >= e - 1e-9:
                idx += 1
                if idx < len(intervals):
                    cur = intervals[idx][0]
        out.append((seg_lo, seg_hi) if seg_lo is not None and seg_hi > seg_lo else (0.0, 0.0))
    return out


# ------------------------------------------------------------- arm builders
def vadsnap(spans: list[dict], speech: list[tuple[float, float]]) -> list[Segment]:
    out = []
    for sp in spans:
        if not sp["segs"]:
            continue
        iv = clip(speech, sp["base"], sp["base"] + sp["dur"])
        w = [s.end - s.start for s in sp["segs"]]
        slices = lay_over(iv, w) if iv else []
        for k, s in enumerate(sp["segs"]):
            if k < len(slices) and slices[k][1] > slices[k][0]:
                a, b = slices[k]
            else:  # VAD found no speech in this span: keep the model's own times
                a, b = sp["base"] + s.start, sp["base"] + s.end
            a, b = max(0.0, a), min(CORPUS, b)
            if b > a:
                out.append(Segment(a, b, s.speaker, s.text))
    out.sort(key=_segment_order)
    return out


def spanfill(spans: list[dict]) -> list[Segment]:
    out = []
    for sp in spans:
        if not sp["segs"]:
            continue
        w = [s.end - s.start for s in sp["segs"]]
        tot = sum(w)
        cur = sp["base"]
        for s, wi in zip(sp["segs"], w):
            width = sp["dur"] * wi / tot
            a, b = max(0.0, cur), min(CORPUS, cur + width)
            if b > a:
                out.append(Segment(a, b, s.speaker, s.text))
            cur += width
    out.sort(key=_segment_order)
    return out


def score(ref: list[Segment], hyp: list[Segment]) -> dict:
    t = calculate_tbsa(ref, hyp)
    d = calculate_diarization(ref, hyp)
    return {
        "tbsa": t["composite"],
        "tsa": t["text_speaker_accuracy"],
        "cov": t["text_coverage"],
        "wer": t["wer"],
        "der": d["der"],
        "secs": round(sum(s.duration for s in hyp), 2),
    }


# ----------------------------------------------------------------- main
def main() -> int:
    per_case: dict[str, dict] = {}
    for case in TRIO:
        ref = load_jsonl(SAMPLES / case / "reference.jsonl")
        live = load_jsonl(ARTIFACTS / case / "live-hypothesis.jsonl")
        file_ = load_jsonl(ARTIFACTS / case / "file-hypothesis.jsonl")
        spans = load_spans(case)
        pcm = load_pcm(case)

        arms = {
            "live_baseline": score(ref, live),
            "file_baseline": score(ref, file_),
            "live_spanfill": score(ref, spanfill(spans)),
            "degenerate_0_60": score(ref, [Segment(0.0, 60.0, "S01", "xx")]),
        }
        vad_secs = {}
        for a in (0, 1, 2, 3):
            speech = vad_speech(pcm, a)
            vad_secs[a] = round(sum(e - s for s, e in speech), 2)
            arms[f"live_vadsnap_a{a}"] = score(ref, vadsnap(spans, speech))
        per_case[case] = {"arms": arms, "vad_speech_seconds": vad_secs}

        # WER must be invariant under pure re-timing
        for k in [f"live_vadsnap_a{a}" for a in (0, 1, 2, 3)] + ["live_spanfill"]:
            assert abs(arms[k]["wer"] - arms["live_baseline"]["wer"]) < 1e-9, (case, k)

    order = [
        "file_baseline",
        "live_baseline",
        "live_vadsnap_a0",
        "live_vadsnap_a1",
        "live_vadsnap_a2",
        "live_vadsnap_a3",
        "live_spanfill",
        "degenerate_0_60",
    ]
    print(f"{'arm':18s} {'TBSA':>7s} {'dTBSA':>7s} {'TSA':>7s} {'cov':>7s} {'WER':>7s} {'DER':>7s} {'hyp_s':>7s}")
    base = statistics.fmean(per_case[c]["arms"]["live_baseline"]["tbsa"] for c in TRIO)
    for arm in order:
        m = {k: round(statistics.fmean(per_case[c]["arms"][arm][k] for c in TRIO), 4) for k in ("tbsa", "tsa", "cov", "wer", "der", "secs")}
        print(
            f"{arm:18s} {m['tbsa']:7.4f} {m['tbsa']-base:+7.4f} {m['tsa']:7.4f} "
            f"{m['cov']:7.4f} {m['wer']:7.4f} {m['der']:7.4f} {m['secs']:7.2f}"
        )
    print("\nVAD speech seconds over the 60s corpus (of 60.0 labelled speech in the reference):")
    for c in TRIO:
        print(f"  {c:20s} {per_case[c]['vad_speech_seconds']}")
    out = Path(__file__).parent / "vad_span_edge_snap.results.json"
    out.write_text(json.dumps(per_case, indent=1) + "\n")
    print(f"\nWROTE {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
