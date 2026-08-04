#!/usr/bin/env python3
"""Explain the first H3 divergence without replaying the identity pipeline."""

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
    raise RuntimeError("h3_explain_repo_root_not_found")


HERE = Path(__file__).resolve().parent
REPO = find_repo(HERE)
L2 = REPO / "prototypes/streaming-diarization/l2-stage0"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(L2))

from legacy_ingest import derive_legacy_plan, load_legacy_archive  # noqa: E402
from production_cache import PlannerConfig  # noqa: E402
from moss_transcribe_diarize.app.live_span_bounds import span_segments  # noqa: E402
from moss_transcribe_diarize.live_speaker_accuracy import (  # noqa: E402
    load_reference_speaker_activity_jsonl,
)


ARCHIVE = REPO / "prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/harness_cache.npz"
REFERENCE = REPO / "prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/reference.jsonl"
SPEC = L2 / "l1-control-spec.json"
H3_RESULT = HERE / "h3-policy-v1/result.json"
LEGACY_SOURCE = L2 / "legacy_ingest.py"
RUNNER_SOURCE = L2 / "run_l1_control.py"
SPAN_SOURCE = REPO / "moss_transcribe_diarize/app/live_span_bounds.py"
IDENTITY_SOURCE = REPO / "moss_transcribe_diarize/app/live_identity.py"
EXPECTED_HASHES = {
    "archive": "fd13bacb3ee8397354c0ae55a8b9534db9df56b13dce73c0b956d7cdf3947be5",
    "reference": "28dc9a5b80098db58a261b4bfa73e2975acac31ef36e7e8f057c514d8bdc0759",
    "spec": "883503461c225f3bfe5888abf3b3fbb5a071fc630d7e23abbf2f5ba2756ed735",
    "h3_result": "f28a1bfb3248210f2502600e3ae5bb4ef0abbc45d430740ed94f52338acaa017",
    "legacy_source": "895aeda6870519ee5b577ce3fc0a47b9c8d7eda84d2af77369e8e503ae9c8c91",
    "runner_source": "8719c18a70433b166d563caca72f0075d89cdab2fea74d27cfecac1b168d85d5",
    "span_source": "c9b88404175d8d4ee9ca0c858dd4076a2cd3fb156da89cef2dbe74924e4884f6",
    "identity_source": "b42efca21dc33462c1b1fe46e9884b6500701060c38b036eacb0a6a232bef744",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def require_inputs() -> dict[str, str]:
    paths = {
        "archive": ARCHIVE,
        "reference": REFERENCE,
        "spec": SPEC,
        "h3_result": H3_RESULT,
        "legacy_source": LEGACY_SOURCE,
        "runner_source": RUNNER_SOURCE,
        "span_source": SPAN_SOURCE,
        "identity_source": IDENTITY_SOURCE,
    }
    actual = {name: sha256_file(path) for name, path in paths.items()}
    drift = {
        name: {"expected": EXPECTED_HASHES[name], "actual": actual[name]}
        for name in paths
        if actual[name] != EXPECTED_HASHES[name]
    }
    if drift:
        raise RuntimeError(f"h3_explain_input_hash_drift:{json.dumps(drift, sort_keys=True)}")
    return actual


def run_probe(output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise RuntimeError(f"h3_explain_output_dir_exists:{output_dir}")
    output_dir.mkdir(parents=True)
    input_hashes = require_inputs()
    h3 = json.loads(H3_RESULT.read_text(encoding="utf-8"))
    first = h3["first_live_divergence"]
    unit_index = int(first["unit"]["unit_index"])
    span_id = int(first["unit"]["span_id"])
    config_payload = json.loads(SPEC.read_text(encoding="utf-8"))["production_config"]
    config = PlannerConfig.from_mapping(config_payload)
    reference = load_reference_speaker_activity_jsonl(REFERENCE)
    truth = [(item.start, item.end, item.speaker, "") for item in reference]
    archive = load_legacy_archive(ARCHIVE)
    plan = derive_legacy_plan(
        archive,
        truth,
        total_samples=300 * config.sample_rate,
        config=config,
    )
    planned_span = next(item for item in plan.spans if item.span_id == span_id)
    members = sorted(
        [index for index, unit in enumerate(plan.units) if unit.span_id == span_id],
        key=lambda index: plan.units[index].pieces[0].start,
    )
    label_of = {index: f"S{position + 1:02d}" for position, index in enumerate(members)}
    span_start = planned_span.start_sample / config.sample_rate
    rendered_segments = []
    for index in members:
        for piece in plan.units[index].pieces:
            rendered_segments.append(
                {
                    "absolute_end": piece.end,
                    "absolute_start": piece.start,
                    "formatted_end": f"{piece.end - span_start:.6f}",
                    "formatted_start": f"{piece.start - span_start:.6f}",
                    "label": label_of[index],
                    "relative_end": piece.end - span_start,
                    "relative_start": piece.start - span_start,
                    "unit_index": index,
                }
            )
    rendered_segments.sort(key=lambda item: (item["relative_start"], item["relative_end"]))
    transcript = "".join(
        f"[{item['formatted_start']}][{item['label']}]w[{item['formatted_end']}]"
        for item in rendered_segments
    )
    sample_count = planned_span.end_sample - planned_span.start_sample
    parsed = span_segments(transcript, sample_count=sample_count)
    negative = [item for item in rendered_segments if item["relative_start"] < 0.0]
    if unit_index not in members:
        raise RuntimeError("h3_explain_first_unit_not_in_span")
    if not negative:
        raise RuntimeError("h3_explain_expected_negative_relative_start_missing")
    if parsed:
        raise RuntimeError("h3_explain_expected_empty_parse_missing")
    result = {
        "causal_chain": [
            "legacy duration reconciliation moves the last selected piece start backward by one sample",
            "the enclosing PlannedSpan start remains the rounded archived row minimum",
            "run_l1_control renders a negative relative start into the transcript",
            "parse_transcript accepts no segment from that grammar, so span_segments returns empty",
            "BoundedCausalIdentityPreparer returns failed/unparseable_transcript before evidence or assignment",
        ],
        "divergent_stage": "PRE_ASSIGNMENT_LEGACY_TRANSCRIPT_INGEST",
        "first_unit": first["unit"],
        "input_hashes": input_hashes,
        "mirror_decision": {
            "best_score": first["mirror_span"]["candidates"][0]["scores"][0],
            "runner_up_score": first["mirror_span"]["candidates"][0]["scores"][1],
            "assigned_canonical": first["mirror_span"]["pending"][0]["canonical_id"],
            "abstain": first["mirror_span"]["abstain"],
        },
        "parsed_segment_count": len(parsed),
        "planned_span": {
            "end_sample": planned_span.end_sample,
            "sample_count": sample_count,
            "span_id": span_id,
            "start_sample": planned_span.start_sample,
            "start_seconds": span_start,
        },
        "rendered_segments": rendered_segments,
        "responsible_sources": {
            "duration_reconciliation": "prototypes/streaming-diarization/l2-stage0/legacy_ingest.py:170-199",
            "span_bounds_not_reconciled": "prototypes/streaming-diarization/l2-stage0/legacy_ingest.py:214-223",
            "relative_timestamp_and_render": "prototypes/streaming-diarization/l2-stage0/run_l1_control.py:350-373",
            "empty_parser_result": "moss_transcribe_diarize/app/live_span_bounds.py:37-54",
            "pre_assignment_failure": "moss_transcribe_diarize/app/live_identity.py:101-106",
        },
        "schema": "moss-l2-stage0-instrument-h3-first-divergence.v1",
        "transcript": transcript,
        "verdict": "IDENTIFIED_PRE_ASSIGNMENT_LEGACY_TRANSCRIPT_INGEST",
    }
    result_path = output_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    transcript_path = output_dir / "transcript.txt"
    transcript_path.write_text(
        "\n".join(
            [
                "H3 first-divergence causal proof",
                f"unit={unit_index} span={span_id}",
                f"planned_span_start_sample={planned_span.start_sample}",
                f"minimum_relative_start={min(item['relative_start'] for item in rendered_segments):.9f}",
                f"rendered_transcript={transcript}",
                f"parsed_segment_count={len(parsed)}",
                "divergence=PRE_ASSIGNMENT_LEGACY_TRANSCRIPT_INGEST",
                "VERDICT IDENTIFIED_PRE_ASSIGNMENT_LEGACY_TRANSCRIPT_INGEST",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = output_dir / "H3_FIRST_DIVERGENCE_EVIDENCE.sha256"
    manifest_inputs = [
        Path(__file__).resolve(),
        ARCHIVE,
        REFERENCE,
        SPEC,
        H3_RESULT,
        LEGACY_SOURCE,
        RUNNER_SOURCE,
        SPAN_SOURCE,
        IDENTITY_SOURCE,
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
        **{key: value for key, value in result.items() if key != "rendered_segments"},
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
