#!/usr/bin/env python3
"""Run the unmodified c650-era L1 runner on the exact superseded alphabet cache."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUNNER = HERE / "run_l1_control.py"
OFFICIAL_CORPUS = HERE / "corpus-manifest.json"
OFFICIAL_SPEC = HERE / "l1-control-spec.json"
MODEL = HERE / "model-manifest.json"
CANDIDATE = HERE / "candidate-config.json"
CONTRACT = REPO / "scripts/ralph-l2-afk/contract.json"
ARCHIVED_CACHE = (
    REPO
    / "prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/harness_cache.npz"
)
CASE_ID = "5m-acquired-alphabet"
EXPECTED_RUNNER_SHA256 = "8719c18a70433b166d563caca72f0075d89cdab2fea74d27cfecac1b168d85d5"
EXPECTED_ARCHIVED_CACHE_SHA256 = "fd13bacb3ee8397354c0ae55a8b9534db9df56b13dce73c0b956d7cdf3947be5"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sha256_file(path)


def repo_path(path: Path) -> str:
    return path.resolve().relative_to(REPO.resolve()).as_posix()


def assert_clean_inputs() -> dict[str, str]:
    runner_hash = sha256_file(RUNNER)
    if runner_hash != EXPECTED_RUNNER_SHA256:
        raise RuntimeError(
            f"anchor_runner_hash_mismatch:expected={EXPECTED_RUNNER_SHA256}:actual={runner_hash}"
        )
    cache_hash = sha256_file(ARCHIVED_CACHE)
    if cache_hash != EXPECTED_ARCHIVED_CACHE_SHA256:
        raise RuntimeError(
            f"anchor_cache_hash_mismatch:expected={EXPECTED_ARCHIVED_CACHE_SHA256}:actual={cache_hash}"
        )
    status = subprocess.run(
        ["git", "-C", str(REPO), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout:
        raise RuntimeError("anchor_worktree_dirty:" + status.stdout.replace("\n", "|"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    official_spec = json.loads(OFFICIAL_SPEC.read_text(encoding="utf-8"))
    official_corpus_hash = sha256_file(OFFICIAL_CORPUS)
    if contract["corpus_manifest_hash"] != official_corpus_hash:
        raise RuntimeError("anchor_official_launcher_pin_drift")
    if official_spec["corpus_manifest_sha256"] != official_corpus_hash:
        raise RuntimeError("anchor_official_l1_pin_drift")
    return {
        "archived_cache_sha256": cache_hash,
        "official_corpus_manifest_sha256": official_corpus_hash,
        "official_l1_spec_sha256": sha256_file(OFFICIAL_SPEC),
        "runner_sha256": runner_hash,
    }


def diagnosis_inputs(output_dir: Path) -> tuple[Path, Path, dict[str, str]]:
    corpus = json.loads(OFFICIAL_CORPUS.read_text(encoding="utf-8"))
    case = next(item for item in corpus["cases"] if item["case_id"] == CASE_ID)
    case["vector_cache_path"] = repo_path(ARCHIVED_CACHE)
    case["vector_cache_sha256"] = EXPECTED_ARCHIVED_CACHE_SHA256
    case["vector_cache_version"] = "superseded-a1-92-unit-anchor"
    corpus_path = output_dir / "diagnosis-corpus-manifest.json"
    corpus_hash = write_json(corpus_path, corpus)

    spec = json.loads(OFFICIAL_SPEC.read_text(encoding="utf-8"))
    spec["case_ids"] = [CASE_ID]
    spec["corpus_manifest_sha256"] = corpus_hash
    spec["expected_case_count"] = 1
    spec_path = output_dir / "diagnosis-l1-control-spec.json"
    spec_hash = write_json(spec_path, spec)
    return corpus_path, spec_path, {
        "diagnosis_corpus_manifest_sha256": corpus_hash,
        "diagnosis_l1_spec_sha256": spec_hash,
    }


def run_probe(output_dir: Path) -> tuple[int, dict[str, Any]]:
    pins = assert_clean_inputs()
    output_dir.mkdir(parents=True, exist_ok=False)
    corpus_path, spec_path, diagnosis_hashes = diagnosis_inputs(output_dir)
    summary_path = output_dir / "summary.json"
    runner_transcript_path = output_dir / "runner-transcript.txt"
    command = [
        sys.executable,
        str(RUNNER),
        "--corpus-manifest",
        str(corpus_path),
        "--candidate-config",
        str(CANDIDATE),
        "--model-manifest",
        str(MODEL),
        "--spec",
        str(spec_path),
        "--case-id",
        CASE_ID,
        "--evidence-dir",
        str(output_dir / "runs"),
        "--json-output",
        str(summary_path),
        "--transcript-output",
        str(output_dir / "measurement-transcript.txt"),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    transcript = (
        "COMMAND " + " ".join(command) + "\n"
        + f"EXIT {completed.returncode}\n"
        + "STDOUT\n" + completed.stdout
        + "STDERR\n" + completed.stderr
    )
    runner_transcript_path.write_text(transcript, encoding="utf-8")
    summary = (
        json.loads(summary_path.read_text(encoding="utf-8"))
        if summary_path.is_file()
        else None
    )
    result: dict[str, Any] = {
        **pins,
        **diagnosis_hashes,
        "case_id": CASE_ID,
        "command": command,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "official_pins_modified": False,
        "runner_exit_code": completed.returncode,
        "runner_summary_created": summary is not None,
        "runner_transcript_path": repo_path(runner_transcript_path),
        "runner_transcript_sha256": sha256_file(runner_transcript_path),
        "schema": "moss-l2-stage0-anchor-fidelity-probe.v1",
    }
    if summary is None:
        result.update(
            {
                "error": "anchor_runner_produced_no_score",
                "overall": "BLOCKED",
                "runs_completed": 0,
            }
        )
        status = 2
    else:
        gate = summary["accepted_alphabet_gate"]
        result.update(
            {
                "accepted_alphabet_gate": gate,
                "overall": "PASS" if gate["passed"] and summary["overall"] == "PASS" else "BLOCKED",
                "runs_completed": len(summary["cases"][0]["runs"]),
                "summary_path": repo_path(summary_path),
                "summary_sha256": sha256_file(summary_path),
            }
        )
        status = 0 if result["overall"] == "PASS" else 2
    write_json(output_dir / "probe-result.json", result)
    return status, result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        status, result = run_probe(args.output_dir)
    except Exception as exc:
        print(f"BLOCKED {exc.__class__.__name__}:{exc}")
        print("<promise>BLOCKED</promise>")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    if status:
        print("<promise>BLOCKED</promise>")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
