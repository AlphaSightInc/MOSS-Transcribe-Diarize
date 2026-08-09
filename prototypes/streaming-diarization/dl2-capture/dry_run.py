#!/usr/bin/env python3
"""Mock one complete pull→ASR→audit→cleanup path without hosts or golden truth."""

from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path

from capture_harness import atomic_json, pcm_to_wav, sha256, validate_grant, validate_tape_dir
from post_session import run_pipeline


HERE = Path(__file__).resolve().parent
OUT = HERE / "evidence" / "dry-run" / "mock-program"


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    session_id = "dry-run-session"
    session_dir = OUT / "sessions" / ("S01-" + session_id)
    raw = session_dir / "raw"
    audio = session_dir / "audio"
    raw.mkdir(parents=True)
    audio.mkdir()
    grant = {
        "ttl_seconds": 86_400,
        "program_cap_bytes": 2_147_483_648,
        "retention_root": "/home/devcontainers/.local/share/moss-transcribe-diarize/live/dl2-capture-sprint",
    }
    ledger = {"schema": "moss-dl2-program-ledger.v1", "captured_bytes_total": 0, "sessions": []}
    atomic_json(OUT / "grant.json", grant)
    atomic_json(OUT / "program-ledger.json", ledger)
    validate_grant(grant, ledger)
    samples = [1000 if index % 2 else -1000 for index in range(16_000)]
    pcm = struct.pack("<" + "h" * len(samples), *samples)
    tracks = {}
    for name in ("system", "microphone", "mixed"):
        path = raw / (name + ".pcm")
        path.write_bytes(pcm)
        tracks[name] = {"sample_count": len(samples), "bytes": len(pcm), "sha256": sha256(path)}
        pcm_to_wav(path, audio / (name + ".wav"))
    atomic_json(
        raw / "index.json",
        {"session_id": session_id, "sample_rate": 16_000, "total_bytes": len(pcm) * 3, "ended_at": 1.0, "degradation": None, "tracks": tracks},
    )
    tape = validate_tape_dir(raw, session_id)
    ledger["captured_bytes_total"] = tape["total_bytes"]
    ledger["sessions"].append(
        {"session_id": session_id, "raw_bytes": tape["total_bytes"], "raw_deleted": False}
    )
    atomic_json(OUT / "program-ledger.json", ledger)
    atomic_json(
        session_dir / "session-manifest.json",
        {
            "schema": "moss-dl2-capture-session.v1",
            "session_id": session_id,
            "shape": {"shape_id": "S01"},
            "state": "pulled_pending_asr",
            "tape": tape,
        },
    )
    mock = {
        "system": [{"id": "s1", "start": 0.0, "end": 1.0, "speaker": "S01", "text": "remote hello"}],
        "microphone": [{"id": "m1", "start": 0.25, "end": 0.75, "speaker": "S01", "text": "local hello"}],
        "mixed": [{"id": "x1", "start": 0.0, "end": 1.0, "speaker": "S01", "text": "remote hello local hello"}],
    }
    mock_path = OUT / "mock-asr.json"
    atomic_json(mock_path, mock)
    result = run_pipeline(session_dir, mock_path, keep_raw=False)
    if (session_dir / "raw").exists() or (session_dir / "audio").exists():
        raise RuntimeError("dry_run_raw_cleanup_failed")
    if not (session_dir / "derived" / "audit-packet" / "audit-rows.html").is_file():
        raise RuntimeError("dry_run_audit_packet_missing")
    print("PASS grant_bounds accepted within 24h/2GiB")
    print("PASS both_lanes_present system+microphone+mixed")
    print("PASS blind_asr mock tracks=3")
    print("PASS audit_packet rows=%s target_listen=%s" % (result["row_count"], result["target_listen"]))
    print("PASS raw_cleanup local=yes remote=mock")
    print("PASS end_to_end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
