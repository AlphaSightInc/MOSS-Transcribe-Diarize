#!/usr/bin/env python3
"""Execute the sealed DL2 deprovision contract and seal before/after proof."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from capture_harness import (
    DEPLOYED_SHA,
    HarnessRefusal,
    assert_capture_idle,
    atomic_json,
    capture_state,
    read_json,
    server_script,
    sha256,
    utc_now,
)
from post_session import seal_tree


HERE = Path(__file__).resolve().parent
CONTRACT_PATH = HERE / "evidence/provisioning-20260805T2305/deprovision-contract.json"
PROVISION_SEAL = HERE / "evidence/provisioning-20260805T2305/PROVISIONING_BLOCK_EVIDENCE.sha256"
RAW_CLEANUP_SEAL = HERE / "evidence/block-close-raw-cleanup-20260809/RAW_CLEANUP_EVIDENCE.sha256"


def verify_row(seal: Path, relative: str, expected: str) -> None:
    rows = dict(line.split("  ", 1)[::-1] for line in seal.read_text(encoding="utf-8").splitlines() if line.strip())
    if rows.get(relative) != expected:
        raise HarnessRefusal("deprovision_sealed_contract_mismatch:" + relative)


def parse_tab(raw: str) -> dict[str, str]:
    output = {}
    for line in raw.splitlines():
        if "\t" in line:
            key, value = line.split("\t", 1)
            output[key] = value
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    contract = read_json(CONTRACT_PATH)
    contract_hash = sha256(CONTRACT_PATH)
    verify_row(PROVISION_SEAL, "deprovision-contract.json", contract_hash)
    cleanup_verdict = read_json(RAW_CLEANUP_SEAL.parent / "RAW_CLEANUP_VERDICT.json")
    if cleanup_verdict.get("verdict") != "PASS_ALL_RETAINED_RAW_DELETED" or not cleanup_verdict.get("remote_root_empty"):
        raise HarnessRefusal("deprovision_raw_cleanup_not_complete")
    capture_before = capture_state()
    assert_capture_idle(capture_before)

    before_script = r'''set -euo pipefail
env_file="%s"
unit_file="%s"
control="%s"
root="%s"
printf 'UTC\t%%s\n' "$(date -u +%%Y-%%m-%%dT%%H:%%M:%%SZ)"
for unit in moss-live-web.service moss-web.service moss-vllm.service; do
  printf 'SERVICE:%%s\t%%s/%%s/%%s\n' "$unit" "$(systemctl --user is-active "$unit")" "$(systemctl --user is-enabled "$unit")" "$(systemctl --user show "$unit" -p MainPID --value)"
done
pid="$(systemctl --user show moss-live-web.service -p MainPID --value)"
printf 'ENV_HASH\t%%s\n' "$(sha256sum "$env_file" | cut -d' ' -f1)"
printf 'UNIT_HASH\t%%s\n' "$(sha256sum "$unit_file" | cut -d' ' -f1)"
printf 'SNAPSHOT_ENV_HASH\t%%s\n' "$(sha256sum "$control/moss-live.env.before" | cut -d' ' -f1)"
printf 'SNAPSHOT_UNIT_HASH\t%%s\n' "$(sha256sum "$control/moss-live-web.service.before" | cut -d' ' -f1)"
printf 'SNAPSHOT_INVOCATION_HASH\t%%s\n' "$(sha256sum "$control/invocation.before.nul" | cut -d' ' -f1)"
printf 'CURRENT_INVOCATION_HASH\t%%s\n' "$(sha256sum "/proc/$pid/cmdline" | cut -d' ' -f1)"
printf 'ROOT_ENTRIES\t%%s\n' "$(find "$root" -mindepth 1 | wc -l)"
printf 'RETENTION_ENV_LINES\t%%s\n' "$(grep -c '^MOSS_LIVE_RETENTION_' "$env_file" || true)"
printf 'RETENTION_ARG_LINES\t%%s\n' "$(tr '\0' '\n' < "/proc/$pid/cmdline" | grep -c '^--live-retention' || true)"
descriptor=''
for _ in $(seq 1 30); do
  if descriptor="$(curl -ksS --max-time 2 https://127.0.0.1:7861/api/live/descriptor 2>/dev/null)"; then break; fi
  sleep 1
done
test -n "$descriptor"
printf 'DESCRIPTOR\t'; printf '%%s' "$descriptor" | jq -c .descriptor
printf 'DEPLOYED_SHA\t%%s\n' "$(git -C /mnt/d/Coding/MOSS-Transcribe-Diarize rev-parse HEAD)"
printf 'DEPLOYED_DIRTY_COUNT\t%%s\n' "$(git -C /mnt/d/Coding/MOSS-Transcribe-Diarize status --porcelain | wc -l)"
''' % (contract["env_path"], contract["unit_path"], contract["control_path"], contract["retention_root"])
    before_raw = server_script(before_script)
    (output / "before-state.txt").write_text(before_raw, encoding="utf-8")
    before = parse_tab(before_raw)
    if before.get("ENV_HASH") != contract["provisioned_env_sha256"]:
        raise HarnessRefusal("deprovision_before_env_hash_drift")
    if before.get("UNIT_HASH") != contract["before_unit_sha256"] or before.get("SNAPSHOT_UNIT_HASH") != contract["before_unit_sha256"]:
        raise HarnessRefusal("deprovision_before_unit_hash_drift")
    if before.get("SNAPSHOT_ENV_HASH") != contract["before_env_sha256"]:
        raise HarnessRefusal("deprovision_snapshot_env_hash_drift")
    if before.get("ROOT_ENTRIES") != "0" or before.get("RETENTION_ENV_LINES") != "3" or before.get("RETENTION_ARG_LINES") != "3":
        raise HarnessRefusal("deprovision_before_effective_state_invalid")
    before_descriptor = json.loads(before["DESCRIPTOR"])
    if before_descriptor.get("source_revision") != DEPLOYED_SHA:
        raise HarnessRefusal("deprovision_before_descriptor_revision_mismatch")

    command = subprocess.run(
        ["python3", "deprovision_retention.py"],
        cwd=HERE,
        text=True,
        capture_output=True,
        check=False,
    )
    (output / "deprovision-command.txt").write_text(
        "COMMAND: python3 deprovision_retention.py\nEXIT: %d\n--- STDOUT ---\n%s--- STDERR ---\n%s"
        % (command.returncode, command.stdout, command.stderr),
        encoding="utf-8",
    )
    if command.returncode:
        raise HarnessRefusal("deprovision_command_failed")

    after_script = r'''set -euo pipefail
env_file="%s"
unit_file="%s"
control="%s"
root="%s"
printf 'UTC\t%%s\n' "$(date -u +%%Y-%%m-%%dT%%H:%%M:%%SZ)"
for unit in moss-live-web.service moss-web.service moss-vllm.service; do
  printf 'SERVICE:%%s\t%%s/%%s/%%s\n' "$unit" "$(systemctl --user is-active "$unit")" "$(systemctl --user is-enabled "$unit")" "$(systemctl --user show "$unit" -p MainPID --value)"
done
pid="$(systemctl --user show moss-live-web.service -p MainPID --value)"
printf 'ENV_HASH\t%%s\n' "$(sha256sum "$env_file" | cut -d' ' -f1)"
printf 'UNIT_HASH\t%%s\n' "$(sha256sum "$unit_file" | cut -d' ' -f1)"
printf 'INVOCATION_HASH\t%%s\n' "$(sha256sum "/proc/$pid/cmdline" | cut -d' ' -f1)"
printf 'ROOT_EXISTS\t%%s\n' "$([ -e "$root" ] && echo yes || echo no)"
printf 'CONTROL_EXISTS\t%%s\n' "$([ -e "$control" ] && echo yes || echo no)"
printf 'RETENTION_ENV_LINES\t%%s\n' "$(grep -c '^MOSS_LIVE_RETENTION_' "$env_file" || true)"
printf 'RETENTION_ARG_LINES\t%%s\n' "$(tr '\0' '\n' < "/proc/$pid/cmdline" | grep -c '^--live-retention' || true)"
printf 'DESCRIPTOR\t'; curl -ksS --max-time 10 https://127.0.0.1:7861/api/live/descriptor | jq -c .descriptor
printf 'DEPLOYED_SHA\t%%s\n' "$(git -C /mnt/d/Coding/MOSS-Transcribe-Diarize rev-parse HEAD)"
printf 'DEPLOYED_DIRTY_COUNT\t%%s\n' "$(git -C /mnt/d/Coding/MOSS-Transcribe-Diarize status --porcelain | wc -l)"
''' % (contract["env_path"], contract["unit_path"], contract["control_path"], contract["retention_root"])
    after_raw = server_script(after_script)
    (output / "after-state.txt").write_text(after_raw, encoding="utf-8")
    after = parse_tab(after_raw)
    if after.get("ENV_HASH") != contract["before_env_sha256"] or after.get("UNIT_HASH") != contract["before_unit_sha256"]:
        raise HarnessRefusal("deprovision_restore_hash_mismatch")
    if after.get("INVOCATION_HASH") != before.get("SNAPSHOT_INVOCATION_HASH"):
        raise HarnessRefusal("deprovision_invocation_not_exact_snapshot")
    if any(after.get(key) != expected for key, expected in (("ROOT_EXISTS", "no"), ("CONTROL_EXISTS", "no"), ("RETENTION_ENV_LINES", "0"), ("RETENTION_ARG_LINES", "0"))):
        raise HarnessRefusal("deprovision_retention_state_remains")
    after_descriptor = json.loads(after["DESCRIPTOR"])
    if after_descriptor.get("source_revision") != DEPLOYED_SHA or after.get("DEPLOYED_SHA") != DEPLOYED_SHA or after.get("DEPLOYED_DIRTY_COUNT") != "0":
        raise HarnessRefusal("deprovision_after_descriptor_or_deployment_mismatch")
    services = ("moss-live-web.service", "moss-web.service", "moss-vllm.service")
    for unit in services:
        if not after.get("SERVICE:" + unit, "").startswith("active/enabled/"):
            raise HarnessRefusal("deprovision_service_unhealthy:" + unit)
    before_pids = {unit: int(before["SERVICE:" + unit].split("/")[-1]) for unit in services}
    after_pids = {unit: int(after["SERVICE:" + unit].split("/")[-1]) for unit in services}
    if after_pids["moss-vllm.service"] != before_pids["moss-vllm.service"] or after_pids["moss-web.service"] != before_pids["moss-web.service"]:
        raise HarnessRefusal("deprovision_non_live_service_restarted")
    if after_pids["moss-live-web.service"] == before_pids["moss-live-web.service"]:
        raise HarnessRefusal("deprovision_live_service_not_restarted")
    capture_after = capture_state()
    assert_capture_idle(capture_after)
    verdict = {
        "schema": "moss-dl2-deprovision-verdict.v1",
        "completed_at_utc": utc_now(),
        "verdict": "PASS_EXACT_PRE_SPRINT_PROFILE_RESTORED",
        "contract_path": str(CONTRACT_PATH),
        "contract_sha256": contract_hash,
        "contract_seal_sha256": sha256(PROVISION_SEAL),
        "raw_cleanup_evidence_sha256": sha256(RAW_CLEANUP_SEAL),
        "before_env_sha256": contract["before_env_sha256"],
        "restored_env_sha256": after["ENV_HASH"],
        "before_unit_sha256": contract["before_unit_sha256"],
        "restored_unit_sha256": after["UNIT_HASH"],
        "before_invocation_sha256": before["SNAPSHOT_INVOCATION_HASH"],
        "restored_invocation_sha256": after["INVOCATION_HASH"],
        "source_revision": after_descriptor["source_revision"],
        "services": {unit: after["SERVICE:" + unit] for unit in services},
        "moss_live_web_restarted": True,
        "moss_web_restarted": False,
        "moss_vllm_restarted": False,
        "retention_root_removed": True,
        "control_snapshot_consumed_by_contract": True,
        "retention_flags_remaining": 0,
        "capture_idle_before": capture_before["status"],
        "capture_idle_after": capture_after["status"],
        "deployed_tree_clean": True,
    }
    atomic_json(output / "DEPROVISION_VERDICT.json", verdict)
    seal_tree(output, output / "DEPROVISION_EVIDENCE.sha256")
    print(json.dumps({"ok": True, **verdict, "evidence_sha256": sha256(output / "DEPROVISION_EVIDENCE.sha256")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
