#!/usr/bin/env python3
"""PROTOTYPE: does matching lane levels recover the quiet speaker's words?

The operator's attended runs lose almost everything they say while the shared lane transcribes
cleanly. Measured disparity is ~15 dB. A previous attempt to correct this measured WORSE and was
rejected -- but that test played the SAME audio in both lanes, where boosting one lane just doubles
the same signal. This test uses two DIFFERENT speakers, which is the real condition.

Per-lane references come from transcribing each lane clean at full level, then we measure how much
of each reference survives the mix under each policy.

  .venv/bin/python prototypes/lane-balance/proto_lane_balance.py \
    --output evidence/phase1/g3-attended/lane-balance-v2.json
"""
from __future__ import annotations
import argparse, array, contextlib, hashlib, json, math, os, sys, tempfile, wave
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.request import urlopen

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from moss_transcribe_diarize.app.vllm_runner import VllmRunner  # noqa: E402
from moss_transcribe_diarize.speaker_reference import normalize_reference_text  # noqa: E402

DATA = REPO / "prototypes/streaming-diarization/data"
PREREGISTRATION = Path(__file__).with_name("preregistration-v2.json")
DEFAULT_BASE_URL = "http://127.0.0.1:18000/v1"
SECONDS = 12
HEADROOM = 10 ** (-6 / 20)          # live_mixer.py:16
LIMIT, RANGE = 0.98, 0.02           # live_mixer.py:17-18
QUIET_DB = -15.0                    # the measured microphone disparity


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("MOSS_VLLM_BASE_URL", DEFAULT_BASE_URL),
        help="OpenAI-compatible vLLM /v1 endpoint (default: MOSS_VLLM_BASE_URL or tunnel).",
    )
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=REPO,
        help="Checkout containing the ignored preregistered fixture paths (default: this checkout).",
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


def read(path: Path, seconds: int) -> tuple[list[float], int]:
    with contextlib.closing(wave.open(str(path))) as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getcomptype() != "NONE":
            raise RuntimeError(f"expected_mono_pcm16:{path}")
        sr = w.getframerate()
        raw = w.readframes(sr * seconds)
    ints = array.array("h")
    ints.frombytes(raw)
    if sys.byteorder != "little":
        ints.byteswap()
    if len(ints) != sr * seconds:
        raise RuntimeError(f"short_clip:{path}:{len(ints)}:{sr * seconds}")
    return [v / 32768.0 for v in ints], sr


def write(path: Path, samples: list[float], sr: int) -> None:
    out = array.array("h", (int(max(-1.0, min(1.0, s)) * 32767) for s in samples))
    if sys.byteorder != "little":
        out.byteswap()
    with contextlib.closing(wave.open(str(path), "w")) as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(out.tobytes())


def rms(xs: list[float]) -> float:
    return math.sqrt(sum(x * x for x in xs) / len(xs)) if xs else 0.0


def mix(system: list[float], microphone: list[float]) -> tuple[list[float], int]:
    """The fixed-headroom soft-limited sample transform from ``live_mixer.py``."""
    if len(system) != len(microphone):
        raise RuntimeError("aligned_track_length_mismatch")
    out = []
    limited_samples = 0
    for s, m in zip(system, microphone):
        v = (s * HEADROOM) + (m * HEADROOM)
        if abs(v) > LIMIT:
            limited_samples += 1
            v = math.copysign(LIMIT + RANGE * math.tanh((abs(v) - LIMIT) / RANGE), v)
        out.append(max(-1.0, min(1.0, v)))
    return out, limited_samples


def words(text: str) -> list[str]:
    return normalize_reference_text(text).split()


def lcs_matches(reference: list[str], observed: list[str]) -> int:
    return sum(
        block.size
        for block in SequenceMatcher(a=reference, b=observed, autojunk=False).get_matching_blocks()
    )


def edit_distance(reference: list[str], observed: list[str]) -> int:
    previous = list(range(len(observed) + 1))
    for reference_index, reference_token in enumerate(reference, 1):
        current = [reference_index]
        for observed_index, observed_token in enumerate(observed, 1):
            current.append(min(
                previous[observed_index] + 1,
                current[observed_index - 1] + 1,
                previous[observed_index - 1] + (reference_token != observed_token),
            ))
        previous = current
    return previous[-1]


