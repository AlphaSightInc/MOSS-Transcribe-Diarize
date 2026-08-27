#!/usr/bin/env python3
"""Normalize and score fresh LiveTranscribe and ProjectClerk actual-live artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SURFACE_SCRIPT = HERE.parent / "live-surface-optimization/measure_three_surfaces.py"
sys.path.insert(0, str(REPO))
_SPEC = importlib.util.spec_from_file_location("live_surface_peer_scoring", SURFACE_SCRIPT)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load {SURFACE_SCRIPT}")
surface = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = surface
_SPEC.loader.exec_module(surface)

EXPECTED_LT_BINARY = "5a59299c1a8fd157cd456e809f6fbd0996970fd3fb462abd411cbec99d72358b"
EXPECTED_PC_BINARY = "106c10081ae758de27208ad053522c05e69ca15a5f91215f270f2a1461311c0c"
QUALITY_FIELDS = surface.QUALITY_FIELDS
TIME_RE = re.compile(r"^(\d+):(\d{2})$")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def iso_epoch(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "max": None}
    values = sorted(values)
    def q(fraction: float) -> float:
        position = (len(values) - 1) * fraction
        lo, hi = int(position), min(int(position) + 1, len(values) - 1)
        return values[lo] + (values[hi] - values[lo]) * (position - lo)
    return {"count": len(values), "mean": statistics.mean(values), "p50": q(.5), "p95": q(.95), "max": max(values)}


def clamp_rows(rows: list[dict[str, Any]], offset: float, duration: float) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        start = max(0.0, float(row["start"]) - offset)
        end = min(duration, float(row["end"]) - offset)
        if end > start and str(row.get("text") or "").strip():
            out.append({"start": start, "end": end, "speaker": str(row["speaker"]), "text": str(row["text"])})
    return out


def parse_afplay_offset(run: Path, session: dict[str, Any]) -> dict[str, Any]:
    text = (run / "afplay_process_identity.txt").read_text(encoding="utf-8")
    match = re.search(r"timestamp_utc:\s*(\S+)", text)
    if not match:
        raise RuntimeError(f"missing afplay timestamp: {run}")
    playback_epoch = iso_epoch(match.group(1))
    session_epoch = iso_epoch(str(session["started_at"]))
    return {
        "seconds": playback_epoch - session_epoch,
        "method": "afplay UTC-second timestamp minus session.started_at",
        "timestamp_resolution_seconds": 1.0,
    }


def lt_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"start": row["start"], "end": row["end"], "speaker": row.get("speaker") or row.get("display_name") or "S00", "text": row.get("text") or ""}
        for row in payload.get("segments") or []
    ]


def lt_latency(run: Path, offset: float, stop_payload: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    observations = []
    states: dict[str, dict[str, Any]] = {}
    corrections = []
    for path in sorted(run.glob("transcript_t_*s.json"), key=lambda item: int(re.search(r"_(\d+)s", item.name).group(1))):
        tick = int(re.search(r"_(\d+)s", path.name).group(1))
        try:
            rows = load(path).get("segments") or []
        except (json.JSONDecodeError, AttributeError):
            continue
        if rows and not observations:
            first_start = min(float(row["start"]) - offset for row in rows)
            observations.append(max(0.0, tick - max(0.0, first_start)))
        for row in rows:
            key = str(row.get("segment_id") or f"{row.get('start')}:{row.get('end')}")
            value = (str(row.get("text") or ""), row.get("speaker"), row.get("start"), row.get("end"))
            prior = states.get(key)
            if prior is None:
                states[key] = {"first": tick, "last_correction": tick, "value": value, "changed": False}
            elif prior["value"] != value:
                old_text, old_speaker, old_start, _ = prior["value"]
                new_text, new_speaker, new_start, _ = value
                normalized_old = " ".join(old_text.lower().split())
                normalized_new = " ".join(new_text.lower().split())
                is_append_only = (
                    normalized_new.startswith(normalized_old)
                    and old_speaker == new_speaker
                    and old_start == new_start
                )
                prior["value"] = value
                if not is_append_only:
                    prior.update({"last_correction": tick, "changed": True})
    for state in states.values():
        if state["changed"]:
            corrections.append(float(state["last_correction"] - state["first"]))
    drain = load(run / "pre_stop_drain.json")
    return {
        "first_visible_audio_age_seconds": distribution(observations),
        "correction_age_seconds": distribution(corrections),
        "pre_stop_drain_wait_seconds": float(drain["pre_stop_drain_wait_ms"]) / 1000,
        "stop_to_terminal_seconds": iso_epoch(session["updated_at"]) - iso_epoch(stop_payload["updated_at"]),
        "asr_latency_p95_seconds": (float(stop_payload.get("asr_latency_p95_ms") or 0) / 1000),
        "canonical_processing_latency_p95_seconds": (float(stop_payload.get("canonical_processing_latency_p95_ms") or 0) / 1000),
        "clock_notes": [
            "first-visible and correction clocks are one-second API snapshot observations; append-only segment growth is not a correction",
            "stop-to-terminal uses stop response updated_at through terminal session updated_at",
        ],
    }


def score_livetranscribe(case_id: str, corpus: Path, run: Path, normalized: Path) -> dict[str, Any]:
    case_dir = corpus / case_id
    case = surface.Case(case_id, case_dir, case_dir / "unused")
    duration = surface.wav_facts(case.audio)["duration_seconds"]
    executable_line = (run / "executable_sha256.txt").read_text(encoding="utf-8").strip()
    executable_sha = executable_line.split()[0]
    session = load(run / "session.json")
    stop_payload = load(run / "stop_response.json")
    offset = parse_afplay_offset(run, session)
    surfaces = {
        "pre_stop_settled": clamp_rows(lt_rows(load(run / "transcript_pre_stop.json")), offset["seconds"], duration),
        "post_stop_final": clamp_rows(lt_rows({"segments": load(run / "segments.json")}), offset["seconds"], duration),
    }
    normalized.mkdir(parents=True, exist_ok=False)
    for name, rows in surfaces.items():
        dump_jsonl(normalized / f"{name}.jsonl", rows)
    return {
        "product": "LiveTranscribe",
        "case_id": case_id,
        "duration_seconds": duration,
        "binary_sha256": executable_sha,
        "binary_matches_preregistered": executable_sha == EXPECTED_LT_BINARY,
        "audio_sha256": load(run / "audio_route_pre.txt") if False else hashlib.sha256(case.audio.read_bytes()).hexdigest(),
        "playback_offset": offset,
        "surfaces": {name: {"rows": len(rows), "scores": surface.score_surface(case, rows)} for name, rows in surfaces.items()},
        "latency": lt_latency(run, offset["seconds"], stop_payload, session),
        "state": {
            "terminal_status": session.get("status"),
            "pre_stop_drain_ready": load(run / "pre_stop_drain.json").get("ready_for_pre_stop_snapshot"),
            "capture_mode": (run / "capture_mode.txt").read_text(encoding="utf-8").strip(),
        },
    }


def pc_persisted_rows(payload: dict[str, Any], offset: float, duration: float) -> list[dict[str, Any]]:
    source = sorted(payload.get("conversation") or [], key=lambda row: float(row["start"]))
    out = []
    for index, row in enumerate(source):
        start = max(0.0, float(row["start"]) - offset)
        next_start = float(source[index + 1]["start"]) - offset if index + 1 < len(source) else duration
        end = min(duration, max(start + 0.01, next_start))
        if end > start and str(row.get("text") or "").strip():
            out.append({
                "start": start,
                "end": end,
                "speaker": str(row.get("speakerKey") or row.get("speaker") or "S00"),
                "text": str(row["text"]),
            })
    return out


def parse_pc_page(path: Path) -> list[dict[str, Any]]:
    records = [row for row in load(path) if row.get("role") == "AXStaticText" and isinstance(row.get("value"), str)]
    times = [row for row in records if TIME_RE.match(row["value"])]
    rows = []
    for stamp in times:
        x, y = float(stamp.get("x") or 0), float(stamp.get("y") or 0)
        candidates = [
            row for row in records
            if x + 35 < float(row.get("x") or 0) < 1060
            and abs(float(row.get("y") or 0) - y) <= max(30.0, float(row.get("height") or 0))
            and not TIME_RE.match(row["value"])
        ]
        if not candidates:
            continue
        text = max(candidates, key=lambda row: (len(row["value"]), float(row.get("width") or 0)))["value"]
        minute, second = TIME_RE.match(stamp["value"]).groups()
        nearby_labels = [
            row for row in records
            if abs(float(row.get("x") or 0) - x) <= 45
            and y - 45 <= float(row.get("y") or 0) < y
            and not TIME_RE.match(row["value"])
        ]
        speaker = max(nearby_labels, key=lambda row: float(row.get("y") or 0))["value"] if nearby_labels else None
        rows.append({"raw_start": int(minute) * 60 + int(second), "speaker": speaker, "text": text})
    return rows


def pc_live_rows(run: Path, offset: float, duration: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # Pages are captured bottom-to-top. Merge by timestamp+text, then carry the displayed speaker
    # in chronological order; a missing label means the UI intentionally continued the prior turn.
    discovered: dict[tuple[int, str], dict[str, Any]] = {}
    for path in sorted((run / "pre-stop-pages").glob("page-*.json"), reverse=True):
        for row in parse_pc_page(path):
            key = (row["raw_start"], row["text"])
            current = discovered.get(key)
            if current is None or (current.get("speaker") is None and row.get("speaker") is not None):
                discovered[key] = row
    ordered = sorted(discovered.values(), key=lambda row: (row["raw_start"], row["text"]))
    current_speaker = None
    for row in ordered:
        if row.get("speaker"):
            current_speaker = row["speaker"]
        row["speaker"] = current_speaker or "S00"
    out = []
    for index, row in enumerate(ordered):
        start = max(0.0, row["raw_start"] - offset)
        next_start = ordered[index + 1]["raw_start"] - offset if index + 1 < len(ordered) else duration
        end = min(duration, max(start + 0.01, next_start))
        if end > start:
            out.append({"start": start, "end": end, "speaker": row["speaker"], "text": row["text"]})
    return out, {
        "timestamp_resolution_seconds": 1.0,
        "pages": len(list((run / "pre-stop-pages").glob("page-*.json"))),
        "parsed_rows": len(out),
        "method": "Accessibility pages; UI m:ss starts; end=next start; final end=clip duration",
    }


def score_projectclerk(case_id: str, corpus: Path, run: Path, normalized: Path) -> dict[str, Any]:
    case_dir = corpus / case_id
    case = surface.Case(case_id, case_dir, case_dir / "unused")
    duration = surface.wav_facts(case.audio)["duration_seconds"]
    clocks = load(run / "clocks.json")
    offset = (clocks["playback_start_epoch_ns"] - clocks["start_issued_epoch_ns"]) / 1e9
    live, live_meta = pc_live_rows(run, offset, duration)
    raw = pc_persisted_rows(load(run / "post-stop-raw.json"), offset, duration)
    stable = pc_persisted_rows(load(run / "post-stop-stable.json"), offset, duration)
    surfaces = {"pre_stop_live": live, "stop_raw": raw, "post_stop_stable": stable}
    normalized.mkdir(parents=True, exist_ok=False)
    for name, rows in surfaces.items():
        dump_jsonl(normalized / f"{name}.jsonl", rows)
    binary_sha = (run / "binary-sha256.txt").read_text(encoding="utf-8").split()[0]
    first_visible = None
    for path in sorted((run / "live-snapshots").glob("t_*.json")):
        if parse_pc_page(path):
            first_visible = int(re.search(r"_(\d+)\.json", path.name).group(1))
            break
    return {
        "product": "ProjectClerk",
        "case_id": case_id,
        "duration_seconds": duration,
        "binary_sha256": binary_sha,
        "binary_matches_preregistered": binary_sha == EXPECTED_PC_BINARY,
        "audio_sha256": load(run / "audio.json")["sha256"],
        "playback_offset": {"seconds": offset, "method": "playback-start wall clock minus Start click wall clock"},
        "surfaces": {name: {"rows": len(rows), "scores": surface.score_surface(case, rows)} for name, rows in surfaces.items()},
        "latency": {
            "first_visible_snapshot_seconds": first_visible,
            "pre_stop_capture_wait_after_audio_seconds": (clocks["pre_stop_captured_epoch_ns"] - clocks["playback_end_epoch_ns"]) / 1e9,
            "stop_to_terminal_capture_seconds": (clocks["terminal_captured_epoch_ns"] - clocks["stop_issued_epoch_ns"]) / 1e9,
            "correction_age_seconds": "unmeasured: Accessibility exposes current rows, not revision identity",
        },
        "timestamp_limit": live_meta,
        "state": {
            "persisted_versions": clocks["persisted_versions"],
            "recluster_status_observed": clocks["recluster_status_observed"],
            "raw_captured": clocks["raw_captured"],
            "stable_captured": clocks["stable_captured"],
        },
    }


def unmeasured_projectclerk(case_id: str, corpus: Path, peer_root: Path, failure: dict[str, Any]) -> dict[str, Any]:
    case_row = next(row for row in failure["comparison_cells"] if row["case_id"] == case_id)
    duration = surface.wav_facts(corpus / case_id / "audio.wav")["duration_seconds"]
    return {
        "product": "ProjectClerk",
        "case_id": case_id,
        "duration_seconds": duration,
        "binary_sha256": failure["binary_sha256"],
        "binary_matches_preregistered": failure["binary_sha256"] == EXPECTED_PC_BINARY,
        "audio_sha256": (
            load(peer_root / "projectclerk/mono_javier_intro_50s/audio.json")["sha256"]
            if case_id == failure["attempted_case"] and (peer_root / "projectclerk/mono_javier_intro_50s/audio.json").is_file()
            else None
        ),
        "surfaces": {},
        "latency": {"state": "unmeasured", "reason": failure["failed_precondition"]},
        "state": {
            "measurement": "unmeasured",
            "attempted_actual_live": case_id == failure["attempted_case"],
            "reason": case_row["reason"],
            "required_action": failure["required_action"],
        },
    }


def aggregate(rows: list[dict[str, Any]], category_of: dict[str, str]) -> dict[str, Any]:
    groups: dict[str, list[tuple[float, dict[str, Any], str]]] = defaultdict(list)
    for row in rows:
        for surface_name, surface_row in row["surfaces"].items():
            groups[f"{row['product']}:{surface_name}"].append((row["duration_seconds"], surface_row["scores"], category_of[row["case_id"]]))
    out = {}
    for name, values in groups.items():
        total = sum(duration for duration, _, _ in values)
        out[name] = {
            "macro_mean": {field: sum(score[field] for _, score, _ in values) / len(values) for field in QUALITY_FIELDS},
            "duration_weighted_mean": {field: sum(duration * score[field] for duration, score, _ in values) / total for field in QUALITY_FIELDS},
            "denominator": {"cases": len(values), "audio_seconds": total},
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--peer-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    corpus, peer_root, out = args.corpus.resolve(), args.peer_root.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = load(corpus / "corpus-manifest.json")
    category_of = {row["case_id"]: row["category"] for row in manifest["cases"]}
    pc_failure_path = peer_root / "projectclerk-unmeasured.json"
    pc_failure = load(pc_failure_path) if pc_failure_path.is_file() else None
    rows = []
    for case_id in category_of:
        rows.append(score_livetranscribe(case_id, corpus, peer_root / "livetranscribe" / case_id, out / "normalized" / "livetranscribe" / case_id))
        rows.append(
            unmeasured_projectclerk(case_id, corpus, peer_root, pc_failure)
            if pc_failure is not None
            else score_projectclerk(case_id, corpus, peer_root / "projectclerk" / case_id, out / "normalized" / "projectclerk" / case_id)
        )
    expected_audio = {row["case_id"]: row["audio"]["wav_sha256"] for row in manifest["cases"]}
    checks = {
        "denominator_12_comparison_cells": len(rows) == 12,
        "binary_hashes_match": all(row["binary_matches_preregistered"] for row in rows),
        "played_audio_hashes_match": all(
            row["audio_sha256"] in {None, expected_audio[row["case_id"]]} for row in rows
        ),
        "livetranscribe_terminal_states": all(
            row["state"].get("terminal_status") == "completed" for row in rows if row["product"] == "LiveTranscribe"
        ),
        "projectclerk_unmeasured_declared": all(
            row["state"].get("measurement") == "unmeasured" for row in rows if row["product"] == "ProjectClerk"
        ) if pc_failure is not None else True,
    }
    payload = {
        "schema": "moss-live-policy-peer-scores.v1",
        "denominator": {
            "comparison_cells": len(rows),
            "actual_live_sessions": sum(row["product"] == "LiveTranscribe" or row["state"].get("attempted_actual_live") for row in rows),
            "scored_surfaces": sum(len(row["surfaces"]) for row in rows),
            "unmeasured_projectclerk_cells": sum(row["product"] == "ProjectClerk" and not row["surfaces"] for row in rows),
        },
        "runs": rows,
        "aggregate": aggregate(rows, category_of),
        "checks": checks,
    }
    dump(out / "peer-results.json", payload)
    print(json.dumps({"result": str(out / 'peer-results.json'), "checks": checks}, indent=2))
    return 0 if all(checks.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
