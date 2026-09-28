"""PROTOTYPE — four fresh accept6 draws plus two Lex30m draws; public audio only.

Run once (resumes from per-draw raw JSON):
  PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
      prototypes/gemini-live/window/variance_probe.py
Canonical Gemini cache is never selected for writes.
"""
from __future__ import annotations

import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
sys.path.insert(0, str(HERE.parent / "continuity"))
sys.path.insert(0, str(HERE.parent / "harness"))
import gemini_common as gc  # noqa: E402
from corpus import clips  # noqa: E402
from h1_offline import score_case  # noqa: E402
from measure import embedding_intervals  # noqa: E402
from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder  # noqa: E402
from score import score  # noqa: E402
from final_policy import MODEL, SELECTION, identity_diagnostics, merge_map, unit  # noqa: E402

EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P53")
RAW = EVIDENCE / "variance-raw"
DRAWS = EVIDENCE / "variance-draws"
SUMMARY = EVIDENCE / "variance-summary.json"
STATUS = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/status/PANE-5.3-STATUS.md")
CAP = 3.0
SELECTION_EXPECTED = {"tau": 0.65, "gap_s": 2.0, "constraint": True, "order": "single"}


def stamp(message: str) -> None:
    row = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} VARIANCE {message}"
    with STATUS.open("a") as out:
        out.write(row + "\n")
    print(row, flush=True)


def receipt_path(clip_id: str, draw: int) -> Path:
    return DRAWS / clip_id.replace(":", "__") / f"draw-{draw}.json"


def raw_result(clip_id: str, draw: int, samples: np.ndarray):
    folder = RAW / clip_id.replace(":", "__") / f"draw-{draw}"
    files = list(folder.glob("*/*.json"))
    if len(files) > 1:
        raise RuntimeError(f"multiple raw responses for one draw: {folder}")
    if files:
        return gc._parse(json.loads(files[0].read_text()), cached=True), files[0], "recovered"
    folder.mkdir(parents=True, exist_ok=True)
    gc.CACHE_DIR = folder
    result = gc.diarize_window(samples, use_cache=False, max_attempts=3, ledger_lane="P53-variance")
    files = list(folder.glob("*/*.json"))
    if len(files) != 1:
        raise RuntimeError(f"expected one raw response in {folder}; got {len(files)}")
    return result, files[0], "fresh"


def score_draw(c, draw: int, embedder, policy: dict, spent: float) -> dict:
    samples = gc.read_wav(c.audio)
    duration = len(samples) / gc.SAMPLE_RATE
    if spent + duration * .0002 >= CAP:
        raise RuntimeError(f"conservative spend guard: ${spent:.4f} plus {duration:.0f}s")
    result, raw, source = raw_result(c.clip_id, draw, samples)
    labels = sorted({w.speaker for w in result.words})
    vectors = {}
    for label in labels:
        intervals = embedding_intervals(0, [w.__dict__ for w in result.words], label)
        if intervals:
            encoded = embedder.embed_intervals(c.audio, intervals)
            vectors[label] = {"intervals": intervals, "vectors": encoded, "centroid": unit(encoded)}
    mapping, motifs = merge_map(result.words, vectors, **policy)
    pure_rows = gc.words_to_segments(result.words)
    policy_rows = gc.words_to_segments(result.words, speaker_map=mapping)
    if c.tier == "accept6":
        pure = score_case(c.clip_id, immediate=[], settled=[], final=pure_rows)["metrics"]["final"]
        selected = score_case(c.clip_id, immediate=[], settled=[], final=policy_rows)["metrics"]["final"]
    else:
        pure = score(c.reference_segments(), pure_rows)
        selected = score(c.reference_segments(), policy_rows)
    diagnostic = identity_diagnostics(c, result.words, mapping)
    return {"clip_id": c.clip_id, "tier": c.tier, "draw": draw, "raw_json": str(raw),
            "source": source, "audio_seconds": duration, "latency_seconds": result.latency_s,
            "cached": result.cached, "cost_usd": result.cost_usd(),
            "usage": result.usage, "timing_anomalies": result.timing_anomalies,
            "words": len(result.words), "input_labels": len(labels), "eligible_labels": len(vectors),
            "output_labels": len(set(mapping.values())), "motif_pairs": len(motifs),
            "mapping": mapping, "identity_diagnostic": diagnostic,
            "pure": {k: pure.get(k) for k in ("der", "wer", "reference_speech_der")},
            "selected": {k: selected.get(k) for k in ("der", "wer", "reference_speech_der")}}