def score(reference_text: str, mixed_text: str) -> dict[str, float | int]:
    ref, hyp = words(reference_text), words(mixed_text)
    if not ref:
        raise RuntimeError("empty_clean_reference")
    matches = lcs_matches(ref, hyp)
    return {
        "reference_tokens": len(ref),
        "mixed_tokens": len(hyp),
        "lcs_matches": matches,
        "word_recall": matches / len(ref),
        "word_error_rate": edit_distance(ref, hyp) / len(ref),
        "missing_reference_words": len(ref) - matches,
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


def policies_from_contract(
    candidates: list[dict[str, Any]], quiet: list[float], shared_rms: float, quiet_rms: float
) -> dict[str, tuple[str, list[float], float]]:
    """Materialize only the preregistered gain rules before any inference begins."""
    policies = {}
    for candidate in candidates:
        identifier = candidate["id"]
        label = candidate["runner_policy_label"]
        if candidate.get("microphone_gain_rule") == "shared_rms_divided_by_attenuated_microphone_rms":
            gain = shared_rms / quiet_rms
        else:
            gain_db = candidate.get("microphone_gain_db_from_quiet")
            if not isinstance(gain_db, (int, float)):
                raise RuntimeError(f"missing_fixed_microphone_gain:{identifier}")
            gain = 10 ** (gain_db / 20)
            declared_gain = candidate.get("microphone_gain")
            if declared_gain is not None and not math.isclose(gain, declared_gain, rel_tol=0.0, abs_tol=1e-15):
                raise RuntimeError(f"declared_microphone_gain_mismatch:{identifier}")
        policies[identifier] = (label, [sample * gain for sample in quiet], gain)
    return policies


def main() -> int:
    args = parse_args()
    output_path = args.output.resolve()
    if output_path.exists():
        raise RuntimeError(f"refuse_to_overwrite_output:{output_path}")
    contract = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    if contract.get("schema") != "moss-lane-balance-preregistration.v2":
        raise RuntimeError("preregistration_schema")

    fixture = contract["fixture"]
    clip_seconds = int(fixture["clip_seconds"])
    quiet_db = float(fixture["microphone_attenuation_db"])
    if clip_seconds != SECONDS or quiet_db != QUIET_DB:
        raise RuntimeError("runner_preregistration_fixture_mismatch")
    fixture_root = args.fixture_root.resolve()
    shared_path = fixture_root / fixture["shared_lane"]
    microphone_path = fixture_root / fixture["microphone_lane"]
    shared, sample_rate = read(shared_path, clip_seconds)
    microphone_source, microphone_sample_rate = read(microphone_path, clip_seconds)
    if sample_rate != microphone_sample_rate:
        raise RuntimeError("sample_rate_mismatch")
    quiet = [sample * (10 ** (quiet_db / 20)) for sample in microphone_source]
    shared_rms, quiet_rms = rms(shared), rms(quiet)
    if shared_rms <= 0 or quiet_rms <= 0:
        raise RuntimeError("nonpositive_lane_rms")
    policies = policies_from_contract(contract["candidates"], quiet, shared_rms, quiet_rms)
    expected_labels = {entry["id"]: entry["runner_policy_label"] for entry in contract["candidates"]}
    if set(expected_labels) != set(policies) or any(
        expected_labels[identifier] != policy[0] for identifier, policy in policies.items()
    ):
        raise RuntimeError("runner_preregistration_policy_mismatch")

    model = discover_model(args.base_url, args.timeout_seconds)
    runner = VllmRunner(base_url=args.base_url, model=model, api_key=None, timeout=args.timeout_seconds)
    with tempfile.TemporaryDirectory(prefix="moss-lane-balance-") as temporary:
        temporary_path = Path(temporary)
        shared_reference_path = temporary_path / "shared-reference.wav"
        microphone_reference_path = temporary_path / "microphone-reference.wav"
        write(shared_reference_path, shared, sample_rate)
        write(microphone_reference_path, microphone_source, sample_rate)
        shared_reference, shared_reference_runtime = transcribe(runner, shared_reference_path)
        microphone_reference, microphone_reference_runtime = transcribe(runner, microphone_reference_path)
        if words(shared_reference) == words(microphone_reference):
            raise RuntimeError("non_distinct_clean_references")

        results: dict[str, dict[str, Any]] = {}
        for identifier, (label, microphone, gain) in policies.items():
            mixed, limited_samples = mix(shared, microphone)
            mixed_path = temporary_path / f"{identifier}.wav"
            write(mixed_path, mixed, sample_rate)
            transcript, transcription_runtime = transcribe(runner, mixed_path)
            results[identifier] = {
                "label": label,
                "microphone_gain": gain,
                "microphone_gain_db_from_quiet": 20 * math.log10(gain),
                "mixed_audio_sha256": sha256(mixed_path),
                "transcript": transcript,
                "transcription_runtime": transcription_runtime,
                "shared": score(shared_reference, transcript),
                "microphone": score(microphone_reference, transcript),
                "limited_samples": limited_samples,
                "limited_output_fraction": limited_samples / len(mixed),
            }
            print(json.dumps({"policy_complete": identifier, "result": results[identifier]}, ensure_ascii=False), flush=True)

    identity = results["identity"]
    eligible: list[tuple[str, dict[str, Any]]] = []
    for identifier, candidate in results.items():
        if identifier == "identity":
            continue
        metrics = {
            "microphone_recall_improvement": candidate["microphone"]["word_recall"] - identity["microphone"]["word_recall"],
            "shared_recall_change": candidate["shared"]["word_recall"] - identity["shared"]["word_recall"],
            "microphone_wer_reduction": identity["microphone"]["word_error_rate"] - candidate["microphone"]["word_error_rate"],
            "microphone_missing_word_reduction": identity["microphone"]["missing_reference_words"] - candidate["microphone"]["missing_reference_words"],
            "limited_sample_fraction_change": candidate["limited_output_fraction"] - identity["limited_output_fraction"],
        }
        candidate["decision_metrics"] = metrics
        reasons = []
        if metrics["microphone_recall_improvement"] < 0.05:
            reasons.append("microphone_recall_improvement_below_0.05")
        if metrics["shared_recall_change"] < -0.05:
            reasons.append("shared_recall_decrease_exceeds_0.05")
        if metrics["microphone_wer_reduction"] < 0.05:
            reasons.append("microphone_wer_reduction_below_0.05")
        if metrics["microphone_missing_word_reduction"] <= 0:
            reasons.append("microphone_missing_word_count_not_strictly_reduced")
        if metrics["limited_sample_fraction_change"] > 0:
            reasons.append("limited_sample_fraction_exceeds_identity")
        candidate["rejection_reasons"] = reasons
        candidate["eligible"] = not reasons
        if not reasons:
            eligible.append((identifier, candidate))

    if eligible:
        greatest_recall_improvement = max(
            candidate["decision_metrics"]["microphone_recall_improvement"] for _, candidate in eligible
        )
        selected_identifier, selected = min(
            (
                (identifier, candidate)
                for identifier, candidate in eligible
                if candidate["decision_metrics"]["microphone_recall_improvement"] >= greatest_recall_improvement - 0.005
            ),
            key=lambda item: item[1]["microphone_gain"],
        )
        selection = {
            "verdict": "CANDIDATE_FOR_SEPARATE_REPLICATION",
            "selected_candidate": selected_identifier,
            "selection_reason": "eligible_within_0.005_of_largest_microphone_recall_improvement_and_lowest_gain",
            "selected_microphone_recall_improvement": selected["decision_metrics"]["microphone_recall_improvement"],
        }
    else:
        selection = {
            "verdict": "RETAIN_IDENTITY",
            "selected_candidate": "identity",
            "selection_reason": contract["decision_rule"]["if_no_candidate_is_eligible"],
        }

    result = {
        "schema": "moss-lane-balance-result.v2",
        "preregistration": {
            "path": str(PREREGISTRATION.relative_to(REPO)),
            "sha256": sha256(PREREGISTRATION),
        },
        "scope": contract["scope"],
        "does_not_establish": contract["decision_rule"]["interpretation_limit"],
        "input": {
            "fixture_root": str(fixture_root),
            "shared_lane": {"path": fixture["shared_lane"], "sha256": sha256(shared_path), "rms": shared_rms},
            "microphone_lane": {"path": fixture["microphone_lane"], "sha256": sha256(microphone_path), "rms_before_attenuation": rms(microphone_source), "rms_after_attenuation": quiet_rms},
            "microphone_attenuation_db": quiet_db,
            "clip_seconds": clip_seconds,
            "sample_rate": sample_rate,
        },
        "vllm": {"base_url": args.base_url, "model": model},
        "clean_references": {
            "shared": {"text": shared_reference, "normalized_tokens": len(words(shared_reference)), "runtime": shared_reference_runtime},
            "microphone": {"text": microphone_reference, "normalized_tokens": len(words(microphone_reference)), "runtime": microphone_reference_runtime},
        },
        "recall_definition": "LCS matches divided by clean-reference token count, normalized by speaker_reference.normalize_reference_text.",
        "results": results,
        "selection": selection,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"complete": True, "output": str(output_path), "selection": selection}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
