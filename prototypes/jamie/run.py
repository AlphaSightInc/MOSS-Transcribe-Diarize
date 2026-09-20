"""R4-4: falsify retained-evidence aggregation policies with production CPU embeddings."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
import tempfile
import wave

import numpy as np

from moss_transcribe_diarize.app.live_identity_album import cosine_similarity
from moss_transcribe_diarize.app.live_provider_bundle import (
    LiveProviderBundleConfig,
    _identity_encoder,
)
from moss_transcribe_diarize.app.speaker_identity import _mean_unit_vector


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
JAMIE_AUDIO = ROOT / "evidence/live-policy-sweep-20260825/corpus/discussion_jamie_dimon_180s/audio.wav"
RTFL_AUDIO = ROOT / "evidence/live-policy-sweep-20260825/corpus/discussion_rtfl_90s/audio.wav"
REFERENCE = JAMIE_AUDIO.with_name("reference.jsonl")
MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
MODEL = Path.home() / ".local/share/moss-transcribe-diarize/live/voxceleb_resnet152_LM.onnx"
RESULTS = ROOT / "evidence/round4/jamie/results.json"


@dataclass(frozen=True)
class Unit:
    name: str
    truth: str | None
    duration: float
    vector: tuple[float, ...]
    population: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mean(vectors: list[list[float]]) -> tuple[float, ...]:
    return tuple(_mean_unit_vector(vectors))


def synth_controls(directory: Path) -> dict[str, Path]:
    sample_rate = 16_000
    seconds = 1.5
    count = int(sample_rate * seconds)
    rng = np.random.default_rng(4404)
    noise = rng.normal(0.0, 0.03, count).astype(np.float32)
    applause = np.zeros(count, dtype=np.float32)
    for center in (0.10, 0.24, 0.39, 0.57, 0.78, 1.02, 1.24, 1.40):
        start = int(center * sample_rate)
        width = min(int(0.045 * sample_rate), count - start)
        envelope = np.exp(-np.arange(width) / (0.010 * sample_rate))
        applause[start : start + width] += rng.normal(0.0, 0.55, width) * envelope
    paths: dict[str, Path] = {}
    for name, samples in {"synthetic_noise": noise, "synthetic_applause_proxy": applause}.items():
        path = directory / f"{name}.wav"
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(pcm.tobytes())
        paths[name] = path
    return paths


def embed_plan(encoder) -> tuple[dict[str, tuple[float, ...]], dict[str, object]]:
    plans = {
        "ben_enroll": [(135.78, 138.61), (138.61, 142.40), (143.78, 146.78), (146.78, 149.75), (149.75, 151.82), (160.00, 162.16)],
        "david_enroll": [(120.64, 125.15), (125.15, 130.78), (130.78, 135.42)],
        "ben_return_1": [(163.52, 164.52)],
        "ben_return_2": [(178.97, 180.00)],
        "david_return_1": [(169.47, 170.34), (170.34, 170.84)],
        "david_return_2": [(174.87, 176.22)],
        "jamie_retained": [(165.68, 166.46)],
        "laughter": [(167.08, 168.93)],
    }
    flat = [interval for intervals in plans.values() for interval in intervals]
    raw = encoder.embed_intervals(JAMIE_AUDIO, flat)
    vectors: dict[str, tuple[float, ...]] = {}
    cursor = 0
    for name, intervals in plans.items():
        width = len(intervals)
        vectors[name] = mean(raw[cursor : cursor + width])
        cursor += width

    rtfl = {
        "eng_a_1": [(5.9175, 6.803333)],
        "eng_a_2": [(49.0575, 49.63)],
        "eng_b_1": [(45.288462, 46.161875)],
        "eng_b_2": [(55.855, 56.694999)],
    }
    for name, intervals in rtfl.items():
        vectors[name] = mean(encoder.embed_intervals(RTFL_AUDIO, intervals))

    with tempfile.TemporaryDirectory(prefix="r4-jamie-") as temporary:
        paths = synth_controls(Path(temporary))
        for name, path in paths.items():
            vectors[name] = mean(encoder.embed_intervals(path, [(0.0, 1.5)]))

    state = {
        "jamie_interval_filter": {
            "retained_vector": [165.68, 166.46],
            "excluded_below_min_segment_samples": [[166.57, 166.95], [177.96, 178.22]],
            "min_segment_samples": 8000,
            "sample_rate": 16000,
        },
        "same_person_cosines": {
            "ENG_A": round(float(cosine_similarity(vectors["eng_a_1"], vectors["eng_a_2"])), 6),
            "ENG_B": round(float(cosine_similarity(vectors["eng_b_1"], vectors["eng_b_2"])), 6),
        },
        "closest_different_pair_cosine": round(
            max(float(cosine_similarity(vectors[a], vectors[b])) for a in ("eng_a_1", "eng_a_2") for b in ("eng_b_1", "eng_b_2")), 6
        ),
    }
    return vectors, state


def score(vector: tuple[float, ...], references: dict[str, tuple[float, ...]], threshold: float, margin: float):
    ranked = sorted(
        ((speaker, float(cosine_similarity(vector, reference))) for speaker, reference in references.items()),
        key=lambda item: (-item[1], item[0]),
    )
    best = ranked[0] if ranked else None
    runner = ranked[1][1] if len(ranked) > 1 else 0.0
    accepted = best is not None and best[1] >= threshold and best[1] - runner >= margin
    return (best[0] if accepted and best else None), {speaker: round(value, 6) for speaker, value in ranked}, round(runner, 6)


def weighted_centroid(items: list[Unit]) -> tuple[float, ...]:
    values = np.asarray([item.vector for item in items], dtype=np.float64)
    weights = np.asarray([item.duration for item in items], dtype=np.float64)
    center = np.average(values, axis=0, weights=weights)
    norm = float(np.linalg.norm(center))
    return tuple((center / norm).tolist())


def evaluate_policy(name: str, units: list[Unit], base_refs: dict[str, tuple[float, ...]], *, score_floor: float, margin: float, birth: float, admission: float):
    references = dict(base_refs)
    canonical_truth: dict[str, str | None] = {"speaker-ben": "Ben", "speaker-david": "David"}
    truth_ids: dict[str, list[str]] = {"Ben": ["speaker-ben"], "David": ["speaker-david"]}
    pending: list[list[Unit]] = []
    decisions: list[dict[str, object]] = []
    next_id = 3

    def birth_group(group: list[Unit], phase: str) -> str:
        nonlocal next_id
        canonical = f"speaker-{next_id:04d}"
        next_id += 1
        truth_set = {item.truth for item in group}
        canonical_truth[canonical] = next(iter(truth_set)) if len(truth_set) == 1 else "MIXED"
        if canonical_truth[canonical] is not None and canonical_truth[canonical] != "MIXED":
            truth_ids.setdefault(str(canonical_truth[canonical]), []).append(canonical)
        references[canonical] = weighted_centroid(group)
        disposition = "admitted" if sum(item.duration for item in group) >= admission else "provisional"
        for item in group:
            decisions.append({"unit": item.name, "truth": item.truth, "duration_sec": round(item.duration, 6), "action": "birth", "canonical": canonical, "phase": phase, "disposition": disposition})
        return canonical

    def place_pending(unit: Unit, phase: str) -> bool:
        candidates = []
        for index, group in enumerate(pending):
            similarities = [float(cosine_similarity(unit.vector, item.vector)) for item in group]
            candidates.append((index, min(similarities)))
        candidates.sort(key=lambda item: (-item[1], item[0]))
        if candidates:
            best_index, best_value = candidates[0]
            runner = candidates[1][1] if len(candidates) > 1 else 0.0
            if best_value >= score_floor and best_value - runner >= margin:
                pending[best_index].append(unit)
                group = pending[best_index]
                if sum(item.duration for item in group) >= birth:
                    pending.pop(best_index)
                    birth_group(group, phase)
                else:
                    decisions.append({"unit": unit.name, "truth": unit.truth, "duration_sec": round(unit.duration, 6), "action": "pooled_pending", "pool_support_sec": round(sum(item.duration for item in group), 6), "phase": phase})
                return True
        pending.append([unit])
        decisions.append({"unit": unit.name, "truth": unit.truth, "duration_sec": round(unit.duration, 6), "action": "deferred", "phase": phase})
        return False

    for unit in units:
        matched, scores, runner = score(unit.vector, references, score_floor, margin)
        if matched is not None:
            decisions.append({"unit": unit.name, "truth": unit.truth, "duration_sec": round(unit.duration, 6), "action": "match", "canonical": matched, "canonical_truth": canonical_truth[matched], "scores": scores, "runner_up": runner, "phase": "live"})
            continue
        if unit.duration >= birth:
            birth_group([unit], "live")
            decisions[-1]["scores"] = scores
            decisions[-1]["runner_up"] = runner
            continue
        if name in {"P1_cross_span_pooling", "P2_deferred_re_evaluation"}:
            place_pending(unit, "live")
        else:
            pending.append([unit])
            decisions.append({"unit": unit.name, "truth": unit.truth, "duration_sec": round(unit.duration, 6), "action": "deferred", "scores": scores, "runner_up": runner, "phase": "live"})

    if name == "P3_terminal_retrospective":
        original = [item for group in pending for item in group]
        pending = []
        for unit in original:
            place_pending(unit, "terminal")

    assignments: dict[str, tuple[str | None, str]] = {}
    for decision in decisions:
        assignments[str(decision["unit"])] = (decision.get("canonical"), str(decision["action"]))
    denominators = {"Ben": 2.03, "David": 2.72, "ENG_A": 1.458333, "ENG_B": 1.713412, "Jamie": 4.221}
    per_person: dict[str, dict[str, float]] = {}
    unit_truth = {unit.name: unit for unit in units}
    for truth, denominator in denominators.items():
        correct = wrong = 0.0
        for unit in unit_truth.values():
            if unit.truth != truth:
                continue
            canonical, _action = assignments.get(unit.name, (None, "missing"))
            if canonical is None:
                continue
            if canonical_truth.get(canonical) == truth:
                correct += unit.duration
            else:
                wrong += unit.duration
        if truth == "Jamie":
            correct = wrong = 0.0  # human identity/boundary adjudication is deliberately absent
        unknown = max(0.0, denominator - correct - wrong)
        per_person[truth] = {
            "source_denominator_sec": round(denominator, 6),
            "correct_sec": round(correct, 6),
            "wrong_sec": round(wrong, 6),
            "unknown_sec": round(unknown, 6),
            "missed_identity_sec": round(unknown, 6),
        }

    births = [row for row in decisions if row["action"] == "birth"]
    false_births = sum(row["truth"] is None for row in births)
    nonperson_assignments = sum(unit.truth is None and assignments.get(unit.name, (None,))[0] is not None for unit in units)
    duplicate_births = sum(max(0, len(ids) - 1) for truth, ids in truth_ids.items() if truth not in {"Ben", "David"})
    merges = sum(row["wrong_sec"] > 0 for row in per_person.values())
    return {
        "policy": name,
        "decision_state": decisions,
        "remaining_pending": [[item.name for item in group] for group in pending],
        "per_person": per_person,
        "false_births": false_births,
        "nonperson_id_assignments": nonperson_assignments,
        "duplicate_births": duplicate_births,
        "merges": merges,
        "provisional_births": sum(row.get("disposition") == "provisional" for row in births),
        "admitted_births": sum(row.get("disposition") == "admitted" for row in births),
        "words_times_unchanged": True,
    }


def main() -> None:
    config = LiveProviderBundleConfig.from_manifest(MANIFEST)
    encoder = _identity_encoder(config, interval_workers=1)
    vectors, acoustic_state = embed_plan(encoder)
    base_refs = {"speaker-ben": vectors["ben_enroll"], "speaker-david": vectors["david_enroll"]}
    units = [
        Unit("ben_return_1", "Ben", 1.00, vectors["ben_return_1"], "established_return"),
        Unit("david_return_1", "David", 1.37, vectors["david_return_1"], "established_return"),
        Unit("ben_return_2", "Ben", 1.03, vectors["ben_return_2"], "established_return"),
        Unit("david_return_2", "David", 1.35, vectors["david_return_2"], "established_return"),
        Unit("eng_a_1", "ENG_A", 0.885833, vectors["eng_a_1"], "separated_short_utterances"),
        Unit("eng_b_1", "ENG_B", 0.873413, vectors["eng_b_1"], "similar_different_person"),
        Unit("eng_a_2", "ENG_A", 0.5725, vectors["eng_a_2"], "separated_short_utterances"),
        Unit("eng_b_2", "ENG_B", 0.839999, vectors["eng_b_2"], "similar_different_person"),
        Unit("jamie_retained", "Jamie", 0.78, vectors["jamie_retained"], "lone_brief_source_owned"),
        Unit("laughter", None, 1.85, vectors["laughter"], "real_nonperson"),
        Unit("synthetic_applause_proxy", None, 1.5, vectors["synthetic_applause_proxy"], "synthetic_nonperson_proxy"),
        Unit("synthetic_noise", None, 1.5, vectors["synthetic_noise"], "synthetic_nonperson"),
    ]
    threshold = float(config.identity_config["min_match_score"])
    margin = float(config.identity_config["min_match_margin"])
    birth = float(config.identity_provider["birth_min_seconds"])
    admission = float(config.identity_provider["album_admission_seconds"])
    policies = [
        evaluate_policy(name, units, base_refs, score_floor=threshold, margin=margin, birth=birth, admission=admission)
        for name in ("P0_current", "P1_cross_span_pooling", "P2_deferred_re_evaluation", "P3_terminal_retrospective")
    ]
    repeated_vectors = encoder.embed_intervals(JAMIE_AUDIO, [(165.68, 166.46)] * 3)
    repeated_cosines = [round(float(cosine_similarity(repeated_vectors[a], repeated_vectors[b])), 6) for a, b in ((0, 1), (0, 2), (1, 2))]
    output = {
        "verdict": "FALSIFIED",
        "implementation_disposition": "REJECTED: no run-B product implementation",
        "reason": "All tried policies leave the one source-owned 0.78 s Jamie vector unresolved; unchanged current birth semantics also give non-person controls an identity. Cross-repeat Jamie pooling is an exact-audio duplicate, not independent evidence.",
        "runtime": {"device": "cpu", "fresh_encoder_session": True, "decoder_requests": 0, "source_revision": "89f833acd4c654dd702664a17ed19783a2999c95", "scorer": "r4-jamie-policy-scorer-v1", "reference_sha256": sha256(REFERENCE), "audio_sha256": sha256(JAMIE_AUDIO), "manifest_sha256": sha256(MANIFEST), "model_sha256": sha256(MODEL)},
        "constants": {"min_match_score": threshold, "min_match_margin": margin, "birth_min_seconds": birth, "album_admission_seconds": admission, "min_segment_samples": int(config.identity_provider["min_segment_samples"])},
        "acoustic_state": acoustic_state,
        "repeated_source_diagnostic": {"population": "retained 600 s run, three exact repeats of one 180 s source", "pair_cosines": repeated_cosines, "compatible_support_sec": 2.34, "would_cross_birth_and_admission": True, "valid_generalization_evidence": False},
        "denominators": {"single_180s_source_jamie_sec": 4.221, "retained_600s_three_repeat_jamie_sec": 12.663, "measured_session_count_claim": 10, "sessions_replayed_here": 0, "adjudicated_jamie_sec": 0.0},
        "transcript_invariants": {"word_changes": 0, "timestamp_changes": 0},
        "policies": policies,
        "unmeasured": ["all six snippets in prototypes/jamie/snippets.json: human speaker identity and spill boundaries were not attended-adjudicated", "real applause: no source-owned labelled applause interval exists in the retained corpus; synthetic proxy reported separately"],
        "target_proposal": {"Ben_selected_return_controls": "correct 2.03/2.03 s; wrong 0 s", "David_selected_return_controls": "correct 2.72/2.72 s; wrong 0 s", "Jamie": "UNMEASURED; no numeric target proposed before R4-11 adjudication", "all_people": "misattribution 0 s; no denominator exclusions", "nonperson": "0 identity assignments and 0 births"},
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
