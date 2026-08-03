#!/usr/bin/env python3
"""Freeze an operator-audited speaker reference without mutating its candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from moss_transcribe_diarize.speaker_reference import normalize_reference_text


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-provenance", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--acoustic-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    args = parser.parse_args()

    audit = json.loads(args.audit.read_text())
    candidate_provenance = json.loads(args.candidate_provenance.read_text())
    candidate_sha = _sha256(args.candidate)
    if audit.get("status") != "accepted":
        raise ValueError("audit must be accepted")
    if audit.get("candidate_reference_sha256") != candidate_sha:
        raise ValueError("audit is not bound to the candidate")
    if candidate_provenance.get("v2_reference_sha256") != candidate_sha:
        raise ValueError("candidate provenance hash mismatch")
    if audit.get("v1_reference_sha256") != _sha256(args.v1):
        raise ValueError("audit v1 hash mismatch")
    if audit.get("acoustic_evidence_sha256") != _sha256(args.acoustic_evidence):
        raise ValueError("audit acoustic-evidence hash mismatch")

    rows = _load_jsonl(args.candidate)
    by_line = {row["transcript"]["line_index"]: row for row in rows}
    removed_lines: list[int] = []
    edited_lines: list[int] = []
    for decision in audit["decisions"]:
        disposition = decision["disposition"]
        line_indices = decision["line_indices"]
        if disposition == "PRESENT":
            continue
        if disposition == "ABSENT":
            removed_lines.extend(line_indices)
            continue
        if disposition != "EDIT" or len(line_indices) != 1:
            raise ValueError(f"unsupported audit decision: {decision}")
        line_index = line_indices[0]
        row = by_line[line_index]
        if row["transcript"]["text"] != decision["candidate_text"]:
            raise ValueError(f"candidate text mismatch at line {line_index}")
        text = decision["post_audit_text"]
        normalized = normalize_reference_text(text)
        row["speaker_activity"] = {
            "start": decision["speaker_activity"]["start"],
            "end": decision["speaker_activity"]["end"],
            "speaker": decision["speaker"],
        }
        row["transcript"] = {
            "start": decision["transcript_activity"]["start"],
            "end": decision["transcript_activity"]["end"],
            "line_index": line_index,
            "text": text,
        }
        row["nonlexical_activity"] = decision["nonlexical_activity"]
        row["alignment"] = {
            "method": "operator-audited transcript-independent acoustic existence",
            "normalized_text": normalized,
            "normalized_text_sha256": hashlib.sha256(normalized.encode()).hexdigest(),
            "word_count": len(normalized.split()),
        }
        edited_lines.append(line_index)

    rows = [
        row for row in rows if row["transcript"]["line_index"] not in set(removed_lines)
    ]
    _write_jsonl(args.output, rows)
    output_sha = _sha256(args.output)
    provenance = {
        "schema": "moss-speaker-reference-provenance.v2",
        "status": "post-audit-frozen",
        "freeze_date": audit["audit_date"],
        "reference_version": 2,
        "segment_count": len(rows),
        "audio_sha256": audit["audio_sha256"],
        "v1_reference_sha256": _sha256(args.v1),
        "rejected_candidate_reference_sha256": candidate_sha,
        "rejected_candidate_provenance_sha256": _sha256(args.candidate_provenance),
        "human_audit_sha256": _sha256(args.audit),
        "human_audit_primary_basis": audit.get("primary_basis"),
        "acoustic_evidence_sha256": _sha256(args.acoustic_evidence),
        "post_audit_reference_sha256": output_sha,
        "provenance_chain": "v1 -> rejected-candidate -> operator-audited-v2",
        "edited_line_indices": edited_lines,
        "removed_line_indices": sorted(removed_lines),
        "edit_policy": "proven-absent lexical text is removed, never retimed; speaker activity remains separate",
        "blind_to_live_output": True,
    }
    args.provenance.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    print(json.dumps(provenance, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
