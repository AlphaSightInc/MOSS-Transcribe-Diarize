"""Replay content-free H1 browser evidence through frozen acceptance validators."""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from moss_transcribe_diarize.phase2_acceptance import _validate_raw_predicate
from moss_transcribe_diarize.phase2_acceptance_completion import (
    SUMMARY_CHECKS,
    validate_completion_observation,
)


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def main(root: Path) -> None:
    for layer in ("deployed", "pre_admission"):
        observed = read(root / f"{layer}-observations.json")
        rows = {item["id"]: item for item in observed["predicates"]}
        g9 = rows["browser_final_summary"]
        g1 = rows["sentinel_absence"]
        g10 = rows["transcript_pane_fidelity"]
        g9_raw = g9["raw"]
        g1_raw = g1["raw"]
        g10_valid = _validate_raw_predicate(
            "transcript_pane_fidelity", g10,
            candidate_sha="", candidate_tree="", uv_lock_sha256="", fixtures={},
            wheel_record_projection_sha256="", dependency_projection_sha256="",
        )
        print(json.dumps({
            "layer": layer,
            "g9": {
                "measurement": g9["counts"],
                "failure_operation": g9_raw.get("failure_operation"),
                "validator_pass": validate_completion_observation("browser_final_summary", g9_raw),
                "check_bits_retained": len(set(g9_raw.get("checks", {})) & SUMMARY_CHECKS),
                "required_check_bits": len(SUMMARY_CHECKS),
            },
            "g1": {
                "measurement": g1["counts"],
                "failure_operation": g1_raw.get("failure_operation"),
                "surfaces_retained": len(g1_raw.get("surfaces", [])),
                "audio_checks_retained": len(g1_raw.get("audio_sentinel_checks", [])),
            },
            "g10": {
                "measurement": g10["counts"], "validator_pass": g10_valid,
                "viewports": [
                    {"viewport": f"{v['width']}x{v['height']}",
                     "pane": f"{v['pane_width']}x{v['pane_height']}",
                     "total_pct": round(100 * v["total_difference"], 4),
                     "total_excess_pp": round(100 * (v["total_difference"] - 0.02), 4),
                     "largest_pct": round(100 * v["largest_connected_difference"], 4),
                     "largest_excess_pp": round(100 * (v["largest_connected_difference"] - 0.01), 4)}
                    for v in g10["raw"]["viewports"]
                ],
            },
        }, sort_keys=True))

    counts = Counter()
    for case in ET.parse(root / "python-report.xml").iter("testcase"):
        for kind in ("failure", "error"):
            failure = case.find(kind)
            if failure is None:
                continue
            message = failure.get("message", "")
            if "TargetClosedError" in message or "Chrome exited before" in message:
                label = "chrome_launch"
            elif "F_GETPATH" in message:
                label = "linux_fcntl"
            elif "60084 == 60000" in message:
                label = "tape_accounting"
            else:
                label = "other"
            counts[label] += 1
    print(json.dumps({"host_pytest_failures": dict(counts), "total": sum(counts.values())}, sort_keys=True))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
