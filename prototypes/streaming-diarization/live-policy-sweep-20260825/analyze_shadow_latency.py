#!/usr/bin/env python3
"""Derive shadow-owned word availability ages from retained decodes; issue no inference."""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("live_policy_latency", HERE / "moss_sweep.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load moss_sweep.py")
moss = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = moss
SPEC.loader.exec_module(moss)
MODEL = "OpenMOSS-Team/MOSS-Transcribe-Diarize"


class NoInference:
    def transcribe(self, *_args, **_kwargs):
        raise RuntimeError("latency analysis attempted inference")


def distribution(values: list[float]) -> dict:
    values = sorted(values)
    def q(fraction: float):
        if not values:
            return None
        position = (len(values) - 1) * fraction
        lo, hi = int(position), min(int(position) + 1, len(values) - 1)
        return values[lo] + (values[hi] - values[lo]) * (position - lo)
    return {
        "count": len(values),
        "mean": statistics.mean(values) if values else None,
        "p50": q(.5),
        "p95": q(.95),
        "max": max(values) if values else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--moss-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    corpus, root = args.corpus.resolve(), args.moss_root.resolve()
    all_ages = {"lexical": [], "stable_anchor": []}
    cases = []
    for pass_name in ("A", "B"):
        cache = root / "shadow-cache" / ("pass-A.json" if pass_name == "A" else "pass-B-recovery.json")
        decoder = moss.bench.Decoder(runner=NoInference(), model=MODEL, cache_path=cache)
        for case_id in moss.CASE_ORDER:
            actual_dir = (
                root / "replacement-pass-B-mono/actual"
                if pass_name == "B" and case_id == "mono_javier_intro_50s"
                else root / f"pass-{pass_name}" / case_id / "actual"
            )
            case_dir = corpus / case_id
            facts = moss.surface.wav_facts(case_dir / "audio.wav")
            pcm = moss.bench.read_pcm(case_dir / "audio.wav")
            with tempfile.TemporaryDirectory(prefix="moss-latency-cache-only-") as scratch:
                decoded = moss.decode_geometry(
                    pcm=pcm,
                    audio_sha=facts["wav_sha256"],
                    duration=facts["duration_seconds"],
                    geometry=(15.0, 10.0),
                    decoder=decoder,
                    scratch=Path(scratch),
                )
            captures = {
                row["surface"]: row
                for row in (json.loads(line) for line in (actual_dir / "snapshots.jsonl").read_text(encoding="utf-8").splitlines())
            }
            session = captures["pre_stop_settled"]["snapshot"]["session"]
            base_segments = list(moss.lsa._hypothesis_from_committed(session, corpus_start_sample=0, corpus_duration_sec=facts["duration_seconds"]))
            base_rows = moss.bench.word_rows(
                [moss.Segment(row.start, row.end, row.speaker, row.text) for row in base_segments], "base"
            )
            word_rows = [
                moss.rolling.word_rows_weighted(window["segments"], window["index"], lambda token: float(len(token)))
                for window in decoded
            ]
            schedule = moss.schedule(decoded)
            completion = {row["window"]: row["completion_seconds"] for row in schedule["windows"]}
            lexical, _ = moss.lexical_stitch(decoded, word_rows, base_rows)
            stable, _ = moss.stable_anchor_stitch(decoded, word_rows, base_rows)
            row = {"pass": pass_name, "case_id": case_id, "policies": {}}
            for name, merged in (("lexical", lexical), ("stable_anchor", stable)):
                ages = []
                for word in merged:
                    source = word["src"]
                    if source == "base" or (isinstance(source, (list, tuple)) and source[0] == "base"):
                        continue
                    window_index = int(source[0])
                    ages.append(max(0.0, completion[window_index] - float(word["mid"])))
                row["policies"][name] = distribution(ages)
                all_ages[name].extend(ages)
            cases.append(row)
        accounting = decoder.take_accounting()
        if accounting["fresh_requests"] != 0:
            raise RuntimeError(f"pass {pass_name} latency analysis issued inference")
    payload = {
        "schema": "moss-live-policy-shadow-latency.v1",
        "definition": "completion clock minus selected shadow-owned word midpoint; includes the 15-second audio accumulation and measured decode wall; base-tail words excluded",
        "limitations": "availability age is not browser paint and not provisional-to-correction age; it includes unchanged as well as corrected shadow-owned words",
        "aggregate": {name: distribution(values) for name, values in all_ages.items()},
        "cases": cases,
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload["aggregate"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