def summarize(accept, long):
    per_case = {}
    for cid, rows in accept.items():
        per_case[cid] = {}
        for arm in ("pure", "selected"):
            vals = [r[arm]["der"] for r in rows]
            per_case[cid][arm] = {"mean": float(np.mean(vals)), "min": min(vals), "max": max(vals),
                                  "draws": vals}
    macro_draws = []
    cases = list(accept)
    for i in range(4):
        macro_draws.append({"draw": i+1, **{arm: float(np.mean([accept[c][i][arm]["der"] for c in cases]))
                                             for arm in ("pure", "selected")}})
    combinations = {}
    for arm in ("pure", "selected"):
        vals = [float(np.mean(v)) for v in itertools.product(*[[r[arm]["der"] for r in accept[c]] for c in cases])]
        combinations[arm] = {"n": len(vals), "mean": float(np.mean(vals)), "min": min(vals),
                             "max": max(vals), "passing": sum(v <= .110 for v in vals),
                             "fraction_at_or_below_0_110": sum(v <= .110 for v in vals)/len(vals)}
    long_summary = {arm: {"draws": [r[arm]["der"] for r in long],
                          "mean": float(np.mean([r[arm]["der"] for r in long])),
                          "min": min(r[arm]["der"] for r in long),
                          "max": max(r[arm]["der"] for r in long)} for arm in ("pure", "selected")}
    return {"policy": SELECTION_EXPECTED, "accept6_case_order": cases,
            "per_case": per_case, "paired_macro_draws": macro_draws,
            "all_independent_combinations": combinations, "lex_bill_30m": long_summary,
            "spent_usd": sum(r["cost_usd"] for rows in list(accept.values())+[long] for r in rows),
            "provider_calls": sum(len(rows) for rows in list(accept.values())+[long])}


def main():
    policy = json.loads(SELECTION.read_text())
    if policy != SELECTION_EXPECTED:
        raise RuntimeError(f"frozen policy changed: {policy}")
    canonical = gc.CACHE_DIR
    selected = [c for c in clips() if c.tier == "accept6"]
    selected.sort(key=lambda c: c.clip_id)
    long = next(c for c in clips("long30m") if c.clip_id == "benchmark_30m:lex_bill_ackman")
    plan = [(c, i) for i in range(1, 5) for c in selected] + [(long, i) for i in range(1, 3)]
    done = sorted(DRAWS.glob("*/draw-*.json"))
    spent = sum(json.loads(p.read_text())["cost_usd"] for p in done)
    stamp(f"START planned={len(plan)} completed={len(done)} spent=${spent:.4f} canonical_cache={canonical}")
    embedder = _OnnxWeSpeakerEmbedder(MODEL, device="cpu")
    for c, draw in plan:
        path = receipt_path(c.clip_id, draw)
        if path.exists():
            continue
        try:
            receipt = score_draw(c, draw, embedder, policy, spent)
        except Exception as exc:
            stamp(f"ERROR {c.clip_id} draw={draw} {type(exc).__name__}: {str(exc)[:220]}")
            raise
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt, indent=2, default=str) + "\n")
        spent += receipt["cost_usd"]
        stamp(f"DRAW {c.clip_id} {draw}/{'4' if c.tier == 'accept6' else '2'} "
              f"DER={receipt['pure']['der']:.6f}->{receipt['selected']['der']:.6f} "
              f"labels={receipt['input_labels']}->{receipt['output_labels']} "
              f"anomaly={receipt['timing_anomalies']} source={receipt['source']} "
              f"call_cost=${receipt['cost_usd']:.4f} spent=${spent:.4f}")
    gc.CACHE_DIR = canonical
    accept = {c.clip_id: [json.loads(receipt_path(c.clip_id, i).read_text()) for i in range(1,5)] for c in selected}
    long_rows = [json.loads(receipt_path(long.clip_id, i).read_text()) for i in range(1,3)]
    summary = summarize(accept, long_rows)
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    stamp(f"COMPLETE 26/26 fresh-draw receipts, spend=${summary['spent_usd']:.4f}; "
          f"paired selected macro={[round(x['selected'],6) for x in summary['paired_macro_draws']]}; "
          f"all combinations pass={summary['all_independent_combinations']['selected']['passing']}/4096")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
