from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import math
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from moss_transcribe_diarize.transcript_parser import TranscriptSegment

from .live_session import CanonicalResult, FrozenSpan, LIVE_SAMPLE_RATE, PCM16_BYTES_PER_SAMPLE
from .live_span_bounds import span_segments
from .transcription_outcome import EmptyTranscriptionError, TransientTranscriptionError


class LiveProviderError(RuntimeError):
    pass


class LiveProviderAdmissionError(LiveProviderError):
    pass


class LiveProviderTransientError(LiveProviderError):
    """The decoder did not answer for this span, and the same bytes may decode later.

    A `LiveProviderError` subclass so that every caller which already treats a decode
    failure as a failure keeps doing so; the subclass exists so the one caller that can act
    on the difference -- the live coordinator, which owns the span -- can offer the span
    again instead of ending the meeting. What is transient is decided by the exception the
    runner raises, never by its message.
    """


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
class OfflineProviderManifest:
    kind: str
    revision: str
    assets: tuple[OfflineAsset, ...]
    package_name: str | None = None
    package_version: str | None = None
    import_name: str | None = None


@dataclass(frozen=True, slots=True)
class LiveProviderConfig:
    name: str
    assets: tuple[OfflineAsset, ...]
    offline_providers: tuple[OfflineProviderManifest, ...] = ()


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
    elapsed_sec: float | None = None

    def __post_init__(self) -> None:
        if self.elapsed_sec is None:
            return
        object.__setattr__(
            self,
            "elapsed_sec",
            _finite_non_negative_float(self.elapsed_sec, "elapsed_sec"),
        )


OPTIONAL_LIVE_PROVIDER_KINDS = frozenset(
    {
        "silero_vad",
        "webrtc_vad",
        "wespeaker_identity",
    }
)


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
    _verify_offline_provider_manifests(config.offline_providers)
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
            started = time.monotonic()
            try:
                result = self.runner.transcribe(wav_path, **self.transcribe_kwargs)
            except EmptyTranscriptionError:
                # Nothing was said in this span. That is a transcript of "", not a failure:
                # the span is committed empty upstream so the audio stays accounted for.
                return InferenceTranscript(
                    transcript="",
                    generated_tokens=0,
                    elapsed_sec=time.monotonic() - started,
                )
            except LiveProviderError:
                raise
            except (TransientTranscriptionError, ConnectionError, TimeoutError) as exc:
                # The request never got an answer. The bare exception types are here so this
                # holds for any runner, not only the one that types its own transport
                # failures: a reset socket and an expired deadline mean the same thing
                # whoever raises them.
                raise LiveProviderTransientError(
                    f"canonical decode did not answer: {exc.__class__.__name__}: {exc}"
                ) from exc
            except Exception as exc:
                # Nothing leaves this seam unclassified. A decoder that failed is not a span
                # with nothing to say, and must stay distinguishable from one -- and from a
                # decoder that merely blinked.
                raise LiveProviderError(
                    f"canonical decode failed: {exc.__class__.__name__}: {exc}"
                ) from exc
        return InferenceTranscript(
            transcript=str(result.text),
            prompt_len=int(getattr(result, "prompt_len", 0) or 0),
            generated_tokens=int(getattr(result, "generated_tokens", 0) or 0),
            elapsed_sec=_runner_elapsed_sec(result),
        )


def silero_vad_manifest(
    *,
    model_path: str | Path,
    sha256: str,
    revision: str,
    package_name: str | None = None,
    package_version: str | None = None,
    import_name: str | None = None,
) -> OfflineProviderManifest:
    return OfflineProviderManifest(
        kind="silero_vad",
        revision=revision,
        assets=(OfflineAsset("silero_vad_model", model_path, sha256),),
        package_name=package_name,
        package_version=package_version,
        import_name=import_name,
    )


def webrtc_vad_manifest(
    *,
    asset_path: str | Path,
    sha256: str,
    revision: str,
    package_name: str | None = None,
    package_version: str | None = None,
    import_name: str | None = None,
) -> OfflineProviderManifest:
    return OfflineProviderManifest(
        kind="webrtc_vad",
        revision=revision,
        assets=(OfflineAsset("webrtc_vad_asset", asset_path, sha256),),
        package_name=package_name,
        package_version=package_version,
        import_name=import_name,
    )


def wespeaker_identity_manifest(
    *,
    state_path: str | Path,
    sha256: str,
    revision: str,
    package_name: str | None = None,
    package_version: str | None = None,
    import_name: str | None = None,
) -> OfflineProviderManifest:
    return OfflineProviderManifest(
        kind="wespeaker_identity",
        revision=revision,
        assets=(OfflineAsset("wespeaker_state", state_path, sha256),),
        package_name=package_name,
        package_version=package_version,
        import_name=import_name,
    )


def _verify_offline_provider_manifests(manifests: tuple[OfflineProviderManifest, ...]) -> None:
    seen: set[str] = set()
    for manifest in manifests:
        if manifest.kind not in OPTIONAL_LIVE_PROVIDER_KINDS:
            raise LiveProviderAdmissionError(f"unsupported optional provider kind: {manifest.kind}")
        if manifest.kind in seen:
            raise LiveProviderAdmissionError(f"duplicate optional provider manifest: {manifest.kind}")
        seen.add(manifest.kind)
        if not manifest.revision.strip():
            raise LiveProviderAdmissionError(f"{manifest.kind} provider revision is required.")
        if not manifest.assets:
            raise LiveProviderAdmissionError(f"{manifest.kind} provider must declare offline assets.")
        _verify_assets(manifest.assets)
        _verify_pinned_package(manifest)
        _verify_import_name(manifest)


def _verify_pinned_package(manifest: OfflineProviderManifest) -> None:
    if manifest.package_name is None and manifest.package_version is None:
        return
    if not manifest.package_name or not manifest.package_version:
        raise LiveProviderAdmissionError(f"{manifest.kind} provider package must be version-pinned.")
    try:
        actual_version = importlib.metadata.version(manifest.package_name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise LiveProviderAdmissionError(
            f"{manifest.kind} provider package is not preinstalled: {manifest.package_name}"
        ) from exc
    if actual_version != manifest.package_version:
        raise LiveProviderAdmissionError(f"{manifest.kind} provider package version mismatch.")


def _verify_import_name(manifest: OfflineProviderManifest) -> None:
    if manifest.import_name is None:
        return
    if importlib.util.find_spec(manifest.import_name) is None:
        raise LiveProviderAdmissionError(f"{manifest.kind} provider module is not importable: {manifest.import_name}")


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
    # The same clamp as the identity preparer and the session use -- see `live_span_bounds`.
    segments = span_segments(transcript, sample_count=span.sample_count)
    if not segments:
        raise LiveProviderError("canonical inference returned zero parsed segments.")
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


def _runner_elapsed_sec(result) -> float:
    try:
        return _finite_non_negative_float(
            getattr(result, "elapsed_sec", None),
            "runner result elapsed_sec",
        )
    except ValueError as exc:
        raise LiveProviderError(str(exc)) from exc


def _finite_non_negative_float(value, label: str) -> float:
    if value is None:
        raise ValueError(f"{label} must be present.")
    try:
        elapsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be finite and non-negative.") from None
    if not math.isfinite(elapsed) or elapsed < 0.0:
        raise ValueError(f"{label} must be finite and non-negative.")
    return elapsed
