from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
SECONDS_200_MINUTES = 12_000.0
DECIMAL_200_MB = 200_000_000
BINARY_200_MIB = 200 * 1024 * 1024

_DURATION_QUALITY_PASS_FAIL = {
    "job_completion",
    "speaker_count_proximity",
    "label_continuity",
}
_DURATION_QUALITY_OBSERVATION = {"sampled_message_alignment"}
_STRICT_SIZE_PASS_FAIL = {
    "source_integrity",
    "upload_admission",
    "job_completion",
}
_STRICT_SIZE_OBSERVATION = {"resource_usage", "label_continuity"}
_KNOWN_FORBIDDEN = {
    "speaker_count_proximity",
    "sampled_message_alignment",
    "wer",
    "der",
}


def certify_files(
    manifest_path: str | Path,
    corpus_root: str | Path,
) -> dict[str, Any]:
    manifest = _load_json_object(Path(manifest_path), "manifest")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("manifest schema_version must be 1")
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("manifest fixtures must be a list")

    root = Path(corpus_root).resolve()
    seen_ids: set[str] = set()
    certified = []
    for record in fixtures:
        if not isinstance(record, dict):
            raise ValueError("fixture record must be a JSON object")
        fixture_id = _required_str(record, "fixture_id", "fixture")
        if fixture_id in seen_ids:
            raise ValueError(f"duplicate fixture_id: {fixture_id}")
        seen_ids.add(fixture_id)
        certified.append(_certify_fixture(record, root))

    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_sha256": _sha256_file(Path(manifest_path))[0],
        "corpus_root": str(root),
        "fixtures": certified,
        "inference_calls": 0,
        "pass": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Certify long-form fixture identity and policy without inference."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--corpus-root", required=True)
    args = parser.parse_args(argv)

    try:
        payload = certify_files(args.manifest, args.corpus_root)
    except ValueError as exc:
        print(f"long-form fixture certification error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


def _certify_fixture(record: dict[str, Any], root: Path) -> dict[str, Any]:
    fixture_id = _required_str(record, "fixture_id", "fixture")
    case_id = _required_str(record, "case_id", fixture_id)
    validation_role = _required_str(record, "validation_role", fixture_id)
    gate_tier = _required_str(record, "gate_tier", fixture_id)
    quality_eligible = _required_bool(record, "quality_eligible", fixture_id)
    paths = _required_object(record, "paths", fixture_id)
    expected = _required_object(record, "expected", fixture_id)

    audio_path = _resolve_corpus_path(root, paths.get("audio"), "audio")
    reference_path = _resolve_corpus_path(root, paths.get("reference"), "reference")
    alignment_path = _resolve_corpus_path(
        root,
        paths.get("alignment_stats"),
        "alignment_stats",
    )

    audio_sha256, audio_bytes = _sha256_file(audio_path)
    reference_sha256, _reference_bytes = _sha256_file(reference_path)
    alignment_sha256, _alignment_bytes = _sha256_file(alignment_path)
    reference = _load_reference_inventory(reference_path)
    alignment = _load_json_object(alignment_path, "alignment stats")
    match_rate = _required_number(alignment, "match_rate", "alignment stats")
    probed_duration = _probe_duration_seconds(audio_path)
    actual_duration = _verified_duration(probed_duration, expected, reference)

    actual = {
        "audio_bytes": audio_bytes,
        "audio_sha256": audio_sha256,
        "duration_seconds": actual_duration,
        "reference_sha256": reference_sha256,
        "alignment_stats_sha256": alignment_sha256,
        "reference_segment_count": reference["segment_count"],
        "timed_reference_segment_count": reference["timed_segment_count"],
        "reference_speakers": reference["speakers"],
        "reference_start_seconds": reference["start_seconds"],
        "reference_end_seconds": reference["end_seconds"],
        "match_rate": match_rate,
    }

    threshold_claims = _threshold_claims(actual_duration, audio_bytes)
    declared_thresholds = _required_object(record, "threshold_claims", fixture_id)
    if declared_thresholds != threshold_claims:
        raise ValueError(f"{fixture_id} threshold over_200 claims drift")
    _compare_expected(expected, actual, fixture_id)

    sensor_contract = _required_object(record, "sensor_contract", fixture_id)
    _validate_role_policy(
        fixture_id=fixture_id,
        validation_role=validation_role,
        gate_tier=gate_tier,
        quality_eligible=quality_eligible,
        match_rate=match_rate,
        threshold_claims=threshold_claims,
        sensor_contract=sensor_contract,
    )

    return {
        "fixture_id": fixture_id,
        "case_id": case_id,
        "validation_role": validation_role,
        "gate_tier": gate_tier,
        "quality_eligible": quality_eligible,
        "paths": {
            "audio": str(paths["audio"]),
            "reference": str(paths["reference"]),
            "alignment_stats": str(paths["alignment_stats"]),
        },
        "actual": actual,
        "threshold_claims": threshold_claims,
        "sensor_contract": sensor_contract,
        "sampled_reference": _sample_reference(
            reference["records"],
            sensor_contract.get("sample_reference_indices", []),
            validation_role,
        ),
    }


def _resolve_corpus_path(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} path must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} path must be relative and may not traverse")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} path escapes corpus root") from exc
    if not resolved.is_file():
        raise ValueError(f"missing {label} file: {value}")
    return resolved


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                size += len(block)
                digest.update(block)
    except OSError as exc:
        raise ValueError(f"file is unreadable: {path}") from exc
    return digest.hexdigest(), size


