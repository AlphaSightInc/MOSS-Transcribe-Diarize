"""Merge two completed opposite-order H1 quality passes without rescoring.

Usage: python merge_quality_passes.py --pass1 <quality-out> --pass2 <quality-out> --out <new-dir>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from moss_transcribe_diarize.phase2_acceptance import QUALITY_CASE_IDS
from moss_transcribe_diarize.phase2_acceptance_external import _quality_projection

from run_quality import CORPUS, write_json


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cases(rows: list[dict], pass_number: int, order: list[str]) -> None:
    expected = [(case_id, pass_number) for case_id in (
        order if pass_number == 1 else reversed(order)
    )]
    actual = [(row["case_id"], row["pass"]) for row in rows]
    if actual != expected:
        raise ValueError(f"pass {pass_number} is not the frozen ordered six-case population")


def merge(pass1: Path, pass2: Path, out: Path) -> None:
    if out.exists():
        raise ValueError("--out must be a new directory")
    quality = [_read(path / "pass-content-free-metrics.json") for path in (pass1, pass2)]
    timed = [_read(path / "h1-timed-segments.json") for path in (pass1, pass2)]
    engines = [_read(path / "engine-diagnostics.json") for path in (pass1, pass2)]
    manifest = quality[0]["corpus_manifest_sha256"]
    order = [item["case_id"] for item in _read(CORPUS / "corpus-manifest.json")["cases"]]
    if len(order) != 6 or set(order) != QUALITY_CASE_IDS:
        raise ValueError("local frozen case manifest changed")
    for index, (q, t, e) in enumerate(zip(quality, timed, engines), start=1):
        if q["corpus_manifest_sha256"] != manifest or t["corpus_manifest_sha256"] != manifest:
            raise ValueError("pass corpus manifests disagree")
        if t["schema"] != "h1-timed-segments.v1":
            raise ValueError("timed sidecar schema changed")
        for rows in (q["per_case"], t["cases"], e["cases"]):
            _cases(rows, index, order)
    projected = _quality_projection(
        quality[0]["per_case"] + quality[1]["per_case"],
        corpus_manifest_sha256=manifest,
    )
    projected["source_passes"] = [str(pass1.resolve()), str(pass2.resolve())]
    for index, source in enumerate((pass1, pass2), start=1):
        for case_id in QUALITY_CASE_IDS:
            case_dir = source / f"pass-{index}" / case_id
            if not all((case_dir / name).is_file() for name in (
                "replay-manifest.json", "latency.json", "timed-segments.json"
            )):
                raise ValueError(f"pass {index} case {case_id} lacks a replay receipt")
    out.mkdir(parents=True)
    write_json(out / "content-free-metrics.json", projected)
    write_json(out / "h1-timed-segments.json", {
        "schema": "h1-timed-segments.v1", "corpus_manifest_sha256": manifest,
        "cases": timed[0]["cases"] + timed[1]["cases"],
    })
    engine_rows = engines[0]["cases"] + engines[1]["cases"]
    calls = sum(sum(row["engine_diagnostics"].get("calls_by_kind", {}).values()) for row in engine_rows)
    anomalies = {name: sum(row["engine_diagnostics"].get("timing_anomalies", {}).get(name, 0)
                           for row in engine_rows) for name in ("clamped", "dropped")}
    costs = [row["engine_diagnostics"].get("cost_usd") for row in engine_rows]
    write_json(out / "engine-diagnostics.json", {
        "cases": engine_rows, "total_calls": calls, "timing_anomalies": anomalies,
        "anomalies_per_call": {name: value / calls if calls else None for name, value in anomalies.items()},
        "known_cost_usd": sum(value for value in costs if isinstance(value, (int, float))),
        "cost_complete": all(isinstance(value, (int, float)) for value in costs),
    })
    for index, source in enumerate((pass1, pass2), start=1):
        for case_id in QUALITY_CASE_IDS:
            target = out / f"pass-{index}" / case_id
            target.mkdir(parents=True)
            for name in ("replay-manifest.json", "latency.json", "timed-segments.json"):
                shutil.copy2(source / f"pass-{index}" / case_id / name, target / name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pass1", required=True, type=Path)
    parser.add_argument("--pass2", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    merge(args.pass1, args.pass2, args.out)


if __name__ == "__main__":
    main()
