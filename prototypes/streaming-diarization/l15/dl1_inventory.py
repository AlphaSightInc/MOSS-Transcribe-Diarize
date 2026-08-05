#!/usr/bin/env python3
"""Validate and record the read-only DL1 dual-lane corpus inventory."""

from __future__ import annotations

import hashlib
import json
import wave
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_ROOT = ROOT / "data" / "dual_lane_diarization"
EVIDENCE_ROOT = ROOT / "evidence" / "dl1-inventory"
OUTPUT = EVIDENCE_ROOT / "dl1-inventory.json"

SOURCE_HOST = "ga0@m4mbp"
SOURCE_ROOT = "/Users/ga0/Desktop/AI_Projects/LiveTranscribe/data/dual_lane_diarization"
SOURCE_CHECKOUT_HEAD = "c861a51303229fb88527395019d17aad377c360a"
SOURCE_CHECKOUT_BRANCH = "ralph/production"
REFERENCE_COMMIT = "dd9c7cb07f609763dea9993e9f2a2f0da2c5a8ae"
REFERENCE_BRANCH = "ralph/diarization-architecture-0428"

EXPECTED_HASHES = {
    "README.md": "4bba1f0a6799247dcb6f33413441998d55275c47ecc068a9db74bdb8d1456a32",
    "manifest.json": "bd910436aa5cf08e6f3e54fb3290e76085e7febf2e1a338a36c765df9e1db3b6",
    "cases/pending_source_separation_001/capture_notes.md": "c8a4201b768edb3017bfc3dc3bf4fc66a03048d525bdf83064b64a23278f702b",
    "cases/pending_source_separation_001/local.wav": "830a5558cf90fe7f5571dc2cfc6e0708d1e09194b5b716532d6d6902bf953251",
    "cases/pending_source_separation_001/reference_microphone.jsonl": "b3acd32f2f1023b328b0ba0634427e035ca8ce32edc0bb101cc9607a2947d880",
    "cases/pending_source_separation_001/reference_system_audio.jsonl": "fda7c141c7a5a9c7dc8d445a5fae83acf1e96cf25059c57912d4ce9a9a6c0abe",
    "cases/pending_source_separation_001/remote.wav": "5299e742325fa9d3c58946222262a8262bd7e47863c97d0f0a772956050c1c1d",
}

REPLICAS = [
    "/Users/ga0/Desktop/AI_Projects/LiveTranscribe/data/dual_lane_diarization",
    "/Users/ga0/Desktop/AI_Projects/LiveTranscribe--soniqo-vad-ane/data/dual_lane_diarization",
    "/Users/ga0/Desktop/AI_Projects/LiveTranscribe-ralph-outstanding-0727-v2/data/dual_lane_diarization",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, object]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"reference_jsonl_invalid:{path}:{line_number}") from exc
            if not isinstance(row, dict):
                raise RuntimeError(f"reference_row_not_object:{path}:{line_number}")
            rows.append(row)
    if not rows:
        raise RuntimeError(f"reference_empty:{path}")
    return rows


