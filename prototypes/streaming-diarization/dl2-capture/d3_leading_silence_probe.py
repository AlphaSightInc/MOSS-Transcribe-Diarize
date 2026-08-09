#!/usr/bin/env python3
"""Build and submit the frozen D3 leading-silence batch probes."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import wave
from pathlib import Path
from typing import Any, Dict, List

from capture_harness import atomic_json, sha256, utc_now
from post_session import API, batch_idle, collect_track, trim_leading_silence


DURATIONS = (30, 60, 120, 210)


def run(argv: List[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(argv, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise RuntimeError("command_failed:%r:%s" % (argv, completed.stderr.strip()))
    return completed


def audio_info(path: Path) -> Dict[str, Any]:
    with wave.open(str(path), "rb") as reader:
        return {
            "channels": reader.getnchannels(),
            "sample_width": reader.getsampwidth(),
            "sample_rate": reader.getframerate(),
            "sample_count": reader.getnframes(),
            "duration_seconds": reader.getnframes() / reader.getframerate(),
        }


def prepare(source: Path, root: Path) -> Dict[str, Any]:
    source = source.resolve()
    root.mkdir(parents=True, exist_ok=False)
    source_info = audio_info(source)
    if source_info["channels"] != 1 or source_info["sample_width"] != 2 or source_info["sample_rate"] != 16_000:
        raise RuntimeError("source_format_not_pcm16_mono_16k")
    with wave.open(str(source), "rb") as reader:
        source_frames = reader.readframes(reader.getnframes())
    fixtures = []
    for seconds in DURATIONS:
        destination = root / ("leading-%03ds.wav" % seconds)
        with wave.open(str(destination), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(16_000)
            writer.writeframes(b"\0\0" * (seconds * 16_000))
            writer.writeframes(source_frames)
        with wave.open(str(destination), "rb") as reader:
            prefix = reader.readframes(seconds * 16_000)
            suffix = reader.readframes(source_info["sample_count"])
        fixtures.append(
            {
                "prepend_seconds": seconds,
                "path": destination.name,
                "sha256": sha256(destination),
                "audio": audio_info(destination),
                "prefix_exact_zero": prefix == b"\0\0" * (seconds * 16_000),
                "decoded_source_suffix_byte_identical": suffix == source_frames,
            }
        )
    manifest = {
        "schema": "moss-dl2-d3-fixtures.v1",
        "created_at_utc": utc_now(),
        "source": {"path": str(source), "sha256": sha256(source), "audio": source_info},
        "fixtures": fixtures,
    }
    atomic_json(root / "fixture-manifest.json", manifest)
    return manifest


def curl_json(argv: List[str]) -> Dict[str, Any]:
    completed = run(argv)
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("api_object_required")
    return payload


def submit_and_wait(audio: Path, case_root: Path) -> Dict[str, Any]:
    submit_argv = [
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
    submitted = curl_json(submit_argv)
    atomic_json(case_root / "submit.json", submitted)
    job_id = submitted.get("id")
    if not isinstance(job_id, str) or not job_id:
        raise RuntimeError("batch_submit_schema")
    status_argv = ["/usr/bin/curl", "-fsS", API + "/api/jobs/%s" % job_id]
    deadline = time.monotonic() + 3600.0
    while True:
        terminal = curl_json(status_argv)
        status = terminal.get("status")
        if status in {"waiting_review", "complete", "completed", "failed", "cancelled", "canceled"}:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("batch_timeout:%s:%s" % (job_id, status))
        time.sleep(2.0)
    atomic_json(case_root / "terminal.json", terminal)
    segments_payload: Dict[str, Any]
    if status in {"waiting_review", "complete", "completed"}:
        segments_argv = ["/usr/bin/curl", "-fsS", API + "/api/jobs/%s/segments" % job_id]
        segments_payload = curl_json(segments_argv)
    else:
        segments_argv = []
        segments_payload = {"segments": [], "unavailable_due_to_terminal_status": status}
    atomic_json(case_root / "segments.json", segments_payload)
    segments = segments_payload.get("segments", [])
    if not isinstance(segments, list):
        raise RuntimeError("segments_schema:%s" % job_id)
    return {
        "job_id": job_id,
        "status": status,
        "generated_tokens": terminal.get("generated_tokens"),
        "segment_count": len(segments),
        "window_count": terminal.get("window_count"),
        "completed_windows": terminal.get("completed_windows"),
        "possibly_truncated": terminal.get("possibly_truncated"),
        "error": terminal.get("error"),
        "elapsed_sec": terminal.get("elapsed_sec"),
        "source_sha256": terminal.get("source_sha256"),
        "max_segment_end": max((float(segment.get("end", 0.0)) for segment in segments), default=None),
        "submit_api_argv": submit_argv,
        "status_api_argv": status_argv,
        "segments_api_argv": segments_argv,
    }


def measure(fixtures: Path, output: Path) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    preflight = batch_idle()
    atomic_json(output / "batch-preflight.json", preflight)
    manifest = json.loads((fixtures / "fixture-manifest.json").read_text(encoding="utf-8"))
    results = []
    for fixture in manifest["fixtures"]:
        seconds = int(fixture["prepend_seconds"])
        case_root = output / ("leading-%03ds" % seconds)
        case_root.mkdir()
        audio = fixtures / fixture["path"]
        result = submit_and_wait(audio, case_root)
        results.append({"prepend_seconds": seconds, "fixture_sha256": sha256(audio), **result})
    postflight = batch_idle()
    atomic_json(output / "batch-postflight.json", postflight)
    summary = {
        "schema": "moss-dl2-d3-leading-silence-results.v1",
        "started_at_utc": preflight["checked_at_utc"],
        "ended_at_utc": postflight["checked_at_utc"],
        "accepted_control": {"generated_tokens": 521, "segment_count": 17, "job_id": "77bc16ec2ae6"},
        "results": results,
    }
    atomic_json(output / "summary.json", summary)
    return summary


def green(source: Path, output: Path) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    preflight = batch_idle()
    atomic_json(output / "batch-preflight.json", preflight)
    selected, trim = trim_leading_silence(source, output / "leading-210s-trimmed.wav")
    atomic_json(output / "trim-record.json", trim)
    record = collect_track(
        "control",
        selected,
        output / "asr",
        None,
        timestamp_offset_seconds=float(trim["offset_seconds"]),
        original_audio_sha256=sha256(source),
        sample_offset=int(trim["sample_offset"]),
        leading_silence=trim,
    )
    terminal = json.loads(Path(record["terminal_path"]).read_text(encoding="utf-8"))
    transcript = json.loads(Path(record["transcript_path"]).read_text(encoding="utf-8"))
    postflight = batch_idle()
    atomic_json(output / "batch-postflight.json", postflight)
    summary = {
        "schema": "moss-dl2-d3-leading-silence-green.v1",
        "source_path": str(source),
        "source_sha256": sha256(source),
        "selected_path": str(selected),
        "selected_sha256": sha256(selected),
        "trim": trim,
        "batch": record,
        "generated_tokens": terminal.get("generated_tokens"),
        "segment_count": record["segment_count"],
        "mapped_first_segment_start": min(
            (float(segment["start"]) for segment in transcript["segments"]), default=None
        ),
        "mapped_last_segment_end": max(
            (float(segment["end"]) for segment in transcript["segments"]), default=None
        ),
        "accepted_control": {"generated_tokens": 521, "segment_count": 17, "job_id": "77bc16ec2ae6"},
        "regression_pass": terminal.get("generated_tokens") == 521 and record["segment_count"] == 17,
    }
    atomic_json(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--source", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    measure_parser = sub.add_parser("measure")
    measure_parser.add_argument("--fixtures", type=Path, required=True)
    measure_parser.add_argument("--output", type=Path, required=True)
    green_parser = sub.add_parser("green")
    green_parser.add_argument("--source", type=Path, required=True)
    green_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        payload = prepare(args.source, args.output)
    elif args.command == "measure":
        payload = measure(args.fixtures, args.output)
    else:
        payload = green(args.source, args.output)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
