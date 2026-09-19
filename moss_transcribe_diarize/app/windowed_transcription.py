from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import wave
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from moss_transcribe_diarize.transcript_parser import TranscriptSegment, parse_transcript

from .ffmpeg import detect_ffmpeg, probe_media
from .model_runner import StatusCallback, TranscriptionResult
from .speaker_identity import IdentityResolver
from .transcription_outcome import EmptyTranscriptionError, EmptyTranscriptCause


class WindowTranscriptionError(RuntimeError):
    """Content-free condition and window coordinates; never a decoder response."""

    def __init__(self, message: str, *, condition: str = "checkpoint_error",
                 window_index: int | None = None, start_seconds: float | None = None,
                 end_seconds: float | None = None, exception: Exception | None = None):
        super().__init__(message)
        self.condition = condition
        self.window_index = window_index
        self.start_seconds = start_seconds
        self.end_seconds = end_seconds
        self.exception_type = type(exception).__name__ if exception is not None else None
        self.exception_message = _exception_message(exception) if exception is not None else None

    def to_dict(self) -> dict[str, object]:
        result = {"condition": self.condition, "window_index": self.window_index,
                  "start_seconds": self.start_seconds, "end_seconds": self.end_seconds}
        if self.exception_type is not None:
            result.update(exception_type=self.exception_type, exception_message=self.exception_message)
        return result


class RunnerDelegate(Protocol):
    model_path: str

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        prompt: str | None = None,
        max_length: int = 131072,
        max_new_tokens: int = 2048,
        decoding: str = "greedy",
        temperature: float | None = None,
        status_callback: StatusCallback | None = None,
    ) -> TranscriptionResult:
        ...


@dataclass(frozen=True, slots=True)
class WindowPlan:
    index: int
    start: float
    end: float
    own_start: float
    own_end: float
    merged_tail_start: float | None = None

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


# Operational floor for redundant terminal tails, not a hard model input limit.
# The processor emits ~12.5 audio tokens/s: .5 s offers only ~7 tokens. Keep
# sub-second tails in the preceding overlapping witness instead of decoding them
# alone. Never discard their PCM or exceed the existing window bound.
MIN_USEFUL_TAIL_SECONDS = 1.0


def plan_windows(duration_seconds: float, *, window_seconds: float = 150.0, stride_seconds: float = 120.0) -> list[WindowPlan]:
    if duration_seconds <= 0:
        raise RuntimeError(f"Media duration must be greater than zero, got {duration_seconds}.")
    starts: list[float] = []
    cursor = 0.0
    while cursor < duration_seconds:
        starts.append(cursor)
        cursor += stride_seconds
    raw = [(start, min(start + window_seconds, duration_seconds)) for start in starts]
    merged_tail_start = None
    if len(raw) > 1 and raw[-1][1] - raw[-1][0] < MIN_USEFUL_TAIL_SECONDS and raw[-2][1] >= raw[-1][1]:
        merged_tail_start = raw.pop()[0]
    windows: list[WindowPlan] = []
    for index, (start, end) in enumerate(raw):
        own_start = 0.0 if index == 0 else (start + raw[index - 1][1]) / 2.0
        own_end = duration_seconds if index == len(raw) - 1 else (end + raw[index + 1][0]) / 2.0
        windows.append(WindowPlan(index=index, start=start, end=end, own_start=own_start, own_end=own_end,
                                  merged_tail_start=merged_tail_start if index == len(raw) - 1 else None))
    return windows


