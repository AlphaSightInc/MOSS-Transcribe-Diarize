#!/usr/bin/env python3
"""PROTOTYPE: score a calibrated microphone-gain sweep without double-counting words.

Question: at the attended 15.377 dB disparity, does a gain region reduce the minimum
edit distance to any order-preserving interleaving of both lane references, and does it
replicate on three held-out different-speech pairs?

One command:

  .venv/bin/python prototypes/lane-balance/proto_lane_balance_v3.py \
    --output evidence/phase1/g3-attended/lane-balance-v3.json

Every candidate prints its complete transcript, alignment trace, audio state, and timing.
The output is diagnostic evidence only; it cannot select a production policy.
"""
from __future__ import annotations

import argparse
import array
import contextlib
import hashlib
import json
import math
import os
import statistics
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any
from urllib.request import urlopen


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from moss_transcribe_diarize.app.vllm_runner import VllmRunner  # noqa: E402
from moss_transcribe_diarize.speaker_reference import normalize_reference_text  # noqa: E402


PREREGISTRATION = Path(__file__).with_name("preregistration-v3.json")
DEFAULT_BASE_URL = "http://127.0.0.1:18000/v1"
HEADROOM = 10 ** (-6 / 20)
LIMIT = 0.98
LIMIT_RANGE = 0.02


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("MOSS_VLLM_BASE_URL", DEFAULT_BASE_URL),
        help="OpenAI-compatible vLLM /v1 endpoint (default: tunnel on 127.0.0.1:18000).",
    )
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=REPO,
        help="Checkout containing the ignored WAV fixtures.",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_pcm(path: Path, seconds: int) -> tuple[list[float], int]:
    with contextlib.closing(wave.open(str(path))) as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getcomptype() != "NONE":
            raise RuntimeError(f"expected_mono_pcm16:{path}")
        sample_rate = source.getframerate()
        raw = source.readframes(sample_rate * seconds)
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    if len(samples) != sample_rate * seconds:
        raise RuntimeError(f"short_clip:{path}:{len(samples)}:{sample_rate * seconds}")
    return [sample / 32768.0 for sample in samples], sample_rate


def write_pcm(path: Path, samples: list[float], sample_rate: int) -> None:
    encoded = array.array(
        "h", (int(max(-1.0, min(1.0, sample)) * 32767) for sample in samples)
    )
    if sys.byteorder != "little":
        encoded.byteswap()
    with contextlib.closing(wave.open(str(path), "w")) as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(encoded.tobytes())


def rms(samples: list[float]) -> float:
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples)) if samples else 0.0


def dbfs(value: float) -> float:
    return 20 * math.log10(value) if value > 0 else float("-inf")


def mix(system: list[float], microphone: list[float]) -> tuple[list[float], int]:
    """Faithful sample transform from ``LiveCompatibilityMixer``."""
    if len(system) != len(microphone):
        raise RuntimeError("aligned_track_length_mismatch")
    output: list[float] = []
    limited_samples = 0
    for system_sample, microphone_sample in zip(system, microphone):
        value = (system_sample * HEADROOM) + (microphone_sample * HEADROOM)
        if abs(value) > LIMIT:
            limited_samples += 1
            value = math.copysign(
                LIMIT + LIMIT_RANGE * math.tanh((abs(value) - LIMIT) / LIMIT_RANGE),
                value,
            )
        output.append(max(-1.0, min(1.0, value)))
    return output, limited_samples


def words(text: str) -> list[str]:
    return normalize_reference_text(text).split()


def true_lcs_matches(reference: list[str], hypothesis: list[str]) -> int:
    """Exact dynamic-programming LCS length; no SequenceMatcher heuristics."""
    previous = [0] * (len(hypothesis) + 1)
    for reference_token in reference:
        current = [0]
        for hypothesis_index, hypothesis_token in enumerate(hypothesis, 1):
            if reference_token == hypothesis_token:
                current.append(previous[hypothesis_index - 1] + 1)
            else:
                current.append(max(previous[hypothesis_index], current[-1]))
        previous = current
    return previous[-1]


