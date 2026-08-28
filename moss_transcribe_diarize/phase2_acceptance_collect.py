"""Candidate-owned reducer for one layer's raw qualification observations.

Measurement programs write one raw predicate envelope per required predicate. This reducer, shipped
inside the candidate, refuses missing/duplicate/mismatched envelopes and derives the only report the
acceptance driver will consume. It does not accept a pre-authored report or execute profile code.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Mapping

from .phase2_acceptance import EXTERNAL_REQUIREMENTS, OBSERVATION_SCHEMA, _write_all


RAW_SCHEMA = "moss-phase2-raw-observation.v1"


def _artifact_name(layer: str, gate: str, predicate_id: str) -> str:
    return f"{layer}--{gate}--{predicate_id}.json"


def collect_layer(
    *, layer: str, candidate_sha: str, raw_dir: Path
) -> dict[str, object]:
    if layer not in EXTERNAL_REQUIREMENTS:
        raise ValueError(f"unsupported observation layer: {layer}")
    raw_dir = raw_dir.resolve()
    if raw_dir.stat().st_mode & 0o777 != 0o700:
        raise PermissionError("raw observation directory must be mode 0700")

    predicates: list[dict[str, object]] = []
    artifacts: list[dict[str, object]] = []
    expected_names: set[str] = set()
    for gate, ids in EXTERNAL_REQUIREMENTS[layer].items():
        for predicate_id in ids:
            name = _artifact_name(layer, gate, predicate_id)
            expected_names.add(name)
            path = raw_dir / name
            encoded = path.read_bytes()
            payload = json.loads(encoded)
            if not isinstance(payload, dict):
                raise ValueError(f"raw observation is not an object: {name}")
            expected = {
                "schema": RAW_SCHEMA,
                "layer": layer,
                "candidate_sha": candidate_sha,
                "gate": gate,
                "id": predicate_id,
            }
            if any(payload.get(key) != value for key, value in expected.items()):
                raise ValueError(f"raw observation identity mismatch: {name}")
            samples = payload.get("samples")
            raw = payload.get("raw")
            if not isinstance(samples, list) or not samples or not isinstance(raw, dict):
                raise ValueError(f"raw observation has no measured samples/state: {name}")
            cases: list[dict[str, object]] = []
            sample_ids: set[str] = set()
            for sample in samples:
                if not isinstance(sample, dict):
                    raise ValueError(f"raw sample is not an object: {name}")
                sample_id = sample.get("id")
                executed = sample.get("executed")
                passed = sample.get("passed")
                if (
                    not isinstance(sample_id, str)
                    or not sample_id
                    or sample_id in sample_ids
                    or not isinstance(executed, bool)
                    or not isinstance(passed, bool)
                    or passed and not executed
                ):
                    raise ValueError(f"raw sample is incomplete: {name}")
                sample_ids.add(sample_id)
                cases.append(
                    {"id": sample_id, "executed": executed, "passed": passed}
                )
            executed_count = sum(item["executed"] is True for item in cases)
            passed_count = sum(item["passed"] is True for item in cases)
            failed_count = sum(
                item["executed"] is True and item["passed"] is False for item in cases
            )
            predicates.append(
                {
                    "gate": gate,
                    "id": predicate_id,
                    "cases": cases,
                    "counts": {
                        "collected": len(cases),
                        "executed": executed_count,
                        "passed": passed_count,
                        "failed": failed_count,
                        "skipped": 0,
                        "unmeasured": len(cases) - executed_count,
                    },
                    "raw": raw,
                }
            )
            artifacts.append(
                {
                    "name": name,
                    "sha256": hashlib.sha256(encoded).hexdigest(),
                    "bytes": len(encoded),
                }
            )

    expected_names.add("measurement-state.json")
    state_path = raw_dir / "measurement-state.json"
    state_encoded = state_path.read_bytes()
    state = json.loads(state_encoded)
    campaign_artifacts = state.get("campaign_artifacts") if isinstance(state, dict) else None
    if (
        not isinstance(state, dict)
        or state.get("layer") != layer
        or state.get("candidate_sha") != candidate_sha
        or not isinstance(campaign_artifacts, list)
        or any(not isinstance(name, str) or not name for name in campaign_artifacts)
        or len(set(campaign_artifacts)) != len(campaign_artifacts)
    ):
        raise ValueError("measurement state artifact manifest is invalid")
    retained = [state_path]
    artifact_root = raw_dir / "artifacts"
    if campaign_artifacts:
        if artifact_root.is_symlink() or not artifact_root.is_dir():
            raise ValueError("campaign artifact root is invalid")
        expected_artifacts: set[Path] = set()
        for name in campaign_artifacts:
            relative = Path(name)
            if (
                relative.is_absolute()
                or not relative.parts
                or any(part in {"", ".", ".."} for part in relative.parts)
            ):
                raise ValueError("campaign artifact path is invalid")
            expected_artifacts.add(artifact_root / relative)
        observed_artifacts = {
            path for path in artifact_root.rglob("*") if path.is_file()
        }
        if any(path.is_symlink() for path in artifact_root.rglob("*")):
            raise ValueError("campaign artifact must not be a symlink")
        if observed_artifacts != expected_artifacts:
            raise ValueError("campaign artifact manifest does not match files")
        retained.extend(sorted(expected_artifacts))
    elif artifact_root.exists():
        raise ValueError("unmanifested campaign artifact root")
    for path in retained:
        encoded = path.read_bytes()
        artifacts.append(
            {
                "name": path.relative_to(raw_dir).as_posix(),
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "bytes": len(encoded),
            }
        )
    unexpected = sorted(
        path.name
        for path in raw_dir.iterdir()
        if path.is_file() and path.name not in expected_names
    )
    if unexpected:
        raise ValueError(f"unexpected raw observation artifacts: {unexpected}")
    return {
        "schema": OBSERVATION_SCHEMA,
        "layer": layer,
        "candidate_sha": candidate_sha,
        "collector": {
            "id": "candidate-owned-raw-reducer.v1",
            "raw_schema": RAW_SCHEMA,
            "artifacts": artifacts,
        },
        "predicates": predicates,
    }


def write_collected_report(payload: Mapping[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
