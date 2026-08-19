#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CONTRACT = Path(__file__).with_name("preregistration-live-dual-lane-v1.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["schema"] == "moss-live-dual-lane-preregistration.v1"
    for binding in contract["bound_evidence"].values():
        path = REPO / binding["path"]
        assert path.is_file(), path
        assert sha256(path) == binding["sha256"], path
    manifest = REPO / contract["production_contract"]["manifest_path"]
    assert sha256(manifest) == contract["production_contract"]["manifest_sha256"]
    assert contract["arms"] == ["production_mono_mix", "dual_lane_serial"]
    print(json.dumps({
        "valid": True,
        "contract": str(CONTRACT.relative_to(REPO)),
        "sha256": sha256(CONTRACT),
        "question": contract["question"],
        "module_interface": contract["module_interface"],
        "decision_rule": contract["decision_rule"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
