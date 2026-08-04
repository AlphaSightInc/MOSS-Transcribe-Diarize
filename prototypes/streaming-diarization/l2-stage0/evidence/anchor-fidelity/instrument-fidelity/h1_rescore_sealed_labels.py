#!/usr/bin/env python3
"""H1: re-score sealed final labels without replaying the identity pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def find_repo(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "moss_transcribe_diarize").is_dir():
            return candidate
    raise RuntimeError("h1_repo_root_not_found")


HERE = Path(__file__).resolve().parent
REPO = find_repo(HERE)
L2 = REPO / "prototypes/streaming-diarization/l2-stage0"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(L2))

from legacy_ingest import derive_legacy_plan, load_legacy_archive  # noqa: E402
from production_cache import PlannerConfig  # noqa: E402
from moss_transcribe_diarize.live_speaker_accuracy import (  # noqa: E402
    SpeakerActivityInterval,
    load_reference_speaker_activity_jsonl,
    score_live_speaker_accuracy,
)


SEALED_RUN = (
    L2 / "evidence/anchor-fidelity/legacy-measurement-v2/legacy-anchor-run1.json"
)
ARCHIVE = (
    REPO
    / "prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/harness_cache.npz"
)
REFERENCE = (
    REPO
    / "prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/reference.jsonl"
)
SPEC = L2 / "l1-control-spec.json"
SCORER = REPO / "moss_transcribe_diarize/live_speaker_accuracy.py"
EXPECTED = {
    "archive": "fd13bacb3ee8397354c0ae55a8b9534db9df56b13dce73c0b956d7cdf3947be5",
    "reference": "28dc9a5b80098db58a261b4bfa73e2975acac31ef36e7e8f057c514d8bdc0759",
    "run": "d1076d21735de792111f4ce957e9593ebabf98e10d43eb1ae4b0c967d92536a5",
    "scorer": "10be298132e82148cfca520404ca42b6fb8c7bd5a56a2322000ca0ebe8dec469",
}
ANCHOR = 0.9135
TOLERANCE = 0.001


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def semantic_sha256(payload: object) -> str:
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, payload: object) -> str:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sha256_file(path)


def assert_inputs() -> dict[str, str]:
    paths = {
        "archive": ARCHIVE,
        "reference": REFERENCE,
        "run": SEALED_RUN,
        "scorer": SCORER,
    }
    actual = {name: sha256_file(path) for name, path in paths.items()}
    drift = {
        name: {"actual": actual[name], "expected": EXPECTED[name]}
        for name in paths
        if actual[name] != EXPECTED[name]
    }
    if drift:
        raise RuntimeError(f"h1_input_hash_drift:{json.dumps(drift, sort_keys=True)}")
    return actual


def run_probe(output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise RuntimeError(f"h1_output_dir_exists:{output_dir}")
    output_dir.mkdir(parents=True)
    input_hashes = assert_inputs()
    sealed = json.loads(SEALED_RUN.read_text(encoding="utf-8"))
    labels = sealed["result"]["final_unit_labels"]
    sealed_metrics = sealed["result"]["metrics"]
    config_payload = json.loads(SPEC.read_text(encoding="utf-8"))["production_config"]
    config = PlannerConfig.from_mapping(config_payload)
    reference = load_reference_speaker_activity_jsonl(REFERENCE)
    truth = [(item.start, item.end, item.speaker, "") for item in reference]
    archive = load_legacy_archive(ARCHIVE)
    plan = derive_legacy_plan(
        archive,
        truth,
        total_samples=int(round(300.0 * config.sample_rate)),
        config=config,
    )
    if len(labels) != len(plan.units):
        raise RuntimeError(f"h1_label_unit_count_mismatch:{len(labels)}:{len(plan.units)}")
    hypothesis = tuple(
        SpeakerActivityInterval(piece.start, piece.end, label)
        for unit, label in zip(plan.units, labels, strict=True)
        if label is not None
        for piece in unit.pieces
    )
    rescored = score_live_speaker_accuracy(reference, hypothesis)
    matches_sealed = rescored == sealed_metrics
    if not matches_sealed:
        raise RuntimeError("h1_rescore_does_not_match_sealed_metrics")
    delta = abs(float(rescored["speaker_accuracy"]) - ANCHOR)
    identifies_scorer = delta <= TOLERANCE
    result = {
        "anchor": ANCHOR,
        "anchor_absolute_delta": round(delta, 9),
        "anchor_tolerance": TOLERANCE,
        "final_label_count": len(labels),
        "final_labels_semantic_sha256": semantic_sha256(labels),
        "h1_identifies_divergence": identifies_scorer,
        "hypothesis": "H1_SCORER_DEFINITION",
        "hypothesis_interval_count": len(hypothesis),
        "input_hashes": input_hashes,
        "next_hypothesis": None if identifies_scorer else "H2_IDENTITY_CONSTANTS",
        "overall": "PASS",
        "rescored_metrics": rescored,
        "schema": "moss-l2-stage0-instrument-h1.v1",
        "scorer_call": "moss_transcribe_diarize.live_speaker_accuracy.score_live_speaker_accuracy",
        "scorer_source_line": 148,
        "sealed_metrics_exact_match": matches_sealed,
        "sealed_run_path": repo_path(SEALED_RUN),
        "verdict": "IDENTIFIED_SCORER" if identifies_scorer else "H1_REFUTED",
    }
    result_path = output_dir / "result.json"
    write_json(result_path, result)
    transcript_path = output_dir / "transcript.txt"
    transcript_path.write_text(
        "\n".join(
            [
                "H1 scorer-definition differential",
                f"sealed_run_sha256={input_hashes['run']}",
                f"final_labels_sha256={result['final_labels_semantic_sha256']}",
                f"scorer={result['scorer_call']}:{result['scorer_source_line']}",
                f"sealed_metrics_exact_match={matches_sealed}",
                f"rescored_accuracy={rescored['speaker_accuracy']:.6f}",
                f"anchor={ANCHOR:.6f} tolerance={TOLERANCE:.6f} delta={delta:.6f}",
                f"VERDICT {result['verdict']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = output_dir / "H1_SCORER_EVIDENCE.sha256"
    manifest_inputs = [
        Path(__file__).resolve(),
        SEALED_RUN,
        ARCHIVE,
        REFERENCE,
        SPEC,
        SCORER,
        result_path,
        transcript_path,
    ]
    manifest_path.write_text(
        "\n".join(
            f"{sha256_file(path)}  {repo_path(path)}" for path in sorted(manifest_inputs)
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        **result,
        "evidence_manifest_path": repo_path(manifest_path),
        "evidence_manifest_sha256": sha256_file(manifest_path),
        "result_path": repo_path(result_path),
        "result_sha256": sha256_file(result_path),
        "transcript_path": repo_path(transcript_path),
        "transcript_sha256": sha256_file(transcript_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run_probe(args.output_dir)
    except Exception as exc:
        print(f"BLOCKED {exc.__class__.__name__}:{exc}")
        print("<promise>BLOCKED</promise>")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
