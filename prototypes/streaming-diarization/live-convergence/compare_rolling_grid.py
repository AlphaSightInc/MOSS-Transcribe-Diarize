#!/usr/bin/env python3
"""PROTOTYPE -- throwaway. Plan §10.2-§10.4: which rolling window/stride and truth-blind
stitch policy preserve the rolling gain with the fewest joins and least GPU work?

Preregistered in `PREREGISTRATION-M2-grid.md` (questions, arms, gates, selection rule and six
falsifiable predictions, all written before the first decode). Nothing here may be changed to
make a number pass; the selection rule is plan §10.4's and is applied verbatim.

The measurement bench is `prototypes/live-file-gap-context/proto_context_arms.py`: this script
imports its decoder, its cache, its span loader, its shared speaker timeline and its scorer
rather than rebuilding them (AGENTS.md: extend the bench). What is new here is the grid --
four window/stride geometries x three ownership policies -- and the §10.3 instrumentation.

One command:

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
      prototypes/streaming-diarization/live-convergence/compare_rolling_grid.py \\
      --cases lex_bill_ackman,lex_javier_milei,lex_keyu_jin \\
      --windows 10/5,10/10,15/7.5,15/10 \\
      --stitches char,uniform,lexical \\
      --runs 3 \\
      --output /tmp/moss-rolling-grid.json

Exit 0 iff the bench validates (P1) and at least one arm passes G1-G3; the selected arm is
printed last. Every wall-clock number is measured on the shared 4070 Ti through the read-only
tunnel and is reported as measured, not as a production latency verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "prototypes/live-file-gap-context"))

import proto_context_arms as bench  # noqa: E402
from moss_transcribe_diarize.app.live_adapters import canonical_decode_token_cap  # noqa: E402
from moss_transcribe_diarize.evaluation import Segment  # noqa: E402

SAMPLE_RATE = bench.SAMPLE_RATE
PREREG = ROOT / "PREREGISTRATION-M2-grid.md"
DEFAULT_BASELINE = REPO / "prototypes/live-file-gap-baseline-20260824/trio-60s"
DEFAULT_CACHE_DIR = Path("/tmp/moss-rolling-grid-decode-cache-v1")

STITCHES = ("char", "uniform", "lexical")

# Gate thresholds. Immutable per the preregistration; sourced from PRD M2 / plan §1.3.
GATE_WER_MAX = 0.150
GATE_RECALL_MIN = 0.940
# Per-case live comparators the PRD prints to 4 dp; the full-precision values are read from the
# frozen baseline artifact below and asserted to round to these.
PRD_LIVE_WER = {
    "lex_bill_ackman": 0.2614,
    "lex_javier_milei": 0.1440,
    "lex_keyu_jin": 0.1942,
}
# P1: the base control must reproduce the published live trio means this closely.
PUBLISHED_LIVE_TRIO = {"wer": 0.19987, "content_recall": 0.91349}
PUBLISHED_A2_10_5 = {"wer": 0.128926, "content_recall": 0.948477}
BENCH_TOLERANCE = 0.005

# G6's production threshold, reported here only as a structural floor (see §"latency" below).
G6_SECONDS = 6.0


# ---------------------------------------------------------------- truth-blindness


class ReferenceReadInsideReconciler(RuntimeError):
    """The reconciler tried to read reference truth. Plan §10.2 forbids it."""


class _TruthBlind:
    """While an arm is produced, reading the reference aborts the run.

    Plan §10.2 says "the reconciler sees no reference". Asserting that in prose is worth
    nothing; this makes the forbidden call raise, so a future edit that scores an arm against
    truth while choosing its words fails loudly instead of quietly selecting itself.
    """

    def __enter__(self) -> "_TruthBlind":
        self._saved = bench.load_reference

        def _forbidden(case: str) -> list[Segment]:
            raise ReferenceReadInsideReconciler(case)

        bench.load_reference = _forbidden
        return self

    def __exit__(self, *exc: Any) -> None:
        bench.load_reference = self._saved


# ---------------------------------------------------------------- geometry


class RegionsDoNotTile(RuntimeError):
    """Ownership regions overlap or leave a gap, so words are published twice or dropped."""


def plan_windows(duration: float, window: float, stride: float) -> list[dict[str, Any]]:
    """Windows tiling [0, duration], each with the central region it owns.

    Ownership boundary between consecutive windows is the midpoint of their overlap. On the
    unclamped windows that is exactly `proto_context_arms`'s a2 rule -- `lo + (L±S)/2` -- and
    unlike that rule it still tiles when the final window is pulled back to end at `duration`
    (15/10 on a 60 s clip clamps its last start from 50 s to 45 s, and the a2 formula would
    then hand [47.5, 52.5] to two windows at once, publishing those words twice).
    """
    count = math.ceil(max(duration - window, 0.0) / stride) + 1
    ranges: list[tuple[float, float]] = []
    for index in range(count):
        hi = min(duration, index * stride + window)
        lo = max(0.0, hi - window)
        ranges.append((lo, hi))
    out: list[dict[str, Any]] = []
    for index, (lo, hi) in enumerate(ranges):
        region_lo = 0.0 if index == 0 else (ranges[index][0] + ranges[index - 1][1]) / 2
        region_hi = (
            duration
            if index == len(ranges) - 1
            else (ranges[index + 1][0] + ranges[index][1]) / 2
        )
        out.append({
            "index": index,
            "start_sample": int(round(lo * SAMPLE_RATE)),
            "end_sample": int(round(hi * SAMPLE_RATE)),
            "range": [lo, hi],
            "region": [region_lo, region_hi],
        })
    # The regions must partition [0, duration]: an overlap publishes the same words from two
    # windows, a gap drops them. Checked here rather than inferred from a metric, because a
    # double-published word only shows up in WER when it happens to hurt.
    if out[0]["region"][0] != 0.0 or abs(out[-1]["region"][1] - duration) > 1e-9:
        raise RegionsDoNotTile(f"ends {out[0]['region'][0]}..{out[-1]['region'][1]} != 0..{duration}")
    for left, right in zip(out, out[1:]):
        if abs(left["region"][1] - right["region"][0]) > 1e-9:
            raise RegionsDoNotTile(
                f"window {left['index']} ends {left['region'][1]}, "
                f"window {right['index']} starts {right['region'][0]}"
            )
    return out


# ---------------------------------------------------------------- word times


def word_rows_weighted(
    segments: list[Segment], source: Any, weight: Callable[[str], float]
) -> list[dict[str, Any]]:
    """`proto_context_arms.word_rows`, with the intra-segment time weighting made a parameter.

    `weight=len` is the character-proportional policy that bench already ships (and the one
    the published `.1289` was measured with); `weight=lambda _: 1.0` is uniform token time.
    """
    rows: list[dict[str, Any]] = []
    for index, segment in enumerate(sorted(segments, key=lambda item: (item.start, item.end))):
        tokens = segment.text.split()
        if not tokens:
            continue
        total = sum(weight(token) for token in tokens)
        if total <= 0:
            continue
        duration = max(segment.end - segment.start, 1e-6)
        cursor = 0.0
        for token in tokens:
            start = segment.start + duration * cursor / total
            cursor += weight(token)
            end = segment.start + duration * cursor / total
            rows.append({
                "word": token,
                "start": start,
                "end": end,
                "mid": (start + end) / 2,
                "speaker": segment.speaker,
                "src": (source, index),
            })
    return rows


WEIGHTS: dict[str, Callable[[str], float]] = {
    "char": lambda token: float(len(token)),
    "uniform": lambda token: 1.0,
    "lexical": lambda token: float(len(token)),
}


# ---------------------------------------------------------------- stitchers


def _norm(row: dict[str, Any]) -> str:
    return "".join(character for character in row["word"].lower() if character.isalnum())


def join_duplicate(committed: list[dict[str, Any]], taken: list[dict[str, Any]], limit: int = 6):
    """Longest run of >= 2 words the join publishes twice. Zero is the healthy answer."""
    for size in range(min(limit, len(committed), len(taken)), 1, -1):
        if [_norm(row) for row in committed[-size:]] == [_norm(row) for row in taken[:size]]:
            return size
    return 0


def stitch(
    policy: str,
    windows: list[dict[str, Any]],
    window_rows: list[list[dict[str, Any]]],
    base_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    """Merge the window decodes into one word sequence. Sees no reference, by construction.

    `char` / `uniform`: a word belongs to the window whose central region contains its
    midpoint. `lexical`: the cut is where the already-committed overlap text stops aligning
    with the head of the fresh window, so no interpolated clock decides ownership.
    """
    covered_lo = windows[0]["range"][0]
    covered_hi = windows[-1]["range"][1]
    merged = [
        row for row in base_rows if not covered_lo <= row["mid"] < covered_hi
    ]
    kept_base = len(merged)
    report: list[dict[str, Any]] = []
    contributed: dict[int, list[dict[str, Any]]] = {}

    for window, rows in zip(windows, window_rows):
        region_lo, region_hi = window["region"]
        before = len(merged)
        if policy == "lexical":
            if window["index"] == 0:
                taken, note = list(rows), "first_window"
            else:
                taken, note = bench.trim_prefix_by_text(
                    merged, rows, prefix_start=window["range"][0]
                )
            dropped = rows[: len(rows) - len(taken)]
        else:
            taken = [row for row in rows if region_lo <= row["mid"] < region_hi]
            dropped = [row for row in rows if not region_lo <= row["mid"] < region_hi]
            note = "central_region"
        duplicate = join_duplicate(merged, taken) if window["index"] else 0
        merged.extend(taken)
        contributed[window["index"]] = taken
        report.append({
            "window": window["index"],
            "range": window["range"],
            "region": window["region"],
            "words_available": len(rows),
            "words_taken": len(taken),
            "words_dropped": len(dropped),
            "cut": note,
            "join_duplicate_run": duplicate,
            "selected": [row["word"] for row in taken],
            "dropped": [row["word"] for row in dropped],
            "committed_before": before,
        })
    return merged, [{"kept_base_words": kept_base}] + report, contributed


# ---------------------------------------------------------------- latency floor


def correction_age_floor(
    *,
    base_spans: list[dict[str, Any]],
    windows: list[dict[str, Any]],
    base_rows: list[dict[str, Any]],
    contributed: dict[int, list[dict[str, Any]]],
    stitch_report: list[dict[str, Any]],
) -> dict[str, Any]:
    """Earliest possible age of a rolling correction, per changed word (plan §1.3 G6 floor).

    A word owned by window [lo, hi] cannot be corrected before `hi + decode(window)`; it was
    published provisionally when the 2.5 s span containing it finished decoding, at
    `span_end + decode(span)`. The difference is a FLOOR: it excludes queue wait, scheduling
    and portal render, all of which only add. Only regions whose text actually changed enter
    the distribution, which is how §1.3 defines G6.
    """
    ages: list[float] = []
    changed_regions = 0
    total_regions = 0
    for window, entry in zip(windows, stitch_report[1:]):
        region_lo, region_hi = window["region"]
        total_regions += 1
        was = [
            _norm(row) for row in base_rows if region_lo <= row["mid"] < region_hi
        ]
        now = [
            _norm(row)
            for row in contributed.get(window["index"], [])
            if region_lo <= row["mid"] < region_hi
        ]
        if was == now:
            continue
        changed_regions += 1
        rolling_ready = window["range"][1] + window["decode_seconds"]
        for row in contributed.get(window["index"], []):
            if not region_lo <= row["mid"] < region_hi:
                continue
            provisional = None
            for span in base_spans:
                if span["start_seconds"] <= row["mid"] < span["end_seconds"]:
                    provisional = span["end_seconds"] + span["decode_seconds"]
                    break
            if provisional is None:
                earlier = [
                    span for span in base_spans if span["end_seconds"] <= row["mid"]
                ]
                if not earlier:
                    continue
                span = earlier[-1]
                provisional = span["end_seconds"] + span["decode_seconds"]
            ages.append(max(0.0, rolling_ready - provisional))
    return {
        "definition": "floor: window_end + window_decode - (span_end + span_decode), changed regions only",
        "changed_regions": changed_regions,
        "total_regions": total_regions,
        "words": len(ages),
        "p50_seconds": _quantile(ages, 0.50),
        "p95_seconds": _quantile(ages, 0.95),
        "max_seconds": max(ages) if ages else None,
        "floor_exceeds_g6": (_quantile(ages, 0.95) or 0.0) > G6_SECONDS,
    }


def _quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


# ---------------------------------------------------------------- one arm


def decode_base(
    *, pcm: bytes, audio_sha: str, spans: list[dict[str, Any]], decoder: Any, scratch: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The provisional surface: the recorded live span grid, each span decoded alone."""
    rows: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    for span in spans:
        start, end = span["start_sample"], span["end_sample"]
        decoded = decoder.decode(
            pcm=pcm,
            audio_sha=audio_sha,
            start_sample=start,
            end_sample=end,
            token_cap=canonical_decode_token_cap(sample_count=end - start),
            scratch=scratch,
        )
        produced = bench.word_rows(
            bench.absolute_segments(
                decoded["transcript"], start_sample=start, end_sample=end
            ),
            span["span_id"],
        )
        rows.extend(produced)
        report.append({
            "span_id": span["span_id"],
            "start_seconds": start / SAMPLE_RATE,
            "end_seconds": end / SAMPLE_RATE,
            "decode_seconds": float(decoded["elapsed_seconds"]),
            "words": len(produced),
            "classification": decoded["classification"],
            "health": decoded["health"],
            "capped": decoded["capped"],
            "generated_tokens": decoded["generated_tokens"],
            "transcript": decoded["transcript"],
        })
    return rows, report


