#!/usr/bin/env python3
"""THROWAWAY diagnostic: measure mixer lane-level effects before changing policy.

One command (with the current tunnel):
  .venv/bin/python prototypes/streaming-diarization/proto_lane_level_effect.py \
    --preregistration prototypes/streaming-diarization/lane-level-preregistration-v2.json \
    --base-url http://127.0.0.1:18000/v1 \
    --output evidence/phase1/g3-attended/iteration-20-lane-level-prototype.json

Question: on two real aligned recorded lanes, does peer-RMS microphone matching improve
quiet-microphone word error relative to the exact production fixed-headroom
mixer?  This script is deliberately not product code and never selects a policy:
the preregistration requires a distinct lexical system reference, which the current
leakage fixture does not supply.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
import wave
from array import array
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from moss_transcribe_diarize.app.live_lane_contract import LiveLane, LiveV2Frame  # noqa: E402
from moss_transcribe_diarize.app.live_mixer import LiveCompatibilityMixer  # noqa: E402
from moss_transcribe_diarize.app.live_v2_session import LiveV2Session  # noqa: E402
from moss_transcribe_diarize.app.vllm_runner import VllmRunner  # noqa: E402
from moss_transcribe_diarize.speaker_reference import normalize_reference_text  # noqa: E402
from moss_transcribe_diarize.transcript_parser import parse_transcript  # noqa: E402


@dataclass(frozen=True)
class PcmTrack:
    values: tuple[int, ...]
    sample_rate: int

    @property
    def duration_seconds(self) -> float:
        return len(self.values) / self.sample_rate

    @property
    def rms(self) -> float:
        if not self.values:
            return 0.0
        return math.sqrt(sum(value * value for value in self.values) / len(self.values)) / 32768.0

    @property
    def peak(self) -> float:
        return max((abs(value) for value in self.values), default=0) / 32768.0


class CollectingRuntime:
    """The minimal runtime seam required by the real production mixer."""

    def __init__(self) -> None:
        self.frames = []

    def snapshot(self, _session_id: str) -> SimpleNamespace:
        return SimpleNamespace(session=SimpleNamespace(next_frame_sequence=len(self.frames)))

    def accept_frame(self, _session_id: str, frame, *, retryable_queue_backpressure: bool) -> SimpleNamespace:
        if retryable_queue_backpressure is not True:
            raise RuntimeError("prototype must exercise the v2 retryable mixer path")
        self.frames.append(frame)
        return SimpleNamespace(queued_item_ids=(), snapshot=self.snapshot(_session_id))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--base-url", required=True, help="OpenAI-compatible vLLM /v1 URL")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_mono_pcm16(path: Path) -> PcmTrack:
    with wave.open(str(path), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getcomptype() != "NONE":
            raise RuntimeError(f"expected_mono_pcm16:{path}")
        values = array("h")
        values.frombytes(source.readframes(source.getnframes()))
        if sys.byteorder != "little":
            values.byteswap()
        return PcmTrack(values=tuple(values), sample_rate=source.getframerate())


def pcm_bytes(values: tuple[int, ...]) -> bytes:
    encoded = array("h", values)
    if sys.byteorder != "little":
        encoded.byteswap()
    return encoded.tobytes()


def scale_pcm(values: tuple[int, ...], gain: float) -> tuple[tuple[int, ...], int]:
    scaled: list[int] = []
    clipped = 0
    for value in values:
        candidate = int(round(value * gain))
        if candidate > 32767:
            candidate = 32767
            clipped += 1
        elif candidate < -32768:
            candidate = -32768
            clipped += 1
        scaled.append(candidate)
    return tuple(scaled), clipped


def frame(lane: LiveLane, sequence: int, timestamp_ns: int, sample_rate: int, values: tuple[int, ...], *, silent: bool = False) -> LiveV2Frame:
    return LiveV2Frame(
        lane=lane,
        sequence=sequence,
        capture_timestamp_ns=timestamp_ns,
        device_epoch=0,
        silent=silent,
        discontinuity=False,
        sample_rate=sample_rate,
        sample_count=len(values),
        pcm=pcm_bytes(values),
    )


def production_mix(system: tuple[int, ...], microphone: tuple[int, ...], *, sample_rate: int, frame_samples: int) -> tuple[bytes, dict[str, int]]:
    if len(system) != len(microphone):
        raise RuntimeError("aligned_track_length_mismatch")
    source = LiveV2Session(max_retained_samples=frame_samples * 4)
    runtime = CollectingRuntime()
    mixer = LiveCompatibilityMixer(max_output_samples=frame_samples)
    diagnostics = {"overlap_samples": 0, "limited_samples": 0, "gap_samples": 0, "silent_samples": 0}
    timestamp_ns = 0
    sequence = 0
    for start in range(0, len(system), frame_samples):
        system_values = system[start : start + frame_samples]
        microphone_values = microphone[start : start + frame_samples]
        source.accept(frame(LiveLane.SYSTEM, sequence, timestamp_ns, sample_rate, system_values, silent=not any(system_values)))
        source.accept(frame(LiveLane.MICROPHONE, sequence, timestamp_ns, sample_rate, microphone_values, silent=not any(microphone_values)))
        result = mixer.admit_available("lane-level-prototype", source, runtime, final=False)
        if result is not None:
            _accumulate_diagnostics(diagnostics, result.diagnostics)
        timestamp_ns += math.ceil(len(system_values) * 1_000_000_000 / sample_rate)
        sequence += 1
    while True:
        result = mixer.admit_available("lane-level-prototype", source, runtime, final=True)
        if result is None:
            break
        _accumulate_diagnostics(diagnostics, result.diagnostics)
    output = b"".join(frame.pcm for frame in runtime.frames)
    if len(output) != len(system) * 2:
        raise RuntimeError(f"production_mixer_output_length:{len(output)}:{len(system) * 2}")
    return output, diagnostics


def _accumulate_diagnostics(total: dict[str, int], diagnostics: Any) -> None:
    total["overlap_samples"] += diagnostics.overlap_samples
    total["limited_samples"] += diagnostics.limited_samples
    total["gap_samples"] += sum(diagnostics.gap_samples.values())
    total["silent_samples"] += sum(diagnostics.silent_samples.values())


def write_wav(path: Path, pcm: bytes, *, sample_rate: int) -> None:
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(sample_rate)
        destination.writeframes(pcm)


def reference_tokens(path: Path) -> list[str]:
    text = " ".join(json.loads(line)["text"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return normalize_reference_text(text).split()


def transcript_text(raw: str) -> str:
    try:
        parsed = parse_transcript(raw)
    except ValueError:
        return raw
    if not parsed:
        return raw
    return " ".join(segment.text for segment in parsed)


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


def score_reference(reference: list[str], raw_transcript: str) -> dict[str, Any]:
    observed = normalize_reference_text(transcript_text(raw_transcript)).split()
    matches = sum(block.size for block in SequenceMatcher(a=reference, b=observed, autojunk=False).get_matching_blocks())
    distance = edit_distance(reference, observed)
    return {
        "reference_tokens": len(reference),
        "transcript_tokens": len(observed),
        "lcs_matches": matches,
        "missing_reference_words": len(reference) - matches,
        "word_error_rate": distance / len(reference) if reference else 0.0,
        "word_recall": matches / len(reference) if reference else 0.0,
        "word_precision": matches / len(observed) if observed else 0.0,
    }


def discover_model(base_url: str, timeout_seconds: float) -> str:
    with urlopen(base_url.rstrip("/") + "/models", timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    models = [item.get("id") for item in payload.get("data", []) if isinstance(item, dict) and isinstance(item.get("id"), str)]
    if len(models) != 1:
        raise RuntimeError(f"expected_one_vllm_model:{models}")
    return models[0]


def main() -> int:
    args = parse_args()
    preregistration_path = args.preregistration.resolve()
    output_path = args.output.resolve()
    if output_path.exists():
        raise RuntimeError(f"refuse_to_overwrite_output:{output_path}")
    contract = json.loads(preregistration_path.read_text(encoding="utf-8"))
    if contract.get("schema") != "moss-lane-level-prototype-preregistration.v2":
        raise RuntimeError("preregistration_schema")
    system_spec = contract["inputs"]["system"]
    microphone_spec = contract["inputs"]["microphone"]
    system_path = ROOT / system_spec["audio_path"]
    microphone_path = ROOT / microphone_spec["audio_path"]
    system_reference_path = ROOT / system_spec["reference_jsonl"]
    microphone_reference_path = ROOT / microphone_spec["reference_jsonl"]
    for path, expected in (
        (system_path, system_spec["sha256"]),
        (microphone_path, microphone_spec["sha256"]),
        (system_reference_path, system_spec["reference_sha256"]),
        (microphone_reference_path, microphone_spec["reference_sha256"]),
    ):
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"input_hash_mismatch:{path}:{actual}")
    system_track = load_mono_pcm16(system_path)
    microphone_track = load_mono_pcm16(microphone_path)
    sample_rate = int(contract["production_path"]["sample_rate"])
    frame_samples = int(contract["production_path"]["frame_samples"])
    if system_track.sample_rate != sample_rate or microphone_track.sample_rate != sample_rate:
        raise RuntimeError("sample_rate_mismatch")
    shared_samples = min(len(system_track.values), len(microphone_track.values))
    system = system_track.values[:shared_samples]
    microphone = microphone_track.values[:shared_samples]
    measured_system_rms = PcmTrack(system, sample_rate).rms
    measured_microphone_rms = PcmTrack(microphone, sample_rate).rms
    if measured_system_rms <= 0 or measured_microphone_rms <= 0:
        raise RuntimeError("nonpositive_input_rms")
    peer_gain = measured_system_rms / measured_microphone_rms
    references = {
        "system": reference_tokens(system_reference_path),
        "microphone": reference_tokens(microphone_reference_path),
    }
    model = discover_model(args.base_url, args.timeout_seconds)
    runner = VllmRunner(base_url=args.base_url, model=model, timeout=args.timeout_seconds)
    variants = {
        "microphone_only_control": (tuple(0 for _ in range(shared_samples)), microphone, 1.0),
        "production_fixed_headroom": (system, microphone, 1.0),
        "peer_rms_matched_microphone": (system, microphone, peer_gain),
    }
    result_variants: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="moss-lane-level-") as temporary:
        temporary_path = Path(temporary)
        for identifier, (variant_system, raw_microphone, gain) in variants.items():
            scaled_microphone, input_clipped_samples = scale_pcm(raw_microphone, gain)
            mixed, diagnostics = production_mix(variant_system, scaled_microphone, sample_rate=sample_rate, frame_samples=frame_samples)
            wav_path = temporary_path / f"{identifier}.wav"
            write_wav(wav_path, mixed, sample_rate=sample_rate)
            transcription = runner.transcribe(wav_path)
            result_variants[identifier] = {
                "microphone_gain": gain,
                "input_clipped_samples": input_clipped_samples,
                "mixed_audio_sha256": sha256(wav_path),
                "mixer_diagnostics": diagnostics,
                "limited_output_fraction": diagnostics["limited_samples"] / shared_samples,
                "transcription": {
                    "elapsed_seconds": transcription.elapsed_sec,
                    "generated_tokens": transcription.generated_tokens,
                    "text": transcription.text,
                },
                "system_reference_score": score_reference(references["system"], transcription.text),
                "microphone_reference_score": score_reference(references["microphone"], transcription.text),
            }
            print(json.dumps({"variant_complete": identifier, "state": result_variants[identifier]}, indent=2, ensure_ascii=False), flush=True)
    baseline = result_variants["production_fixed_headroom"]
    candidate = result_variants["peer_rms_matched_microphone"]
    microphone_wer_reduction = baseline["microphone_reference_score"]["word_error_rate"] - candidate["microphone_reference_score"]["word_error_rate"]
    microphone_missing_word_reduction = baseline["microphone_reference_score"]["missing_reference_words"] - candidate["microphone_reference_score"]["missing_reference_words"]
    selection = contract["selection_rule"]
    non_distinct_lane_references = references["system"] == references["microphone"]
    candidate_limiter_ok = candidate["limited_output_fraction"] <= baseline["limited_output_fraction"]
    policy_selection = (
        not non_distinct_lane_references
        and microphone_wer_reduction >= selection["minimum_quiet_microphone_wer_reduction_fraction"]
        and microphone_missing_word_reduction > 0
        and candidate_limiter_ok
    )
    result = {
        "schema": "moss-lane-level-prototype-result.v1",
        "preregistration_path": str(preregistration_path.relative_to(ROOT)),
        "preregistration_sha256": sha256(preregistration_path),
        "scope": contract["scope"],
        "inputs": {
            "shared_samples": shared_samples,
            "shared_duration_seconds": shared_samples / sample_rate,
            "system": {"path": system_spec["audio_path"], "sha256": sha256(system_path), "rms": measured_system_rms, "rms_dbfs": 20 * math.log10(measured_system_rms), "peak": PcmTrack(system, sample_rate).peak},
            "microphone": {"path": microphone_spec["audio_path"], "sha256": sha256(microphone_path), "rms": measured_microphone_rms, "rms_dbfs": 20 * math.log10(measured_microphone_rms), "peak": PcmTrack(microphone, sample_rate).peak},
            "rms_difference_db_system_over_microphone": 20 * math.log10(peer_gain),
            "system_reference_sha256": sha256(system_reference_path),
            "system_reference_tokens": len(references["system"]),
            "microphone_reference_sha256": sha256(microphone_reference_path),
            "microphone_reference_tokens": len(references["microphone"]),
        },
        "vllm": {"base_url": args.base_url, "model": model},
        "variants": result_variants,
        "selection": {
            "quiet_microphone_wer_reduction_peer_rms_minus_production": microphone_wer_reduction,
            "quiet_microphone_missing_word_reduction_peer_rms_minus_production": microphone_missing_word_reduction,
            "candidate_limiter_not_worse": candidate_limiter_ok,
            "non_distinct_lane_references": non_distinct_lane_references,
            "production_policy_selected": policy_selection,
            "verdict": "NO_POLICY_SELECTED" if not policy_selection else "CANDIDATE_FOR_SEPARATE_REPLICATION",
            "reason": selection["if_any_requirement_is_missing"] if non_distinct_lane_references else "all preregistered conditions met",
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"complete": True, "output": str(output_path.relative_to(ROOT)), "state": result}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
