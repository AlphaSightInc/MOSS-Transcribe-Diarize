#!/usr/bin/env python3
"""H2: compare the L1 runner constants with the sealed deployed contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def find_repo(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "moss_transcribe_diarize").is_dir():
            return candidate
    raise RuntimeError("h2_repo_root_not_found")


HERE = Path(__file__).resolve().parent
REPO = find_repo(HERE)
L2 = REPO / "prototypes/streaming-diarization/l2-stage0"
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.live_service_runtime import hash_config  # noqa: E402


SPEC = L2 / "l1-control-spec.json"
RUNNER = L2 / "run_l1_control.py"
ALBUM_SOURCE = REPO / "moss_transcribe_diarize/app/live_identity_album.py"
HASH_SOURCE = REPO / "moss_transcribe_diarize/app/live_service_runtime.py"
DEPLOY_TRANSCRIPT = Path(
    "/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/"
    "evidence/f4b-remediation-20260803/deploy/server-finalize.txt"
)
EXPECTED_HASHES = {
    "spec": "883503461c225f3bfe5888abf3b3fbb5a071fc630d7e23abbf2f5ba2756ed735",
    "runner": "8719c18a70433b166d563caca72f0075d89cdab2fea74d27cfecac1b168d85d5",
    "album_source": "760f87bb306f06ae0fc26c14c77a97fc24466d70304a09156d92c3be12f06bf9",
    "hash_source": "225c7298fe4203777421a5d506ab8fada0d56fead4e75435d505cd4cf322eb8c",
    "deploy_transcript": "72e8b4d67dc5e74c2b9605cfd063906a7a7d6a72233b404f335265f40e8e379e",
}
EXPECTED_SOURCE_REVISION = "9089b33210401111865da7abc160ab0bcb4aa266"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO).as_posix()
    except ValueError:
        return resolved.as_posix()


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_pinned_inputs() -> dict[str, str]:
    paths = {
        "spec": SPEC,
        "runner": RUNNER,
        "album_source": ALBUM_SOURCE,
        "hash_source": HASH_SOURCE,
        "deploy_transcript": DEPLOY_TRANSCRIPT,
    }
    actual = {name: sha256_file(path) for name, path in paths.items()}
    drift = {
        name: {"expected": EXPECTED_HASHES[name], "actual": actual[name]}
        for name in paths
        if actual[name] != EXPECTED_HASHES[name]
    }
    if drift:
        raise RuntimeError(f"h2_input_hash_drift:{json.dumps(drift, sort_keys=True)}")
    return actual


def parse_deployed() -> dict[str, object]:
    text = DEPLOY_TRANSCRIPT.read_text(encoding="utf-8")
    evidence: dict[str, str] = {}
    for name in (
        "hard_cap_samples",
        "identity_max_speakers",
        "identity_min_match_score",
        "identity_min_match_margin",
        "identity_album_admission_seconds",
        "identity_birth_min_seconds",
        "source_revision",
    ):
        values = re.findall(rf"^evidence: {re.escape(name)}=(.+)$", text, re.MULTILINE)
        if not values:
            raise RuntimeError(f"h2_deployed_field_missing:{name}")
        if len(set(values)) != 1:
            raise RuntimeError(f"h2_deployed_field_ambiguous:{name}:{values}")
        evidence[name] = values[0]
    descriptor_lines = [line for line in text.splitlines() if line.startswith('{"descriptor":')]
    if len(descriptor_lines) != 1:
        raise RuntimeError(f"h2_deployed_descriptor_count:{len(descriptor_lines)}")
    descriptor = json.loads(descriptor_lines[0])["descriptor"]
    if descriptor["source_revision"] != evidence["source_revision"]:
        raise RuntimeError("h2_deployed_source_revision_disagrees")
    if descriptor["bounds"]["hard_cap_samples"] != int(evidence["hard_cap_samples"]):
        raise RuntimeError("h2_deployed_hard_cap_disagrees")
    return {
        "album_admission_seconds": float(evidence["identity_album_admission_seconds"]),
        "album_birth_min_seconds": float(evidence["identity_birth_min_seconds"]),
        "hard_cap_samples": int(evidence["hard_cap_samples"]),
        "identity_config_hash": descriptor["config_hashes"]["identity_config_hash"],
        "max_speakers": int(evidence["identity_max_speakers"]),
        "min_match_margin": float(evidence["identity_min_match_margin"]),
        "min_match_score": float(evidence["identity_min_match_score"]),
        "source_revision": descriptor["source_revision"],
    }


def run_probe(output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise RuntimeError(f"h2_output_dir_exists:{output_dir}")
    output_dir.mkdir(parents=True)
    input_hashes = require_pinned_inputs()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    runner = spec["production_config"]
    deployed = parse_deployed()
    runner_identity_payload = {
        "max_speakers": int(runner["max_speakers"]),
        "min_match_score": float(runner["min_match_score"]),
        "min_match_margin": float(runner["min_match_margin"]),
    }
    runner_values: dict[str, object] = {
        "album_admission_seconds": float(runner["album_admission_seconds"]),
        "album_birth_min_seconds": float(runner["album_birth_min_seconds"]),
        "hard_cap_samples": int(runner["hard_cap_samples"]),
        "identity_config_hash": hash_config(runner_identity_payload),
        **runner_identity_payload,
        "source_revision": EXPECTED_SOURCE_REVISION,
    }
    fields = (
        "min_match_score",
        "min_match_margin",
        "album_admission_seconds",
        "album_birth_min_seconds",
        "hard_cap_samples",
        "max_speakers",
        "identity_config_hash",
        "source_revision",
    )
    comparison = [
        {
            "field": field,
            "runner": runner_values[field],
            "deployed": deployed[field],
            "match": runner_values[field] == deployed[field],
        }
        for field in fields
    ]
    mismatches = [row for row in comparison if not row["match"]]
    verdict = "IDENTIFIED_IDENTITY_CONSTANTS" if mismatches else "H2_REFUTED"
    result = {
        "comparison": comparison,
        "deployed_evidence": {
            "path": display_path(DEPLOY_TRANSCRIPT),
            "sha256": input_hashes["deploy_transcript"],
            "value_lines": "server-finalize.txt:19,27-31,72,83",
        },
        "hypothesis": "H2_IDENTITY_CONSTANTS",
        "identity_hash_call": "moss_transcribe_diarize.app.live_service_runtime.hash_config",
        "input_hashes": input_hashes,
        "mismatch_count": len(mismatches),
        "next_hypothesis": None if mismatches else "H3_ASSIGNMENT_ABSTENTION_BIRTH_POLICY",
        "overall": "PASS",
        "runner_identity_payload": runner_identity_payload,
        "runner_sources": {
            "album_constants": "moss_transcribe_diarize/app/live_identity_album.py:45-57",
            "config_assertions": "prototypes/streaming-diarization/l2-stage0/run_l1_control.py:563-588",
            "config_wiring": "prototypes/streaming-diarization/l2-stage0/run_l1_control.py:247-260",
            "identity_hash": "moss_transcribe_diarize/app/live_service_runtime.py:946-948",
        },
        "schema": "moss-l2-stage0-instrument-h2.v1",
        "verdict": verdict,
    }
    result_path = output_dir / "result.json"
    write_json(result_path, result)
    transcript_path = output_dir / "transcript.txt"
    rows = [
        "H2 identity-constants differential",
        "field | runner | deployed | match",
        *(
            f"{row['field']} | {row['runner']} | {row['deployed']} | {row['match']}"
            for row in comparison
        ),
        f"mismatch_count={len(mismatches)}",
        f"VERDICT {verdict}",
    ]
    transcript_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    manifest_path = output_dir / "H2_CONSTANTS_EVIDENCE.sha256"
    manifest_inputs = [
        Path(__file__).resolve(),
        SPEC,
        RUNNER,
        ALBUM_SOURCE,
        HASH_SOURCE,
        DEPLOY_TRANSCRIPT,
        result_path,
        transcript_path,
    ]
    manifest_path.write_text(
        "\n".join(
            f"{sha256_file(path)}  {display_path(path)}" for path in sorted(manifest_inputs)
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        **result,
        "evidence_manifest_path": display_path(manifest_path),
        "evidence_manifest_sha256": sha256_file(manifest_path),
        "result_path": display_path(result_path),
        "result_sha256": sha256_file(result_path),
        "transcript_path": display_path(transcript_path),
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
