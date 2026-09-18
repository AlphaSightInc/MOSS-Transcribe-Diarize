#!/usr/bin/env python
"""PROTOTYPE -- THROWAWAY. WP10: where can an all-zero span be excluded from decoding?

Delete me once the verdict in NOTES.md is folded into the real code and its tests.

This is the *requirements* half of the harness. `run_candidates.sh` is the contracts half: it
runs the nineteen regressed seam tests plus WP3's guard tests against each candidate. Neither
half alone decides anything -- a candidate that keeps every contract but lets a model be asked
about digital zeros has not answered the question, and a candidate that never asks but voids
the seams has answered a different one.

Run:  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python prototypes/zero-guard-seams/falsify.py

Every check drives the REAL live runtime (real coordinator, real session, real tape, real
identity preparer seam) with a runner that raises if it is ever asked to decode, and prints
the full state it observed after each step. Whatever a candidate does, it does it here.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig
from moss_transcribe_diarize.app.live_provider_bundle import bounded_live_inference
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceRuntime,
    _ManualCanonicalPumpScheduler,
)
from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    FrozenSpan,
    LIVE_SAMPLE_RATE,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
)
from moss_transcribe_diarize.app.live_tape import CompleteMixedTape
from moss_transcribe_diarize.app.live_transcript_convergence import (
    PCM16_BYTES_PER_SAMPLE,
    RollingStatus,
    TerminalDecodePlan,
    TerminalTranscriptFinalizer,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
from tests.test_live_service_runtime import _descriptor, ScriptedSpeechProvider  # noqa: E402


FRAME_SAMPLES = 1000
HARD_CAP_SAMPLES = 4000
RESULTS: list[dict[str, object]] = []


class MustNotDecode:
    """Every candidate's forbidden event, made loud. `transcribe` is the model request."""

    max_samples = HARD_CAP_SAMPLES

    def __init__(self) -> None:
        self.requests: list[str] = []

    def transcribe(self, audio_path, **kwargs):
        self.requests.append(str(audio_path))
        raise AssertionError("a model request was made for digital silence")


class DecodingRunner:
    """The control: a runner that answers, so "nothing decoded" can be told from "nothing ran"."""

    def __init__(self, text: str = "[0][S01]words[0.25]") -> None:
        self.text = text
        self.requests: list[str] = []

    def transcribe(self, audio_path, **kwargs):
        self.requests.append(str(audio_path))
        return type("R", (), {"text": self.text, "prompt_len": 10, "generated_tokens": 5})()


class BirthRecordingIdentity:
    """A preparer that records every span it was offered evidence for. Births are calls."""

    def __init__(self) -> None:
        self.prepared: list[int] = []

    def prepare(self, *, span, pcm, transcript, base_snapshot):
        del pcm, transcript
        self.prepared.append(span.id)
        proposed = LiveIdentitySnapshot(
            version=base_snapshot.version + 1,
            canonical_speakers=base_snapshot.canonical_speakers or ("speaker-0001",),
        )
        return LiveIdentityPreparation(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            base_snapshot_version=base_snapshot.version,
            proposed_snapshot=proposed,
            relabeled_transcript=f"[0][S01]stable[{span.sample_count / LIVE_SAMPLE_RATE:g}]",
            status="prepared",
        )


def _frame(sequence: int, *, byte: bytes = b"\0", samples: int = FRAME_SAMPLES) -> AudioFrame:
    return AudioFrame(sequence=sequence, pcm=byte * samples * 2, sample_count=samples)


