#!/usr/bin/env python3
"""Collect deployed batch ASR for the read-only exploratory dual-lane audio."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import time

from collect_runtime_asr import await_job, curl_json, remote_preflight, sha256, submit


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
ROOT = HERE / "exploratory/f2-dual-lane"
SOURCE = ROOT / "source"
OUTPUT = ROOT / "runtime-asr"
EVIDENCE = HERE / "evidence/f2"
EXPECTED = {
    "local-mic": ("local.wav", "830a5558cf90fe7f5571dc2cfc6e0708d1e09194b5b716532d6d6902bf953251"),
    "remote-system": ("remote.wav", "5299e742325fa9d3c58946222262a8262bd7e47863c97d0f0a772956050c1c1d"),
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    provenance_path = OUTPUT / "provenance.json"
    if provenance_path.exists():
        raise RuntimeError("f2_runtime_asr_version_exists")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    transcript = []
    preflight = remote_preflight()
    preflight_path = EVIDENCE / "runtime-asr-preflight.json"
    preflight_path.write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n")
    transcript.append("PASS preflight idle healthy no-live-session")
    records = []
    for lane, (filename, expected_hash) in EXPECTED.items():
        audio = SOURCE / filename
        actual_hash = sha256(audio)
        if actual_hash != expected_hash:
            raise RuntimeError(f"f2_source_hash_mismatch:{lane}:{actual_hash}")
        started = utc_now()
        clock = time.monotonic()
        job_id, submit_argv = submit(audio)
        terminal = await_job(job_id)
        if terminal.get("source_sha256") != actual_hash:
            raise RuntimeError(f"f2_uploaded_hash_mismatch:{lane}:{job_id}")
        if terminal.get("possibly_truncated"):
            raise RuntimeError(f"f2_batch_truncated:{lane}:{job_id}")
        if terminal.get("completed_windows") != terminal.get("window_count"):
            raise RuntimeError(f"f2_batch_incomplete:{lane}:{job_id}")
        segments = curl_json(f"/api/jobs/{job_id}/segments")
        if not isinstance(segments, dict) or not isinstance(segments.get("segments"), list):
            raise RuntimeError(f"f2_segments_schema:{lane}:{job_id}")
        lane_dir = OUTPUT / lane
        lane_dir.mkdir(parents=True, exist_ok=True)
        segments_path = lane_dir / "segments.json"
        terminal_path = lane_dir / "job-terminal.json"
        segments_path.write_text(json.dumps(segments, indent=2, ensure_ascii=False) + "\n")
        terminal_path.write_text(json.dumps(terminal, indent=2, ensure_ascii=False) + "\n")
        record = {
            "capture_lane": lane,
            "audio_path": audio.relative_to(REPO).as_posix(),
            "audio_sha256": actual_hash,
            "job_id": job_id,
            "submit_api_argv": submit_argv,
            "status_api_argv": ["curl", "-fsS", f"http://ga0-alienware-rtx4070ti.local:7860/api/jobs/{job_id}"],
            "segments_api_argv": ["curl", "-fsS", f"http://ga0-alienware-rtx4070ti.local:7860/api/jobs/{job_id}/segments"],
            "started_at_utc": started,
            "ended_at_utc": utc_now(),
            "wall_seconds": round(time.monotonic() - clock, 6),
            "terminal_status": terminal["status"],
            "segments_path": segments_path.relative_to(REPO).as_posix(),
            "segments_sha256": sha256(segments_path),
            "job_terminal_path": terminal_path.relative_to(REPO).as_posix(),
            "job_terminal_sha256": sha256(terminal_path),
            "segment_count": len(segments["segments"]),
        }
        records.append(record)
        transcript.append(f"PASS {lane} job={job_id} segments={record['segment_count']}")
    jobs = curl_json("/api/jobs")
    active = [
        {"id": item.get("id"), "status": item.get("status")}
        for item in jobs.get("jobs", [])
        if item.get("status") in {"queued", "running", "processing"}
    ]
    if active:
        raise RuntimeError(f"f2_postflight_batch_not_idle:{active}")
    provenance = {
        "schema": "moss-l15-f2-runtime-asr.v1",
        "created_at_utc": utc_now(),
        "deployment_sha": "9089b33210401111865da7abc160ab0bcb4aa266",
        "batch_api": "http://ga0-alienware-rtx4070ti.local:7860",
        "preflight_path": preflight_path.relative_to(REPO).as_posix(),
        "preflight_sha256": sha256(preflight_path),
        "cases": records,
        "postflight_active_jobs": active,
        "constraints": {
            "reference_opened": False,
            "gated_corpus_opened": False,
            "validation_opened": False,
            "holdout_opened": False,
            "batch_jobs_only": True,
            "service_restart": False,
            "deployed_tree_modified": False,
        },
        "overall": "PASS",
    }
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    transcript.append(f"PASS overall lanes=2 provenance_sha256={sha256(provenance_path)}")
    (EVIDENCE / "runtime-asr-transcript.txt").write_text("\n".join(transcript) + "\n")
    print("\n".join(transcript))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
