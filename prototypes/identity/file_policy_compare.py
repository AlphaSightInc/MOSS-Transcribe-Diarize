#!/usr/bin/env python3
"""THROWAWAY WP55a-P prototype: compare four File identity policies offline.

Question: when interval evidence disagrees with a pooled File identity, which
smallest policy preserves pooled evidence without giving up source-backed repair?

The retained baseline transcript is the pooled/swept decision (``current``), and
the retained candidate transcript is production P0 interval refinement.  Fresh
CPU ONNX vectors are computed from the identical retained media.  No decoder,
network, or GPU request occurs.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from moss_transcribe_diarize.app.live_identity_album import cosine_similarity
from moss_transcribe_diarize.app.file_identity_album import AlbumIdentityResolver
from moss_transcribe_diarize.app.live_provider_bundle import (
    LiveProviderBundleConfig,
    _fingerprint_album,
    _identity_encoder,
)
from moss_transcribe_diarize.app.speaker_identity import _mean_unit_vector
from moss_transcribe_diarize.app.windowed_transcription import (
    WindowPlan,
    _stitch_segments,
    extract_window_wav,
    plan_windows,
)
from moss_transcribe_diarize.live_speaker_accuracy import Segment, score_live_speaker_accuracy
from moss_transcribe_diarize.transcript_parser import TranscriptSegment


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ROUND2 = Path("/Users/gao/Documents/Codex/2026-09-19/moss-round2")
RUNTIME = Path(
    "/private/tmp/moss-independent-assessment-20260918/.wp25runtime/"
    "20260919T033906530769Z/files"
)
CANDIDATE = Path("/private/tmp/claude-501/r2verify-e/sc")
MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
EXPECTED_SHA = "a7a738cf9f9ff246f64c52c112e0bf597ba58241"
UNKNOWN = {"", "S00", "speaker-0000", "unassigned", "Speaker uncertain"}
MS = 10
POLICIES = ("P0", "P1", "P2", "P3")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def load(path: Path) -> Any:
    return json.loads(path.read_text())


def normalize_speaker(value: str) -> str:
    return "S00" if value in UNKNOWN else value


def meeting_segments(path: Path) -> list[dict[str, Any]]:
    rows = load(path)["transcript"]["segments"]
    return [
        {
            "start": float(row["start"]),
            "end": float(row["end"]),
            "speaker": normalize_speaker(str(row["speaker"])),
            "text": str(row.get("text", "")),
        }
        for row in rows
    ]


def reference_rows(path: Path, duration: float) -> list[dict[str, Any]]:
    return [
        row for row in (json.loads(line) for line in path.read_text().splitlines())
        if float(row["start"]) < duration
    ]


def ticks(start: float, end: float) -> range:
    return range(int(round(start * 1000 / MS)), int(round(end * 1000 / MS)))


def analyse(reference: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    ref = [Segment(float(r["start"]), float(r["end"]), str(r["speaker"]), str(r.get("text", "")))
           for r in reference]
    hyp = [Segment(r["start"], r["end"], r["speaker"], r["text"]) for r in rows]
    assigned = [row for row in hyp if row.speaker != "S00"]
    scored = score_live_speaker_accuracy(ref, assigned)
    mapping = scored["speaker_mapping"]
    assigned_grid: dict[int, str] = {}
    unknown_grid: set[int] = set()
    for row in hyp:
        target = unknown_grid if row.speaker == "S00" else None
        for tick in ticks(row.start, row.end):
            if target is not None:
                target.add(tick)
            else:
                assigned_grid.setdefault(tick, row.speaker)
    ref_grid: dict[int, str] = {}
    for row in ref:
        for tick in ticks(row.start, row.end):
            ref_grid.setdefault(tick, row.speaker)
    category: dict[int, str] = {}
    labels: dict[int, str | None] = {}
    per_person: dict[str, Counter[str]] = defaultdict(Counter)
    for tick, person in ref_grid.items():
        label = assigned_grid.get(tick)
        labels[tick] = label if label is not None else ("S00" if tick in unknown_grid else None)
        if label is not None:
            outcome = "correct" if label == mapping.get(person) else "wrong"
        elif tick in unknown_grid:
            outcome = "unknown"
        else:
            outcome = "missed"
        category[tick] = outcome
        per_person[person][outcome] += 1
    report = {}
    for person, counts in sorted(per_person.items()):
        report[person] = {
            key: round(counts[key] * MS / 1000, 3)
            for key in ("correct", "wrong", "unknown", "missed")
        }
        report[person]["denominator"] = round(sum(counts.values()) * MS / 1000, 3)
    totals = Counter()
    for counts in per_person.values():
        totals.update(counts)
    report["TOTAL"] = {
        key: round(totals[key] * MS / 1000, 3)
        for key in ("correct", "wrong", "unknown", "missed")
    }
    report["TOTAL"]["denominator"] = round(sum(totals.values()) * MS / 1000, 3)
    return {
        "mapping": mapping,
        "per_person": report,
        "ref_grid": ref_grid,
        "category": category,
        "labels": labels,
    }


def transition_report(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    matrix: dict[str, Counter[str]] = defaultdict(Counter)
    selected: dict[tuple[str, str], list[int]] = defaultdict(list)
    for tick in baseline["ref_grid"]:
        pair = (baseline["category"][tick], candidate["category"][tick])
        matrix[pair[0]][pair[1]] += 1
        if pair[0] != pair[1]:
            selected[pair].append(tick)
    intervals = []
    for pair, values in selected.items():
        current = None
        for tick in values:
            key = (
                pair,
                baseline["ref_grid"][tick],
                baseline["labels"][tick],
                candidate["labels"][tick],
            )
            if current and current["end_tick"] == tick and current["key"] == key:
                current["end_tick"] = tick + 1
            else:
                if current:
                    intervals.append(current)
                current = {"key": key, "start_tick": tick, "end_tick": tick + 1}
        if current:
            intervals.append(current)
    rendered = []
    for item in intervals:
        pair, person, before_label, after_label = item["key"]
        start = item["start_tick"] * MS / 1000
        end = item["end_tick"] * MS / 1000
        seam = any(start < boundary <= end + 1e-9 for boundary in range(60, 1801, 60))
        rendered.append({
            "start": round(start, 3), "end": round(end, 3),
            "seconds": round(end - start, 3), "person": person,
            "from": pair[0], "to": pair[1],
            "baseline_label": before_label, "candidate_label": after_label,
            "splice_seam": seam,
        })
    return {
        "matrix": {
            left: {right: round(matrix[left][right] * MS / 1000, 3)
                   for right in ("correct", "wrong", "unknown", "missed")}
            for left in ("correct", "wrong", "unknown", "missed")
        },
        "changed_intervals": sorted(rendered, key=lambda row: (row["start"], row["end"])),
        "correct_to_wrong_nonsplice_seconds": round(sum(
            row["seconds"] for row in rendered
            if row["from"] == "correct" and row["to"] == "wrong" and not row["splice_seam"]
        ), 3),
        "correct_to_wrong_splice_seconds": round(sum(
            row["seconds"] for row in rendered
            if row["from"] == "correct" and row["to"] == "wrong" and row["splice_seam"]
        ), 3),
        "correct_to_unknown_seconds": round(sum(
            row["seconds"] for row in rendered
            if row["from"] == "correct" and row["to"] == "unknown"
        ), 3),
        "wrong_to_correct_seconds": round(sum(
            row["seconds"] for row in rendered
            if row["from"] == "wrong" and row["to"] == "correct"
        ), 3),
        "wrong_to_unknown_seconds": round(sum(
            row["seconds"] for row in rendered
            if row["from"] == "wrong" and row["to"] == "unknown"
        ), 3),
    }


def unit(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


def choose(
    policy: str,
    *,
    current: str,
    terminal: str | None,
    pooled_score: float | None,
    terminal_score: float | None,
    margin: float,
) -> tuple[str, str]:
    """Pure policy primitive shared by synthetic and retained comparisons."""
    terminal = None if terminal in (None, "S00") else terminal
    if policy == "P0":
        return (terminal or "S00", "terminal_or_unknown")
    if policy == "P1":
        return ("S00" if terminal is None else current, "abstain_only")
    if policy == "P2":
        return (terminal or current, "current_fallback")
    if policy != "P3":
        raise ValueError(policy)
    if terminal is None or terminal == current:
        return (current, "current_on_abstention_or_agreement")
    if pooled_score is None:
        return (current, "no_pooled_score_keep_current")
    if terminal_score is None or terminal_score - pooled_score < margin:
        return (current, "pooled_margin_block")
    return (terminal, "pooled_margin_override")


def synthetic_controls(margin: float) -> dict[str, Any]:
    # Verbatim vectors from fable-review-evidence/identity_repro.py.
    s01 = [1.0, 0.0, 0.0]
    s02 = [0.0, 1.0, 0.0]
    a = unit([0.5, 0.5, 0.0])
    b = unit([0.9, -0.9, 0.0])
    c = unit([0.3, 0.9, 0.0])
    d = unit([1.2, -0.3, 0.0])
    case1_mean = _mean_unit_vector([a, b])
    case2_mean = _mean_unit_vector([c, d])
    case1_pooled = float(cosine_similarity(case1_mean, s01))
    case2_pooled = float(cosine_similarity(case2_mean, s01))
    rows = {}
    for policy in POLICIES:
        rows[policy] = {
            "case1": {
                "pooled": "S01", "terminal": None,
                "published": choose(
                    policy, current="S01", terminal=None,
                    pooled_score=case1_pooled, terminal_score=None, margin=margin,
                )[0],
            },
            "case2": {
                "pooled": "S01", "terminal": "S02",
                "pooled_score": round(case2_pooled, 6),
                "terminal_score": round(float(cosine_similarity(c, s02)), 6),
                "published": choose(
                    policy, current="S01", terminal="S02",
                    pooled_score=case2_pooled,
                    terminal_score=float(cosine_similarity(c, s02)), margin=margin,
                )[0],
            },
        }
    return rows


def embed_rows(
    encoder: Any,
    source: Path,
    rows: list[dict[str, Any]],
    minimum_samples: int,
    scratch: Path,
) -> tuple[dict[int, tuple[float, ...]], Path]:
    wav = scratch / f"{source.name}.pcm.wav"
    duration = max(row["end"] for row in rows)
    extract_window_wav(source, wav, start_seconds=0.0, duration_seconds=duration)
    selected = [
        (index, row["start"], row["end"])
        for index, row in enumerate(rows)
        if round((row["end"] - row["start"]) * 16000) >= minimum_samples
    ]
    vectors = encoder.embed_intervals(wav, [(start, end) for _, start, end in selected])
    if len(vectors) != len(selected):
        raise AssertionError("production encoder omitted an eligible retained interval")
    return ({index: tuple(vector) for (index, _, _), vector in zip(selected, vectors, strict=True)}, wav)


def pooled_scores(
    rows: list[dict[str, Any]],
    vectors: dict[int, tuple[float, ...]],
    duration: float,
    config: LiveProviderBundleConfig,
) -> tuple[dict[int, float | None], dict[str, tuple[float, ...]], dict[str, Any]]:
    """Reconstruct sequential pooled evidence from retained pooled labels.

    This is explicitly a retained-transcript counterfactual: the full MP3/M4A
    raw window responses were not retained.  Each published segment is assigned
    to its owning production window by midpoint, then the unchanged album observes
    that window's label mean.
    """
    windows = plan_windows(duration, window_seconds=150.0, stride_seconds=120.0)
    owner: dict[int, int] = {}
    for index, row in enumerate(rows):
        midpoint = (row["start"] + row["end"]) / 2.0
        matches = [window.index for window in windows
                   if midpoint >= window.own_start
                   and (midpoint < window.own_end or window.index == windows[-1].index)]
        if len(matches) != 1:
            raise AssertionError(f"retained interval has {len(matches)} owner windows: {row}")
        owner[index] = matches[0]

    album = _fingerprint_album(config.identity_provider)
    pooled_by_index: dict[int, float | None] = {}
    window_state = []
    for window in windows:
        by_label: dict[str, list[tuple[int, tuple[float, ...]]]] = defaultdict(list)
        for index, vector in vectors.items():
            if owner[index] == window.index and rows[index]["speaker"] != "S00":
                by_label[rows[index]["speaker"]].append((index, vector))
        state = {"window": window.index, "scores": {}, "labels": {}}
        for label, items in sorted(by_label.items()):
            mean = tuple(_mean_unit_vector([vector for _, vector in items]))
            reference = album.reference(label)
            score = None if reference is None else float(cosine_similarity(mean, reference))
            state["scores"][label] = None if score is None else round(score, 6)
            state["labels"][label] = len(items)
            for index, _ in items:
                pooled_by_index[index] = score
            duration_sec = sum(rows[index]["end"] - rows[index]["start"] for index, _ in items)
            album.observe(
                canonical_speaker=label, vector=mean,
                duration_sec=duration_sec, span_id=window.index,
            )
        window_state.append(state)
    references = {
        speaker: tuple(reference)
        for speaker in album.speakers()
        if (reference := album.reference(speaker)) is not None
    }
    return pooled_by_index, references, {"windows": window_state}


def compare_codec(
    *,
    name: str,
    source: Path,
    baseline_path: Path,
    candidate_path: Path,
    reference_path: Path,
    encoder: Any,
    config: LiveProviderBundleConfig,
    scratch: Path,
) -> dict[str, Any]:
    baseline = meeting_segments(baseline_path)
    candidate = meeting_segments(candidate_path)
    if len(baseline) != len(candidate):
        raise AssertionError(f"{name}: retained segment count changed")
    for index, (left, right) in enumerate(zip(baseline, candidate, strict=True)):
        if (left["start"], left["end"], left["text"]) != (right["start"], right["end"], right["text"]):
            raise AssertionError(f"{name}: words/times changed at segment {index}")
    duration = max(max(row["end"] for row in baseline), 360.0 if name == "six.wav" else 1800.0)
    reference = reference_rows(reference_path, duration)
    vectors, _ = embed_rows(
        encoder, source, baseline,
        int(config.identity_provider["min_segment_samples"]), scratch,
    )
    pooled, references, reconstruction = pooled_scores(baseline, vectors, duration, config)
    margin = float(config.identity_config["min_match_margin"])
    policy_rows = {policy: [] for policy in POLICIES}
    decision_rows = []
    reasons = {policy: Counter() for policy in POLICIES}
    for index, (current_row, terminal_row) in enumerate(zip(baseline, candidate, strict=True)):
        current = current_row["speaker"]
        terminal = None if terminal_row["speaker"] == "S00" else terminal_row["speaker"]
        vector = vectors.get(index)
        terminal_score = None
        if terminal is not None and vector is not None and terminal in references:
            terminal_score = float(cosine_similarity(vector, references[terminal]))
        for policy in POLICIES:
            published, reason = choose(
                policy, current=current, terminal=terminal,
                pooled_score=pooled.get(index), terminal_score=terminal_score,
                margin=margin,
            )
            reasons[policy][reason] += 1
            policy_rows[policy].append({**current_row, "speaker": published})
        if terminal_row["speaker"] != current:
            decision_rows.append({
                "segment": index,
                "start": current_row["start"], "end": current_row["end"],
                "current": current, "p0_terminal": terminal_row["speaker"],
                "pooled_score": None if pooled.get(index) is None else round(float(pooled[index]), 6),
                "terminal_score": None if terminal_score is None else round(terminal_score, 6),
                "p3": policy_rows["P3"][-1]["speaker"],
                "p3_reason": choose(
                    "P3", current=current, terminal=terminal,
                    pooled_score=pooled.get(index), terminal_score=terminal_score,
                    margin=margin,
                )[1],
            })
    baseline_analysis = analyse(reference, baseline)
    results = {}
    for policy in POLICIES:
        policy_analysis = analyse(reference, policy_rows[policy])
        transitions = transition_report(baseline_analysis, policy_analysis)
        results[policy] = {
            "per_person": policy_analysis["per_person"],
            "transitions": transitions,
            "decision_reasons": dict(sorted(reasons[policy].items())),
            "words_times_identical": all(
                (left["start"], left["end"], left["text"]) ==
                (right["start"], right["end"], right["text"])
                for left, right in zip(baseline, policy_rows[policy], strict=True)
            ),
        }
    return {
        "name": name,
        "inputs": {
            "source": str(source), "baseline": str(baseline_path),
            "candidate": str(candidate_path), "reference": str(reference_path),
            "segments": len(baseline), "eligible_vectors": len(vectors),
            "duration_seconds": duration,
            "evidence_class": "retained-transcript counterfactual with fresh CPU ONNX vectors",
        },
        "baseline": baseline_analysis["per_person"],
        "policies": results,
        "p3_decisions": decision_rows,
        "pooled_reconstruction": reconstruction,
    }


def exact_raw_fixture(
    *,
    name: str,
    fixture_path: Path,
    source: Path,
    reference_path: Path,
    encoder: Any,
    config: LiveProviderBundleConfig,
    scratch: Path,
) -> dict[str, Any]:
    """Replay retained raw decoder windows through the production resolver.

    Unlike the stitched-transcript counterfactual, this has the exact local labels,
    pooled state scores, retrospective sweep, window audio, and final album shape.
    """
    fixture = load(fixture_path)
    windows = [WindowPlan(**row) for row in fixture["windows"]]
    groups = [
        [TranscriptSegment(**segment) for segment in group]
        for group in fixture["local_results"]
    ]
    paths = []
    for window in windows:
        path = scratch / f"exact-{name}-{window.index}.wav"
        extract_window_wav(
            source, path, start_seconds=window.start, duration_seconds=window.duration,
        )
        paths.append(path)
    resolution = AlbumIdentityResolver(config=config, encoder=encoder).resolve(
        windows, groups, window_audio_paths=paths,
    )

    labels: dict[tuple[int, str], str] = {}
    for state in resolution.diagnostics["windows"]:
        labels.update({
            (int(state["window"]), str(local)): str(canonical)
            for local, canonical in state["mapping"].items()
        })
    for correction in resolution.diagnostics["sweep"]["corrections"]:
        labels[int(correction["span_id"]), str(correction["local_speaker"])] = str(
            correction["canonical_speaker"]
        )

    minimum = int(config.identity_provider["min_segment_samples"])
    interval_vectors: dict[tuple[int, int], tuple[float, ...]] = {}
    means: dict[tuple[int, str], tuple[float, ...]] = {}
    durations: dict[tuple[int, str], float] = {}
    for window, group, path in zip(windows, groups, paths, strict=True):
        for local in dict.fromkeys(segment.speaker for segment in group if segment.speaker != "S00"):
            selected = [
                (index, max(0.0, segment.start), min(window.duration, segment.end))
                for index, segment in enumerate(group)
                if segment.speaker == local
                and round((min(window.duration, segment.end) - max(0.0, segment.start)) * 16000)
                >= minimum
            ]
            if not selected:
                continue
            embedded = encoder.embed_intervals(path, [(start, end) for _, start, end in selected])
            if len(embedded) != len(selected):
                raise AssertionError("exact fixture encoder omitted eligible interval")
            vectors = [tuple(vector) for vector in embedded]
            means[window.index, local] = tuple(_mean_unit_vector(vectors))
            durations[window.index, local] = sum(end - start for _, start, end in selected)
            for (segment_index, _, _), vector in zip(selected, vectors, strict=True):
                interval_vectors[window.index, segment_index] = vector

    album = _fingerprint_album(config.identity_provider)
    for state in resolution.diagnostics["windows"]:
        window_index = int(state["window"])
        for local, canonical in state["mapping"].items():
            key = (window_index, str(local))
            if key in means:
                album.observe(
                    canonical_speaker=str(canonical), vector=means[key],
                    duration_sec=durations[key], span_id=window_index,
                )
    references = {
        speaker: tuple(reference)
        for speaker in album.speakers()
        if (reference := album.reference(speaker)) is not None
    }
    states = {int(state["window"]): state for state in resolution.diagnostics["windows"]}
    margin = float(config.identity_config["min_match_margin"])
    policy_groups: dict[str, list[list[TranscriptSegment]]] = {
        policy: [] for policy in POLICIES
    }
    decision_rows = []
    reason_counts = {policy: Counter() for policy in POLICIES}
    for window, group, p0_group in zip(windows, groups, resolution.relabeled_results, strict=True):
        rendered = {policy: [] for policy in POLICIES}
        state = states[window.index]
        for index, (segment, p0_segment) in enumerate(zip(group, p0_group, strict=True)):
            current = labels.get((window.index, segment.speaker), "S00")
            terminal = None if p0_segment.speaker == "S00" else p0_segment.speaker
            pooled_score = next((
                float(row["score"])
                for row in state["scores"]
                if row["local_speaker"] == segment.speaker
                and row["canonical_speaker"] == current
            ), None)
            vector = interval_vectors.get((window.index, index))
            terminal_score = None
            if terminal is not None and vector is not None and terminal in references:
                terminal_score = float(cosine_similarity(vector, references[terminal]))
            for policy in POLICIES:
                published, reason = choose(
                    policy, current=current, terminal=terminal,
                    pooled_score=pooled_score, terminal_score=terminal_score,
                    margin=margin,
                )
                reason_counts[policy][reason] += 1
                rendered[policy].append(TranscriptSegment(
                    segment.start, segment.end, published, segment.text,
                ))
            if p0_segment.speaker != current:
                decision_rows.append({
                    "window": window.index, "segment": index,
                    "absolute_start": round(window.start + segment.start, 3),
                    "absolute_end": round(window.start + segment.end, 3),
                    "local": segment.speaker, "current": current,
                    "p0_terminal": p0_segment.speaker,
                    "pooled_score": None if pooled_score is None else round(pooled_score, 6),
                    "terminal_score": None if terminal_score is None else round(terminal_score, 6),
                    "p3": rendered["P3"][-1].speaker,
                    "p3_reason": choose(
                        "P3", current=current, terminal=terminal,
                        pooled_score=pooled_score, terminal_score=terminal_score,
                        margin=margin,
                    )[1],
                })
        for policy in POLICIES:
            policy_groups[policy].append(rendered[policy])

    baseline_groups = [
        [TranscriptSegment(segment.start, segment.end,
                           labels.get((window.index, segment.speaker), "S00"), segment.text)
         for segment in group]
        for window, group in zip(windows, groups, strict=True)
    ]
    baseline_rows = [
        {"start": item.start, "end": item.end, "speaker": item.speaker, "text": item.text}
        for item in _stitch_segments(windows, baseline_groups)
    ]
    duration = windows[-1].end
    reference = reference_rows(reference_path, duration)
    baseline_analysis = analyse(reference, baseline_rows)
    policies = {}
    for policy in POLICIES:
        rows = [
            {"start": item.start, "end": item.end, "speaker": item.speaker, "text": item.text}
            for item in _stitch_segments(windows, policy_groups[policy])
        ]
        analysis = analyse(reference, rows)
        policies[policy] = {
            "per_person": analysis["per_person"],
            "transitions": transition_report(baseline_analysis, analysis),
            "decision_reasons": dict(sorted(reason_counts[policy].items())),
            "words_times_identical": [
                (row["start"], row["end"], row["text"]) for row in rows
            ] == [
                (row["start"], row["end"], row["text"]) for row in baseline_rows
            ],
        }
    return {
        "name": name,
        "inputs": {
            "fixture": str(fixture_path), "source": str(source),
            "reference": str(reference_path), "windows": len(windows),
            "evidence_class": "exact retained raw-window production-seam replay",
        },
        "baseline": baseline_analysis["per_person"],
        "p0_matches_production_resolver": all(
            policy_groups["P0"][window.index] == resolution.relabeled_results[window.index]
            for window in windows
        ),
        "policies": policies,
        "p3_decisions": decision_rows,
    }


def policy_gate(codec_results: list[dict[str, Any]], synthetic: dict[str, Any]) -> dict[str, Any]:
    verdict = {}
    for policy in POLICIES:
        codecs = {}
        for arm in codec_results:
            base = arm["baseline"]["TOTAL"]
            result = arm["policies"][policy]
            total = result["per_person"]["TOTAL"]
            transitions = result["transitions"]
            codecs[arm["name"]] = {
                "words_times_identical": result["words_times_identical"],
                "wrong_seconds_decreased": total["wrong"] < base["wrong"],
                "correct_to_unknown_seconds": transitions["correct_to_unknown_seconds"],
                "correct_to_wrong_nonsplice_seconds": transitions["correct_to_wrong_nonsplice_seconds"],
                "correct_to_wrong_splice_seconds": transitions["correct_to_wrong_splice_seconds"],
                "all_people_retain_correct_coverage": all(
                    row["correct"] > 0
                    for person, row in result["per_person"].items() if person != "TOTAL"
                ),
            }
        case1 = synthetic[policy]["case1"]["published"] == "S01"
        case2 = synthetic[policy]["case2"]["published"] == "S01"
        verdict[policy] = {
            "synthetic_case1_pass": case1,
            "synthetic_case2_pass": case2,
            "codecs": codecs,
            "qualifies": case1 and case2 and all(
                row["words_times_identical"]
                and row["wrong_seconds_decreased"]
                and row["correct_to_wrong_nonsplice_seconds"] == 0
                and row["all_people_retain_correct_coverage"]
                for row in codecs.values()
            ) and all(
                row["correct_to_unknown_seconds"] == 0 for row in codecs.values()
            ),
        }
    return verdict


def main() -> int:
    if git("rev-parse", "HEAD") != EXPECTED_SHA:
        raise SystemExit("WP55a-P must run on unmodified a7a738cf")
    before = git("status", "--porcelain")
    config = LiveProviderBundleConfig.from_manifest(MANIFEST)
    encoder = _identity_encoder(config, interval_workers=4)
    reference = RUNTIME / "media/reference.jsonl"
    arms = (
        ("long.wav", RUNTIME / "media/long.wav", RUNTIME / "long.wav.meeting.json", CANDIDATE / "long.wav.meeting.json"),
        ("long.mp3", RUNTIME / "media/long.mp3", RUNTIME / "long.mp3.meeting.json", CANDIDATE / "long.mp3.meeting.json"),
        ("long.m4a", RUNTIME / "media/long.m4a", RUNTIME / "long.m4a.meeting.json", CANDIDATE / "long.m4a.meeting.json"),
        ("six.wav", RUNTIME / "media/six.wav", RUNTIME / "six.wav.meeting.json", ROUND2 / "retained-short-file-exports/six.wav.meeting.json"),
    )
    with tempfile.TemporaryDirectory(prefix="wp55a-file-policy-") as directory:
        scratch = Path(directory)
        codec_results = [
            compare_codec(
                name=name, source=source, baseline_path=baseline,
                candidate_path=candidate, reference_path=reference,
                encoder=encoder, config=config, scratch=scratch,
            )
            for name, source, baseline, candidate in arms
        ]
        exact_raw = [
            exact_raw_fixture(
                name=f"exact-{minutes}m-wav",
                fixture_path=ROOT / f"evidence/mvpfix/wp28/fixture-{minutes}.json",
                source=RUNTIME / f"media/{'six' if minutes == 6 else 'long'}.wav",
                reference_path=reference, encoder=encoder, config=config, scratch=scratch,
            )
            for minutes in (6, 30)
        ]
    synthetic = synthetic_controls(float(config.identity_config["min_match_margin"]))
    gates = policy_gate(codec_results, synthetic)
    qualifiers = [policy for policy in POLICIES if gates[policy]["qualifies"]]
    result = {
        "schema": "moss-round3-wp55a-file-policy-prototype.v1",
        "scope": {
            "candidate_sha": EXPECTED_SHA,
            "decoder_requests": 0,
            "network_calls": 0,
            "encoder": encoder.descriptor,
            "identity_provider_revision": config.identity_provider["revision"],
            "min_segment_samples": config.identity_provider["min_segment_samples"],
            "min_match_score": config.identity_config["min_match_score"],
            "min_match_margin": config.identity_config["min_match_margin"],
            "source_revision": "retained 120-second periodic composite; 135 reference rows / 1800 seconds",
            "scorer": "score_live_speaker_accuracy plus 10 ms union transition accounting",
            "splice_rule": (
                "Report separately any changed interval that touches a documented 60-second "
                "composite seam; exclude it only from the non-splice correct-to-wrong gate."
            ),
            "composite_independence_limit": (
                "The 30-minute source repeats 120 seconds: observed recurring behavior is "
                "effectively two source halves, not 15 independent samples."
            ),
        },
        "synthetic_controls": synthetic,
        "arms": codec_results,
        "exact_raw_arms": exact_raw,
        "gates": gates,
        "qualifying_policies": qualifiers,
        "selected_policy": "P3" if gates["P3"]["qualifies"] else None,
        "gate_verdict": "PASS" if gates["P3"]["qualifies"] else "FAIL",
        "git_status_before": before.splitlines(),
        "git_status_after": git("status", "--porcelain").splitlines(),
    }
    output = HERE / "file-policy-results.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    evidence = ROOT / "evidence/round3/wp55a-p/file-policy-results.json"
    evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "gate_verdict": result["gate_verdict"],
        "selected_policy": result["selected_policy"],
        "qualifying_policies": qualifiers,
        "gates": gates,
        "results": str(output),
        "evidence": str(evidence),
    }, indent=2, sort_keys=True))
    return 0 if result["gate_verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
