#!/usr/bin/env python3
"""Verify the frozen L1.5 split and launcher pins without opening corpus truth."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--transcript-output", type=Path, required=True)
    args = parser.parse_args()
    corpus_path = REPO / "prototypes/streaming-diarization/l2-stage0/corpus-manifest.json"
    split_path = HERE / "split-manifest.json"
    procedure_path = HERE / "holdout-procedure.json"
    contract_path = REPO / "scripts/ralph-l15-afk/contract.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    split = json.loads(split_path.read_text(encoding="utf-8"))
    procedure = json.loads(procedure_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    groups = split["groups"]
    ids = {
        group: [case["case_id"] for case in cases]
        for group, cases in groups.items()
    }
    all_ids = [case_id for group_ids in ids.values() for case_id in group_ids]
    corpus_ids = [case["case_id"] for case in corpus["cases"]]
    checks = {
        "candidate_freeze_absent": not (REPO / procedure["candidate_freeze_path"]).exists(),
        "corpus_pin": contract["corpus_manifest_hash"] == sha256_file(corpus_path),
        "exact_19_cases": len(all_ids) == len(set(all_ids)) == len(corpus_ids) == 19
        and set(all_ids) == set(corpus_ids),
        "holdout_has_30m": any(
            case["duration_seconds"] >= 1800 for case in groups["blind_holdout"]
        ),
        "holdout_has_three_prior_dev_unseen": len(
            set(ids["blind_holdout"])
            - set(split["prior_exposure"]["stage0_development_validation"])
        )
        >= 3,
        "opening_marker_absent": not (REPO / procedure["opening_marker_path"]).exists(),
        "procedure_pin": contract["holdout_procedure_sha256"] == sha256_file(procedure_path),
        "split_pin": contract["split_manifest_hash"] == sha256_file(split_path),
        "training_has_30m": any(
            case["duration_seconds"] >= 1800
            for group in ("development", "validation")
            for case in groups[group]
        ),
    }
    failures = sorted(name for name, passed in checks.items() if not passed)
    payload = {
        "checks": checks,
        "content_files_read": [
            contract_path.relative_to(REPO).as_posix(),
            corpus_path.relative_to(REPO).as_posix(),
            procedure_path.relative_to(REPO).as_posix(),
            split_path.relative_to(REPO).as_posix(),
        ],
        "counts": {group: len(group_ids) for group, group_ids in ids.items()},
        "failures": failures,
        "holdout_case_ids": ids["blind_holdout"],
        "holdout_status": "SEALED",
        "overall": "PASS" if not failures else "FAIL",
        "procedure_sha256": sha256_file(procedure_path),
        "schema": "moss-l15-split-freeze-verdict.v1",
        "split_manifest_sha256": sha256_file(split_path),
    }
    transcript = "\n".join(
        [
            *(f"{'PASS' if passed else 'FAIL'} {name}" for name, passed in checks.items()),
            f"HOLDOUT SEALED cases={','.join(ids['blind_holdout'])}",
            f"RESULT {payload['overall']} failures={','.join(failures) if failures else 'none'}",
        ]
    ) + "\n"
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.transcript_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.transcript_output.write_text(transcript, encoding="utf-8")
    print(transcript, end="")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
