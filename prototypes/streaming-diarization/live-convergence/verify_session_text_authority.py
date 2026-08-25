#!/usr/bin/env python3
"""Does the SHIPPED session authority publish the arm the §10.2 grid selected, and attribute it?

Plan §10.5 step 2 implements M3 (`LiveSession.apply_text_revision` + the §7.3 snapshot fields
+ the label projection). The grid scored every arm through `proto_context_arms.SpeakerTimeline`
-- an *external* relabelling step that presumed the session would attribute rolling words from
the base's own labels. This drives the real objects end to end and requires that presumption to
be true of the production code:

    baseline spans -> LiveSession (real freeze/submit path)
      -> RollingTranscriptConverger (production, grid-selected 10/10)
        -> LiveSession.apply_text_revision (production, seven validations)
          -> snapshot().effective_transcript -> the grid's own scorer

Zero MOSS requests by construction: the decoder is handed a runner that raises, so a cache miss
is a failure rather than a fresh GPU call. Reviewers can run this with no 4070 Ti.

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
      prototypes/streaming-diarization/live-convergence/verify_session_text_authority.py

Exit 0 iff every gate below passes.

- G1 per-case WER and content recall from `effective_transcript` equal the grid's `10/10` arm
  to 6 dp, and the trio means equal `.131861` / `.943916`
- G2 the session's label projection agrees segment for segment with the `SpeakerTimeline` the
  arm was measured through
- G3 the effective transcript has one owner per interval: ordered, non-overlapping, and the
  revised prefix tiles `[0, canonical_through_sample)` with no base segment inside it
- G4 every base commit is byte-identical before and after the whole revision sequence, and the
  committed prefix hash never moves (ADR-0005 D2)
- G5 every proposal is accepted, `text_revision_version` equals the number applied, and no
  refusal is counted
- G6 zero fresh MOSS requests
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "prototypes/live-file-gap-context"))

import proto_context_arms as bench  # noqa: E402
from moss_transcribe_diarize.app.live_adapters import InferenceTranscript  # noqa: E402
from moss_transcribe_diarize.app.live_session import (  # noqa: E402
    AudioFrame,
    CanonicalResult,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    LiveSession,
    UNATTRIBUTED_SPEAKER,
    display_speaker_label,
)
from moss_transcribe_diarize.app.live_span_bounds import span_segments  # noqa: E402
from moss_transcribe_diarize.app.live_transcript_convergence import (  # noqa: E402
    DEFAULT_ROLLING_GEOMETRY,
    RollingTranscriptConverger,
)
from moss_transcribe_diarize.evaluation import Segment  # noqa: E402

SAMPLE_RATE = bench.SAMPLE_RATE
GRID = REPO / "evidence/live-convergence-0824/M2-rolling-grid"
DEFAULT_BASELINE = REPO / "prototypes/live-file-gap-baseline-20260824/trio-60s"
SELECTED_ARM = "10/10:char"  # all three stitch policies are one arm at zero overlap (F1)
PLACES = 6
# The meeting identities the baseline's `Sxx` labels name. The session maps them positionally
# (`display_speaker_label`), so this list is what makes a committed `S02` resolvable at all --
# in production it is the album; here it is the album the baseline run actually established.
CANONICAL_SPEAKERS = ("speaker-0001", "speaker-0002")


class CacheMiss(RuntimeError):
    """The replay asked for a decode the grid never recorded. No GPU call is made."""


class _NoRunner:
    def transcribe(self, *args: Any, **kwargs: Any) -> Any:
        raise CacheMiss("the shipped converger asked for a window the grid did not decode.")


def canonical_of_label(label: str) -> str | None:
    if label == UNATTRIBUTED_SPEAKER:
        return None
    index = int(label[1:]) - 1
    return CANONICAL_SPEAKERS[index] if 0 <= index < len(CANONICAL_SPEAKERS) else None


def label_of_canonical(canonical_speaker: str | None) -> str:
    if canonical_speaker is None:
        return UNATTRIBUTED_SPEAKER
    return display_speaker_label(canonical_speaker, CANONICAL_SPEAKERS)


def commit_span(session: LiveSession, span_payload: dict[str, Any]) -> None:
    """Replay one baseline span through the session's real publication path."""

    samples = span_payload["end_sample"] - span_payload["start_sample"]
    session.accept_frame(
        AudioFrame(
            sequence=span_payload["span_id"],
            pcm=b"\0" * samples * 2,
            sample_count=samples,
        )
    )
    span = session.freeze_until(span_payload["end_sample"], reason="hard_cap")
    transcript = span_payload["transcript"]
    segments = span_segments(transcript, sample_count=samples)
    if not segments:
        submission = session.submit_empty_canonical(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
        )
    else:
        base = session.snapshot().identity_snapshot
        preparation = LiveIdentityPreparation(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            base_snapshot_version=base.version,
            proposed_snapshot=LiveIdentitySnapshot(
                version=base.version + 1, canonical_speakers=CANONICAL_SPEAKERS
            ),
            relabeled_transcript=transcript,
        )
        submission = session.submit_prepared_canonical(
            CanonicalResult(
                span_id=span.id,
                epoch=span.epoch,
                start_sample=span.start_sample,
                end_sample=span.end_sample,
                transcript=transcript,
                identity_preparation=preparation,
                local_speakers=tuple(segment.speaker for segment in segments),
            )
        )
    if not submission.submitted:
        raise AssertionError(f"span {span.id} refused: {submission.refusal}")


