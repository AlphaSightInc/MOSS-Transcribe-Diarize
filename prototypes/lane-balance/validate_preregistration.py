#!/usr/bin/env python3
"""Validate and print the sealed lane-balance v2 measurement contract."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).parent
V1 = ROOT / "preregistration-v1.json"
V2 = ROOT / "preregistration-v2.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    v1 = json.loads(V1.read_text(encoding="utf-8"))
    v2 = json.loads(V2.read_text(encoding="utf-8"))
    assert v1["schema"] == "moss-lane-balance-preregistration.v1"
    assert v2["schema"] == "moss-lane-balance-preregistration.v2"
    assert v2["amends"]["path"] == "prototypes/lane-balance/preregistration-v1.json"
    assert v2["amends"]["sha256"] == sha256(V1)
    for key in ("question", "scope", "production_path"):
        assert v2[key] == v1[key]
    assert v2["fixture"] == v1["fixture"]
    assert v2["metrics"] == v1["metrics"]
    assert v2["decision_rule"] == v1["decision_rule"]
    assert [candidate["id"] for candidate in v2["candidates"]] == [
        "identity",
        "peer_rms_matched_microphone",
        "half_matched_microphone",
        "restore_microphone_to_clean_level",
    ]
    for original, amended in zip(v1["candidates"], v2["candidates"][:3]):
        for key, value in original.items():
            assert amended[key] == value
    restored = v2["candidates"][-1]
    attenuation = -v2["fixture"]["microphone_attenuation_db"]
    assert restored["microphone_gain_db_from_quiet"] == attenuation
    assert math.isclose(restored["microphone_gain"], 10 ** (attenuation / 20), rel_tol=0.0, abs_tol=1e-15)
    print(json.dumps(v2, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
