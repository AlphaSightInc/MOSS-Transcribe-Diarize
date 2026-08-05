#!/usr/bin/env python3
"""Freeze the L1.5 case split from manifest metadata without reading corpus files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CORPUS_SHA256 = "7c60cb1aaba807adcf6969c616130f0c71b7d8ffb9014d9221d60e1c333f27cb"

DEVELOPMENT = (
    "1m-acquired-nfl",
    "3m-acquired-jamie-dimon",
    "1m-acquired-jamie-dimon",
    "5m-acquired-jamie-dimon",
    "5m-acquired-nfl",
    "5m-lex-bill-ackman",
    "5m-lex-javier-milei",
    "30m-lex-bill-ackman",
)
VALIDATION = (
    "1m-acquired-rolex",
    "1m-lex-bill-ackman",
    "1m-lex-javier-milei",
    "1m-lex-keyu-jin",
    "3m-lex-adam-frank",
    "3m-lex-shapiro-destiny",
    "5m-acquired-alphabet",
    "5m-acquired-rolex",
)
BLIND_HOLDOUT = (
    "5m-acquired-coca-cola",
    "5m-lex-keyu-jin",
    "30m-acquired-jamie-dimon",
)
PRIOR_STAGE0_DEVELOPMENT_VALIDATION = (
    "1m-acquired-nfl",
    "1m-acquired-rolex",
    "1m-lex-bill-ackman",
    "3m-acquired-jamie-dimon",
    "3m-lex-adam-frank",
    "5m-acquired-alphabet",
)
PRIOR_STAGE0_HOLDOUT = (
    "1m-lex-javier-milei",
    "1m-lex-keyu-jin",
    "3m-lex-shapiro-destiny",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def case_record(case: dict[str, Any], split: str) -> dict[str, Any]:
    return {
        "audio_path": case["audio_path"],
        "audio_sha256": case["audio_sha256"],
        "case_id": case["case_id"],
        "duration_seconds": case["duration_seconds"],
        "reference_path": case["reference_path"],
        "reference_sha256": case["reference_sha256"],
        "split": split,
        "vector_cache_path": case["vector_cache_path"],
        "vector_cache_sha256": case["vector_cache_sha256"],
    }


def build(corpus_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if sha256_file(corpus_path) != CORPUS_SHA256:
        raise RuntimeError("split_corpus_hash_mismatch")
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    by_id = {str(case["case_id"]): case for case in corpus["cases"]}
    assigned = DEVELOPMENT + VALIDATION + BLIND_HOLDOUT
    if len(assigned) != len(set(assigned)):
        raise RuntimeError("split_duplicate_case")
    if set(assigned) != set(by_id):
        raise RuntimeError("split_membership_mismatch")
    if len(by_id) != 19:
        raise RuntimeError("split_case_count_mismatch")
    for case_id in assigned:
        if not by_id[case_id].get("acceptance_eligible"):
            raise RuntimeError(f"split_case_not_acceptance_eligible:{case_id}")
    if not any(by_id[case_id]["duration_seconds"] >= 1800 for case_id in DEVELOPMENT + VALIDATION):
        raise RuntimeError("split_no_30m_development_validation")
    if not any(by_id[case_id]["duration_seconds"] >= 1800 for case_id in BLIND_HOLDOUT):
        raise RuntimeError("split_no_30m_holdout")
    unseen_holdout = sorted(set(BLIND_HOLDOUT) - set(PRIOR_STAGE0_DEVELOPMENT_VALIDATION))
    if len(unseen_holdout) < 3:
        raise RuntimeError("split_holdout_prior_development_overlap")

    groups = {
        "blind_holdout": [case_record(by_id[case_id], "blind_holdout") for case_id in BLIND_HOLDOUT],
        "development": [case_record(by_id[case_id], "development") for case_id in DEVELOPMENT],
        "validation": [case_record(by_id[case_id], "validation") for case_id in VALIDATION],
    }
    split = {
        "case_count": len(assigned),
        "corpus_manifest_path": corpus_path.relative_to(REPO).as_posix(),
        "corpus_manifest_sha256": CORPUS_SHA256,
        "freeze_date": "2026-08-04",
        "groups": groups,
        "holdout_requirements": {
            "certified_30m_cases": [
                case_id for case_id in BLIND_HOLDOUT if by_id[case_id]["duration_seconds"] >= 1800
            ],
            "not_seen_in_prior_campaign_development": unseen_holdout,
            "passed": True,
        },
        "prior_exposure": {
            "stage0_development_validation": list(PRIOR_STAGE0_DEVELOPMENT_VALIDATION),
            "stage0_holdout": list(PRIOR_STAGE0_HOLDOUT),
        },
        "schema": "moss-l15-split-manifest.v1",
        "selection_basis": [
            "manifest metadata and prior split exposure only; no audio/reference content read",
            "one certified 30-minute case in development and one in blind holdout",
            "blind holdout uses three promoted cases absent from Stage-0 development/validation",
            "prior Stage-0 holdout cases are not reused as L1.5 holdout",
        ],
    }
    split_hash = hashlib.sha256(canonical_bytes(split)).hexdigest()
    procedure = {
        "candidate_freeze_path": "prototypes/streaming-diarization/l15/candidate-freeze.json",
        "corpus_manifest_sha256": CORPUS_SHA256,
        "holdout_cases": groups["blind_holdout"],
        "opening_marker_path": "prototypes/streaming-diarization/l15/evidence/holdout-opening/holdout-opened.json",
        "rules": {
            "all_frozen_candidate_arms_same_session": True,
            "candidate_family_and_thresholds_frozen_before_open": True,
            "holdout_cache_rebuild_inside_opening": True,
            "l1_runs_per_case": 2,
            "no_post_open_tuning": True,
            "opening_count_max": 1,
            "same_production_planned_frame_all_arms": True,
        },
        "schema": "moss-l15-holdout-procedure.v1",
        "split_manifest_path": "prototypes/streaming-diarization/l15/split-manifest.json",
        "split_manifest_sha256": split_hash,
        "status": "SEALED_UNTIL_POST_FREEZE_SUPERVISOR_GO",
        "supervisor_ruling": {
            "date": "2026-08-04",
            "text": "L1 baseline runs on dev/validation only now; holdout L1 x2 runs inside the single post-freeze opening alongside candidate arms",
        },
    }
    return split, procedure


def write_or_check(path: Path, payload: object, *, check: bool) -> None:
    expected = canonical_bytes(payload)
    if check:
        if not path.is_file() or path.read_bytes() != expected:
            raise RuntimeError(f"split_freeze_drift:{path}")
        return
    if path.exists():
        raise RuntimeError(f"split_freeze_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(expected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus-manifest",
        type=Path,
        default=REPO / "prototypes/streaming-diarization/l2-stage0/corpus-manifest.json",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    split, procedure = build(args.corpus_manifest.resolve())
    split_path = HERE / "split-manifest.json"
    procedure_path = HERE / "holdout-procedure.json"
    write_or_check(split_path, split, check=args.check)
    write_or_check(procedure_path, procedure, check=args.check)
    print(
        json.dumps(
            {
                "case_count": split["case_count"],
                "holdout": [case["case_id"] for case in split["groups"]["blind_holdout"]],
                "holdout_procedure_sha256": hashlib.sha256(canonical_bytes(procedure)).hexdigest(),
                "overall": "PASS",
                "split_manifest_sha256": hashlib.sha256(canonical_bytes(split)).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
