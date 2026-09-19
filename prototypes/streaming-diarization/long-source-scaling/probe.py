"""Throwaway deterministic P3 probe; no decoder, network, or microphone calls."""

from __future__ import annotations

import asyncio
import json
import tempfile
import tracemalloc
import wave
from dataclasses import replace
from pathlib import Path

from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.live_adapters import AdapterPreflight, InferenceTranscript
from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks
from moss_transcribe_diarize.app.speaker_identity import IdentityResolution
from moss_transcribe_diarize.app.live_service_runtime import (
    _ManualCanonicalPumpScheduler,
    _ManualTerminalScheduler,
)
from moss_transcribe_diarize.app.live_session import AudioFrame, LIVE_SAMPLE_RATE
from moss_transcribe_diarize.app.live_endpoint import SpeechObservation
from moss_transcribe_diarize.app.live_transcript_convergence import TerminalTranscriptFinalizer
from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner, plan_windows
from tests.test_live_rolling_wiring import FRAME_SAMPLES, _decoders, _runtime


HERE = Path(__file__).resolve().parent


def result(index: int) -> TranscriptionResult:
    return TranscriptionResult(
        text=f"[0][S01]window-{index:04d}[1]",
        prompt_len=1,
        generated_tokens=1,
        elapsed_sec=0.001,
        model="deterministic-stub",
        audio=f"window-{index:04d}.wav",
        decoding="greedy",
        temperature=None,
    )


class DeterministicDecoder:
    model_path = "deterministic-stub"

    def __init__(self, *, fail_once_at: int | None = None) -> None:
        self.fail_once_at = fail_once_at
        self.calls: list[int] = []

    def transcribe(self, audio_path: str | Path, **_: object) -> TranscriptionResult:
        index = int(Path(audio_path).stem.rsplit("-", 1)[1])
        self.calls.append(index)
        if self.fail_once_at == index:
            self.fail_once_at = None
            raise RuntimeError("deterministic interruption")
        return result(index)


class TinyExtractor:
    def __init__(self) -> None:
        self.calls: list[tuple[float, float]] = []

    def __call__(
        self,
        _source: str | Path,
        destination: str | Path,
        *,
        start_seconds: float,
        duration_seconds: float,
    ) -> None:
        self.calls.append((start_seconds, duration_seconds))
        Path(destination).write_text(str(start_seconds), encoding="ascii")


class AudioSensitiveIdentity:
    """Makes missing checkpoint-prefix audio observable in the final public result."""

    requires_window_audio = True

    def contract(self) -> dict[str, object]:
        return {"schema_version": 1, "resolver": "audio-sensitive-control"}

    def resolve(self, windows, local_results, *, window_audio_paths) -> IdentityResolution:
        relabeled = []
        missing = []
        for window, segments, audio_path in zip(
            windows, local_results, window_audio_paths, strict=True
        ):
            available = audio_path is not None and Path(audio_path).is_file()
            if not available:
                missing.append(window.index)
            relabeled.append(
                [replace(segment, speaker="S01" if available else "S00") for segment in segments]
            )
        return IdentityResolution(
            relabeled_results=relabeled,
            summary={"missing_audio_windows": missing},
            diagnostics={"schema_version": 1, "missing_audio_windows": missing},
        )


class KwargRecorder:
    model_path = "kwarg-recorder"

    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    def transcribe(self, _path: str | Path, **kwargs: object) -> TranscriptionResult:
        self.kwargs = kwargs
        return result(0)


class NoSpeech:
    """Keep canonical transcript work out of a source-retention measurement."""

    def observe(self, *, frame: AudioFrame, start_sample: int, end_sample: int):
        del frame
        return (
            SpeechObservation(
                start_sample=start_sample,
                end_sample=end_sample,
                speech_present=False,
            ),
        )


