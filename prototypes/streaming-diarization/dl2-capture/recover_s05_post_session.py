#!/usr/bin/env python3
"""Recover S05 post-session output after an externally stopped, dead-air-tailed capture."""

from __future__ import annotations

import argparse
from array import array
import json
import shutil
import tempfile
import time
import wave
from pathlib import Path
from typing import Any

from capture_harness import DEPLOYED_SHA, HarnessRefusal, atomic_json, read_json, sha256, utc_now
from post_session import (
    API,
    await_job,
    batch_idle,
    bleed_rate_for_packet,
    curl_json,
    extract_interval,
    raw_retention_decision,
    render_html,
    seal_tree,
    submit,
    triangulate,
)


SESSION_ID = "40422fb135a146579d013d663652bd56"


def extract_bounded(source: Path, destination: Path, start: float, end: float) -> dict[str, Any]:
    with wave.open(str(source), "rb") as reader:
        rate = reader.getframerate()
        frames = reader.getnframes()
        left, right = int(round(start * rate)), int(round(end * rate))
        if left < 0 or right <= left or right > frames:
            raise HarnessRefusal(f"s05_recovery_interval_invalid:{source.name}:{start}:{end}")
        params = reader.getparams()
        reader.setpos(left)
        payload = reader.readframes(right - left)
    with wave.open(str(destination), "wb") as writer:
        writer.setparams(params)
        writer.writeframes(payload)
    return {
        "start_seconds": start,
        "end_seconds": end,
        "sample_rate": rate,
        "source_frames": frames,
        "selected_frames": right - left,
        "selected_sha256": sha256(destination),
    }


def shift_and_own(segments: list[dict[str, Any]], offset: float, own: tuple[float, float] | None) -> list[dict[str, Any]]:
    output = []
    for item in segments:
        result = dict(item)
        result["start"] = round(float(item["start"]) + offset, 6)
        result["end"] = round(float(item["end"]) + offset, 6)
        midpoint = (result["start"] + result["end"]) / 2.0
        if own is None or own[0] <= midpoint < own[1] or (midpoint == own[1] and own[1] == 420.0):
            output.append(result)
    return output