def _runtime(runner, identity, *, tape_bytes=None, finalizer=None, draft=None, rolling=False):
    descriptor = _descriptor()
    if tape_bytes is not None:
        descriptor = replace(
            descriptor, bounds=replace(descriptor.bounds, max_tape_bytes=tape_bytes)
        )
    scheduler = _ManualCanonicalPumpScheduler()
    runtime = LiveServiceRuntime(
        descriptor=descriptor,
        endpoint_policy_factory=lambda: EndpointPolicy(
            EndpointPolicyConfig(
                min_speech_samples=1, min_silence_samples=1, hard_cap_samples=HARD_CAP_SAMPLES
            )
        ),
        speech_provider_factory=lambda: ScriptedSpeechProvider((True,) * 200),
        decoder_factory=lambda: bounded_live_inference(runner, max_samples=HARD_CAP_SAMPLES),
        rolling_decoder_factory=(
            (lambda: bounded_live_inference(runner, max_samples=HARD_CAP_SAMPLES))
            if rolling
            else None
        ),
        identity_preparer_factory=lambda: identity,
        terminal_finalizer=finalizer,
        draft_lane_seconds=draft,
        draft_decoder_factory=(
            (lambda: bounded_live_inference(runner, max_samples=HARD_CAP_SAMPLES))
            if draft is not None
            else None
        ),
        _canonical_scheduler=scheduler,
    )
    return runtime, scheduler


def check(name: str, requirement: str, *, passed: bool, state: dict[str, object]) -> None:
    RESULTS.append({"check": name, "requirement": requirement, "pass": passed, "state": state})
    mark = "\x1b[32mPASS\x1b[0m" if passed else "\x1b[31mFAIL\x1b[0m"
    print(f"  {mark} \x1b[1m{name}\x1b[0m  \x1b[2m{requirement}\x1b[0m")
    for key, value in state.items():
        print(f"        \x1b[2m{key}\x1b[0m = {value!r}")


# -- R1/R2/R6: the canonical lane ------------------------------------------------------


def canonical_lane() -> None:
    print("\n\x1b[1m[1] canonical lane: four all-zero frames -> one hard-capped span\x1b[0m")
    runner, identity = MustNotDecode(), BirthRecordingIdentity()
    runtime, scheduler = _runtime(runner, identity)
    session_id = runtime.create().session_id
    for sequence in range(4):
        runtime.accept_frame(session_id, _frame(sequence))
    scheduler.run_one()
    snapshot = runtime.snapshot(session_id).session
    events = [event.to_dict() for event in runtime.events(session_id)]
    empty_reasons = [
        event["payload"].get("empty_reason")
        for event in events
        if "empty_reason" in event.get("payload", {})
    ]
    check(
        "R1 no model request for an all-zero canonical span",
        "(a) no model request is made for digital silence",
        passed=not runner.requests,
        state={"model_requests": runner.requests},
    )
    check(
        "R2 no identity birth from an all-zero span",
        "(d) the identity path births no speaker from it",
        passed=not identity.prepared and snapshot.identity_snapshot.version == 0,
        state={
            "identity_prepare_calls": identity.prepared,
            "identity_version": snapshot.identity_snapshot.version,
            "canonical_speakers": snapshot.identity_snapshot.canonical_speakers,
        },
    )
    check(
        "R6 the span is still accounted for, and says why it is empty",
        "(c) accounting/timeline/sequence continue",
        passed=snapshot.committed_samples == HARD_CAP_SAMPLES
        and len(snapshot.committed) == 1
        and snapshot.committed[0].transcript == ""
        and any(reason for reason in empty_reasons),
        state={
            "committed_samples": snapshot.committed_samples,
            "committed_spans": len(snapshot.committed),
            "transcripts": [span.transcript for span in snapshot.committed],
            "empty_reasons": empty_reasons,
        },
    )


# -- R7: WP3's keeper ------------------------------------------------------------------


def one_nonzero_sample() -> None:
    print("\n\x1b[1m[2] one nonzero least-significant bit among the zeros\x1b[0m")
    runner, identity = DecodingRunner(), BirthRecordingIdentity()
    runtime, scheduler = _runtime(runner, identity)
    session_id = runtime.create().session_id
    runtime.accept_frame(session_id, _frame(0, byte=b"\x01"))
    for sequence in range(1, 4):
        runtime.accept_frame(session_id, _frame(sequence))
    scheduler.run_one()
    snapshot = runtime.snapshot(session_id).session
    check(
        "R7 quiet speech still reaches the decoder",
        "WP3's kept contract: one nonzero sample among zeros still decodes",
        passed=len(runner.requests) == 1 and bool(snapshot.committed[0].transcript),
        state={
            "model_requests": len(runner.requests),
            "transcript": snapshot.committed[0].transcript if snapshot.committed else None,
        },
    )