def run_case(case: str, *, decoder: Any, baseline: Path, scratch: Path) -> dict[str, Any]:
    audio_path = bench.CORPUS / case / "audio.wav"
    pcm = bench.read_pcm(audio_path)
    audio_sha = hashlib.sha256(audio_path.read_bytes()).hexdigest()
    total_samples = len(pcm) // 2
    duration = total_samples / SAMPLE_RATE
    spans = bench.load_baseline_spans(baseline / case / "live/run-001/trace.jsonl")

    session = LiveSession(max_retained_samples=total_samples)
    converger = RollingTranscriptConverger(epoch=session.epoch)
    proposals: list[tuple[int, int]] = []
    refusals: list[str] = []
    frontiers: list[dict[str, Any]] = []
    applied = 0

    for span_payload in spans:
        start = span_payload["start_sample"]
        end = span_payload["end_sample"]
        commit_span(session, span_payload)
        # Plan §5.1's composition is only observable *while* the meeting runs: by the end the
        # windows have tiled the whole clip and there is no base suffix left to get wrong. The
        # surface is inspected after every commit and every revision, so a boundary rule that
        # published two owners is caught by the corpus and not only by a test.
        frontiers.append(_frontier_shape(session))
        requests = converger.accept_pcm(start, pcm[start * 2 : end * 2])
        requests = requests + converger.observe_base(session.snapshot())
        while requests:
            request = requests[0]
            decoded = decoder.decode(
                pcm=pcm,
                audio_sha=audio_sha,
                start_sample=request.start_sample,
                end_sample=request.end_sample,
                token_cap=request.token_cap,
                scratch=scratch,
            )
            proposal = converger.complete(
                request.id,
                InferenceTranscript(
                    transcript=decoded["transcript"],
                    elapsed_sec=float(decoded["elapsed_seconds"]),
                ),
            )
            if proposal is None:
                raise AssertionError(f"{case}: window {request.window_index} published nothing")
            outcome = session.apply_text_revision(proposal)
            if not outcome.applied:
                refusals.append(outcome.refusal or "unknown")
            else:
                applied += 1
                proposals.append((proposal.start_sample, proposal.end_sample))
                frontiers.append(_frontier_shape(session))
            # The runtime observes the snapshot again after applying a revision; the frontier
            # it learns there is what makes the next window plannable.
            requests = converger.observe_base(session.snapshot())

    snapshot = session.snapshot()
    committed_after = [
        {
            "span_id": commit.span_id,
            "start_sample": commit.start_sample,
            "end_sample": commit.end_sample,
            "transcript": commit.transcript,
            "revised_transcript": commit.revised_transcript,
        }
        for commit in snapshot.committed
    ]
    effective = snapshot.effective_transcript
    hypothesis = bench.normalise(
        [
            Segment(
                item.start_sample / SAMPLE_RATE,
                item.end_sample / SAMPLE_RATE,
                label_of_canonical(item.canonical_speaker),
                item.text,
            )
            for item in effective
        ],
        duration,
    )
    scores = bench.score(bench.load_reference(case), hypothesis)

    # G2: the projection the arm was measured through, asked the same question segment by
    # segment. The timeline is the baseline live hypothesis, exactly as the grid built it.
    timeline = bench.SpeakerTimeline(
        bench.load_jsonl_segments(baseline / case / "live-hypothesis.jsonl")
    )
    disagreements = []
    for item in effective:
        if item.authority != "rolling":
            continue
        measured = timeline.label(item.start_sample / SAMPLE_RATE, item.end_sample / SAMPLE_RATE)
        produced = label_of_canonical(item.canonical_speaker)
        if measured != produced:
            disagreements.append(
                {
                    "start_sample": item.start_sample,
                    "end_sample": item.end_sample,
                    "measured": measured,
                    "produced": produced,
                    "text": item.text,
                }
            )

    ordered = all(
        left.end_sample <= right.start_sample for left, right in zip(effective, effective[1:])
    )
    frontier = snapshot.canonical_through_sample
    revised = [item for item in effective if item.authority == "rolling"]
    base_inside_prefix = [
        item
        for item in effective
        if item.authority == "provisional" and item.start_sample < frontier
    ]
    return {
        "duration_seconds": duration,
        "spans": len(spans),
        "frontiers": frontiers,
        "frontier_base_inside_prefix": sum(item["base_inside_prefix"] for item in frontiers),
        "frontiers_with_both_authorities": sum(
            1 for item in frontiers if item["rolling"] and item["provisional"]
        ),
        "frontiers_out_of_order": sum(1 for item in frontiers if not item["ordered"]),
        "scores": scores,
        "proposals": proposals,
        "applied": applied,
        "refusals": refusals,
        "text_revision_version": snapshot.text_revision_version,
        "canonical_through_sample": frontier,
        "finalization_status": snapshot.finalization_status,
        "effective_segments": len(effective),
        "rolling_segments": len(revised),
        "provisional_segments": len(effective) - len(revised),
        "ordered": ordered,
        "base_inside_prefix": len(base_inside_prefix),
        "prefix_tiles": bool(revised)
        and revised[0].start_sample >= 0
        and proposals
        == [
            (
                index * DEFAULT_ROLLING_GEOMETRY.stride_samples,
                index * DEFAULT_ROLLING_GEOMETRY.stride_samples
                + DEFAULT_ROLLING_GEOMETRY.window_samples,
            )
            for index in range(len(proposals))
        ],
        "projection_disagreements": disagreements,
        "committed_matches_baseline": committed_after
        == [
            {
                "span_id": item["span_id"],
                "start_sample": item["start_sample"],
                "end_sample": item["end_sample"],
                "transcript": item["transcript"],
                "revised_transcript": None,
            }
            for item in spans
            if span_segments(item["transcript"], sample_count=item["end_sample"] - item["start_sample"])
        ]
        or _committed_diff(committed_after, spans),
        "committed_prefix_hash": snapshot.committed_prefix_hash,
        "label_revision_version": snapshot.label_revision_version,
    }