def inspect_reference(path: Path, expected_lane: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    rows = load_jsonl(path)
    required = {
        "speaker",
        "text",
        "start",
        "end",
        "source_lane",
        "reference_source",
        "capture_start_offset_sec",
    }
    previous_end = -1.0
    for index, row in enumerate(rows):
        missing = required - row.keys()
        if missing:
            raise RuntimeError(f"reference_schema_missing:{path}:{index}:{sorted(missing)}")
        start = float(row["start"])
        end = float(row["end"])
        if start < 0 or end <= start or start < previous_end:
            raise RuntimeError(f"reference_timing_invalid:{path}:{index}")
        if row["source_lane"] != expected_lane:
            raise RuntimeError(f"reference_lane_mismatch:{path}:{index}")
        previous_end = end
    summary = {
        "format": "JSONL",
        "row_count": len(rows),
        "schema_fields": sorted(required),
        "speakers": sorted({str(row["speaker"]) for row in rows}),
        "start_min_seconds": min(float(row["start"]) for row in rows),
        "end_max_seconds": max(float(row["end"]) for row in rows),
        "reference_sources": sorted({str(row["reference_source"]) for row in rows}),
        "human_audit_status": "NOT_AUDITED",
    }
    return summary, rows


def inspect_wav(path: Path) -> dict[str, object]:
    with wave.open(str(path), "rb") as audio:
        channels = audio.getnchannels()
        sample_width = audio.getsampwidth()
        sample_rate = audio.getframerate()
        frame_count = audio.getnframes()
        compression = audio.getcomptype()
    duration = frame_count / sample_rate
    if (channels, sample_width, sample_rate, frame_count, compression) != (
        1,
        2,
        16000,
        953344,
        "NONE",
    ):
        raise RuntimeError(f"audio_contract_mismatch:{path}")
    if abs(duration - 59.584) > 1e-9:
        raise RuntimeError(f"audio_duration_mismatch:{path}:{duration}")
    return {
        "container": "WAVE",
        "encoding": "PCM signed 16-bit little-endian",
        "channels": channels,
        "sample_width_bytes": sample_width,
        "sample_rate_hz": sample_rate,
        "frame_count": frame_count,
        "duration_seconds": duration,
        "file_bytes": path.stat().st_size,
    }


def main() -> int:
    files = []
    for relative, expected_hash in EXPECTED_HASHES.items():
        path = DATA_ROOT / relative
        if not path.is_file():
            raise RuntimeError(f"inventory_file_missing:{relative}")
        actual_hash = sha256(path)
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"inventory_hash_mismatch:{relative}:expected={expected_hash}:actual={actual_hash}"
            )
        files.append(
            {
                "path": f"prototypes/streaming-diarization/l15/data/dual_lane_diarization/{relative}",
                "sha256": actual_hash,
                "bytes": path.stat().st_size,
            }
        )

    source_manifest = json.loads((DATA_ROOT / "manifest.json").read_text(encoding="utf-8"))
    cases = source_manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != 1:
        raise RuntimeError("source_manifest_case_count_mismatch")
    source_case = cases[0]
    if source_case.get("case_id") != "pending_source_separation_001":
        raise RuntimeError("source_manifest_case_id_mismatch")

    case_root = DATA_ROOT / "cases" / "pending_source_separation_001"
    system_reference, system_rows = inspect_reference(
        case_root / "reference_system_audio.jsonl", "system_audio"
    )
    microphone_reference, microphone_rows = inspect_reference(
        case_root / "reference_microphone.jsonl", "microphone"
    )
    paired_fields = ("speaker", "text", "start", "end", "reference_source")
    if [tuple(row[field] for field in paired_fields) for row in system_rows] != [
        tuple(row[field] for field in paired_fields) for row in microphone_rows
    ]:
        raise RuntimeError("lane_references_not_same_content")

    local_audio = inspect_wav(case_root / "local.wav")
    remote_audio = inspect_wav(case_root / "remote.wav")
    if local_audio != remote_audio:
        raise RuntimeError("lane_audio_metadata_mismatch")

    inventory = {
        "schema": "moss-l15-dl1-inventory.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS",
        "disposition": "INVENTORY_COMPLETE_EXPLORATORY_NOT_ACCEPTANCE_GRADE",
        "read_only_source": True,
        "new_recording_created": False,
        "source": {
            "host": SOURCE_HOST,
            "canonical_working_tree_path": SOURCE_ROOT,
            "working_tree_head": SOURCE_CHECKOUT_HEAD,
            "working_tree_branch": SOURCE_CHECKOUT_BRANCH,
            "audio_source": "current ignored working-tree bytes",
            "reference_and_provenance_source": {
                "commit": REFERENCE_COMMIT,
                "branch": REFERENCE_BRANCH,
                "commit_timestamp": "2026-04-29T08:56:56-04:00",
                "commit_subject": "ralph: iteration 3 - DARCHDISC-055: Capture real aligned dual-lane Mic+Speaker recordings",
                "reason": "latest commit in all-branch history that changes data/dual_lane_diarization",
            },
            "physical_replicas": [
                {
                    "path": replica,
                    "local_wav_sha256": EXPECTED_HASHES[
                        "cases/pending_source_separation_001/local.wav"
                    ],
                    "remote_wav_sha256": EXPECTED_HASHES[
                        "cases/pending_source_separation_001/remote.wav"
                    ],
                }
                for replica in REPLICAS
            ],
            "copy_protocol": {
                "audio": "scp -p from canonical working tree",
                "references_and_notes": "git archive from reference commit over read-only ssh",
                "remote_writes": 0,
            },
        },
        "dataset": {
            "name": source_manifest["dataset_name"],
            "source_schema_version": source_manifest["schema_version"],
            "case_count": 1,
            "total_aligned_duration_seconds": 59.584,
            "case_ids": ["pending_source_separation_001"],
        },
        "cases": [
            {
                "case_id": "pending_source_separation_001",
                "duration_seconds": 59.584,
                "capture_mode": "mic_plus_speaker",
                "recording_status": "captured_real_recording",
                "alignment": source_case["alignment"],
                "lane_structure": "two synchronized per-lane mono tracks sharing host-time start",
                "lanes": [
                    {
                        "lane": "system_audio",
                        "capture_seam": "Core Audio Tap",
                        "audio_path": "cases/pending_source_separation_001/remote.wav",
                        "audio": remote_audio,
                        "reference_path": "cases/pending_source_separation_001/reference_system_audio.jsonl",
                        "reference": system_reference,
                        "expected_speakers": 2,
                    },
                    {
                        "lane": "microphone",
                        "capture_seam": "AVAudioEngine room capture",
                        "audio_path": "cases/pending_source_separation_001/local.wav",
                        "audio": local_audio,
                        "reference_path": "cases/pending_source_separation_001/reference_microphone.jsonl",
                        "reference": microphone_reference,
                        "expected_speakers": 2,
                    },
                ],
                "reference_relationship": "same three truth intervals and two speakers on both lanes; source_lane differs",
                "known_stressors": source_case["known_stressors"],
                "provenance_summary": source_case["notes"],
                "acceptance_truth_status": "NOT_HUMAN_AUDITED",
            }
        ],
        "copied_files": sorted(files, key=lambda row: row["path"]),
        "acceptance_grade_gap": {
            "current_corpus_is_sufficient": False,
            "reasons": [
                "only one short 59.584-second meeting",
                "both lanes carry the same playback-derived two-speaker content",
                "identity, activity, overlap, and crosstalk truth is not human-audited",
                "no varied speakers, acoustics, or same-speaker-cross-lane counterexamples",
                "no dev, validation, or single-open long/hard holdout split is possible",
            ],
            "required_program": [
                "multiple synchronized dual-lane meetings with varied speakers, acoustics, crosstalk, overlap, and same-speaker-cross-lane cases",
                "immutable lane metadata plus missing-lane and wrong-lane controls",
                "human-audited identity, activity, overlap, and crosstalk truth",
                "preregistered development, validation, and single-open long/hard holdout splits",
                "D8-safe same-frame L1/F2 measurement with full-chain label-perturbation audit",
                "accuracy, DER, false-positive, regression, mapping, determinism, and compute gates",
            ],
        },
    }
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": "PASS", "output": str(OUTPUT), "case_count": 1}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