def shuffle_edit_score(
    shared_reference: list[str],
    microphone_reference: list[str],
    hypothesis: list[str],
) -> dict[str, Any]:
    """Minimum edit distance to any order-preserving interleaving of two references.

    ``D[i,j,k]`` consumes ``i`` shared tokens, ``j`` microphone tokens, and ``k``
    hypothesis tokens. A diagonal step consumes a hypothesis token for exactly one lane.
    The deterministic tie order prefers an exact/substitution alignment, then an insertion,
    then a deletion; it changes attribution diagnostics but never the minimum distance.
    """
    shared_count = len(shared_reference)
    microphone_count = len(microphone_reference)
    hypothesis_count = len(hypothesis)
    j_size = microphone_count + 1
    k_size = hypothesis_count + 1
    state_count = (shared_count + 1) * j_size * k_size
    distances = array.array("H", [0]) * state_count
    parents = array.array("B", [0]) * state_count

    def offset(i: int, j: int, k: int) -> int:
        return (i * j_size + j) * k_size + k

    # Parent codes: 1 shared diagonal, 2 microphone diagonal, 3 hypothesis insertion,
    # 4 shared deletion, 5 microphone deletion.
    for i in range(shared_count + 1):
        for j in range(microphone_count + 1):
            for k in range(hypothesis_count + 1):
                if i == 0 and j == 0 and k == 0:
                    continue
                candidates: list[tuple[int, int]] = []
                if i and k:
                    candidates.append((
                        distances[offset(i - 1, j, k - 1)]
                        + int(shared_reference[i - 1] != hypothesis[k - 1]),
                        1,
                    ))
                if j and k:
                    candidates.append((
                        distances[offset(i, j - 1, k - 1)]
                        + int(microphone_reference[j - 1] != hypothesis[k - 1]),
                        2,
                    ))
                if k:
                    candidates.append((distances[offset(i, j, k - 1)] + 1, 3))
                if i:
                    candidates.append((distances[offset(i - 1, j, k)] + 1, 4))
                if j:
                    candidates.append((distances[offset(i, j - 1, k)] + 1, 5))
                distance, parent = min(candidates, key=lambda candidate: candidate[0])
                distances[offset(i, j, k)] = distance
                parents[offset(i, j, k)] = parent

    i, j, k = shared_count, microphone_count, hypothesis_count
    operations: list[dict[str, Any]] = []
    counts = {
        "shared_matches": 0,
        "microphone_matches": 0,
        "shared_substitutions": 0,
        "microphone_substitutions": 0,
        "shared_deletions": 0,
        "microphone_deletions": 0,
        "hypothesis_insertions": 0,
    }
    while i or j or k:
        parent = parents[offset(i, j, k)]
        if parent == 1:
            reference_token = shared_reference[i - 1]
            hypothesis_token = hypothesis[k - 1]
            exact = reference_token == hypothesis_token
            counts["shared_matches" if exact else "shared_substitutions"] += 1
            operations.append({
                "operation": "match" if exact else "substitute",
                "lane": "shared",
                "reference_token": reference_token,
                "hypothesis_token": hypothesis_token,
            })
            i -= 1
            k -= 1
        elif parent == 2:
            reference_token = microphone_reference[j - 1]
            hypothesis_token = hypothesis[k - 1]
            exact = reference_token == hypothesis_token
            counts["microphone_matches" if exact else "microphone_substitutions"] += 1
            operations.append({
                "operation": "match" if exact else "substitute",
                "lane": "microphone",
                "reference_token": reference_token,
                "hypothesis_token": hypothesis_token,
            })
            j -= 1
            k -= 1
        elif parent == 3:
            counts["hypothesis_insertions"] += 1
            operations.append({
                "operation": "insert",
                "lane": None,
                "reference_token": None,
                "hypothesis_token": hypothesis[k - 1],
            })
            k -= 1
        elif parent == 4:
            counts["shared_deletions"] += 1
            operations.append({
                "operation": "delete",
                "lane": "shared",
                "reference_token": shared_reference[i - 1],
                "hypothesis_token": None,
            })
            i -= 1
        elif parent == 5:
            counts["microphone_deletions"] += 1
            operations.append({
                "operation": "delete",
                "lane": "microphone",
                "reference_token": microphone_reference[j - 1],
                "hypothesis_token": None,
            })
            j -= 1
        else:
            raise RuntimeError(f"shuffle_backtrace_missing:{i}:{j}:{k}")
    operations.reverse()
    distance = int(distances[offset(shared_count, microphone_count, hypothesis_count)])
    denominator = shared_count + microphone_count
    error_count = (
        counts["shared_substitutions"]
        + counts["microphone_substitutions"]
        + counts["shared_deletions"]
        + counts["microphone_deletions"]
        + counts["hypothesis_insertions"]
    )
    if error_count != distance:
        raise RuntimeError(f"shuffle_backtrace_distance_mismatch:{error_count}:{distance}")
    return {
        "distance": distance,
        "reference_tokens": denominator,
        "hypothesis_tokens": hypothesis_count,
        "word_error_rate": distance / denominator if denominator else 0.0,
        **counts,
        "operation_trace": operations,
    }