# -- R4: the draft lane ----------------------------------------------------------------


def draft_lane() -> None:
    print("\n\x1b[1m[3] draft lane tick over all-zero audio\x1b[0m")
    import time

    runner, identity = MustNotDecode(), BirthRecordingIdentity()
    runtime, _ = _runtime(runner, identity, draft=FRAME_SAMPLES / LIVE_SAMPLE_RATE)
    session_id = runtime.create().session_id
    runtime.accept_frame(session_id, _frame(0))
    deadline = time.monotonic() + 5
    while runtime._draft_in_flight and time.monotonic() < deadline:
        time.sleep(0.001)
    stats = runtime.snapshot(session_id).draft_stats
    check(
        "R4 no model request for an all-zero draft window",
        "(a) holds for every lane that dispatches a decode, not only the canonical one",
        passed=not runner.requests,
        state={"model_requests": runner.requests, "draft_stats": dict(stats)},
    )


# -- R5/R8: the terminal pass ----------------------------------------------------------


def terminal_pass() -> None:
    print("\n\x1b[1m[4] terminal pass over a whole meeting of zeros, then over one with signal\x1b[0m")
    meeting_samples = HARD_CAP_SAMPLES
    plan = TerminalDecodePlan(
        epoch=0,
        end_sample=meeting_samples,
        rolling_through_sample=meeting_samples,
        rolling_status=RollingStatus.ROLLING,
        windows_completed=1,
        windows_failed=0,
    )
    for label, byte, runner in (
        ("all-zero tape", b"\0", MustNotDecode()),
        ("tape with signal", b"\x07", DecodingRunner("[0][S01]the whole meeting[0.25]")),
    ):
        tape = CompleteMixedTape(
            epoch=0, capacity_bytes=meeting_samples * PCM16_BYTES_PER_SAMPLE * 2
        )
        tape.append(start_sample=0, pcm=byte * meeting_samples * PCM16_BYTES_PER_SAMPLE)
        finalization = TerminalTranscriptFinalizer(runner=runner).finalize(
            plan=plan, tape=tape, base_text_revision_version=0
        )
        state = {
            "model_requests": len(runner.requests),
            "outcome": finalization.accounting.outcome.value,
            "finalization_status": finalization.accounting.outcome.finalization_status,
            "reason": finalization.accounting.reason,
            "proposal": finalization.proposal is not None,
        }
        if label == "all-zero tape":
            check(
                "R5 no model request for an all-zero terminal tape",
                "(a) the last listener decodes minutes of audio; zeros there are the worst case",
                passed=not runner.requests,
                state=state,
            )
        else:
            check(
                "R8 a meeting with signal still reaches a terminal surface",
                "(b) the terminal contract ('failed' != 'final') survives the guard",
                passed=len(runner.requests) == 1 and finalization.proposal is not None,
                state=state,
            )


def main() -> int:
    print("\x1b[1mPROTOTYPE\x1b[0m \x1b[2m-- WP10 zero-guard placement, requirement half\x1b[0m")
    for stage in (canonical_lane, one_nonzero_sample, draft_lane, terminal_pass):
        try:
            stage()
        except AssertionError as exc:
            check(
                f"{stage.__name__} aborted",
                "a forbidden model request escaped the guard",
                passed=False,
                state={"error": str(exc)},
            )
        except Exception as exc:  # noqa: BLE001 -- a prototype reports, it does not hide
            check(
                f"{stage.__name__} raised",
                "the candidate could not be driven to an answer",
                passed=False,
                state={"error": f"{type(exc).__name__}: {exc}"},
            )
    failed = [row for row in RESULTS if not row["pass"]]
    print("\n\x1b[1mverdict\x1b[0m", f"{len(RESULTS) - len(failed)}/{len(RESULTS)} requirements met")
    out = Path(__file__).with_name("falsify-result.json")
    out.write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")
    print(f"\x1b[2mwrote {out}\x1b[0m")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
