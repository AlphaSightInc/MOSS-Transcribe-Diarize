#!/usr/bin/env python3
"""Validate an already-successful deprovision after bounded HTTP readiness."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from capture_harness import DEPLOYED_SHA, HarnessRefusal, assert_capture_idle, atomic_json, capture_state, read_json, server_script, sha256, utc_now
from post_session import seal_tree


HERE = Path(__file__).resolve().parent
ATTEMPT = HERE / "evidence/block-close-deprovision-attempt-1-http-readiness-race"
CONTRACT_PATH = HERE / "evidence/provisioning-20260805T2305/deprovision-contract.json"
RAW_CLEANUP_SEAL = HERE / "evidence/block-close-raw-cleanup-20260809/RAW_CLEANUP_EVIDENCE.sha256"


def parse_tab(raw: str) -> dict[str, str]:
    result = {}
    for line in raw.splitlines():
        if "\t" in line:
            key, value = line.split("\t", 1)
            result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    contract = read_json(CONTRACT_PATH)
    attempt_seal = ATTEMPT / "ATTEMPT1_EVIDENCE.sha256"
    for line in attempt_seal.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        if sha256(ATTEMPT / relative) != expected:
            raise HarnessRefusal("deprovision_attempt_evidence_drift:" + relative)
    command_text = (ATTEMPT / "deprovision-command.txt").read_text(encoding="utf-8")
    if "EXIT: 0" not in command_text or "PASS restored_env_sha256\t" + contract["before_env_sha256"] not in command_text:
        raise HarnessRefusal("deprovision_command_not_successful")
    shutil.copyfile(ATTEMPT / "before-state.txt", output / "before-state.txt")
    shutil.copyfile(ATTEMPT / "deprovision-command.txt", output / "deprovision-command.txt")
    before = parse_tab((output / "before-state.txt").read_text(encoding="utf-8"))

    after_script = r'''set -euo pipefail
env_file="%s"
unit_file="%s"
control="%s"
root="%s"
descriptor=''
for attempt in $(seq 1 30); do
  if descriptor="$(curl -ksS --max-time 2 https://127.0.0.1:7861/api/live/descriptor 2>/dev/null)"; then
    printf 'DESCRIPTOR_READY_ATTEMPT\t%%s\n' "$attempt"
    break
  fi
  sleep 1
done
test -n "$descriptor"
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
printf 'DESCRIPTOR\t'; printf '%%s' "$descriptor" | jq -c .descriptor
printf 'DEPLOYED_SHA\t%%s\n' "$(git -C /mnt/d/Coding/MOSS-Transcribe-Diarize rev-parse HEAD)"
printf 'DEPLOYED_DIRTY_COUNT\t%%s\n' "$(git -C /mnt/d/Coding/MOSS-Transcribe-Diarize status --porcelain | wc -l)"
''' % (contract["env_path"], contract["unit_path"], contract["control_path"], contract["retention_root"])
    after_raw = server_script(after_script)
    (output / "after-state.txt").write_text(after_raw, encoding="utf-8")
    after = parse_tab(after_raw)
    if after.get("ENV_HASH") != contract["before_env_sha256"] or after.get("UNIT_HASH") != contract["before_unit_sha256"]:
        raise HarnessRefusal("deprovision_restored_hash_mismatch")
    if after.get("INVOCATION_HASH") != before.get("SNAPSHOT_INVOCATION_HASH"):
        raise HarnessRefusal("deprovision_restored_invocation_mismatch")
    if any(after.get(key) != value for key, value in (("ROOT_EXISTS", "no"), ("CONTROL_EXISTS", "no"), ("RETENTION_ENV_LINES", "0"), ("RETENTION_ARG_LINES", "0"))):
        raise HarnessRefusal("deprovision_retention_state_remains")
    descriptor = json.loads(after["DESCRIPTOR"])
    if descriptor.get("source_revision") != DEPLOYED_SHA or after.get("DEPLOYED_SHA") != DEPLOYED_SHA or after.get("DEPLOYED_DIRTY_COUNT") != "0":
        raise HarnessRefusal("deprovision_descriptor_or_deployment_mismatch")
    units = ("moss-live-web.service", "moss-web.service", "moss-vllm.service")
    before_pids, after_pids = {}, {}
    for unit in units:
        if not after.get("SERVICE:" + unit, "").startswith("active/enabled/"):
            raise HarnessRefusal("deprovision_service_unhealthy:" + unit)
        before_pids[unit] = int(before["SERVICE:" + unit].split("/")[-1])
        after_pids[unit] = int(after["SERVICE:" + unit].split("/")[-1])
    if after_pids["moss-web.service"] != before_pids["moss-web.service"] or after_pids["moss-vllm.service"] != before_pids["moss-vllm.service"]:
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
        "contract_sha256": sha256(CONTRACT_PATH),
        "raw_cleanup_evidence_sha256": sha256(RAW_CLEANUP_SEAL),
        "attempt1_readiness_race_seal_sha256": sha256(attempt_seal),
        "deprovision_command_rerun": False,
        "before_env_sha256": contract["before_env_sha256"],
        "restored_env_sha256": after["ENV_HASH"],
        "before_unit_sha256": contract["before_unit_sha256"],
        "restored_unit_sha256": after["UNIT_HASH"],
        "before_invocation_sha256": before["SNAPSHOT_INVOCATION_HASH"],
        "restored_invocation_sha256": after["INVOCATION_HASH"],
        "descriptor_ready_poll_attempt": int(after["DESCRIPTOR_READY_ATTEMPT"]),
        "source_revision": descriptor["source_revision"],
        "services": {unit: after["SERVICE:" + unit] for unit in units},
        "moss_live_web_restarted": True,
        "moss_web_restarted": False,
        "moss_vllm_restarted": False,
        "retention_root_removed": True,
        "retention_flags_remaining": 0,
        "control_snapshot_consumed_by_contract": True,
        "capture_idle_after": capture_after["status"],
        "deployed_tree_clean": True,
    }
    atomic_json(output / "DEPROVISION_VERDICT.json", verdict)
    seal_tree(output, output / "DEPROVISION_EVIDENCE.sha256")
    print(json.dumps({"ok": True, **verdict, "evidence_sha256": sha256(output / "DEPROVISION_EVIDENCE.sha256")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
