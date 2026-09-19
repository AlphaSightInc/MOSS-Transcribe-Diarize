#!/usr/bin/env python3
"""PROTOTYPE: expose pre-mean interval evidence and test terminal reassignment.

No decoder call. The retained WP28 window/local-label fixture and source audio drive
the production pinned WeSpeaker encoder. Each eligible interval is embedded exactly
once; its vectors are then reduced to the current per-label mean and independently
matched against the final current-policy album.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
from typing import Any

from moss_transcribe_diarize.app.live_identity_album import cosine_similarity
from moss_transcribe_diarize.app.live_provider_bundle import (
    LiveProviderBundleConfig,
    _fingerprint_album,
    _identity_encoder,
)
from moss_transcribe_diarize.app.speaker_identity import (
    _mean_unit_vector,
    _normalized_vector,
    _run_onnx_embedding,
    _slice_interval,
)
from moss_transcribe_diarize.app.windowed_transcription import extract_window_wav


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNTIME = Path(
    "/private/tmp/moss-independent-assessment-20260918/.wp25runtime/"
    "20260919T033906530769Z"
)


@dataclass(frozen=True)
class Observation:
    window: int
    local: str
    segment: int
    start: float
    end: float
    vector: tuple[float, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture",
        type=Path,
        default=ROOT / "evidence/mvpfix/wp28/fixture-30.json",
    )
    parser.add_argument(
        "--audio",
        type=Path,
        default=DEFAULT_RUNTIME / "files/media/long.wav",
    )
    parser.add_argument(
        "--reference",
        type=Path,
        default=DEFAULT_RUNTIME / "files/media/reference.jsonl",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path.home()
        / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("results.json"),
    )
    return parser.parse_args()


def overlap(left: tuple[float, float], right: tuple[float, float]) -> float:
    return max(0.0, min(left[1], right[1]) - max(left[0], right[0]))


def truth_support(
    interval: tuple[float, float], reference: list[dict[str, Any]]
) -> dict[str, float]:
    support: dict[str, float] = defaultdict(float)
    for row in reference:
        seconds = overlap(interval, (float(row["start"]), float(row["end"])))
        if seconds:
            support[str(row["speaker"])] += seconds
    return dict(sorted(support.items()))


def interval_vectors(embedder: Any, wav: Path, intervals: list[tuple[float, float]]):
    session = embedder._load_session()
    samples, sample_rate = embedder._load_audio(wav)
    if sample_rate != 16000:
        raise ValueError("prototype requires 16 kHz mono source")

    clips = []
    kept = []
    for interval in intervals:
        values = _slice_interval(samples, sample_rate, *interval)
        if len(values):
            clips.append(values)
            kept.append(interval)

    def one(values):
        return tuple(
            _normalized_vector(
                _run_onnx_embedding(session, embedder._features(values))
            )
        )

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="purity-prototype") as pool:
        vectors = list(pool.map(one, clips))
    return kept, vectors


def confident_match(vector, references, *, score_floor: float, margin: float):
    scores = sorted(
        (
            (speaker, float(score))
            for speaker, reference in references.items()
            if (score := cosine_similarity(vector, reference)) is not None
        ),
        key=lambda item: (-item[1], item[0]),
    )
    if not scores:
        return None, scores
    best = scores[0]
    runner = scores[1][1] if len(scores) > 1 else 0.0
    if best[1] < score_floor or best[1] - runner < margin:
        return None, scores
    return best[0], scores


def main() -> None:
    args = parse_args()
    fixture = json.loads(args.fixture.read_text())
    reference = [json.loads(line) for line in args.reference.read_text().splitlines()]
    config = LiveProviderBundleConfig.from_manifest(args.manifest)
    adapter = _identity_encoder(config, interval_workers=4)
    embedder = adapter._get_embedder()
    minimum = int(config.identity_provider["min_segment_samples"]) / 16000.0

    observations: list[Observation] = []
    label_means: dict[tuple[int, str], tuple[float, ...]] = {}
    durations: dict[tuple[int, str], float] = {}
    purity_rows = []

    with tempfile.TemporaryDirectory(prefix="local-label-purity-") as directory:
        scratch = Path(directory)
        for window, segments in zip(
            fixture["windows"], fixture["local_results"], strict=True
        ):
            wav = scratch / f"window-{window['index']}.wav"
            extract_window_wav(
                args.audio,
                wav,
                start_seconds=float(window["start"]),
                duration_seconds=float(window["end"] - window["start"]),
            )
            for local in sorted({str(segment["speaker"]) for segment in segments}):
                selected = [
                    (index, max(0.0, float(segment["start"])), min(
                        float(window["end"] - window["start"]), float(segment["end"])
                    ))
                    for index, segment in enumerate(segments)
                    if segment["speaker"] == local
                    and float(segment["end"]) - max(0.0, float(segment["start"]))
                    >= minimum
                ]
                kept, vectors = interval_vectors(
                    embedder, wav, [(start, end) for _, start, end in selected]
                )
                if len(kept) != len(selected):
                    raise AssertionError("eligible interval disappeared before embedding")
                key = (int(window["index"]), local)
                label_means[key] = tuple(_mean_unit_vector(vectors))
                durations[key] = sum(end - start for _, start, end in selected)
                support: dict[str, float] = defaultdict(float)
                for (segment, start, end), vector in zip(selected, vectors, strict=True):
                    absolute = (
                        float(window["start"]) + start,
                        float(window["start"]) + end,
                    )
                    for speaker, seconds in truth_support(absolute, reference).items():
                        support[speaker] += seconds
                    observations.append(
                        Observation(
                            window=int(window["index"]),
                            local=local,
                            segment=segment,
                            start=start,
                            end=end,
                            vector=vector,
                        )
                    )
                total = sum(support.values())
                purity_rows.append(
                    {
                        "window": int(window["index"]),
                        "local": local,
                        "eligible_intervals": len(vectors),
                        "aligned_seconds": round(total, 6),
                        "majority_fraction": round(
                            max(support.values(), default=0.0) / total if total else 0.0,
                            6,
                        ),
                        "truth_seconds": {
                            speaker: round(seconds, 6)
                            for speaker, seconds in sorted(support.items())
                        },
                    }
                )

    album = _fingerprint_album(config.identity_provider)
    mappings: dict[tuple[int, str], str] = {}
    for state in fixture["expected"]["diagnostics"]["windows"]:
        window = int(state["window"])
        for local, canonical in sorted(state["mapping"].items()):
            key = (window, local)
            mappings[key] = canonical
            album.observe(
                canonical_speaker=canonical,
                vector=label_means[key],
                duration_sec=durations[key],
                span_id=window,
            )
    references = {speaker: album.reference(speaker) for speaker in album.speakers()}
    if any(vector is None for vector in references.values()):
        raise AssertionError("current-policy album lacks a final reference")

    # Resolve canonical IDs to source people only for scoring, never candidate input.
    canonical_truth: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in purity_rows:
        canonical = mappings[(row["window"], row["local"])]
        for speaker, seconds in row["truth_seconds"].items():
            canonical_truth[canonical][speaker] += float(seconds)
    canonical_person = {
        canonical: max(support, key=support.get)
        for canonical, support in canonical_truth.items()
    }

    score_floor = float(config.identity_config["min_match_score"])
    margin = float(config.identity_config["min_match_margin"])
    totals = defaultdict(float)
    controls = defaultdict(float)
    decision_rows = []
    purity_by_key = {
        (row["window"], row["local"]): row["majority_fraction"]
        for row in purity_rows
    }
    windows = {int(row["index"]): row for row in fixture["windows"]}
    for item in observations:
        window = windows[item.window]
        absolute = (
            float(window["start"]) + item.start,
            float(window["start"]) + item.end,
        )
        owned = (
            max(absolute[0], float(window["own_start"])),
            min(absolute[1], float(window["own_end"])),
        )
        if owned[1] <= owned[0]:
            continue
        truth = truth_support(owned, reference)
        if not truth:
            continue
        person = max(truth, key=truth.get)
        weight = sum(truth.values())
        current = mappings[(item.window, item.local)]
        candidate, scores = confident_match(
            item.vector,
            references,
            score_floor=score_floor,
            margin=margin,
        )
        current_correct = canonical_person[current] == person
        candidate_correct = candidate is not None and canonical_person[candidate] == person
        totals["scored_seconds"] += weight
        totals["current_correct_seconds" if current_correct else "current_confused_seconds"] += weight
        totals[
            "candidate_unknown_seconds"
            if candidate is None
            else ("candidate_correct_seconds" if candidate_correct else "candidate_confused_seconds")
        ] += weight
        if candidate != current:
            totals["changed_seconds"] += weight
        clean_control = purity_by_key[(item.window, item.local)] >= 0.95 and current_correct
        if clean_control:
            controls["seconds"] += weight
            if candidate is None:
                controls["candidate_unknown_seconds"] += weight
            elif candidate_correct:
                controls["candidate_correct_seconds"] += weight
            else:
                controls["candidate_confused_seconds"] += weight
        decision_rows.append(
            {
                "window": item.window,
                "local": item.local,
                "segment": item.segment,
                "duration": round(weight, 6),
                "truth": person,
                "current": current,
                "candidate": candidate or "S00",
                "current_correct": current_correct,
                "candidate_correct": candidate_correct,
                "scores": {speaker: round(score, 6) for speaker, score in scores},
            }
        )

    result = {
        "schema": "moss-local-label-purity-prototype.v1",
        "inputs": {
            "fixture": str(args.fixture),
            "audio": str(args.audio),
            "reference": str(args.reference),
            "eligible_interval_seconds": minimum,
            "match_score": score_floor,
            "match_margin": margin,
        },
        "population": {
            "windows": len(fixture["windows"]),
            "eligible_intervals": len(observations),
            "local_labels": len(purity_rows),
        },
        "canonical_person_for_scoring_only": canonical_person,
        "purity": purity_rows,
        "outcome_seconds": {key: round(value, 6) for key, value in sorted(totals.items())},
        "clean_control_seconds": {
            key: round(value, 6) for key, value in sorted(controls.items())
        },
        "decisions": decision_rows,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "decisions"}, indent=2))
    print(json.dumps({"results": str(args.output), "decision_rows": len(decision_rows)}))


if __name__ == "__main__":
    main()
