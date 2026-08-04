#!/usr/bin/env python3
"""H3: trace the existing live-policy mirror and diff it against sealed L1 labels."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path
import sys
from types import FrameType
from typing import Any

import numpy as np


def find_repo(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "moss_transcribe_diarize").is_dir():
            return candidate
    raise RuntimeError("h3_repo_root_not_found")


HERE = Path(__file__).resolve().parent
REPO = find_repo(HERE)
PROTO = REPO / "prototypes/streaming-diarization"
L2 = PROTO / "l2-stage0"
sys.path.insert(0, str(PROTO))

import proto_ab_identity as mirror  # noqa: E402


ARCHIVE = PROTO / "data/real/benchmark_5m/acquired_alphabet/harness_cache.npz"
SEALED_RUN = L2 / "evidence/anchor-fidelity/legacy-measurement-v2/legacy-anchor-run1.json"
MIRROR_SOURCE = PROTO / "proto_ab_identity.py"
RUNNER_SOURCE = L2 / "run_l1_control.py"
IDENTITY_SOURCE = REPO / "moss_transcribe_diarize/app/live_identity.py"
ALBUM_SOURCE = REPO / "moss_transcribe_diarize/app/live_identity_album.py"
EXPECTED_HASHES = {
    "archive": "fd13bacb3ee8397354c0ae55a8b9534db9df56b13dce73c0b956d7cdf3947be5",
    "sealed_run": "d1076d21735de792111f4ce957e9593ebabf98e10d43eb1ae4b0c967d92536a5",
    "mirror_source": "e4e8305ca16fba361e0bd53bdaf0b7e973f3bb45ce6be78b536df2219ffe1791",
    "runner_source": "8719c18a70433b166d563caca72f0075d89cdab2fea74d27cfecac1b168d85d5",
    "identity_source": "b42efca21dc33462c1b1fe46e9884b6500701060c38b036eacb0a6a232bef744",
    "album_source": "760f87bb306f06ae0fc26c14c77a97fc24466d70304a09156d92c3be12f06bf9",
}
PARAMETERS = {
    "admission": 2.0,
    "birth_floor": 1.0,
    "margin": 0.1,
    "merge_thr": 0.7,
    "min_score": 0.35,
    "policy": "album",
    "sweep": True,
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_inputs() -> dict[str, str]:
    paths = {
        "archive": ARCHIVE,
        "sealed_run": SEALED_RUN,
        "mirror_source": MIRROR_SOURCE,
        "runner_source": RUNNER_SOURCE,
        "identity_source": IDENTITY_SOURCE,
        "album_source": ALBUM_SOURCE,
    }
    actual = {name: sha256_file(path) for name, path in paths.items()}
    drift = {
        name: {"expected": EXPECTED_HASHES[name], "actual": actual[name]}
        for name in paths
        if actual[name] != EXPECTED_HASHES[name]
    }
    if drift:
        raise RuntimeError(f"h3_input_hash_drift:{json.dumps(drift, sort_keys=True)}")
    return actual


def line_of(fragment: str) -> int:
    lines, start = inspect.getsourcelines(mirror.simulate)
    matches = [start + offset for offset, line in enumerate(lines) if fragment in line]
    if len(matches) != 1:
        raise RuntimeError(f"h3_mirror_trace_line_ambiguous:{fragment}:{matches}")
    return matches[0]


def native(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, tuple):
        return [native(item) for item in value]
    if isinstance(value, list):
        return [native(item) for item in value]
    if isinstance(value, dict):
        return {str(key): native(item) for key, item in value.items()}
    return value


def trace_mirror(cache: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, list[object], float, list[dict[str, object]]]:
    trace_lines = {
        "span_start": line_of("elig.sort(key="),
        "candidate": line_of("if best is not None and s[best] >= min_score:"),
        "outcome": line_of("if abstain:"),
        "committed": line_of("# retrospective sweep (B)"),
    }
    events: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    def tracer(frame: FrameType, event: str, arg: object):
        nonlocal current
        if frame.f_code is not mirror.simulate.__code__ or event != "line":
            return tracer
        local = frame.f_locals
        if frame.f_lineno == trace_lines["span_start"]:
            current = {
                "span_id": int(local["span"]),
                "unit_ids": [int(item) for item in local["unit_ids"]],
                "candidates": [],
                "assigned_before": native(local["assigned"].copy()),
            }
            events.append(current)
        elif frame.f_lineno == trace_lines["candidate"] and current is not None:
            current["candidates"].append(
                {
                    "unit_index": int(local["u"]),
                    "canonical_ids": [int(item) for item in local["cids"]],
                    "open_indexes": [int(item) for item in local["open_idx"]],
                    "best_index": None if local["best"] is None else int(local["best"]),
                    "scores": [round(float(item), 9) for item in local["s"]],
                }
            )
        elif frame.f_lineno == trace_lines["outcome"] and current is not None:
            current["abstain"] = bool(local["abstain"])
            current["eligible_units"] = [int(item) for item in local["elig"]]
            current["pending"] = [
                {"unit_index": int(unit), "canonical_id": int(canonical)}
                for unit, canonical, _vector in local["pending"]
            ]
            if local["abstain"]:
                current["assigned_after"] = native(local["assigned"].copy())
        elif frame.f_lineno == trace_lines["committed"] and current is not None:
            current["assigned_after"] = native(local["assigned"].copy())
        return tracer

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        live, final, sweep_log, sweep_cost = mirror.simulate(cache, **PARAMETERS)
    finally:
        sys.settrace(previous)
    return live, final, sweep_log, sweep_cost, events


def canonical_number(label: str | None) -> int:
    if label is None:
        return -1
    prefix = "speaker-"
    if not label.startswith(prefix) or not label[len(prefix):].isdigit():
        raise RuntimeError(f"h3_runner_label_schema_surprise:{label}")
    return int(label[len(prefix):]) - 1


def run_probe(output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise RuntimeError(f"h3_output_dir_exists:{output_dir}")
    output_dir.mkdir(parents=True)
    input_hashes = require_inputs()
    with np.load(ARCHIVE, allow_pickle=False) as payload:
        cache = {name: payload[name].copy() for name in ("rows", "vec_idx", "vecs")}
    sealed = json.loads(SEALED_RUN.read_text(encoding="utf-8"))["result"]
    mirror_live, mirror_final, sweep_log, sweep_cost, mirror_trace = trace_mirror(cache)
    runner_live = np.asarray([canonical_number(item) for item in sealed["live_unit_labels"]])
    runner_final = np.asarray([canonical_number(item) for item in sealed["final_unit_labels"]])
    if not (len(runner_live) == len(runner_final) == len(mirror_live) == len(cache["rows"])):
        raise RuntimeError("h3_unit_count_mismatch")
    unit_trace = []
    for index, row in enumerate(cache["rows"]):
        unit_trace.append(
            {
                "duration_seconds": round(float(row[4]), 9),
                "eligible": bool(row[5]),
                "end_seconds": round(float(row[3]), 9),
                "final_match": int(runner_final[index]) == int(mirror_final[index]),
                "live_match": int(runner_live[index]) == int(mirror_live[index]),
                "mirror_final": int(mirror_final[index]),
                "mirror_live": int(mirror_live[index]),
                "runner_final": int(runner_final[index]),
                "runner_live": int(runner_live[index]),
                "span_id": int(row[0]),
                "start_seconds": round(float(row[2]), 9),
                "true_speaker": int(row[1]),
                "unit_index": index,
            }
        )
    first_live = next((item for item in unit_trace if not item["live_match"]), None)
    first_final = next((item for item in unit_trace if not item["final_match"]), None)
    span_by_id = {int(item["span_id"]): item for item in sealed["span_trace"]}
    mirror_span_by_id = {int(item["span_id"]): item for item in mirror_trace}
    first_context = None
    if first_live is not None:
        span_id = int(first_live["span_id"])
        first_context = {
            "runner_span": span_by_id[span_id],
            "mirror_span": mirror_span_by_id[span_id],
            "unit": first_live,
        }
    verdict = "IDENTIFIED_ASSIGNMENT_ABSTENTION_BIRTH_POLICY" if first_live else "H3_REFUTED"
    result = {
        "first_final_divergence": first_final,
        "first_live_divergence": first_context,
        "hypothesis": "H3_ASSIGNMENT_ABSTENTION_BIRTH_POLICY",
        "input_hashes": input_hashes,
        "mirror_final_accuracy": round(float(mirror.accuracy(cache["rows"], mirror_final)), 9),
        "mirror_final_canonical_count": len({int(item) for item in mirror_final if item >= 0}),
        "mirror_invocation": PARAMETERS,
        "mirror_live_accuracy": round(float(mirror.accuracy(cache["rows"], mirror_live)), 9),
        "mirror_live_canonical_count": len({int(item) for item in mirror_live if item >= 0}),
        "mirror_policy_sources": {
            "assignment_order_and_gates": "prototypes/streaming-diarization/proto_ab_identity.py:299-339",
            "production_assignment": "moss_transcribe_diarize/app/live_identity.py:297-355",
            "production_birth": "moss_transcribe_diarize/app/live_identity.py:127-140",
            "production_birth_floor": "moss_transcribe_diarize/app/live_provider_bundle.py:633-669",
        },
        "mirror_sweep_count": len(sweep_log),
        "mirror_sweep_cost_seconds": round(float(sweep_cost), 9),
        "next_hypothesis": None if first_live else "H4_SWEEP_INVOCATION_CONFIG",
        "overall": "PASS",
        "runner_final_accuracy": sealed["metrics"]["speaker_accuracy"],
        "runner_final_canonical_count": sealed["counts"]["final_canonical_speakers"],
        "runner_live_accuracy": sealed["live_metrics"]["speaker_accuracy"],
        "runner_live_canonical_count": sealed["counts"]["live_canonical_speakers"],
        "schema": "moss-l2-stage0-instrument-h3.v1",
        "stage_comparison": "causal live labels before any retrospective sweep",
        "unit_trace": unit_trace,
        "verdict": verdict,
    }
    result_path = output_dir / "result.json"
    write_json(result_path, result)
    transcript_path = output_dir / "transcript.txt"
    lines = [
        "H3 assignment/abstention/birth policy differential",
        f"mirror_live_accuracy={result['mirror_live_accuracy']:.9f}",
        f"runner_live_accuracy={result['runner_live_accuracy']:.9f}",
        f"mirror_final_accuracy={result['mirror_final_accuracy']:.9f}",
        f"runner_final_accuracy={result['runner_final_accuracy']:.9f}",
        f"first_live_divergence={json.dumps(first_context, sort_keys=True)}",
        f"VERDICT {verdict}",
    ]
    transcript_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest_path = output_dir / "H3_POLICY_EVIDENCE.sha256"
    manifest_inputs = [
        Path(__file__).resolve(),
        ARCHIVE,
        SEALED_RUN,
        MIRROR_SOURCE,
        RUNNER_SOURCE,
        IDENTITY_SOURCE,
        ALBUM_SOURCE,
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
        **{name: value for name, value in result.items() if name != "unit_trace"},
        "evidence_manifest_path": repo_path(manifest_path),
        "evidence_manifest_sha256": sha256_file(manifest_path),
        "result_path": repo_path(result_path),
        "result_sha256": sha256_file(result_path),
        "transcript_path": repo_path(transcript_path),
        "transcript_sha256": sha256_file(transcript_path),
        "unit_count": len(unit_trace),
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
