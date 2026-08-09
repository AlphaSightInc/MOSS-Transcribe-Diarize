#!/usr/bin/env python3
"""Run and seal DL2-PREP dry-run proofs plus read-only deployment preflight."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, List

from capture_harness import atomic_json, sha256, utc_now


HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
SEAL = EVIDENCE / "DL2_PREP_EVIDENCE.sha256"


def run(argv: List[str], stdin: str = "") -> Dict[str, object]:
    completed = subprocess.run(argv, input=stdin or None, text=True, capture_output=True, check=False)
    return {
        "argv": argv,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def write_transcript(path: Path, result: Dict[str, object]) -> None:
    path.write_text(
        "COMMAND: %s\nEXIT: %s\n--- STDOUT ---\n%s--- STDERR ---\n%s"
        % (" ".join(result["argv"]), result["exit_code"], result["stdout"], result["stderr"]),
        encoding="utf-8",
    )


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    tests = run(["python3", "-m", "unittest", "-v", "test_capture_harness.py"])
    write_transcript(EVIDENCE / "green-safety-tests.txt", tests)
    dry = run(["python3", "dry_run.py"])
    write_transcript(EVIDENCE / "mock-end-to-end.txt", dry)
    clock = run(["sh", "-c", "date; date -u; TZ=America/New_York date '+%Y-%m-%dT%H:%M:%S%z %Z'"])
    write_transcript(EVIDENCE / "clock-observation.txt", clock)
    service_script = r'''set -euo pipefail
printf 'utc\t'; date -u +%Y-%m-%dT%H:%M:%SZ
for unit in moss-live-web.service moss-web.service moss-vllm.service; do
  printf 'service:%s\t%s/%s\n' "$unit" "$(systemctl --user is-active "$unit")" "$(systemctl --user is-enabled "$unit")"
done
pid="$(systemctl --user show moss-live-web.service -p MainPID --value)"
printf 'live_pid\t%s\n' "$pid"
printf 'deployed_sha\t%s\n' "$(git -C /mnt/d/Coding/MOSS-Transcribe-Diarize rev-parse HEAD)"
printf 'deployed_dirty_count\t%s\n' "$(git -C /mnt/d/Coding/MOSS-Transcribe-Diarize status --porcelain | wc -l)"
printf 'retention_flags\t'
tr '\0' '\n' < "/proc/$pid/cmdline" | grep -E '^--live-retention' | paste -sd, - || true
printf '\n'
'''
    service = run(
        ["ssh", "gyauo@ga0-alienware-rtx4070ti.local", "wsl.exe -d Ubuntu -- bash -s"],
        service_script,
    )
    write_transcript(EVIDENCE / "live-service-readonly-state.txt", service)
    capture = run(
        ["ssh", "ga0@m4mbp", "bash -s"],
        "set -euo pipefail\nprintf 'status\\t'; $HOME/.local/bin/mtd-capture status | tr -d '\\n'; printf '\\ncli_sha\\t'; shasum -a 256 $HOME/.local/bin/mtd-capture | cut -d' ' -f1\n",
    )
    write_transcript(EVIDENCE / "capture-host-readonly-state.txt", capture)
    preflight = run(
        [
            "python3",
            "capture_harness.py",
            "preflight",
            "--program-root",
            "program",
            "--projected-bytes",
            "256000000",
        ]
    )
    write_transcript(EVIDENCE / "real-preflight-refusal.txt", preflight)
    expected_refusal = (
        preflight["exit_code"] == 2 and "retention_not_declared" in str(preflight["stdout"])
    )
    service_healthy = (
        service["exit_code"] == 0
        and str(service["stdout"]).count("active/enabled") == 3
        and "deployed_sha\t9089b33210401111865da7abc160ab0bcb4aa266" in str(service["stdout"])
    )
    capture_idle = capture["exit_code"] == 0 and '"running":false' in str(capture["stdout"])
    verdict = {
        "schema": "moss-dl2-prep-readiness.v1",
        "created_at_utc": utc_now(),
        "sprint_anchor_et": "2026-08-05T21:50:00-04:00",
        "hour_10_deadline_et": "2026-08-06T07:50:00-04:00",
        "raw_delete_deadline_et": "2026-08-06T21:50:00-04:00",
        "clock_correction": "earlier 01:30 EDT anchor was operator-rejected; local date agrees with corrected 21:50 ET anchor",
        "safety_tests_pass": tests["exit_code"] == 0,
        "mock_end_to_end_pass": dry["exit_code"] == 0,
        "service_healthy": service_healthy,
        "capture_idle_both_lanes_stopped": capture_idle,
        "retention_preflight_named_refusal_pass": expected_refusal,
        "harness_dry_run_ready": tests["exit_code"] == 0 and dry["exit_code"] == 0,
        "ready_to_record": False,
        "blocker": "deployed live service has no --live-retention-* declaration; retention is startup-scoped and service changes are forbidden",
        "required_external_action": "deployment owner must establish the already-authorized retention declaration or authorize an in-scope service change; harness itself will not do so",
        "product_code_modified": False,
        "host_state_modified": False,
        "live_session_started": False,
        "overall": "DRY_RUN_READY_REAL_PILOT_BLOCKED",
    }
    atomic_json(EVIDENCE / "readiness-verdict.json", verdict)
    rows = []
    for path in sorted(EVIDENCE.rglob("*")):
        if path.is_file() and path != SEAL:
            rows.append("%s  %s" % (sha256(path), path.relative_to(HERE).as_posix()))
    SEAL.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0 if all((tests["exit_code"] == 0, dry["exit_code"] == 0, service_healthy, capture_idle, expected_refusal)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
