#!/usr/bin/env python3
"""Does the SHIPPED rolling converger reproduce the arm the §10.2 grid selected?

Plan §10.5 step 1 implements M2 (`moss_transcribe_diarize/app/live_transcript_convergence.py`).
A module that merely *looks like* the measured arm is worth nothing: this drives the production
class -- its own window planning, its own retention, its own parsing -- over the trio, decoding
through the grid's checked-in cache, and requires it to land on the selected `10/10` column to
every printed digit.

Zero MOSS requests by construction: the decoder is handed a runner that raises, so a cache miss
is a failure rather than a fresh GPU call. Reviewers can run this with no 4070 Ti.

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
      prototypes/streaming-diarization/live-convergence/verify_production_converger.py

Exit 0 iff every gate below passes.

- G1 per-case WER and content recall equal `grid.json`'s `10/10` arm to 6 dp
- G2 trio means equal `.131861` / `.943916` to 6 dp
- G3 the proposals tile `[0, duration)` exactly: no overlap, no gap, no re-owned interval
- G4 six windows planned, six completed, none failed or stale; 1.000x added decode audio
- G5 retained rolling PCM never exceeds the plan §6 M2 bound of `2 x window`
- G6 zero fresh MOSS requests
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "prototypes/live-file-gap-context"))

import proto_context_arms as bench  # noqa: E402
from moss_transcribe_diarize.app.live_adapters import InferenceTranscript  # noqa: E402
from moss_transcribe_diarize.app.live_transcript_convergence import (  # noqa: E402
    DEFAULT_ROLLING_GEOMETRY,
    RollingStatus,
    RollingTranscriptConverger,
)
from moss_transcribe_diarize.evaluation import Segment  # noqa: E402

SAMPLE_RATE = bench.SAMPLE_RATE
GRID = REPO / "evidence/live-convergence-0824/M2-rolling-grid"
DEFAULT_BASELINE = REPO / "prototypes/live-file-gap-baseline-20260824/trio-60s"
SELECTED_ARM = "10/10:char"  # all three stitch policies are one arm at zero overlap (F1)
FRAME_SAMPLES = SAMPLE_RATE // 2  # the session hands the converger audio in frames
PLACES = 6


class CacheMiss(RuntimeError):
    """The replay asked for a decode the grid never recorded. No GPU call is made."""


class _NoRunner:
    def transcribe(self, *args: Any, **kwargs: Any) -> Any:
        raise CacheMiss("the shipped converger asked for a window the grid did not decode.")


class _Session:
    """The half of `LiveSession` the converger talks to, and nothing more (plan §7.3).

    M3 makes the real session satisfy this; until then the surface is scripted so that this
    check measures the converger alone. It accepts every proposal, which is the case the grid
    measured -- a refusal path has its own tests in `tests/test_live_transcript_convergence.py`.
    """

    def __init__(self, epoch: int = 0):
        self.epoch = epoch
        self.committed_samples = 0
        self.canonical_through_sample = 0
        self.text_revision_version = 0
        self.segments: list[Segment] = []

    def apply(self, proposal: Any) -> None:
        if proposal.start_sample != self.canonical_through_sample:
            raise AssertionError(
                f"proposal starts at {proposal.start_sample}, frontier is "
                f"{self.canonical_through_sample}"
            )
        for segment in proposal.segments:
            self.segments.append(
                Segment(
                    segment.start_sample / SAMPLE_RATE,
                    segment.end_sample / SAMPLE_RATE,
                    segment.canonical_speaker or "S00",
                    segment.text,
                )
            )
        self.canonical_through_sample = proposal.end_sample
        self.text_revision_version += 1


def run_case(case: str, *, decoder: Any, baseline: Path, scratch: Path) -> dict[str, Any]:
    audio_path = bench.CORPUS / case / "audio.wav"
    pcm = bench.read_pcm(audio_path)
    audio_sha = hashlib.sha256(audio_path.read_bytes()).hexdigest()
    duration = (len(pcm) // 2) / SAMPLE_RATE

    converger = RollingTranscriptConverger(epoch=0)
    session = _Session()
    intervals: list[tuple[int, int]] = []

    cursor = 0
    total_samples = len(pcm) // 2
    while cursor < total_samples:
        size = min(FRAME_SAMPLES, total_samples - cursor)
        requests = converger.accept_pcm(cursor, pcm[cursor * 2 : (cursor + size) * 2])
        cursor += size
        # The base path commits what it has accepted; a live session lags by a span or two,
        # which only delays a window, never changes which audio it owns.
        session.committed_samples = cursor
        requests = requests + converger.observe_base(session)
        for request in requests:
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
            session.apply(proposal)
            intervals.append((proposal.start_sample, proposal.end_sample))

    # The runtime observes the snapshot again after applying a revision; without it the
    # converger's view of the frontier stops one window short of what the session accepted.
    converger.observe_base(session)
    plan = converger.stop(total_samples)
    accounting = converger.accounting()
    reference = bench.load_reference(case)
    timeline = bench.SpeakerTimeline(
        bench.load_jsonl_segments(baseline / case / "live-hypothesis.jsonl")
    )
    scores = bench.score(
        reference, timeline.relabel(bench.normalise(session.segments, duration))
    )
    return {
        "duration_seconds": duration,
        "scores": scores,
        "intervals": intervals,
        "tiles": intervals == [
            (index * DEFAULT_ROLLING_GEOMETRY.stride_samples,
             index * DEFAULT_ROLLING_GEOMETRY.stride_samples + DEFAULT_ROLLING_GEOMETRY.window_samples)
            for index in range(len(intervals))
        ],
        "rolling_through_sample": plan.rolling_through_sample,
        "rolling_status": plan.rolling_status.value,
        "accounting": {
            "windows_planned": accounting.windows_planned,
            "windows_completed": accounting.windows_completed,
            "windows_failed": accounting.windows_failed,
            "stale_completions": accounting.stale_completions,
            "decoded_audio_seconds": accounting.decoded_audio_samples / SAMPLE_RATE,
            "added_decode_audio_seconds_per_audio_second": (
                accounting.decoded_audio_samples / SAMPLE_RATE / duration
            ),
            "retained_high_water_samples": accounting.retained_high_water_samples,
            "max_retained_samples": accounting.max_retained_samples,
        },
    }


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
        "schema": "moss-live-convergence-production-converger.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "module": "moss_transcribe_diarize/app/live_transcript_convergence.py",
        "geometry": {
            "window_samples": DEFAULT_ROLLING_GEOMETRY.window_samples,
            "stride_samples": DEFAULT_ROLLING_GEOMETRY.stride_samples,
            "max_retained_samples": DEFAULT_ROLLING_GEOMETRY.max_retained_samples,
        },
        "grid": {
            "path": str(cli.grid.relative_to(REPO)),
            "sha256": hashlib.sha256(cli.grid.read_bytes()).hexdigest(),
            "arm": SELECTED_ARM,
        },
        "cases": {},
    }

    decoder.take_accounting()
    with tempfile.TemporaryDirectory(prefix="moss-converger-verify-") as temporary:
        for case in cases:
            document["cases"][case] = run_case(
                case, decoder=decoder, baseline=cli.baseline, scratch=Path(temporary)
            )
    cost = decoder.take_accounting()
    document["decode_cost"] = cost

    failures: list[str] = []

    def close(actual: float, want: float) -> bool:
        return round(float(actual), PLACES) == round(float(want), PLACES)

    for case in cases:
        entry = document["cases"][case]
        scores = entry["scores"]
        want_wer = expected["per_case"][case]["wer_mean"]
        if not close(scores["wer"], want_wer):
            failures.append(f"G1 {case} wer {scores['wer']:.6f} != grid {want_wer:.6f}")
        if not entry["tiles"]:
            failures.append(f"G3 {case} proposals do not tile: {entry['intervals']}")
        account = entry["accounting"]
        if account["windows_planned"] != expected["windows_per_case"]:
            failures.append(
                f"G4 {case} planned {account['windows_planned']} windows, "
                f"grid decoded {expected['windows_per_case']}"
            )
        if (
            account["windows_completed"] != account["windows_planned"]
            or account["windows_failed"]
            or account["stale_completions"]
        ):
            failures.append(f"G4 {case} accounting {account}")
        if not close(account["added_decode_audio_seconds_per_audio_second"],
                     expected["added_decode_audio_seconds_per_audio_second"]):
            failures.append(f"G4 {case} added decode audio {account}")
        if account["retained_high_water_samples"] > account["max_retained_samples"]:
            failures.append(f"G5 {case} retained {account['retained_high_water_samples']}")
        if entry["rolling_status"] != RollingStatus.ROLLING.value:
            failures.append(f"G4 {case} rolling status {entry['rolling_status']}")
        if entry["rolling_through_sample"] != int(entry["duration_seconds"] * SAMPLE_RATE):
            failures.append(f"G3 {case} frontier {entry['rolling_through_sample']}")

    mean_wer = sum(document["cases"][case]["scores"]["wer"] for case in cases) / len(cases)
    mean_recall = sum(
        document["cases"][case]["scores"]["content_recall"] for case in cases
    ) / len(cases)
    document["trio"] = {"wer": mean_wer, "content_recall": mean_recall}
    if not close(mean_wer, expected["wer"]["mean"]):
        failures.append(f"G2 trio wer {mean_wer:.6f} != grid {expected['wer']['mean']:.6f}")
    if not close(mean_recall, expected["content_recall"]["mean"]):
        failures.append(
            f"G2 trio recall {mean_recall:.6f} != grid {expected['content_recall']['mean']:.6f}"
        )
    if cost["fresh_requests"]:
        failures.append(f"G6 {cost['fresh_requests']} fresh MOSS requests")

    for case in cases:
        entry = document["cases"][case]
        scores = entry["scores"]
        print(
            f"{case:18s} wer={scores['wer']:.6f} (grid {expected['per_case'][case]['wer_mean']:.6f}) "
            f"recall={scores['content_recall']:.6f} "
            f"windows={entry['accounting']['windows_planned']} "
            f"added={entry['accounting']['added_decode_audio_seconds_per_audio_second']:.3f}x "
            f"pcm_high_water={entry['accounting']['retained_high_water_samples']}"
            f"/{entry['accounting']['max_retained_samples']} tiles={entry['tiles']}"
        )
    print(
        f"{'TRIO':18s} wer={mean_wer:.6f} (grid {expected['wer']['mean']:.6f}) "
        f"recall={mean_recall:.6f} (grid {expected['content_recall']['mean']:.6f})"
    )
    print(f"decode cost: {cost['requests']} requests, {cost['fresh_requests']} fresh (0 = no GPU)")

    document["failures"] = failures
    document["passed"] = not failures
    if cli.output is not None:
        cli.output.parent.mkdir(parents=True, exist_ok=True)
        cli.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {cli.output}")
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    print("PASS the shipped converger reproduces the grid's selected arm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