class WindowedRunner:
    # Dense-speech estimate: 3 words/s * 150 s * 1.5 tokens/word = 675 text
    # tokens, before speaker/timestamp formatting. The deployed 12000-token cap
    # leaves substantial headroom; this estimate is not a measured worst-case bound.
    window_seconds = 150
    stride_seconds = 120

    def __init__(
        self,
        delegate: RunnerDelegate,
        *,
        duration_probe=probe_media_duration,
        window_extractor=extract_window_wav,
        scratch_dir: str | Path | None = None,
        identity_resolver: IdentityResolver | None = None,
    ):
        self.delegate = delegate
        self.duration_probe = duration_probe
        self.window_extractor = window_extractor
        self.scratch_dir = None if scratch_dir is None else Path(scratch_dir)
        self.identity_resolver = identity_resolver or IdentityResolver()
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
        data["speaker_identity"] = self.identity_resolver.contract()
        return data

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        prompt: str | None = None,
        max_length: int | None = None,
        max_new_tokens: int | None = None,
        decoding: str | None = None,
        temperature: float | None = None,
        status_callback: StatusCallback | None = None,
        checkpoint_dir: str | Path | None = None,
        _dispatch_key: str | None = None,
        _dispatch_on_wait: Callable[[], None] | None = None,
        _dispatch_on_start: Callable[[], None] | None = None,
    ) -> TranscriptionResult:
        source = Path(audio_path)
        kwargs: dict[str, Any] = {
            name: value
            for name, value in {
                "prompt": prompt,
                "max_length": max_length,
                "max_new_tokens": max_new_tokens,
                "decoding": decoding,
                "temperature": temperature,
                "status_callback": status_callback,
                "_dispatch_key": _dispatch_key,
                "_dispatch_on_wait": _dispatch_on_wait,
                "_dispatch_on_start": _dispatch_on_start,
            }.items()
            if value is not None
        }
        duration = float(self.duration_probe(source))
        windows = plan_windows(
            duration,
            window_seconds=float(self.window_seconds),
            stride_seconds=float(self.stride_seconds),
        )
        if len(windows) == 1:
            result = self._decode_window(source, windows[0], kwargs)
            result = _with_window_metadata(
                result,
                window_count=1,
                completed_windows=1,
                possibly_truncated=_hit_token_cap(result, kwargs.get("max_new_tokens")),
            )
        else:
            checkpoint = None
            if checkpoint_dir is not None:
                checkpoint = _CheckpointStore(
                    Path(checkpoint_dir),
                    source=source,
                    windows=windows,
                    model_path=str(self.model_path),
                    inference=_checkpoint_inference(kwargs),
                    window_seconds=float(self.window_seconds),
                    stride_seconds=float(self.stride_seconds),
                    identity_contract=self.identity_resolver.contract(),
                )
            result = self._transcribe_windows(source, windows, kwargs, checkpoint)
        merged = [{"condition": "short_tail_window_merged", "window_index": w.index,
                   "start_seconds": w.merged_tail_start, "end_seconds": w.end,
                   "merged_into_start_seconds": w.start, "minimum_tail_seconds": MIN_USEFUL_TAIL_SECONDS}
                  for w in windows if w.merged_tail_start is not None]
        return replace(result, window_diagnostics=[*(result.window_diagnostics or []), *merged]) if merged else result

    def _decode_window(self, audio: Path, window: WindowPlan, kwargs: dict) -> TranscriptionResult:
        started = time.monotonic()
        try:
            result = self.delegate.transcribe(audio, **kwargs)
        except EmptyTranscriptionError as exc:
            if exc.cause == EmptyTranscriptCause.UNPARSEABLE_TEXT or (
                exc.cause in (EmptyTranscriptCause.NO_GENERATED_TOKENS, EmptyTranscriptCause.EMPTY_TEXT) and not exc.text.strip()
            ):
                diagnostic = _speechless_window(audio, window)
                if diagnostic is not None and exc.cause == EmptyTranscriptCause.UNPARSEABLE_TEXT:
                    diagnostic["condition"] = "unparseable_speechless"
                if diagnostic is not None:
                    return TranscriptionResult(
                        text="", prompt_len=0, generated_tokens=exc.generated_tokens,
                        elapsed_sec=time.monotonic() - started, model=self.model_path,
                        audio=str(audio), decoding=str(kwargs.get("decoding") or "greedy"),
                        temperature=kwargs.get("temperature"), window_diagnostics=[diagnostic],
                    )
            raise _window_error(window, exc.cause.value, exc) from exc
        except Exception as exc:
            raise _window_error(window, "decoder_exception", exc) from exc
        if not result.text.strip():
            diagnostic = _speechless_window(audio, window)
            if diagnostic is not None:
                return replace(result, text="", window_diagnostics=[diagnostic])
            raise _window_error(window, "no_generated_tokens" if result.generated_tokens <= 0 else "empty_text")
        if not parse_transcript(result.text):
            diagnostic = _speechless_window(audio, window)
            if diagnostic is not None:
                diagnostic["condition"] = "unparseable_speechless"
                return replace(result, text="", window_diagnostics=[diagnostic])
            raise _window_error(window, "no_generated_tokens" if result.generated_tokens <= 0 else "unparseable_text")
        return result

    def _transcribe_windows(
        self,
        source: Path,
        windows: list[WindowPlan],
        kwargs: dict,
        checkpoint: _CheckpointStore | None,
    ) -> TranscriptionResult:
        status_callback = kwargs.get("status_callback")
        child_kwargs = dict(kwargs)
        prefix_results = checkpoint.load_prefix() if checkpoint is not None else []
        completed = len(prefix_results)
        prompt_tokens = 0
        generated_tokens = 0
        elapsed_sec = 0.0
        possibly_truncated = False
        segments_by_window: list[list[TranscriptSegment]] = []
        window_audio_paths: list[Path | None] = []
        window_diagnostics: list[dict[str, Any]] = []
        last_progress = 0.0
        for result in prefix_results:
            segments = parse_transcript(result.text)
            if result.generated_tokens <= 0 and not _accepted_speechless(result):
                raise _window_error(windows[len(segments_by_window)], "no_generated_tokens")
            if (not result.text.strip() or not segments) and not _accepted_speechless(result):
                raise _window_error(windows[len(segments_by_window)], "unparseable_text")
            segments_by_window.append(segments)
            window_audio_paths.append(None)
            window_diagnostics.extend(result.window_diagnostics or [])
            prompt_tokens += result.prompt_len
            generated_tokens += result.generated_tokens
            elapsed_sec += result.elapsed_sec
            possibly_truncated = possibly_truncated or _hit_token_cap(result, kwargs.get("max_new_tokens"))

        if self.scratch_dir is not None:
            self.scratch_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="mtd-window-", dir=self.scratch_dir) as scratch:
            scratch_path = Path(scratch)
            # A checkpoint retains the decoder answer, not the source evidence consumed by
            # identity resolution. Re-extract the committed prefix into bounded scratch so a
            # resumed run presents the identity module exactly the audio paths an uninterrupted
            # run would. Re-decoding that prefix would waste the durable progress; passing
            # `None` changes speaker attribution after a restart.
            if self.identity_resolver.requires_window_audio:
                for window in windows[:completed]:
                    window_audio = scratch_path / f"window-{window.index:04d}.wav"
                    try:
                        self.window_extractor(
                            source,
                            window_audio,
                            start_seconds=window.start,
                            duration_seconds=window.duration,
                        )
                    except Exception as exc:
                        raise _window_error(window, "extraction_exception", exc) from exc
                    window_audio_paths[window.index] = window_audio
            for window in windows[completed:]:
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
                except Exception as exc:
                    raise _window_error(window, "extraction_exception", exc) from exc
                result = self._decode_window(window_audio, window, child_kwargs)

                segments = parse_transcript(result.text)
                if result.generated_tokens <= 0 and not _accepted_speechless(result):
                    raise _window_error(window, "no_generated_tokens")
                if not result.text.strip() and not _accepted_speechless(result):
                    raise _window_error(window, "empty_text")
                if not segments and not _accepted_speechless(result):
                    raise _window_error(window, "unparseable_text")

                if checkpoint is not None:
                    checkpoint.commit_window(window, result, possibly_truncated=_hit_token_cap(result, kwargs.get("max_new_tokens")))
                segments_by_window.append(segments)
                window_audio_paths.append(window_audio)
                window_diagnostics.extend(result.window_diagnostics or [])
                prompt_tokens += result.prompt_len
                generated_tokens += result.generated_tokens
                elapsed_sec += result.elapsed_sec
                possibly_truncated = possibly_truncated or _hit_token_cap(result, kwargs.get("max_new_tokens"))
                completed += 1
                if status_callback is not None:
                    last_progress = max(last_progress, 0.25 + 0.60 * (completed / len(windows)))
                    status_callback("transcribing", last_progress, generated_tokens)

            identity = self.identity_resolver.resolve(
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
            window_diagnostics=window_diagnostics,
            identity_summary=identity.summary,
            identity_resolution={
                "schema_version": identity.diagnostics["schema_version"],
                "summary": identity.summary,
                "diagnostics": identity.diagnostics,
            },
        )


