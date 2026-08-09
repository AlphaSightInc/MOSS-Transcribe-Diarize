#!/usr/bin/env python3
"""Provision bounded DL2 retention with sealed before/after evidence."""

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
    read_json,
    sha256,
    utc_now,
    validate_grant,
)

HERE = Path(__file__).resolve().parent
PROGRAM = HERE / "program"
OUT = HERE / "evidence" / "provisioning-20260805T2305"
ENV = "/mnt/d/Coding/MOSS-Transcribe-Diarize/ops/moss-live.env"
UNIT = "/home/devcontainers/.config/systemd/user/moss-live-web.service"
CONTROL = "/home/devcontainers/.local/share/moss-transcribe-diarize/live/dl2-capture-sprint-control-20260805T2305"


def run(argv: List[str], stdin: str = "") -> Dict[str, Any]:
    completed = subprocess.run(argv, input=stdin or None, text=True, capture_output=True, check=False)
    return {
        "argv": argv,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


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


def seal(destination: Path) -> None:
    rows = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path != destination and not path.name.endswith("_EVIDENCE.sha256"):
            rows.append("%s  %s" % (sha256(path), path.relative_to(OUT).as_posix()))
    destination.write_text("\n".join(rows) + "\n", encoding="utf-8")


def server(script: str) -> Dict[str, Any]:
    return run(["ssh", SERVER, SERVER_SHELL], script)


def capture(script: str) -> Dict[str, Any]:
    return run(["ssh", CAPTURE_HOST, "bash -s"], script)


def main() -> int:
    if OUT.exists():
        raise RuntimeError("provisioning_evidence_exists")
    OUT.mkdir(parents=True)
    grant = read_json(PROGRAM / "grant.json")
    ledger = read_json(PROGRAM / "program-ledger.json")
    validate_grant(grant, ledger, projected_bytes=4_000_000)

    clock = run(["sh", "-c", "date; date -u; TZ=America/New_York date '+%Y-%m-%dT%H:%M:%S%z %Z'"])
    save(OUT / "clock-before.txt", clock)
    capture_before = capture(
        "set -euo pipefail\n"
        "printf 'STATUS\\t'; $HOME/.local/bin/mtd-capture status | tr -d '\\n'; printf '\\n'"
        "printf 'CLI_SHA\\t'; shasum -a 256 $HOME/.local/bin/mtd-capture | cut -d' ' -f1\n"
    )
    save(OUT / "capture-before.txt", capture_before)
    capture_raw = require(capture_before, "capture_before")
    status = json.loads(re.search(r"STATUS\t([^\n]+)", capture_raw).group(1))
    if status.get("running"):
        raise RuntimeError("live_session_active_before")

    before_script = r'''set -euo pipefail
printf 'UTC\t'; date -u +%Y-%m-%dT%H:%M:%SZ
for unit in moss-live-web.service moss-web.service moss-vllm.service; do
  printf 'SERVICE:%s\t%s/%s\t%s\n' "$unit" "$(systemctl --user is-active "$unit")" "$(systemctl --user is-enabled "$unit")" "$(systemctl --user show "$unit" -p MainPID --value)"
done
printf '%s\n' '--- SHOW ---'
systemctl --user show moss-live-web.service -p FragmentPath -p DropInPaths -p EnvironmentFiles -p ExecStart -p ActiveEnterTimestamp
printf '%s\n' '--- UNIT EXACT ---'
cat /home/devcontainers/.config/systemd/user/moss-live-web.service
printf '%s\n' '--- UNIT SHA ---'
sha256sum /home/devcontainers/.config/systemd/user/moss-live-web.service
pid="$(systemctl --user show moss-live-web.service -p MainPID --value)"
printf '%s\n' '--- INVOCATION EXACT ARGV ---'
tr '\0' '\n' < "/proc/$pid/cmdline"
printf '%s\n' '--- ENV HASH/METADATA/RETENTION ---'
stat -c '%n mode=%a uid=%u gid=%g bytes=%s' /mnt/d/Coding/MOSS-Transcribe-Diarize/ops/moss-live.env
sha256sum /mnt/d/Coding/MOSS-Transcribe-Diarize/ops/moss-live.env
sed -n '/^MOSS_LIVE_RETENTION_/p' /mnt/d/Coding/MOSS-Transcribe-Diarize/ops/moss-live.env
printf '%s\n' '--- DEPLOYMENT ---'
git -C /mnt/d/Coding/MOSS-Transcribe-Diarize rev-parse HEAD
git -C /mnt/d/Coding/MOSS-Transcribe-Diarize status --porcelain
'''
    before = server(before_script)
    save(OUT / "server-before.txt", before)
    before_raw = require(before, "server_before")
    env_match = re.search(r"([0-9a-f]{64})  " + re.escape(ENV), before_raw)
    unit_match = re.search(r"([0-9a-f]{64})  " + re.escape(UNIT), before_raw)
    if not env_match or not unit_match:
        raise RuntimeError("before_hash_missing")
    if "MOSS_LIVE_RETENTION_" in before_raw:
        raise RuntimeError("retention_already_declared")
    if before_raw.count("active/enabled") != 3 or DEPLOYED_SHA not in before_raw:
        raise RuntimeError("before_state_invalid")
    before_env_hash = env_match.group(1)
    before_unit_hash = unit_match.group(1)
    vllm_pid = int(re.search(r"SERVICE:moss-vllm.service\tactive/enabled\t(\d+)", before_raw).group(1))
    atomic_json(
        OUT / "before-verdict.json",
        {
            "schema": "moss-dl2-provision-before.v1",
            "recorded_at_utc": utc_now(),
            "operator_anchor_et": "2026-08-05T23:05:00-04:00",
            "live_session_active": False,
            "services_active_enabled": True,
            "deployed_sha": DEPLOYED_SHA,
            "live_env_sha256": before_env_hash,
            "live_unit_sha256": before_unit_hash,
            "retention_declared": False,
            "vllm_pid": vllm_pid,
            "overall": "PASS_SAFE_TO_PROVISION",
        },
    )
    seal(OUT / "BEFORE_EVIDENCE.sha256")

    root = str(grant["retention_root"])
    cap = int(grant["program_cap_bytes"])
    ttl = int(grant["ttl_seconds"])
    apply_script = r'''set -euo pipefail
env_file="%s"
unit_file="%s"
control="%s"
root="%s"
expected_before="%s"
cap="%d"
ttl="%d"
test "$(sha256sum "$env_file" | cut -d' ' -f1)" = "$expected_before"
! grep -q '^MOSS_LIVE_RETENTION_' "$env_file"
test "$(systemctl --user is-active moss-live-web.service)" = active
test "$(systemctl --user is-active moss-vllm.service)" = active
install -d -m 700 "$control"
cp --preserve=all "$env_file" "$control/moss-live.env.before"
cp --preserve=all "$unit_file" "$control/moss-live-web.service.before"
pid="$(systemctl --user show moss-live-web.service -p MainPID --value)"
cp "/proc/$pid/cmdline" "$control/invocation.before.nul"
chmod 600 "$control"/*
test "$(sha256sum "$control/moss-live.env.before" | cut -d' ' -f1)" = "$expected_before"
install -d -m 700 "$root"
test -z "$(find "$root" -mindepth 1 -print -quit)"
rollback() {
  cp "$control/moss-live.env.before" "$env_file"
  systemctl --user restart moss-live-web.service || true
  rmdir "$root" 2>/dev/null || true
}
trap rollback ERR
printf '\nMOSS_LIVE_RETENTION_ROOT=%%s\nMOSS_LIVE_RETENTION_MAX_BYTES=%%s\nMOSS_LIVE_RETENTION_TTL_SECONDS=%%s\n' "$root" "$cap" "$ttl" >> "$env_file"
systemctl --user restart moss-live-web.service
for _ in $(seq 1 30); do
  [ "$(systemctl --user is-active moss-live-web.service || true)" = active ] && break
  sleep 1
done
test "$(systemctl --user is-active moss-live-web.service)" = active
test "$(systemctl --user is-active moss-vllm.service)" = active
trap - ERR
printf 'before_env_sha256\t%%s\n' "$expected_before"
printf 'provisioned_env_sha256\t%%s\n' "$(sha256sum "$env_file" | cut -d' ' -f1)"
printf 'backup_env_sha256\t%%s\n' "$(sha256sum "$control/moss-live.env.before" | cut -d' ' -f1)"
printf 'backup_unit_sha256\t%%s\n' "$(sha256sum "$control/moss-live-web.service.before" | cut -d' ' -f1)"
printf 'backup_invocation_sha256\t%%s\n' "$(sha256sum "$control/invocation.before.nul" | cut -d' ' -f1)"
printf 'root_stat\t'; stat -c 'path=%%n mode=%%a uid=%%u gid=%%g' "$root"
printf 'live_pid\t%%s\n' "$(systemctl --user show moss-live-web.service -p MainPID --value)"
printf 'vllm_pid\t%%s\n' "$(systemctl --user show moss-vllm.service -p MainPID --value)"
''' % (ENV, UNIT, CONTROL, root, before_env_hash, cap, ttl)
    applied = server(apply_script)
    save(OUT / "provision-apply.txt", applied)
    applied_raw = require(applied, "provision_apply")
    provisioned_hash = re.search(r"provisioned_env_sha256\t([0-9a-f]{64})", applied_raw).group(1)
    if int(re.search(r"vllm_pid\t(\d+)", applied_raw).group(1)) != vllm_pid:
        raise RuntimeError("vllm_pid_changed")

    after_script = r'''set -euo pipefail
printf 'UTC\t'; date -u +%Y-%m-%dT%H:%M:%SZ
for unit in moss-live-web.service moss-web.service moss-vllm.service; do
  printf 'SERVICE:%s\t%s/%s\t%s\n' "$unit" "$(systemctl --user is-active "$unit")" "$(systemctl --user is-enabled "$unit")" "$(systemctl --user show "$unit" -p MainPID --value)"
done
pid="$(systemctl --user show moss-live-web.service -p MainPID --value)"
printf '%s\n' '--- EFFECTIVE INVOCATION ---'
tr '\0' '\n' < "/proc/$pid/cmdline"
printf '%s\n' '--- RETENTION ENV ---'
sed -n '/^MOSS_LIVE_RETENTION_/p' /mnt/d/Coding/MOSS-Transcribe-Diarize/ops/moss-live.env
printf '%s\n' '--- ROOT ---'
stat -c 'path=%n mode=%a uid=%u gid=%g bytes=%s' /home/devcontainers/.local/share/moss-transcribe-diarize/live/dl2-capture-sprint
printf '%s\n' '--- PROVIDER SOURCE ---'
jq -r '.source_revision' /home/devcontainers/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json
printf '%s\n' '--- DEPLOYMENT ---'
git -C /mnt/d/Coding/MOSS-Transcribe-Diarize rev-parse HEAD
git -C /mnt/d/Coding/MOSS-Transcribe-Diarize status --porcelain
'''
    after = server(after_script)
    save(OUT / "server-after-provision.txt", after)
    after_raw = require(after, "server_after")
    for expected in (root, str(cap), str(ttl), DEPLOYED_SHA, "mode=700"):
        if expected not in after_raw:
            raise RuntimeError("effective_value_missing:%s" % expected)

    atomic_json(
        OUT / "deprovision-contract.json",
        {
            "schema": "moss-dl2-deprovision-contract.v1",
            "server": SERVER,
            "server_shell": SERVER_SHELL,
            "env_path": ENV,
            "unit_path": UNIT,
            "control_path": CONTROL,
            "retention_root": root,
            "before_env_sha256": before_env_hash,
            "provisioned_env_sha256": provisioned_hash,
            "before_unit_sha256": before_unit_hash,
            "vllm_pid_at_provisioning": vllm_pid,
            "restore_command": "python3 deprovision_retention.py",
        },
    )
    atomic_json(
        OUT / "provision-phase-verdict.json",
        {
            "schema": "moss-dl2-provision-phase.v1",
            "created_at_utc": utc_now(),
            "root": root,
            "ttl_seconds": ttl,
            "cap_bytes": cap,
            "effective_flags_verified": True,
            "vllm_pid_unchanged": True,
            "source_revision": DEPLOYED_SHA,
            "canary_pending": True,
            "overall": "PROVISIONED_PENDING_CANARY",
        },
    )
    seal(OUT / "PROVISION_PHASE_EVIDENCE.sha256")
    print(json.dumps({"ok": True, "state": "PROVISIONED_PENDING_CANARY", "evidence": str(OUT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
