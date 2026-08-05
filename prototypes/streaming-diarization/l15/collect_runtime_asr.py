#!/usr/bin/env python3
"""Collect label-blind runtime ASR fixtures for L1.5 dev/validation cases only."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SPLITS = HERE / "split-manifest.json"
OUTPUT = HERE / "runtime-inputs" / "asr"
EVIDENCE = HERE / "evidence" / "runtime-inputs"
API = "http://ga0-alienware-rtx4070ti.local:7860"
DEPLOYED_SHA = "9089b33210401111865da7abc160ab0bcb4aa266"
TERMINAL = {"waiting_review", "complete", "completed"}
TRANSCRIPT: list[str] = []

# Prior blind, operator-directed batch jobs produced by this exact deployed revision.
# Reusing their API artifacts avoids duplicate inference. No golden file is consulted.
REUSED_JOB_IDS = {
    "1m-acquired-jamie-dimon": "493868ad900f",
    "5m-acquired-jamie-dimon": "a2ebbc9aa37c",
    "5m-acquired-nfl": "60d4ec44355d",
    "5m-acquired-rolex": "6b61c2b97d94",
    "5m-lex-bill-ackman": "d49c8141eb22",
    "5m-lex-javier-milei": "e1a673321ee8",
    "30m-lex-bill-ackman": "4511b53252e5",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def emit(message: str) -> None:
    TRANSCRIPT.append(message)
    print(message, flush=True)


def run(argv: list[str], *, stdin: str | None = None) -> str:
    completed = subprocess.run(
        argv,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            f"command_failed exit={completed.returncode} argv={argv!r} stderr={completed.stderr.strip()}"
        )
    return completed.stdout


def curl_json(path: str, *extra: str) -> Any:
    raw = run(["/usr/bin/curl", "-fsS", "--max-time", "900", *extra, f"{API}{path}"])
    return json.loads(raw)


def remote_preflight() -> dict[str, Any]:
    script = r'''set -euo pipefail
for unit in moss-live-web.service moss-web.service moss-vllm.service; do
  printf '%s\t%s\t%s\n' "$unit" "$(systemctl --user is-active "$unit")" "$(systemctl --user is-enabled "$unit")"
done
since="$(systemctl --user show moss-live-web.service -p ActiveEnterTimestamp --value)"
printf 'since\t%s\n' "$since"
printf 'live_post_count\t%s\n' "$(journalctl --user -u moss-live-web.service --since "$since" --no-pager | grep -Ec '\"(POST|PUT|PATCH|DELETE) /api/live/' || true)"
cd /mnt/d/Coding/MOSS-Transcribe-Diarize
printf 'deployed_sha\t%s\n' "$(git rev-parse HEAD)"
printf 'dirty_count\t%s\n' "$(git status --porcelain | wc -l)"
'''
    raw = run(
        [
            "ssh",
            "gyauo@ga0-alienware-rtx4070ti.local",
            "wsl.exe -d Ubuntu -- bash -s",
        ],
        stdin=script,
    )
    rows = [line.split("\t", 2) for line in raw.splitlines() if line.strip()]
    services = {
        row[0]: {"active": row[1], "enabled": row[2]}
        for row in rows
        if row[0].endswith(".service")
    }
    values = {row[0]: row[1] for row in rows if not row[0].endswith(".service")}
    jobs = curl_json("/api/jobs")
    active_jobs = [
        {"id": item.get("id"), "status": item.get("status")}
        for item in jobs.get("jobs", [])
        if item.get("status") in {"queued", "running", "processing"}
    ]
    runtime = curl_json("/api/runtime")
    problems: list[str] = []
    for unit, state in services.items():
        if state != {"active": "active", "enabled": "enabled"}:
            problems.append(f"service_unhealthy:{unit}:{state}")
    if values.get("deployed_sha") != DEPLOYED_SHA:
        problems.append(f"deployed_sha_mismatch:{values.get('deployed_sha')}")
    if values.get("dirty_count") != "0":
        problems.append(f"deployed_tree_dirty:{values.get('dirty_count')}")
    if values.get("live_post_count") != "0":
        problems.append(f"live_session_activity_present:{values.get('live_post_count')}")
    if active_jobs:
        problems.append(f"batch_queue_not_idle:{active_jobs}")
    if problems:
        raise RuntimeError("preflight_refused " + ";".join(problems))
    return {
        "checked_at_utc": utc_now(),
        "raw_ssh_stdout": raw,
        "services": services,
        "live_service_since": values.get("since"),
        "live_api_mutation_count_since_service_start": int(values["live_post_count"]),
        "deployed_sha": values["deployed_sha"],
        "deployed_dirty_count": int(values["dirty_count"]),
        "batch_total_jobs": len(jobs.get("jobs", [])),
        "batch_active_jobs": active_jobs,
        "runtime": runtime,
        "verdict": "PASS_IDLE_HEALTHY_NO_LIVE_SESSION",
    }


def dev_validation_cases() -> list[dict[str, Any]]:
    payload = json.loads(SPLITS.read_text(encoding="utf-8"))
    cases = [*payload["groups"]["development"], *payload["groups"]["validation"]]
    if len(cases) != 16 or any(item["split"] == "blind_holdout" for item in cases):
        raise RuntimeError("split_scope_invalid")
    return cases


def job_status(job_id: str) -> dict[str, Any]:
    payload = curl_json(f"/api/jobs/{job_id}")
    if not isinstance(payload, dict) or payload.get("id") != job_id:
        raise RuntimeError(f"job_status_schema:{job_id}")
    return payload


def await_job(job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 900.0
    while True:
        status = job_status(job_id)
        state = status.get("status")
        if state in TERMINAL:
            return status
        if state in {"failed", "cancelled", "canceled"}:
            raise RuntimeError(f"batch_job_failed:{job_id}:{status.get('error')}")
        if time.monotonic() >= deadline:
            raise RuntimeError(f"batch_job_timeout:{job_id}:{state}")
        time.sleep(2.0)


def submit(audio: Path) -> tuple[str, list[str]]:
    argv = [
        "/usr/bin/curl",
        "-fsS",
        "--max-time",
        "900",
        "-X",
        "POST",
        "-F",
        f"file=@{audio};type=audio/wav",
        f"{API}/api/jobs",
    ]
    payload = json.loads(run(argv))
    job_id = payload.get("id")
    if not isinstance(job_id, str) or not job_id:
        raise RuntimeError(f"submit_schema:{payload}")
    return job_id, argv


def collect_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    audio = REPO / case["audio_path"]
    actual_audio_hash = sha256(audio)
    if actual_audio_hash != case["audio_sha256"]:
        raise RuntimeError(f"audio_hash_mismatch:{case_id}:{actual_audio_hash}")
    started = utc_now()
    monotonic_start = time.monotonic()
    reused = case_id in REUSED_JOB_IDS
    submit_argv: list[str] | None = None
    if reused:
        job_id = REUSED_JOB_IDS[case_id]
    else:
        job_id, submit_argv = submit(audio)
    terminal = await_job(job_id)
    if terminal.get("source_sha256") != actual_audio_hash:
        raise RuntimeError(f"uploaded_source_hash_mismatch:{case_id}:{terminal.get('source_sha256')}")
    if terminal.get("possibly_truncated"):
        raise RuntimeError(f"batch_output_truncated:{case_id}:{job_id}")
    if terminal.get("completed_windows") != terminal.get("window_count"):
        raise RuntimeError(f"batch_windows_incomplete:{case_id}:{job_id}")
    segments = curl_json(f"/api/jobs/{job_id}/segments")
    if not isinstance(segments, dict) or not isinstance(segments.get("segments"), list):
        raise RuntimeError(f"segments_schema:{case_id}:{job_id}")
    case_dir = OUTPUT / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    segments_path = case_dir / "segments.json"
    terminal_path = case_dir / "job-terminal.json"
    segments_path.write_text(json.dumps(segments, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    terminal_path.write_text(json.dumps(terminal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    record = {
        "case_id": case_id,
        "split": case["split"],
        "audio_path": case["audio_path"],
        "audio_sha256": actual_audio_hash,
        "job_id": job_id,
        "job_reused": reused,
        "submit_api_argv": submit_argv,
        "status_api_argv": ["curl", "-fsS", f"{API}/api/jobs/{job_id}"],
        "segments_api_argv": ["curl", "-fsS", f"{API}/api/jobs/{job_id}/segments"],
        "started_at_utc": started,
        "ended_at_utc": utc_now(),
        "collection_wall_seconds": round(time.monotonic() - monotonic_start, 6),
        "terminal_status": terminal["status"],
        "window_count": terminal["window_count"],
        "completed_windows": terminal["completed_windows"],
        "possibly_truncated": terminal["possibly_truncated"],
        "segment_count": len(segments["segments"]),
        "speaker_labels": sorted({str(item.get("speaker")) for item in segments["segments"]}),
        "segments_path": str(segments_path.relative_to(REPO)),
        "segments_sha256": sha256(segments_path),
        "job_terminal_path": str(terminal_path.relative_to(REPO)),
        "job_terminal_sha256": sha256(terminal_path),
    }
    (case_dir / "provenance.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    emit(f"PASS {case_id} job={job_id} reused={reused} segments={record['segment_count']}")
    return record


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    preflight = remote_preflight()
    (EVIDENCE / "preflight.json").write_text(
        json.dumps(preflight, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    emit("PASS preflight idle healthy no-live-session")
    records = [collect_case(case) for case in dev_validation_cases()]
    post_jobs = curl_json("/api/jobs")
    active = [
        {"id": item.get("id"), "status": item.get("status")}
        for item in post_jobs.get("jobs", [])
        if item.get("status") in {"queued", "running", "processing"}
    ]
    if active:
        raise RuntimeError(f"postflight_batch_not_idle:{active}")
    provenance = {
        "schema": "moss-l15-runtime-asr.v1",
        "created_at_utc": utc_now(),
        "purpose": "D8-safe runtime-visible ASR fixtures; no golden path opened by collector",
        "deployment_sha": DEPLOYED_SHA,
        "batch_api": API,
        "preflight_path": str((EVIDENCE / "preflight.json").relative_to(REPO)),
        "preflight_sha256": sha256(EVIDENCE / "preflight.json"),
        "case_count": len(records),
        "reused_job_count": sum(bool(item["job_reused"]) for item in records),
        "new_job_count": sum(not bool(item["job_reused"]) for item in records),
        "cases": records,
        "constraints": {
            "golden_reference_opened": False,
            "holdout_case_opened": False,
            "batch_jobs_only": True,
            "service_restart": False,
            "deployed_tree_modified": False,
            "normal_runs_dir_artifacts_only": True,
        },
        "postflight_active_jobs": active,
        "overall": "PASS",
    }
    provenance_path = HERE / "runtime-inputs" / "asr-provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    emit(f"PASS overall cases={len(records)} provenance_sha256={sha256(provenance_path)}")
    (EVIDENCE / "collection-transcript.txt").write_text("\n".join(TRANSCRIPT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