# Strictly below 0.01%: one voiced 20ms frame in a maximum 150s window
# is enough to refuse empty-output success. Mode 0 minimizes missed speech.
SPEECHLESS_VOICED_FRACTION = 0.0001


def _speechless_window(audio: Path, window: WindowPlan) -> dict[str, Any] | None:
    """Inspect exactly the decoded PCM; unavailable/unsupported VAD never excuses failure."""
    try:
        import webrtcvad  # Existing live/acceptance dependency; optional in bare file installs.
        with wave.open(str(audio), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 16000):
                return None
            pcm = wav.readframes(wav.getnframes())
        samples = len(pcm) // 2
        if not samples:
            return None
        vad = webrtcvad.Vad(0)
        voiced_samples = 0
        for start in range(0, len(pcm), 640):
            frame = pcm[start:start + 640]
            # Only the final incomplete frame is padded; count actual samples only.
            if vad.is_speech(frame.ljust(640, b"\0"), 16000):
                voiced_samples += len(frame) // 2
        fraction = voiced_samples / samples
    except Exception:
        return None
    if fraction >= SPEECHLESS_VOICED_FRACTION:
        return None
    return {"condition": "speechless_window_empty", "window_index": window.index,
            "start_seconds": window.start, "end_seconds": window.end,
            "vad": "webrtc", "vad_mode": 0, "frame_ms": 20,
            "samples": samples, "voiced_samples": voiced_samples,
            "voiced_fraction": fraction, "speechless_threshold": SPEECHLESS_VOICED_FRACTION}


