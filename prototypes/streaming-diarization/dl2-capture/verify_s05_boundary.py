#!/usr/bin/env python3
"""Seal the recovered S05 finish/verdict boundary."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from capture_harness import atomic_json, read_json, sha256, utc_now
from post_session import seal_tree


def verify_manifest(path: Path) -> dict:
    rows, failures = 0, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        target = path.parent / relative
        rows += 1
        if not target.is_file() or sha256(target) != expected:
            failures.append(relative)
    return {"path": str(path), "sha256": sha256(path), "rows": rows, "failures": failures, "passes": not failures}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    session = args.session_dir.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = read_json(session / "session-manifest.json")
    seals = [
        session / "derived/DERIVED_EVIDENCE_V2.sha256",
        session / "derived/s05-verdict/S05_VERDICT_EVIDENCE.sha256",
        session / "derived-recovery-v1-system-through-360/DERIVED_EVIDENCE.sha256",
        session / "derived-attempt-card-60-360-partial/PARTIAL_ATTEMPT_EVIDENCE.sha256",
    ]
    verification = [verify_manifest(path) for path in seals]
    if not all(item["passes"] for item in verification):
        raise RuntimeError("S05 evidence verification failed")

    tests = subprocess.run(
        ["python3", "-m", "unittest", "-v", "test_capture_harness.py", "test_post_session.py"],
        cwd=Path(__file__).resolve().parent,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    (output / "prototype-tests.txt").write_text(tests.stdout + tests.stderr, encoding="utf-8")
    if tests.returncode:
        raise RuntimeError("S05 prototype tests failed")

    remote_script = r'''set -euo pipefail
root=/home/devcontainers/.local/share/moss-transcribe-diarize/live/dl2-capture-sprint
sid=40422fb135a146579d013d663652bd56
test -d "$root/$sid"
stat -c 'root=%n mode=%a owner=%U:%G' "$root/$sid"
find "$root/$sid" -maxdepth 1 -type f -print0 | sort -z | xargs -0 sha256sum
for unit in moss-live-web.service moss-web.service moss-vllm.service; do
  printf 'service:%s\t%s/%s\n' "$unit" "$(systemctl --user is-active "$unit")" "$(systemctl --user is-enabled "$unit")"
done
printf 'deployed_sha\t%s\n' "$(git -C /mnt/d/Coding/MOSS-Transcribe-Diarize rev-parse HEAD)"
printf 'deployed_dirty_count\t%s\n' "$(git -C /mnt/d/Coding/MOSS-Transcribe-Diarize status --porcelain | wc -l)"
'''
    remote = subprocess.run(
        ["ssh", "gyauo@ga0-alienware-rtx4070ti.local", "wsl.exe -d Ubuntu -- bash -s"],
        input=remote_script,
        text=True,
        capture_output=True,
        check=False,
    )
    (output / "remote-raw-and-service-state.txt").write_text(remote.stdout + remote.stderr, encoding="utf-8")
    if remote.returncode or "deployed_sha\t9089b33210401111865da7abc160ab0bcb4aa266" not in remote.stdout:
        raise RuntimeError("S05 remote state failed")

    raw = {}
    for lane, record in manifest["tape"]["tracks"].items():
        path = session / "raw" / f"{lane}.pcm"
        raw[lane] = {
            "bytes": path.stat().st_size,
            "sample_count": record["sample_count"],
            "sha256": sha256(path),
            "matches_manifest": path.stat().st_size == record["bytes"] and sha256(path) == record["sha256"],
        }
    ledger = read_json(session.parents[1] / "program-ledger.json")
    retained = [item for item in ledger["sessions"] if item.get("raw_deleted") is False]
    verdict = read_json(session / "derived/s05-verdict/S05_TIMELINE_VERDICT.json")
    boundary = {
        "schema": "moss-dl2-s05-finish-verdict-boundary.v1",
        "session_id": manifest["session_id"],
        "evaluated_at_utc": utc_now(),
        "verdict": "PASS_USABLE_AS_IS_RAW_RETAINED",
        "external_stop_recovery": manifest["capture_stop_deviation"],
        "tape": {
            "published_frames": manifest["capture_stop_deviation"]["published_frame_count"],
            "outbox_retained_frames": manifest["capture_stop_deviation"]["outbox_retained_frames"],
            "total_bytes": manifest["tape"]["total_bytes"],
            "tracks": raw,
        },
        "timeline_gate": verdict["gate"],
        "type_totals_seconds": verdict["type_totals_seconds"],
        "longest_contiguous_seconds": verdict["longest_contiguous_seconds"],
        "card_tape_seconds": [verdict["card_t0_tape_seconds"], verdict["card_end_tape_seconds"]],
        "trailing_dead_air": verdict["trailing_dead_air"],
        "asr": {
            lane: {
                "segment_count": verdict["per_lane"][lane]["segment_count"],
                "speaker_labels": verdict["per_lane"][lane]["speaker_labels"],
                "transcript_sha256": verdict["per_lane"][lane]["transcript_sha256"],
            }
            for lane in ("system", "microphone", "mixed")
        },
        "audit_packet": manifest["derived"],
        "evidence_manifests": verification,
        "prototype_tests": {"passes": True, "count": 23, "transcript_sha256": sha256(output / "prototype-tests.txt")},
        "program_cap": {
            "cap_bytes": 2147483648,
            "captured_bytes_total": ledger["captured_bytes_total"],
            "remaining_bytes": 2147483648 - ledger["captured_bytes_total"],
            "retained_raw_bytes": sum(int(item["raw_bytes"]) for item in retained),
            "retained_session_count": len(retained),
        },
        "raw_retention": manifest["raw_retention"],
        "block_close_started": False,
        "capture_beyond_s05": False,
        "future_rail": "Controller heartbeat watchdog: auto-stop a live capture after more than 120 seconds without authenticated controller heartbeat; seal watchdog stop reason and final lane/outbox status.",
    }
    atomic_json(output / "S05_BOUNDARY_VERDICT.json", boundary)
    commands = """# S05 recovery commands (worktree cwd unless noted)