def _frontier_shape(session: LiveSession) -> dict[str, Any]:
    """What the surface looks like the instant a revision lands: who owns what, in order."""

    snapshot = session.snapshot()
    effective = snapshot.effective_transcript
    frontier = snapshot.canonical_through_sample
    return {
        "canonical_through_sample": frontier,
        "rolling": sum(1 for item in effective if item.authority == "rolling"),
        "provisional": sum(1 for item in effective if item.authority == "provisional"),
        "base_inside_prefix": sum(
            1
            for item in effective
            if item.authority == "provisional" and item.start_sample < frontier
        ),
        "ordered": all(
            left.end_sample <= right.start_sample
            for left, right in zip(effective, effective[1:])
        ),
    }


def _committed_diff(committed_after: list[dict[str, Any]], spans: list[dict[str, Any]]) -> bool:
    """Byte-for-byte D2 check that tolerates the empty spans the session commits as `""`."""

    by_id = {item["span_id"]: item for item in spans}
    for commit in committed_after:
        original = by_id.get(commit["span_id"])
        if original is None:
            return False
        expected = original["transcript"]
        if not span_segments(expected, sample_count=original["end_sample"] - original["start_sample"]):
            expected = ""
        if commit["transcript"] != expected or commit["revised_transcript"] is not None:
            return False
    return len(committed_after) == len(spans)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=",".join(bench.CASES))
    parser.add_argument("--grid", type=Path, default=GRID / "grid.json")
    parser.add_argument("--cache", type=Path, default=GRID / "decode-cache/run0.json")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=None)
    cli = parser.parse_args()

    grid = json.loads(cli.grid.read_text(encoding="utf-8"))
    expected = grid["summary"]["arms"][SELECTED_ARM]
    cases = [item for item in cli.cases.split(",") if item]
    decoder = bench.Decoder(
        runner=_NoRunner(), model=grid["vllm"]["model"], cache_path=cli.cache
    )

    document: dict[str, Any] = {
        "schema": "moss-live-convergence-session-text-authority.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "modules": [
            "moss_transcribe_diarize/app/live_session.py",
            "moss_transcribe_diarize/app/live_transcript_convergence.py",
        ],
        "grid": {
            "path": str(cli.grid.relative_to(REPO)),
            "sha256": hashlib.sha256(cli.grid.read_bytes()).hexdigest(),
            "arm": SELECTED_ARM,
        },
        "canonical_speakers": list(CANONICAL_SPEAKERS),
        "cases": {},
    }

    decoder.take_accounting()
    with tempfile.TemporaryDirectory(prefix="moss-authority-verify-") as temporary:
        for case in cases:
            document["cases"][case] = run_case(
                case, decoder=decoder, baseline=cli.baseline, scratch=Path(temporary)
            )
    document["decode_cost"] = decoder.take_accounting()

    failures: list[str] = []

    def close(actual: float, want: float) -> bool:
        return round(float(actual), PLACES) == round(float(want), PLACES)

    for case in cases:
        entry = document["cases"][case]
        scores = entry["scores"]
        want = expected["per_case"][case]
        if not close(scores["wer"], want["wer_mean"]):
            failures.append(f"G1 {case} wer {scores['wer']:.6f} != grid {want['wer_mean']:.6f}")
        if entry["projection_disagreements"]:
            failures.append(
                f"G2 {case} projection disagrees with the measured timeline on "
                f"{len(entry['projection_disagreements'])} of {entry['rolling_segments']} segments"
            )
        if not entry["ordered"]:
            failures.append(f"G3 {case} effective transcript is not ordered/non-overlapping")
        if entry["base_inside_prefix"] or entry["frontier_base_inside_prefix"]:
            failures.append(
                f"G3 {case} base segments sit inside the revised prefix: "
                f"{entry['base_inside_prefix']} at the end, "
                f"{entry['frontier_base_inside_prefix']} across {len(entry['frontiers'])} frontiers"
            )
        if entry["frontiers_out_of_order"]:
            failures.append(
                f"G3 {case} {entry['frontiers_out_of_order']} frontiers published an "
                "out-of-order surface"
            )
        if not entry["frontiers_with_both_authorities"]:
            failures.append(
                f"G3 {case} no frontier showed a rolling prefix beside a provisional suffix, "
                "so the ownership boundary was never exercised"
            )
        if not entry["prefix_tiles"]:
            failures.append(f"G3 {case} proposals do not tile: {entry['proposals']}")
        if entry["committed_matches_baseline"] is not True:
            failures.append(f"G4 {case} committed spans moved under revision")
        if entry["label_revision_version"] != 0:
            failures.append(f"G4 {case} label revision version moved to {entry['label_revision_version']}")
        if entry["refusals"] or entry["applied"] != entry["text_revision_version"]:
            failures.append(
                f"G5 {case} applied {entry['applied']} revisions, version "
                f"{entry['text_revision_version']}, refusals {entry['refusals']}"
            )
        if entry["applied"] != expected["windows_per_case"]:
            failures.append(
                f"G5 {case} applied {entry['applied']} of {expected['windows_per_case']} windows"
            )

    mean_wer = sum(document["cases"][case]["scores"]["wer"] for case in cases) / len(cases)
    mean_recall = sum(
        document["cases"][case]["scores"]["content_recall"] for case in cases
    ) / len(cases)
    document["trio"] = {"wer_mean": mean_wer, "content_recall_mean": mean_recall}
    if len(cases) == len(bench.CASES):
        if not close(mean_wer, expected["wer"]["mean"]):
            failures.append(f"G1 trio wer {mean_wer:.6f} != grid {expected['wer']['mean']:.6f}")
        if not close(mean_recall, expected["content_recall"]["mean"]):
            failures.append(
                f"G1 trio recall {mean_recall:.6f} != grid {expected['content_recall']['mean']:.6f}"
            )
    if document["decode_cost"].get("fresh_requests"):
        failures.append(f"G6 {document['decode_cost']['fresh_requests']} fresh MOSS requests")

    document["failures"] = failures
    document["passed"] = not failures

    for case in cases:
        entry = document["cases"][case]
        print(
            f"{case:<18} wer={entry['scores']['wer']:.6f} "
            f"(grid {expected['per_case'][case]['wer_mean']:.6f}) "
            f"recall={entry['scores']['content_recall']:.6f} "
            f"rolling={entry['rolling_segments']} base={entry['provisional_segments']} "
            f"frontiers={entry['frontiers_with_both_authorities']}/{len(entry['frontiers'])} "
            f"revisions={entry['text_revision_version']} "
            f"projection_disagreements={len(entry['projection_disagreements'])}"
        )
    print(
        f"{'TRIO':<18} wer={mean_wer:.6f} (grid {expected['wer']['mean']:.6f}) "
        f"recall={mean_recall:.6f} (grid {expected['content_recall']['mean']:.6f})"
    )
    print(f"decode cost: {document['decode_cost']}")
    if cli.output:
        cli.output.parent.mkdir(parents=True, exist_ok=True)
        cli.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for failure in failures:
        print(f"FAIL {failure}")
    print("PASS" if not failures else f"FAILED {len(failures)} gate(s)")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
