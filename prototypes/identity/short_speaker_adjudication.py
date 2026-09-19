#!/usr/bin/env python3
"""THROWAWAY WP55b-P step-1 custody/adjudication refusal.

The brief requires acoustic listening before three snippets are frozen.  The common
contract forbids playing audio.  This script verifies retained source/sample custody
and records why the existing three-case population cannot be promoted without
pretending reference timestamps prove acoustic purity.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import soundfile as sf


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ROUND2 = Path("/Users/gao/Documents/Codex/2026-09-19/moss-round2")
CANDIDATE = ROUND2 / "candidate"
ORACLE = ROUND2 / "mvp-plan/prototypes/identity/oracle-population"
EXPECTED_SHA = "a7a738cf9f9ff246f64c52c112e0bf597ba58241"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def main() -> int:
    base_is_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", EXPECTED_SHA, "HEAD"],
        cwd=ROOT,
    ).returncode == 0
    product_tree_unchanged = subprocess.run(
        [
            "git", "diff", "--quiet", EXPECTED_SHA, "--",
            "moss_transcribe_diarize", "tests", "frontend",
        ],
        cwd=ROOT,
    ).returncode == 0
    if not base_is_ancestor or not product_tree_unchanged:
        raise SystemExit(
            "WP55b-P requires a7a738cf ancestry and its unchanged product/test tree"
        )
    manifest = json.loads((ORACLE / "manifest.json").read_text())
    analysis = json.loads((ORACLE / "oracle-analysis.json").read_text())
    by_case = {row["case_id"]: row for row in analysis["cases"]}
    cases = []
    for row in manifest["population"]:
        audio = Path(row["source_audio"])
        info = sf.info(audio)
        start = int(row["source_sample_start"])
        end = int(row["source_sample_end"])
        if info.samplerate != 16_000 or info.channels < 1 or end > info.frames or start < 0:
            raise RuntimeError(f"invalid retained source custody: {row['case_id']}")
        prior = by_case[row["case_id"]]
        if row["case_id"] == "boss_how_long":
            status = "retained_useful_exact_witness_not_freshly_listened"
            reason = (
                "Exact phrase passed sequential and isolated controls in round 2, but "
                "step 1 requires fresh listening-based ownership/purity adjudication."
            )
        else:
            status = "rejected_boundary_spill"
            reason = prior["source_limit"]
        cases.append({
            "case_id": row["case_id"],
            "source_audio": str(audio),
            "source_reference": row["source_reference"],
            "source_speaker": row["source_speaker"],
            "reference_phrase": row["target_phrase"],
            "sample_start": start,
            "sample_end": end,
            "sample_count": end - start,
            "duration_seconds": (end - start) / info.samplerate,
            "source_sample_rate": info.samplerate,
            "source_frames": info.frames,
            "status": status,
            "reason": reason,
        })
    result = {
        "schema": "moss-round3-wp55b-step1.v1",
        "scope": {
            "candidate_sha": EXPECTED_SHA,
            "candidate_is_ancestor": base_is_ancestor,
            "product_test_frontend_tree_unchanged": product_tree_unchanged,
            "source_revision": git(CANDIDATE, "rev-parse", "HEAD"),
            "decoder_requests": 0,
            "network_calls": 0,
            "audio_playback": 0,
            "constraint": "COMMON.md forbids unmuting or playing audio",
        },
        "structural_question": (
            "Can three complete source-owned utterances be frozen without adjacent "
            "speaker spill before any decoder lease is justified?"
        ),
        "minimum_primitives": [
            "source-owned utterance", "exact sample boundary", "speaker ownership",
            "complete reference words", "adjacent-speaker exclusion",
        ],
        "invariants": [
            "no boundary spill", "three independently complete snippets",
            "no decoder call before step 1 passes", "no audio playback under common contract",
        ],
        "cases": cases,
        "retained_useful_candidates": sum(
            row["status"].startswith("retained_useful") for row in cases
        ),
        "fresh_listening_adjudications": 0,
        "required_clean_snippets": 3,
        "clean_snippets_frozen": 0,
        "gate_verdict": "FAIL",
        "blocker": (
            "Three clean snippets cannot be independently established: two retained cases "
            "have demonstrated boundary spill, and the required listening step conflicts "
            "with the common no-audio-playback instruction."
        ),
        "next_steps": {
            "ip1_cpu_onnx": "NOT RUN: step 1 says stop if three clean snippets cannot be produced",
            "oracle_matrix": "NOT UNLOCKED",
            "decoder_budget": "0 of gated 12 used",
        },
    }
    output = HERE / "short-speaker-results.json"
    evidence = ROOT / "evidence/round3/wp55b-p/short-speaker-results.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    output.write_text(payload)
    evidence.write_text(payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