def transcribe(runner: VllmRunner, path: Path) -> tuple[str, dict[str, float | int]]:
    result = runner.transcribe(str(path))
    return result.text, {
        "elapsed_seconds": result.elapsed_sec,
        "generated_tokens": result.generated_tokens,
        "prompt_tokens": result.prompt_len,
    }


def discover_model(base_url: str, timeout_seconds: float) -> str:
    with urlopen(base_url.rstrip("/") + "/models", timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    models = [
        item.get("id")
        for item in payload.get("data", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    if len(models) != 1:
        raise RuntimeError(f"expected_one_vllm_model:{models}")
    return models[0]


def historical_audit(path: Path) -> dict[str, Any]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    shared_reference = words(artifact["clean_references"]["shared"]["text"])
    microphone_reference = words(artifact["clean_references"]["microphone"]["text"])
    corrected: dict[str, Any] = {}
    for identifier, result in artifact["results"].items():
        hypothesis = words(result["transcript"])
        corrected[identifier] = {
            "hypothesis_tokens": len(hypothesis),
            "shared_true_lcs_matches": true_lcs_matches(shared_reference, hypothesis),
            "microphone_true_lcs_matches": true_lcs_matches(microphone_reference, hypothesis),
            "shuffle_edit": shuffle_edit_score(shared_reference, microphone_reference, hypothesis),
        }
    return {
        "path": str(path.relative_to(REPO)),
        "sha256": sha256(path),
        "policy_selection_valid": False,
        "invalid_reasons": [
            "fixture total disparity was 25.741875 dB, not attended 15.377 dB",
            "emitted lcs_matches used SequenceMatcher matching blocks, not true LCS",
            "per-lane WER charged other-lane words as insertions",
            "summing per-lane matches double-counts hypothesis tokens",
        ],
        "corrected_transcript_only_metrics": corrected,
    }


def corpus_measurement(
    *,
    contract: dict[str, Any],
    corpus: dict[str, Any],
    fixture_root: Path,
    runner: VllmRunner,
    temporary_root: Path,
) -> dict[str, Any]:
    shared_path = fixture_root / corpus["shared_lane"]
    microphone_path = fixture_root / corpus["microphone_lane"]
    if sha256(shared_path) != corpus["shared_sha256"]:
        raise RuntimeError(f"shared_fixture_hash_mismatch:{corpus['id']}")
    if sha256(microphone_path) != corpus["microphone_sha256"]:
        raise RuntimeError(f"microphone_fixture_hash_mismatch:{corpus['id']}")
    shared, sample_rate = read_pcm(shared_path, int(corpus["clip_seconds"]))
    microphone_source, microphone_sample_rate = read_pcm(
        microphone_path, int(corpus["clip_seconds"])
    )
    if microphone_sample_rate != sample_rate:
        raise RuntimeError(f"sample_rate_mismatch:{corpus['id']}")
    attenuation_gain = 10 ** (float(corpus["microphone_attenuation_db"]) / 20)
    quiet_microphone = [sample * attenuation_gain for sample in microphone_source]
    shared_rms = rms(shared)
    microphone_source_rms = rms(microphone_source)
    quiet_microphone_rms = rms(quiet_microphone)
    total_disparity_db = dbfs(shared_rms) - dbfs(quiet_microphone_rms)
    calibration = contract["calibration"]
    if not math.isclose(
        total_disparity_db,
        float(calibration["target_total_disparity_db"]),
        rel_tol=0.0,
        abs_tol=float(calibration["tolerance_db"]),
    ):
        raise RuntimeError(f"calibration_mismatch:{corpus['id']}:{total_disparity_db}")

    corpus_root = temporary_root / corpus["id"]
    corpus_root.mkdir()
    shared_reference_path = corpus_root / "shared-reference.wav"
    microphone_reference_path = corpus_root / "microphone-reference.wav"
    write_pcm(shared_reference_path, shared, sample_rate)
    write_pcm(microphone_reference_path, microphone_source, sample_rate)
    shared_reference_text, shared_reference_runtime = transcribe(runner, shared_reference_path)
    microphone_reference_text, microphone_reference_runtime = transcribe(
        runner, microphone_reference_path
    )
    shared_reference = words(shared_reference_text)
    microphone_reference = words(microphone_reference_text)
    if not shared_reference or not microphone_reference:
        raise RuntimeError(f"empty_clean_reference:{corpus['id']}")
    if shared_reference == microphone_reference:
        raise RuntimeError(f"non_distinct_clean_references:{corpus['id']}")

    results: dict[str, Any] = {}
    for candidate in contract["candidates"]:
        identifier = candidate["id"]
        gain_db = float(candidate["microphone_gain_db_from_quiet"])
        gain = 10 ** (gain_db / 20)
        scaled_microphone = [sample * gain for sample in quiet_microphone]
        mixed, limited_samples = mix(shared, scaled_microphone)
        mixed_path = corpus_root / f"{identifier}.wav"
        write_pcm(mixed_path, mixed, sample_rate)
        transcript, runtime = transcribe(runner, mixed_path)
        hypothesis = words(transcript)
        result = {
            "microphone_gain": gain,
            "microphone_gain_db_from_quiet": gain_db,
            "mixed_audio_sha256": sha256(mixed_path),
            "transcript": transcript,
            "normalized_hypothesis_tokens": hypothesis,
            "transcription_runtime": runtime,
            "shuffle_edit": shuffle_edit_score(
                shared_reference, microphone_reference, hypothesis
            ),
            "per_lane_lcs_diagnostic": {
                "shared": {
                    "reference_tokens": len(shared_reference),
                    "true_lcs_matches": true_lcs_matches(shared_reference, hypothesis),
                },
                "microphone": {
                    "reference_tokens": len(microphone_reference),
                    "true_lcs_matches": true_lcs_matches(microphone_reference, hypothesis),
                },
                "warning": "diagnostic only; never sum these lane scores",
            },
            "audio_state": {
                "scaled_microphone_peak": max(abs(sample) for sample in scaled_microphone),
                "scaled_microphone_over_range_samples": sum(
                    abs(sample) > 1.0 for sample in scaled_microphone
                ),
                "output_peak": max(abs(sample) for sample in mixed),
                "limited_samples": limited_samples,
                "limited_output_fraction": limited_samples / len(mixed),
            },
        }
        results[identifier] = result
        print(json.dumps({
            "candidate_complete": True,
            "corpus": corpus["id"],
            "candidate": identifier,
            "full_state": result,
        }, ensure_ascii=False), flush=True)

    return {
        "role": corpus["role"],
        "input": {
            "shared_lane": {
                "path": corpus["shared_lane"],
                "sha256": corpus["shared_sha256"],
                "rms": shared_rms,
                "dbfs": dbfs(shared_rms),
            },
            "microphone_lane": {
                "path": corpus["microphone_lane"],
                "sha256": corpus["microphone_sha256"],
                "rms_before_attenuation": microphone_source_rms,
                "dbfs_before_attenuation": dbfs(microphone_source_rms),
                "attenuation_db": corpus["microphone_attenuation_db"],
                "rms_after_attenuation": quiet_microphone_rms,
                "dbfs_after_attenuation": dbfs(quiet_microphone_rms),
            },
            "total_disparity_db": total_disparity_db,
            "clip_seconds": corpus["clip_seconds"],
            "sample_rate": sample_rate,
        },
        "clean_references": {
            "shared": {
                "text": shared_reference_text,
                "normalized_tokens": shared_reference,
                "runtime": shared_reference_runtime,
            },
            "microphone": {
                "text": microphone_reference_text,
                "normalized_tokens": microphone_reference,
                "runtime": microphone_reference_runtime,
            },
        },
        "results": results,
    }


def select(contract: dict[str, Any], corpora: dict[str, Any]) -> dict[str, Any]:
    discovery_id = next(
        corpus["id"] for corpus in contract["corpora"] if corpus["role"] == "discovery"
    )
    discovery = corpora[discovery_id]["results"]
    identity_wer = discovery["gain_0db"]["shuffle_edit"]["word_error_rate"]
    best_wer = min(result["shuffle_edit"]["word_error_rate"] for result in discovery.values())
    within_best = [
        candidate for candidate in contract["candidates"]
        if discovery[candidate["id"]]["shuffle_edit"]["word_error_rate"] <= best_wer + 0.01
    ]
    selected_contract = min(
        within_best, key=lambda candidate: float(candidate["microphone_gain_db_from_quiet"])
    )
    selected_id = selected_contract["id"]
    discovery_improvement = (
        identity_wer - discovery[selected_id]["shuffle_edit"]["word_error_rate"]
    )
    if selected_id == "gain_0db" or discovery_improvement < 0.05:
        return {
            "verdict": "GAIN_ONLY_FAILED_DISCOVERY",
            "selected_candidate": None,
            "best_observed_candidate": selected_id,
            "identity_total_content_wer": identity_wer,
            "best_total_content_wer": best_wer,
            "discovery_improvement": discovery_improvement,
            "next_step": "prototype separate-lane decode/merge",
        }

    validation_improvements: dict[str, float] = {}
    for corpus in contract["corpora"]:
        if corpus["role"] != "validation":
            continue
        results = corpora[corpus["id"]]["results"]
        validation_improvements[corpus["id"]] = (
            results["gain_0db"]["shuffle_edit"]["word_error_rate"]
            - results[selected_id]["shuffle_edit"]["word_error_rate"]
        )
    improvements = list(validation_improvements.values())
    wins = sum(improvement > 0 for improvement in improvements)
    median_improvement = statistics.median(improvements)
    worst_improvement = min(improvements)
    passes = wins >= 2 and median_improvement >= 0.05 and worst_improvement >= -0.05
    return {
        "verdict": (
            "CAUSAL_GAIN_RULE_PROTOTYPE_REQUIRED"
            if passes else "GAIN_ONLY_FAILED_REPLICATION"
        ),
        "selected_candidate": selected_id,
        "selected_gain_db_from_quiet": selected_contract["microphone_gain_db_from_quiet"],
        "identity_total_content_wer": identity_wer,
        "best_total_content_wer": best_wer,
        "discovery_improvement": discovery_improvement,
        "validation_improvements": validation_improvements,
        "validation_wins": wins,
        "validation_median_improvement": median_improvement,
        "validation_worst_improvement": worst_improvement,
        "replication_passes": passes,
        "next_step": (
            "prototype a causal live gain rule"
            if passes else "prototype separate-lane decode/merge"
        ),
    }


def main() -> int:
    args = parse_args()
    output_path = args.output.resolve()
    if output_path.exists():
        raise RuntimeError(f"refuse_to_overwrite_output:{output_path}")
    contract = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    if contract.get("schema") != "moss-lane-balance-preregistration.v3":
        raise RuntimeError("preregistration_schema")
    fixture_root = args.fixture_root.resolve()
    model = discover_model(args.base_url, args.timeout_seconds)
    runner = VllmRunner(
        base_url=args.base_url,
        model=model,
        api_key=None,
        timeout=args.timeout_seconds,
    )
    historical_paths = [
        REPO / "evidence/phase1/g3-attended/iteration-2-lane-balance.json",
        REPO / "evidence/phase1/g3-attended/iteration-2-lane-balance-v2.json",
    ]
    with tempfile.TemporaryDirectory(prefix="moss-lane-balance-v3-") as temporary:
        temporary_root = Path(temporary)
        corpora = {
            corpus["id"]: corpus_measurement(
                contract=contract,
                corpus=corpus,
                fixture_root=fixture_root,
                runner=runner,
                temporary_root=temporary_root,
            )
            for corpus in contract["corpora"]
        }
    selection = select(contract, corpora)
    result = {
        "schema": "moss-lane-balance-result.v3",
        "preregistration": {
            "path": str(PREREGISTRATION.relative_to(REPO)),
            "sha256": sha256(PREREGISTRATION),
        },
        "scope": contract["scope"],
        "does_not_establish": contract["decision_rule"]["interpretation_limit"],
        "vllm": {"base_url": args.base_url, "model": model},
        "historical_artifact_audit": [historical_audit(path) for path in historical_paths],
        "corpora": corpora,
        "selection": selection,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "complete": True,
        "output": str(output_path),
        "output_sha256": sha256(output_path),
        "selection": selection,
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
