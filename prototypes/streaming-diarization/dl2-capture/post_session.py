#!/usr/bin/env python3
"""One-command blind ASR + lane triangulation + raw cleanup for one DL2 session."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from capture_harness import (
    DEPLOYED_SHA,
    TRACKS,
    HarnessRefusal,
    atomic_json,
    cleanup_raw,
    read_json,
    sha256,
    utc_now,
)


API = "http://ga0-alienware-rtx4070ti.local:7860"
TERMINAL = {"waiting_review", "complete", "completed"}
LEADING_SILENCE_DB = -35
LEADING_SILENCE_MIN_SECONDS = 2.0
LEADING_SILENCE_PREROLL_SECONDS = 0.0


def curl_json(path: str, extra: Optional[List[str]] = None) -> Any:
    argv = ["/usr/bin/curl", "-fsS", "--max-time", "1800"]
    if extra:
        argv.extend(extra)
    argv.append(API + path)
    completed = subprocess.run(argv, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise HarnessRefusal("batch_api_failed:%s:%s" % (path, completed.stderr.strip()))
    return json.loads(completed.stdout)


def batch_idle() -> Dict[str, Any]:
    payload = curl_json("/api/jobs")
    active = [
        {"id": item.get("id"), "status": item.get("status")}
        for item in payload.get("jobs", [])
        if item.get("status") in {"queued", "running", "processing"}
    ]
    if active:
        raise HarnessRefusal("batch_queue_not_idle:%r" % active)
    runtime = curl_json("/api/runtime")
    return {"checked_at_utc": utc_now(), "active_jobs": active, "runtime": runtime}


def submit(audio: Path) -> Tuple[str, List[str]]:
    argv = [
        "/usr/bin/curl",
        "-fsS",
        "--max-time",
        "1800",
        "-X",
        "POST",
        "-F",
        "file=@%s;type=audio/wav" % audio,
        API + "/api/jobs",
    ]
    completed = subprocess.run(argv, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise HarnessRefusal("batch_submit_failed:%s" % completed.stderr.strip())
    payload = json.loads(completed.stdout)
    job_id = payload.get("id")
    if not isinstance(job_id, str) or not job_id:
        raise HarnessRefusal("batch_submit_schema")
    return job_id, argv


def await_job(job_id: str) -> Dict[str, Any]:
    deadline = time.monotonic() + 3600.0
    while True:
        payload = curl_json("/api/jobs/%s" % job_id)
        state = payload.get("status")
        if state in TERMINAL:
            return payload
        if state in {"failed", "cancelled", "canceled"}:
            raise HarnessRefusal("batch_job_failed:%s:%s" % (job_id, payload.get("error")))
        if time.monotonic() >= deadline:
            raise HarnessRefusal("batch_job_timeout:%s:%s" % (job_id, state))
        time.sleep(2.0)


def _shift_timestamps(value: Any, offset_seconds: float) -> Any:
    if isinstance(value, list):
        return [_shift_timestamps(item, offset_seconds) for item in value]
    if not isinstance(value, dict):
        return value
    shifted = {}
    for key, item in value.items():
        if key in {"start", "end"} and isinstance(item, (int, float)):
            shifted[key] = round(float(item) + offset_seconds, 6)
        else:
            shifted[key] = _shift_timestamps(item, offset_seconds)
    return shifted


def extract_interval(source: Path, destination: Path, start_seconds: float) -> Dict[str, Any]:
    with wave.open(str(source), "rb") as reader:
        params = reader.getparams()
        start_frame = int(round(start_seconds * reader.getframerate()))
        if start_frame < 0 or start_frame >= reader.getnframes():
            raise HarnessRefusal("asr_interval_out_of_bounds:%s:%s" % (source.name, start_seconds))
        source_frames = reader.getnframes()
        reader.setpos(start_frame)
        payload = reader.readframes(source_frames - start_frame)
    with wave.open(str(destination), "wb") as writer:
        writer.setparams(params)
        writer.writeframes(payload)
    return {
        "start_seconds": start_seconds,
        "source_frames": source_frames,
        "selected_frames": source_frames - start_frame,
        "sample_rate": params.framerate,
        "selected_sha256": sha256(destination),
    }


def trim_leading_silence(source: Path, destination: Path) -> Tuple[Path, Dict[str, Any]]:
    detector_argv = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        str(source),
        "-af",
        "silencedetect=noise=%ddB:d=%.1f" % (LEADING_SILENCE_DB, LEADING_SILENCE_MIN_SECONDS),
        "-f",
        "null",
        "-",
    ]
    completed = subprocess.run(detector_argv, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise HarnessRefusal("leading_silence_detect_failed:%s" % completed.stderr.strip())
    starts = [float(value) for value in re.findall(r"silence_start:\s*([0-9.]+)", completed.stderr)]
    ends = [float(value) for value in re.findall(r"silence_end:\s*([0-9.]+)", completed.stderr)]
    leading_end = ends[0] if starts and starts[0] <= 0.05 and ends else 0.0
    with wave.open(str(source), "rb") as reader:
        params = reader.getparams()
        source_frames = reader.getnframes()
        sample_offset = int(round(max(0.0, leading_end - LEADING_SILENCE_PREROLL_SECONDS) * params.framerate))
        if sample_offset >= source_frames:
            raise HarnessRefusal("leading_silence_no_speech:%s" % source.name)
        if sample_offset:
            reader.setpos(sample_offset)
            payload = reader.readframes(source_frames - sample_offset)
    record = {
        "detector": "ffmpeg silencedetect",
        "detector_argv": detector_argv,
        "threshold_db": LEADING_SILENCE_DB,
        "minimum_seconds": LEADING_SILENCE_MIN_SECONDS,
        "preroll_seconds": LEADING_SILENCE_PREROLL_SECONDS,
        "leading_silence_end_seconds": leading_end or None,
        "sample_rate": params.framerate,
        "sample_offset": sample_offset,
        "offset_seconds": sample_offset / params.framerate,
        "trimmed": bool(sample_offset),
        "source_sample_count": source_frames,
        "selected_sample_count": source_frames - sample_offset,
    }
    if not sample_offset:
        return source, record
    with wave.open(str(destination), "wb") as writer:
        writer.setparams(params)
        writer.writeframes(payload)
    record["selected_sha256"] = sha256(destination)
    return destination, record


def collect_track(
    track: str,
    audio: Path,
    output: Path,
    mock: Optional[Dict[str, Any]],
    timestamp_offset_seconds: float = 0.0,
    operator_declared_non_speech: bool = False,
    original_audio_sha256: Optional[str] = None,
    sample_offset: int = 0,
    leading_silence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    started = utc_now()
    clock = time.monotonic()
    submit_argv: Optional[List[str]] = None
    if operator_declared_non_speech:
        job_id = "operator-declared-non-speech-%s" % track
        terminal = {
            "id": job_id,
            "status": "skipped_operator_declared_non_speech",
            "source_sha256": sha256(audio),
            "window_count": 0,
            "completed_windows": 0,
            "possibly_truncated": False,
        }
        segments = {"segments": []}
    elif mock is not None:
        job_id = "mock-%s" % track
        terminal = {
            "id": job_id,
            "status": "complete",
            "source_sha256": sha256(audio),
            "window_count": 1,
            "completed_windows": 1,
            "possibly_truncated": False,
        }
        segments = {"segments": mock[track]}
    else:
        job_id, submit_argv = submit(audio)
        terminal = await_job(job_id)
        if terminal.get("source_sha256") != sha256(audio):
            raise HarnessRefusal("batch_uploaded_hash_mismatch:%s" % track)
        if terminal.get("possibly_truncated"):
            raise HarnessRefusal("batch_output_truncated:%s" % track)
        if terminal.get("completed_windows") != terminal.get("window_count"):
            raise HarnessRefusal("batch_windows_incomplete:%s" % track)
        segments = curl_json("/api/jobs/%s/segments" % job_id)
    if not isinstance(segments, dict) or not isinstance(segments.get("segments"), list):
        raise HarnessRefusal("batch_segments_schema:%s" % track)
    segments = _shift_timestamps(segments, timestamp_offset_seconds)
    track_dir = output / track
    track_dir.mkdir(parents=True, exist_ok=False)
    transcript_path = track_dir / "asr-transcript.json"
    terminal_path = track_dir / "job-terminal.json"
    text_path = track_dir / "asr-text.txt"
    atomic_json(transcript_path, segments)
    atomic_json(terminal_path, terminal)
    text_path.write_text(
        " ".join(str(item.get("text", "")).strip() for item in segments["segments"] if str(item.get("text", "")).strip()) + "\n",
        encoding="utf-8",
    )
    return {
        "track": track,
        "audio_sha256": sha256(audio),
        "original_audio_sha256": original_audio_sha256 or sha256(audio),
        "timestamp_offset_seconds": timestamp_offset_seconds,
        "sample_offset": sample_offset,
        "leading_silence": leading_silence,
        "operator_declared_non_speech": operator_declared_non_speech,
        "job_id": job_id,
        "submit_api_argv": submit_argv,
        "status_api_argv": None if mock is not None or operator_declared_non_speech else ["curl", "-fsS", API + "/api/jobs/%s" % job_id],
        "segments_api_argv": None if mock is not None or operator_declared_non_speech else ["curl", "-fsS", API + "/api/jobs/%s/segments" % job_id],
        "started_at_utc": started,
        "ended_at_utc": utc_now(),
        "wall_seconds": round(time.monotonic() - clock, 6),
        "segment_count": len(segments["segments"]),
        "transcript_path": str(transcript_path),
        "transcript_sha256": sha256(transcript_path),
        "text_path": str(text_path),
        "text_sha256": sha256(text_path),
        "terminal_path": str(terminal_path),
        "terminal_sha256": sha256(terminal_path),
    }


def _segments(path: Path) -> List[Dict[str, Any]]:
    payload = read_json(path)
    result = payload.get("segments")
    if not isinstance(result, list):
        raise HarnessRefusal("triangulation_segments_invalid:%s" % path)
    return result


def _text_overlapping(segments: List[Dict[str, Any]], start: float, end: float) -> str:
    parts = []
    for segment in segments:
        left = float(segment.get("start", 0.0))
        right = float(segment.get("end", left))
        if right > start and left < end:
            text = str(segment.get("text", "")).strip()
            if text and text not in parts:
                parts.append(text)
    return " ".join(parts)


def _normalize(text: str) -> str:
    return " ".join("".join(character.lower() if character.isalnum() else " " for character in text).split())


def triangulate(asr_root: Path) -> List[Dict[str, Any]]:
    by_track = {track: _segments(asr_root / track / "asr-transcript.json") for track in TRACKS}
    boundaries = sorted(
        {
            float(segment.get(key, 0.0))
            for segments in by_track.values()
            for segment in segments
            for key in ("start", "end")
        }
    )
    rows = []
    for start, end in zip(boundaries, boundaries[1:]):
        if end <= start:
            continue
        texts = {track: _text_overlapping(by_track[track], start, end) for track in TRACKS}
        if not any(texts.values()):
            continue
        system_norm = _normalize(texts["system"])
        microphone_norm = _normalize(texts["microphone"])
        mixed_norm = _normalize(texts["mixed"])
        mixed_agrees = bool(mixed_norm) and mixed_norm in {system_norm, microphone_norm}
        rows.append(
            {
                "row": len(rows) + 1,
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "system_text": texts["system"],
                "microphone_text": texts["microphone"],
                "mixed_text": texts["mixed"],
                "mixed_agrees_with_a_lane": mixed_agrees,
                "target_listen": not mixed_agrees or (bool(system_norm) and bool(microphone_norm)),
            }
        )
    return rows


def bleed_rate_for_packet(manifest: Dict[str, Any]) -> Dict[str, Any]:
    metric = manifest.get("bleed_rate")
    if metric is None:
        return {
            "status": "pending_human_audit",
            "bleeded_speech_seconds": None,
            "true_local_speech_seconds": None,
            "mic_speech_seconds": None,
            "value": None,
            "percent_rounded_1dp": None,
            "formula": "bleeded_speech_seconds / mic_speech_seconds",
        }
    if not isinstance(metric, dict):
        raise HarnessRefusal("bleed_rate_schema_invalid")
    required = {
        "status",
        "bleeded_speech_seconds",
        "true_local_speech_seconds",
        "mic_speech_seconds",
        "value",
        "percent_rounded_1dp",
        "formula",
    }
    if set(metric) != required or metric.get("status") != "human_audited":
        raise HarnessRefusal("bleed_rate_schema_invalid")
    denominator = float(metric["mic_speech_seconds"])
    if denominator <= 0:
        raise HarnessRefusal("bleed_rate_denominator_invalid")
    expected = float(metric["bleeded_speech_seconds"]) / denominator
    if abs(float(metric["value"]) - expected) > 1e-12:
        raise HarnessRefusal("bleed_rate_value_mismatch")
    return dict(metric)


def raw_retention_decision(
    grant: Dict[str, Any], manifest: Dict[str, Any], observed: Optional[dt.datetime] = None
) -> Dict[str, Any]:
    amendment = grant.get("raw_retention_amendment")
    if amendment is None:
        return {"retain": False, "reason": "immediate_cleanup_default"}
    if not isinstance(amendment, dict) or amendment.get("authorized") is not True:
        raise HarnessRefusal("raw_retention_amendment_invalid")
    shape_ids = amendment.get("shape_ids")
    deadline_text = amendment.get("retain_until_et")
    if not isinstance(shape_ids, list) or not all(isinstance(item, str) for item in shape_ids):
        raise HarnessRefusal("raw_retention_shape_scope_invalid")
    if deadline_text != grant.get("raw_delete_deadline_et"):
        raise HarnessRefusal("raw_retention_deadline_mismatch")
    shape_id = manifest.get("shape", {}).get("shape_id")
    if shape_id not in shape_ids:
        return {"retain": False, "reason": "shape_not_in_retention_amendment", "shape_id": shape_id}
    deadline = dt.datetime.fromisoformat(str(deadline_text))
    now = observed or dt.datetime.now(dt.timezone.utc)
    retain = now < deadline.astimezone(dt.timezone.utc)
    return {
        "retain": retain,
        "reason": "operator_authorized_until_sprint_close" if retain else "retention_deadline_reached",
        "shape_id": shape_id,
        "retain_until_et": deadline_text,
        "cleanup_command": "python3 capture_harness.py cleanup --session-dir <session-dir>",
    }


def render_html(rows: List[Dict[str, Any]], session_id: str, bleed_rate: Dict[str, Any]) -> str:
    body = []
    for row in rows:
        body.append(
            "<tr class='%s'><td>%d</td><td>%.3f–%.3f</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                "listen" if row["target_listen"] else "agree",
                row["row"],
                row["start"],
                row["end"],
                html.escape(row["system_text"]),
                html.escape(row["microphone_text"]),
                html.escape(row["mixed_text"]),
                "LISTEN" if row["target_listen"] else "AGREE",
            )
        )
    if bleed_rate["status"] == "human_audited":
        bleed_summary = "Bleed rate: %.1f%% (%0.2fs / %0.2fs mic speech)." % (
            bleed_rate["percent_rounded_1dp"],
            bleed_rate["bleeded_speech_seconds"],
            bleed_rate["mic_speech_seconds"],
        )
    else:
        bleed_summary = "Bleed rate: pending human audit."
    return """<!doctype html>
