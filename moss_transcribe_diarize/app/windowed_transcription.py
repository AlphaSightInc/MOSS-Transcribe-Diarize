from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from moss_transcribe_diarize.transcript_parser import TranscriptSegment, parse_transcript

from .ffmpeg import detect_ffmpeg, probe_media
from .model_runner import StatusCallback, TranscriptionResult
from .speaker_identity import IdentityResolver


class WindowTranscriptionError(RuntimeError):
    """Raised when any child window cannot produce a complete parent result."""


class RunnerDelegate(Protocol):
    model_path: str

    def transcribe(self, audio_path: str | Path, **kwargs) -> TranscriptionResult:
        ...


@dataclass(frozen=True, slots=True)
class WindowPlan:
    index: int
    start: float
    end: float
    own_start: float
    own_end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class AbsoluteSegment:
    start: float
    end: float
    speaker: str
    text: str


def probe_media_duration(path: str | Path) -> float:
    media = probe_media(path)
    candidates: list[float] = []
    duration = (media.get("format") or {}).get("duration")
    if duration is not None:
        candidates.append(float(duration))
    for stream in media.get("streams") or []:
        stream_duration = stream.get("duration")
        if stream_duration is not None:
            candidates.append(float(stream_duration))
    if not candidates or max(candidates) <= 0:
        raise RuntimeError(f"Could not determine media duration for {Path(path).expanduser()}.")
    return max(candidates)


