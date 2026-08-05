#!/usr/bin/env python3
"""Verify and optionally seal the D8-safe dev/validation ASR collection."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PROVENANCE = HERE / "runtime-inputs" / "asr-provenance.json"
SPLITS = HERE / "split-manifest.json"
EVIDENCE = HERE / "evidence" / "runtime-inputs"
MANIFEST = EVIDENCE / "RUNTIME_ASR_EVIDENCE.sha256"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_cases() -> dict[str, dict[str, object]]:
    payload = json.loads(SPLITS.read_text(encoding="utf-8"))
    return {
        item["case_id"]: item
        for split in ("development", "validation")
        for item in payload["groups"][split]
    }


def verify() -> list[Path]:
    payload = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    expected = expected_cases()
    records = {item["case_id"]: item for item in payload["cases"]}
    if payload["overall"] != "PASS" or payload["case_count"] != 16 or records.keys() != expected.keys():
        raise RuntimeError("runtime_asr_case_set_mismatch")
    if payload["constraints"] != {
        "golden_reference_opened": False,
        "holdout_case_opened": False,
        "batch_jobs_only": True,
        "service_restart": False,
        "deployed_tree_modified": False,
        "normal_runs_dir_artifacts_only": True,
    }:
        raise RuntimeError("runtime_asr_constraints_mismatch")
    members = [
        HERE / "collect_runtime_asr.py",
        HERE / "verify_runtime_asr.py",
        PROVENANCE,
        EVIDENCE / "preflight.json",
        EVIDENCE / "collection-transcript.txt",
    ]
    for case_id, record in sorted(records.items()):
        frozen = expected[case_id]
        if record["split"] != frozen["split"] or record["audio_sha256"] != frozen["audio_sha256"]:
            raise RuntimeError(f"runtime_asr_split_or_audio_mismatch:{case_id}")
        for path_key, hash_key in (
            ("segments_path", "segments_sha256"),
            ("job_terminal_path", "job_terminal_sha256"),
        ):
            path = REPO / record[path_key]
            if sha256(path) != record[hash_key]:
                raise RuntimeError(f"runtime_asr_hash_mismatch:{case_id}:{path_key}")
            members.append(path)
        provenance = HERE / "runtime-inputs" / "asr" / case_id / "provenance.json"
        if json.loads(provenance.read_text(encoding="utf-8")) != record:
            raise RuntimeError(f"runtime_asr_case_provenance_mismatch:{case_id}")
        members.append(provenance)
        segments = json.loads((REPO / record["segments_path"]).read_text(encoding="utf-8"))["segments"]
        if len(segments) != record["segment_count"] or any(
            not {"start", "end", "speaker", "text"}.issubset(segment) for segment in segments
        ):
            raise RuntimeError(f"runtime_asr_segment_schema:{case_id}")
    return sorted(set(members), key=lambda path: path.relative_to(REPO).as_posix())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seal", action="store_true")
    args = parser.parse_args()
    members = verify()
    if args.seal:
        MANIFEST.write_text(
            "".join(
                f"{sha256(path)}  {Path(os.path.relpath(path, EVIDENCE)).as_posix()}\n"
                for path in members
            ),
            encoding="utf-8",
        )
    if not MANIFEST.is_file():
        raise RuntimeError("runtime_asr_evidence_manifest_absent")
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        expected_hash, relative = line.split("  ", 1)
        path = EVIDENCE / relative
        if sha256(path) != expected_hash:
            raise RuntimeError(f"runtime_asr_evidence_hash_mismatch:{relative}")
    print(f"PASS runtime_asr cases=16 evidence_members={len(members)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