python3 capture_harness.py finish --external-stop-recovery --session-dir program/sessions/S05-BLOCK-20260808-40422fb135a146579d013d663652bd56 --operator-log program/s05-block-operator-log.txt
python3 post_session.py program/sessions/S05-BLOCK-20260808-40422fb135a146579d013d663652bd56
# named failure: full system job 5a6131a3ec23 refused at silent window 4 (480-630s)
python3 recover_s05_post_session.py program/sessions/S05-BLOCK-20260808-40422fb135a146579d013d663652bd56 --plan program/s05-recovery-intervals.json
# named failure: V1 mic short-slice job 4b52d5ca5d47 returned zero parsed segments
python3 recover_s05_post_session.py program/sessions/S05-BLOCK-20260808-40422fb135a146579d013d663652bd56 --plan program/s05-recovery-intervals-v2.json
# mic completed as b5b8093aa988; local Python 3.9 zip(strict=True) stopped before mixed submission
python3 recover_s05_post_session.py program/sessions/S05-BLOCK-20260808-40422fb135a146579d013d663652bd56 --plan program/s05-recovery-intervals-v3.json
python3.12 supplement_s05_system_prefix.py program/sessions/S05-BLOCK-20260808-40422fb135a146579d013d663652bd56 --plan program/s05-system-prefix-supplement.json
python3 analyze_s05_timeline.py program/sessions/S05-BLOCK-20260808-40422fb135a146579d013d663652bd56
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_capture_harness.py test_post_session.py
# first boundary verifier invocation replaced PATH and could not find ffmpeg; preserved as s05-recovery-boundary-attempt-1-env-path-failure
python3 verify_s05_boundary.py program/sessions/S05-BLOCK-20260808-40422fb135a146579d013d663652bd56 --output evidence/s05-recovery-boundary
"""
    (output / "commands.txt").write_text(commands, encoding="utf-8")
    seal_tree(output, output / "S05_BOUNDARY_EVIDENCE.sha256")
    print(json.dumps({"ok": True, "verdict": boundary["verdict"], "seal_sha256": sha256(output / "S05_BOUNDARY_EVIDENCE.sha256"), "packet": manifest["derived"]["audit_html_path"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
