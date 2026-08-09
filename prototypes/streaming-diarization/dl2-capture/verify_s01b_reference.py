#!/usr/bin/env python3
"""Verify the operator-audited S01b TRUE/BLEED reference package."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from capture_harness import read_json, sha256
from post_session import bleed_rate_for_packet


ROOT = Path(__file__).resolve().parent
SESSION = ROOT / "program" / "sessions" / "S01b-b3ddcda9517947ba89a2fc5f9e8cacdb"


def jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def check_pin(session: Path, pin: Dict[str, Any]) -> bool:
    return sha256(session / pin["path"]) == pin["sha256"]


def main() -> int:
    session = SESSION
    manifest = read_json(session / "session-manifest.json")
    audit = manifest["human_audit"]
    layers = read_json(session / audit["reference_layers"]["path"])
    microphone = read_json(session / layers["source_asr"]["microphone_path"])["segments"]
    system = read_json(session / layers["source_asr"]["system_path"])["segments"]
    true_rows = jsonl(session / audit["true_reference"]["path"])
    bleed_rows = jsonl(session / audit["bleed_reference"]["path"])

    checks: Dict[str, bool] = {
        "attestation_pin": check_pin(session, audit["attestation"]),
        "true_split_pin": check_pin(session, audit["true_split"]),
        "bleed_split_pin": check_pin(session, audit["bleed_split"]),
        "true_reference_pin": check_pin(session, audit["true_reference"]),
        "bleed_reference_pin": check_pin(session, audit["bleed_reference"]),
        "reference_layers_pin": check_pin(session, audit["reference_layers"]),
        "microphone_asr_pin": sha256(session / layers["source_asr"]["microphone_path"])
        == layers["source_asr"]["microphone_sha256"],
        "system_asr_pin": sha256(session / layers["source_asr"]["system_path"])
        == layers["source_asr"]["system_sha256"],
        "partition_27_of_27": sorted(row["row"] for row in true_rows + bleed_rows)
        == list(range(len(microphone))),
        "partition_zero_overlap": not ({row["row"] for row in true_rows} & {row["row"] for row in bleed_rows}),
        "true_identity_collapsed": {row["reference_speaker"] for row in true_rows} == {"Operator"}
        and {row["source_asr_speaker"] for row in true_rows} == {"S02", "S03"},
    }

    for row in true_rows + bleed_rows:
        source = microphone[row["row"]]
        checks["row_%02d_matches_mic_asr" % row["row"]] = (
            row["segment_id"],
            row["start"],
            row["end"],
            row["source_asr_speaker"],
            row["text"],
        ) == (source["id"], source["start"], source["end"], source["speaker"], source["text"])

    for row in bleed_rows:
        overlap: Dict[str, float] = {}
        for segment in system:
            seconds = max(0.0, min(row["end"], segment["end"]) - max(row["start"], segment["start"]))
            overlap[segment["speaker"]] = overlap.get(segment["speaker"], 0.0) + seconds
        checks["bleed_row_%02d_system_mapping" % row["row"]] = row["system_asr_speaker"] == max(
            overlap, key=overlap.get
        )

    true_seconds = round(sum(float(row["duration"]) for row in true_rows), 2)
    bleed_seconds = round(sum(float(row["duration"]) for row in bleed_rows), 2)
    mic_seconds = round(true_seconds + bleed_seconds, 2)
    value = bleed_seconds / mic_seconds
    metric = manifest["bleed_rate"]
    checks.update(
        {
            "true_seconds": true_seconds == 75.27,
            "bleed_seconds": bleed_seconds == 66.79,
            "mic_seconds": mic_seconds == 142.06,
            "bleed_rate_value": abs(metric["value"] - value) <= 1e-12,
            "bleed_rate_rounded": metric["percent_rounded_1dp"] == round(100.0 * value, 1) == 47.0,
            "packet_emitter_accepts_manifest_metric": bleed_rate_for_packet(manifest) == metric,
        }
    )

    skeleton = read_json(ROOT / "f2a-preregistration-skeleton.json")
    mechanism = skeleton["bleed_aware_mechanism"]
    checks.update(
        {
            "f2a_still_unfrozen": skeleton["status"] == "UNFROZEN_SKELETON_DO_NOT_RUN",
            "f2a_bleed_aware": skeleton["family"].startswith("bleed-aware-")
            and "voiceprint" in mechanism["rule"],
            "f2a_attestation_pin": mechanism["specimen"]["attestation_sha256"]
            == audit["attestation"]["sha256"],
        }
    )

    output = {
        "schema": "moss-dl2-s01b-reference-verification.v1",
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "counts": {"passed": sum(checks.values()), "total": len(checks)},
        "measurements": {
            "true_rows": len(true_rows),
            "bleed_rows": len(bleed_rows),
            "true_seconds": true_seconds,
            "bleed_seconds": bleed_seconds,
            "mic_speech_seconds": mic_seconds,
            "bleed_rate": value,
            "bleed_percent_rounded_1dp": round(100.0 * value, 1),
        },
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
