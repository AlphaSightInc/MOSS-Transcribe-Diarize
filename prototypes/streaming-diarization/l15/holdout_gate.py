#!/usr/bin/env python3
"""Procedural opening-once guard for the sealed L1.5 holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


class GateError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def canonical_bytes(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(repo: Path, value: object) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else repo / path


def _split_index(split: dict[str, Any]) -> dict[str, str]:
    if split.get("schema") != "moss-l15-split-manifest.v1":
        raise GateError("l15_split_schema_invalid", str(split.get("schema")))
    index: dict[str, str] = {}
    for group in ("development", "validation", "blind_holdout"):
        for case in split.get("groups", {}).get(group, []):
            case_id = str(case.get("case_id"))
            if case_id in index:
                raise GateError("l15_split_duplicate_case", case_id)
            index[case_id] = group
    if len(index) != int(split.get("case_count", -1)):
        raise GateError("l15_split_case_count_mismatch", str(len(index)))
    return index


def _validate_procedure(split: dict[str, Any], procedure: dict[str, Any]) -> None:
    if procedure.get("schema") != "moss-l15-holdout-procedure.v1":
        raise GateError("l15_holdout_procedure_schema_invalid", str(procedure.get("schema")))
    actual_split_hash = hashlib.sha256(canonical_bytes(split)).hexdigest()
    if procedure.get("split_manifest_sha256") != actual_split_hash:
        raise GateError("l15_split_hash_mismatch", actual_split_hash)
    if procedure.get("corpus_manifest_sha256") != split.get("corpus_manifest_sha256"):
        raise GateError("l15_corpus_pin_mismatch", str(procedure.get("corpus_manifest_sha256")))
    rules = procedure.get("rules", {})
    required_rules = {
        "all_frozen_candidate_arms_same_session": True,
        "candidate_family_and_thresholds_frozen_before_open": True,
        "holdout_cache_rebuild_inside_opening": True,
        "l1_runs_per_case": 2,
        "no_post_open_tuning": True,
        "opening_count_max": 1,
        "same_production_planned_frame_all_arms": True,
    }
    if any(rules.get(name) != value for name, value in required_rules.items()):
        raise GateError("l15_holdout_rules_invalid", json.dumps(rules, sort_keys=True))


def _load_candidate_freeze(procedure: dict[str, Any], repo: Path) -> dict[str, Any]:
    path = _resolve(repo, procedure["candidate_freeze_path"])
    if not path.is_file():
        raise GateError("l15_holdout_before_candidate_freeze", str(path))
    try:
        frozen = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError("l15_candidate_freeze_invalid", str(path)) from exc
    if frozen.get("schema") != "moss-l15-candidate-freeze.v1" or not frozen.get("candidate_frozen"):
        raise GateError("l15_candidate_freeze_invalid", str(path))
    if frozen.get("corpus_manifest_sha256") != procedure.get("corpus_manifest_sha256"):
        raise GateError("l15_candidate_corpus_pin_mismatch", str(path))
    if frozen.get("split_manifest_sha256") != procedure.get("split_manifest_sha256"):
        raise GateError("l15_candidate_split_pin_mismatch", str(path))
    return frozen


def assert_case_access(
    case_id: str,
    split: dict[str, Any],
    procedure: dict[str, Any],
    *,
    repo: Path = REPO,
) -> str:
    """Permit unsealed cases; direct holdout reads always fail outside the opener."""
    _validate_procedure(split, procedure)
    group = _split_index(split).get(case_id)
    if group is None:
        raise GateError("l15_case_unknown", case_id)
    if group != "blind_holdout":
        return group
    _load_candidate_freeze(procedure, repo)
    marker = _resolve(repo, procedure["opening_marker_path"])
    if marker.exists():
        raise GateError("l15_holdout_already_opened", str(marker))
    raise GateError("l15_holdout_requires_single_opening_session", case_id)


def open_holdout_session(
    procedure_path: Path,
    *,
    repo: Path = REPO,
    authorization: str,
) -> Path:
    """Create the one exclusive opening marker after validating the frozen pins."""
    if authorization != "SUPERVISOR_GO":
        raise GateError("l15_holdout_authorization_missing", authorization)
    procedure = json.loads(procedure_path.read_text(encoding="utf-8"))
    split_path = _resolve(repo, procedure["split_manifest_path"])
    if not split_path.is_file():
        raise GateError("l15_split_manifest_missing", str(split_path))
    split = json.loads(split_path.read_text(encoding="utf-8"))
    _validate_procedure(split, procedure)
    if sha256_file(split_path) != procedure["split_manifest_sha256"]:
        raise GateError("l15_split_file_hash_mismatch", str(split_path))
    frozen = _load_candidate_freeze(procedure, repo)
    marker = _resolve(repo, procedure["opening_marker_path"])
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "candidate_freeze_sha256": hashlib.sha256(canonical_bytes(frozen)).hexdigest(),
        "corpus_manifest_sha256": procedure["corpus_manifest_sha256"],
        "holdout_case_ids": [case["case_id"] for case in procedure["holdout_cases"]],
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "opening_count": 1,
        "schema": "moss-l15-holdout-opening.v1",
        "split_manifest_sha256": procedure["split_manifest_sha256"],
    }
    try:
        with marker.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    except FileExistsError as exc:
        raise GateError("l15_holdout_already_opened", str(marker)) from exc
    return marker


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check-case")
    check.add_argument("--case-id", required=True)
    check.add_argument("--split", type=Path, default=HERE / "split-manifest.json")
    check.add_argument("--procedure", type=Path, default=HERE / "holdout-procedure.json")
    opening = subparsers.add_parser("open")
    opening.add_argument("--procedure", type=Path, default=HERE / "holdout-procedure.json")
    opening.add_argument("--authorization", required=True)
    args = parser.parse_args()
    try:
        if args.command == "check-case":
            split = json.loads(args.split.read_text(encoding="utf-8"))
            procedure = json.loads(args.procedure.read_text(encoding="utf-8"))
            group = assert_case_access(args.case_id, split, procedure)
            print(json.dumps({"case_id": args.case_id, "split": group, "status": "PASS"}, sort_keys=True))
        else:
            marker = open_holdout_session(
                args.procedure, authorization=args.authorization
            )
            print(json.dumps({"marker": marker.relative_to(REPO).as_posix(), "status": "OPENED"}, sort_keys=True))
    except GateError as exc:
        print(f"BLOCKED {exc.code}: {exc.detail}")
        print("<promise>BLOCKED</promise>")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
