from __future__ import annotations

import hashlib
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from moss_transcribe_diarize.transcript_parser import TranscriptSegment, parse_transcript

from .live_session import CanonicalResult, FrozenSpan, LIVE_SAMPLE_RATE, PCM16_BYTES_PER_SAMPLE


class LiveProviderError(RuntimeError):
    pass


class LiveProviderAdmissionError(LiveProviderError):
    pass


@dataclass(frozen=True, slots=True)
class AdapterPreflight:
    available: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class OfflineAsset:
    name: str
    path: str | Path
    sha256: str


@dataclass(frozen=True, slots=True)
class LiveProviderConfig:
    name: str
    assets: tuple[OfflineAsset, ...]


@dataclass(frozen=True, slots=True)
class VadDecision:
    end_sample: int | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class IdentityDecision:
    confirmed: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class InferenceTranscript:
    transcript: str
    prompt_len: int = 0
    generated_tokens: int = 1


class LiveVad(Protocol):
    def preflight(self) -> AdapterPreflight:
        ...

    def observe(self, *, start_sample: int, end_sample: int, pcm: bytes) -> VadDecision:
        ...


class StableLiveIdentity(Protocol):
    def preflight(self) -> AdapterPreflight:
        ...

    def confirm(self, segments: tuple[TranscriptSegment, ...]) -> IdentityDecision:
        ...


class BoundedWavInference(Protocol):
    max_samples: int

    def preflight(self) -> AdapterPreflight:
        ...

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        ...


@dataclass(frozen=True, slots=True)
class LiveProvider:
    config: LiveProviderConfig
    vad: LiveVad
    identity: StableLiveIdentity
    inference: BoundedWavInference

    def observe_vad(self, *, start_sample: int, end_sample: int, pcm: bytes) -> VadDecision:
        _validate_pcm_length(pcm, end_sample - start_sample)
        return self.vad.observe(start_sample=start_sample, end_sample=end_sample, pcm=pcm)

    def decode_canonical(self, span: FrozenSpan, pcm: bytes) -> CanonicalResult:
        _validate_pcm_length(pcm, span.sample_count)
        if span.sample_count > self.inference.max_samples:
            raise LiveProviderError("canonical span exceeds bounded inference capacity.")
        inferred = self.inference.transcribe_pcm(span=span, pcm=pcm)
        segments = _validated_segments(inferred.transcript, span)
        identity = self.identity.confirm(segments)
        return CanonicalResult(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            transcript=inferred.transcript,
            identity_confirmed=identity.confirmed,
        )


def admit_live_provider(
    config: LiveProviderConfig,
    *,
    vad: LiveVad,
    identity: StableLiveIdentity,
    inference: BoundedWavInference,
) -> LiveProvider:
    _verify_assets(config.assets)
    for label, adapter in (("vad", vad), ("identity", identity), ("inference", inference)):
        preflight = adapter.preflight()
        if not preflight.available:
            reason = preflight.reason or "preflight failed"
            raise LiveProviderAdmissionError(f"{label} provider unavailable: {reason}")
    if inference.max_samples <= 0:
        raise LiveProviderAdmissionError("inference provider max_samples must be positive.")
    return LiveProvider(config=config, vad=vad, identity=identity, inference=inference)


class FakeVad:
    def __init__(self, *, freeze_after_samples: int | None = None, available: bool = True):
        self.freeze_after_samples = freeze_after_samples
        self.available = available

    def preflight(self) -> AdapterPreflight:
        return AdapterPreflight(self.available, None if self.available else "fake vad disabled")

    def observe(self, *, start_sample: int, end_sample: int, pcm: bytes) -> VadDecision:
        del start_sample, pcm
        if self.freeze_after_samples is not None and end_sample >= self.freeze_after_samples:
            return VadDecision(end_sample=end_sample, reason="end_silence")
        return VadDecision()