class EmptyCanonicalDecoder:
    """Exercise canonical scheduling without growing a synthetic transcript."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def preflight(self) -> AdapterPreflight:
        return AdapterPreflight(True)

    def transcribe_pcm(self, *, span, pcm: bytes) -> InferenceTranscript:
        if len(pcm) != span.sample_count * 2:
            raise AssertionError("canonical PCM did not match its span")
        self.calls.append((span.start_sample, span.end_sample))
        return InferenceTranscript(
            transcript="",
            elapsed_sec=0.0,
            token_cap=1,
            capped=False,
        )


def geometry(duration_seconds: float) -> dict[str, object]:
    tracemalloc.start()
    windows = plan_windows(duration_seconds)
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    ownership = [(window.own_start, window.own_end) for window in windows]
    contiguous = ownership[0][0] == 0 and ownership[-1][1] == duration_seconds and all(
        left[1] == right[0] for left, right in zip(ownership, ownership[1:], strict=False)
    )
    return {
        "duration_seconds": duration_seconds,
        "window_count": len(windows),
        "last_window_end_seconds": windows[-1].end,
        "maximum_window_seconds": max(window.duration for window in windows),
        "ownership_contiguous": contiguous,
        "plan_peak_python_bytes": peak_bytes,
        "normalized_source_bytes": int(duration_seconds * 16_000 * 2),
        "maximum_active_window_pcm_bytes": 150 * 16_000 * 2,
        "all_window_scratch_pcm_bytes": int(sum(window.duration for window in windows) * 16_000 * 2),
    }


def resume_probe(root: Path) -> dict[str, object]:
    root.mkdir(parents=True)
    source = root / "source.wav"
    source.write_bytes(b"source")
    duration = 360.0

    clean_decoder = DeterministicDecoder()
    clean_extractor = TinyExtractor()
    clean = WindowedRunner(
        clean_decoder,
        duration_probe=lambda _: duration,
        window_extractor=clean_extractor,
        identity_resolver=AudioSensitiveIdentity(),
    ).transcribe(source, max_new_tokens=12_000)

    resumed_decoder = DeterministicDecoder(fail_once_at=2)
    resumed_extractor = TinyExtractor()
    runner = WindowedRunner(
        resumed_decoder,
        duration_probe=lambda _: duration,
        window_extractor=resumed_extractor,
        identity_resolver=AudioSensitiveIdentity(),
    )
    checkpoint = root / "checkpoint"
    interrupted = None
    try:
        runner.transcribe(source, max_new_tokens=12_000, checkpoint_dir=checkpoint)
    except Exception as exc:  # Expected falsifier capture.
        interrupted = type(exc).__name__
    resumed = runner.transcribe(source, max_new_tokens=12_000, checkpoint_dir=checkpoint)
    return {
        "interruption": interrupted,
        "clean_decoder_calls": clean_decoder.calls,
        "resume_decoder_calls": resumed_decoder.calls,
        "checkpoint_record_count": len(list((checkpoint / "windows").glob("w*.json"))),
        "clean_text": clean.text,
        "resumed_text": resumed.text,
        "clean_identity": clean.identity_summary,
        "resumed_identity": resumed.identity_summary,
        "semantic_equivalence": clean.text == resumed.text
        and clean.identity_summary == resumed.identity_summary,
        "resume_extractions": resumed_extractor.calls,
    }


def production_checkpoint_probe(root: Path) -> dict[str, object]:
    root.mkdir(parents=True)
    source = root / "input.wav"
    source.write_bytes(b"source")
    recorder = KwargRecorder()
    tasks = FileMeetingTasks(recorder, root / "file-work")
    tasks._transcribe_from_one_mix(source, {"max_new_tokens": 12_000})
    kwargs = recorder.kwargs or {}
    return {
        "forwarded_keys": sorted(kwargs),
        "checkpoint_dir_forwarded": "checkpoint_dir" in kwargs,
    }


def wav_duration(path: str | Path) -> float:
    with wave.open(str(path), "rb") as source:
        return source.getnframes() / source.getframerate()


async def stop_with_manual_drain(runtime, scheduler, session_id: str):
    task = asyncio.create_task(runtime.stop(session_id, 30.0))
    while not task.done():
        scheduler.drain()
        await asyncio.sleep(0)
    return await task


def live_runtime_probe(root: Path, *, seconds: int, capacity_bytes: int, ending: str) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    canonical_scheduler = _ManualCanonicalPumpScheduler()
    base = EmptyCanonicalDecoder()
    rolling = EmptyCanonicalDecoder()
    runtime = _runtime(base=base, rolling=rolling, scheduler=canonical_scheduler)
    runtime.descriptor = replace(
        runtime.descriptor,
        bounds=replace(runtime.descriptor.bounds, max_tape_bytes=capacity_bytes),
    )
    terminal_scheduler = _ManualTerminalScheduler()
    runtime._terminal_scheduler = terminal_scheduler
    window_decoder = DeterministicDecoder()
    window_runner = WindowedRunner(
        window_decoder,
        duration_probe=wav_duration,
        identity_resolver=AudioSensitiveIdentity(),
        scratch_dir=root,
    )
    runtime._terminal_finalizer = TerminalTranscriptFinalizer(
        runner=window_runner,
        scratch_dir=root,
    )
    created = runtime.create()
    session_id = created.session_id
    runtime._sessions[session_id].coordinator.speech_provider = NoSpeech()
    frame_samples = LIVE_SAMPLE_RATE
    pcm = b"\x11\x22" * frame_samples
    frames = seconds * LIVE_SAMPLE_RATE // frame_samples

    tracemalloc.start()
    for sequence in range(frames):
        runtime.accept_frame(
            session_id,
            AudioFrame(sequence=sequence, pcm=pcm, sample_count=frame_samples),
        )
        canonical_scheduler.drain()
    before = runtime._sessions[session_id].coordinator.tape_accounting().to_dict()
    if ending == "stop":
        stopped = asyncio.run(
            stop_with_manual_drain(runtime, canonical_scheduler, session_id)
        ).to_dict()
        terminal_pending = terminal_scheduler.pending
        terminal_scheduler.drain()
        final = runtime.snapshot(session_id).to_dict()
    elif ending == "abort":
        stopped = asyncio.run(runtime.abort(session_id, "duration_probe_abort")).to_dict()
        terminal_pending = terminal_scheduler.pending
        final = runtime.snapshot(session_id).to_dict()
    else:
        raise ValueError(ending)
    _, peak_python_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    released = runtime._sessions[session_id].coordinator.tape_accounting().to_dict()
    return {
        "seconds": seconds,
        "ending": ending,
        "capacity_bytes": capacity_bytes,
        "frames": frames,
        "canonical_stub_calls": len(base.calls),
        "terminal_window_stub_calls": len(window_decoder.calls),
        "before": before,
        "stop_status": stopped["session"]["status"],
        "terminal_pending_after_stop": terminal_pending,
        "finalization_status": final["session"]["finalization_status"],
        "final_status": final["session"]["status"],
        "released": released,
        "peak_python_bytes": peak_python_bytes,
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="moss-p3-") as directory:
        root = Path(directory)
        long_seconds = 12_060
        full_capacity = long_seconds * LIVE_SAMPLE_RATE * 2
        report = {
            "schema_version": 1,
            "decoder_calls": 0,
            "geometry": [geometry(seconds) for seconds in (11_940.0, 12_000.0, 12_060.0, 24_000.0)],
            "resume": resume_probe(root / "resume"),
            "production_file_seam": production_checkpoint_probe(root / "file-seam"),
            "live": {
                "baseline_30m_overflow": live_runtime_probe(
                    root / "live-baseline",
                    seconds=1_801,
                    capacity_bytes=57_600_000,
                    ending="stop",
                ),
                "full_201m_stop": live_runtime_probe(
                    root / "live-stop",
                    seconds=long_seconds,
                    capacity_bytes=full_capacity,
                    ending="stop",
                ),
                "full_201m_abort": live_runtime_probe(
                    root / "live-abort",
                    seconds=long_seconds,
                    capacity_bytes=full_capacity,
                    ending="abort",
                ),
            },
        }
    report["falsifiers"] = {
        "geometry_failed": not all(
            item["last_window_end_seconds"] == item["duration_seconds"]
            and item["maximum_window_seconds"] <= 150
            and item["ownership_contiguous"]
            for item in report["geometry"]
        ),
        "resume_semantics_changed": not report["resume"]["semantic_equivalence"],
        "production_checkpoint_missing": not report["production_file_seam"]["checkpoint_dir_forwarded"],
        "baseline_live_30m_blocks_over_30m": not report["live"]["baseline_30m_overflow"]["before"]["complete"],
        "full_live_stop_incomplete": (
            not report["live"]["full_201m_stop"]["before"]["complete"]
            or report["live"]["full_201m_stop"]["finalization_status"] != "final"
        ),
        "full_live_abort_retained_audio": report["live"]["full_201m_abort"]["released"]["retained_bytes"] != 0,
    }
    output = HERE / "results.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
