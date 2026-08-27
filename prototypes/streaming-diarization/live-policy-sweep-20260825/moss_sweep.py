#!/usr/bin/env python3
"""Run the preregistered MOSS actual-live and 15/10 shadow sweep."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import math
import socket
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CONVERGENCE = HERE.parent / "live-convergence"
CONTEXT = REPO / "prototypes/live-file-gap-context"
SURFACE_SCRIPT = HERE.parent / "live-surface-optimization/measure_three_surfaces.py"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(CONVERGENCE))
sys.path.insert(0, str(CONTEXT))

import compare_rolling_grid as rolling  # noqa: E402
import proto_context_arms as bench  # noqa: E402
from moss_transcribe_diarize import live_service_replay as replay  # noqa: E402
from moss_transcribe_diarize import live_speaker_accuracy as lsa  # noqa: E402
from moss_transcribe_diarize.app.live_adapters import canonical_decode_token_cap  # noqa: E402
from moss_transcribe_diarize.evaluation import Segment  # noqa: E402

_SPEC = importlib.util.spec_from_file_location("live_surface_measurement", SURFACE_SCRIPT)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load {SURFACE_SCRIPT}")
surface = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = surface
_SPEC.loader.exec_module(surface)

SAMPLE_RATE = 16_000
DEPLOYED_CODE_REVISION = "22dc5b8de3ed31a94dcb1b93d2256f8cb8ac75d8"
CASE_ORDER = (
    "mono_javier_intro_50s",
    "interview_bill_ackman_60s",
    "interview_keyu_jin_60s",
    "interview_adam_frank_180s",
    "discussion_jamie_dimon_180s",
    "discussion_rtfl_90s",
)
QUALITY_FIELDS = surface.QUALITY_FIELDS
DRIFT_LIMIT = 0.75


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log(message: str) -> None:
    print(f"[{utc_now()}] {message}", flush=True)


def dump(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows_of(segments: list[Segment] | tuple[Segment, ...]) -> list[dict[str, Any]]:
    return [
        {"start": row.start, "end": row.end, "speaker": row.speaker, "text": row.text}
        for row in segments
    ]


def as_segments(rows: list[dict[str, Any]]) -> list[Segment]:
    return [
        Segment(float(row["start"]), float(row["end"]), str(row["speaker"]), str(row.get("text") or ""))
        for row in rows
        if float(row["end"]) > float(row["start"]) and str(row.get("text") or "").strip()
    ]


def plan_live_windows(duration: float, window: float, stride: float) -> list[dict[str, Any]]:
    out = []
    index = 0
    while index * stride + window <= duration + 1e-9:
        lo = index * stride
        hi = lo + window
        out.append({
            "index": index,
            "start_sample": int(round(lo * SAMPLE_RATE)),
            "end_sample": int(round(hi * SAMPLE_RATE)),
            "range": [lo, hi],
            "region": [lo, hi],
        })
        index += 1
    return out


def norm(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def align(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[tuple[int | None, int | None]]:
    rows, cols = len(left) + 1, len(right) + 1
    cost = [[0.0] * cols for _ in range(rows)]
    move = [[""] * cols for _ in range(rows)]
    for i in range(1, rows):
        cost[i][0], move[i][0] = float(i), "up"
    for j in range(1, cols):
        cost[0][j], move[0][j] = float(j), "left"
    for i in range(1, rows):
        for j in range(1, cols):
            exact = norm(left[i - 1]["word"]) == norm(right[j - 1]["word"])
            drift = abs(left[i - 1]["mid"] - right[j - 1]["mid"])
            candidates = (
                (cost[i - 1][j - 1] + (min(drift / DRIFT_LIMIT, 1.0) * 0.1 if exact else 2.0), "diag"),
                (cost[i - 1][j] + 1.0, "up"),
                (cost[i][j - 1] + 1.0, "left"),
            )
            cost[i][j], move[i][j] = min(
                candidates, key=lambda item: (item[0], {"diag": 0, "up": 1, "left": 2}[item[1]])
            )
    out: list[tuple[int | None, int | None]] = []
    i, j = len(left), len(right)
    while i or j:
        chosen = move[i][j]
        if chosen == "diag":
            out.append((i - 1, j - 1)); i -= 1; j -= 1
        elif chosen == "up":
            out.append((i - 1, None)); i -= 1
        else:
            out.append((None, j - 1)); j -= 1
    return list(reversed(out))


def stable_anchor_stitch(
    windows: list[dict[str, Any]], window_rows: list[list[dict[str, Any]]], base_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not windows:
        return list(base_rows), []
    merged = list(window_rows[0])
    reports: list[dict[str, Any]] = []
    for index in range(1, len(windows)):
        fresh = window_rows[index]
        lo, hi = windows[index]["range"][0], windows[index - 1]["range"][1]
        left = [row for row in merged if lo <= row["mid"] < hi]
        right = [row for row in fresh if lo <= row["mid"] < hi]
        exact = [
            (i, j) for i, j in align(left, right)
            if i is not None and j is not None
            and norm(left[i]["word"]) == norm(right[j]["word"])
            and abs(left[i]["mid"] - right[j]["mid"]) <= DRIFT_LIMIT
        ]
        midpoint = (lo + hi) / 2
        anchor = min(
            exact,
            key=lambda pair: (
                abs(((left[pair[0]]["mid"] + right[pair[1]]["mid"]) / 2) - midpoint),
                abs(left[pair[0]]["mid"] - right[pair[1]]["mid"]),
                pair,
            ),
            default=None,
        )
        if anchor is None:
            merged = [row for row in merged if row["mid"] < midpoint]
            merged.extend(row for row in fresh if row["mid"] >= midpoint)
            reports.append({"join": index, "overlap": [lo, hi], "valid_anchors": 0, "decision": "central_time_fallback", "cut_time": midpoint})
        else:
            left_anchor, right_anchor = left[anchor[0]], right[anchor[1]]
            left_position = next(i for i, row in enumerate(merged) if row is left_anchor)
            right_position = next(i for i, row in enumerate(fresh) if row is right_anchor)
            merged = merged[:left_position + 1] + fresh[right_position + 1:]
            reports.append({
                "join": index,
                "overlap": [lo, hi],
                "valid_anchors": len(exact),
                "decision": "stable_anchor_once",
                "anchor_word": left_anchor["word"],
                "cut_time": (left_anchor["mid"] + right_anchor["mid"]) / 2,
            })
    covered_hi = windows[-1]["range"][1]
    merged.extend(row for row in base_rows if row["mid"] >= covered_hi)
    return merged, reports


def lexical_stitch(
    windows: list[dict[str, Any]], window_rows: list[list[dict[str, Any]]], base_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not windows:
        return list(base_rows), []
    merged: list[dict[str, Any]] = []
    reports = []
    for index, (window, fresh) in enumerate(zip(windows, window_rows)):
        if index == 0:
            taken, note = list(fresh), "first_window"
        else:
            taken, note = bench.trim_prefix_by_text(merged, fresh, prefix_start=window["range"][0])
        reports.append({"join": index, "range": window["range"], "words_available": len(fresh), "words_taken": len(taken), "decision": note})
        merged.extend(taken)
    covered_hi = windows[-1]["range"][1]
    merged.extend(row for row in base_rows if row["mid"] >= covered_hi)
    return merged, reports


def project_and_group(rows: list[dict[str, Any]], timeline: bench.SpeakerTimeline, duration: float) -> list[dict[str, Any]]:
    segments = bench.rows_to_segments(rows, duration)
    return rows_of(timeline.relabel(segments))


def schedule(windows: list[dict[str, Any]]) -> dict[str, Any]:
    completion = 0.0
    rows = []
    for window in windows:
        ready = float(window["range"][1])
        completion = max(ready, completion) + float(window["decode_seconds"])
        rows.append({
            "window": window["index"],
            "range": window["range"],
            "audio_ready_seconds": ready,
            "decode_seconds": float(window["decode_seconds"]),
            "completion_seconds": completion,
            "ready_to_completion_seconds": completion - ready,
        })
    return {"windows": rows, "settled_completion_seconds": completion}


def token_speaker_pairs(rows: list[dict[str, Any]], end: float) -> list[list[str]]:
    words = bench.word_rows(as_segments(rows), "differential")
    return [[norm(row["word"]), str(row["speaker"])] for row in words if row["mid"] < end and norm(row["word"])]


def decode_geometry(
    *, pcm: bytes, audio_sha: str, duration: float, geometry: tuple[float, float], decoder: Any, scratch: Path
) -> list[dict[str, Any]]:
    windows = plan_live_windows(duration, *geometry)
    return rolling.decode_windows(pcm=pcm, audio_sha=audio_sha, windows=windows, decoder=decoder, scratch=scratch)


def capture_actual(case_id: str, corpus: Path, run_dir: Path, runtime: dict[str, Any], settle_timeout: float) -> dict[str, Any]:
    case_dir = corpus / case_id
    case = surface.Case(case_id, case_dir, case_dir / "unused-comparator.jsonl")
    audio = surface.wav_facts(case.audio)
    service = surface.SurfaceCaptureService(
        replay.HttpLiveReplayService(
            base_url=surface.BASE_URL,
            bearer_token=surface.TOKEN_PATH.read_text(encoding="utf-8").strip(),
        ),
        settle_timeout=settle_timeout,
        poll_seconds=0.1,
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    live_dir = run_dir / "live-replay"
    descriptor = runtime["live"]["descriptor"]
    log(f"actual START case={case_id} duration={audio['duration_seconds']:.4f}s")
    replay_gate_failure = None
    try:
        replay.run_service_replay(
            service=service,
            audio_path=case.audio,
            out_dir=live_dir,
            pace=1.0,
            max_pacing_lag=3.0,
            runs=1,
            expect_revision=descriptor["source_revision"],
            expect_provider_hash=descriptor["provider_manifest_hash"],
            expect_config_hash=descriptor["config_hashes"]["combined_config_hash"],
        )
    except replay.ServiceReplayRtfFailure as exc:
        # The replay has already retained its complete trace and terminal snapshot. Preserve
        # every observed surface and make the stress failure data, rather than dropping the case.
        replay_gate_failure = {"kind": "canonical_decode_rtf", "message": str(exc)}
        log(f"actual STRESS_GATE_FAIL case={case_id} {exc}")
    trace = live_dir / "run-001/trace.jsonl"
    events = surface.read_service_events(trace)
    if "post_stop_final" not in service.captures:
        for line in trace.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("kind") == "terminal" and row.get("snapshot"):
                service._capture("post_stop_final", replay._snapshot_from_dict(row["snapshot"]))
    required = ("pre_stop_immediate", "pre_stop_settled", "stop_return", "post_stop_final")
    missing = [name for name in required if name not in service.captures]
    if missing:
        raise RuntimeError(f"missing actual-live surfaces {case_id}: {missing}")
    dump_jsonl(run_dir / "events.jsonl", events)
    dump_jsonl(run_dir / "snapshots.jsonl", [service.captures[name] for name in required])
    rows_by_surface = {}
    scores = {}
    for name in required:
        rows = surface.transcript_rows(service.captures[name]["snapshot"], audio["duration_seconds"])
        rows_by_surface[name] = rows
        dump_jsonl(run_dir / f"{name}.jsonl", rows)
        scores[name] = surface.score_surface(case, rows)
    metrics = surface.event_measurements(
        events,
        service.captures["pre_stop_settled"]["snapshot"],
        service.captures["post_stop_final"],
        service.stop_requested_monotonic_ns,
        audio["duration_seconds"],
    )
    final_session = service.captures["post_stop_final"]["snapshot"]["session"]
    result = {
        "case_id": case_id,
        "duration_seconds": audio["duration_seconds"],
        "audio": audio,
        "reference_sha256": sha256(case.reference),
        "surface_scores": scores,
        "surface_sha256": {name: sha256(run_dir / f"{name}.jsonl") for name in required},
        "surface_clocks": {
            name: {key: value for key, value in service.captures[name].items() if key != "snapshot"}
            for name in required
        },
        "events": metrics,
        "sample_accounting": {
            "accepted_samples": final_session["accepted_samples"],
            "accounted_samples": final_session["accounted_samples"],
            "exact": final_session["accepted_samples"] == final_session["accounted_samples"],
        },
        "replay_gate_failure": replay_gate_failure,
    }
    dump(run_dir / "actual-result.json", result)
    log(
        f"actual DONE case={case_id} immediate_WER={scores['pre_stop_immediate']['wer']:.4f} "
        f"settled_WER={scores['pre_stop_settled']['wer']:.4f} final_WER={scores['post_stop_final']['wer']:.4f}"
    )
    return result


def make_shadow(
    *, case_id: str, corpus: Path, actual_dir: Path, shadow_dir: Path, decoder: Any
) -> dict[str, Any]:
    case_dir = corpus / case_id
    case = surface.Case(case_id, case_dir, case_dir / "unused-comparator.jsonl")
    facts = surface.wav_facts(case.audio)
    duration = float(facts["duration_seconds"])
    pcm = bench.read_pcm(case.audio)
    captures = {
        row["surface"]: row
        for row in (json.loads(line) for line in (actual_dir / "snapshots.jsonl").read_text(encoding="utf-8").splitlines())
    }
    settled_session = captures["pre_stop_settled"]["snapshot"]["session"]
    base_segments = list(lsa._hypothesis_from_committed(settled_session, corpus_start_sample=0, corpus_duration_sec=duration))
    base_rows = bench.word_rows(
        [Segment(row.start, row.end, row.speaker, row.text) for row in base_segments], "base"
    )
    settled_rows = surface.transcript_rows(captures["pre_stop_settled"]["snapshot"], duration)
    timeline = bench.SpeakerTimeline(as_segments(settled_rows))
    shadow_dir.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix=f"moss-shadow-{case_id}-") as scratch_name:
        scratch = Path(scratch_name)
        decoded_10 = decode_geometry(
            pcm=pcm, audio_sha=facts["wav_sha256"], duration=duration, geometry=(10.0, 10.0), decoder=decoder, scratch=scratch
        )
        decoded_15 = decode_geometry(
            pcm=pcm, audio_sha=facts["wav_sha256"], duration=duration, geometry=(15.0, 10.0), decoder=decoder, scratch=scratch
        )
    schedule_10, schedule_15 = schedule(decoded_10), schedule(decoded_15)
    word_10 = [rolling.word_rows_weighted(window["segments"], window["index"], lambda token: float(len(token))) for window in decoded_10]
    word_15 = [rolling.word_rows_weighted(window["segments"], window["index"], lambda token: float(len(token))) for window in decoded_15]

    external_10_words = [row for group in word_10 for row in group]
    external_10 = project_and_group(external_10_words, timeline, duration)
    covered_10 = decoded_10[-1]["range"][1] if decoded_10 else 0.0
    actual_pairs = token_speaker_pairs(settled_rows, covered_10)
    external_pairs = token_speaker_pairs(external_10, covered_10)
    differential = {
        "covered_through_seconds": covered_10,
        "actual_token_speaker_pairs": len(actual_pairs),
        "external_token_speaker_pairs": len(external_pairs),
        "content_and_speaker_exact": actual_pairs == external_pairs,
        "actual_tokens": [pair[0] for pair in actual_pairs],
        "external_tokens": [pair[0] for pair in external_pairs],
        "actual_speakers": [pair[1] for pair in actual_pairs],
        "external_speakers": [pair[1] for pair in external_pairs],
    }

    outputs: dict[str, Any] = {}
    for surface_name, admitted in (
        ("pre_stop_immediate", sum(row["completion_seconds"] <= duration + 1e-9 for row in schedule_15["windows"])),
        ("pre_stop_settled", len(decoded_15)),
    ):
        windows = decoded_15[:admitted]
        window_rows = word_15[:admitted]
        lexical_rows, lexical_report = lexical_stitch(windows, window_rows, base_rows)
        stable_rows, stable_report = stable_anchor_stitch(windows, window_rows, base_rows)
        for policy, merged, report in (
            ("15_10_lexical_speaker_map", lexical_rows, lexical_report),
            ("15_10_stable_anchor", stable_rows, stable_report),
        ):
            rows = project_and_group(merged, timeline, duration)
            name = f"{policy}-{surface_name}"
            dump_jsonl(shadow_dir / f"{name}.jsonl", rows)
            outputs[name] = {
                "surface": surface_name,
                "policy": policy,
                "admitted_windows": admitted,
                "rows_file": f"{name}.jsonl",
                "rows_sha256": sha256(shadow_dir / f"{name}.jsonl"),
                "scores": surface.score_surface(case, rows),
                "stitch_report": report,
            }
    result = {
        "case_id": case_id,
        "duration_seconds": duration,
        "differential_10_10": differential,
        "schedules": {"10_10": schedule_10, "15_10": schedule_15},
        "decode": {
            "10_10_requests": len(decoded_10),
            "15_10_requests": len(decoded_15),
            "10_10_audio_seconds": sum(window["range"][1] - window["range"][0] for window in decoded_10),
            "15_10_audio_seconds": sum(window["range"][1] - window["range"][0] for window in decoded_15),
            "10_10_wall_seconds": sum(float(window["decode_seconds"]) for window in decoded_10),
            "15_10_wall_seconds": sum(float(window["decode_seconds"]) for window in decoded_15),
        },
        "outputs": outputs,
    }
    dump(shadow_dir / "shadow-result.json", result)
    log(
        f"shadow DONE case={case_id} differential={differential['content_and_speaker_exact']} "
        f"lex_settled_WER={outputs['15_10_lexical_speaker_map-pre_stop_settled']['scores']['wer']:.4f} "
        f"anchor_settled_WER={outputs['15_10_stable_anchor-pre_stop_settled']['scores']['wer']:.4f}"
    )
    return result


def aggregate(actual: list[dict[str, Any]], shadows: list[dict[str, Any]]) -> dict[str, Any]:
    observations: dict[str, list[tuple[float, dict[str, Any], str]]] = defaultdict(list)
    categories = json.loads((Path(actual[0]["audio"]["path"]).parents[1] / "corpus-manifest.json").read_text(encoding="utf-8"))
    category_of = {row["case_id"]: row["category"] for row in categories["cases"]}
    for row in actual:
        for name in ("pre_stop_immediate", "pre_stop_settled", "post_stop_final"):
            observations[f"current_10_10:{name}"].append((row["duration_seconds"], row["surface_scores"][name], category_of[row["case_id"]]))
    for row in shadows:
        for name, output in row["outputs"].items():
            observations[f"{output['policy']}:{output['surface']}"] .append((row["duration_seconds"], output["scores"], category_of[row["case_id"]]))
    result = {}
    for arm, rows in observations.items():
        total = sum(duration for duration, _, _ in rows)
        macro = {field: sum(scores[field] for _, scores, _ in rows) / len(rows) for field in QUALITY_FIELDS}
        weighted = {field: sum(duration * scores[field] for duration, scores, _ in rows) / total for field in QUALITY_FIELDS}
        by_category = {}
        for category in sorted({category for _, _, category in rows}):
            subset = [scores for _, scores, item_category in rows if item_category == category]
            by_category[category] = {field: sum(scores[field] for scores in subset) / len(subset) for field in QUALITY_FIELDS}
        result[arm] = {
            "macro_mean": macro,
            "duration_weighted_mean": weighted,
            "category_macro": by_category,
            "denominator": {"observations": len(rows), "audio_seconds": total},
        }
    return result


def validate(corpus: Path) -> dict[str, Any]:
    manifest = json.loads((corpus / "corpus-manifest.json").read_text(encoding="utf-8"))
    if tuple(row["case_id"] for row in manifest["cases"]) != CASE_ORDER:
        raise RuntimeError("corpus case order differs from preregistration")
    if not surface.TOKEN_PATH.is_file():
        raise RuntimeError(f"missing MOSS live token: {surface.TOKEN_PATH}")
    subprocess.run(["git", "cat-file", "-e", f"{DEPLOYED_CODE_REVISION}^{{commit}}"], cwd=REPO, check=True)
    runtime = surface.runtime_descriptor()
    descriptor = runtime.get("live", {}).get("descriptor") or {}
    if not descriptor.get("feature_enabled"):
        raise RuntimeError("deployed live refinement is disabled")
    model = bench.discover_model("http://127.0.0.1:18000/v1", 30.0)
    return {"manifest": manifest, "runtime": runtime, "shadow_model": model}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--settle-timeout", type=float, default=30.0)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--actual-only",
        action="store_true",
        help="run only the deployed 10/10 live control; preserve the default shadow matrix",
    )
    args = parser.parse_args()
    if args.passes not in {1, 2}:
        raise SystemExit("passes must be 1 or 2")
    corpus = args.corpus.resolve()
    state = validate(corpus)
    log(
        f"validation PASS cases={state['manifest']['denominator']['cases']} "
        f"audio_seconds={state['manifest']['denominator']['audio_seconds']} model={state['shadow_model']}"
    )
    if args.validate_only:
        return 0
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    dump(out / "runtime-start.json", state["runtime"])
    surface.warm_decoder(out)
    runner = None
    if not args.actual_only:
        runner = bench.VllmRunner(
            base_url="http://127.0.0.1:18000/v1",
            model=state["shadow_model"],
            api_key=None,
            timeout=180.0,
        )
    all_actual, all_shadow = [], []
    for pass_index in range(args.passes):
        pass_name = chr(ord("A") + pass_index)
        ordered = CASE_ORDER if pass_index % 2 == 0 else tuple(reversed(CASE_ORDER))
        pass_dir = out / f"pass-{pass_name}"
        pass_dir.mkdir()
        for case_id in ordered:
            actual_dir = pass_dir / case_id / "actual"
            actual = capture_actual(case_id, corpus, actual_dir, state["runtime"], args.settle_timeout)
            all_actual.append({"pass": pass_name, **actual})
        if not args.actual_only:
            cache = out / "shadow-cache" / f"pass-{pass_name}.json"
            if cache.exists():
                raise RuntimeError(f"shadow cache was not absent at pass start: {cache}")
            decoder = bench.Decoder(
                runner=runner, model=state["shadow_model"], cache_path=cache
            )
            for case_id in ordered:
                actual_dir = pass_dir / case_id / "actual"
                shadow = make_shadow(
                    case_id=case_id,
                    corpus=corpus,
                    actual_dir=actual_dir,
                    shadow_dir=pass_dir / case_id / "shadow",
                    decoder=decoder,
                )
                all_shadow.append({"pass": pass_name, **shadow})
            accounting = decoder.take_accounting()
            if accounting["fresh_requests"] != accounting["requests"]:
                raise RuntimeError(
                    f"pass {pass_name} used a pre-existing shadow decode: {accounting}"
                )
            dump(pass_dir / "shadow-accounting.json", accounting)
    runtime_end = surface.runtime_descriptor()
    dump(out / "runtime-end.json", runtime_end)
    common_checks = {
        "runtime_descriptor_unchanged": (
            runtime_end["live"]["descriptor"] == state["runtime"]["live"]["descriptor"]
        ),
        "exact_sample_accounting": all(
            row["sample_accounting"]["exact"] for row in all_actual
        ),
        "pre_stop_combined_rtf_lt_1": all(
            row["events"]["rtf"]["pre_stop_combined"] < 1 for row in all_actual
        ),
        "rolling_queue_clean": all(
            row["events"]["rolling_queue"]["max_depth"] <= 1
            and row["events"]["rolling_queue"]["final_depth"] == 0
            and row["events"]["rolling_queue"]["admission_refusals"] == 0
            and row["events"]["rolling_queue"]["stale_completions"] == 0
            and row["events"]["rolling_queue"]["failed_windows"] == 0
            for row in all_actual
        ),
        "terminal_failures_zero": all(
            not row["events"]["terminal_failures"] for row in all_actual
        ),
    }
    if args.actual_only:
        expected_windows = {
            row["case_id"]: int(row["audio"]["samples"]) // 160_000
            for row in state["manifest"]["cases"]
        }
        checks = {
            **common_checks,
            "actual_sessions_exact": len(all_actual) == args.passes * len(CASE_ORDER),
            "observed_audio_seconds_exact": math.isclose(
                sum(row["duration_seconds"] for row in all_actual),
                args.passes * state["manifest"]["denominator"]["audio_seconds"],
                abs_tol=1e-9,
            ),
            "full_rolling_grid": all(
                [item["window_index"] for item in row["events"]["rolling_queue"]["windows"]]
                == list(range(expected_windows[row["case_id"]]))
                and all(
                    item["outcome"] == "applied"
                    for item in row["events"]["rolling_queue"]["windows"]
                )
                for row in all_actual
            ),
            "rolling_refusals_zero": all(
                row["events"]["rolling_queue"]["proposal_refusals"] == 0
                and not row["events"]["rolling_queue"]["text_revision_refusals"]
                for row in all_actual
            ),
            "pcm_evicted_zero": all(
                row["events"]["rolling_queue"]["status_counts"].get("pcm_evicted", 0)
                == 0
                for row in all_actual
            ),
        }
    else:
        checks = {
            **common_checks,
            "production_10_10_differential": all(
                row["differential_10_10"]["content_and_speaker_exact"]
                for row in all_shadow
            ),
            "strict_replay_gate_failures_zero": all(
                row.get("replay_gate_failure") is None for row in all_actual
            ),
        }
    results = {
        "schema": "moss-live-policy-sweep.v1",
        "created_utc": utc_now(),
        "host": socket.gethostname(),
        "preregistration_sha256": sha256(HERE / "PREREGISTRATION.md"),
        "denominator": {
            "passes": args.passes,
            "cases": len(CASE_ORDER),
            "actual_sessions": len(all_actual),
            "observed_audio_seconds": sum(row["duration_seconds"] for row in all_actual),
        },
        "actual": all_actual,
        "shadows": all_shadow,
        "aggregate": aggregate(all_actual, all_shadow),
        "checks": checks,
    }
    if args.actual_only:
        results["mode"] = "actual_only"
    dump(out / "moss-results.json", results)
    log(f"MOSS RESULTS {out / 'moss-results.json'}")
    log(f"CHECKS {json.dumps(checks, sort_keys=True)}")
    return 0 if all(checks.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
