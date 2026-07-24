from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from moss_transcribe_diarize.app.live_session import LIVE_SAMPLE_RATE


TRUTH_SCHEMA_VERSION = 1
CANDIDATE_SCHEMA_VERSION = 1
DEVELOPMENT_60S_PHASE = "development_60s"
HOLDOUT_300S_PHASE = "holdout_300s"
DEVELOPMENT_60S_SAMPLES = 60 * LIVE_SAMPLE_RATE
HOLDOUT_300S_SAMPLES = 300 * LIVE_SAMPLE_RATE
END_SILENCE_REASON = "end_silence"


class LiveVadTruthError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LiveVadTruthInterval:
    start_sample: int
    end_sample: int

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, field: str) -> "LiveVadTruthInterval":
        return cls(
            start_sample=_required_int(payload, "start_sample", field=field),
            end_sample=_required_int(payload, "end_sample", field=field),
        )

    @property
    def sample_count(self) -> int:
        return self.end_sample - self.start_sample


@dataclass(frozen=True, slots=True)
class LiveVadTruth:
    fixture_sha256: str
    fixture_sample_count: int
    annotation_provenance: str
    review_provenance: str
    speech_intervals: tuple[LiveVadTruthInterval, ...]
    non_speech_intervals: tuple[LiveVadTruthInterval, ...]
    safe_end_intervals: tuple[LiveVadTruthInterval, ...]
    uncertain_intervals: tuple[LiveVadTruthInterval, ...] = ()
    provider_blind: bool = True
    fixture_sample_rate: int = LIVE_SAMPLE_RATE
    schema_version: int = TRUTH_SCHEMA_VERSION

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "LiveVadTruth":
        if _required_int(payload, "schema_version", field="truth") != TRUTH_SCHEMA_VERSION:
            raise LiveVadTruthError("unsupported truth schema_version.")
        truth = cls(
            fixture_sha256=_required_sha256(payload, "fixture_sha256", field="truth"),
            fixture_sample_count=_required_positive_int(payload, "fixture_sample_count", field="truth"),
            fixture_sample_rate=_required_int(payload, "fixture_sample_rate", field="truth"),
            annotation_provenance=_required_str(payload, "annotation_provenance", field="truth"),
            review_provenance=_required_str(payload, "review_provenance", field="truth"),
            provider_blind=bool(payload.get("provider_blind", False)),
            speech_intervals=_intervals(payload, "speech_intervals"),
            non_speech_intervals=_intervals(payload, "non_speech_intervals"),
            safe_end_intervals=_intervals(payload, "safe_end_intervals"),
            uncertain_intervals=_intervals(payload, "uncertain_intervals"),
        )
        validate_live_vad_truth(truth)
        return truth

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LiveVadCandidateObservation:
    start_sample: int
    end_sample: int
    speech_present: bool

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, field: str) -> "LiveVadCandidateObservation":
        return cls(
            start_sample=_required_int(payload, "start_sample", field=field),
            end_sample=_required_int(payload, "end_sample", field=field),
            speech_present=bool(payload.get("speech_present", False)),
        )


@dataclass(frozen=True, slots=True)
class LiveVadCandidateEndpoint:
    start_sample: int
    end_sample: int
    reason: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, field: str) -> "LiveVadCandidateEndpoint":
        return cls(
            start_sample=_required_int(payload, "start_sample", field=field),
            end_sample=_required_int(payload, "end_sample", field=field),
            reason=_required_str(payload, "reason", field=field),
        )


@dataclass(frozen=True, slots=True)
class LiveVadCandidate:
    name: str
    config_hash: str
    fixture_sha256: str
    observations: tuple[LiveVadCandidateObservation, ...]
    endpoint_spans: tuple[LiveVadCandidateEndpoint, ...] = ()
    schema_version: int = CANDIDATE_SCHEMA_VERSION

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "LiveVadCandidate":
        if _required_int(payload, "schema_version", field="candidate") != CANDIDATE_SCHEMA_VERSION:
            raise LiveVadTruthError("unsupported candidate schema_version.")
        return cls(
            name=_required_str(payload, "name", field="candidate"),
            config_hash=_required_sha256(payload, "config_hash", field="candidate"),
            fixture_sha256=_required_sha256(payload, "fixture_sha256", field="candidate"),
            observations=tuple(
                LiveVadCandidateObservation.from_mapping(_as_mapping(item, "observations[]"), field="observations[]")
                for item in _required_sequence(payload, "observations", field="candidate")
            ),
            endpoint_spans=tuple(
                LiveVadCandidateEndpoint.from_mapping(_as_mapping(item, "endpoint_spans[]"), field="endpoint_spans[]")
                for item in payload.get("endpoint_spans", ())
            ),
        )