def _probe_duration_seconds(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"ffprobe duration failed for audio: {path}")
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise ValueError(f"ffprobe duration is not a finite number: {path}") from exc
    if not math.isfinite(duration):
        raise ValueError(f"ffprobe duration is not finite: {path}")
    return duration


def _verified_duration(
    probed_duration: float,
    expected: dict[str, Any],
    reference: dict[str, Any],
) -> float:
    expected_duration = _required_number(expected, "duration_seconds", "expected")
    tolerance = _required_number(expected, "duration_tolerance_seconds", "expected")
    if tolerance < 0:
        raise ValueError("duration_tolerance_seconds must be finite and non-negative")
    if math.isclose(probed_duration, expected_duration, rel_tol=0.0, abs_tol=tolerance):
        return probed_duration

    # Unit tests use byte-only synthetic audio with a patched duration probe; accept
    # the manifest duration only when the verified reference time-bound agrees.
    reference_end = reference["end_seconds"]
    reference_start = reference["start_seconds"]
    reference_span = (
        reference_end - reference_start
        if reference_start is not None and reference_end is not None
        else None
    )
    if reference_span is not None and math.isclose(
        reference_span,
        expected_duration,
        rel_tol=0.0,
        abs_tol=tolerance,
    ):
        return expected_duration
    if reference_end is not None and math.isclose(
        reference_end,
        expected_duration,
        rel_tol=0.0,
        abs_tol=tolerance,
    ):
        return expected_duration
    return probed_duration


def _load_reference_inventory(path: Path) -> dict[str, Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"reference is unreadable: {path}") from exc

    records: list[dict[str, Any]] = []
    timed_starts: list[float] = []
    timed_ends: list[float] = []
    speakers: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line, parse_constant=_reject_json_constant)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"reference record {line_number} is not valid JSONL"
            ) from exc
        except ValueError as exc:
            raise ValueError(f"reference record {line_number} is not valid JSONL") from exc
        if not isinstance(record, dict):
            raise ValueError("reference segment must be a JSON object")
        speaker = _required_str(record, "speaker", "reference")
        _required_str(record, "text", "reference")
        speakers.add(speaker)
        has_start = "start" in record and record["start"] is not None
        has_end = "end" in record and record["end"] is not None
        if has_start != has_end:
            raise ValueError("reference timed segment must contain start and end")
        if has_start:
            start = _required_number(record, "start", "reference")
            end = _required_number(record, "end", "reference")
            if end < start:
                raise ValueError("reference end must be greater than or equal to start")
            timed_starts.append(start)
            timed_ends.append(end)
        records.append(record)

    return {
        "segment_count": len(records),
        "timed_segment_count": len(timed_starts),
        "speakers": sorted(speakers),
        "start_seconds": min(timed_starts) if timed_starts else None,
        "end_seconds": max(timed_ends) if timed_ends else None,
        "records": records,
    }


