#!/usr/bin/env python3
"""Validate the sealed cap/silence contract before any score is produced."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CONTRACT = Path(__file__).with_name("preregistration-cap-silence-v1.json")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["schema"] == "moss-live-cap-silence-preregistration.v1"
    candidates = contract["candidates"]
    ids = [item["id"] for item in candidates]
    assert len(ids) == len(set(ids)) == 9
    assert contract["discovery_selection"]["baseline_id"] == ids[0]
    assert {item["hard_cap_ms"] for item in candidates} >= {750, 1000, 1500, 2000, 2500}
    assert {item["min_silence_ms"] for item in candidates} == {250, 500, 750}
    assert all(item["hard_cap_ms"] > 0 and item["min_silence_ms"] > 0 for item in candidates)

    production = contract["production_contract"]
    for path_key, hash_key in (
        ("manifest_path", "manifest_sha256"),
        ("model_path", "model_sha256"),
    ):
        owner = production if path_key == "manifest_path" else production["identity"]
        path = REPO / owner[path_key]
        assert digest(path) == owner[hash_key], (path, digest(path), owner[hash_key])
    evidence = production["reader_render_bound_evidence"]
    assert digest(REPO / evidence["path"]) == evidence["sha256"]

    roles = [item["role"] for item in contract["corpora"]]
    assert roles.count("discovery") == roles.count("validation") == 2
    for corpus in contract["corpora"]:
        assert "holdout" not in corpus["id"].lower()
        assert digest(REPO / corpus["audio"]) == corpus["audio_sha256"]
        assert digest(REPO / corpus["reference"]) == corpus["reference_sha256"]

    print(json.dumps({
        "valid": True,
        "contract_sha256": digest(CONTRACT),
        "candidate_ids": ids,
        "corpus_roles": roles,
        "production_manifest_sha256": production["manifest_sha256"],
        "reader_render_bound_ms": production["reader_render_bound_ms"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
