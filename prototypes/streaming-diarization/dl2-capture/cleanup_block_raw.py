#!/usr/bin/env python3
"""Verify retained DL2 evidence, then delete all block raw locally and remotely."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from capture_harness import (
    HarnessRefusal,
    assert_capture_idle,
    atomic_json,
    capture_state,
    cleanup_raw,
    read_json,
    server_preflight,
    server_script,
    sha256,
    utc_now,
)
from post_session import seal_tree


SESSIONS = {
    "79a72cdb46df4c3e8a1fe1857b9836e8": {
        "directory": "CAL-HP-BLOCK-20260808-79a72cdb46df4c3e8a1fe1857b9836e8",
        "artifact_class": "calibration_gate_no_three_lane_audit_packet",
        "seals": ["derived/CAL_HP_DERIVED_EVIDENCE.sha256"],
        "required": ["derived/cal-hp-gate/CAL_HP_GATE.json"],
    },
    "52f4856ab04a469b92f72fc5ea199d44": {
        "directory": "S06-BLOCK-20260808-52f4856ab04a469b92f72fc5ea199d44",
        "artifact_class": "solo_enrollment_no_system_speech_no_three_lane_audit_packet",
        "seals": ["derived/S06_DERIVED_EVIDENCE.sha256"],
        "required": ["derived/s06-verdict/S06_SOLO_D2_ADDENDUM.json"],
    },
    "7515d518db0a4488a8e6b26eae04fe66": {
        "directory": "S06R-BLOCK-20260808-7515d518db0a4488a8e6b26eae04fe66",
        "artifact_class": "three_lane_audit_packet_and_timeline_verdict",
        "seals": ["derived/DERIVED_EVIDENCE.sha256", "derived/s06r-verdict/S06R_VERDICT_EVIDENCE.sha256"],
        "required": ["derived/audit-packet/audit-rows.html", "derived/audit-packet/audit-rows.json"],
    },
    "40422fb135a146579d013d663652bd56": {
        "directory": "S05-BLOCK-20260808-40422fb135a146579d013d663652bd56",
        "artifact_class": "externally_stopped_recovered_three_lane_audit_packet_and_timeline_verdict",
        "seals": ["derived/DERIVED_EVIDENCE_V2.sha256", "derived/s05-verdict/S05_VERDICT_EVIDENCE.sha256"],
        "required": ["derived/audit-packet/audit-rows.html", "derived/audit-packet/audit-rows.json"],
    },
}


def verify_seal(path: Path) -> dict:
    rows, failures = 0, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        target = path.parent / relative
        rows += 1
        if not target.is_file() or sha256(target) != expected:
            failures.append(relative)
    if failures:
        raise HarnessRefusal("block_cleanup_evidence_non_ok:" + str(path) + ":" + ",".join(failures))
    return {"path": str(path), "sha256": sha256(path), "rows": rows, "non_ok": 0}


def remote_inventory(root: str) -> tuple[str, dict[tuple[str, str], dict]]:
    raw = server_script(
        r'''set -euo pipefail
root="%s"
find "$root" -mindepth 1 -maxdepth 2 -type f -print0 | sort -z | while IFS= read -r -d '' file; do
  sid="$(basename "$(dirname "$file")")"
  name="$(basename "$file")"
  printf 'FILE\t%%s\t%%s\t%%s\t%%s\n' "$sid" "$name" "$(stat -c %%s "$file")" "$(sha256sum "$file" | cut -d' ' -f1)"
done
''' % root
    )
    records = {}
    for line in raw.splitlines():
        if not line.startswith("FILE\t"):
            continue
        _, sid, name, size, digest = line.split("\t")
        records[(sid, name)] = {"bytes": int(size), "sha256": digest}
    return raw, records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--program-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    program = args.program_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    grant = read_json(program / "grant.json")
    ledger_before = read_json(program / "program-ledger.json")
    server_before = server_preflight(grant)
    capture_before = capture_state()
    assert_capture_idle(capture_before)

    inventory = []
    seal_results = []
    for session_id, spec in SESSIONS.items():
        session = program / "sessions" / spec["directory"]
        manifest = read_json(session / "session-manifest.json")
        if manifest.get("session_id") != session_id or manifest.get("state") != "audit_ready_raw_retained":
            raise HarnessRefusal("block_cleanup_session_state_refused:" + session_id)
        if manifest.get("derived", {}).get("artifact_class", spec["artifact_class"]) != spec["artifact_class"]:
            raise HarnessRefusal("block_cleanup_artifact_class_mismatch:" + session_id)
        for required in spec["required"]:
            if not (session / required).is_file():
                raise HarnessRefusal("block_cleanup_required_artifact_missing:" + session_id + ":" + required)
        session_seals = [verify_seal(session / relative) for relative in spec["seals"]]
        seal_results.append({"session_id": session_id, "artifact_class": spec["artifact_class"], "seals": session_seals})
        files = []
        for directory in (session / "raw", session / "audio"):
            if not directory.is_dir():
                raise HarnessRefusal("block_cleanup_local_raw_missing:" + session_id + ":" + directory.name)
            for path in sorted(directory.iterdir()):
                if path.is_file():
                    files.append({"scope": "local", "path": str(path), "relative_path": str(path.relative_to(session)), "bytes": path.stat().st_size, "sha256": sha256(path)})
        inventory.append({"session_id": session_id, "shape_id": manifest["shape"]["shape_id"], "artifact_class": spec["artifact_class"], "files": files})

    remote_raw, remote_records = remote_inventory(grant["retention_root"])
    (output / "remote-inventory-before.txt").write_text(remote_raw, encoding="utf-8")
    expected_remote = set()
    for item in inventory:
        sid = item["session_id"]
        local_raw = {Path(file["relative_path"]).name: file for file in item["files"] if file["relative_path"].startswith("raw/")}
        for name, record in local_raw.items():
            expected_remote.add((sid, name))
            remote = remote_records.get((sid, name))
            if remote is None or remote["sha256"] != record["sha256"] or remote["bytes"] != record["bytes"]:
                raise HarnessRefusal("block_cleanup_remote_hash_mismatch:" + sid + ":" + name)
            item["files"].append({"scope": "remote", "path": grant["retention_root"] + "/" + sid + "/" + name, "relative_path": name, **remote})
    if set(remote_records) != expected_remote:
        raise HarnessRefusal("block_cleanup_remote_inventory_unexpected")

    predelete = {
        "schema": "moss-dl2-block-raw-deletion-inventory.v1",
        "grant_id": grant["grant_id"],
        "captured_bytes_total": ledger_before["captured_bytes_total"],
        "created_at_utc": utc_now(),
        "server_before": server_before,
        "capture_before": capture_before,
        "derived_verification": seal_results,
        "deletion_targets": inventory,
    }
    atomic_json(output / "RAW_DELETION_INVENTORY.json", predelete)

    cleanup_results = []
    for session_id, spec in SESSIONS.items():
        session = program / "sessions" / spec["directory"]
        cleanup_results.append({"session_id": session_id, "result": cleanup_raw(session)})

    remote_after_raw, remote_after = remote_inventory(grant["retention_root"])
    (output / "remote-inventory-after.txt").write_text(remote_after_raw, encoding="utf-8")
    if remote_after:
        raise HarnessRefusal("block_cleanup_remote_root_not_empty")
    for spec in SESSIONS.values():
        session = program / "sessions" / spec["directory"]
        if (session / "raw").exists() or (session / "audio").exists():
            raise HarnessRefusal("block_cleanup_local_raw_remains:" + spec["directory"])
    ledger_after = read_json(program / "program-ledger.json")
    if ledger_after["captured_bytes_total"] != ledger_before["captured_bytes_total"]:
        raise HarnessRefusal("block_cleanup_cap_ledger_total_changed")
    target_rows = [item for item in ledger_after["sessions"] if item.get("session_id") in SESSIONS]
    if len(target_rows) != len(SESSIONS) or any(item.get("raw_deleted") is not True for item in target_rows):
        raise HarnessRefusal("block_cleanup_ledger_not_closed")
    retained = [item for item in ledger_after["sessions"] if item.get("raw_deleted") is False]
    if retained:
        raise HarnessRefusal("block_cleanup_retained_rows_remain")
    verdict = {
        "schema": "moss-dl2-block-raw-cleanup-verdict.v1",
        "grant_id": grant["grant_id"],
        "completed_at_utc": utc_now(),
        "verdict": "PASS_ALL_RETAINED_RAW_DELETED",
        "session_count": len(SESSIONS),
        "derived_seals_verified": sum(len(item["seals"]) for item in seal_results),
        "derived_non_ok": 0,
        "cleanup_results": cleanup_results,
        "remote_root_empty": True,
        "local_raw_directories_remaining": 0,
        "captured_bytes_total_final": ledger_after["captured_bytes_total"],
        "retained_session_count_final": 0,
        "program_ledger_sha256": sha256(program / "program-ledger.json"),
        "deletion_inventory_path": "RAW_DELETION_INVENTORY.json",
        "deletion_inventory_sha256": sha256(output / "RAW_DELETION_INVENTORY.json"),
    }
    atomic_json(output / "RAW_CLEANUP_VERDICT.json", verdict)
    seal_tree(output, output / "RAW_CLEANUP_EVIDENCE.sha256")
    print(json.dumps({"ok": True, **verdict, "evidence_sha256": sha256(output / "RAW_CLEANUP_EVIDENCE.sha256")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