def extract_window_wav(
    source: str | Path,
    destination: str | Path,
    *,
    start_seconds: float,
    duration_seconds: float,
) -> None:
    tools = detect_ffmpeg()
    if not tools.ffmpeg:
        raise RuntimeError("ffmpeg is not available on PATH.")
    command = [
        tools.ffmpeg,
        "-y",
        "-ss",
        _format_ffmpeg_seconds(start_seconds),
        "-t",
        _format_ffmpeg_seconds(duration_seconds),
        "-i",
        str(Path(source).expanduser()),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        str(Path(destination).expanduser()),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def plan_windows(duration_seconds: float, *, window_seconds: float = 150.0, stride_seconds: float = 120.0) -> list[WindowPlan]:
    if duration_seconds <= 0:
        raise RuntimeError(f"Media duration must be greater than zero, got {duration_seconds}.")
    starts: list[float] = []
    cursor = 0.0
    while cursor < duration_seconds:
        starts.append(cursor)
        cursor += stride_seconds
    raw = [(start, min(start + window_seconds, duration_seconds)) for start in starts]
    windows: list[WindowPlan] = []
    for index, (start, end) in enumerate(raw):
        own_start = 0.0 if index == 0 else (start + raw[index - 1][1]) / 2.0
        own_end = duration_seconds if index == len(raw) - 1 else (end + raw[index + 1][0]) / 2.0
        windows.append(WindowPlan(index=index, start=start, end=end, own_start=own_start, own_end=own_end))
    return windows


class WindowedRunner:
    window_seconds = 150
    stride_seconds = 120

    def __init__(
        self,
        delegate: RunnerDelegate,
        *,
        duration_probe=probe_media_duration,
        window_extractor=extract_window_wav,
        scratch_dir: str | Path | None = None,
    ):
        self.delegate = delegate
        self.duration_probe = duration_probe
        self.window_extractor = window_extractor
        self.scratch_dir = None if scratch_dir is None else Path(scratch_dir)
        self.model_path = delegate.model_path

    @property
    def is_loaded(self) -> bool:
        return bool(getattr(self.delegate, "is_loaded", True))

    def runtime_info(self) -> dict:
        runtime = getattr(self.delegate, "runtime_info", None)
        data = runtime() if callable(runtime) else {"backend": "vllm", "path": self.model_path}
        data["windowing"] = {
            "window_seconds": self.window_seconds,
            "stride_seconds": self.stride_seconds,
        }
        return data

    def transcribe(self, audio_path: str | Path, **kwargs) -> TranscriptionResult:
        source = Path(audio_path)
        duration = float(self.duration_probe(source))
        windows = plan_windows(
            duration,
            window_seconds=float(self.window_seconds),
            stride_seconds=float(self.stride_seconds),
        )
        if len(windows) == 1:
            result = self.delegate.transcribe(source, **kwargs)
            return _with_window_metadata(
                result,
                window_count=1,
                completed_windows=1,
                possibly_truncated=_hit_token_cap(result, kwargs.get("max_new_tokens")),
            )

        return self._transcribe_windows(source, windows, kwargs)

    def _transcribe_windows(
        self,
        source: Path,
        windows: list[WindowPlan],
        kwargs: dict,
    ) -> TranscriptionResult:
        status_callback = kwargs.get("status_callback")
        child_kwargs = dict(kwargs)
        completed = 0
        prompt_tokens = 0
        generated_tokens = 0
        elapsed_sec = 0.0
        possibly_truncated = False
        segments_by_window: list[list[TranscriptSegment]] = []
        window_audio_paths: list[Path] = []
        last_progress = 0.0

        with tempfile.TemporaryDirectory(prefix="mtd-window-", dir=self.scratch_dir) as scratch:
            scratch_path = Path(scratch)
            for window in windows:
                window_audio = scratch_path / f"window-{window.index:04d}.wav"

                def window_status(status: str, progress: float | None, tokens: int | None = None) -> None:
                    nonlocal last_progress
                    if status_callback is None:
                        return
                    parent_progress = _parent_progress(window.index, len(windows), progress)
                    last_progress = max(last_progress, parent_progress)
                    status_callback(status, last_progress, generated_tokens + int(tokens or 0))

                if status_callback is not None:
                    child_kwargs["status_callback"] = window_status
                try:
                    self.window_extractor(
                        source,
                        window_audio,
                        start_seconds=window.start,
                        duration_seconds=window.duration,
                    )
                    result = self.delegate.transcribe(window_audio, **child_kwargs)
                except Exception as exc:
                    raise _window_error(window, f"failed: {exc}") from exc

                segments = parse_transcript(result.text)
                if result.generated_tokens <= 0:
                    raise _window_error(window, "returned zero generated tokens")
                if not result.text.strip():
                    raise _window_error(window, "returned empty transcript text")
                if not segments:
                    raise _window_error(window, "returned zero parsed segments")

                segments_by_window.append(segments)
                window_audio_paths.append(window_audio)
                prompt_tokens += result.prompt_len
                generated_tokens += result.generated_tokens
                elapsed_sec += result.elapsed_sec
                possibly_truncated = possibly_truncated or _hit_token_cap(result, kwargs.get("max_new_tokens"))
                completed += 1
                if status_callback is not None:
                    last_progress = max(last_progress, 0.25 + 0.60 * (completed / len(windows)))
                    status_callback("transcribing", last_progress, generated_tokens)

            identity = IdentityResolver().resolve(
                windows,
                segments_by_window,
                window_audio_paths=window_audio_paths,
            )

        stitched = _stitch_segments(windows, identity.relabeled_results)
        return TranscriptionResult(
            text=_serialize_segments(stitched),
            prompt_len=prompt_tokens,
            generated_tokens=generated_tokens,
            elapsed_sec=elapsed_sec,
            model=self.model_path,
            audio=str(source.expanduser()),
            decoding=str(kwargs.get("decoding") or "greedy"),
            temperature=kwargs.get("temperature") if kwargs.get("decoding") == "sample" else None,
            window_count=len(windows),
            completed_windows=completed,
            possibly_truncated=possibly_truncated,
            identity_summary=identity.summary,
            identity_resolution={
                "schema_version": identity.diagnostics["schema_version"],
                "summary": identity.summary,
                "diagnostics": identity.diagnostics,
            },
        )


def _stitch_segments(windows: list[WindowPlan], local_results: list[list[TranscriptSegment]]) -> list[AbsoluteSegment]:
    output: list[AbsoluteSegment] = []
    for window, segments in zip(windows, local_results, strict=True):
        if not segments:
            raise _window_error(window, "returned zero parsed segments")
        for segment in segments:
            absolute = AbsoluteSegment(
                start=window.start + segment.start,
                end=window.start + segment.end,
                speaker=segment.speaker,
                text=segment.text,
            )
            midpoint = (absolute.start + absolute.end) / 2.0
            upper_owned = midpoint < window.own_end or (
                window.index == len(windows) - 1 and midpoint <= window.own_end
            )
            if midpoint >= window.own_start and upper_owned:
                output.append(absolute)
    output.sort(key=lambda segment: (segment.start, segment.end))
    return output


def _serialize_segments(segments: list[AbsoluteSegment]) -> str:
    return "".join(
        f"[{_format_transcript_seconds(segment.start)}][{segment.speaker}]"
        f"{segment.text}[{_format_transcript_seconds(segment.end)}]"
        for segment in segments
    )


def _with_window_metadata(
    result: TranscriptionResult,
    *,
    window_count: int,
    completed_windows: int,
    possibly_truncated: bool,
) -> TranscriptionResult:
    return replace(
        result,
        window_count=window_count,
        completed_windows=completed_windows,
        possibly_truncated=possibly_truncated,
    )


def _window_error(window: WindowPlan, message: str) -> WindowTranscriptionError:
    return WindowTranscriptionError(
        f"window {window.index} ({_format_transcript_seconds(window.start)}-"
        f"{_format_transcript_seconds(window.end)}s) {message}"
    )


def _hit_token_cap(result: TranscriptionResult, max_new_tokens: object) -> bool:
    try:
        cap = int(max_new_tokens)
    except (TypeError, ValueError):
        return False
    return cap > 0 and result.generated_tokens >= cap


def _parent_progress(window_index: int, window_count: int, child_progress: float | None) -> float:
    if child_progress is None:
        child_fraction = 0.0
    else:
        child_fraction = (max(0.25, min(0.85, child_progress)) - 0.25) / 0.60
    return 0.25 + 0.60 * ((window_index + child_fraction) / window_count)


def _format_ffmpeg_seconds(value: float) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def _format_transcript_seconds(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-6:
        return str(int(rounded))
    return f"{value:.3f}".rstrip("0").rstrip(".")


__all__ = [
    "WindowTranscriptionError",
    "WindowedRunner",
    "WindowPlan",
    "extract_window_wav",
    "plan_windows",
    "probe_media_duration",
]
