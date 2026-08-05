#!/usr/bin/env python3
"""Promote the ten 2026-08-04 human-audited cases into an unassigned acceptance pool."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STAGE0 = HERE.parent
REPO = STAGE0.parents[2]

import sys

sys.path.insert(0, str(STAGE0))

from validate_inputs import load_reference, reference_findings, sha256_file  # noqa: E402


AUDIT_DATE = "2026-08-04"
ATTESTATION_ROOT = "prototypes/streaming-diarization/l2-stage0/human-audit/attestations"
EXPECTED_SOURCE_SCHEMA = "moss-l2-stage0-corpus.v1"
OUTPUT_SCHEMA = "moss-l2-stage0-corpus.v2"


def _audit(filename: str, basis: str) -> dict[str, str]:
    return {
        "attestation_path": f"{ATTESTATION_ROOT}/{filename}",
        "basis": basis,
        "date": AUDIT_DATE,
    }


DIRECT_LISTENING = (
    "operator direct listening; blind fresh ASR cross-check at deployed 9089b332; "
    "blanket timing confirmation"
)
Q3_BASIS = (
    "three-source validation: golden reference, blind fresh ASR at deployed 9089b332, "
    "and official lexfridman.com transcript; operator signed off; blanket timing confirmation"
)
Q4_BASIS = (
    "operator targeted listening, official show transcript, and blind fresh ASR at deployed "
    "9089b332; blanket timing confirmation"
)
Q5_BASIS = (
    "operator targeted listening, official lexfridman.com transcript, and blind fresh ASR at "
    "deployed 9089b332; genuine-crosstalk overlaps and blanket timing confirmation"
)


PROMOTIONS: dict[str, dict[str, Any]] = {
    "1m-acquired-jamie-dimon": {
        "audit": _audit("q1-1m-acquired-jamie-dimon-20260804.md", DIRECT_LISTENING),
    },
    "5m-acquired-coca-cola": {
        "audit": _audit("q2-5m-acquired-coca-cola-20260804.md", DIRECT_LISTENING),
        "reference_path": (
            "prototypes/streaming-diarization/data/real/benchmark_5m/"
            "acquired_coca_cola/reference-v2-human-20260804.jsonl"
        ),
        "reference_sha256": "d2b92f1aff1df0a15b183205cc04246bc09097270a3445b3203d96d9fbb738fa",
        "superseded_sha256": "41146f40c372a928607219df34b78b4cb68c10ca5cf1cbcb4bba1c33b8135809",
    },
    "5m-acquired-jamie-dimon": {
        "audit": _audit("q2-5m-acquired-jamie-dimon-20260804.md", DIRECT_LISTENING),
    },
    "5m-acquired-nfl": {
        "audit": _audit("q2-5m-acquired-nfl-20260804.md", DIRECT_LISTENING),
    },
    "5m-acquired-rolex": {
        "audit": _audit("q2-5m-acquired-rolex-20260804.md", DIRECT_LISTENING),
        "reference_path": (
            "prototypes/streaming-diarization/data/real/benchmark_5m/"
            "acquired_rolex/reference-v2-human-20260804.jsonl"
        ),
        "reference_sha256": "177caa44c892dc804d5efba661749c2e72ecf734d1457f3cc0ab079d4e5401d2",
        "superseded_sha256": "88f84c94b0f184939906249747ae489c58563ac81483eb1447ef2d00e4f58b1c",
    },
    "5m-lex-bill-ackman": {
        "audit": _audit("q3-lex-5m-batch-20260804.md", Q3_BASIS),
    },
    "5m-lex-javier-milei": {
        "audit": _audit("q3-lex-5m-batch-20260804.md", Q3_BASIS),
    },
    "5m-lex-keyu-jin": {
        "audit": _audit("q3-lex-5m-batch-20260804.md", Q3_BASIS),
    },
    "30m-acquired-jamie-dimon": {
        "audit": _audit("q4-30m-acquired-jamie-dimon-20260804.md", Q4_BASIS),
    },
    "30m-lex-bill-ackman": {
        "audit": _audit("q5-30m-lex-bill-ackman-20260804.md", Q5_BASIS),
    },
}


def _audio_duration(case: dict[str, Any]) -> float:
    return float(case["duration_seconds"])


def promote(manifest_path: Path) -> dict[str, Any]:
    corpus = json.loads(manifest_path.read_text(encoding="utf-8"))
    if corpus.get("schema") != EXPECTED_SOURCE_SCHEMA:
        raise RuntimeError(f"promotion_source_schema_mismatch:{corpus.get('schema')}")
    by_id = {str(case["case_id"]): case for case in corpus["cases"]}
    if set(PROMOTIONS) - set(by_id):
        raise RuntimeError("promotion_case_missing")
    changed_references: list[str] = []
    finding_counts: dict[str, int] = {}
    for case_id, promotion in PROMOTIONS.items():
        case = by_id[case_id]
        if case.get("split") != "exploratory" or case.get("acceptance_eligible") is not False:
            raise RuntimeError(f"promotion_source_state_mismatch:{case_id}")
        attestation = REPO / promotion["audit"]["attestation_path"]
        if not attestation.is_file():
            raise RuntimeError(f"promotion_attestation_missing:{case_id}")
        if "reference_path" in promotion:
            if case["reference_sha256"] != promotion["superseded_sha256"]:
                raise RuntimeError(f"promotion_superseded_hash_mismatch:{case_id}")
            old_path = REPO / case["reference_path"]
            if sha256_file(old_path) != case["reference_sha256"]:
                raise RuntimeError(f"promotion_superseded_file_mismatch:{case_id}")
            case["superseded_reference"] = {
                "path": case["reference_path"],
                "sha256": case["reference_sha256"],
            }
            case["reference_path"] = promotion["reference_path"]
            case["reference_sha256"] = promotion["reference_sha256"]
            changed_references.append(case_id)
        reference = REPO / case["reference_path"]
        if sha256_file(reference) != case["reference_sha256"]:
            raise RuntimeError(f"promotion_reference_hash_mismatch:{case_id}")
        findings = reference_findings(load_reference(reference), _audio_duration(case))
        case["mechanical_findings"] = [
            {**finding, "adjudicated": True} for finding in findings
        ]
        case["human_audit"] = promotion["audit"]
        case["validation_state"] = "human_audited"
        case["reference_status"] = "human_audit_frozen"
        case["acceptance_eligible"] = True
        case["split"] = "acceptance_pool"
        finding_counts[case_id] = len(findings)
    attestation_manifest = REPO / ATTESTATION_ROOT / "ATTESTATIONS.sha256"
    corpus["human_audit_attestations_manifest_path"] = (
        f"{ATTESTATION_ROOT}/ATTESTATIONS.sha256"
    )
    corpus["human_audit_attestations_manifest_sha256"] = sha256_file(attestation_manifest)
    corpus["acceptance_pool_promoted_at"] = AUDIT_DATE
    corpus["acceptance_pool_split_policy"] = (
        "unassigned; L1.5 dev/validation/holdout freeze is a separate campaign action"
    )
    corpus["schema"] = OUTPUT_SCHEMA
    rendered = json.dumps(corpus, indent=2, sort_keys=True) + "\n"
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(manifest_path)
    return {
        "acceptance_pool_case_count": len(PROMOTIONS),
        "changed_reference_case_ids": changed_references,
        "finding_counts": finding_counts,
        "manifest_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
        "overall": "PASS",
        "schema": OUTPUT_SCHEMA,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=STAGE0 / "corpus-manifest.json")
    args = parser.parse_args()
    print(json.dumps(promote(args.manifest), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