<meta charset="utf-8"><title>DL2 audit %s</title>
<style>body{font:14px system-ui;margin:24px}table{border-collapse:collapse;width:100%%}th,td{border:1px solid #bbb;padding:6px;vertical-align:top}.listen{background:#fff1d6}.agree{background:#e9f7ed}</style>
<h1>Blind ASR lane triangulation — %s</h1>
<p>LISTEN rows are ASR disagreements or simultaneous lane speech. This packet contains no golden reference.</p>
<p>%s</p>
<table><thead><tr><th>#</th><th>time</th><th>system</th><th>microphone</th><th>mixed</th><th>audit</th></tr></thead><tbody>%s</tbody></table>
""" % (html.escape(session_id), html.escape(session_id), html.escape(bleed_summary), "\n".join(body))


def seal_tree(root: Path, destination: Path) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path != destination:
            rows.append("%s  %s" % (sha256(path), path.relative_to(root).as_posix()))
    destination.write_text("\n".join(rows) + "\n", encoding="utf-8")


def run_pipeline(
    session_dir: Path,
    mock_path: Optional[Path],
    keep_raw: bool,
    start_seconds: float = 0.0,
    operator_non_speech_tracks: Optional[List[str]] = None,
) -> Dict[str, Any]:
    session_dir = session_dir.resolve()
    manifest_path = session_dir / "session-manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("state") != "pulled_pending_asr":
        raise HarnessRefusal("post_session_state_refused:%s" % manifest.get("state"))
    mock = read_json(mock_path) if mock_path is not None else None
    preflight = {"mock": True, "checked_at_utc": utc_now()} if mock is not None else batch_idle()
    asr_root = session_dir / "derived" / "asr"
    asr_root.mkdir(parents=True, exist_ok=False)
    non_speech = set(operator_non_speech_tracks or [])
    interval_records: Dict[str, Any] = {}
    records = []
    with tempfile.TemporaryDirectory(prefix="moss-dl2-asr-") as temp_name:
        temp_root = Path(temp_name)
        for track in TRACKS:
            original = session_dir / "audio" / (track + ".wav")
            selected = original
            manual_record: Optional[Dict[str, Any]] = None
            if start_seconds:
                selected = temp_root / (track + "-manual.wav")
                manual_record = extract_interval(original, selected, start_seconds)
            if track in non_speech:
                trimmed = selected
                with wave.open(str(selected), "rb") as reader:
                    sample_rate = reader.getframerate()
                    sample_count = reader.getnframes()
                leading_record = {
                    "detector": "skipped_operator_declared_non_speech",
                    "detector_argv": None,
                    "threshold_db": LEADING_SILENCE_DB,
                    "minimum_seconds": LEADING_SILENCE_MIN_SECONDS,
                    "preroll_seconds": LEADING_SILENCE_PREROLL_SECONDS,
                    "leading_silence_end_seconds": None,
                    "sample_rate": sample_rate,
                    "source_sample_count": sample_count,
                    "selected_sample_count": sample_count,
                    "sample_offset": 0,
                    "offset_seconds": 0.0,
                    "trimmed": False,
                    "selected_sha256": sha256(selected),
                }
            else:
                trimmed, leading_record = trim_leading_silence(
                    selected,
                    temp_root / (track + "-leading-trim.wav"),
                )
            sample_rate = int(leading_record["sample_rate"])
            manual_sample_offset = int(round(start_seconds * sample_rate))
            total_sample_offset = manual_sample_offset + int(leading_record["sample_offset"])
            timestamp_offset_seconds = total_sample_offset / sample_rate
            interval_records[track] = {
                "manual": manual_record,
                "leading_silence": leading_record,
                "total_sample_offset": total_sample_offset,
                "timestamp_offset_seconds": timestamp_offset_seconds,
            }
            records.append(
                collect_track(
                    track,
                    trimmed,
                    asr_root,
                    mock,
                    timestamp_offset_seconds=timestamp_offset_seconds,
                    operator_declared_non_speech=track in non_speech,
                    original_audio_sha256=sha256(original),
                    sample_offset=total_sample_offset,
                    leading_silence=leading_record,
                )
            )
    if mock is None:
        postflight = batch_idle()
    else:
        postflight = {"mock": True, "checked_at_utc": utc_now()}
    rows = triangulate(asr_root)
    bleed_rate = bleed_rate_for_packet(manifest)
    packet_root = session_dir / "derived" / "audit-packet"
    packet_root.mkdir()
    rows_path = packet_root / "audit-rows.json"
    html_path = packet_root / "audit-rows.html"
    atomic_json(
        rows_path,
        {
            "schema": "moss-dl2-audit-rows.v1",
            "session_id": manifest["session_id"],
            "bleed_rate": bleed_rate,
            "rows": rows,
        },
    )
    html_path.write_text(render_html(rows, str(manifest["session_id"]), bleed_rate), encoding="utf-8")
    provenance = {
        "schema": "moss-dl2-post-session.v1",
        "session_id": manifest["session_id"],
        "shape_id": manifest["shape"]["shape_id"],
        "started_at_utc": preflight["checked_at_utc"],
        "ended_at_utc": utc_now(),
        "deployment_sha": DEPLOYED_SHA,
        "batch_api": API,
        "blind": True,
        "golden_reference_opened": False,
        "interval_selection": {
            "start_seconds": start_seconds,
            "end": "track end",
            "same_interval_all_tracks": len(
                {record["total_sample_offset"] for record in interval_records.values()}
            )
            == 1,
            "automatic_leading_silence": {
                "threshold_db": LEADING_SILENCE_DB,
                "minimum_seconds": LEADING_SILENCE_MIN_SECONDS,
                "preroll_seconds": LEADING_SILENCE_PREROLL_SECONDS,
            },
            "tracks": interval_records,
        },
        "operator_declared_non_speech_tracks": sorted(non_speech),
        "content_note": "S01 system lane contained music only; empty system transcript is operator-declared content, not an ASR success claim." if non_speech else None,
        "preflight": preflight,
        "postflight": postflight,
        "tracks": records,
        "audit_row_count": len(rows),
        "target_listen_row_count": sum(bool(row["target_listen"]) for row in rows),
        "bleed_rate": bleed_rate,
        "mock": mock is not None,
    }
    provenance_path = session_dir / "derived" / "provenance.json"
    atomic_json(provenance_path, provenance)
    seal_path = session_dir / "derived" / "DERIVED_EVIDENCE.sha256"
    seal_tree(session_dir / "derived", seal_path)
    manifest["state"] = "derived_hashed"
    manifest["derived"] = {
        "provenance_path": "derived/provenance.json",
        "provenance_sha256": sha256(provenance_path),
        "audit_rows_path": "derived/audit-packet/audit-rows.json",
        "audit_rows_sha256": sha256(rows_path),
        "audit_html_path": "derived/audit-packet/audit-rows.html",
        "audit_html_sha256": sha256(html_path),
        "seal_path": "derived/DERIVED_EVIDENCE.sha256",
        "seal_sha256": sha256(seal_path),
    }
    atomic_json(manifest_path, manifest)
    cleanup = None
    if mock is not None:
        retention = {"retain": bool(keep_raw), "reason": "mock_keep_raw" if keep_raw else "mock_cleanup"}
    else:
        grant = read_json(session_dir.parents[1] / "grant.json")
        retention = raw_retention_decision(grant, manifest)
    manifest["raw_retention"] = retention
    if retention["retain"]:
        manifest["state"] = "audit_ready_raw_retained"
        atomic_json(manifest_path, manifest)
    else:
        cleanup = cleanup_raw(session_dir, mock=mock is not None)
    return {
        "session_id": manifest["session_id"],
        "row_count": len(rows),
        "target_listen": provenance["target_listen_row_count"],
        "cleanup": cleanup,
        "raw_retention": retention,
        "mock": mock is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--mock-asr", type=Path)
    parser.add_argument("--keep-raw", action="store_true", help="Dry-run only; real sessions must delete raw")
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--operator-non-speech-track", action="append", choices=TRACKS, default=[])
    args = parser.parse_args()
    if args.keep_raw and args.mock_asr is None:
        print("REFUSED keep_raw_real_session_forbidden")
        return 2
    try:
        result = run_pipeline(
            args.session_dir,
            args.mock_asr,
            args.keep_raw,
            start_seconds=args.start_seconds,
            operator_non_speech_tracks=args.operator_non_speech_track,
        )
    except HarnessRefusal as exc:
        print("REFUSED %s" % exc)
        return 2
    print(json.dumps({"ok": True, **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