def _accepted_speechless(result: TranscriptionResult) -> bool:
    return not result.text.strip() and any(
        d.get("condition") in ("speechless_window_empty", "unparseable_speechless") for d in (result.window_diagnostics or [])
    )


class _CheckpointError(WindowTranscriptionError):
    pass


class _CheckpointStore:
    schema_version = 1

    def __init__(
        self,
        root: Path,
        *,
        source: Path,
        windows: list[WindowPlan],
        model_path: str,
        inference: dict[str, Any],
        window_seconds: float,
        stride_seconds: float,
        identity_contract: dict[str, Any],
    ):
        self.root = root
        self.windows_dir = root / "windows"
        self.source = source
        self.windows = windows
        self.plan = [_plan_entry(window) for window in windows]
        self.contract = {
            "source_sha256": _sha256_file(source),
            "model": model_path,
            "inference": inference,
            "windowing": {
                "window_seconds": window_seconds,
                "stride_seconds": stride_seconds,
            },
            "plan": self.plan,
            "identity": deepcopy(identity_contract),
        }
        self.fingerprint = _sha256_canonical(self.contract)
        self.manifest = self._load_or_create_manifest()

    def load_prefix(self) -> list[TranscriptionResult]:
        records = self._load_records()
        return [_result_from_raw(record["raw_result"]) for record in records]

    def commit_window(self, window: WindowPlan, result: TranscriptionResult, *, possibly_truncated: bool) -> None:
        key = _window_key(window)
        path = self.windows_dir / f"{key}.json"
        if path.exists():
            raise _CheckpointError(f"checkpoint duplicate committed record for {key}")
        raw_result = result.to_dict()
        record = {
            "schema_version": self.schema_version,
            "key": key,
            "index": window.index,
            "contract_fingerprint": self.fingerprint,
            "plan": _plan_entry(window),
            "raw_result": raw_result,
            "possibly_truncated": possibly_truncated,
        }
        record["checksum"] = _sha256_canonical(record)
        _atomic_write_json(path, record)

    def _load_or_create_manifest(self) -> dict[str, Any]:
        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            if any(self.windows_dir.glob("w*.json")):
                raise _CheckpointError("checkpoint manifest missing with committed records present")
            self.root.mkdir(parents=True, exist_ok=True)
            self.windows_dir.mkdir(parents=True, exist_ok=True)
            manifest = {
                "schema_version": self.schema_version,
                "job_id": self.root.name,
                "source_sha256": self.contract["source_sha256"],
                "model": self.contract["model"],
                "inference": self.contract["inference"],
                "windowing": self.contract["windowing"],
                "plan": self.plan,
                "identity": self.contract["identity"],
                "contract": self.contract,
                "created_at": time.time(),
                "contract_fingerprint": self.fingerprint,
            }
            _atomic_write_json(manifest_path, manifest)
            return manifest

        manifest = _read_json(manifest_path, "checkpoint manifest")
        if manifest.get("schema_version") != self.schema_version:
            raise _CheckpointError("checkpoint manifest schema mismatch")
        if manifest.get("source_sha256") != self.contract["source_sha256"]:
            raise _CheckpointError("checkpoint source SHA mismatch")
        if manifest.get("plan") != self.plan:
            raise _CheckpointError("checkpoint plan mismatch")
        if manifest.get("contract_fingerprint") != self.fingerprint:
            raise _CheckpointError("checkpoint contract fingerprint mismatch")
        if manifest.get("model") != self.contract["model"] or manifest.get("inference") != self.contract["inference"]:
            raise _CheckpointError("checkpoint manifest inference mismatch")
        return manifest

    def _load_records(self) -> list[dict[str, Any]]:
        if not self.windows_dir.exists():
            return []
        by_index: dict[int, dict[str, Any]] = {}
        for path in sorted(self.windows_dir.glob("w*.json")):
            if path.name.endswith(".tmp"):
                continue
            record = _read_json(path, f"checkpoint record {path.name}")
            checksum = record.get("checksum")
            unsigned = dict(record)
            unsigned.pop("checksum", None)
            if checksum != _sha256_canonical(unsigned):
                raise _CheckpointError(f"checkpoint checksum mismatch for {path.name}")
            if record.get("schema_version") != self.schema_version:
                raise _CheckpointError(f"checkpoint record schema mismatch for {path.name}")
            index = record.get("index")
            if not isinstance(index, int) or index < 0 or index >= len(self.windows):
                raise _CheckpointError(f"checkpoint record plan mismatch for {path.name}")
            expected_window = self.windows[index]
            expected_key = _window_key(expected_window)
            if path.name != f"{expected_key}.json" or record.get("key") != expected_key:
                raise _CheckpointError(f"checkpoint record key mismatch for {path.name}")
            if record.get("plan") != _plan_entry(expected_window):
                raise _CheckpointError(f"checkpoint record plan mismatch for {path.name}")
            if record.get("contract_fingerprint") != self.fingerprint:
                raise _CheckpointError(f"checkpoint record fingerprint mismatch for {path.name}")
            if index in by_index:
                raise _CheckpointError(f"checkpoint duplicate committed record for window {index}")
            by_index[index] = record
        indexes = sorted(by_index)
        if indexes != list(range(len(indexes))):
            raise _CheckpointError("checkpoint committed prefix has a gap")
        return [by_index[index] for index in indexes]


