"""Score the M2 (plan E2) exit gates on four fresh paired passes of the deployed service.

The gates, their clocks and their comparators are fixed in `PREREGISTRATION-M2-exit.md`,
written before the passes were launched. Nothing here may be re-decided after a number is seen.

  G-M2-1  trio rolling WER mean <= .150
  G-M2-2  per-case rolling WER strictly below baseline live (.2614 / .1440 / .1942)
  G-M2-3  trio content recall mean >= .940                  (evaluator v2)
  G-M2-4  correction-after-provisional p95 <= 6.0 s         (plan §1.3 G6 clock)
  G-M2-5  single-session combined inference RTF < 1, bounded queues (rescoped G7)
  G-M2-6  5-minute-case rolling WER <= .0985
  G-M2-7  accepted samples == accounted samples, exactly
  G-M2-8  file mode byte-identical to the checked-in 2026-08-24 baseline

G-M2-4's "changed" test is decided offline from the terminal snapshot rather than from the
event stream, because event payloads carry no meeting words by design: the base reading and the
surface reading of the SAME snapshot are produced by the two production exporters, and a
rolling-owned region counts as changed iff those two readings differ over it.

The §10.6 soak quantities (Appendix B rescopes the 30-minute soak to the 5-minute case, which
these passes already are) are reported beside the gates, never blended into them.

Usage:
  python verify_m2_exit.py --fresh-root /tmp/m2-exit-<stamp> [--output out.json]

Exit 0 iff every gate passes.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluator_v2 import Segment as V2Segment, score_v2, speech_regions_from_wav  # noqa: E402
from moss_transcribe_diarize.live_speaker_accuracy import (  # noqa: E402
    _hypothesis_from_committed,
    _hypothesis_from_surface,
)

BASELINE = REPO / "prototypes/live-file-gap-baseline-20260824"
CASES_CONTRACT = Path(__file__).resolve().parent / "cases.json"
SAMPLE_RATE = 16000
RUNS = ("A", "B")

# Preregistered, from the PRD's M2 milestone. Not tunable here.
TRIO_WER_BOUND = 0.150
RECALL_BOUND = 0.940
CORRECTION_P95_BOUND_SEC = 6.0
COMBINED_RTF_BOUND = 1.0
FIVE_MINUTE_WER_BOUND = 0.0985
PRD_BASELINE_LIVE_WER_4DP = {"lex_bill_ackman": 0.2614, "lex_javier_milei": 0.1440, "lex_keyu_jin": 0.1942}
# The rolling geometry the §10.2 grid selected, read from the production module so that a
# geometry change is a gate change rather than a silent one.
from moss_transcribe_diarize.app.live_transcript_convergence import (  # noqa: E402
    DEFAULT_ROLLING_GEOMETRY,
)

WINDOW_SAMPLES = DEFAULT_ROLLING_GEOMETRY.window_samples
STRIDE_SAMPLES = DEFAULT_ROLLING_GEOMETRY.stride_samples
RETAINED_BOUND_SAMPLES = 2 * WINDOW_SAMPLES

TRIO_CASES = ("lex_bill_ackman", "lex_javier_milei", "lex_keyu_jin")
FIVE_MINUTE_CASE = "keyu-5m"
CASE_DURATION_SEC = {FIVE_MINUTE_CASE: 300.0}


# ------------------------------------------------------------------ small helpers


def sha256_bytes(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def trace_lines(trace: Path) -> list[str]:
    if not trace.exists():
        gz = trace.with_suffix(trace.suffix + ".gz")
        if gz.exists():
            with gzip.open(gz, "rt") as handle:
                return handle.read().splitlines()
        return []
    if trace.suffix == ".gz":
        with gzip.open(trace, "rt") as handle:
            return handle.read().splitlines()
    return trace.read_text().splitlines()


def read_trace(trace: Path) -> dict:
    """Events in stream order plus the terminal snapshot, from one replay trace."""

    events: list[dict] = []
    terminal: dict | None = None
    for line in trace_lines(trace):
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("kind") == "service_event":
            event = entry["event"]
            events.append(
                {"seq": event.get("seq"), "kind": event.get("kind"), "payload": event.get("payload") or {}}
            )
        elif entry.get("kind") == "terminal":
            terminal = entry
    return {"events": events, "terminal": terminal, "bytes": sum(len(line) + 1 for line in trace_lines(trace))}


def percentile_interpolated(values: list[float], quantile: float) -> float | None:
    """`lane_rolling_terminal._percentile` -- the plan's own G5/G6 percentile."""

    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def percentile_nearest_rank(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    import math

    ordered = sorted(values)
    return ordered[math.ceil(quantile * len(ordered)) - 1]


def distribution(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "max": None}
    return {
        "count": len(values),
        "mean": round(sum(values) / len(values), 6),
        "p50": round(percentile_interpolated(values, 0.50), 6),
        "p95": round(percentile_interpolated(values, 0.95), 6),
        "max": round(max(values), 6),
    }


def words(segments) -> list[str]:
    out: list[str] = []
    for segment in segments:
        out.extend(str(segment.text).split())
    return out


# ------------------------------------------------------------------ corpus contract


def corpus_contract() -> dict[str, dict]:
    """Which reference and which audio each scored case is measured against."""

    contract = json.loads(CASES_CONTRACT.read_text())
    by_case = {case["case_id"]: case for case in contract["cases"]}
    mapping = {case: by_case[case] for case in TRIO_CASES}
    mapping[FIVE_MINUTE_CASE] = by_case["5m-lex-keyu-jin"]
    return mapping


def baseline_live_wer() -> dict[str, float]:
    """The comparators, read from the artifact the PRD's 4-dp digits were rounded from."""

    data = json.loads((BASELINE / "trio-60s/results.json").read_text())
    measured = {
        case["case_id"]: case["arms"]["live"]["scores"]["tbsa"]["wer"]
        for case in data["cases"]
        if case["tier"] == "primary"
    }
    for case, stated in PRD_BASELINE_LIVE_WER_4DP.items():
        if round(measured[case], 4) != stated:
            raise SystemExit(
                f"baseline artifact disagrees with the PRD comparator for {case}: "
                f"{measured[case]} does not round to {stated}"
            )
    return measured


# ------------------------------------------------------------------ collection


def case_paths(fresh_root: Path, case: str, run: str) -> dict[str, Path]:
    if case == FIVE_MINUTE_CASE:
        root = fresh_root / f"keyu5m-{run}"
        return {
            "results": root / "results.json",
            "file_hypothesis": root / "file-hypothesis.jsonl",
            "live_hypothesis": root / "live-hypothesis.jsonl",
            "trace": root / "live/run-001/trace.jsonl",
            "summary": root / "live/run-001/summary.json",
        }
    root = fresh_root / f"trio-{run}"
    return {
        "results": root / "results.json",
        "file_hypothesis": root / case / "file-hypothesis.jsonl",
        "live_hypothesis": root / case / "live-hypothesis.jsonl",
        "trace": root / case / "live/run-001/trace.jsonl",
        "summary": root / case / "live/run-001/summary.json",
    }


def collect(fresh_root: Path) -> dict:
    contract = corpus_contract()
    report: dict = {"fresh_root": str(fresh_root), "cases": {}}
    for case in list(TRIO_CASES) + [FIVE_MINUTE_CASE]:
        duration = CASE_DURATION_SEC.get(case, 60.0)
        reference = [
            V2Segment(**row)
            for row in load_reference_rows(REPO / contract[case]["reference"])
        ]
        audio = REPO / contract[case]["audio"]
        regions = speech_regions_from_wav(audio) if audio.exists() else None
        node: dict = {"duration_sec": duration, "runs": {}}
        for run in RUNS:
            paths = case_paths(fresh_root, case, run)
            run_node: dict = {}
            if paths["results"].exists():
                data = json.loads(paths["results"].read_text())
                if case == FIVE_MINUTE_CASE:
                    arms = data["results"]
                else:
                    arms = next(
                        (c["arms"] for c in data["cases"] if c["case_id"] == case),
                        {},
                    )
                live = (arms.get("live") or {}).get("scores") or {}
                file_arm = (arms.get("file") or {}).get("scores") or {}
                run_node["live_wer"] = (live.get("tbsa") or {}).get("wer")
                run_node["live_der"] = (live.get("diarization") or {}).get("der")
                run_node["file_wer"] = (file_arm.get("tbsa") or {}).get("wer")
                run_node["live_segments"] = ((arms.get("live") or {}).get("meta") or {}).get("segments")
            run_node["file_sha256"] = sha256_bytes(paths["file_hypothesis"])
            if paths["live_hypothesis"].exists():
                hypothesis = [
                    V2Segment(**row) for row in load_reference_rows(paths["live_hypothesis"])
                ]
                scored = score_v2(
                    reference,
                    hypothesis,
                    speech_regions=regions,
                    speech_regions_source="webrtcvad_mode1_10ms" if regions else "reference_intervals",
                )
                run_node["v2"] = {
                    "content_recall": scored["content_recall"],
                    "wer": scored["wer"]["wer"],
                    "matched_word_speaker_accuracy": scored["matched_word_speaker"][
                        "matched_word_speaker_accuracy"
                    ],
                    "der_reference_speech": scored["der_reference_speech"]["der"],
                    "hypothesis_segments": scored["extent"]["hypothesis_segments"],
                }
            if paths["summary"].exists():
                summary = json.loads(paths["summary"].read_text())
                run_node["summary"] = {
                    key: summary.get(key)
                    for key in (
                        "status",
                        "failure_kind",
                        "accepted_samples",
                        "accounted_samples",
                        "frame_count",
                        "canonical_decode_rtf_p95",
                        "canonical_decode_rtf_passed",
                    )
                }
            run_node.update(read_session(paths["trace"], duration))
            node["runs"][run] = run_node
        report["cases"][case] = node
    return report


def load_reference_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        rows.append(
            {
                "start": float(record["start"]),
                "end": float(record["end"]),
                "speaker": str(record["speaker"]),
                "text": str(record.get("text") or ""),
            }
        )
    return rows


def read_session(trace: Path, duration_sec: float) -> dict:
    """Everything the gates and the soak read off one live session."""

    parsed = read_trace(trace)
    events = parsed["events"]
    terminal = parsed["terminal"]
    session = ((terminal or {}).get("snapshot") or {}).get("session") or {}

    canonical: list[dict] = []
    queued_ns: dict[int, int] = {}
    for event in events:
        payload = event["payload"]
        if event["kind"] == "canonical_queued":
            queued_ns[int(payload["item_id"])] = int(payload["runtime_monotonic_ns"])
        elif event["kind"] == "canonical_processed":
            committed = payload.get("committed_samples")
            span_samples = payload.get("frozen_span_sample_count") or 0
            item_id = payload.get("item_id")
            canonical.append(
                {
                    "span_id": payload.get("span_id"),
                    "item_id": item_id,
                    "start_sample": None if committed is None else int(committed) - int(span_samples),
                    "end_sample": None if committed is None else int(committed),
                    "published_ns": int(payload["runtime_monotonic_ns"]),
                    "queued_ns": queued_ns.get(int(item_id)) if item_id is not None else None,
                    "queue_wait_ms": payload.get("queue_wait_ms"),
                    "queued_to_processed_ms": payload.get("queued_to_processed_ms"),
                    "decode_elapsed_sec": payload.get("canonical_decode_elapsed_sec"),
                    "decode_rtf": payload.get("canonical_decode_rtf"),
                    "submitted": payload.get("submitted"),
                    "rolling_status": payload.get("rolling_status"),
                    "salvage": payload.get("canonical_decode_salvage"),
                }
            )

    rolling_queued = [
        {
            "item_id": event["payload"].get("item_id"),
            "admitted": bool(event["payload"].get("admitted")),
            "window_index": event["payload"].get("window_index"),
            "start_sample": event["payload"].get("start_sample"),
            "end_sample": event["payload"].get("end_sample"),
            "queued_ns": event["payload"].get("runtime_monotonic_ns"),
        }
        for event in events
        if event["kind"] == "rolling_decode_queued"
    ]
    rolling_completed = [
        {
            "item_id": event["payload"].get("item_id"),
            "outcome": event["payload"].get("outcome"),
            "window_index": event["payload"].get("window_index"),
            "owned_start_sample": event["payload"].get("owned_start_sample"),
            "owned_end_sample": event["payload"].get("owned_end_sample"),
            "applied": bool(event["payload"].get("applied")),
            "proposed": bool(event["payload"].get("proposed")),
            "refusal": event["payload"].get("refusal"),
            "published_ns": event["payload"].get("runtime_monotonic_ns"),
            "queue_wait_ms": event["payload"].get("queue_wait_ms"),
            "decode_elapsed_sec": event["payload"].get("rolling_decode_elapsed_sec"),
            "decode_rtf": event["payload"].get("rolling_decode_rtf"),
            "generated_tokens": event["payload"].get("rolling_decode_generated_tokens"),
            "decoded_audio_samples": event["payload"].get("decoded_audio_samples"),
            "retained_high_water_samples": event["payload"].get("retained_high_water_samples"),
            "windows_planned": event["payload"].get("windows_planned"),
            "windows_completed": event["payload"].get("windows_completed"),
            "windows_failed": event["payload"].get("windows_failed"),
            "stale_completions": event["payload"].get("stale_completions"),
            "admission_refusals": event["payload"].get("admission_refusals"),
            "rolling_status": event["payload"].get("rolling_status"),
        }
        for event in events
        if event["kind"] == "rolling_decode_completed"
    ]

    # Rolling queue depth, walked in event order: admitted-minus-completed, which the §7.4
    # accounting property (one announcement per planned window, one completion per admitted
    # window) makes a real depth rather than a leak counter.
    depth = 0
    max_depth = 0
    for event in events:
        if event["kind"] == "rolling_decode_queued" and event["payload"].get("admitted"):
            depth += 1
            max_depth = max(max_depth, depth)
        elif event["kind"] == "rolling_decode_completed":
            depth -= 1

    base_segments = surface_segments = None
    if session:
        try:
            base_segments = _hypothesis_from_committed(
                session, corpus_start_sample=0, corpus_duration_sec=duration_sec
            )
        except Exception as exc:  # a snapshot the exporter refuses is a finding, not a crash
            base_segments = f"refused: {type(exc).__name__}: {exc}"
        if "effective_transcript" in session:
            try:
                surface_segments = _hypothesis_from_surface(
                    session, corpus_start_sample=0, corpus_duration_sec=duration_sec
                )
            except Exception as exc:
                surface_segments = f"refused: {type(exc).__name__}: {exc}"

    return {
        "canonical": canonical,
        "rolling_queued": rolling_queued,
        "rolling_completed": rolling_completed,
        "rolling_max_depth": max_depth,
        "rolling_final_depth": depth,
        "text_revision_applied": sum(1 for e in events if e["kind"] == "text_revision_applied"),
        "text_revision_refused": [
            e["payload"] for e in events if e["kind"] == "text_revision_refused"
        ],
        "decode_salvaged": sum(1 for e in events if e["kind"] == "decode_salvaged"),
        "event_kinds": sorted({e["kind"] for e in events}),
        "terminal_failure": [e["payload"] for e in events if e["kind"] == "terminal_failure"],
        "snapshot": {
            "text_revision_version": session.get("text_revision_version"),
            "finalization_status": session.get("finalization_status"),
            "canonical_through_sample": session.get("canonical_through_sample"),
            "accepted_samples": session.get("accepted_samples"),
            "accounted_samples": session.get("accounted_samples"),
            "label_revision_version": session.get("label_revision_version"),
            "committed_spans": len(session.get("committed") or []),
            "surface_segments": len(session.get("effective_transcript") or []),
            "bytes": len(json.dumps(((terminal or {}).get("snapshot") or {}), ensure_ascii=False)),
        },
        "base_segments": base_segments,
        "surface_segments_export": surface_segments,
        "trace_bytes": parsed["bytes"],
    }


# ------------------------------------------------------------------ the G6 clock


def correction_latencies(run_node: dict) -> dict:
    """Plan §1.3's G6 clock, over changed rolling-owned regions only."""

    base = run_node.get("base_segments")
    surface = run_node.get("surface_segments_export")
    if not isinstance(base, tuple) or not isinstance(surface, tuple):
        return {"latencies": [], "changed": 0, "unchanged": 0, "regions": [], "readable": False}

    latencies: list[float] = []
    regions: list[dict] = []
    changed = unchanged = 0
    for completion in run_node.get("rolling_completed") or []:
        if not completion.get("applied"):
            continue
        start = completion.get("owned_start_sample")
        end = completion.get("owned_end_sample")
        if start is None or end is None:
            continue
        lo, hi = start / SAMPLE_RATE, end / SAMPLE_RATE
        base_words = words([s for s in base if lo - 1e-9 <= s.start < hi + 1e-9])
        surface_words = words([s for s in surface if lo - 1e-9 <= s.start < hi + 1e-9])
        region_changed = base_words != surface_words
        region = {
            "window_index": completion.get("window_index"),
            "owned_start_sec": round(lo, 3),
            "owned_end_sec": round(hi, 3),
            "base_words": len(base_words),
            "surface_words": len(surface_words),
            "changed": region_changed,
            "latencies": [],
        }
        if not region_changed:
            unchanged += 1
            regions.append(region)
            continue
        changed += 1
        for span in run_node.get("canonical") or []:
            if span["start_sample"] is None:
                continue
            midpoint = (span["start_sample"] + span["end_sample"]) / 2.0
            if start <= midpoint <= end + 1e-9:
                wait = max(0.0, (completion["published_ns"] - span["published_ns"]) / 1e9)
                latencies.append(wait)
                region["latencies"].append(round(wait, 6))
        regions.append(region)
    return {
        "latencies": latencies,
        "changed": changed,
        "unchanged": unchanged,
        "regions": regions,
        "readable": True,
    }


# ------------------------------------------------------------------ gates


def evaluate(report: dict) -> dict:
    cases = report["cases"]
    gates: dict[str, dict] = {}

    means: dict[str, dict] = {}
    for case, node in cases.items():
        wers = [node["runs"][run].get("live_wer") for run in RUNS]
        recalls = [(node["runs"][run].get("v2") or {}).get("content_recall") for run in RUNS]
        ders = [node["runs"][run].get("live_der") for run in RUNS]
        means[case] = {
            "live_wer_per_pass": wers,
            "live_wer_mean": None if any(w is None for w in wers) else round(sum(wers) / len(wers), 6),
            "content_recall_per_pass": recalls,
            "content_recall_mean": None
            if any(r is None for r in recalls)
            else round(sum(recalls) / len(recalls), 6),
            "live_der_per_pass": ders,
            "live_der_mean": None if any(d is None for d in ders) else round(sum(ders) / len(ders), 6),
        }

    trio_wers = [means[c]["live_wer_mean"] for c in TRIO_CASES]
    trio_wer = None if any(w is None for w in trio_wers) else round(sum(trio_wers) / len(trio_wers), 6)
    trio_recalls = [means[c]["content_recall_mean"] for c in TRIO_CASES]
    trio_recall = (
        None if any(r is None for r in trio_recalls) else round(sum(trio_recalls) / len(trio_recalls), 6)
    )

    gates["G_M2_1_trio_rolling_wer"] = {
        "pass": trio_wer is not None and trio_wer <= TRIO_WER_BOUND,
        "trio_rolling_wer_mean": trio_wer,
        "bound": TRIO_WER_BOUND,
        "grid_projection": 0.131861,
        "baseline_live_trio_wer": 0.199870,
        "per_case": {c: means[c] for c in TRIO_CASES},
    }

    comparators = baseline_live_wer()
    per_case = {}
    for case in TRIO_CASES:
        mean = means[case]["live_wer_mean"]
        per_case[case] = {
            "baseline_live_wer": comparators[case],
            "prd_states": PRD_BASELINE_LIVE_WER_4DP[case],
            "measured_mean": mean,
            "delta": None if mean is None else round(mean - comparators[case], 6),
            "improves": mean is not None and mean < comparators[case],
        }
    gates["G_M2_2_per_case_improvement"] = {
        "pass": all(v["improves"] for v in per_case.values()),
        "per_case": per_case,
    }

    gates["G_M2_3_content_recall"] = {
        "pass": trio_recall is not None and trio_recall >= RECALL_BOUND,
        "trio_content_recall_mean": trio_recall,
        "bound": RECALL_BOUND,
        "grid_projection": 0.943916,
        "baseline_live_recall": 0.913490,
        "per_case": {c: means[c]["content_recall_per_pass"] for c in TRIO_CASES},
        "five_minute": means[FIVE_MINUTE_CASE]["content_recall_per_pass"],
    }

    # --- G-M2-4 the correction clock, pooled over the primary trio, both passes ---
    pooled: list[float] = []
    per_run_corrections: dict[str, dict] = {}
    unreadable: list[str] = []
    for case in TRIO_CASES:
        for run in RUNS:
            node = cases[case]["runs"][run]
            measured = correction_latencies(node)
            if not measured["readable"]:
                unreadable.append(f"{case}/{run}")
            pooled.extend(measured["latencies"])
            per_run_corrections[f"{case}/{run}"] = {
                "changed_regions": measured["changed"],
                "unchanged_regions": measured["unchanged"],
                "latency_count": len(measured["latencies"]),
                "distribution": distribution(measured["latencies"]),
            }
    p95 = percentile_interpolated(pooled, 0.95)
    gates["G_M2_4_correction_p95"] = {
        "pass": bool(pooled) and not unreadable and p95 is not None and p95 <= CORRECTION_P95_BOUND_SEC,
        "p95_sec": None if p95 is None else round(p95, 6),
        "p95_nearest_rank_sec": None
        if not pooled
        else round(percentile_nearest_rank(pooled, 0.95), 6),
        "bound_sec": CORRECTION_P95_BOUND_SEC,
        "structural_floor_sec_at_10_10": 8.51,
        "distribution": distribution(pooled),
        "unreadable_sessions": unreadable,
        "per_session": per_run_corrections,
        "note": (
            "iteration 10 F3 preregistered this miss: with central ownership the oldest owned "
            "word has age (L+S)/2, so L+S <= 12 is required and the selected geometry is L+S = 20"
        ),
    }

    # --- G-M2-5 combined RTF and bounded queues, one session at a time ---
    sessions: dict[str, dict] = {}
    for case, node in cases.items():
        duration = node["duration_sec"]
        for run in RUNS:
            run_node = node["runs"][run]
            canonical = run_node.get("canonical") or []
            rolling = run_node.get("rolling_completed") or []
            base_sec = sum(float(c["decode_elapsed_sec"] or 0.0) for c in canonical)
            witness_sec = sum(float(r["decode_elapsed_sec"] or 0.0) for r in rolling)
            # A window is plannable once the session's own committed prefix covers it, so the
            # count is read from `canonical_through_sample` rather than from the corpus
            # duration: a meeting whose last span stops one sample short of the nominal
            # length has one fewer window and no defect.
            through = (run_node.get("snapshot") or {}).get("canonical_through_sample")
            if not isinstance(through, int):
                through = int(duration * SAMPLE_RATE)
            expected_windows = int(through // STRIDE_SAMPLES)
            planned = len(run_node.get("rolling_queued") or [])
            refused_admissions = sum(
                1 for item in (run_node.get("rolling_queued") or []) if not item["admitted"]
            )
            failures = [r for r in rolling if r["outcome"] not in {"applied", "refused"}]
            unsubmitted = [c for c in canonical if c.get("submitted") is not True]
            high_water = max(
                [int(r["retained_high_water_samples"] or 0) for r in rolling] or [0]
            )
            sessions[f"{case}/{run}"] = {
                "audio_sec": duration,
                "base_decode_sec": round(base_sec, 6),
                "witness_decode_sec": round(witness_sec, 6),
                "base_rtf": round(base_sec / duration, 6),
                "witness_rtf": round(witness_sec / duration, 6),
                "combined_rtf": round((base_sec + witness_sec) / duration, 6),
                "windows_expected": expected_windows,
                "windows_planned": planned,
                "windows_admitted": planned - refused_admissions,
                "windows_completed": len(rolling),
                "windows_applied": sum(1 for r in rolling if r["applied"]),
                "windows_failed_outcomes": [r["outcome"] for r in failures],
                "admission_refusals": refused_admissions,
                "stale_completions": max([int(r["stale_completions"] or 0) for r in rolling] or [0]),
                "rolling_max_depth": run_node.get("rolling_max_depth"),
                "rolling_final_depth": run_node.get("rolling_final_depth"),
                "retained_high_water_samples": high_water,
                "retained_bound_samples": RETAINED_BOUND_SAMPLES,
                "unsubmitted_canonical_spans": len(unsubmitted),
                "canonical_spans": len(canonical),
                "text_revision_version": (run_node.get("snapshot") or {}).get("text_revision_version"),
                "canonical_queue_wait_ms": distribution(
                    [float(c["queue_wait_ms"]) for c in canonical if c.get("queue_wait_ms") is not None]
                ),
                "rolling_queue_wait_ms": distribution(
                    [float(r["queue_wait_ms"]) for r in rolling if r.get("queue_wait_ms") is not None]
                ),
                "canonical_queued_to_processed_ms": distribution(
                    [
                        float(c["queued_to_processed_ms"])
                        for c in canonical
                        if c.get("queued_to_processed_ms") is not None
                    ]
                ),
                "canonical_decode_rtf_p95": (run_node.get("summary") or {}).get(
                    "canonical_decode_rtf_p95"
                ),
            }
    def bounded(node: dict) -> bool:
        return (
            node["combined_rtf"] < COMBINED_RTF_BOUND
            and node["rolling_max_depth"] <= 1
            and node["rolling_final_depth"] == 0
            and node["windows_completed"] == node["windows_admitted"]
            and node["windows_planned"] == node["windows_expected"]
            and not node["windows_failed_outcomes"]
            and node["unsubmitted_canonical_spans"] == 0
            and node["retained_high_water_samples"] <= RETAINED_BOUND_SAMPLES
            and (node["text_revision_version"] or 0) > 0
        )

    gates["G_M2_5_combined_rtf_bounded_queues"] = {
        "pass": bool(sessions) and all(bounded(node) for node in sessions.values()),
        "bound_combined_rtf": COMBINED_RTF_BOUND,
        "failing_sessions": [key for key, node in sessions.items() if not bounded(node)],
        "per_session": sessions,
        "note": (
            "the witness ran on the deployed service is part of this gate: a session with no "
            "planned window or no applied revision cannot satisfy it"
        ),
    }

    five = means[FIVE_MINUTE_CASE]["live_wer_mean"]
    gates["G_M2_6_five_minute_rolling_wer"] = {
        "pass": five is not None and five <= FIVE_MINUTE_WER_BOUND,
        "five_minute_rolling_wer_mean": five,
        "per_pass": means[FIVE_MINUTE_CASE]["live_wer_per_pass"],
        "bound": FIVE_MINUTE_WER_BOUND,
        "baseline_live_wer": 0.1464,
        "paired_file_wer": 0.0506,
        "der_mean": means[FIVE_MINUTE_CASE]["live_der_mean"],
    }

    accounting: dict[str, dict] = {}
    for case, node in cases.items():
        for run in RUNS:
            run_node = node["runs"][run]
            summary = run_node.get("summary") or {}
            snapshot = run_node.get("snapshot") or {}
            accepted = summary.get("accepted_samples")
            accounted = summary.get("accounted_samples")
            accounting[f"{case}/{run}"] = {
                "status": summary.get("status"),
                "accepted_samples": accepted,
                "accounted_samples": accounted,
                "snapshot_accepted": snapshot.get("accepted_samples"),
                "snapshot_accounted": snapshot.get("accounted_samples"),
                "exact": (
                    summary.get("status") == "succeeded"
                    and accepted is not None
                    and accepted == accounted
                    and snapshot.get("accepted_samples") == snapshot.get("accounted_samples")
                ),
            }
    gates["G_M2_7_exact_sample_accounting"] = {
        "pass": bool(accounting) and all(v["exact"] for v in accounting.values()),
        "per_session": accounting,
    }

    # Every case the checked-in baseline holds a file arm for, not only the scored trio: the
    # secondary `acquired_*` cases never enter a promotion denominator, but their file output
    # is exactly as much a regression tripwire as the trio's.
    g8: dict[str, dict] = {}
    baseline_cases = [c["case_id"] for c in json.loads((BASELINE / "trio-60s/results.json").read_text())["cases"]]
    baseline_paths = {case: BASELINE / "trio-60s" / case / "file-hypothesis.jsonl" for case in baseline_cases}
    baseline_paths[FIVE_MINUTE_CASE] = BASELINE / "keyu-5m/file-hypothesis.jsonl"
    for case in baseline_cases + [FIVE_MINUTE_CASE]:
        expected = sha256_bytes(baseline_paths[case])
        node = {"baseline_sha256": expected}
        for run in RUNS:
            node[run] = (
                cases[case]["runs"][run].get("file_sha256")
                if case in cases
                else sha256_bytes(case_paths(Path(report["fresh_root"]), case, run)["file_hypothesis"])
            )
        node["identical"] = expected is not None and all(node[run] == expected for run in RUNS)
        g8[case] = node
    gates["G_M2_8_file_mode_byte_identical"] = {
        "pass": all(v["identical"] for v in g8.values()),
        "per_case": g8,
    }

    gates["_soak_10_6"] = {
        "pass": True,
        "note": (
            "Appendix B rescopes the §10.6 soak to the 5-minute case; reported, not gated. "
            "Portal render time stays the attended browser item."
        ),
        "five_minute": {
            run: {
                "combined_rtf": sessions[f"{FIVE_MINUTE_CASE}/{run}"]["combined_rtf"],
                "base_rtf": sessions[f"{FIVE_MINUTE_CASE}/{run}"]["base_rtf"],
                "witness_rtf": sessions[f"{FIVE_MINUTE_CASE}/{run}"]["witness_rtf"],
                "windows": {
                    key: sessions[f"{FIVE_MINUTE_CASE}/{run}"][key]
                    for key in (
                        "windows_expected",
                        "windows_planned",
                        "windows_completed",
                        "windows_applied",
                        "admission_refusals",
                        "stale_completions",
                        "rolling_max_depth",
                        "retained_high_water_samples",
                    )
                },
                "canonical_queue_wait_ms": sessions[f"{FIVE_MINUTE_CASE}/{run}"]["canonical_queue_wait_ms"],
                "rolling_queue_wait_ms": sessions[f"{FIVE_MINUTE_CASE}/{run}"]["rolling_queue_wait_ms"],
                "canonical_queued_to_processed_ms": sessions[f"{FIVE_MINUTE_CASE}/{run}"][
                    "canonical_queued_to_processed_ms"
                ],
                "correction_latency": distribution(
                    correction_latencies(cases[FIVE_MINUTE_CASE]["runs"][run])["latencies"]
                ),
                "snapshot_bytes": (cases[FIVE_MINUTE_CASE]["runs"][run].get("snapshot") or {}).get("bytes"),
                "trace_bytes": cases[FIVE_MINUTE_CASE]["runs"][run].get("trace_bytes"),
                "text_revisions": (cases[FIVE_MINUTE_CASE]["runs"][run].get("snapshot") or {}).get(
                    "text_revision_version"
                ),
                "text_revision_refused": cases[FIVE_MINUTE_CASE]["runs"][run].get("text_revision_refused"),
                "salvaged_spans": cases[FIVE_MINUTE_CASE]["runs"][run].get("decode_salvaged"),
                "v2": cases[FIVE_MINUTE_CASE]["runs"][run].get("v2"),
            }
            for run in RUNS
        },
        "trio_sessions": {
            key: {
                "combined_rtf": node["combined_rtf"],
                "witness_rtf": node["witness_rtf"],
                "windows_applied": node["windows_applied"],
                "rolling_max_depth": node["rolling_max_depth"],
                "retained_high_water_samples": node["retained_high_water_samples"],
                "snapshot_bytes": (cases[key.split("/")[0]]["runs"][key.split("/")[1]].get("snapshot") or {}).get("bytes"),
            }
            for key, node in sessions.items()
            if not key.startswith(FIVE_MINUTE_CASE)
        },
    }
    gates["_v2_report"] = {
        "pass": True,
        "note": "evaluator v2 axes, reported for continuity (M1-M4 gates name the deployed metrics)",
        "per_case": {case: {run: cases[case]["runs"][run].get("v2") for run in RUNS} for case in cases},
    }
    return gates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = collect(args.fresh_root.resolve())
    gates = evaluate(report)
    if args.output:
        args.output.write_text(
            json.dumps({"fresh_root": str(args.fresh_root.resolve()), "gates": gates}, indent=2)
            + "\n"
        )
    ok = True
    for name, gate in gates.items():
        if name.startswith("_"):
            continue
        ok = ok and gate["pass"]
        print(f"[{'PASS' if gate['pass'] else 'FAIL'}] {name}")
        printable = {k: v for k, v in gate.items() if k not in {"pass", "per_session", "per_case"}}
        for line in json.dumps(printable, indent=2).splitlines():
            print("    " + line)
        for key in ("per_case", "per_session"):
            if key in gate:
                for line in json.dumps(gate[key], indent=2).splitlines()[:60]:
                    print("    " + line)
    print("\n-- reported, not gated: §10.6 soak --")
    print(json.dumps(gates["_soak_10_6"], indent=2))
    print("\nALL GATES PASS" if ok else "\nGATE FAILURE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
