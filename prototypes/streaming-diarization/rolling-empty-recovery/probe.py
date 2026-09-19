"""THROWAWAY: deterministic lifecycle probe for stop-on-empty rolling policy."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace

from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_lane_decode import decode_refinement
from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    CanonicalResult,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    LiveSession,
)
from moss_transcribe_diarize.app.live_tape import CompleteMixedTape
from moss_transcribe_diarize.app.live_transcript_convergence import (
    RollingStatus,
    RollingTranscriptConverger,
    TerminalTranscriptFinalizer,
)
from moss_transcribe_diarize.app.phase2_live import _transcript_document


HERE = Path(__file__).resolve().parent
RATE = 16_000
WINDOW = 10 * RATE
PCM_SAMPLE = b"\x01\x00"  # Nonzero PCM: the digital-silence fast path cannot explain the empty.


class ScriptedRollingDecoder:
    def __init__(self) -> None:
        self.calls: list[dict[str, int]] = []

    def transcribe_pcm(self, *, span, pcm):
        assert any(pcm)
        self.calls.append({"start_sample": span.start_sample, "end_sample": span.end_sample})
        return InferenceTranscript(transcript="", elapsed_sec=0.01)


class ScriptedTerminalRunner:
    window_seconds = 150
    stride_seconds = 120

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, int]] = []

    def transcribe(self, audio_path, **_kwargs):
        import wave

        with wave.open(str(audio_path), "rb") as audio:
            samples = audio.getnframes()
            pcm = audio.readframes(samples)
        assert any(pcm)
        self.calls.append({"samples": samples})
        return SimpleNamespace(
            text=self.text,
            generated_tokens=12,
            prompt_len=20,
            window_count=1,
            completed_windows=1,
            possibly_truncated=False,
        )


def _session(samples: int, base_text: str) -> LiveSession:
    session = LiveSession(max_retained_samples=samples)
    pcm = PCM_SAMPLE * samples
    session.accept_frame(AudioFrame(sequence=0, pcm=pcm, sample_count=samples))
    span = session.freeze_until(samples, reason="prototype")
    identity = LiveIdentitySnapshot(version=1, canonical_speakers=("speaker-0001",))
    preparation = LiveIdentityPreparation(
        span_id=span.id,
        epoch=span.epoch,
        start_sample=span.start_sample,
        end_sample=span.end_sample,
        base_snapshot_version=0,
        proposed_snapshot=identity,
        relabeled_transcript=base_text,
    )
    submitted = session.submit_prepared_canonical(
        CanonicalResult(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            transcript=base_text,
            identity_preparation=preparation,
            local_speakers=("S101", "S101"),
            source_lanes=("system", "system"),
        )
    )
    assert submitted.submitted
    return session


def _tape(samples: int) -> CompleteMixedTape:
    tape = CompleteMixedTape(epoch=0, capacity_bytes=samples * 2)
    assert tape.append(start_sample=0, pcm=PCM_SAMPLE * samples).written
    return tape


def run_case(
    *,
    name: str,
    seconds: int,
    late_chunks: tuple[int, ...],
    terminal_text: str,
) -> dict[str, object]:
    samples = seconds * RATE
    base_text = (
        f"[0][S01]base opening survives[1]"
        f"[{max(1, seconds - 4)}][S01]base later speech survives[{seconds - 1}]"
    )
    session = _session(samples, base_text)
    tape = _tape(samples)
    rolling = ScriptedRollingDecoder()
    converger = RollingTranscriptConverger(epoch=session.epoch)
    first_pcm = PCM_SAMPLE * WINDOW
    converger.accept_pcm(0, first_pcm)
    request = converger.observe_base(session.snapshot())[0]
    coordinator = SimpleNamespace(
        session=session,
        rolling_decoder=rolling,
        lane_tapes={"system": tape},
        _stopped_refinement_lanes=set(),
        _lane_preparers={},
        _lane_speakers={},
    )
    decoded = decode_refinement(coordinator, request)
    proposal = converger.complete(
        request.id,
        decoded.outcome,
        segments=decoded.lane_segments,
        revision_lanes=decoded.revision_lanes,
    )
    assert proposal is None
    after_empty = {
        "nonzero_pcm": any(first_pcm),
        "lane_failure": decoded.failure,
        "failed_lanes": list(decoded.failed_lanes),
        "stopped_lanes": sorted(coordinator._stopped_refinement_lanes),
        "rolling": asdict(converger.accounting()),
        "rolling_calls": list(rolling.calls),
        "base_words": [segment.text for segment in session.snapshot().effective_transcript],
    }

    cursor = WINDOW
    later_plans = []
    for chunk_seconds in late_chunks:
        chunk_samples = chunk_seconds * RATE
        later_plans.append(len(converger.accept_pcm(cursor, PCM_SAMPLE * chunk_samples)))
        cursor += chunk_samples
        later_plans.append(len(converger.observe_base(session.snapshot())))
    assert cursor == samples

    plan = converger.stop(samples)
    terminal = ScriptedTerminalRunner(terminal_text)
    final = TerminalTranscriptFinalizer(runner=terminal).finalize(
        plan=plan,
        tape=tape,
        base_text_revision_version=session.snapshot().text_revision_version,
        base_surface=session.snapshot().effective_transcript,
        canonical_speakers=session.snapshot().identity_snapshot.canonical_speakers,
    )
    assert final.proposal is not None
    publication = session.apply_text_revision(final.proposal)
    snapshot = session.snapshot()
    document = _transcript_document(
        SimpleNamespace(
            session=snapshot,
            descriptor=SimpleNamespace(sample_rate=RATE),
        )
    )
    saved_words = [segment["text"] for segment in document["segments"]]
    return {
        "case": name,
        "after_empty": after_empty,
        "later_plan_counts": later_plans,
        "rolling_calls_total": len(rolling.calls),
        "stop_plan": {
            "rolling_status": plan.rolling_status.value,
            "windows_completed": plan.windows_completed,
            "windows_failed": plan.windows_failed,
        },
        "terminal_calls": len(terminal.calls),
        "terminal_outcome": final.outcome.value,
        "publication_applied": publication.applied,
        "finalization_status": snapshot.finalization_status,
        "saved_words": saved_words,
        "terminal_words_saved": all(
            phrase in " ".join(saved_words)
            for phrase in ("terminal opening", "terminal later speech")
        ),
    }


def main() -> None:
    cases = [
        run_case(
            name="nonzero_empty_then_later_speech",
            seconds=30,
            late_chunks=(10, 10),
            terminal_text=(
                "[0][S01]terminal opening[2]"
                "[12][S01]terminal later speech[18]"
            ),
        ),
        run_case(
            name="repeated_empty_attempts_are_suppressed",
            seconds=30,
            late_chunks=(10, 10),
            terminal_text=(
                "[0][S01]terminal opening[2]"
                "[20][S01]terminal later speech[28]"
            ),
        ),
        run_case(
            name="stop_immediately_after_empty",
            seconds=10,
            late_chunks=(),
            terminal_text=(
                "[0][S01]terminal opening[2]"
                "[6][S01]terminal later speech[9]"
            ),
        ),
    ]
    assertions = {
        "all_nonzero_empty_windows_stop_rolling": all(
            row["after_empty"]["rolling"]["status"] == RollingStatus.WINDOW_FAILED.value
            for row in cases
        ),
        "later_windows_make_no_more_rolling_calls": all(
            row["rolling_calls_total"] == 1 for row in cases
        ),
        "later_plans_are_suppressed": all(
            all(count == 0 for count in row["later_plan_counts"]) for row in cases
        ),
        "stop_preserves_failure_reason": all(
            row["stop_plan"]["rolling_status"] == RollingStatus.WINDOW_FAILED.value
            for row in cases
        ),
        "terminal_runs_once_and_publishes": all(
            row["terminal_calls"] == 1
            and row["terminal_outcome"] == "finalized"
            and row["publication_applied"]
            and row["finalization_status"] == "final"
            for row in cases
        ),
        "terminal_words_reach_saved_document": all(
            row["terminal_words_saved"] for row in cases
        ),
    }
    result = {
        "scope": "deterministic lifecycle only; no acoustic-quality claim",
        "cases": cases,
        "assertions": assertions,
        "keep_current_policy": all(assertions.values()),
        "retry_design": "defer_without_real_benefit_and_hallucination_evidence",
    }
    (HERE / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if all(assertions.values()) else 1)


if __name__ == "__main__":
    main()