def _stitch_segments(windows: list[WindowPlan], local_results: list[list[TranscriptSegment]]) -> list[AbsoluteSegment]:
    output: list[AbsoluteSegment] = []
    for window, segments in zip(windows, local_results, strict=True):
        # Empty lists have already passed the window-level speechless check.
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


def _exception_message(exc: Exception) -> str:
    """Retain structural diagnostics, never arbitrary decoder bodies or transcript text.

    Python attribute errors expose names, so the observed prompt=None failure can be
    retained exactly. Arbitrary messages have no content boundary and are labelled redacted.
    """
    message = str(exc)
    if isinstance(exc, AttributeError) and re.fullmatch(
        r"'[A-Za-z_][A-Za-z_0-9]*' object has no attribute '[A-Za-z_][A-Za-z_0-9]*'", message
    ):
        return message
    if isinstance(exc, EmptyTranscriptionError):
        return exc.cause.value
    if isinstance(exc, subprocess.CalledProcessError):
        return f"subprocess exited with status {exc.returncode}"
    if isinstance(exc, OSError) and exc.errno is not None:
        return f"[Errno {exc.errno}] {os.strerror(exc.errno)}"
    return "[redacted: unstructured exception message]"


def _window_error(window: WindowPlan, condition: str, exception: Exception | None = None) -> WindowTranscriptionError:
    return WindowTranscriptionError(
        f"window {window.index} ({_format_transcript_seconds(window.start)}-"
        f"{_format_transcript_seconds(window.end)}s) {condition}",
        condition=condition, window_index=window.index,
        start_seconds=window.start, end_seconds=window.end, exception=exception,
    )


