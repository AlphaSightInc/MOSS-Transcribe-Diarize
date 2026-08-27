#!/usr/bin/env python3
"""PROTOTYPE -- prove the saved 15/10 lexical arm can publish causally.

Question: can the preregistered lexical stitch turn every saved 15 s decode on a
10 s stride into contiguous, append-only revision proposals accepted by the real
``LiveSession`` seam, without reading reference truth?

One command:

    .venv/bin/python prototypes/streaming-diarization/live-policy-sweep-20260825/verify_causal_15_10.py \
      --output evidence/live-15-10-lexical-20260825/causal-prototype.json

The JSON contains every decode cursor, ownership interval, lexical alignment,
selected/dropped word, straddler, eligibility clock, proposal, seam outcome, and
reader-visible surface. Exit zero means every causal and saved-shadow equivalence
gate passed. This prototype never opens a reference transcript or invokes a scorer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
CONTEXT = REPO / "prototypes/live-file-gap-context"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(CONTEXT))

import proto_context_arms as bench  # noqa: E402
from moss_transcribe_diarize.app.live_session import (  # noqa: E402
    AudioFrame,
    CanonicalResult,
    EffectiveTranscriptSegment,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    LiveSession,
    TextRevisionProposal,
)
from moss_transcribe_diarize.app.live_transcript_convergence import (  # noqa: E402
    resolve_segment_overlaps,
)
from moss_transcribe_diarize.live_surface import published_speaker_label  # noqa: E402

SAMPLE_RATE = 16_000
WINDOW_SAMPLES = 15 * SAMPLE_RATE
STRIDE_SAMPLES = 10 * SAMPLE_RATE
EVIDENCE = REPO / "evidence/live-policy-sweep-20260825"
MANIFEST = EVIDENCE / "corpus/corpus-manifest.json"
RECOVERED = EVIDENCE / "moss-recovered"
CACHES = {
    "A": EVIDENCE / "moss/shadow-cache/pass-A.json",
    "B": EVIDENCE / "moss/shadow-cache/pass-B-recovery.json",
}
CASE_ORDER = (
    "mono_javier_intro_50s",
    "interview_bill_ackman_60s",
    "interview_keyu_jin_60s",
    "interview_adam_frank_180s",
    "discussion_jamie_dimon_180s",
    "discussion_rtfl_90s",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def actual_dir(pass_name: str, case_id: str) -> Path:
    if pass_name == "B" and case_id == "mono_javier_intro_50s":
        return EVIDENCE / "moss/replacement-pass-B-mono/actual"
    return EVIDENCE / f"moss/pass-{pass_name}/{case_id}/actual"


def settled_snapshot(pass_name: str, case_id: str) -> dict[str, Any]:
    rows = load_jsonl(actual_dir(pass_name, case_id) / "snapshots.jsonl")
    matches = [row["snapshot"]["session"] for row in rows if row.get("surface") == "pre_stop_settled"]
    if len(matches) != 1:
        raise RuntimeError(f"{pass_name}/{case_id}: expected one pre_stop_settled snapshot")
    return matches[0]


def base_rows(pass_name: str, case_id: str) -> list[dict[str, Any]]:
    return load_jsonl(actual_dir(pass_name, case_id) / "pre_stop_settled.jsonl")


def saved_rows(pass_name: str, case_id: str) -> list[dict[str, Any]]:
    return load_jsonl(
        RECOVERED
        / f"pass-{pass_name}/{case_id}/15_10_lexical_speaker_map-pre_stop_settled.jsonl"
    )


def transcript_of(rows: list[dict[str, Any]]) -> str:
    return "".join(
        f"[{float(row['start']):g}][{row['speaker']}]{row['text']}[{float(row['end']):g}]"
        for row in rows
        if float(row["end"]) > float(row["start"]) and str(row.get("text") or "").strip()
    )


def build_session(
    *, rows: list[dict[str, Any]], committed_samples: int, canonical_speakers: tuple[str, ...]
) -> LiveSession:
    """Build the frozen comparator surface through public production APIs.

    One synthetic span is sufficient: Goal 2 consumes the settled reader-visible
    comparator as a speaker timeline, not its historical endpoint partition. The real
    revision seam, projection rule, prefix hash, and committed record are exercised.
    """

    session = LiveSession(max_retained_samples=committed_samples + 1)
    session.accept_frame(
        AudioFrame(sequence=0, pcm=b"\0" * committed_samples * 2, sample_count=committed_samples)
    )
    span = session.freeze_until(committed_samples, reason="prototype_frozen_comparator")
    text = transcript_of(rows)
    local_speakers = tuple(
        str(row["speaker"])
        for row in rows
        if float(row["end"]) > float(row["start"]) and str(row.get("text") or "").strip()
    )
    preparation = LiveIdentityPreparation(
        span_id=span.id,
        epoch=span.epoch,
        start_sample=span.start_sample,
        end_sample=span.end_sample,
        base_snapshot_version=0,
        proposed_snapshot=LiveIdentitySnapshot(
            version=1,
            canonical_speakers=canonical_speakers,
            diagnostics=(("prototype", "frozen_goal1_surface"),),
        ),
        relabeled_transcript=text,
    )
    submission = session.submit_prepared_canonical(
        CanonicalResult(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            transcript=text,
            identity_preparation=preparation,
            local_speakers=local_speakers,
        )
    )
    if not submission.submitted:
        raise RuntimeError(f"could not build frozen comparator: {submission.refusal}")
    return session


def cache_entry(
    entries: dict[str, Any], *, wav_sha256: str, start_sample: int, end_sample: int
) -> tuple[str, dict[str, Any]]:
    matches = []
    prefix = f"{wav_sha256}:{start_sample}:{end_sample}:"
    for key, value in entries.items():
        if key.startswith(prefix):
            matches.append((key, value))
    if len(matches) != 1:
        raise RuntimeError(
            f"cache range {wav_sha256}:{start_sample}:{end_sample} has {len(matches)} matches"
        )
    return matches[0]


def word_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "word": row["word"],
        "start_sample": int(round(float(row["start"]) * SAMPLE_RATE)),
        "end_sample": int(round(float(row["end"]) * SAMPLE_RATE)),
        "speaker": row["speaker"],
        "source": row["src"],
    }


def segment_view(segment: EffectiveTranscriptSegment) -> dict[str, Any]:
    return {
        "start_sample": segment.start_sample,
        "end_sample": segment.end_sample,
        "text": segment.text,
        "canonical_speaker": segment.canonical_speaker,
        "authority": segment.authority,
    }


def normalized_word(word: str) -> str:
    return "".join(character for character in word.lower() if character.isalnum())


def token_speaker_pairs(
    segments: list[dict[str, Any]], *, before_sample: int
) -> list[list[str]]:
    source = [
        bench.Segment(
            float(row["start"]), float(row["end"]), str(row["speaker"]), str(row["text"])
        )
        for row in segments
    ]
    words = bench.word_rows(source, "equivalence")
    return [
        [normalized_word(str(row["word"])), str(row["speaker"])]
        for row in words
        if int(round(float(row["mid"]) * SAMPLE_RATE)) < before_sample
        and normalized_word(str(row["word"]))
    ]


def displayed_surface(session: LiveSession) -> list[dict[str, Any]]:
    snapshot = session.snapshot()
    speakers = snapshot.identity_snapshot.canonical_speakers
    return [
        {
            "start": segment.start_sample / SAMPLE_RATE,
            "end": segment.end_sample / SAMPLE_RATE,
            "speaker": published_speaker_label(segment.canonical_speaker, speakers),
            "text": segment.text,
            "authority": segment.authority,
        }
        for segment in snapshot.effective_transcript
    ]


def run_case(
    *, pass_name: str, case: dict[str, Any], entries: dict[str, Any]
) -> dict[str, Any]:
    case_id = str(case["case_id"])
    duration_samples = int(case["audio"]["samples"])
    original_session = settled_snapshot(pass_name, case_id)
    committed_samples = int(original_session["committed_samples"])
    canonical_speakers = tuple(original_session["identity_snapshot"]["canonical_speakers"])
    frozen_rows = base_rows(pass_name, case_id)
    session = build_session(
        rows=frozen_rows,
        committed_samples=committed_samples,
        canonical_speakers=canonical_speakers,
    )
    before = session.snapshot()
    frozen_hash = before.committed_prefix_hash
    frozen_commits = before.committed
    published_words: list[dict[str, Any]] = []
    windows: list[dict[str, Any]] = []
    intended_frontier = 0
    live_frontier = 0
    seam_live = True
    completion_clock = 0.0
    failures: list[str] = []

    index = 0
    while index * STRIDE_SAMPLES + WINDOW_SAMPLES <= committed_samples:
        decode_start = index * STRIDE_SAMPLES
        decode_end = decode_start + WINDOW_SAMPLES
        key, cached = cache_entry(
            entries,
            wav_sha256=str(case["audio"]["wav_sha256"]),
            start_sample=decode_start,
            end_sample=decode_end,
        )
        fresh_segments = bench.absolute_segments(
            str(cached["transcript"]), start_sample=decode_start, end_sample=decode_end
        )
        fresh_words = bench.word_rows(fresh_segments, (pass_name, case_id, index))
        if index == 0:
            selected, decision = list(fresh_words), "first_window"
        else:
            selected, decision = bench.trim_prefix_by_text(
                published_words, fresh_words, prefix_start=decode_start / SAMPLE_RATE
            )
        selected_ids = {id(row) for row in selected}
        dropped = [row for row in fresh_words if id(row) not in selected_ids]
        selected_behind = [
            row
            for row in selected
            if int(round(float(row["end"]) * SAMPLE_RATE)) <= intended_frontier
        ]
        selected_straddlers = [
            row
            for row in selected
            if int(round(float(row["start"]) * SAMPLE_RATE)) < intended_frontier
            < int(round(float(row["end"]) * SAMPLE_RATE))
        ]
        dropped_straddlers = [
            row
            for row in dropped
            if int(round(float(row["start"]) * SAMPLE_RATE)) < intended_frontier
            < int(round(float(row["end"]) * SAMPLE_RATE))
        ]
        if selected_behind:
            failures.append(f"window {index}: selected words wholly behind frontier")
        if selected_straddlers:
            failures.append(f"window {index}: unmatched selected word straddles frontier")

        grouped = bench.rows_to_segments(selected, duration_samples / SAMPLE_RATE)
        placed = [
            (
                str(segment.speaker),
                int(round(segment.start * SAMPLE_RATE)),
                int(round(segment.end * SAMPLE_RATE)),
                str(segment.text),
            )
            for segment in grouped
        ]
        normalized = resolve_segment_overlaps(placed)
        proposal_segments = tuple(
            EffectiveTranscriptSegment(
                start_sample=start,
                end_sample=end,
                text=text,
                canonical_speaker=None,
                authority="rolling",
            )
            for _speaker, start, end, text in normalized.segments
        )
        outside = [
            segment_view(segment)
            for segment in proposal_segments
            if segment.start_sample < intended_frontier or segment.end_sample > decode_end
        ]
        if outside:
            failures.append(f"window {index}: normalized segment outside owned interval")

        ready_seconds = decode_end / SAMPLE_RATE
        completion_clock = max(ready_seconds, completion_clock) + float(cached["elapsed_seconds"])
        proposal = TextRevisionProposal(
            epoch=session.epoch,
            base_text_revision_version=session.snapshot().text_revision_version,
            source="rolling",
            start_sample=intended_frontier,
            end_sample=decode_end,
            segments=proposal_segments,
            decode_elapsed_sec=float(cached["elapsed_seconds"]),
            normalization_merged_segments=normalized.merged,
            normalization_dropped_segments=normalized.dropped,
            normalization_displaced_samples=normalized.displaced_samples,
        )
        if seam_live:
            outcome = session.apply_text_revision(proposal)
            seam_outcome = {
                "attempted": True,
                "applied": outcome.applied,
                "refusal": outcome.refusal,
                "version": outcome.version,
                "canonical_through_sample": outcome.canonical_through_sample,
            }
            if not outcome.applied:
                failures.append(f"window {index}: seam refusal {outcome.refusal}")
                seam_live = False
            else:
                live_frontier = outcome.canonical_through_sample
        else:
            snapshot = session.snapshot()
            seam_outcome = {
                "attempted": False,
                "applied": False,
                "refusal": "not_attempted_after_causal_failure",
                "version": snapshot.text_revision_version,
                "canonical_through_sample": snapshot.canonical_through_sample,
            }
        published_words.extend(selected)
        intended_frontier = decode_end

        after_window = session.snapshot()
        if after_window.committed_prefix_hash != frozen_hash or after_window.committed != frozen_commits:
            failures.append(f"window {index}: frozen comparator changed")
        windows.append(
            {
                "window_index": index,
                "decode_cursor": [decode_start, decode_end],
                "frontier_before": proposal.start_sample,
                "owned_interval": [proposal.start_sample, proposal.end_sample],
                "intended_frontier_after": intended_frontier,
                "live_frontier_after": live_frontier,
                "cache_key": key,
                "decode_classification": cached["classification"],
                "alignment": {
                    "decision": decision,
                    "fresh_words": len(fresh_words),
                    "selected_words": len(selected),
                    "dropped_words": len(dropped),
                },
                "selected": [word_view(row) for row in selected],
                "dropped_aligned": [word_view(row) for row in dropped],
                "straddlers": {
                    "selected_unmatched": [word_view(row) for row in selected_straddlers],
                    "dropped_aligned": [word_view(row) for row in dropped_straddlers],
                },
                "eligibility_clock": {
                    "audio_ready_seconds": ready_seconds,
                    "decode_elapsed_seconds": float(cached["elapsed_seconds"]),
                    "publication_seconds": completion_clock,
                    "ready_to_publication_seconds": completion_clock - ready_seconds,
                },
                "normalization": {
                    "merged_segments": normalized.merged,
                    "dropped_segments": normalized.dropped,
                    "displaced_samples": normalized.displaced_samples,
                },
                "proposal_segments": [segment_view(segment) for segment in proposal_segments],
                "outside_owned_interval": outside,
                "seam_outcome": seam_outcome,
                "effective_surface": displayed_surface(session),
            }
        )
        index += 1

    final = session.snapshot()
    next_decode_start = index * STRIDE_SAMPLES
    next_decode_end = next_decode_start + WINDOW_SAMPLES
    incomplete_tail_not_planned = next_decode_end > committed_samples
    if not incomplete_tail_not_planned:
        failures.append("planner stopped despite a complete next 15 second window")
    suffix = [
        segment_view(segment)
        for segment in final.effective_transcript
        if segment.authority == "provisional"
    ]
    if any(segment["start_sample"] < final.canonical_through_sample for segment in suffix):
        failures.append("provisional suffix begins behind candidate frontier")

    saved = saved_rows(pass_name, case_id)
    frozen_segments = [
        bench.Segment(
            float(row["start"]), float(row["end"]), str(row["speaker"]), str(row["text"])
        )
        for row in frozen_rows
    ]
    timeline = bench.SpeakerTimeline(frozen_segments)
    frozen_words = bench.word_rows(frozen_segments, "goal1_frozen_comparator")
    stitched_words = published_words + [
        row
        for row in frozen_words
        if float(row["mid"]) >= intended_frontier / SAMPLE_RATE
    ]
    reconstructed_segments = timeline.relabel(
        bench.rows_to_segments(stitched_words, duration_samples / SAMPLE_RATE)
    )
    reconstructed_rows = [
        {
            "start": segment.start,
            "end": segment.end,
            "speaker": segment.speaker,
            "text": segment.text,
        }
        for segment in reconstructed_segments
    ]
    actual_display = displayed_surface(session)
    actual_prefix = [row for row in actual_display if row["authority"] == "rolling"]
    actual_pairs = token_speaker_pairs(actual_prefix, before_sample=live_frontier)
    expected_live_pairs = token_speaker_pairs(saved, before_sample=live_frontier)
    reconstructed_pairs = token_speaker_pairs(
        reconstructed_rows, before_sample=intended_frontier
    )
    expected_pairs = token_speaker_pairs(saved, before_sample=intended_frontier)
    content_equivalent = [pair[0] for pair in reconstructed_pairs] == [
        pair[0] for pair in expected_pairs
    ]
    speaker_projection_equivalent = reconstructed_pairs == expected_pairs
    live_prefix_equivalent = actual_pairs == expected_live_pairs
    if not content_equivalent:
        failures.append("candidate-owned token surface differs from saved lexical shadow")
    if not speaker_projection_equivalent:
        failures.append("candidate-owned token/speaker projection differs from saved lexical shadow")
    if not live_prefix_equivalent:
        failures.append("accepted live prefix differs from saved lexical shadow")

    return {
        "pass": pass_name,
        "case_id": case_id,
        "duration_samples": duration_samples,
        "committed_samples": committed_samples,
        "windows_expected": max(0, (committed_samples - WINDOW_SAMPLES) // STRIDE_SAMPLES + 1),
        "windows_executed": len(windows),
        "intended_candidate_frontier_sample": intended_frontier,
        "accepted_live_frontier_sample": live_frontier,
        "next_decode_cursor": [next_decode_start, next_decode_end],
        "incomplete_tail_not_planned": incomplete_tail_not_planned,
        "tail_authority": "provisional",
        "provisional_suffix": suffix,
        "frozen_comparator": {
            "prefix_hash_before": frozen_hash,
            "prefix_hash_after": final.committed_prefix_hash,
            "committed_records_unchanged": final.committed == frozen_commits,
        },
        "equivalence": {
            "scope": "candidate-owned prefix only; saved suffix is Goal 1 10/10 comparator text",
            "accepted_live_token_speaker_pairs": actual_pairs,
            "saved_accepted_live_token_speaker_pairs": expected_live_pairs,
            "reconstructed_candidate_token_speaker_pairs": reconstructed_pairs,
            "saved_token_speaker_pairs": expected_pairs,
            "content_equivalent": content_equivalent,
            "speaker_projection_equivalent": speaker_projection_equivalent,
            "accepted_live_prefix_equivalent": live_prefix_equivalent,
        },
        "windows": windows,
        "failures": failures,
        "passed": not failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite {output}")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = {str(case["case_id"]): case for case in manifest["cases"]}
    caches = {
        pass_name: json.loads(path.read_text(encoding="utf-8"))["entries"]
        for pass_name, path in CACHES.items()
    }
    results = [
        run_case(pass_name=pass_name, case=cases[case_id], entries=caches[pass_name])
        for pass_name in ("A", "B")
        for case_id in CASE_ORDER
    ]
    failures = [
        f"{result['pass']}/{result['case_id']}: {failure}"
        for result in results
        for failure in result["failures"]
    ]
    payload = {
        "schema": "moss-causal-15-10-lexical-prototype.v1",
        "question": "Can saved 15/10 lexical publish causally through the production seam?",
        "truth_blind": True,
        "reference_transcripts_opened": 0,
        "scorer_invocations": 0,
        "geometry": {"window_samples": WINDOW_SAMPLES, "stride_samples": STRIDE_SAMPLES},
        "lexical_policy": "proto_context_arms.trim_prefix_by_text",
        "production_seams": ["resolve_segment_overlaps", "LiveSession.apply_text_revision"],
        "inputs": {
            "manifest": {"path": str(MANIFEST.relative_to(REPO)), "sha256": sha256(MANIFEST)},
            "caches": {
                pass_name: {"path": str(path.relative_to(REPO)), "sha256": sha256(path)}
                for pass_name, path in CACHES.items()
            },
        },
        "denominator": {
            "passes": 2,
            "cases": 12,
            "windows": sum(result["windows_expected"] for result in results),
            "audio_seconds": 2 * float(manifest["denominator"]["audio_seconds"]),
        },
        "results": results,
        "failures": failures,
        "verdict": "PASS_CAUSAL" if not failures else "FAIL_STOP_NO_IMPLEMENTATION",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
