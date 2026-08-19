#!/usr/bin/env python3
"""Validate and print the sealed lane-balance v3 contract and scoring self-checks."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).parent
REPO = ROOT.parents[1]
V2 = ROOT / "preregistration-v2.json"
V3 = ROOT / "preregistration-v3.json"
sys.path.insert(0, str(ROOT))
from proto_lane_balance_v3 import read_pcm, rms, sha256, shuffle_edit_score  # noqa: E402


def edit_distance(reference: tuple[str, ...], hypothesis: tuple[str, ...]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for reference_index, reference_token in enumerate(reference, 1):
        current = [reference_index]
        for hypothesis_index, hypothesis_token in enumerate(hypothesis, 1):
            current.append(min(
                previous[hypothesis_index] + 1,
                current[-1] + 1,
                previous[hypothesis_index - 1] + int(reference_token != hypothesis_token),
            ))
        previous = current
    return previous[-1]


def interleavings(a: tuple[str, ...], b: tuple[str, ...]) -> set[tuple[str, ...]]:
    output: set[tuple[str, ...]] = set()
    for a_positions in itertools.combinations(range(len(a) + len(b)), len(a)):
        a_position_set = set(a_positions)
        a_index = 0
        b_index = 0
        row: list[str] = []
        for index in range(len(a) + len(b)):
            if index in a_position_set:
                row.append(a[a_index])
                a_index += 1
            else:
                row.append(b[b_index])
                b_index += 1
        output.add(tuple(row))
    return output


def brute_force_shuffle_distance(
    a: tuple[str, ...], b: tuple[str, ...], hypothesis: tuple[str, ...]
) -> int:
    return min(edit_distance(reference, hypothesis) for reference in interleavings(a, b))


def main() -> None:
    contract = json.loads(V3.read_text(encoding="utf-8"))
    assert contract["schema"] == "moss-lane-balance-preregistration.v3"
    assert contract["amends"]["path"] == "prototypes/lane-balance/preregistration-v2.json"
    assert contract["amends"]["sha256"] == sha256(V2)
    assert contract["amends"]["result_sha256"] == sha256(
        REPO / contract["amends"]["result_path"]
    )
    assert [corpus["role"] for corpus in contract["corpora"]].count("discovery") == 1
    assert [corpus["role"] for corpus in contract["corpora"]].count("validation") == 3
    assert [candidate["microphone_gain_db_from_quiet"] for candidate in contract["candidates"]] == [
        0.0, 3.0, 6.0, 9.0, 12.0, 15.377, 18.377, 21.377
    ]
    assert "D[i,j,k]" in contract["metrics"]["primary_recurrence"]
    assert "never summed" in contract["metrics"]["diagnostics"][0]

    calibration_rows = []
    target = float(contract["calibration"]["target_total_disparity_db"])
    tolerance = float(contract["calibration"]["tolerance_db"])
    for corpus in contract["corpora"]:
        shared_path = REPO / corpus["shared_lane"]
        microphone_path = REPO / corpus["microphone_lane"]
        assert sha256(shared_path) == corpus["shared_sha256"]
        assert sha256(microphone_path) == corpus["microphone_sha256"]
        shared, shared_rate = read_pcm(shared_path, int(corpus["clip_seconds"]))
        microphone, microphone_rate = read_pcm(
            microphone_path, int(corpus["clip_seconds"])
        )
        assert shared_rate == microphone_rate == 16000
        attenuation = 10 ** (float(corpus["microphone_attenuation_db"]) / 20)
        measured = 20 * math.log10(rms(shared) / rms([sample * attenuation for sample in microphone]))
        assert math.isclose(measured, target, rel_tol=0.0, abs_tol=tolerance)
        calibration_rows.append({
            "corpus": corpus["id"],
            "attenuation_db": corpus["microphone_attenuation_db"],
            "measured_total_disparity_db": measured,
        })
    assert math.isclose(
        contract["corpora"][0]["microphone_attenuation_db"],
        contract["calibration"]["k2_required_synthetic_attenuation_db"],
        rel_tol=0.0,
        abs_tol=1e-12,
    )

    scoring_rows = []
    token_values = ("a", "b")
    for a_length in range(3):
        for b_length in range(3):
            for h_length in range(4):
                for a in itertools.product(token_values, repeat=a_length):
                    for b in itertools.product(token_values, repeat=b_length):
                        for hypothesis in itertools.product(token_values, repeat=h_length):
                            measured = shuffle_edit_score(list(a), list(b), list(hypothesis))["distance"]
                            expected = brute_force_shuffle_distance(a, b, hypothesis)
                            assert measured == expected, (a, b, hypothesis, measured, expected)
                scoring_rows.append({
                    "shared_length": a_length,
                    "microphone_length": b_length,
                    "hypothesis_length": h_length,
                    "exhaustive_cases": (
                        len(token_values) ** (a_length + b_length + h_length)
                    ),
                })

    print(json.dumps({
        "contract_path": str(V3.relative_to(REPO)),
        "contract_sha256": hashlib.sha256(V3.read_bytes()).hexdigest(),
        "calibration": calibration_rows,
        "scoring_exhaustive_crosscheck": scoring_rows,
        "contract": contract,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
