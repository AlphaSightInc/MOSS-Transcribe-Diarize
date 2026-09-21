"""Deterministic production-seam control for terminal partition capture."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from moss_transcribe_diarize.app.live_identity import (
    BoundedCausalIdentityPreparer,
    LiveIdentityConfig,
    LiveSpeakerEvidence,
)
from moss_transcribe_diarize.app.live_lane_decode import finalize_lanes
from moss_transcribe_diarize.app.live_session import (
    EffectiveTranscriptSegment,
    LiveIdentitySnapshot,
)
from moss_transcribe_diarize.app.live_tape import CompleteMixedTape
from moss_transcribe_diarize.app.live_transcript_convergence import (
    RollingStatus,
    TerminalDecodePlan,
    TerminalTranscriptFinalizer,
)


RATE = 16_000
ADAM = "speaker-0001"


TRANSCRIPTS = {
    "partition": (
        "[0][S01]established[2.5]"
        "[3][S02]brief return[3.27]"
        "[3.3][S02]eligible return[5.8]"
    ),
    "contained_cross_label": (
        "[0][S01]outer evidence[2][0.5][S02]contained brief span[0.77]"
    ),
    "same_label_merge": "[0][S01]first[1][1][S01]second[2]",
}


class SplitTerminalRunner:
    def __init__(self, transcript: str):
        self.transcript = transcript

    def transcribe(self, *_args, **_kwargs):
        return SimpleNamespace(text=self.transcript)


class DeterministicEvidence:
    """The replay controls' actual-score protocol, with no decoder request."""

    min_segment_samples = 8_000

    def revision_reader(self):
        return DeterministicEvidence()

    def score(self, *, span, pcm, segments, base_snapshot):
        del base_snapshot
        if span.sample_count < self.min_segment_samples:
            return ()
        score = 0.909091 if pcm[0] == 1 else 0.017033
        return tuple(
            LiveSpeakerEvidence(segment.speaker, ADAM, score)
            for segment in segments
        )


def proposal_bytes(result) -> bytes:
    return json.dumps(
        [
            {
                "start_sample": segment.start_sample,
                "end_sample": segment.end_sample,
                "canonical_speaker": segment.canonical_speaker,
                "source_lane": segment.source_lane,
                "text": segment.text,
            }
            for segment in result.proposal.segments
        ],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def run(returning_marker: int, transcript: str = TRANSCRIPTS["partition"]):
    with tempfile.TemporaryDirectory(prefix="moss-terminal-label-capture-") as directory:
        tape = CompleteMixedTape(
            epoch=0, capacity_bytes=6 * RATE * 2, storage_root=Path(directory)
        )
        pcm = bytearray(6 * RATE * 2)
        pcm[: round(2.5 * RATE) * 2] = bytes([1]) * round(2.5 * RATE) * 2
        pcm[3 * RATE * 2 : round(3.27 * RATE) * 2] = (
            bytes([returning_marker]) * round(0.27 * RATE) * 2
        )
        pcm[round(3.3 * RATE) * 2 : round(5.8 * RATE) * 2] = (
            bytes([returning_marker]) * round(2.5 * RATE) * 2
        )
        assert tape.append(start_sample=0, pcm=bytes(pcm)).written
        preparer = BoundedCausalIdentityPreparer(
            config=LiveIdentityConfig(16, 0.35, 0.1),
            evidence_provider=DeterministicEvidence(),
        )
        snapshot = SimpleNamespace(
            identity_snapshot=LiveIdentitySnapshot(canonical_speakers=(ADAM,))
        )
        coordinator = SimpleNamespace(
            session_key="terminal-label-capture",
            lane_tapes={"system": tape},
            _lane_speakers={"system": {ADAM}},
            _lane_preparers={"system": preparer},
            session=SimpleNamespace(snapshot=lambda: snapshot),
        )
        return finalize_lanes(
            coordinator,
            TerminalTranscriptFinalizer(
                runner=SplitTerminalRunner(transcript), scratch_dir=Path(directory)
            ),
            plan=TerminalDecodePlan(0, 6 * RATE, 0, RollingStatus.STOPPED, 0, 0),
            tape=tape,
            base_text_revision_version=0,
            base_surface=(
                EffectiveTranscriptSegment(
                    0, round(2.5 * RATE), "established", ADAM, "rolling", "system"
                ),
            ),
            canonical_speakers=(ADAM,),
        )


def product_partitions(result) -> list[dict]:
    return [
        {
            "lane": partition.lane,
            "partition_id": partition.partition_id,
            "terminal_local_label": partition.terminal_local_label,
            "decision": partition.decision,
            "minimum_samples": partition.minimum_samples,
            "member_raw_indexes": list(partition.member_raw_indexes),
            "start": partition.start,
            "end": partition.end,
            "samples": partition.samples,
            "eligible": partition.eligible,
            "score_by_canonical": dict(partition.score_by_canonical),
            "margin": partition.margin,
            "published_identity": partition.published_identity,
            "meeting_owner": partition.meeting_owner,
            "run_owner": partition.run_owner,
            "schema_version": partition.schema_version,
            "spans": [
                {
                    "span_index": span.span_index,
                    "source_start": span.source_start,
                    "source_end": span.source_end,
                    "published_identity": span.published_identity,
                }
                for span in partition.spans
            ],
        }
        for partition in result.terminal_partitions
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--returning-marker", choices=("adam", "keyu"), default="adam")
    parser.add_argument("--shape", choices=tuple(TRANSCRIPTS), default="partition")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = run(
        1 if args.returning_marker == "adam" else 2,
        TRANSCRIPTS[args.shape],
    )
    destination = os.environ.get("MOSS_TERMINAL_LABEL_CAPTURE")
    rows = []
    if destination and Path(destination).is_file():
        rows = [json.loads(line) for line in Path(destination).read_text().splitlines()]
    payload = {
        "question": "does opt-in partition capture preserve the published proposal?",
        "returning_voice": args.returning_marker,
        "decoder_requests": 0,
        "published_proposal_bytes": proposal_bytes(result).decode(),
        "published_identities": [
            segment.canonical_speaker for segment in result.proposal.segments
        ],
        "product_terminal_partitions": product_partitions(result),
        "capture_rows": rows,
    }
    rendered = json.dumps(payload, sort_keys=True, indent=2)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
