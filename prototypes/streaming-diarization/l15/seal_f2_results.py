#!/usr/bin/env python3
"""Verify and seal F2 exploratory measurement outputs."""

from __future__ import annotations

import json
import os
from pathlib import Path

from runtime_fixture import sha256_file


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence/f2"
SEAL = EVIDENCE / "F2_EXPLORATORY_EVIDENCE.sha256"


def main() -> int:
    result = json.loads((EVIDENCE / "f2-exploratory-effects.json").read_text())
    verdict = json.loads((EVIDENCE / "f2-exploratory-verdict.json").read_text())
    fixture = json.loads((HERE / "exploratory/f2-dual-lane/runtime-fixture.json").read_text())
    provenance = json.loads((HERE / "exploratory/f2-dual-lane/runtime-asr/provenance.json").read_text())
    checks = {
        "three_strengths": [run["prior_strength"] for run in result["runs"]] == [0.05, 0.1, 0.2],
        "all_deterministic": all(run["deterministic"] for run in result["runs"]),
        "no_selection": not result["selection_performed"],
        "no_acceptance_scoring": not result["acceptance_scoring_performed"],
        "no_identity_claim": not result["identity_accuracy_claim"],
        "exploratory_verdict": verdict["disposition"] == "EXPLORATORY_ONLY_NOT_FREEZEABLE",
        "not_freezeable": verdict["freezeable"] is False,
        "sources_pinned": all(
            sha256_file(REPO / case["audio_path"]) == case["audio_sha256"]
            for case in provenance["cases"]
        ),
        "cache_self_replan": all(case["self_replan"]["self_replan"] == "PASS" for case in fixture["cases"]),
        "holdout_sealed": not result["holdout_opened"] and not verdict["holdout_opened"],
    }
    if not all(checks.values()):
        raise RuntimeError(f"f2_results_verification_failed:{checks}")
    verification_path = EVIDENCE / "f2-exploratory-verification.json"
    verification_path.write_text(
        json.dumps({"schema": "moss-l15-f2-exploratory-verification.v1", "checks": checks, "overall": "PASS"}, indent=2, sort_keys=True) + "\n"
    )
    members = [
        HERE / "f2-lane-prior-family.json",
        HERE / "f2_candidate.py",
        HERE / "collect_f2_runtime_asr.py",
        HERE / "build_f2_runtime_fixture.py",
        HERE / "run_f2_exploratory.py",
        HERE / "seal_f2_results.py",
        HERE / "exploratory/f2-dual-lane/runtime-asr/provenance.json",
        HERE / "exploratory/f2-dual-lane/runtime-fixture.json",
        EVIDENCE / "runtime-asr-preflight.json",
        EVIDENCE / "runtime-asr-transcript.txt",
        EVIDENCE / "commands.txt",
        EVIDENCE / "f2-exploratory-effects.json",
        EVIDENCE / "f2-exploratory-verdict.json",
        verification_path,
        HERE / "evidence/f2-precondition/F2_PRECONDITION_EVIDENCE.sha256",
        HERE / "exploratory/f2-dual-lane/source/local.wav",
        HERE / "exploratory/f2-dual-lane/source/remote.wav",
    ]
    for case in provenance["cases"]:
        members.extend([REPO / case["segments_path"], REPO / case["job_terminal_path"]])
    for case in fixture["cases"]:
        members.append(REPO / case["cache_path"])
    SEAL.write_text(
        "".join(
            f"{sha256_file(path)}  {Path(os.path.relpath(path, EVIDENCE)).as_posix()}\n"
            for path in sorted(members, key=lambda item: item.relative_to(REPO).as_posix())
        )
    )
    print(f"PASS f2_results evidence_members={len(members)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
