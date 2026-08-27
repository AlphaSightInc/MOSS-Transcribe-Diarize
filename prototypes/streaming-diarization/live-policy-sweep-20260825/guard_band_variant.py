#!/usr/bin/env python3
"""Owner-proposed guard-band 15/7.5 rolling variant vs fresh 15/10 lexical.

Preregistration: PREREGISTRATION-guard-band.md (same directory). Reuses the sweep's own
machinery (moss_sweep align/lexical_stitch/project_and_group, bench Decoder/VllmRunner,
surface.score_surface) so every number is on the sweep's instrument. Offline shadow; no
production code touched; one decoder request in flight.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import moss_sweep as ms  # noqa: E402  (brings bench/rolling/surface/lsa/Segment with it)

bench = ms.bench
rolling = ms.rolling
surface = ms.surface
lsa = ms.lsa
Segment = ms.Segment

SR = ms.SAMPLE_RATE
GUARD = 2.5
OWNED = 10.0
STRIDE = 7.5
WINDOW = 15.0


def plan_guard_windows(duration: float) -> list[dict[str, Any]]:
    """W0 decodes [0, 12.5] owning [0, 10]; Wk decodes [7.5k-2.5, 7.5k+12.5] owning [7.5k, 7.5k+10]."""
    out = []
    index = 0
    while True:
        if index == 0:
            lo, hi = 0.0, OWNED + GUARD
            own_lo, own_hi = 0.0, OWNED
        else:
            own_lo = STRIDE * index
            own_hi = own_lo + OWNED
            lo, hi = own_lo - GUARD, own_hi + GUARD
        if hi > duration + 1e-9:
            break
        out.append({
            "index": index,
            "start_sample": int(round(lo * SR)),
            "end_sample": int(round(hi * SR)),
            "range": [lo, hi],
            "region": [own_lo, own_hi],
        })
        index += 1
    return out


def guard_stitch(
    windows: list[dict[str, Any]],
    window_rows: list[list[dict[str, Any]]],
    base_rows: list[dict[str, Any]],
    *,
    anchor: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Trim each window's words to its owned region; reconcile the 2.5 s owned-overlap."""
    if not windows:
        return list(base_rows), []
    merged: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for index, (window, fresh) in enumerate(zip(windows, window_rows)):
        own_lo, own_hi = window["region"]
        owned = [row for row in fresh if own_lo <= row["mid"] < own_hi]
        if index == 0:
            merged = list(owned)
            reports.append({"join": 0, "owned": [own_lo, own_hi], "decision": "first_window",
                            "words_taken": len(owned)})
            continue
        zone_lo, zone_hi = own_lo, windows[index - 1]["region"][1]  # 2.5 s owned-overlap
        left = [row for row in merged if zone_lo <= row["mid"] < zone_hi]
        right = [row for row in owned if zone_lo <= row["mid"] < zone_hi]
        cut = None
        decision = "zone_midpoint_fallback"
        if anchor:
            exact = [
                (i, j) for i, j in ms.align(left, right)
                if i is not None and j is not None
                and ms.norm(left[i]["word"]) == ms.norm(right[j]["word"])
                and abs(left[i]["mid"] - right[j]["mid"]) <= ms.DRIFT_LIMIT
            ]
            midpoint = (zone_lo + zone_hi) / 2
            best = min(
                exact,
                key=lambda pair: (
                    abs(((left[pair[0]]["mid"] + right[pair[1]]["mid"]) / 2) - midpoint),
                    abs(left[pair[0]]["mid"] - right[pair[1]]["mid"]),
                    pair,
                ),
                default=None,
            )
            if best is not None:
                left_anchor, right_anchor = left[best[0]], right[best[1]]
                left_pos = next(i for i, row in enumerate(merged) if row is left_anchor)
                right_pos = next(i for i, row in enumerate(owned) if row is right_anchor)
                merged = merged[: left_pos + 1] + owned[right_pos + 1 :]
                decision = "anchor_in_safe_zone"
                cut = (left_anchor["mid"] + right_anchor["mid"]) / 2
                reports.append({"join": index, "zone": [zone_lo, zone_hi],
                                "valid_anchors": len(exact), "decision": decision,
                                "anchor_word": left_anchor["word"], "cut_time": cut})
                continue
        cut = (zone_lo + zone_hi) / 2
        merged = [row for row in merged if row["mid"] < cut]
        merged.extend(row for row in owned if row["mid"] >= cut)
        reports.append({"join": index, "zone": [zone_lo, zone_hi], "decision": decision,
                        "cut_time": cut})
    covered_hi = windows[-1]["region"][1]
    merged.extend(row for row in base_rows if row["mid"] >= covered_hi)
    return merged, reports