def _hit_token_cap(result: TranscriptionResult, max_new_tokens: object) -> bool:
    try:
        cap = int(max_new_tokens)
    except (TypeError, ValueError):
        return False
    return cap > 0 and result.generated_tokens >= cap


def _checkpoint_inference(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt": kwargs.get("prompt"),
        "max_length": kwargs.get("max_length"),
        "max_new_tokens": kwargs.get("max_new_tokens"),
        "decoding": kwargs.get("decoding") or "greedy",
        "temperature": kwargs.get("temperature") if kwargs.get("decoding") == "sample" else None,
        "top_p": kwargs.get("top_p"),
        "top_k": kwargs.get("top_k"),
    }


def _plan_entry(window: WindowPlan) -> dict[str, int]:
    return {
        "index": int(window.index),
        "start_us": _seconds_to_us(window.start),
        "end_us": _seconds_to_us(window.end),
        "own_start_us": _seconds_to_us(window.own_start),
        "own_end_us": _seconds_to_us(window.own_end),
    }


def _window_key(window: WindowPlan) -> str:
    entry = _plan_entry(window)
    return f"w{window.index:06d}-{entry['start_us']}-{entry['end_us']}"


def _seconds_to_us(value: float) -> int:
    return int(round(float(value) * 1_000_000))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_canonical(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _CheckpointError(f"{label} malformed JSON") from exc
    if not isinstance(data, dict):
        raise _CheckpointError(f"{label} must be a JSON object")
    return data


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def _result_from_raw(raw: dict[str, Any]) -> TranscriptionResult:
    return TranscriptionResult(
        text=str(raw.get("text") or ""),
        prompt_len=int(raw.get("prompt_len") or 0),
        generated_tokens=int(raw.get("generated_tokens") or 0),
        elapsed_sec=float(raw.get("elapsed_sec") or 0.0),
        model=str(raw.get("model") or ""),
        audio=str(raw.get("audio") or ""),
        decoding=str(raw.get("decoding") or "greedy"),
        temperature=raw.get("temperature"),
        window_diagnostics=raw.get("window_diagnostics"),
        top_p=raw.get("top_p"),
        top_k=raw.get("top_k"),
        window_count=raw.get("window_count"),
        completed_windows=raw.get("completed_windows"),
        possibly_truncated=raw.get("possibly_truncated"),
        identity_summary=raw.get("identity_summary"),
        identity_resolution=raw.get("identity_resolution"),
    )


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
