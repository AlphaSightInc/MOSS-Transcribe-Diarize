#!/usr/bin/env python3
"""PROTOTYPE — measure durable MOSS voice-profile matching; never production code.

Question: on production WeSpeaker ResNet152 ONNX embeddings and live-path evidence units,
what score/margin/evidence rule recognizes an enrolled name while abstaining from other
people?  The script prints the complete evaluated state as JSON.

One-command fresh run from the repository root:

  prototypes/streaming-diarization/.venv/bin/python \
    prototypes/streaming-diarization/voice-profile-matching/prototype_voice_profile_match.py \
    --fresh
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
REPO = BENCH.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(BENCH))

from matching_rule import MatchDecision, decide, normalized_mean  # noqa: E402
import proto_ab_identity as harness  # noqa: E402

MODEL_SHA256 = "5b734353b4b410e222bbd124dd095537642237ad895727d18a3b9fee330262a8"
ENROLLMENT_WINDOWS = ((0.0, 300.0), (300.0, 600.0), (600.0, 900.0))
PROBE_START_SECONDS = 900.0
TERMINAL_WINDOW_SECONDS = 300.0
EVIDENCE_FLOORS = (0.5, 1.0, 2.0)
SCORE_THRESHOLDS = tuple(round(0.30 + index * 0.01, 2) for index in range(51))
MARGINS = (0.0, 0.05, 0.10, 0.15, 0.20)
AGGREGATIONS = ("arithmetic_mean", "duration_weighted_mean")


@dataclass(frozen=True, slots=True)
class Case:
    case_id: str
    root: Path


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    case_id: str
    speaker_name: str
    profile_id: str
    span_id: int
    start_sec: float
    end_sec: float
    evidence_seconds: float
    vector: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ProfileSample:
    window_start_sec: float
    window_end_sec: float
    sample_seconds: float
    exemplar_count: int
    vector: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class Profile:
    profile_id: str
    case_id: str
    speaker_name: str
    samples: tuple[ProfileSample, ...]
    arithmetic_mean: tuple[float, ...]
    duration_weighted_mean: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ScoredObservation:
    observation_id: str
    surface: str
    case_id: str
    speaker_name: str
    true_profile_id: str
    start_sec: float
    end_sec: float
    evidence_seconds: float
    scores: dict[str, float]


def load_album_module():
    path = REPO / "moss_transcribe_diarize" / "app" / "live_identity_album.py"
    spec = importlib.util.spec_from_file_location("voice_profile_album_production", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load production album module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def cases() -> tuple[Case, ...]:
    root = BENCH / "data" / "real" / "benchmark_30m"
    return (
        Case("acquired_jamie_dimon", root / "acquired_jamie_dimon"),
        Case("lex_bill_ackman", root / "lex_bill_ackman"),
    )


def load_truth(case: Case) -> tuple[list[tuple[float, float, int]], dict[int, str]]:
    speakers: dict[str, int] = {}
    truth: list[tuple[float, float, int]] = []
    previous_end = 0.0
    for raw in (case.root / "reference.jsonl").read_text().splitlines():
        if not raw.strip():
            continue
        segment = json.loads(raw)
        name = str(segment["speaker"])
        speaker_id = speakers.setdefault(name, len(speakers))
        start = max(float(segment["start"]), previous_end)
        end = float(segment["end"])
        if end <= start:
            continue
        truth.append((start, end, speaker_id))
        previous_end = end
    return truth, {speaker_id: name for name, speaker_id in speakers.items()}


def extract_fresh(case: Case, adapter: Any) -> dict[str, np.ndarray]:
    truth, _ = load_truth(case)
    pieces = harness.plan_spans(truth)
    groups: dict[tuple[int, int], list[Any]] = defaultdict(list)
    for piece in pieces:
        groups[(piece.span, piece.true_spk)].append(piece)
    vectors: list[np.ndarray] = []
    vector_indices: list[int] = []
    rows: list[tuple[float, ...]] = []
    total = len(groups)
    for ordinal, ((span_id, speaker_id), group) in enumerate(sorted(groups.items()), start=1):
        usable = [piece for piece in group if piece.dur >= harness.MIN_EVID]
        duration = sum(piece.dur for piece in usable) or sum(piece.dur for piece in group)
        eligible = bool(usable)
        if eligible:
            vector = adapter.embed(
                case.root / "audio.wav",
                [(piece.start, piece.end) for piece in usable],
            )
            vectors.append(np.asarray(vector, dtype=np.float32))
            vector_indices.append(len(vectors) - 1)
        else:
            vector_indices.append(-1)
        rows.append(
            (
                float(span_id),
                float(speaker_id),
                min(piece.start for piece in group),
                max(piece.end for piece in group),
                float(duration),
                float(eligible),
            )
        )
        if ordinal == 1 or ordinal % 100 == 0 or ordinal == total:
            print(
                f"fresh embedding {case.case_id}: {ordinal}/{total} evidence groups",
                file=sys.stderr,
                flush=True,
            )
    return {
        "vecs": np.stack(vectors) if vectors else np.zeros((0, 256), dtype=np.float32),
        "vec_idx": np.asarray(vector_indices, dtype=np.int64),
        "rows": np.asarray(rows, dtype=np.float64),
    }


def load_cached(case: Case) -> dict[str, np.ndarray]:
    with np.load(case.root / "harness_cache.npz", allow_pickle=False) as payload:
        cache = {key: np.asarray(payload[key]) for key in payload.files}
    eligible = cache["rows"][:, 5] > 0
    cache["vec_idx"] = np.where(eligible, np.cumsum(eligible) - 1, -1).astype(np.int64)
    return cache


def evidence_from_cache(case: Case, cache: dict[str, np.ndarray]) -> list[Evidence]:
    _, speaker_names = load_truth(case)
    observations: list[Evidence] = []
    for row_index, row in enumerate(cache["rows"]):
        vector_index = int(cache["vec_idx"][row_index])
        if row[5] <= 0 or vector_index < 0:
            continue
        speaker_name = speaker_names[int(row[1])]
        profile_id = f"{case.case_id}:{speaker_name}"
        observations.append(
            Evidence(
                evidence_id=f"{case.case_id}:row-{row_index}",
                case_id=case.case_id,
                speaker_name=speaker_name,
                profile_id=profile_id,
                span_id=int(row[0]),
                start_sec=float(row[2]),
                end_sec=float(row[3]),
                evidence_seconds=float(row[4]),
                vector=tuple(float(value) for value in cache["vecs"][vector_index]),
            )
        )
    return observations


def album_sample(
    album_module: Any,
    profile_id: str,
    observations: Sequence[Evidence],
    *,
    window_start: float,
    window_end: float,
) -> ProfileSample | None:
    album = album_module.FingerprintAlbum()
    selected = [
        observation
        for observation in observations
        if observation.profile_id == profile_id
        and observation.start_sec >= window_start
        and observation.end_sec <= window_end
    ]
    for observation in selected:
        album.observe(
            canonical_speaker=profile_id,
            vector=observation.vector,
            duration_sec=observation.evidence_seconds,
            span_id=observation.span_id,
        )
    if album.exemplar_count(profile_id) == 0:
        return None
    vector = album.reference(profile_id)
    support = album.exemplars(profile_id)
    if vector is None:
        return None
    return ProfileSample(
        window_start_sec=window_start,
        window_end_sec=window_end,
        sample_seconds=sum(item.duration_sec for item in support),
        exemplar_count=len(support),
        vector=tuple(float(value) for value in vector),
    )


def build_profiles(album_module: Any, evidence: Sequence[Evidence]) -> dict[str, Profile]:
    profiles: dict[str, Profile] = {}
    by_profile: dict[str, list[Evidence]] = defaultdict(list)
    for observation in evidence:
        by_profile[observation.profile_id].append(observation)
    for profile_id, observations in sorted(by_profile.items()):
        samples = tuple(
            sample
            for window_start, window_end in ENROLLMENT_WINDOWS
            if (
                sample := album_sample(
                    album_module,
                    profile_id,
                    observations,
                    window_start=window_start,
                    window_end=window_end,
                )
            )
            is not None
        )
        if not samples:
            continue
        arithmetic = normalized_mean([sample.vector for sample in samples])
        weighted_support = [
            album_module.AlbumExemplar(
                vector=sample.vector,
                duration_sec=sample.sample_seconds,
                span_id=index,
            )
            for index, sample in enumerate(samples)
        ]
        duration_weighted = album_module.duration_weighted_centroid(weighted_support)
        if duration_weighted is None:
            raise RuntimeError(f"profile aggregation failed: {profile_id}")
        first = observations[0]
        profiles[profile_id] = Profile(
            profile_id=profile_id,
            case_id=first.case_id,
            speaker_name=first.speaker_name,
            samples=samples,
            arithmetic_mean=arithmetic,
            duration_weighted_mean=tuple(float(value) for value in duration_weighted),
        )
    return profiles


def profile_vector(profile: Profile, aggregation: str) -> tuple[float, ...]:
    return getattr(profile, aggregation)


def score_vector(
    album_module: Any,
    vector: Sequence[float],
    profiles: dict[str, Profile],
    aggregation: str,
) -> dict[str, float]:
    result: dict[str, float] = {}
    for profile_id, profile in profiles.items():
        score = album_module.cosine_similarity(vector, profile_vector(profile, aggregation))
        if score is None:
            raise RuntimeError(f"undefined profile score: {profile_id}")
        result[profile_id] = float(score)
    return result


def causal_observations(
    album_module: Any,
    evidence: Sequence[Evidence],
    profiles: dict[str, Profile],
    aggregation: str,
) -> list[ScoredObservation]:
    return [
        ScoredObservation(
            observation_id=observation.evidence_id,
            surface="causal_live_evidence_unit",
            case_id=observation.case_id,
            speaker_name=observation.speaker_name,
            true_profile_id=observation.profile_id,
            start_sec=observation.start_sec,
            end_sec=observation.end_sec,
            evidence_seconds=observation.evidence_seconds,
            scores=score_vector(album_module, observation.vector, profiles, aggregation),
        )
        for observation in evidence
        if observation.start_sec >= PROBE_START_SECONDS and observation.profile_id in profiles
    ]


def terminal_observations(
    album_module: Any,
    evidence: Sequence[Evidence],
    profiles: dict[str, Profile],
    aggregation: str,
) -> list[ScoredObservation]:
    result: list[ScoredObservation] = []
    by_case: dict[str, list[Evidence]] = defaultdict(list)
    for observation in evidence:
        by_case[observation.case_id].append(observation)
    for case_id, case_evidence in sorted(by_case.items()):
        case_end = max(observation.end_sec for observation in case_evidence)
        window_start = PROBE_START_SECONDS
        while window_start < case_end:
            window_end = min(window_start + TERMINAL_WINDOW_SECONDS, case_end + 1e-9)
            profile_ids = sorted({
                observation.profile_id
                for observation in case_evidence
                if observation.start_sec >= window_start and observation.end_sec <= window_end
            })
            for profile_id in profile_ids:
                sample = album_sample(
                    album_module,
                    profile_id,
                    case_evidence,
                    window_start=window_start,
                    window_end=window_end,
                )
                if sample is None:
                    continue
                profile = profiles.get(profile_id)
                if profile is None:
                    continue
                result.append(
                    ScoredObservation(
                        observation_id=(
                            f"{case_id}:terminal-{window_start:.0f}-{window_end:.0f}:"
                            f"{profile.speaker_name}"
                        ),
                        surface="terminal_truth_aligned_album_opportunity",
                        case_id=case_id,
                        speaker_name=profile.speaker_name,
                        true_profile_id=profile_id,
                        start_sec=window_start,
                        end_sec=window_end,
                        evidence_seconds=sample.sample_seconds,
                        scores=score_vector(album_module, sample.vector, profiles, aggregation),
                    )
                )
            window_start += TERMINAL_WINDOW_SECONDS
    return result


def evaluate_surface(
    observations: Sequence[ScoredObservation],
    *,
    minimum_score: float,
    minimum_margin: float,
    evidence_floor: float,
) -> dict[str, int | float]:
    counts = Counter(
        known_total=len(observations),
        known_eligible=0,
        known_correct=0,
        known_wrong_name=0,
        known_abstain=0,
        unknown_total=len(observations),
        unknown_eligible=0,
        unknown_false_name=0,
        unknown_abstain=0,
    )
    for observation in observations:
        if observation.evidence_seconds < evidence_floor:
            counts["known_abstain"] += 1
            counts["unknown_abstain"] += 1
            continue
        counts["known_eligible"] += 1
        counts["unknown_eligible"] += 1
        known = decide(
            observation.scores,
            minimum_score=minimum_score,
            minimum_margin=minimum_margin,
        )
        if known.profile_id is None:
            counts["known_abstain"] += 1
        elif known.profile_id == observation.true_profile_id:
            counts["known_correct"] += 1
        else:
            counts["known_wrong_name"] += 1
        unknown_scores = {
            profile_id: score
            for profile_id, score in observation.scores.items()
            if profile_id != observation.true_profile_id
        }
        unknown = decide(
            unknown_scores,
            minimum_score=minimum_score,
            minimum_margin=minimum_margin,
        )
        if unknown.profile_id is None:
            counts["unknown_abstain"] += 1
        else:
            counts["unknown_false_name"] += 1
    result: dict[str, int | float] = dict(counts)
    result["known_correct_rate"] = counts["known_correct"] / max(1, counts["known_total"])
    result["unknown_abstention_rate"] = counts["unknown_abstain"] / max(1, counts["unknown_total"])
    return result


def operating_points(
    causal_by_aggregation: dict[str, list[ScoredObservation]],
    terminal_by_aggregation: dict[str, list[ScoredObservation]],
) -> list[dict[str, Any]]:
    result = []
    for aggregation in AGGREGATIONS:
        for evidence_floor in EVIDENCE_FLOORS:
            for minimum_score in SCORE_THRESHOLDS:
                for minimum_margin in MARGINS:
                    result.append(
                        {
                            "aggregation": aggregation,
                            "evidence_floor_seconds": evidence_floor,
                            "minimum_score": minimum_score,
                            "minimum_margin": minimum_margin,
                            "causal": evaluate_surface(
                                causal_by_aggregation[aggregation],
                                minimum_score=minimum_score,
                                minimum_margin=minimum_margin,
                                evidence_floor=evidence_floor,
                            ),
                            "terminal": evaluate_surface(
                                terminal_by_aggregation[aggregation],
                                minimum_score=minimum_score,
                                minimum_margin=minimum_margin,
                                evidence_floor=evidence_floor,
                            ),
                        }
                    )
    return result


def choose_candidate(points: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    safe = [
        point
        for point in points
        if point["causal"]["known_wrong_name"] == 0
        and point["causal"]["unknown_false_name"] == 0
        and point["terminal"]["known_wrong_name"] == 0
        and point["terminal"]["unknown_false_name"] == 0
    ]
    pool = safe or list(points)

    def rank(point: dict[str, Any]) -> tuple[float, ...]:
        false_names = (
            point["causal"]["known_wrong_name"]
            + point["causal"]["unknown_false_name"]
            + point["terminal"]["known_wrong_name"]
            + point["terminal"]["unknown_false_name"]
        )
        return (
            -float(false_names),
            float(point["causal"]["known_correct"]),
            float(point["terminal"]["known_correct"]),
            float(point["aggregation"] == "arithmetic_mean"),
            -abs(float(point["minimum_score"]) - 0.51),
            -abs(float(point["minimum_margin"])),
            -abs(float(point["evidence_floor_seconds"]) - 1.0),
        )

    return max(pool, key=rank), "zero_observed_false_names" if safe else "no_zero_false_name_point"


def distribution(values: Sequence[float]) -> dict[str, float | int]:
    array = np.asarray(values, dtype=np.float64)
    if not len(array):
        return {"count": 0}
    return {
        "count": int(len(array)),
        "minimum": float(np.min(array)),
        "p01": float(np.quantile(array, 0.01)),
        "p05": float(np.quantile(array, 0.05)),
        "median": float(np.quantile(array, 0.50)),
        "p95": float(np.quantile(array, 0.95)),
        "p99": float(np.quantile(array, 0.99)),
        "maximum": float(np.max(array)),
    }


def score_distributions(observations: Sequence[ScoredObservation]) -> dict[str, Any]:
    same = []
    different = []
    best_impostor = []
    by_speaker: dict[str, list[float]] = defaultdict(list)
    by_case: Counter[str] = Counter()
    for observation in observations:
        same.append(observation.scores[observation.true_profile_id])
        impostors = [
            score
            for profile_id, score in observation.scores.items()
            if profile_id != observation.true_profile_id
        ]
        different.extend(impostors)
        best_impostor.append(max(impostors))
        by_speaker[observation.true_profile_id].append(
            observation.scores[observation.true_profile_id]
        )
        by_case[observation.case_id] += 1
    return {
        "same_person_pairs": distribution(same),
        "different_person_pairs": distribution(different),
        "best_impostor_per_probe": distribution(best_impostor),
        "probe_units_by_case": dict(sorted(by_case.items())),
        "probe_units_by_speaker": {
            profile_id: distribution(scores)
            for profile_id, scores in sorted(by_speaker.items())
        },
    }


def decision_for_point(
    observation: ScoredObservation,
    point: dict[str, Any],
) -> dict[str, Any]:
    if observation.evidence_seconds < point["evidence_floor_seconds"]:
        return {
            "known": {"profile_id": None, "outcome": "abstain_below_evidence_floor"},
            "unknown": {"profile_id": None, "outcome": "abstain_below_evidence_floor"},
        }
    known = decide(
        observation.scores,
        minimum_score=point["minimum_score"],
        minimum_margin=point["minimum_margin"],
    )
    unknown = decide(
        {
            profile_id: score
            for profile_id, score in observation.scores.items()
            if profile_id != observation.true_profile_id
        },
        minimum_score=point["minimum_score"],
        minimum_margin=point["minimum_margin"],
    )
    return {"known": known.as_dict(), "unknown": unknown.as_dict()}


def full_observation_state(
    observations_by_aggregation: dict[str, list[ScoredObservation]],
    selected: dict[str, Any],
) -> list[dict[str, Any]]:
    by_id = {
        aggregation: {observation.observation_id: observation for observation in observations}
        for aggregation, observations in observations_by_aggregation.items()
    }
    ids = sorted(by_id["arithmetic_mean"])
    points = {
        "livetranscribe_baseline": {
            "aggregation": "arithmetic_mean",
            "evidence_floor_seconds": 1.0,
            "minimum_score": 0.51,
            "minimum_margin": 0.0,
        },
        "moss_within_session_baseline": {
            "aggregation": "duration_weighted_mean",
            "evidence_floor_seconds": 0.5,
            "minimum_score": 0.35,
            "minimum_margin": 0.10,
        },
        "selected_candidate": {
            key: selected[key]
            for key in (
                "aggregation",
                "evidence_floor_seconds",
                "minimum_score",
                "minimum_margin",
            )
        },
    }
    result = []
    for observation_id in ids:
        base = by_id["arithmetic_mean"][observation_id]
        row = {
            key: value
            for key, value in asdict(base).items()
            if key != "scores"
        }
        row["scores_by_aggregation"] = {
            aggregation: by_id[aggregation][observation_id].scores
            for aggregation in AGGREGATIONS
        }
        row["decisions"] = {}
        for name, point in points.items():
            observation = by_id[point["aggregation"]][observation_id]
            row["decisions"][name] = decision_for_point(observation, point)
        result.append(row)
    return result


def compact_profile(profile: Profile, album_module: Any) -> dict[str, Any]:
    similarity = album_module.cosine_similarity(
        profile.arithmetic_mean,
        profile.duration_weighted_mean,
    )
    return {
        "profile_id": profile.profile_id,
        "case_id": profile.case_id,
        "speaker_name": profile.speaker_name,
        "sample_count": len(profile.samples),
        "samples": [
            {
                "window_start_sec": sample.window_start_sec,
                "window_end_sec": sample.window_end_sec,
                "sample_seconds": sample.sample_seconds,
                "exemplar_count": sample.exemplar_count,
            }
            for sample in profile.samples
        ],
        "arithmetic_vs_duration_weighted_cosine": similarity,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="recompute every vector in memory with the production embedder instead of caches",
    )
    args = parser.parse_args()

    album_module = load_album_module()
    model_path = harness.ONNX
    model_sha = file_sha256(model_path)
    if model_sha != MODEL_SHA256:
        raise SystemExit(f"wrong production model: {model_sha}")
    adapter = harness.load_production_embedder()

    all_evidence: list[Evidence] = []
    cache_rows: dict[str, dict[str, int]] = {}
    for case in cases():
        cache = extract_fresh(case, adapter) if args.fresh else load_cached(case)
        evidence = evidence_from_cache(case, cache)
        all_evidence.extend(evidence)
        cache_rows[case.case_id] = {
            "all_evidence_groups": int(len(cache["rows"])),
            "embedded_evidence_groups": int(len(evidence)),
        }

    profiles = build_profiles(album_module, all_evidence)
    expected_profiles = {observation.profile_id for observation in all_evidence}
    if set(profiles) != expected_profiles:
        missing = sorted(expected_profiles - set(profiles))
        raise SystemExit(f"speakers without enrollment profiles: {missing}")

    causal_by_aggregation = {
        aggregation: causal_observations(
            album_module,
            all_evidence,
            profiles,
            aggregation,
        )
        for aggregation in AGGREGATIONS
    }
    terminal_by_aggregation = {
        aggregation: terminal_observations(
            album_module,
            all_evidence,
            profiles,
            aggregation,
        )
        for aggregation in AGGREGATIONS
    }
    points = operating_points(causal_by_aggregation, terminal_by_aggregation)
    selected, selection_status = choose_candidate(points)

    report = {
        "schema": "moss-voice-profile-matching-prototype.v1",
        "question": (
            "What score, margin, evidence floor, and profile aggregation recognize an "
            "enrolled voice while abstaining when that voice is absent from the bank?"
        ),
        "command": (
            "prototypes/streaming-diarization/.venv/bin/python "
            "prototypes/streaming-diarization/voice-profile-matching/"
            "prototype_voice_profile_match.py --fresh"
        ),
        "fresh_production_embeddings": bool(args.fresh),
        "production_path": {
            "embedder": (
                "moss_transcribe_diarize.app.speaker_identity."
                "_OnnxWeSpeakerEmbedder via WeSpeakerResNet152LmAdapter"
            ),
            "model": str(model_path.relative_to(REPO)),
            "model_sha256": model_sha,
            "metric": "production clamped cosine similarity",
            "session_album": "production FingerprintAlbum, top-10, 2.0 s admission",
        },
        "measurement_frame": {
            "corpora": [case.case_id for case in cases()],
            "enrollment_windows_seconds": ENROLLMENT_WINDOWS,
            "probe_start_seconds": PROBE_START_SECONDS,
            "terminal_window_seconds": TERMINAL_WINDOW_SECONDS,
            "cache_rows": cache_rows,
            "profile_count": len(profiles),
            "profile_names": sorted(profiles),
            "grid": {
                "score_thresholds": SCORE_THRESHOLDS,
                "margins": MARGINS,
                "evidence_floors_seconds": EVIDENCE_FLOORS,
                "aggregations": AGGREGATIONS,
                "operating_point_count": len(points),
            },
        },
        "profiles": [
            compact_profile(profile, album_module)
            for profile in sorted(profiles.values(), key=lambda item: item.profile_id)
        ],
        "distributions": {
            aggregation: score_distributions(causal_by_aggregation[aggregation])
            for aggregation in AGGREGATIONS
        },
        "selected_candidate": {
            "selection_status": selection_status,
            **selected,
        },
        "reference_points": {
            "livetranscribe_baseline": {
                "aggregation": "arithmetic_mean",
                "minimum_score": 0.51,
                "minimum_margin": 0.0,
                "evidence_floor_seconds": 1.0,
                "causal": evaluate_surface(
                    causal_by_aggregation["arithmetic_mean"],
                    minimum_score=0.51,
                    minimum_margin=0.0,
                    evidence_floor=1.0,
                ),
                "terminal": evaluate_surface(
                    terminal_by_aggregation["arithmetic_mean"],
                    minimum_score=0.51,
                    minimum_margin=0.0,
                    evidence_floor=1.0,
                ),
            },
            "moss_within_session_baseline": {
                "aggregation": "duration_weighted_mean",
                "minimum_score": 0.35,
                "minimum_margin": 0.10,
                "evidence_floor_seconds": 0.5,
                "causal": evaluate_surface(
                    causal_by_aggregation["duration_weighted_mean"],
                    minimum_score=0.35,
                    minimum_margin=0.10,
                    evidence_floor=0.5,
                ),
                "terminal": evaluate_surface(
                    terminal_by_aggregation["duration_weighted_mean"],
                    minimum_score=0.35,
                    minimum_margin=0.10,
                    evidence_floor=0.5,
                ),
            },
        },
        "operating_points": points,
        "full_state": {
            "causal_probes": full_observation_state(causal_by_aggregation, selected),
            "terminal_probes": full_observation_state(terminal_by_aggregation, selected),
        },
        "limits": [
            "Five speakers from two English interview recordings; every other population is unmeasured.",
            "Enrollment and probe audio are non-overlapping, but come from the same recordings.",
            "Terminal results use truth-aligned within-session speaker groups and therefore measure the existing album-centroid opportunity, not end-to-end future product behavior.",
            "The durable-profile production path does not exist; this prototype changes no production code.",
        ],
    }
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
