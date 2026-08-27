#!/usr/bin/env python3
"""Finish the matrix after the retained session-12 RTF gate aborted summary assembly."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("live_policy_recovery", HERE / "moss_sweep.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load moss_sweep.py")
moss = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = moss
SPEC.loader.exec_module(moss)


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--moss-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    corpus, root, out = args.corpus.resolve(), args.moss_root.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    runtime = read(root / "runtime-start.json")

    original_failure_trace = root / "pass-B/mono_javier_intro_50s/actual/live-replay/run-001/trace.jsonl"
    terminal = None
    rtf = None
    for line in original_failure_trace.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("kind") == "canonical_decode_rtf_evaluation":
            rtf = row
        elif row.get("kind") == "terminal":
            terminal = row
    if not terminal or terminal.get("failure_kind") != "rtf" or not rtf:
        raise RuntimeError("the retained session-12 trace is not the expected RTF gate failure")
    original_failure = {
        "pass": "B",
        "case_id": "mono_javier_intro_50s",
        "trace": str(original_failure_trace),
        "failure_kind": terminal["failure_kind"],
        "message": terminal["message"],
        "canonical_decode_rtf_p95": rtf["canonical_decode_rtf_p95"],
        "canonical_decode_rtf_bound": rtf["canonical_decode_rtf_bound"],
        "terminal_status": terminal["status"],
    }

    replacement_dir = root / "replacement-pass-B-mono/actual"
    replacement = moss.capture_actual(
        "mono_javier_intro_50s", corpus, replacement_dir, runtime, settle_timeout=30.0
    )

    actual = []
    actual_dirs = {}
    for pass_name in ("A", "B"):
        for case_id in moss.CASE_ORDER:
            if pass_name == "B" and case_id == "mono_javier_intro_50s":
                row, directory = replacement, replacement_dir
                source = "accuracy replacement after retained stress-gate abort"
            else:
                directory = root / f"pass-{pass_name}" / case_id / "actual"
                row = read(directory / "actual-result.json")
                source = "preregistered session"
            actual.append({"pass": pass_name, "source": source, **row})
            actual_dirs[(pass_name, case_id)] = directory

    model = moss.bench.discover_model("http://127.0.0.1:18000/v1", 30.0)
    runner = moss.bench.VllmRunner(base_url="http://127.0.0.1:18000/v1", model=model, api_key=None, timeout=180.0)
    shadows, accounting = [], {}
    for pass_name in ("A", "B"):
        cache = root / "shadow-cache" / ("pass-A.json" if pass_name == "A" else "pass-B-recovery.json")
        if pass_name == "B" and cache.exists():
            raise RuntimeError(f"recovery pass-B cache must be absent: {cache}")
        decoder = moss.bench.Decoder(runner=runner, model=model, cache_path=cache)
        ordered = moss.CASE_ORDER if pass_name == "A" else tuple(reversed(moss.CASE_ORDER))
        for case_id in ordered:
            shadow = moss.make_shadow(
                case_id=case_id,
                corpus=corpus,
                actual_dir=actual_dirs[(pass_name, case_id)],
                shadow_dir=out / f"pass-{pass_name}" / case_id,
                decoder=decoder,
            )
            shadows.append({"pass": pass_name, **shadow})
        accounting[pass_name] = decoder.take_accounting()
    if accounting["A"]["fresh_requests"] != 0:
        raise RuntimeError("pass A reconciliation did not reuse its retained fresh cache")
    if accounting["B"]["fresh_requests"] != accounting["B"]["requests"]:
        raise RuntimeError("pass B recovery shadow cache was not wholly fresh")

    runtime_end = moss.surface.runtime_descriptor()
    moss.dump(out / "runtime-end.json", runtime_end)
    queue_clean = all(
        row["events"]["rolling_queue"]["max_depth"] <= 1
        and row["events"]["rolling_queue"]["final_depth"] == 0
        and row["events"]["rolling_queue"]["admission_refusals"] == 0
        and row["events"]["rolling_queue"]["stale_completions"] == 0
        and row["events"]["rolling_queue"]["failed_windows"] == 0
        for row in actual
    )
    checks = {
        "runtime_descriptor_unchanged": runtime_end["live"]["descriptor"] == runtime["live"]["descriptor"],
        "exact_sample_accounting": all(row["sample_accounting"]["exact"] for row in actual),
        "production_10_10_differential": all(row["differential_10_10"]["content_and_speaker_exact"] for row in shadows),
        "rolling_queue_clean": queue_clean,
        "terminal_failures_zero": all(not row["events"]["terminal_failures"] for row in actual),
        "pre_stop_combined_rtf_lt_1": all(row["events"]["rtf"]["pre_stop_combined"] < 1 for row in actual),
        "strict_canonical_p95_rtf_gate": False,
    }
    payload = {
        "schema": "moss-live-policy-sweep.recovered.v1",
        "recovery_reason": "session 12 reached final but strict canonical p95 RTF aborted the replay before wrapper snapshots could be serialized",
        "stress_sessions": {"preregistered": 12, "accuracy_replacements": 1, "total": 13},
        "accuracy_denominator": {"passes": 2, "cases": 6, "observations": 12, "audio_seconds": sum(row["duration_seconds"] for row in actual)},
        "original_stress_failure": original_failure,
        "replacement_gate_failure": replacement.get("replay_gate_failure"),
        "shadow_accounting": accounting,
        "actual": actual,
        "shadows": shadows,
        "aggregate": moss.aggregate(actual, shadows),
        "checks": checks,
    }
    moss.dump(out / "moss-results.json", payload)
    print(json.dumps({"result": str(out / "moss-results.json"), "checks": checks}, indent=2, sort_keys=True))
    return 0 if all(checks.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