def submit_interval(track: str, source: Path, interval: list[float], temp: Path, own: tuple[float, float] | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    start, end = map(float, interval)
    selected = temp / f"{track}-{start:g}-{end:g}.wav"
    selection = extract_bounded(source, selected, start, end)
    job_id, argv = submit(selected)
    terminal = await_job(job_id)
    if terminal.get("source_sha256") != sha256(selected):
        raise HarnessRefusal(f"s05_recovery_uploaded_hash_mismatch:{track}:{start}:{end}")
    if terminal.get("possibly_truncated"):
        raise HarnessRefusal(f"s05_recovery_truncated:{track}:{start}:{end}")
    if terminal.get("completed_windows") != terminal.get("window_count"):
        raise HarnessRefusal(f"s05_recovery_windows_incomplete:{track}:{start}:{end}")
    payload = curl_json(f"/api/jobs/{job_id}/segments")
    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        raise HarnessRefusal(f"s05_recovery_segments_empty:{track}:{start}:{end}")
    shifted = shift_and_own(segments, start, own)
    return shifted, {
        "job_id": job_id,
        "track": track,
        "interval_seconds": [start, end],
        "ownership_seconds": None if own is None else list(own),
        "selection": selection,
        "submit_api_argv": argv,
        "terminal": terminal,
        "raw_segment_count": len(segments),
        "owned_segment_count": len(shifted),
    }


def compact_intervals(source: Path, destination: Path, intervals: list[list[float]], separator_seconds: float) -> list[dict[str, Any]]:
    pieces = []
    with wave.open(str(source), "rb") as reader:
        params = reader.getparams()
        rate = reader.getframerate()
        if reader.getnchannels() != 1 or reader.getsampwidth() != 2:
            raise HarnessRefusal("s05_recovery_compact_format_refused")
        chunks: list[bytes] = []
        compact_cursor = 0.0
        for index, interval in enumerate(intervals):
            start, end = map(float, interval)
            left, right = int(round(start * rate)), int(round(end * rate))
            if left < 0 or right <= left or right > reader.getnframes():
                raise HarnessRefusal(f"s05_recovery_compact_interval_invalid:{start}:{end}")
            reader.setpos(left)
            chunks.append(reader.readframes(right - left))
            duration = (right - left) / rate
            pieces.append({
                "index": index,
                "compact_start_seconds": compact_cursor,
                "compact_end_seconds": compact_cursor + duration,
                "tape_start_seconds": start,
                "tape_end_seconds": end,
            })
            compact_cursor += duration
            if index + 1 < len(intervals):
                separator_frames = int(round(separator_seconds * rate))
                chunks.append(b"\0" * separator_frames * params.sampwidth)
                compact_cursor += separator_frames / rate
    with wave.open(str(destination), "wb") as writer:
        writer.setparams(params)
        for chunk in chunks:
            writer.writeframes(chunk)
    return pieces


def map_compact_segments(segments: list[dict[str, Any]], pieces: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    output = []
    clamp_count = 0
    for item in segments:
        left, right = float(item["start"]), float(item["end"])
        midpoint = (left + right) / 2.0
        piece = next((candidate for candidate in pieces if candidate["compact_start_seconds"] <= midpoint < candidate["compact_end_seconds"]), None)
        if piece is None:
            continue
        mapped_left = left - piece["compact_start_seconds"] + piece["tape_start_seconds"]
        mapped_right = right - piece["compact_start_seconds"] + piece["tape_start_seconds"]
        clamped_left = max(piece["tape_start_seconds"], min(piece["tape_end_seconds"], mapped_left))
        clamped_right = max(piece["tape_start_seconds"], min(piece["tape_end_seconds"], mapped_right))
        if clamped_left != mapped_left or clamped_right != mapped_right:
            clamp_count += 1
        if clamped_right <= clamped_left:
            continue
        result = dict(item)
        result["start"] = round(clamped_left, 6)
        result["end"] = round(clamped_right, 6)
        output.append(result)
    return output, clamp_count


def submit_compact_microphone(source: Path, spec: dict[str, Any], temp: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected = temp / "microphone-compact.wav"
    pieces = compact_intervals(source, selected, spec["intervals_seconds"], float(spec["separator_silence_seconds"]))
    job_id = spec.get("completed_job_id")
    if job_id is None:
        job_id, argv = submit(selected)
        terminal = await_job(job_id)
    else:
        argv = None
        terminal = curl_json(f"/api/jobs/{job_id}")
        if terminal.get("status") not in {"waiting_review", "complete", "completed"}:
            raise HarnessRefusal("s05_recovery_completed_microphone_job_not_terminal")
    if terminal.get("source_sha256") != sha256(selected):
        raise HarnessRefusal("s05_recovery_uploaded_hash_mismatch:microphone:compact")
    if terminal.get("possibly_truncated") or terminal.get("completed_windows") != terminal.get("window_count"):
        raise HarnessRefusal("s05_recovery_compact_microphone_incomplete")
    payload = curl_json(f"/api/jobs/{job_id}/segments")
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise HarnessRefusal("s05_recovery_segments_empty:microphone:compact")
    mapped, clamp_count = map_compact_segments(raw_segments, pieces)
    if not mapped:
        raise HarnessRefusal("s05_recovery_mapped_segments_empty:microphone:compact")
    return mapped, {
        "job_id": job_id,
        "track": "microphone",
        "mode": "compact_disjoint_signal_bearing_intervals",
        "selected_sha256": sha256(selected),
        "submit_api_argv": argv,
        "reused_completed_job": spec.get("completed_job_id") is not None,
        "terminal": terminal,
        "piecewise_tape_map": pieces,
        "raw_segment_count": len(raw_segments),
        "mapped_segment_count": len(mapped),
        "clamped_segment_count": clamp_count,
    }


def write_track(root: Path, track: str, segments: list[dict[str, Any]], terminal: dict[str, Any]) -> dict[str, Any]:
    directory = root / "asr" / track
    directory.mkdir(parents=True, exist_ok=False)
    transcript = directory / "asr-transcript.json"
    text = directory / "asr-text.txt"
    terminal_path = directory / "job-terminal.json"
    atomic_json(transcript, {"segments": segments})
    text.write_text(" ".join(str(item.get("text", "")).strip() for item in segments if str(item.get("text", "")).strip()) + "\n", encoding="utf-8")
    atomic_json(terminal_path, terminal)
    return {
        "track": track,
        "segment_count": len(segments),
        "speaker_labels": sorted({str(item.get("speaker")) for item in segments}),
        "transcript_path": str(transcript),
        "transcript_sha256": sha256(transcript),
        "text_path": str(text),
        "text_sha256": sha256(text),
        "terminal_path": str(terminal_path),
        "terminal_sha256": sha256(terminal_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    session = args.session_dir.resolve()
    plan = read_json(args.plan)
    manifest_path = session / "session-manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("session_id") != SESSION_ID or plan.get("session_id") != SESSION_ID:
        raise HarnessRefusal("s05_recovery_session_mismatch")
    if manifest.get("state") != "pulled_pending_asr":
        raise HarnessRefusal(f"s05_recovery_state_refused:{manifest.get('state')}")
    if not manifest.get("capture_stop_deviation", {}).get("authorized_recovery"):
        raise HarnessRefusal("s05_recovery_external_stop_not_recorded")
    if manifest.get("capture_stopped_status", {}).get("running") is not False:
        raise HarnessRefusal("s05_recovery_capture_not_stopped")
    if manifest.get("capture_stopped_status", {}).get("outboxRetainedFrames") != 0:
        raise HarnessRefusal("s05_recovery_outbox_not_empty")

    partial = session / "derived"
    archived = session / "derived-attempt-card-60-360-partial"
    if not partial.is_dir() or archived.exists():
        raise HarnessRefusal("s05_recovery_expected_partial_missing_or_archived")
    system_transcript = read_json(partial / "asr/system/asr-transcript.json")
    system_terminal = read_json(partial / "asr/system/job-terminal.json")
    if system_terminal.get("id") != plan["system"]["job_id"]:
        raise HarnessRefusal("s05_recovery_system_job_mismatch")
    if system_terminal.get("possibly_truncated") or system_terminal.get("completed_windows") != system_terminal.get("window_count"):
        raise HarnessRefusal("s05_recovery_system_job_incomplete")

    preflight = batch_idle()
    started = utc_now()
    job_records: list[dict[str, Any]] = []
    results: dict[str, list[dict[str, Any]]] = {"system": system_transcript["segments"], "microphone": [], "mixed": []}
    with tempfile.TemporaryDirectory(prefix="moss-s05-recovery-") as temp_name:
        temp = Path(temp_name)
        if plan["microphone"]["mode"] == "compact_disjoint_signal_bearing_intervals":
            segments, record = submit_compact_microphone(session / "audio/microphone.wav", plan["microphone"], temp)
            results["microphone"].extend(segments)
            job_records.append(record)
        else:
            for interval in plan["microphone"]["intervals_seconds"]:
                segments, record = submit_interval("microphone", session / "audio/microphone.wav", interval, temp, None)
                results["microphone"].extend(segments)
                job_records.append(record)
        intervals = plan["mixed"]["intervals_seconds"]
        ownership = plan["mixed"]["ownership_seconds"]
        if len(intervals) != len(ownership):
            raise HarnessRefusal("s05_recovery_mixed_plan_length_mismatch")
        for interval, own in zip(intervals, ownership):
            segments, record = submit_interval("mixed", session / "audio/mixed.wav", interval, temp, tuple(map(float, own)))
            results["mixed"].extend(segments)
            job_records.append(record)
    postflight = batch_idle()

    partial.rename(archived)
    seal_tree(archived, archived / "PARTIAL_ATTEMPT_EVIDENCE.sha256")
    derived = session / "derived"
    derived.mkdir()
    records = []
    records.append(write_track(derived, "system", results["system"], system_terminal))
    for track in ("microphone", "mixed"):
        results[track].sort(key=lambda item: (float(item["start"]), float(item["end"])))
        records.append(write_track(derived, track, results[track], {"recovery_jobs": [item for item in job_records if item["track"] == track]}))

    failed_jobs = {item["job_id"]: curl_json(f"/api/jobs/{item['job_id']}") for item in plan["failed_arms_never_retried"]}
    recovery_root = derived / "recovery"
    recovery_root.mkdir()
    atomic_json(recovery_root / "recovery-plan.json", plan)
    atomic_json(recovery_root / "failed-job-metadata.json", failed_jobs)
    atomic_json(recovery_root / "recovery-job-records.json", {"jobs": job_records})
    atomic_json(
        recovery_root / "recovery-verdict.json",
        {
            "schema": "moss-dl2-s05-post-session-recovery-verdict.v1",
            "session_id": SESSION_ID,
            "started_at_utc": started,
            "ended_at_utc": utc_now(),
            "verdict": "PASS_RECOVERED_CARD_INTERVAL",
            "external_stop_deviation_preserved": True,
            "full_track_failure_preserved": True,
            "trailing_dead_air_excluded": True,
            "capture_stop_reissued": False,
            "plan_sha256": sha256(args.plan),
            "partial_attempt_path": archived.name,
            "partial_attempt_seal_sha256": sha256(archived / "PARTIAL_ATTEMPT_EVIDENCE.sha256"),
        },
    )
    seal_tree(recovery_root, recovery_root / "S05_RECOVERY_EVIDENCE.sha256")

    rows = triangulate(derived / "asr")
    bleed = bleed_rate_for_packet(manifest)
    packet = derived / "audit-packet"
    packet.mkdir()
    atomic_json(packet / "audit-rows.json", {"schema": "moss-dl2-audit-rows.v1", "session_id": SESSION_ID, "bleed_rate": bleed, "rows": rows})
    (packet / "audit-rows.html").write_text(render_html(rows, SESSION_ID, bleed), encoding="utf-8")
    provenance = {
        "schema": "moss-dl2-post-session-recovery.v1",
        "session_id": SESSION_ID,
        "shape_id": "S05",
        "deployment_sha": DEPLOYED_SHA,
        "batch_api": API,
        "blind": True,
        "golden_reference_opened": False,
        "started_at_utc": started,
        "ended_at_utc": utc_now(),
        "preflight": preflight,
        "postflight": postflight,
        "recovery_plan_path": "derived/recovery/recovery-plan.json",
        "recovery_plan_sha256": sha256(recovery_root / "recovery-plan.json"),
        "tracks": records,
        "audit_row_count": len(rows),
        "target_listen_row_count": sum(bool(row["target_listen"]) for row in rows),
        "bleed_rate": bleed,
        "external_stop_deviation": manifest["capture_stop_deviation"],
        "trailing_dead_air": "excluded under frozen recovery plan after named production batch refusal",
    }
    atomic_json(derived / "provenance.json", provenance)
    seal_tree(derived, derived / "DERIVED_EVIDENCE.sha256")

    grant = read_json(session.parents[1] / "grant.json")
    retention = raw_retention_decision(grant, manifest)
    if not retention.get("retain"):
        raise HarnessRefusal("s05_recovery_raw_must_remain_retained_at_boundary")
    manifest["state"] = "audit_ready_raw_retained"
    manifest["raw_retention"] = retention
    manifest["derived"] = {
        "provenance_path": "derived/provenance.json",
        "provenance_sha256": sha256(derived / "provenance.json"),
        "audit_rows_path": "derived/audit-packet/audit-rows.json",
        "audit_rows_sha256": sha256(packet / "audit-rows.json"),
        "audit_html_path": "derived/audit-packet/audit-rows.html",
        "audit_html_sha256": sha256(packet / "audit-rows.html"),
        "seal_path": "derived/DERIVED_EVIDENCE.sha256",
        "seal_sha256": sha256(derived / "DERIVED_EVIDENCE.sha256"),
    }
    manifest["post_session_recovery"] = {
        "reason": "controller died mid-session; supervisor externally stopped after the card; standard ASR refused on trailing dead air",
        "capture_stop_reissued": False,
        "plan_path": "../../s05-recovery-intervals.json",
        "plan_sha256": sha256(args.plan),
        "verdict_path": "derived/recovery/recovery-verdict.json",
        "verdict_sha256": sha256(recovery_root / "recovery-verdict.json"),
    }
    atomic_json(manifest_path, manifest)
    print(json.dumps({"ok": True, "session_id": SESSION_ID, "rows": len(rows), "target_listen": provenance["target_listen_row_count"], "retention": retention, "jobs": [item["job_id"] for item in job_records]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
