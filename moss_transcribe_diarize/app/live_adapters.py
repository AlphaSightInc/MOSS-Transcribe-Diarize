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
from typing import Any, Mapping, Protocol

from moss_transcribe_diarize.transcript_parser import TranscriptSegment

from .live_session import CanonicalResult, FrozenSpan, LIVE_SAMPLE_RATE, PCM16_BYTES_PER_SAMPLE
from .live_span_bounds import span_segments
from .transcription_outcome import EmptyTranscriptionError, TransientTranscriptionError


class LiveProviderError(RuntimeError):
    """A canonical decode did not produce a usable answer.

    `detail` carries the facts of the refusal in machine-readable form -- the underlying
    exception type, how many spans an outage has now covered -- beside the prose that has
    always carried them. A failure whose only structured field is the exception's class
    name forces whoever reads it to parse an English sentence, which is how a typed
    refusal ends up needing a host-side probe to explain itself.
    """

    def __init__(self, message: str, *, detail: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.detail: Mapping[str, Any] = dict(detail or {})


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


# --------------------------------------------------------------------------------------
# The bound on a runaway canonical decode.
#
# Measured 2026-07-28 on the committed spans of two independent live runs -- the F1 canary
# (42 spans) and the echo-free canary (46 spans) -- tokenised with the deployed decoder's
# own tokenizer through the vLLM `/tokenize` endpoint. Over 76 spans of real speech the
# decoder never emitted more than **54 tokens** for a full 2.5 s span (21.6 tokens per
# audio-second), and never more than **17 tokens** for a span shorter than 0.5 s: the fixed
# cost of the transcript's own syntax -- two timestamps and a speaker tag -- which does not
# shrink with the audio. The same evidence holds the two spans that set the latency tail,
# both degenerate repeat loops for 2.5 s of audio: **2024** and **2019** generated tokens,
# i.e. they ran to `VllmRunner.transcribe`'s 2048-token default, the only bound they had,
# and each held the serial decode queue for ~8.5 s.
#
# So the budget is affine in the span's own duration -- an allowance for the syntax plus a
# rate for the words -- and each term is the observed maximum times an explicit margin.
# Every one of the 76 real spans sits at least 4.8x under the result, and a 2.5 s span may
# now generate 286 tokens instead of 2048.
#
# These are tuning values derived from measurement, not domain-contract values: the
# contractual quantity is `hard_cap_samples` (2.5 s), which is what the budget is derived
# *from*. Lowering the margin needs new measurement, which is what the tracked node
# `test_the_token_cap_covers_the_measured_speech_and_still_bounds_a_runaway` holds in place.
# --------------------------------------------------------------------------------------
OBSERVED_MAX_SPAN_SYNTAX_TOKENS = 17
OBSERVED_MAX_TOKENS_PER_AUDIO_SECOND = 21.6
LIVE_DECODE_TOKEN_MARGIN = 4
LIVE_DECODE_TOKEN_BUDGET_BASE = LIVE_DECODE_TOKEN_MARGIN * OBSERVED_MAX_SPAN_SYNTAX_TOKENS
LIVE_DECODE_TOKENS_PER_AUDIO_SECOND = math.ceil(LIVE_DECODE_TOKEN_MARGIN * OBSERVED_MAX_TOKENS_PER_AUDIO_SECOND)


def canonical_decode_token_cap(*, sample_count: int) -> int:
    """The most tokens the decoder may generate for a span of `sample_count` samples."""

    if sample_count <= 0:
        raise LiveProviderError("sample_count must be positive.")
    duration_sec = sample_count / float(LIVE_SAMPLE_RATE)
    return LIVE_DECODE_TOKEN_BUDGET_BASE + math.ceil(LIVE_DECODE_TOKENS_PER_AUDIO_SECOND * duration_sec)


@dataclass(frozen=True, slots=True)
class InferenceTranscript:
    transcript: str
    prompt_len: int = 0
    generated_tokens: int = 1
    elapsed_sec: float | None = None
    # What the decode was allowed to generate, and whether it used all of it. A capped span
    # publishes what came back -- the words are accepted audio and stay in the transcript --
    # so truncation has to be *stated*, or a shortened span is indistinguishable from a
    # quiet one to everybody downstream.
    token_cap: int | None = None
    capped: bool = False

    def __post_init__(self) -> None:
        # Timing metadata that cannot be trusted is recorded as *unknown*, never raised. See
        # `trustworthy_duration_sec` for the rule and why it is a rule rather than a guard.
        object.__setattr__(self, "elapsed_sec", trustworthy_duration_sec(self.elapsed_sec))


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
        token_cap = self._token_cap(span)
        with tempfile.TemporaryDirectory(prefix="mtd-live-", dir=self.scratch_dir) as scratch:
            wav_path = Path(scratch) / f"span-{span.id:04d}.wav"
            _write_pcm16_wav(wav_path, pcm)
            started = time.monotonic()
            try:
                result = self.runner.transcribe(
                    wav_path,
                    **{**self.transcribe_kwargs, "max_new_tokens": token_cap},
                )
            except EmptyTranscriptionError:
                # Nothing was said in this span. That is a transcript of "", not a failure:
                # the span is committed empty upstream so the audio stays accounted for.
                return InferenceTranscript(
                    transcript="",
                    generated_tokens=0,
                    elapsed_sec=time.monotonic() - started,
                    token_cap=token_cap,
                )
            except LiveProviderError:
                raise
            except (TransientTranscriptionError, ConnectionError, TimeoutError) as exc:
                # The request never got an answer. The bare exception types are here so this
                # holds for any runner, not only the one that types its own transport
                # failures: a reset socket and an expired deadline mean the same thing
                # whoever raises them.
                raise LiveProviderTransientError(
                    f"canonical decode did not answer: {exc.__class__.__name__}: {exc}",
                    detail={"span_id": span.id, "cause": exc.__class__.__name__},
                ) from exc
            except Exception as exc:
                # Nothing leaves this seam unclassified. A decoder that failed is not a span
                # with nothing to say, and must stay distinguishable from one -- and from a
                # decoder that merely blinked.
                raise LiveProviderError(
                    f"canonical decode failed: {exc.__class__.__name__}: {exc}",
                    detail={"span_id": span.id, "cause": exc.__class__.__name__},
                ) from exc
            # This decode's duration is measured here, on the same monotonic clock as the
            # empty-transcript branch above, and the runner's own `elapsed_sec` is not read.
            # A runner reports whatever clock it happens to hold -- `VllmRunner` reported a
            # *wall* clock until this cycle -- and a wall clock is a timestamp, not a
            # duration: NTP resynchronised the deployed host ~1.5 s backwards every ~32.3 s,
            # so any decode bracketing a step produced an elapsed wrong by that much, and a
            # negative one ended the meeting. Only a monotonic difference is a duration.
            elapsed_sec = time.monotonic() - started
        generated_tokens = int(getattr(result, "generated_tokens", 0) or 0)
        return InferenceTranscript(
            transcript=str(result.text),
            prompt_len=int(getattr(result, "prompt_len", 0) or 0),
            generated_tokens=generated_tokens,
            elapsed_sec=elapsed_sec,
            token_cap=token_cap,
            capped=generated_tokens >= token_cap,
        )

    def _token_cap(self, span: FrozenSpan) -> int:
        """The span's own duration decides, and a configured ceiling may only tighten it.

        A live decode that answers too slowly damages the meeting exactly as a decode that
        does not answer does -- the queue is serial, so one runaway span is the whole
        latency tail -- and the deployment that configures the runner is not the place that
        can see that. So the derived bound always applies; an explicit `max_new_tokens`
        stays honoured, but only where it is stricter.
        """

        cap = canonical_decode_token_cap(sample_count=span.sample_count)
        configured = self.transcribe_kwargs.get("max_new_tokens")
        if configured is None:
            return cap
        return min(cap, int(configured))


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


def trustworthy_duration_sec(value) -> float | None:
    """A duration is a finite non-negative number, or it is not known. It is never a failure.

    The rule this states is general and it is about *metadata*, not about this one field: a
    measurement the live path cannot trust degrades to `None` and the meeting continues.
    Only a condition that makes the session genuinely unable to continue may be terminal,
    and a decode whose clock misbehaved still returned a transcript -- the span is fine, the
    words are publishable, and the only thing missing is the number used to compute RTF.

    This is the fifth condition of that shape to have ended a meeting (an unparseable span,
    an abstained identity preparation, a transient decoder failure, a timestamp a hair past
    the span, and now an untrustworthy duration), which is why it is answered here as a
    conversion rather than in each caller as a guard: the next caller inherits the rule.
    """

    if value is None:
        return None
    try:
        elapsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(elapsed) or elapsed < 0.0:
        return None
    return elapsed
