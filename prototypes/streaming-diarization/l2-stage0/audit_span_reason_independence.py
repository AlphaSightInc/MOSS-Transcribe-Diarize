#!/usr/bin/env python3
"""Prove the current scoring path never reads ``FrozenSpan.reason``."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
TEST_RESULT = HERE / "evidence/anchor-fidelity/legacy-green-reason-post-duration.json"
INPUTS = (
    HERE / "run_l1_control.py",
    HERE / "production_cache.py",
    HERE / "legacy_ingest.py",
    HERE / "run_legacy_anchor_fidelity.py",
    HERE / "test_legacy_ingest.py",
    REPO / "moss_transcribe_diarize/app/live_identity.py",
    REPO / "moss_transcribe_diarize/app/live_provider_bundle.py",
    REPO / "moss_transcribe_diarize/live_speaker_accuracy.py",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(path: Path) -> str:
    return path.resolve().relative_to(REPO.resolve()).as_posix()


def lines_with(path: Path, needle: str) -> list[int]:
    return [
        index
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if needle in line
    ]


def span_reason_reads(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "reason"
        and isinstance(node.value, ast.Name)
        and node.value.id == "span"
    )


def citation(path: Path, needle: str, statement: str) -> dict[str, object]:
    matches = lines_with(path, needle)
    if not matches:
        raise RuntimeError(f"span_reason_audit_citation_missing:{repo_path(path)}:{needle}")
    return {
        "line": matches[0],
        "path": repo_path(path),
        "statement": statement,
    }


def audit() -> dict[str, object]:
    runner = HERE / "run_l1_control.py"
    cache = HERE / "production_cache.py"
    identity = REPO / "moss_transcribe_diarize/app/live_identity.py"
    provider = REPO / "moss_transcribe_diarize/app/live_provider_bundle.py"
    scorer = REPO / "moss_transcribe_diarize/live_speaker_accuracy.py"
    reason_lines = lines_with(runner, "planned_span.reason")
    if reason_lines != [332, 367, 419]:
        raise RuntimeError(f"span_reason_audit_runner_use_drift:{reason_lines}")
    downstream_reads = {
        repo_path(path): span_reason_reads(path)
        for path in (identity, provider, scorer)
    }
    if any(downstream_reads.values()):
        raise RuntimeError(f"span_reason_scoring_read_detected:{downstream_reads}")
    cache_reason_lines = lines_with(cache, "span_reasons")
    if cache_reason_lines != [291, 313, 324]:
        raise RuntimeError(f"span_reason_audit_cache_use_drift:{cache_reason_lines}")
    test = json.loads(TEST_RESULT.read_text(encoding="utf-8"))
    expected_test = (
        "test_legacy_ingest.LegacyIngestTest."
        "test_span_reason_placeholder_does_not_change_score"
    )
    if test.get("overall") != "PASS" or not any(
        expected_test in name for name in test.get("tests", [])
    ):
        raise RuntimeError("span_reason_equivalence_test_missing")
    return {
        "citations": [
            citation(
                runner,
                "reason=planned_span.reason",
                "The official replay copies the planner reason into FrozenSpan; it does not branch on it.",
            ),
            citation(
                identity,
                "expected_pcm_bytes = span.sample_count",
                "Preparation consumes sample count, PCM, transcript segments, and provider evidence.",
            ),
            citation(
                identity,
                "evidence = self.evidence_provider.score(",
                "Preparation passes the span to the evidence provider without reading its reason.",
            ),
            citation(
                provider,
                "intervals_by_speaker = _speaker_intervals_by_label",
                "Evidence scoring derives intervals from span bounds and transcript segments.",
            ),
            citation(
                provider,
                "duration = span.sample_count",
                "Interval clipping consumes span duration only.",
            ),
            citation(
                runner,
                '"reason": planned_span.reason',
                "The other official runner uses are trace reporting.",
            ),
            citation(
                cache,
                'span_reasons = payload["span_reasons"]',
                "The cache path reads span reasons for validation only.",
            ),
            citation(
                runner,
                "metrics = score_live_speaker_accuracy(reference, final_hypothesis)",
                "Final scoring consumes only reference and hypothesis intervals.",
            ),
        ],
        "downstream_span_reason_reads": downstream_reads,
        "equivalence_test": {
            "path": repo_path(TEST_RESULT),
            "sha256": sha256_file(TEST_RESULT),
            "status": "PASS",
        },
        "input_files": [
            {"path": repo_path(path), "sha256": sha256_file(path)} for path in INPUTS
        ],
        "official_runner_planned_span_reason_lines": reason_lines,
        "overall": "PASS",
        "production_cache_span_reason_lines": cache_reason_lines,
        "schema": "moss-l2-stage0-span-reason-independence-audit.v1",
        "verdict": "span_reasons_feed_validation_and_reporting_only",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()
    result = audit()
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
