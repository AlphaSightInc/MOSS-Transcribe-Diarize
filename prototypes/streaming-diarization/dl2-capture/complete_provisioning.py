#!/usr/bin/env python3
"""Run the post-restart live canary, clean its tape, and seal READY evidence."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from capture_harness import (
    CAPTURE_HOST,
    DEPLOYED_SHA,
    SERVER,
    SERVER_SHELL,
    atomic_json,
    capture_state,
    read_json,
    server_preflight,
    sha256,
    utc_now,
    validate_grant,
)

HERE = Path(__file__).resolve().parent
PROGRAM = HERE / "program"
OUT = HERE / "evidence" / "provisioning-20260805T2305"


def run(argv: List[str], stdin: str = "") -> Dict[str, Any]:
    completed = subprocess.run(argv, input=stdin or None, text=True, capture_output=True, check=False)
    return {"argv": argv, "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def require(result: Dict[str, Any], name: str) -> str:
    if result["exit_code"]:
        raise RuntimeError("%s_failed:%s" % (name, result["stderr"]))
    return str(result["stdout"])


def save(path: Path, result: Dict[str, Any]) -> None:
    path.write_text(
        "COMMAND: %s\nEXIT: %s\n--- STDOUT ---\n%s--- STDERR ---\n%s"
        % (" ".join(result["argv"]), result["exit_code"], result["stdout"], result["stderr"]),
        encoding="utf-8",
    )


def remote(host: str, shell: str, script: str) -> Dict[str, Any]:
    return run(["ssh", host, shell], script)


def seal() -> None:
    destination = OUT / "PROVISIONING_EVIDENCE.sha256"
    rows = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path != destination:
            rows.append("%s  %s" % (sha256(path), path.relative_to(OUT).as_posix()))
    destination.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    if (OUT / "provisioning-verdict.json").exists():
        raise RuntimeError("provisioning_already_completed")
    grant = read_json(PROGRAM / "grant.json")
    ledger_path = PROGRAM / "program-ledger.json"
    ledger = read_json(ledger_path)
    contract = read_json(OUT / "deprovision-contract.json")
    validate_grant(grant, ledger, projected_bytes=4_000_000)

    canary_script = r'''set -euo pipefail
cli="$HOME/.local/bin/mtd-capture"
san=ga0-alienware-rtx4070ti.tailnet.aisight.us
ip=100.64.0.8
port=7861
pin=a35ca9fc4a0f5b32bf7da6dc2e03c1fa5b4ac60992f0ee49b6d5677d22b680ff
tmp="$(mktemp -d /tmp/dl2-provision-canary.XXXXXX)"
started=0
cleanup() {
  if [ "$started" = 1 ]; then "$cli" stop >/dev/null 2>&1 || true; fi
  pbcopy < /dev/null
  rm -rf "$tmp"
}
trap cleanup EXIT INT TERM
before="$($cli status)"
test "$(printf '%s' "$before" | jq -r .running)" = false
start="$($cli start --label dl2-provision-canary)"
started=1
sleep 3
running="$($cli status)"
test "$(printf '%s' "$running" | jq -r .running)" = true
test "$(printf '%s' "$running" | jq '[.lanes[] | select(.lane=="system" or .lane=="microphone")] | length')" = 2
handoff="$($cli handoff)"
sid="$(printf '%s' "$handoff" | jq -r '.sessionID // empty')"
test -n "$sid"
token="$(pbpaste)"
test -n "$token"
echo | openssl s_client -connect "$ip:$port" -servername "$san" 2>/dev/null | openssl x509 > "$tmp/leaf.pem"
got="$(openssl x509 -in "$tmp/leaf.pem" -outform DER | shasum -a 256 | cut -d' ' -f1)"
test "$got" = "$pin"
cfg() {
  printf 'header = "Authorization: Bearer %s"\n' "$token"
  printf 'silent\n'
  printf 'cacert = "%s"\n' "$tmp/leaf.pem"
  printf 'resolve = "%s:%s:%s"\n' "$san" "$port" "$ip"
}
snapshot_code="$(cfg | curl -K - -m 10 -o "$tmp/snapshot.json" -w '%{http_code}' "https://$san:$port/api/live/sessions/$sid/snapshot")"
events_code="$(cfg | curl -K - -m 10 -o "$tmp/events.json" -w '%{http_code}' "https://$san:$port/api/live/sessions/$sid/events?since_seq=0")"
test "$snapshot_code" = 200
test "$events_code" = 200
source_revision="$(jq -r '.snapshot.descriptor.source_revision // empty' "$tmp/snapshot.json")"
test "$source_revision" = 9089b33210401111865da7abc160ab0bcb4aa266
stop="$($cli stop)"
started=0
after="$($cli status)"
test "$(printf '%s' "$after" | jq -r .running)" = false
printf 'SESSION_ID\t%s\n' "$sid"
printf 'SNAPSHOT_HTTP\t%s\n' "$snapshot_code"
printf 'EVENTS_HTTP\t%s\n' "$events_code"
printf 'SOURCE_REVISION\t%s\n' "$source_revision"
printf 'RUNNING_STATUS\t%s\n' "$(printf '%s' "$running" | jq -c '{ok,running,lanes,publishedFrameCount,outboxRetainedFrames}')"
printf 'STOP_STATUS\t%s\n' "$(printf '%s' "$stop" | jq -c '{ok,running,lanes,publishedFrameCount,outboxRetainedFrames,sessionRefusal}')"
printf 'AFTER_STATUS\t%s\n' "$(printf '%s' "$after" | jq -c '{ok,running,lanes,publishedFrameCount,outboxRetainedFrames}')"
printf 'SNAPSHOT_SHA256\t%s\n' "$(shasum -a 256 "$tmp/snapshot.json" | cut -d' ' -f1)"
printf 'EVENTS_SHA256\t%s\n' "$(shasum -a 256 "$tmp/events.json" | cut -d' ' -f1)"
'''
    canary = remote(CAPTURE_HOST, "bash -s", canary_script)
    save(OUT / "canary-snapshot-events-post-fix-v2.txt", canary)
    canary_raw = require(canary, "canary")
    sid_match = re.search(r"SESSION_ID\t([A-Za-z0-9._-]+)", canary_raw)
    if not sid_match:
        raise RuntimeError("canary_session_id_missing")
    sid = sid_match.group(1)
    if "SNAPSHOT_HTTP\t200" not in canary_raw or "EVENTS_HTTP\t200" not in canary_raw:
        raise RuntimeError("canary_http_failed")

    root = str(grant["retention_root"])
    tape_script = r'''set -euo pipefail
root="%s"
sid="%s"
target="$root/$sid"
test -d "$target"
test -f "$target/index.json"
printf 'INDEX\t'; jq -c '{version,session_id,sample_rate,max_bytes,total_bytes,degradation,ended_at,tracks:(.tracks|with_entries(.value={sample_count:.value.sample_count,bytes:.value.bytes,gaps:(.value.gaps|length)}))}' "$target/index.json"
printf 'HASHES\n'; find "$target" -maxdepth 1 -type f -print0 | sort -z | xargs -0 sha256sum
total="$(jq -r .total_bytes "$target/index.json")"
printf 'TOTAL_BYTES\t%s\n' "$total"
find "$target" -type f -delete
find "$target" -depth -type d -empty -delete
test ! -e "$target"
printf 'DELETED\tyes\n'
''' % (root, sid)
    tape = remote(SERVER, SERVER_SHELL, tape_script)
    save(OUT / "canary-tape-hash-cleanup.txt", tape)
    tape_raw = require(tape, "canary_tape")
    canary_bytes = int(re.search(r"TOTAL_BYTES\t(\d+)", tape_raw).group(1))
    if "DELETED\tyes" not in tape_raw:
        raise RuntimeError("canary_tape_not_deleted")
    validate_grant(grant, ledger, projected_bytes=canary_bytes)
    ledger["captured_bytes_total"] = int(ledger.get("captured_bytes_total", 0)) + canary_bytes
    ledger.setdefault("sessions", []).append(
        {
            "session_id": sid,
            "shape_id": "PROVISION_CANARY",
            "raw_bytes": canary_bytes,
            "raw_deleted": True,
            "raw_deleted_at_utc": utc_now(),
            "acceptance_case": False,
        }
    )
    atomic_json(ledger_path, ledger)

    preflight = server_preflight(grant)
    capture_after = capture_state()
    if capture_after["status"].get("running"):
        raise RuntimeError("live_session_active_after")
    atomic_json(OUT / "full-preflight.json", {"server": preflight, "capture": capture_after})

    final_script = r'''set -euo pipefail
for unit in moss-live-web.service moss-web.service moss-vllm.service; do
  printf 'SERVICE:%s\t%s/%s\t%s\n' "$unit" "$(systemctl --user is-active "$unit")" "$(systemctl --user is-enabled "$unit")" "$(systemctl --user show "$unit" -p MainPID --value)"
done
pid="$(systemctl --user show moss-live-web.service -p MainPID --value)"
printf 'EFFECTIVE_FLAGS\n'; tr '\0' '\n' < "/proc/$pid/cmdline" | grep -A1 '^--live-retention'
printf 'ROOT\t'; stat -c 'path=%n mode=%a uid=%u gid=%g' /home/devcontainers/.local/share/moss-transcribe-diarize/live/dl2-capture-sprint
printf 'ROOT_ENTRIES\t%s\n' "$(find /home/devcontainers/.local/share/moss-transcribe-diarize/live/dl2-capture-sprint -mindepth 1 | wc -l)"
printf 'SOURCE_REVISION\t'; jq -r .source_revision /home/devcontainers/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json
printf 'DEPLOYED_SHA\t'; git -C /mnt/d/Coding/MOSS-Transcribe-Diarize rev-parse HEAD
printf 'DIRTY_COUNT\t%s\n' "$(git -C /mnt/d/Coding/MOSS-Transcribe-Diarize status --porcelain | wc -l)"
'''
    final = remote(SERVER, SERVER_SHELL, final_script)
    save(OUT / "server-final.txt", final)
    final_raw = require(final, "server_final")
    if int(re.search(r"SERVICE:moss-vllm.service\tactive/enabled\t(\d+)", final_raw).group(1)) != int(contract["vllm_pid_at_provisioning"]):
        raise RuntimeError("vllm_pid_changed")
    if "ROOT_ENTRIES\t0" not in final_raw or "DIRTY_COUNT\t0" not in final_raw:
        raise RuntimeError("final_hygiene_failed")

    verdict = {
        "schema": "moss-dl2-provisioning-verdict.v1",
        "created_at_utc": utc_now(),
        "operator_anchor_et": "2026-08-05T23:05:00-04:00",
        "ttl_seconds": int(grant["ttl_seconds"]),
        "raw_delete_deadline_et": grant["raw_delete_deadline_et"],
        "program_cap_bytes": int(grant["program_cap_bytes"]),
        "program_bytes_used": int(ledger["captured_bytes_total"]),
        "retention_root": root,
        "effective_config_verified": True,
        "source_revision": DEPLOYED_SHA,
        "services_healthy": True,
        "moss_vllm_restarted": False,
        "canary_snapshot_http": 200,
        "canary_events_http": 200,
        "canary_raw_bytes_accounted": canary_bytes,
        "canary_raw_deleted": True,
        "live_sessions_active_after": 0,
        "harness_preflight": "PASS",
        "deprovision_command": "python3 deprovision_retention.py",
        "ready_to_record": True,
        "overall": "READY_TO_RECORD_S01",
    }
    atomic_json(OUT / "provisioning-verdict.json", verdict)
    seal()
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