def decode_windows(
    *,
    pcm: bytes,
    audio_sha: str,
    windows: list[dict[str, Any]],
    decoder: Any,
    scratch: Path,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for window in windows:
        start, end = window["start_sample"], window["end_sample"]
        decoded = decoder.decode(
            pcm=pcm,
            audio_sha=audio_sha,
            start_sample=start,
            end_sample=end,
            token_cap=canonical_decode_token_cap(sample_count=end - start),
            scratch=scratch,
        )
        segments = bench.absolute_segments(
            decoded["transcript"], start_sample=start, end_sample=end
        )
        out.append({**window, "decoded": decoded, "segments": segments,
                    "decode_seconds": float(decoded["elapsed_seconds"])})
    return out


# ---------------------------------------------------------------- driver


def parse_windows(spec: str) -> list[tuple[float, float]]:
    out = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        window, _, stride = item.partition("/")
        out.append((float(window), float(stride)))
    return out


def arm_name(window: float, stride: float, policy: str) -> str:
    def fmt(value: float) -> str:
        return f"{value:g}"

    return f"{fmt(window)}/{fmt(stride)}:{policy}"


def load_baseline_scores(baseline: Path) -> dict[str, dict[str, float]]:
    """Full-precision live comparators, read from the artifact the PRD's 4 dp came from."""
    payload = json.loads((baseline / "results.json").read_text(encoding="utf-8"))
    live: dict[str, dict[str, float]] = {}
    for entry in payload["cases"]:
        arm = entry["arms"].get("live")
        if arm is None:
            continue
        live[entry["case_id"]] = {
            "wer": float(arm["scores"]["tbsa"]["wer"]),
            "tbsa": float(arm["scores"]["tbsa"]["composite"]),
        }
    for case, expected in PRD_LIVE_WER.items():
        if case not in live:
            continue
        if round(live[case]["wer"], 4) != expected:
            raise SystemExit(
                f"comparator_drift:{case}:{live[case]['wer']} does not round to {expected}"
            )
    return live


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=",".join(bench.CASES))
    parser.add_argument("--windows", default="10/5,10/10,15/7.5,15/10")
    parser.add_argument("--stitches", default=",".join(STITCHES))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--base-url", default="http://127.0.0.1:18000/v1")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    cli = parser.parse_args()

    cases = [item for item in cli.cases.split(",") if item]
    geometries = parse_windows(cli.windows)
    policies = [item for item in cli.stitches.split(",") if item]
    unknown = [item for item in policies if item not in STITCHES]
    if unknown:
        raise SystemExit(f"unknown stitch policies: {unknown}")

    model = bench.discover_model(cli.base_url, cli.timeout_seconds)
    runner = bench.VllmRunner(
        base_url=cli.base_url, model=model, api_key=None, timeout=cli.timeout_seconds
    )

    document: dict[str, Any] = {
        "schema": "moss-live-convergence-rolling-grid.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "preregistration": {
            "path": str(PREREG.relative_to(REPO)),
            "sha256": hashlib.sha256(PREREG.read_bytes()).hexdigest(),
        },
        "vllm": {"base_url": cli.base_url, "model": model, "request_concurrency": 1},
        "grid": {
            "cases": cases,
            "windows": [f"{w:g}/{s:g}" for w, s in geometries],
            "stitches": policies,
            "runs": cli.runs,
        },
        "baseline_live": load_baseline_scores(cli.baseline),
        "runs": [],
    }

    started_all = time.monotonic()
    for run_index in range(cli.runs):
        decoder = bench.Decoder(
            runner=runner,
            model=model,
            cache_path=cli.cache_dir / f"run{run_index}.json",
        )
        run_entry: dict[str, Any] = {"run": run_index, "cases": {}}
        for case in cases:
            audio_path = bench.CORPUS / case / "audio.wav"
            pcm = bench.read_pcm(audio_path)
            audio_sha = hashlib.sha256(audio_path.read_bytes()).hexdigest()
            duration = (len(pcm) // 2) / SAMPLE_RATE
            reference = bench.load_reference(case)
            spans = bench.load_baseline_spans(
                cli.baseline / case / "live" / "run-001" / "trace.jsonl"
            )
            timeline = bench.SpeakerTimeline(
                bench.load_jsonl_segments(cli.baseline / case / "live-hypothesis.jsonl")
            )
            case_entry: dict[str, Any] = {
                "duration_seconds": duration,
                "span_count": len(spans),
                "arms": {},
            }
            with tempfile.TemporaryDirectory(prefix="moss-rolling-grid-") as temporary:
                scratch = Path(temporary)
                decoder.take_accounting()
                with _TruthBlind():
                    base_rows, base_report = decode_base(
                        pcm=pcm,
                        audio_sha=audio_sha,
                        spans=spans,
                        decoder=decoder,
                        scratch=scratch,
                    )
                base_cost = decoder.take_accounting()
                base_scores = bench.score(reference, timeline.relabel(
                    bench.rows_to_segments(base_rows, duration)
                ))
                case_entry["base"] = {
                    "scores": base_scores,
                    "cost": base_cost,
                    "decode_health": bench.decode_health(base_report),
                    "spans": base_report,
                }
                print(
                    f"[run {run_index}] {case} base  wer={base_scores['wer']:.6f} "
                    f"recall={base_scores['content_recall']:.6f} "
                    f"spans={len(spans)} audio_s={base_cost['decode_audio_seconds']:.0f} "
                    f"fresh={base_cost['fresh_requests']}",
                    flush=True,
                )

                for window, stride in geometries:
                    windows = plan_windows(duration, window, stride)
                    decoder.take_accounting()
                    with _TruthBlind():
                        decoded_windows = decode_windows(
                            pcm=pcm,
                            audio_sha=audio_sha,
                            windows=windows,
                            decoder=decoder,
                            scratch=scratch,
                        )
                    window_cost = decoder.take_accounting()
                    for policy in policies:
                        name = arm_name(window, stride, policy)
                        with _TruthBlind():
                            window_rows = [
                                word_rows_weighted(
                                    entry["segments"], f"w{entry['index']}", WEIGHTS[policy]
                                )
                                for entry in decoded_windows
                            ]
                            merged, report, contributed = stitch(
                                policy, decoded_windows, window_rows, base_rows
                            )
                            segments = bench.rows_to_segments(merged, duration)
                        latency = correction_age_floor(
                            base_spans=base_report,
                            windows=decoded_windows,
                            base_rows=base_rows,
                            contributed=contributed,
                            stitch_report=report,
                        )
                        scores = bench.score(reference, timeline.relabel(segments))
                        arm_audio = window_cost["decode_audio_seconds"]
                        case_entry["arms"][name] = {
                            "window_seconds": window,
                            "stride_seconds": stride,
                            "stitch": policy,
                            "scores": scores,
                            "joins": len(windows) - 1,
                            "window_count": len(windows),
                            "cost": {
                                **window_cost,
                                "added_decode_audio_seconds_per_audio_second": (
                                    arm_audio / duration
                                ),
                                "rolling_pcm_high_water_bytes": int(
                                    window * SAMPLE_RATE * 2
                                ),
                                "decode_rtf_contended": (
                                    window_cost["wall_seconds_contended"] / duration
                                ),
                            },
                            "join_duplicates": sum(
                                1 for item in report[1:] if item["join_duplicate_run"]
                            ),
                            "correction_age_floor": latency,
                            "decode_health": bench.decode_health(
                                [
                                    {
                                        "health": entry["decoded"]["health"],
                                        "classification": entry["decoded"]["classification"],
                                    }
                                    for entry in decoded_windows
                                ]
                            ),
                            "stitch_report": report,
                            "hypothesis": [
                                {
                                    "start": s.start,
                                    "end": s.end,
                                    "speaker": s.speaker,
                                    "text": s.text,
                                }
                                for s in timeline.relabel(segments)
                            ],
                        }
                        print(
                            f"[run {run_index}] {case} {name:>16}  "
                            f"wer={scores['wer']:.6f} recall={scores['content_recall']:.6f} "
                            f"tbsa={scores['tbsa']:.4f} der={scores['der']:.4f} "
                            f"win={len(windows)} added={arm_audio / duration:.3f}x "
                            f"dup={sum(1 for i in report[1:] if i['join_duplicate_run'])} "
                            f"corr_p95={latency['p95_seconds']}",
                            flush=True,
                        )
            run_entry["cases"][case] = case_entry
            document["runs"] = [
                item for item in document["runs"] if item["run"] != run_index
            ] + [run_entry]
            cli.output.parent.mkdir(parents=True, exist_ok=True)
            cli.output.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

    document["elapsed_seconds"] = time.monotonic() - started_all
    document["summary"] = summarise(document, cases)
    cli.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report_summary(document["summary"])
    return 0 if document["summary"]["verdict"]["exit_ok"] else 1


# ---------------------------------------------------------------- summary


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def summarise(document: dict[str, Any], cases: list[str]) -> dict[str, Any]:
    runs = document["runs"]
    live = document["baseline_live"]

    def across(getter: Callable[[dict[str, Any]], float], name: str | None) -> dict[str, Any]:
        per_run = []
        for run in runs:
            values = []
            for case in cases:
                entry = run["cases"].get(case)
                if entry is None:
                    continue
                node = entry["base"] if name is None else entry["arms"].get(name)
                if node is None:
                    continue
                values.append(getter(node))
            if values:
                per_run.append(_mean(values))
        return {
            "per_run": per_run,
            "mean": _mean(per_run),
            "spread": (max(per_run) - min(per_run)) if len(per_run) > 1 else 0.0,
        }

    base = {
        "wer": across(lambda node: node["scores"]["wer"], None),
        "content_recall": across(lambda node: node["scores"]["content_recall"], None),
    }
    bench_valid = (
        abs(base["wer"]["mean"] - PUBLISHED_LIVE_TRIO["wer"]) <= BENCH_TOLERANCE
        and abs(base["content_recall"]["mean"] - PUBLISHED_LIVE_TRIO["content_recall"])
        <= BENCH_TOLERANCE
    )

    names: list[str] = []
    for run in runs:
        for case in cases:
            for name in run["cases"].get(case, {}).get("arms", {}):
                if name not in names:
                    names.append(name)

    arms: dict[str, Any] = {}
    for name in names:
        wer = across(lambda node: node["scores"]["wer"], name)
        recall = across(lambda node: node["scores"]["content_recall"], name)
        per_case: dict[str, Any] = {}
        for case in cases:
            values = [
                run["cases"][case]["arms"][name]["scores"]["wer"]
                for run in runs
                if name in run["cases"].get(case, {}).get("arms", {})
            ]
            per_case[case] = {
                "wer_mean": _mean(values),
                "wer_per_run": values,
                "live_comparator": live[case]["wer"],
                "improves": _mean(values) < live[case]["wer"],
            }
        sample = next(
            run["cases"][case]["arms"][name]
            for run in runs
            for case in cases
            if name in run["cases"].get(case, {}).get("arms", {})
        )
        added = _mean([
            run["cases"][case]["arms"][name]["cost"][
                "added_decode_audio_seconds_per_audio_second"
            ]
            for run in runs
            for case in cases
            if name in run["cases"].get(case, {}).get("arms", {})
        ])
        duplicates = sum(
            run["cases"][case]["arms"][name]["join_duplicates"]
            for run in runs
            for case in cases
            if name in run["cases"].get(case, {}).get("arms", {})
        )
        p95 = [
            run["cases"][case]["arms"][name]["correction_age_floor"]["p95_seconds"]
            for run in runs
            for case in cases
            if name in run["cases"].get(case, {}).get("arms", {})
            and run["cases"][case]["arms"][name]["correction_age_floor"]["p95_seconds"]
            is not None
        ]
        gates = {
            "G1_wer_mean": wer["mean"] <= GATE_WER_MAX,
            "G2_per_case_improves": all(item["improves"] for item in per_case.values()),
            "G3_recall_mean": recall["mean"] >= GATE_RECALL_MIN,
        }
        arms[name] = {
            "window_seconds": sample["window_seconds"],
            "stride_seconds": sample["stride_seconds"],
            "stitch": sample["stitch"],
            "windows_per_case": sample["window_count"],
            "joins_per_case": sample["joins"],
            "wer": wer,
            "content_recall": recall,
            "per_case": per_case,
            "added_decode_audio_seconds_per_audio_second": added,
            "rolling_pcm_high_water_bytes": sample["cost"]["rolling_pcm_high_water_bytes"],
            "join_duplicates": duplicates,
            "correction_age_floor_p95_max": max(p95) if p95 else None,
            "gates": gates,
            "passes": all(gates.values()),
        }

    passing = [name for name, item in arms.items() if item["passes"]]
    selected = None
    if bench_valid and passing:
        selected = sorted(
            passing,
            key=lambda name: (
                arms[name]["added_decode_audio_seconds_per_audio_second"],
                arms[name]["joins_per_case"],
                arms[name]["wer"]["mean"],
                name,
            ),
        )[0]

    return {
        "base_control": {
            **base,
            "published": PUBLISHED_LIVE_TRIO,
            "tolerance": BENCH_TOLERANCE,
            "P1_bench_valid": bench_valid,
        },
        "reproduction_control": _reproduction(arms),
        "zero_overlap_identity": _zero_overlap(document, cases),
        "arms": arms,
        "verdict": {
            "passing_arms": passing,
            "selected_arm": selected,
            "selection_rule": "cheapest arm passing G1-G3 (plan §10.4); ties by fewer joins, then WER",
            "exit_ok": bool(bench_valid and selected),
        },
    }


def _reproduction(arms: dict[str, Any]) -> dict[str, Any]:
    name = "10/5:char"
    if name not in arms:
        return {"checked": False}
    return {
        "checked": True,
        "arm": name,
        "published": PUBLISHED_A2_10_5,
        "measured": {
            "wer": arms[name]["wer"]["mean"],
            "content_recall": arms[name]["content_recall"]["mean"],
        },
        "P2_within_tolerance": (
            abs(arms[name]["wer"]["mean"] - PUBLISHED_A2_10_5["wer"]) <= BENCH_TOLERANCE
            and abs(
                arms[name]["content_recall"]["mean"] - PUBLISHED_A2_10_5["content_recall"]
            )
            <= BENCH_TOLERANCE
        ),
    }


def _zero_overlap(document: dict[str, Any], cases: list[str]) -> dict[str, Any]:
    """P3: where stride == window there is no overlap, so all three policies must agree."""
    checks: list[dict[str, Any]] = []
    for run in document["runs"]:
        for case in cases:
            arms = run["cases"].get(case, {}).get("arms", {})
            by_geometry: dict[str, list[str]] = {}
            for name, item in arms.items():
                if item["window_seconds"] != item["stride_seconds"]:
                    continue
                key = f"{item['window_seconds']:g}/{item['stride_seconds']:g}"
                by_geometry.setdefault(key, []).append(name)
            for key, names in by_geometry.items():
                wers = {arms[name]["scores"]["wer"] for name in names}
                recalls = {arms[name]["scores"]["content_recall"] for name in names}
                checks.append({
                    "run": run["run"],
                    "case": case,
                    "geometry": key,
                    "arms": sorted(names),
                    "identical": len(wers) == 1 and len(recalls) == 1,
                    "wer_values": sorted(wers),
                })
    return {
        "checks": checks,
        "P3_identical": all(item["identical"] for item in checks) if checks else None,
    }


def report_summary(summary: dict[str, Any]) -> None:
    base = summary["base_control"]
    print("\n=== base control (P1) ===", flush=True)
    print(
        f"  wer {base['wer']['mean']:.6f} (published {base['published']['wer']}) "
        f"recall {base['content_recall']['mean']:.6f} "
        f"(published {base['published']['content_recall']}) -> "
        f"{'VALID' if base['P1_bench_valid'] else 'INVALID'}"
    )
    repro = summary["reproduction_control"]
    if repro.get("checked"):
        print(
            f"=== reproduction control (P2) {repro['arm']} ===\n"
            f"  wer {repro['measured']['wer']:.6f} (published {repro['published']['wer']}) "
            f"recall {repro['measured']['content_recall']:.6f} "
            f"(published {repro['published']['content_recall']}) -> "
            f"{'OK' if repro['P2_within_tolerance'] else 'MISS'}"
        )
    zero = summary["zero_overlap_identity"]
    print(f"=== zero-overlap identity (P3) === {zero['P3_identical']}")
    print("\n=== arms (mean over runs) ===")
    header = (
        f"{'arm':>16} {'wer':>9} {'recall':>8} {'added':>7} {'joins':>5} "
        f"{'dup':>4} {'corr_p95':>9} {'G1':>3} {'G2':>3} {'G3':>3}"
    )
    print(header)
    order = sorted(
        summary["arms"],
        key=lambda name: (
            summary["arms"][name]["added_decode_audio_seconds_per_audio_second"],
            name,
        ),
    )
    for name in order:
        item = summary["arms"][name]
        gates = item["gates"]
        p95 = item["correction_age_floor_p95_max"]
        print(
            f"{name:>16} {item['wer']['mean']:9.6f} {item['content_recall']['mean']:8.4f} "
            f"{item['added_decode_audio_seconds_per_audio_second']:7.3f} "
            f"{item['joins_per_case']:5d} {item['join_duplicates']:4d} "
            f"{(f'{p95:.2f}' if p95 is not None else '-'):>9} "
            f"{'Y' if gates['G1_wer_mean'] else 'n':>3} "
            f"{'Y' if gates['G2_per_case_improves'] else 'n':>3} "
            f"{'Y' if gates['G3_recall_mean'] else 'n':>3}"
        )
    verdict = summary["verdict"]
    print(f"\npassing arms: {verdict['passing_arms']}")
    print(f"SELECTED (plan §10.4): {verdict['selected_arm']}")


if __name__ == "__main__":
    raise SystemExit(main())