def main() -> int:
    out_root = Path(sys.argv[1] if len(sys.argv) > 1 else
                    ms.REPO / "evidence/live-policy-sweep-20260825/guard-band-variant")
    corpus = ms.REPO / "evidence/live-policy-sweep-20260825/corpus"
    actual_root = ms.REPO / "evidence/live-policy-sweep-20260825/moss/pass-A"
    out_root.mkdir(parents=True, exist_ok=False)

    model = bench.discover_model("http://127.0.0.1:18000/v1", 30.0)
    runner = bench.VllmRunner(base_url="http://127.0.0.1:18000/v1", model=model,
                              api_key=None, timeout=180.0)
    decoder = bench.Decoder(runner=runner, model=model,
                            cache_path=out_root / "decode-cache.json")

    results: dict[str, Any] = {"cases": {}, "model": model,
                               "preregistration": "PREREGISTRATION-guard-band.md"}
    with tempfile.TemporaryDirectory(prefix="guard-band-") as scratch_name:
        scratch = Path(scratch_name)
        # one discarded warm-up decode (campaign protocol)
        warm_case = corpus / ms.CASE_ORDER[0]
        warm_pcm = bench.read_pcm(warm_case / "audio.wav")
        warm_facts = surface.wav_facts(warm_case / "audio.wav")
        decoder.decode(pcm=warm_pcm, audio_sha="warmup-" + warm_facts["wav_sha256"],
                       start_sample=0, end_sample=SR * 4,
                       token_cap=ms.canonical_decode_token_cap(sample_count=SR * 4),
                       scratch=scratch)

        for case_id in ms.CASE_ORDER:
            case_dir = corpus / case_id
            case = surface.Case(case_id, case_dir, case_dir / "unused.jsonl")
            facts = surface.wav_facts(case.audio)
            duration = float(facts["duration_seconds"])
            pcm = bench.read_pcm(case.audio)

            captures = {
                row["surface"]: row
                for row in (json.loads(line) for line in
                            (actual_root / case_id / "actual/snapshots.jsonl")
                            .read_text(encoding="utf-8").splitlines())
            }
            session = captures["pre_stop_settled"]["snapshot"]["session"]
            base_segments = list(lsa._hypothesis_from_committed(
                session, corpus_start_sample=0, corpus_duration_sec=duration))
            base_rows = bench.word_rows(
                [Segment(r.start, r.end, r.speaker, r.text) for r in base_segments], "base")
            settled_rows = surface.transcript_rows(
                captures["pre_stop_settled"]["snapshot"], duration)
            timeline = bench.SpeakerTimeline(ms.as_segments(settled_rows))

            arms: dict[str, Any] = {}

            guard_windows = plan_guard_windows(duration)
            decoded_guard = rolling.decode_windows(
                pcm=pcm, audio_sha=facts["wav_sha256"], windows=guard_windows,
                decoder=decoder, scratch=scratch)
            rows_guard = [rolling.word_rows_weighted(
                w["segments"], w["index"], lambda t: float(len(t))) for w in decoded_guard]

            decoded_1510 = ms.decode_geometry(
                pcm=pcm, audio_sha=facts["wav_sha256"], duration=duration,
                geometry=(15.0, 10.0), decoder=decoder, scratch=scratch)
            rows_1510 = [rolling.word_rows_weighted(
                w["segments"], w["index"], lambda t: float(len(t))) for w in decoded_1510]

            for name, merged, report in (
                ("guard_anchor", *guard_stitch(decoded_guard, rows_guard, base_rows, anchor=True)),
                ("guard_mid", *guard_stitch(decoded_guard, rows_guard, base_rows, anchor=False)),
                ("15_10_lexical_fresh", *ms.lexical_stitch(decoded_1510, rows_1510, base_rows)),
            ):
                rows = ms.project_and_group(merged, timeline, duration)
                (out_root / case_id).mkdir(exist_ok=True)
                ms.dump_jsonl(out_root / case_id / f"{name}.jsonl", rows)
                arms[name] = {"scores": surface.score_surface(case, rows),
                              "stitch_report": report}

            results["cases"][case_id] = {
                "duration_seconds": duration,
                "arms": arms,
                "decode": {
                    "guard_requests": len(decoded_guard),
                    "guard_audio_seconds": sum(w["range"][1] - w["range"][0] for w in decoded_guard),
                    "guard_wall_seconds": sum(float(w["decode_seconds"]) for w in decoded_guard),
                    "15_10_requests": len(decoded_1510),
                    "15_10_audio_seconds": sum(w["range"][1] - w["range"][0] for w in decoded_1510),
                    "15_10_wall_seconds": sum(float(w["decode_seconds"]) for w in decoded_1510),
                },
            }
            g = arms["guard_anchor"]["scores"]; m = arms["guard_mid"]["scores"]
            l = arms["15_10_lexical_fresh"]["scores"]
            ms.log(f"{case_id}: guard_anchor={g['wer']:.4f} guard_mid={m['wer']:.4f} "
                   f"15/10lex_fresh={l['wer']:.4f}")

    macro = {}
    for arm in ("guard_anchor", "guard_mid", "15_10_lexical_fresh"):
        for metric in ("wer", "tbsa", "der", "matched_word_speaker_accuracy", "content_recall"):
            vals = [results["cases"][c]["arms"][arm]["scores"].get(metric)
                    for c in ms.CASE_ORDER]
            vals = [v for v in vals if v is not None]
            macro.setdefault(arm, {})[metric] = sum(vals) / len(vals) if vals else None
    results["macro"] = macro
    ms.dump(out_root / "results.json", results)
    print(json.dumps(macro, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