def validate_live_vad_truth(truth: LiveVadTruth) -> LiveVadTruth:
    if truth.schema_version != TRUTH_SCHEMA_VERSION:
        raise LiveVadTruthError("unsupported truth schema_version.")
    if truth.fixture_sample_rate != LIVE_SAMPLE_RATE:
        raise LiveVadTruthError("truth fixture_sample_rate must be 16000.")
    if not truth.provider_blind:
        raise LiveVadTruthError("truth must be provider blind.")
    if truth.annotation_provenance == truth.review_provenance:
        raise LiveVadTruthError("annotation and review provenance must be independent.")
    for name, intervals in _truth_interval_groups(truth).items():
        _validate_interval_list(intervals, field=name, upper_bound=truth.fixture_sample_count)
    _validate_partition(
        speech=truth.speech_intervals,
        non_speech=truth.non_speech_intervals,
        uncertain=truth.uncertain_intervals,
        sample_count=truth.fixture_sample_count,
    )
    for safe_end in truth.safe_end_intervals:
        if not _is_covered_by(safe_end, truth.non_speech_intervals):
            raise LiveVadTruthError("safe_end_intervals must be inside non_speech_intervals.")
    return truth


def compare_live_provider_candidates(
    truth: LiveVadTruth | Mapping[str, Any],
    candidates: Sequence[LiveVadCandidate | Mapping[str, Any]],
    *,
    phase: str,
    locked_config_hash: str | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    truth_obj = truth if isinstance(truth, LiveVadTruth) else LiveVadTruth.from_mapping(truth)
    validate_live_vad_truth(truth_obj)
    candidate_objs = tuple(candidate if isinstance(candidate, LiveVadCandidate) else LiveVadCandidate.from_mapping(candidate) for candidate in candidates)
    if not candidate_objs:
        raise LiveVadTruthError("at least one candidate is required.")
    _validate_phase_contract(truth_obj, phase=phase, locked_config_hash=locked_config_hash)
    limits = {
        "min_speech_recall": 0.95,
        "max_false_positive_rate": 0.05,
        "min_safe_end_recall": 1.0,
        **dict(thresholds or {}),
    }
    results = tuple(_score_candidate(truth_obj, candidate, phase=phase, locked_config_hash=locked_config_hash, thresholds=limits) for candidate in candidate_objs)
    accepted = tuple(item for item in results if item["accepted"])
    best = max(results, key=lambda item: (item["accepted"], item["metrics"]["speech_recall"], -item["metrics"]["false_positive_rate"]))
    return {
        "schema_version": 1,
        "phase": phase,
        "fixture_sha256": truth_obj.fixture_sha256,
        "locked_config_hash": _locked_hash_for_phase(phase, accepted, best, locked_config_hash),
        "results": list(results),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate provider-blind live VAD truth and compare candidates.")
    parser.add_argument("--truth", required=True, help="Provider-blind truth JSON file.")
    parser.add_argument("--candidate", action="append", default=[], help="Candidate JSON file. Repeat for multiple candidates.")
    parser.add_argument("--phase", required=True, choices=[DEVELOPMENT_60S_PHASE, HOLDOUT_300S_PHASE])
    parser.add_argument("--locked-config-hash", default=None, help="Required exact config hash for holdout.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    args = parser.parse_args(argv)

    truth = LiveVadTruth.from_mapping(_load_json(Path(args.truth)))
    candidates = [LiveVadCandidate.from_mapping(_load_json(Path(path))) for path in args.candidate]
    result = compare_live_provider_candidates(
        truth,
        candidates,
        phase=args.phase,
        locked_config_hash=args.locked_config_hash,
    )
    if args.json:
        print(json.dumps(result, sort_keys=True, indent=2))
    else:
        print(f"{result['phase']} locked_config_hash={result['locked_config_hash'] or 'none'}")
    return 0 if any(item["accepted"] for item in result["results"]) else 1


def _score_candidate(
    truth: LiveVadTruth,
    candidate: LiveVadCandidate,
    *,
    phase: str,
    locked_config_hash: str | None,
    thresholds: Mapping[str, float],
) -> dict[str, Any]:
    failures = _candidate_failures(truth, candidate)
    if phase == HOLDOUT_300S_PHASE and candidate.config_hash != locked_config_hash:
        failures.append("holdout candidate config_hash does not match locked_config_hash")
    confusion = _confusion(truth, candidate.observations) if not failures else {"tp": 0, "fn": 0, "tn": 0, "fp": 0}
    speech_total = confusion["tp"] + confusion["fn"]
    non_speech_total = confusion["tn"] + confusion["fp"]
    speech_recall = 1.0 if speech_total == 0 else confusion["tp"] / speech_total
    false_positive_rate = 0.0 if non_speech_total == 0 else confusion["fp"] / non_speech_total
    safe_end = _safe_end_result(truth, candidate.endpoint_spans)
    if speech_recall < thresholds["min_speech_recall"]:
        failures.append("speech_recall below threshold")
    if false_positive_rate > thresholds["max_false_positive_rate"]:
        failures.append("false_positive_rate above threshold")
    if safe_end["recall"] < thresholds["min_safe_end_recall"]:
        failures.append("safe_end_recall below threshold")
    return {
        "name": candidate.name,
        "config_hash": candidate.config_hash,
        "accepted": not failures,
        "failures": failures,
        "confusion": confusion,
        "metrics": {
            "speech_recall": speech_recall,
            "false_positive_rate": false_positive_rate,
        },
        "safe_end": safe_end,
        "scored_samples": speech_total + non_speech_total,
        "uncertain_samples_excluded": sum(interval.sample_count for interval in truth.uncertain_intervals),
    }


def _candidate_failures(truth: LiveVadTruth, candidate: LiveVadCandidate) -> list[str]:
    failures: list[str] = []
    if candidate.fixture_sha256 != truth.fixture_sha256:
        failures.append("candidate fixture_sha256 mismatch")
    try:
        _validate_interval_list(candidate.observations, field="observations", upper_bound=truth.fixture_sample_count)
        _validate_partition(
            speech=tuple(item for item in candidate.observations if item.speech_present),
            non_speech=tuple(item for item in candidate.observations if not item.speech_present),
            uncertain=(),
            sample_count=truth.fixture_sample_count,
        )
    except LiveVadTruthError as exc:
        failures.append(str(exc))
    try:
        _validate_interval_list(candidate.endpoint_spans, field="endpoint_spans", upper_bound=truth.fixture_sample_count)
    except LiveVadTruthError as exc:
        failures.append(str(exc))
    return failures


def _confusion(truth: LiveVadTruth, observations: tuple[LiveVadCandidateObservation, ...]) -> dict[str, int]:
    predicted_speech = tuple(_interval(item.start_sample, item.end_sample) for item in observations if item.speech_present)
    predicted_non_speech = tuple(_interval(item.start_sample, item.end_sample) for item in observations if not item.speech_present)
    return {
        "tp": _intersection_total(truth.speech_intervals, predicted_speech),
        "fn": _intersection_total(truth.speech_intervals, predicted_non_speech),
        "tn": _intersection_total(truth.non_speech_intervals, predicted_non_speech),
        "fp": _intersection_total(truth.non_speech_intervals, predicted_speech),
    }


def _safe_end_result(truth: LiveVadTruth, endpoints: tuple[LiveVadCandidateEndpoint, ...]) -> dict[str, Any]:
    matched = 0
    wrong_reason = 0
    for target in truth.safe_end_intervals:
        exact = [item for item in endpoints if target.start_sample <= item.end_sample <= target.end_sample]
        if any(item.reason == END_SILENCE_REASON for item in exact):
            matched += 1
        elif exact:
            wrong_reason += 1
    total = len(truth.safe_end_intervals)
    return {
        "matched": matched,
        "total": total,
        "wrong_reason": wrong_reason,
        "recall": 1.0 if total == 0 else matched / total,
    }


def _validate_phase_contract(truth: LiveVadTruth, *, phase: str, locked_config_hash: str | None) -> None:
    if phase == DEVELOPMENT_60S_PHASE:
        if truth.fixture_sample_count != DEVELOPMENT_60S_SAMPLES:
            raise LiveVadTruthError("development_60s phase requires a 60-second fixture.")
        if locked_config_hash is not None:
            raise LiveVadTruthError("development_60s phase produces, not accepts, a locked config hash.")
        return
    if phase == HOLDOUT_300S_PHASE:
        if truth.fixture_sample_count != HOLDOUT_300S_SAMPLES:
            raise LiveVadTruthError("holdout_300s phase requires a 300-second fixture.")
        if locked_config_hash is None:
            raise LiveVadTruthError("holdout_300s phase requires locked_config_hash.")
        _required_sha256({"locked_config_hash": locked_config_hash}, "locked_config_hash", field="phase")
        return
    raise LiveVadTruthError(f"unsupported phase: {phase}")


def _locked_hash_for_phase(
    phase: str,
    accepted: tuple[dict[str, Any], ...],
    best: dict[str, Any],
    locked_config_hash: str | None,
) -> str | None:
    if phase == HOLDOUT_300S_PHASE:
        return locked_config_hash
    if phase == DEVELOPMENT_60S_PHASE and accepted and best["accepted"]:
        return str(best["config_hash"])
    return None


def _validate_interval_list(items: Sequence[Any], *, field: str, upper_bound: int) -> None:
    cursor = -1
    for item in items:
        if item.start_sample < 0:
            raise LiveVadTruthError(f"{field} start_sample must be non-negative.")
        if item.end_sample <= item.start_sample:
            raise LiveVadTruthError(f"{field} end_sample must advance.")
        if item.end_sample > upper_bound:
            raise LiveVadTruthError(f"{field} exceeds fixture_sample_count.")
        if item.start_sample < cursor:
            raise LiveVadTruthError(f"{field} must be ordered and non-overlapping.")
        cursor = item.end_sample


def _validate_partition(
    *,
    speech: tuple[Any, ...],
    non_speech: tuple[Any, ...],
    uncertain: tuple[Any, ...],
    sample_count: int,
) -> None:
    labeled = sorted(
        [("speech", item) for item in speech]
        + [("non_speech", item) for item in non_speech]
        + [("uncertain", item) for item in uncertain],
        key=lambda item: (item[1].start_sample, item[1].end_sample, item[0]),
    )
    cursor = 0
    for label, item in labeled:
        if item.start_sample != cursor:
            raise LiveVadTruthError(f"{label} intervals do not form an exact fixture partition.")
        cursor = item.end_sample
    if cursor != sample_count:
        raise LiveVadTruthError("truth intervals do not cover fixture_sample_count.")


def _is_covered_by(target: LiveVadTruthInterval, intervals: tuple[LiveVadTruthInterval, ...]) -> bool:
    return any(item.start_sample <= target.start_sample and target.end_sample <= item.end_sample for item in intervals)


def _intersection_total(left: tuple[Any, ...], right: tuple[Any, ...]) -> int:
    total = 0
    i = 0
    j = 0
    while i < len(left) and j < len(right):
        a = left[i]
        b = right[j]
        total += max(0, min(a.end_sample, b.end_sample) - max(a.start_sample, b.start_sample))
        if a.end_sample <= b.end_sample:
            i += 1
        else:
            j += 1
    return total


def _interval(start_sample: int, end_sample: int) -> LiveVadTruthInterval:
    return LiveVadTruthInterval(start_sample=start_sample, end_sample=end_sample)


def _truth_interval_groups(truth: LiveVadTruth) -> dict[str, tuple[LiveVadTruthInterval, ...]]:
    return {
        "speech_intervals": truth.speech_intervals,
        "non_speech_intervals": truth.non_speech_intervals,
        "safe_end_intervals": truth.safe_end_intervals,
        "uncertain_intervals": truth.uncertain_intervals,
    }


def _intervals(payload: Mapping[str, Any], key: str) -> tuple[LiveVadTruthInterval, ...]:
    return tuple(
        LiveVadTruthInterval.from_mapping(_as_mapping(item, f"{key}[]"), field=f"{key}[]")
        for item in payload.get(key, ())
    )


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LiveVadTruthError(f"file is not readable: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LiveVadTruthError(f"file is not valid JSON: {path}") from exc
    return _as_mapping(payload, str(path))


def _as_mapping(payload: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise LiveVadTruthError(f"{field} must be an object.")
    return payload


def _required_sequence(payload: Mapping[str, Any], key: str, *, field: str) -> Sequence[Any]:
    value = payload.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise LiveVadTruthError(f"{field}.{key} must be a list.")
    return value


def _required_int(payload: Mapping[str, Any], key: str, *, field: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise LiveVadTruthError(f"{field}.{key} must be an integer.")
    return value


def _required_positive_int(payload: Mapping[str, Any], key: str, *, field: str) -> int:
    value = _required_int(payload, key, field=field)
    if value <= 0:
        raise LiveVadTruthError(f"{field}.{key} must be positive.")
    return value


def _required_str(payload: Mapping[str, Any], key: str, *, field: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LiveVadTruthError(f"{field}.{key} must be a non-empty string.")
    return value


def _required_sha256(payload: Mapping[str, Any], key: str, *, field: str) -> str:
    value = _required_str(payload, key, field=field)
    if len(value) != 64 or any(item not in "0123456789abcdef" for item in value):
        raise LiveVadTruthError(f"{field}.{key} must be a lowercase sha256 hex string.")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
