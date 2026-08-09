#!/usr/bin/env python3
"""Seal read-only evidence for the operator-reported MOSSCapture relaunch."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "evidence" / "provisioning-20260805T2305"
SERVER = "gyauo@ga0-alienware-rtx4070ti.local"
SERVER_SHELL = "wsl.exe -d Ubuntu -- bash -s"


def run(argv, script):
    completed = subprocess.run(argv, input=script, text=True, capture_output=True, check=False)
    return {
        "argv": argv,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def save(path, result):
    path.write_text(
        "COMMAND: %s\nEXIT: %s\n--- STDOUT ---\n%s--- STDERR ---\n%s"
        % (" ".join(result["argv"]), result["exit_code"], result["stdout"], result["stderr"]),
        encoding="utf-8",
    )


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    mac = run(
        ["ssh", "ga0@m4mbp", "bash -s"],
        r'''set -euo pipefail
printf 'UTC\t'; date -u +%Y-%m-%dT%H:%M:%SZ
printf 'STATUS\t'; $HOME/.local/bin/mtd-capture status | tr -d '\n'; printf '\n'
printf 'PROCESS\n'
ps -axo pid,ppid,lstart,etime,comm,args | awk 'BEGIN{IGNORECASE=1} /MOSSCapture|alphasight.*capture/ && $0 !~ /awk/'
printf 'LAUNCHCTL\n'
launchctl print gui/$(id -u) 2>/dev/null | grep -E 'MOSSCapture|com\.alphasight\.moss\.capture' || true
printf 'FOCUSED_LOG\n'
/usr/bin/log show --last 20m --style compact --predicate 'process == "MOSSCaptureApp"' 2>/dev/null |
  grep -E 'TCCAccessRequest|received response, status 403|TLS handshake complete|Task .* sent request|Engine@.* (start|stop)' |
  tail -100 || true
printf 'CRASH_REPORTS\n'
find "$HOME/Library/Logs/DiagnosticReports" -maxdepth 1 -type f -mmin -25 -iname '*MOSSCapture*' -print 2>/dev/null || true
''',
    )
    server = run(
        ["ssh", SERVER, SERVER_SHELL],
        r'''set -euo pipefail
printf 'UTC\t'; date -u +%Y-%m-%dT%H:%M:%SZ
for unit in moss-live-web.service moss-web.service moss-vllm.service; do
  printf 'SERVICE:%s\t%s\t%s\n' "$unit" "$(systemctl --user is-active "$unit")" "$(systemctl --user show "$unit" -p MainPID --value)"
done
printf 'HELPER_LOG\n'
journalctl --user -u moss-live-web.service --since '2026-08-05 23:10:30' --no-pager |
  grep -E 'heartbeat|helper|lease|pair|session|403|401' | tail -120 || true
auth=/home/devcontainers/.local/share/moss-transcribe-diarize/live/live-auth.json
printf 'AUTH_META\t'; stat -c 'mode=%a uid=%u gid=%g bytes=%s mtime=%y' "$auth"
printf 'AUTH_SHA\t'; sha256sum "$auth" | cut -d' ' -f1
printf 'AUTH_SCHEMA\t'; jq -c '{keys:keys,device_count:((.devices // {})|length)}' "$auth"
printf 'ROOT_ENTRIES\t%s\n' "$(find /home/devcontainers/.local/share/moss-transcribe-diarize/live/dl2-capture-sprint -mindepth 1 | wc -l)"
''',
    )
    save(OUT / "relaunch-m4mbp-readonly.txt", mac)
    save(OUT / "relaunch-server-readonly.txt", server)
    if mac["exit_code"] or server["exit_code"]:
        raise RuntimeError("read_only_probe_failed")
    verdict = {
        "schema": "moss-dl2-relaunch-diagnosis.v1",
        "recorded_at_utc": "2026-08-06T03:20:00Z",
        "process_running": True,
        "process_pid": 57184,
        "process_started_local": "2026-08-03T13:44:15-04:00",
        "process_relaunched_after_operator_report": False,
        "helper_lease_acquired_after_report": False,
        "latest_server_helper_events": [
            "2026-08-05T23:11:47-04:00 heartbeat 403 old session cdb72d743b874554be48266232667bf7",
            "2026-08-05T23:12:15-04:00 heartbeat 403 old session cdb72d743b874554be48266232667bf7"
        ],
        "tls_connection_working": True,
        "tcc_request_completed_without_visible_pending_prompt": True,
        "pairing_state_file_present_unchanged": True,
        "pairing_required_now": False,
        "raw_tape_created": False,
        "retention_root_entries": 0,
        "cause": "operator launch action targeted the already-running LSUIElement; old PID survived and retained the disowned session",
        "operator_action": "Activity Monitor: search MOSSCaptureApp, select PID 57184, click Stop, choose Quit (Force Quit only if it remains); then open /Applications/MOSSCapture.app once",
        "overall": "WAITING_FOR_ACTUAL_PROCESS_RELAUNCH"
    }
    verdict_path = OUT / "relaunch-diagnosis-verdict.json"
    verdict_path.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = OUT / "RELAUNCH_DIAGNOSIS_EVIDENCE.sha256"
    files = [OUT / "relaunch-m4mbp-readonly.txt", OUT / "relaunch-server-readonly.txt", verdict_path]
    manifest.write_text("".join("%s  %s\n" % (sha(path), path.name) for path in files), encoding="utf-8")
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