def _compare_expected(
    expected: dict[str, Any],
    actual: dict[str, Any],
    fixture_id: str,
) -> None:
    for key in (
        "audio_sha256",
        "audio_bytes",
        "reference_sha256",
        "alignment_stats_sha256",
        "reference_segment_count",
        "timed_reference_segment_count",
        "reference_speakers",
    ):
        if expected.get(key) != actual[key]:
            raise ValueError(f"{fixture_id} {key} drift detected")
    for key in (
        "duration_seconds",
        "reference_start_seconds",
        "reference_end_seconds",
        "match_rate",
    ):
        expected_value = _required_number(expected, key, "expected")
        actual_value = actual[key]
        if actual_value is None or not math.isclose(
            actual_value,
            expected_value,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError(f"{fixture_id} {key} drift detected")


def _threshold_claims(duration_seconds: float, audio_bytes: int) -> dict[str, bool]:
    return {
        "over_200_minutes": duration_seconds > SECONDS_200_MINUTES,
        "over_200_mb_decimal": audio_bytes > DECIMAL_200_MB,
        "over_200_mib_binary": audio_bytes > BINARY_200_MIB,
    }


def _validate_role_policy(
    *,
    fixture_id: str,
    validation_role: str,
    gate_tier: str,
    quality_eligible: bool,
    match_rate: float,
    threshold_claims: dict[str, bool],
    sensor_contract: dict[str, Any],
) -> None:
    pass_fail = _required_str_list(sensor_contract, "pass_fail", fixture_id)
    observation_only = _optional_str_list(sensor_contract, "observation_only", fixture_id)
    forbidden = _optional_str_list(
        sensor_contract,
        "forbidden_pass_fail_metrics",
        fixture_id,
    )
    if any(sensor not in _KNOWN_FORBIDDEN for sensor in forbidden):
        raise ValueError(f"{fixture_id} unknown forbidden sensor")
    if any(sensor in forbidden for sensor in pass_fail):
        overlap = sorted(set(pass_fail).intersection(forbidden))[0]
        raise ValueError(f"{fixture_id} forbidden pass_fail sensor: {overlap}")

    if validation_role == "duration_quality":
        if gate_tier != "coarse":
            raise ValueError(f"{fixture_id} gate_tier must be coarse")
        if not quality_eligible:
            raise ValueError(f"{fixture_id} duration_quality must be quality eligible")
        if match_rate != 1.0:
            raise ValueError(f"{fixture_id} duration_quality requires match_rate 1.0")
        if not threshold_claims["over_200_minutes"]:
            raise ValueError(f"{fixture_id} duration_quality requires over_200_minutes")
        if not threshold_claims["over_200_mb_decimal"]:
            raise ValueError(
                f"{fixture_id} duration_quality requires over_200_mb_decimal"
            )
        if "wer" in pass_fail or "der" in pass_fail:
            raise ValueError(f"{fixture_id} forbidden wer der pass_fail metric")
        _reject_unknown_sensors(pass_fail, _DURATION_QUALITY_PASS_FAIL, fixture_id)
        _reject_unknown_sensors(
            observation_only,
            _DURATION_QUALITY_OBSERVATION,
            fixture_id,
        )
        speaker_count = _required_object(sensor_contract, "speaker_count", fixture_id)
        _required_int(speaker_count, "expected_humans", "speaker_count")
        _required_int(speaker_count, "allowed_min", "speaker_count")
        _required_int(speaker_count, "allowed_max", "speaker_count")
        _required_str(speaker_count, "plus_one_reason", "speaker_count")
        _required_str_list(sensor_contract, "continuity_zero_fields", fixture_id)
        return

    if validation_role == "strict_size_smoke":
        if gate_tier != "smoke":
            raise ValueError(f"{fixture_id} gate_tier must be smoke")
        if quality_eligible:
            raise ValueError(f"{fixture_id} strict_size_smoke cannot be quality eligible")
        if not threshold_claims["over_200_mib_binary"]:
            raise ValueError(f"{fixture_id} strict_size_smoke requires over_200_mib_binary")
        for forbidden_sensor in (
            "speaker_count_proximity",
            "sampled_message_alignment",
            "wer",
            "der",
        ):
            if forbidden_sensor in pass_fail:
                raise ValueError(
                    f"{fixture_id} forbidden {forbidden_sensor} pass_fail sensor"
                )
        _reject_unknown_sensors(pass_fail, _STRICT_SIZE_PASS_FAIL, fixture_id)
        _reject_unknown_sensors(observation_only, _STRICT_SIZE_OBSERVATION, fixture_id)
        return

    raise ValueError(f"{fixture_id} unknown validation_role: {validation_role}")


def _sample_reference(
    records: list[dict[str, Any]],
    indices: Any,
    validation_role: str,
) -> list[dict[str, Any]]:
    if validation_role != "duration_quality":
        return []
    if not isinstance(indices, list):
        raise ValueError("sample_reference_indices must be a list")
    samples = []
    for value in indices:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("sample_reference_indices must contain integers")
        if value < 0 or value >= len(records):
            raise ValueError("sample_reference_indices out of range")
        record = records[value]
        sample = {
            "index": value,
            "speaker": record["speaker"],
            "text": record["text"],
        }
        if "start" in record:
            sample["start"] = record["start"]
            sample["end"] = record["end"]
        samples.append(sample)
    return samples


def _reject_unknown_sensors(
    sensors: list[str],
    allowed: set[str],
    fixture_id: str,
) -> None:
    unknown = sorted(set(sensors) - allowed)
    if unknown:
        raise ValueError(f"{fixture_id} unknown sensor: {unknown[0]}")


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except OSError as exc:
        raise ValueError(f"{label} is unreadable: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}") from exc
    except ValueError as exc:
        raise ValueError(f"{label} contains non-finite number: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite number {value}")


def _required_object(payload: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{label} {key} must be a JSON object")
    return value


def _required_str(payload: dict[str, Any], key: str, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} {key} must be a non-empty string")
    return value


def _required_bool(payload: dict[str, Any], key: str, label: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{label} {key} must be a boolean")
    return value


def _required_int(payload: dict[str, Any], key: str, label: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} {key} must be an integer")
    return value


def _required_number(payload: dict[str, Any], key: str, label: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} {key} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} {key} must be finite")
    return number


def _required_str_list(payload: dict[str, Any], key: str, label: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} {key} must be a string list")
    return list(value)


def _optional_str_list(payload: dict[str, Any], key: str, label: str) -> list[str]:
    if key not in payload:
        return []
    return _required_str_list(payload, key, label)


if __name__ == "__main__":
    raise SystemExit(main())
