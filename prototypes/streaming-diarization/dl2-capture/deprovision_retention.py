#!/usr/bin/env python3
"""Hash-guarded one-command restoration of the exact pre-sprint live profile."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "evidence" / "provisioning-20260805T2305" / "deprovision-contract.json"


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    script = r'''set -euo pipefail
env_file="%s"
unit_file="%s"
control="%s"
root="%s"
expected_current="%s"
expected_before="%s"
expected_unit="%s"
current="$(sha256sum "$env_file" | cut -d' ' -f1)"
test "$current" = "$expected_current" || { echo "REFUSED provisioned_env_hash_drift:$current"; exit 2; }
test "$(sha256sum "$unit_file" | cut -d' ' -f1)" = "$expected_unit" || { echo 'REFUSED unit_hash_drift'; exit 2; }
test "$(sha256sum "$control/moss-live.env.before" | cut -d' ' -f1)" = "$expected_before" || { echo 'REFUSED rollback_snapshot_hash_drift'; exit 2; }
test -z "$(find "$root" -mindepth 1 -print -quit)" || { echo 'REFUSED retention_root_not_empty'; exit 2; }
cp "$control/moss-live.env.before" "$env_file"
test "$(sha256sum "$env_file" | cut -d' ' -f1)" = "$expected_before"
systemctl --user restart moss-live-web.service
for _ in $(seq 1 30); do
  [ "$(systemctl --user is-active moss-live-web.service || true)" = active ] && break
  sleep 1
done
test "$(systemctl --user is-active moss-live-web.service)" = active
test "$(systemctl --user is-active moss-vllm.service)" = active
pid="$(systemctl --user show moss-live-web.service -p MainPID --value)"
! tr '\0' '\n' < "/proc/$pid/cmdline" | grep -q '^--live-retention'
rmdir "$root"
rm -f "$control/moss-live.env.before" "$control/moss-live-web.service.before" "$control/invocation.before.nul"
rmdir "$control"
printf 'PASS restored_env_sha256\t%%s\n' "$(sha256sum "$env_file" | cut -d' ' -f1)"
printf 'live_pid\t%%s\n' "$pid"
printf 'vllm_pid\t%%s\n' "$(systemctl --user show moss-vllm.service -p MainPID --value)"
''' % (
        contract["env_path"],
        contract["unit_path"],
        contract["control_path"],
        contract["retention_root"],
        contract["provisioned_env_sha256"],
        contract["before_env_sha256"],
        contract["before_unit_sha256"],
    )
    completed = subprocess.run(
        ["ssh", contract["server"], contract["server_shell"]],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
