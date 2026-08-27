#!/usr/bin/env python3
"""Replay reconciliation from the sweep's retained fresh decode cache, without new inference."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("live_policy_moss_sweep", HERE / "moss_sweep.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load moss_sweep.py")
moss = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = moss
SPEC.loader.exec_module(moss)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--moss-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    corpus, root, out = args.corpus.resolve(), args.moss_root.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    model = moss.bench.discover_model("http://127.0.0.1:18000/v1", 30.0)
    runner = moss.bench.VllmRunner(base_url="http://127.0.0.1:18000/v1", model=model, api_key=None, timeout=180.0)
    actual, shadows, cache_checks = [], [], []
    for pass_name in ("A", "B"):
        decoder = moss.bench.Decoder(runner=runner, model=model, cache_path=root / "shadow-cache" / f"pass-{pass_name}.json")
        ordered = moss.CASE_ORDER if pass_name == "A" else tuple(reversed(moss.CASE_ORDER))
        for case_id in ordered:
            actual_row = json.loads((root / f"pass-{pass_name}" / case_id / "actual/actual-result.json").read_text(encoding="utf-8"))
            actual.append({"pass": pass_name, **actual_row})
            shadow = moss.make_shadow(
                case_id=case_id,
                corpus=corpus,
                actual_dir=root / f"pass-{pass_name}" / case_id / "actual",
                shadow_dir=out / f"pass-{pass_name}" / case_id,
                decoder=decoder,
            )
            shadows.append({"pass": pass_name, **shadow})
        accounting = decoder.take_accounting()
        cache_checks.append({"pass": pass_name, **accounting})
        if accounting["fresh_requests"] != 0:
            raise RuntimeError(f"reconciliation replay unexpectedly issued inference: {accounting}")
    original = json.loads((root / "moss-results.json").read_text(encoding="utf-8"))
    checks = {
        **{key: value for key, value in original["checks"].items() if key != "production_10_10_differential"},
        "production_10_10_differential": all(row["differential_10_10"]["content_and_speaker_exact"] for row in shadows),
        "zero_new_inference_in_reconciliation_replay": all(row["fresh_requests"] == 0 for row in cache_checks),
    }
    payload = {
        "schema": "moss-live-policy-sweep.reconciled.v1",
        "source_result": str(root / "moss-results.json"),
        "policy_projection": "regroup retained word rows into decoded segments, then project each segment by session-timeline interval overlap",
        "original_fresh_decode_accounting": {
            pass_name: json.loads((root / f"pass-{pass_name}/shadow-accounting.json").read_text(encoding="utf-8"))
            for pass_name in ("A", "B")
        },
        "replay_cache_accounting": cache_checks,
        "denominator": original["denominator"],
        "actual": actual,
        "shadows": shadows,
        "aggregate": moss.aggregate(actual, shadows),
        "checks": checks,
    }
    moss.dump(out / "moss-results-reconciled.json", payload)
    print(json.dumps({"result": str(out / "moss-results-reconciled.json"), "checks": checks}, indent=2, sort_keys=True))
    return 0 if all(checks.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
