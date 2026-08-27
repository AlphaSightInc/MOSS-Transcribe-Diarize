#!/usr/bin/env python3
"""PROTOTYPE: audit the shared overlap rule on every retained 10/10 decode.

Question: can the measured terminal overlap rule normalize every retained rolling proposal
without losing words or regressing the reconstructed full surface, while making the Jamie
window-4 proposal admissible through LiveSession's real revision seam?

One command:
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
    prototypes/streaming-diarization/live-policy-sweep-20260825/audit_rolling_normalization.py \
    --sweep evidence/live-policy-sweep-20260825 \
    --output evidence/live-g4-recovery-20260825/normalization-prototype.json

The retained decoder outputs are hypotheses. Reference truth is read only by score_surface,
after normalization decisions are complete.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Sequence

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SURFACE_SCRIPT = HERE.parent / "live-surface-optimization/measure_three_surfaces.py"
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.live_session import (  # noqa: E402
    AudioFrame,
    CanonicalResult,
    EffectiveTranscriptSegment,
    LiveSession,
    TextRevisionProposal,
    _project_canonical_speaker,
)
from moss_transcribe_diarize.app.live_span_bounds import span_segments  # noqa: E402
from moss_transcribe_diarize.app.live_transcript_convergence import (  # noqa: E402
    resolve_segment_overlaps,
)

_SPEC = importlib.util.spec_from_file_location("g4_surface_measurement", SURFACE_SCRIPT)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load {SURFACE_SCRIPT}")
surface = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = surface
_SPEC.loader.exec_module(surface)

SAMPLE_RATE = 16_000
WINDOW_SAMPLES = 160_000
CACHE_NAMES = {"A": "pass-A.json", "B": "pass-B-recovery.json"}
LOWER_IS_BETTER = ("wer", "der", "reference_speech_der")
HIGHER_IS_BETTER = (
    "text_speaker_accuracy",
    "speaker_accuracy",
    "matched_word_speaker_accuracy",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def words(segments: Sequence[tuple[str, int, int, str]]) -> list[str]:
    return " ".join(text for _, _, _, text in segments).split()


def make_committed_session(samples: int) -> LiveSession:
    session = LiveSession(max_retained_samples=samples)
    session.accept_frame(AudioFrame(sequence=0, pcm=b"\0" * (2 * samples), sample_count=samples))
    frozen = session.freeze_until(samples, reason="prototype_full_extent")
    submitted = session.submit_canonical(
        CanonicalResult(
            span_id=frozen.id,
            epoch=frozen.epoch,
            start_sample=0,
            end_sample=samples,
            transcript=f"[0][S01]prototype base[{samples / SAMPLE_RATE:g}]",
        )
    )
    if not submitted:
        raise RuntimeError("prototype base did not commit")
    return session


def proposal(
    session: LiveSession,
    start: int,
    end: int,
    segments: Sequence[tuple[str, int, int, str]],
) -> TextRevisionProposal:
    snap = session.snapshot()
    return TextRevisionProposal(
        epoch=snap.epoch,
        base_text_revision_version=snap.text_revision_version,
        source="rolling",
        start_sample=start,
        end_sample=end,
        segments=tuple(
            EffectiveTranscriptSegment(
                start_sample=segment_start,
                end_sample=segment_end,
                text=text,
                canonical_speaker=None,
                authority="rolling",
            )
            for _, segment_start, segment_end, text in segments
        ),
        decode_elapsed_sec=0.0,
    )


def base_surface(sweep: Path, pass_name: str, case_id: str) -> tuple[EffectiveTranscriptSegment, ...]:
    snapshot_path = (
        sweep / "moss" / f"pass-{pass_name}" / case_id / "actual" / "snapshots.jsonl"
    )
    if pass_name == "B" and case_id == "mono_javier_intro_50s":
        snapshot_path = sweep / "moss" / "replacement-pass-B-mono" / "actual" / "snapshots.jsonl"
    snapshots = [
        json.loads(line)
        for line in snapshot_path.read_text(encoding="utf-8").splitlines()
    ]
    stopped = next(row for row in snapshots if row["surface"] == "stop_return")
    return tuple(
        EffectiveTranscriptSegment(
            start_sample=int(row["start_sample"]),
            end_sample=int(row["end_sample"]),
            text=str(row["text"]),
            canonical_speaker=row.get("canonical_speaker"),
            authority=str(row["authority"]),
        )
        for row in stopped["snapshot"]["session"]["effective_transcript"]
    )


def scored_rows(
    proposals: Sequence[Sequence[tuple[str, int, int, str]]],
    base: Sequence[EffectiveTranscriptSegment],
    full_window_end: int,
) -> list[dict[str, Any]]:
    selected: list[EffectiveTranscriptSegment] = []
    for placed in proposals:
        for _, start, end, text in placed:
            selected.append(
                EffectiveTranscriptSegment(
                    start_sample=start,
                    end_sample=end,
                    text=text,
                    canonical_speaker=_project_canonical_speaker(start, end, base),
                    authority="rolling",
                )
            )
    selected.extend(row for row in base if row.start_sample >= full_window_end)
    return [
        {
            "start": row.start_sample / SAMPLE_RATE,
            "end": row.end_sample / SAMPLE_RATE,
            "speaker": row.canonical_speaker or "S00",
            "text": row.text,
        }
        for row in selected
    ]


def score_regressions(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    regressions = []
    for field in LOWER_IS_BETTER:
        if after[field] > before[field] + 1e-12:
            regressions.append(field)
    for field in HIGHER_IS_BETTER:
        if after[field] + 1e-12 < before[field]:
            regressions.append(field)
    return regressions


def retained_windows(
    cache: dict[str, Any], audio_hash: str, expected: int
) -> list[tuple[int, int, dict[str, Any], str]]:
    found = []
    for key, value in cache["entries"].items():
        parts = key.split(":")
        if len(parts) != 6 or parts[0] != audio_hash:
            continue
        start, end, token_cap = int(parts[1]), int(parts[2]), int(parts[4])
        if end - start == WINDOW_SAMPLES and token_cap == 938:
            found.append((start, end, value, key))
    found.sort(key=lambda item: item[0])
    expected_ranges = [(index * WINDOW_SAMPLES, (index + 1) * WINDOW_SAMPLES) for index in range(expected)]
    actual_ranges = [(start, end) for start, end, _, _ in found]
    if actual_ranges != expected_ranges:
        raise RuntimeError(f"retained 10/10 grid mismatch: expected={expected_ranges} actual={actual_ranges}")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sweep = args.sweep.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite {output}")

    manifest = load_json(sweep / "corpus" / "corpus-manifest.json")
    cases: list[dict[str, Any]] = []
    proposals_total = ordinary_total = changed_total = 0
    all_words_preserved = all_admissible = all_ordinary_identical = True
    all_score_regressions: list[str] = []
    jamie_records: list[dict[str, Any]] = []

    for pass_name, cache_name in CACHE_NAMES.items():
        cache = load_json(sweep / "moss" / "shadow-cache" / cache_name)
        for case in manifest["cases"]:
            case_id = case["case_id"]
            expected = int(case["audio"]["samples"]) // WINDOW_SAMPLES
            windows = retained_windows(cache, case["audio"]["wav_sha256"], expected)
            session = make_committed_session(int(case["audio"]["samples"]))
            base = base_surface(sweep, pass_name, case_id)
            raw_views: list[tuple[tuple[str, int, int, str], ...]] = []
            normalized_views: list[tuple[tuple[str, int, int, str], ...]] = []
            records = []

            for window_index, (start, end, value, cache_key) in enumerate(windows):
                placed = tuple(
                    (
                        parsed.speaker,
                        start + int(round(parsed.start * SAMPLE_RATE)),
                        start + int(round(parsed.end * SAMPLE_RATE)),
                        parsed.text,
                    )
                    for parsed in span_segments(value["transcript"], sample_count=WINDOW_SAMPLES)
                    if parsed.text.strip() and parsed.end > parsed.start
                )
                resolution = resolve_segment_overlaps(placed)
                raw_outcome = session.apply_text_revision(proposal(session, start, end, placed))
                if raw_outcome.applied:
                    normalized_applied = True
                    normalized_refusal = None
                else:
                    normalized_outcome = session.apply_text_revision(
                        proposal(session, start, end, resolution.segments)
                    )
                    normalized_applied = normalized_outcome.applied
                    normalized_refusal = normalized_outcome.refusal

                before_words = words(placed)
                after_words = words(resolution.segments)
                ordered_before = all(
                    current[1] >= previous[2] for previous, current in zip(placed, placed[1:])
                )
                ordinary = ordered_before
                byte_identical = resolution.segments == placed
                record = {
                    "pass": pass_name,
                    "case_id": case_id,
                    "window_index": window_index,
                    "interval": [start, end],
                    "cache_key": cache_key,
                    "input_segments": [list(row) for row in placed],
                    "output_segments": [list(row) for row in resolution.segments],
                    "merged": resolution.merged,
                    "dropped": resolution.dropped,
                    "displaced_samples": resolution.displaced_samples,
                    "word_count_before": len(before_words),
                    "word_count_after": len(after_words),
                    "word_stream_identical": before_words == after_words,
                    "ordinary_disjoint": ordinary,
                    "byte_identical": byte_identical,
                    "session_refusal_before": raw_outcome.refusal,
                    "session_refusal_after": normalized_refusal,
                    "session_admissible_after": normalized_applied,
                }
                records.append(record)
                raw_views.append(placed)
                normalized_views.append(resolution.segments)
                proposals_total += 1
                ordinary_total += int(ordinary)
                changed_total += int(not byte_identical)
                all_words_preserved &= before_words == after_words
                all_admissible &= normalized_applied
                all_ordinary_identical &= (not ordinary) or byte_identical
                if case_id == "discussion_jamie_dimon_180s" and window_index == 4:
                    jamie_records.append(record)

            full_end = expected * WINDOW_SAMPLES
            score_case = surface.Case(case_id, sweep / "corpus" / case_id, Path("unused"))
            scores_before = surface.score_surface(score_case, scored_rows(raw_views, base, full_end))
            scores_after = surface.score_surface(
                score_case, scored_rows(normalized_views, base, full_end)
            )
            regressions = score_regressions(scores_before, scores_after)
            all_score_regressions.extend(f"{pass_name}:{case_id}:{field}" for field in regressions)
            cases.append(
                {
                    "pass": pass_name,
                    "case_id": case_id,
                    "proposals": len(records),
                    "full_window_end_sample": full_end,
                    "scores_before": scores_before,
                    "scores_after": scores_after,
                    "score_regressions": regressions,
                    "records": records,
                }
            )

    jamie_gate = (
        len(jamie_records) == 2
        and all(row["displaced_samples"] == 2720 for row in jamie_records)
        and all(row["word_count_before"] == row["word_count_after"] == 24 for row in jamie_records)
        and all(row["merged"] == row["dropped"] == 0 for row in jamie_records)
        and all(row["session_refusal_before"] == "segments_out_of_order" for row in jamie_records)
        and all(row["session_admissible_after"] for row in jamie_records)
    )
    gates = {
        "proposals_exact_122": proposals_total == 122,
        "ordinary_disjoint_byte_identical": all_ordinary_identical,
        "every_observed_proposal_admissible": all_admissible,
        "no_observed_word_dropped": all_words_preserved,
        "full_surface_scores_non_regressing": not all_score_regressions,
        "jamie_window_4_exact": jamie_gate,
    }
    report = {
        "schema": "moss-g4-normalization-prototype.v1",
        "question": __doc__.splitlines()[2],
        "truth_blind_decision": True,
        "denominator": {
            "passes": 2,
            "cases": 6,
            "proposals": proposals_total,
            "ordinary_disjoint": ordinary_total,
            "changed_by_normalizer": changed_total,
        },
        "gates": gates,
        "score_regressions": all_score_regressions,
        "jamie_window_4": jamie_records,
        "cases": cases,
        "verdict": "PASS" if all(gates.values()) else "FAIL",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