class FakeStableIdentity:
    def __init__(self, *, confirmed: bool = True, available: bool = True, reason: str | None = None):
        self.confirmed = confirmed
        self.available = available
        self.reason = reason

    def preflight(self) -> AdapterPreflight:
        return AdapterPreflight(self.available, None if self.available else self.reason or "identity unavailable")

    def confirm(self, segments: tuple[TranscriptSegment, ...]) -> IdentityDecision:
        del segments
        return IdentityDecision(self.confirmed, None if self.confirmed else self.reason or "ambiguous identity")


class FakeBoundedWavInference:
    def __init__(self, *, transcript: str, max_samples: int = LIVE_SAMPLE_RATE, available: bool = True):
        self.transcript = transcript
        self.max_samples = max_samples
        self.available = available
        self.calls: list[tuple[int, int]] = []

    def preflight(self) -> AdapterPreflight:
        return AdapterPreflight(self.available, None if self.available else "inference unavailable")

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        del pcm
        self.calls.append((span.start_sample, span.end_sample))
        return InferenceTranscript(self.transcript)


class RunnerBoundedWavInference:
    def __init__(self, runner, *, max_samples: int, scratch_dir: str | Path | None = None, **transcribe_kwargs):
        self.runner = runner
        self.max_samples = int(max_samples)
        self.scratch_dir = None if scratch_dir is None else Path(scratch_dir)
        self.transcribe_kwargs = dict(transcribe_kwargs)

    def preflight(self) -> AdapterPreflight:
        if self.max_samples <= 0:
            return AdapterPreflight(False, "non-positive max_samples")
        if not hasattr(self.runner, "transcribe"):
            return AdapterPreflight(False, "runner has no transcribe method")
        return AdapterPreflight(True)

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        _validate_pcm_length(pcm, span.sample_count)
        if span.sample_count > self.max_samples:
            raise LiveProviderError("canonical span exceeds bounded inference capacity.")
        with tempfile.TemporaryDirectory(prefix="mtd-live-", dir=self.scratch_dir) as scratch:
            wav_path = Path(scratch) / f"span-{span.id:04d}.wav"
            _write_pcm16_wav(wav_path, pcm)
            result = self.runner.transcribe(wav_path, **self.transcribe_kwargs)
        return InferenceTranscript(
            transcript=str(result.text),
            prompt_len=int(getattr(result, "prompt_len", 0) or 0),
            generated_tokens=int(getattr(result, "generated_tokens", 0) or 0),
        )


def _verify_assets(assets: tuple[OfflineAsset, ...]) -> None:
    for asset in assets:
        expected = asset.sha256.strip().lower()
        if len(expected) != 64:
            raise LiveProviderAdmissionError(f"asset {asset.name} must declare a sha256 checksum.")
        path = Path(asset.path).expanduser()
        if not path.is_file():
            raise LiveProviderAdmissionError(f"asset {asset.name} is not preinstalled at {path}.")
        actual = _sha256(path)
        if actual != expected:
            raise LiveProviderAdmissionError(f"asset {asset.name} checksum mismatch.")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_segments(transcript: str, span: FrozenSpan) -> tuple[TranscriptSegment, ...]:
    if not transcript.strip():
        raise LiveProviderError("canonical inference returned empty transcript.")
    segments = tuple(parse_transcript(transcript))
    if not segments:
        raise LiveProviderError("canonical inference returned zero parsed segments.")
    duration = span.sample_count / float(LIVE_SAMPLE_RATE)
    for segment in segments:
        if segment.start < 0 or segment.end > duration:
            raise LiveProviderError("canonical inference returned timestamps outside frozen span.")
    return segments


def _validate_pcm_length(pcm: bytes, sample_count: int) -> None:
    if sample_count <= 0:
        raise LiveProviderError("sample_count must be positive.")
    if len(pcm) != sample_count * PCM16_BYTES_PER_SAMPLE:
        raise LiveProviderError("pcm length must match 16-bit mono sample_count.")


def _write_pcm16_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(PCM16_BYTES_PER_SAMPLE)
        wav.setframerate(LIVE_SAMPLE_RATE)
        wav.writeframes(pcm)
