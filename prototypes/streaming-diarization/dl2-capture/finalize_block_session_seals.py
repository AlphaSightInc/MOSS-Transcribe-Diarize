#!/usr/bin/env python3
"""Add complete derived-tree seals for retained nonstandard DL2 specimens."""

from __future__ import annotations

import json
from pathlib import Path

from capture_harness import HarnessRefusal, atomic_json, read_json, sha256, utc_now
from post_session import seal_tree


ROOT = Path(__file__).resolve().parent / "program" / "sessions"
SPECS = {
    "CAL-HP-BLOCK-20260808-79a72cdb46df4c3e8a1fe1857b9836e8": {
        "seal": "CAL_HP_DERIVED_EVIDENCE.sha256",
        "artifact_class": "calibration_gate_no_three_lane_audit_packet",
        "reason": "silent microphone was a required PASS condition; gate evidence replaces a standard three-lane audit packet",
        "required": [
            "derived/asr/system/asr-transcript.json",
            "derived/asr/mixed/asr-transcript.json",
            "derived/cal-hp-gate/CAL_HP_GATE.json",
            "derived/cal-hp-gate/CAL_HP_GATE_EVIDENCE.sha256",
        ],
    },
    "S06-BLOCK-20260808-52f4856ab04a469b92f72fc5ea199d44": {
        "seal": "S06_DERIVED_EVIDENCE.sha256",
        "artifact_class": "solo_enrollment_no_system_speech_no_three_lane_audit_packet",
        "reason": "system lane was exact-zero; mic/mixed ASR plus timeline and D2 addendum are the complete diagnostic specimen",
        "required": [
            "derived/asr/microphone/asr-transcript.json",
            "derived/asr/mixed/asr-transcript.json",
            "derived/s06-verdict/S06_TIMELINE_VERDICT.json",
            "derived/s06-verdict/S06_VERDICT_EVIDENCE.sha256",
            "derived/s06-verdict/S06_SOLO_D2_ADDENDUM.json",
            "derived/s06-verdict/S06_SOLO_EVIDENCE.sha256",
        ],
    },
}


def main() -> int:
    result = []
    for name, spec in SPECS.items():
        session = ROOT / name
        manifest_path = session / "session-manifest.json"
        manifest = read_json(manifest_path)
        if manifest.get("state") != "audit_ready_raw_retained":
            raise HarnessRefusal("block_seal_state_refused:" + name)
        for relative in spec["required"]:
            if not (session / relative).is_file():
                raise HarnessRefusal("block_seal_required_artifact_missing:" + name + ":" + relative)
        seal_path = session / "derived" / spec["seal"]
        if seal_path.exists():
            raise HarnessRefusal("block_seal_already_exists:" + name)
        seal_tree(session / "derived", seal_path)
        manifest["derived"] = {
            "artifact_class": spec["artifact_class"],
            "audit_packet_present": False,
            "audit_packet_absence_reason": spec["reason"],
            "seal_path": "derived/" + spec["seal"],
            "seal_sha256": sha256(seal_path),
            "sealed_at_utc": utc_now(),
        }
        atomic_json(manifest_path, manifest)
        result.append({
            "session_id": manifest["session_id"],
            "shape_id": manifest["shape"]["shape_id"],
            "artifact_class": spec["artifact_class"],
            "seal_path": str(seal_path),
            "seal_sha256": sha256(seal_path),
            "row_count": sum(1 for line in seal_path.read_text(encoding="utf-8").splitlines() if line.strip()),
        })
    print(json.dumps({"ok": True, "sessions": result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
