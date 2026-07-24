from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import tempfile
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from moss_transcribe_diarize.transcript_parser import TranscriptSegment

from .live_adapters import RunnerBoundedWavInference
from .live_endpoint import EndpointPolicy, EndpointPolicyConfig, SpeechObservation
from .live_identity import BoundedCausalIdentityPreparer, LiveIdentityConfig, LiveSpeakerEvidence
from .live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceProviderConfigFailure,
    LiveServiceRuntime,
    hash_config,
)
from .live_session import AudioFrame, FrozenSpan, LIVE_SAMPLE_RATE, LiveIdentitySnapshot


BUNDLE_SCHEMA_VERSION = 1
REQUIRED_CONFIG_HASH_KEYS = frozenset(
    {
        "endpoint_config_hash",
        "identity_config_hash",
        "decoder_config_hash",
        "bounds_config_hash",
        "component_config_hash",
        "combined_config_hash",
    }
)


class LiveProviderBundleAdmissionError(LiveServiceProviderConfigFailure):
    pass


@dataclass(frozen=True, slots=True)
class LiveProviderBundleAsset:
    name: str
    path: Path
    byte_size: int
    sha256: str
    identity: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, base_dir: Path) -> "LiveProviderBundleAsset":
        return cls(
            name=_required_str(payload, "name"),
            path=_resolve_path(_required_str(payload, "path"), base_dir=base_dir),
            byte_size=_required_int(payload, "byte_size"),
            sha256=_required_sha256(payload, "sha256"),
            identity=_required_str(payload, "identity"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["path"] = str(self.path)
        return payload


@dataclass(frozen=True, slots=True)
class LiveProviderBundlePackage:
    distribution: str
    version: str
    import_name: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "LiveProviderBundlePackage":
        return cls(
            distribution=_required_str(payload, "distribution"),
            version=_required_str(payload, "version"),
            import_name=_required_str(payload, "import_name"),
        )


@dataclass(frozen=True, slots=True)
class LiveProviderBundleRuntime:
    backend: str
    device: str
    intra_op_threads: int
    inter_op_threads: int
    embedding_dimension: int | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "LiveProviderBundleRuntime":
        embedding_dimension = payload.get("embedding_dimension")
        return cls(
            backend=_required_str(payload, "backend"),
            device=_required_str(payload, "device"),
            intra_op_threads=_required_int(payload, "intra_op_threads"),
            inter_op_threads=_required_int(payload, "inter_op_threads"),
            embedding_dimension=None if embedding_dimension is None else _positive_int(embedding_dimension, "embedding_dimension"),
        )


@dataclass(frozen=True, slots=True)
class LiveProviderBundleGolden:
    input: LiveProviderBundleAsset
    expected_output_sha256: str
    expected_output_identity: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, base_dir: Path) -> "LiveProviderBundleGolden":
        raw_input = payload.get("input")
        if not isinstance(raw_input, Mapping):
            raise LiveProviderBundleAdmissionError("golden.input is required.", code="bundle_manifest_incomplete")
        return cls(
            input=LiveProviderBundleAsset.from_mapping(raw_input, base_dir=base_dir),
            expected_output_sha256=_required_sha256(payload, "expected_output_sha256"),
            expected_output_identity=_required_str(payload, "expected_output_identity"),
        )


@dataclass(frozen=True, slots=True)
class LiveProviderBundlePreflight:
    available: bool
    manifest_hash: str
    config_hashes: dict[str, str]
    descriptor: dict[str, Any]
    failures: tuple[str, ...] = ()
    schema_version: int = BUNDLE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "available": self.available,
            "manifest_hash": self.manifest_hash,
            "config_hashes": dict(self.config_hashes),
            "descriptor": dict(self.descriptor),
            "failures": list(self.failures),
        }


@dataclass(frozen=True, slots=True)
class LiveProviderBundleConfig:
    source_revision: str
    provider_name: str
    provider_revision: str
    provider_license: str
    provider_provenance: str
    packages: tuple[LiveProviderBundlePackage, ...]
    assets: tuple[LiveProviderBundleAsset, ...]
    runtime: LiveProviderBundleRuntime
    golden: LiveProviderBundleGolden
    endpoint_config: dict[str, Any]
    identity_config: dict[str, Any]
    decoder_config: dict[str, Any]
    bounds_config: dict[str, Any]
    declared_config_hashes: dict[str, str]
    speech_provider: dict[str, Any]
    manifest_path: Path | None = None
    schema_version: int = BUNDLE_SCHEMA_VERSION

    @classmethod
    def from_manifest(cls, manifest_path: str | Path) -> "LiveProviderBundleConfig":
        path = Path(manifest_path).expanduser()
        base_dir = path.parent
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise LiveProviderBundleAdmissionError(f"manifest is not readable: {path}", code="bundle_manifest_unreadable") from exc
        except json.JSONDecodeError as exc:
            raise LiveProviderBundleAdmissionError("manifest is not valid JSON.", code="bundle_manifest_invalid") from exc
        if not isinstance(payload, Mapping):
            raise LiveProviderBundleAdmissionError("manifest root must be an object.", code="bundle_manifest_invalid")
        config = cls.from_mapping(payload, base_dir=base_dir)
        return cls(
            **{
                **_config_kwargs(config),
                "manifest_path": path,
            }
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, base_dir: str | Path | None = None) -> "LiveProviderBundleConfig":
        base = Path.cwd() if base_dir is None else Path(base_dir)
        if _required_int(payload, "schema_version") != BUNDLE_SCHEMA_VERSION:
            raise LiveProviderBundleAdmissionError("unsupported live provider bundle schema_version.", code="bundle_schema_version")
        raw_packages = _required_sequence(payload, "packages")
        raw_assets = _required_sequence(payload, "assets")
        return cls(
            source_revision=_required_str(payload, "source_revision"),
            provider_name=_required_str(payload, "provider_name"),
            provider_revision=_required_str(payload, "provider_revision"),
            provider_license=_required_str(payload, "provider_license"),
            provider_provenance=_required_str(payload, "provider_provenance"),
            packages=tuple(LiveProviderBundlePackage.from_mapping(_as_mapping(item, "packages[]")) for item in raw_packages),
            assets=tuple(LiveProviderBundleAsset.from_mapping(_as_mapping(item, "assets[]"), base_dir=base) for item in raw_assets),
            runtime=LiveProviderBundleRuntime.from_mapping(_required_mapping(payload, "runtime")),
            golden=LiveProviderBundleGolden.from_mapping(_required_mapping(payload, "golden"), base_dir=base),
            endpoint_config=dict(_required_mapping(payload, "endpoint_config")),
            identity_config=dict(_required_mapping(payload, "identity_config")),
            decoder_config=dict(_required_mapping(payload, "decoder_config")),
            bounds_config=dict(_required_mapping(payload, "bounds_config")),
            declared_config_hashes=_hash_mapping(_required_mapping(payload, "config_hashes")),
            speech_provider=dict(_required_mapping(payload, "speech_provider")),
        )

    def preflight(self) -> LiveProviderBundlePreflight:
        failures = _collect_preflight_failures(self)
        computed = compute_live_provider_bundle_hashes(self)
        descriptor = {
            "source_revision": self.source_revision,
            "provider_name": self.provider_name,
            "provider_revision": self.provider_revision,
            "provider_license": self.provider_license,
            "provider_provenance": self.provider_provenance,
            "runtime": asdict(self.runtime),
            "sample_rate": LIVE_SAMPLE_RATE,
        }
        return LiveProviderBundlePreflight(
            available=not failures,
            manifest_hash=compute_live_provider_manifest_hash(self),
            config_hashes=computed,
            descriptor=descriptor,
            failures=tuple(failures),
        )


def build_live_runtime_factory(
    config: LiveProviderBundleConfig,
    runner: Any,
) -> Callable[[], LiveServiceRuntime]:
    preflight = config.preflight()
    if not preflight.available:
        raise LiveProviderBundleAdmissionError(
            "live provider bundle preflight failed.",
            code="bundle_preflight_failed",
            detail={"failures": preflight.failures},
        )
    if not hasattr(runner, "transcribe"):
        raise LiveProviderBundleAdmissionError("runner has no transcribe method.", code="bundle_runner_invalid")

    bounds = _bounds(config.bounds_config)
    service_hashes = LiveServiceConfigHashes(
        endpoint_config_hash=preflight.config_hashes["endpoint_config_hash"],
        identity_config_hash=preflight.config_hashes["identity_config_hash"],
        decoder_config_hash=preflight.config_hashes["decoder_config_hash"],
        combined_config_hash=preflight.config_hashes["combined_config_hash"],
    )
    descriptor = LiveServiceDescriptor(
        source_revision=config.source_revision,
        provider_name=config.provider_name,
        provider_revision=config.provider_revision,
        provider_manifest_hash=preflight.manifest_hash,
        config_hashes=service_hashes,
        bounds=bounds,
        frame_samples=int(config.bounds_config.get("frame_samples", bounds.max_frame_samples)),
    )

    def factory() -> LiveServiceRuntime:
        return LiveServiceRuntime(
            descriptor=descriptor,
            endpoint_policy_factory=lambda: EndpointPolicy(_endpoint_config(config.endpoint_config)),
            speech_provider_factory=lambda: _speech_provider(config.speech_provider),
            decoder_factory=lambda: RunnerBoundedWavInference(
                runner,
                max_samples=_positive_int(config.decoder_config.get("max_samples"), "decoder_config.max_samples"),
            ),
            identity_preparer_factory=lambda: BoundedCausalIdentityPreparer(config=_identity_config(config.identity_config)),
        )

    return factory


def compute_live_provider_manifest_hash(config: LiveProviderBundleConfig) -> str:
    payload = {
        "schema_version": config.schema_version,
        "source_revision": config.source_revision,
        "provider_name": config.provider_name,
        "provider_revision": config.provider_revision,
        "provider_license": config.provider_license,
        "provider_provenance": config.provider_provenance,
        "packages": [asdict(item) for item in config.packages],
        "assets": [item.to_dict() for item in config.assets],
        "runtime": asdict(config.runtime),
        "golden": {
            "input": config.golden.input.to_dict(),
            "expected_output_sha256": config.golden.expected_output_sha256,
            "expected_output_identity": config.golden.expected_output_identity,
        },
        "endpoint_config": config.endpoint_config,
        "identity_config": config.identity_config,
        "decoder_config": config.decoder_config,
        "bounds_config": config.bounds_config,
        "config_hashes": config.declared_config_hashes,
        "speech_provider": config.speech_provider,
    }
    return hash_config(payload)


def compute_live_provider_bundle_hashes(config: LiveProviderBundleConfig) -> dict[str, str]:
    endpoint_hash = hash_config(config.endpoint_config)
    identity_hash = hash_config(config.identity_config)
    decoder_hash = hash_config(config.decoder_config)
    bounds_hash = hash_config(config.bounds_config)
    component_hash = hash_config(
        {
            "bounds": bounds_hash,
            "decoder": decoder_hash,
            "endpoint": endpoint_hash,
            "identity": identity_hash,
            "runtime": hash_config(asdict(config.runtime)),
            "speech_provider": hash_config(config.speech_provider),
        }
    )
    return {
        "endpoint_config_hash": endpoint_hash,
        "identity_config_hash": identity_hash,
        "decoder_config_hash": decoder_hash,
        "bounds_config_hash": bounds_hash,
        "component_config_hash": component_hash,
        "combined_config_hash": hash_config(
            {
                "decoder": decoder_hash,
                "endpoint": endpoint_hash,
                "identity": identity_hash,
            }
        ),
    }


class _StaticSpeechSignalProvider:
    def __init__(self, *, speech_present: bool, confidence: float | None = None, provider_reason: str | None = None):
        self.speech_present = bool(speech_present)
        self.confidence = confidence
        self.provider_reason = provider_reason

    def observe(
        self,
        *,
        frame: AudioFrame,
        start_sample: int,
        end_sample: int,
    ) -> tuple[SpeechObservation, ...]:
        del frame
        return (
            SpeechObservation(
                start_sample=start_sample,
                end_sample=end_sample,
                speech_present=self.speech_present,
                confidence=self.confidence,
                provider_reason=self.provider_reason,
            ),
        )


class SileroOnnxSpeechProvider:
    """Silero-ONNX speech observation adapter with injected inference."""

    def __init__(
        self,
        *,
        infer: Callable[[bytes, int], float | Mapping[str, Any]],
        threshold: float,
        provider_reason: str = "silero_onnx_observation",
    ):
        if not 0.0 <= threshold <= 1.0:
            raise LiveProviderBundleAdmissionError("silero threshold must be between 0 and 1.")
        self._infer = infer
        self.threshold = float(threshold)
        self.provider_reason = provider_reason

    def observe(
        self,
        *,
        frame: AudioFrame,
        start_sample: int,
        end_sample: int,
    ) -> tuple[SpeechObservation, ...]:
        score = _observation_score(self._infer(frame.pcm, frame.sample_rate), "silero")
        return (
            SpeechObservation(
                start_sample=start_sample,
                end_sample=end_sample,
                speech_present=score >= self.threshold,
                confidence=score,
                provider_reason=self.provider_reason,
            ),
        )


class WebRtcSpeechProvider:
    """WebRTC speech observation adapter with injected binary VAD."""

    def __init__(
        self,
        *,
        vad: Any,
        frame_samples: int,
        sample_rate: int = LIVE_SAMPLE_RATE,
        provider_reason: str = "webrtc_observation",
    ):
        if frame_samples <= 0:
            raise LiveProviderBundleAdmissionError("webrtc frame_samples must be positive.")
        if sample_rate != LIVE_SAMPLE_RATE:
            raise LiveProviderBundleAdmissionError("webrtc sample_rate must be 16000.")
        if not (callable(vad) or callable(getattr(vad, "is_speech", None))):
            raise LiveProviderBundleAdmissionError("webrtc vad must be callable or expose is_speech().")
        self._vad = vad
        self.frame_samples = int(frame_samples)
        self.sample_rate = int(sample_rate)
        self.provider_reason = provider_reason

    def observe(
        self,
        *,
        frame: AudioFrame,
        start_sample: int,
        end_sample: int,
    ) -> tuple[SpeechObservation, ...]:
        if frame.sample_rate != self.sample_rate:
            raise LiveProviderBundleAdmissionError("webrtc frame sample_rate mismatch.")
        observations: list[SpeechObservation] = []
        cursor = start_sample
        byte_cursor = 0
        while cursor < end_sample:
            piece_samples = min(self.frame_samples, end_sample - cursor)
            byte_end = byte_cursor + piece_samples * 2
            piece = frame.pcm[byte_cursor:byte_end]
            voiced = bool(_call_webrtc_vad(self._vad, piece, self.sample_rate))
            observations.append(
                SpeechObservation(
                    start_sample=cursor,
                    end_sample=cursor + piece_samples,
                    speech_present=voiced,
                    confidence=1.0 if voiced else 0.0,
                    provider_reason=self.provider_reason,
                )
            )
            cursor += piece_samples
            byte_cursor = byte_end
        return tuple(observations)


class WeSpeakerLiveEvidenceProvider:
    """Live evidence adapter over the pinned file-mode WeSpeaker encoder seam."""

    def __init__(
        self,
        *,
        encoder: Any,
        canonical_embedding: Callable[[LiveIdentitySnapshot, str], Sequence[float] | None],
        min_segment_samples: int = 1,
    ):
        if min_segment_samples <= 0:
            raise LiveProviderBundleAdmissionError("wespeaker min_segment_samples must be positive.")
        if not callable(getattr(encoder, "embed", None)):
            raise LiveProviderBundleAdmissionError("wespeaker encoder must expose embed().")
        self.encoder = encoder
        self._canonical_embedding = canonical_embedding
        self.min_segment_samples = int(min_segment_samples)

    def score(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        segments: tuple[TranscriptSegment, ...],
        base_snapshot: LiveIdentitySnapshot,
    ) -> tuple[LiveSpeakerEvidence, ...]:
        if not base_snapshot.canonical_speakers:
            return ()
        intervals_by_speaker = _speaker_intervals_by_label(span, segments, self.min_segment_samples)
        if not intervals_by_speaker:
            return ()
        with tempfile.TemporaryDirectory() as directory:
            wav_path = Path(directory) / "live-evidence.wav"
            _write_pcm_wav(wav_path, pcm)
            local_vectors = {
                speaker: _vector_values(self.encoder.embed(wav_path, intervals))
                for speaker, intervals in intervals_by_speaker.items()
            }
        evidence: list[LiveSpeakerEvidence] = []
        for local_speaker, local_vector in sorted(local_vectors.items()):
            for canonical_speaker in base_snapshot.canonical_speakers:
                canonical_vector = self._canonical_embedding(base_snapshot, canonical_speaker)
                if canonical_vector is None:
                    continue
                score = _cosine_similarity(local_vector, _vector_values(canonical_vector))
                evidence.append(
                    LiveSpeakerEvidence(
                        local_speaker=local_speaker,
                        canonical_speaker=canonical_speaker,
                        score=score,
                        evidence_id=f"wespeaker:{span.id}:{local_speaker}:{canonical_speaker}",
                    )
                )
        return tuple(evidence)


def _speech_provider(payload: Mapping[str, Any]) -> _StaticSpeechSignalProvider:
    kind = _required_str(payload, "kind")
    if kind != "static_observation":
        raise LiveProviderBundleAdmissionError(f"unsupported speech provider kind: {kind}", code="bundle_provider_kind")
    confidence = payload.get("confidence")
    if confidence is not None:
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            raise LiveProviderBundleAdmissionError("speech_provider.confidence must be between 0 and 1.")
    return _StaticSpeechSignalProvider(
        speech_present=bool(payload.get("speech_present", False)),
        confidence=confidence,
        provider_reason=payload.get("provider_reason"),
    )


def _observation_score(value: float | Mapping[str, Any], provider: str) -> float:
    raw = value.get("speech_score") if isinstance(value, Mapping) else value
    try:
        score = float(raw)
    except (TypeError, ValueError) as exc:
        raise LiveProviderBundleAdmissionError(f"{provider} speech score must be numeric.") from exc
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise LiveProviderBundleAdmissionError(f"{provider} speech score must be finite and between 0 and 1.")
    return score


def _call_webrtc_vad(vad: Any, pcm: bytes, sample_rate: int) -> bool:
    if callable(vad):
        return bool(vad(pcm, sample_rate))
    return bool(vad.is_speech(pcm, sample_rate))


def _speaker_intervals_by_label(
    span: FrozenSpan,
    segments: tuple[TranscriptSegment, ...],
    min_segment_samples: int,
) -> dict[str, list[tuple[float, float]]]:
    duration = span.sample_count / float(LIVE_SAMPLE_RATE)
    intervals: dict[str, list[tuple[float, float]]] = {}
    for segment in segments:
        start = max(0.0, float(segment.start))
        end = min(duration, float(segment.end))
        if end <= start:
            continue
        if int(round((end - start) * LIVE_SAMPLE_RATE)) < min_segment_samples:
            continue
        intervals.setdefault(segment.speaker, []).append((start, end))
    return intervals


def _write_pcm_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(LIVE_SAMPLE_RATE)
        wav.writeframes(pcm)


def _vector_values(vector: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(item) for item in vector)
    if not values or any(not math.isfinite(item) for item in values):
        raise LiveProviderBundleAdmissionError("wespeaker evidence vector must be finite and non-empty.")
    return values


def _cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise LiveProviderBundleAdmissionError("wespeaker evidence vector dimensions must match.")
    left_norm = math.sqrt(sum(item * item for item in left))
    right_norm = math.sqrt(sum(item * item for item in right))
    if left_norm <= 0.0 or right_norm <= 0.0:
        raise LiveProviderBundleAdmissionError("wespeaker evidence vectors must be non-zero.")
    score = sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
    return max(0.0, min(1.0, score))


def _collect_preflight_failures(config: LiveProviderBundleConfig) -> list[str]:
    failures: list[str] = []
    if config.runtime.device != "cpu":
        failures.append("runtime.device must be cpu")
    for name in ("intra_op_threads", "inter_op_threads"):
        if getattr(config.runtime, name) <= 0:
            failures.append(f"runtime.{name} must be positive")
    failures.extend(_package_failures(config.packages))
    failures.extend(_asset_failures(config.assets + (config.golden.input,)))
    failures.extend(_golden_failures(config.golden))
    computed = compute_live_provider_bundle_hashes(config)
    missing_hashes = REQUIRED_CONFIG_HASH_KEYS.difference(config.declared_config_hashes)
    for key in sorted(missing_hashes):
        failures.append(f"config_hashes.{key} is required")
    for key in sorted(REQUIRED_CONFIG_HASH_KEYS.intersection(config.declared_config_hashes)):
        if config.declared_config_hashes[key] != computed[key]:
            failures.append(f"config_hashes.{key} mismatch")
    try:
        _endpoint_config(config.endpoint_config)
        _identity_config(config.identity_config)
        _bounds(config.bounds_config)
        _positive_int(config.decoder_config.get("max_samples"), "decoder_config.max_samples")
        _speech_provider(config.speech_provider)
    except Exception as exc:
        failures.append(str(exc))
    return failures


def _package_failures(packages: tuple[LiveProviderBundlePackage, ...]) -> list[str]:
    failures: list[str] = []
    seen: set[str] = set()
    for package in packages:
        if package.distribution in seen:
            failures.append(f"duplicate package distribution: {package.distribution}")
        seen.add(package.distribution)
        try:
            actual = importlib.metadata.version(package.distribution)
        except importlib.metadata.PackageNotFoundError:
            failures.append(f"package is not preinstalled: {package.distribution}")
            actual = None
        if actual is not None and actual != package.version:
            failures.append(f"package version mismatch: {package.distribution}")
        if importlib.util.find_spec(package.import_name) is None:
            failures.append(f"package import is not available: {package.import_name}")
    return failures


def _asset_failures(assets: tuple[LiveProviderBundleAsset, ...]) -> list[str]:
    failures: list[str] = []
    seen: set[str] = set()
    for asset in assets:
        if asset.name in seen:
            failures.append(f"duplicate asset: {asset.name}")
        seen.add(asset.name)
        if not asset.path.is_file():
            failures.append(f"asset is not preinstalled: {asset.name}")
            continue
        actual_size = asset.path.stat().st_size
        if actual_size != asset.byte_size:
            failures.append(f"asset byte_size mismatch: {asset.name}")
        actual_hash = _sha256(asset.path)
        if actual_hash != asset.sha256:
            failures.append(f"asset sha256 mismatch: {asset.name}")
    return failures


def _golden_failures(golden: LiveProviderBundleGolden) -> list[str]:
    payload = f"{golden.input.sha256}:{golden.expected_output_identity}".encode("utf-8")
    actual = hashlib.sha256(payload).hexdigest()
    if actual != golden.expected_output_sha256:
        return ["golden expected_output_sha256 mismatch"]
    return []


def _endpoint_config(payload: Mapping[str, Any]) -> EndpointPolicyConfig:
    return EndpointPolicyConfig(
        min_speech_samples=_non_negative_int(payload.get("min_speech_samples"), "endpoint_config.min_speech_samples"),
        min_silence_samples=_non_negative_int(payload.get("min_silence_samples"), "endpoint_config.min_silence_samples"),
        pre_speech_padding_samples=_non_negative_int(
            payload.get("pre_speech_padding_samples", 0),
            "endpoint_config.pre_speech_padding_samples",
        ),
        post_speech_padding_samples=_non_negative_int(
            payload.get("post_speech_padding_samples", 0),
            "endpoint_config.post_speech_padding_samples",
        ),
        hard_cap_samples=None
        if payload.get("hard_cap_samples") is None
        else _positive_int(payload.get("hard_cap_samples"), "endpoint_config.hard_cap_samples"),
    )


def _identity_config(payload: Mapping[str, Any]) -> LiveIdentityConfig:
    return LiveIdentityConfig(
        max_speakers=_positive_int(payload.get("max_speakers"), "identity_config.max_speakers"),
        min_match_score=float(payload.get("min_match_score", 0.0)),
        min_match_margin=float(payload.get("min_match_margin", 0.0)),
    )


def _bounds(payload: Mapping[str, Any]) -> LiveServiceBounds:
    return LiveServiceBounds(
        max_frame_samples=_positive_int(payload.get("max_frame_samples"), "bounds_config.max_frame_samples"),
        max_queue_depth=_positive_int(payload.get("max_queue_depth"), "bounds_config.max_queue_depth"),
        max_retained_samples=_positive_int(payload.get("max_retained_samples"), "bounds_config.max_retained_samples"),
        max_identity_speakers=_positive_int(payload.get("max_identity_speakers"), "bounds_config.max_identity_speakers"),
        max_events=_positive_int(payload.get("max_events"), "bounds_config.max_events"),
        hard_cap_samples=None
        if payload.get("hard_cap_samples") is None
        else _positive_int(payload.get("hard_cap_samples"), "bounds_config.hard_cap_samples"),
        stop_drain_deadline_seconds=None
        if payload.get("stop_drain_deadline_seconds") is None
        else float(payload["stop_drain_deadline_seconds"]),
    )


def _config_kwargs(config: LiveProviderBundleConfig) -> dict[str, Any]:
    return {
        "source_revision": config.source_revision,
        "provider_name": config.provider_name,
        "provider_revision": config.provider_revision,
        "provider_license": config.provider_license,
        "provider_provenance": config.provider_provenance,
        "packages": config.packages,
        "assets": config.assets,
        "runtime": config.runtime,
        "golden": config.golden,
        "endpoint_config": config.endpoint_config,
        "identity_config": config.identity_config,
        "decoder_config": config.decoder_config,
        "bounds_config": config.bounds_config,
        "declared_config_hashes": config.declared_config_hashes,
        "speech_provider": config.speech_provider,
        "schema_version": config.schema_version,
    }


def _hash_mapping(payload: Mapping[str, Any]) -> dict[str, str]:
    return {str(key): _sha256_value(str(value), f"config_hashes.{key}") for key, value in payload.items()}


def _required_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise LiveProviderBundleAdmissionError(f"{key} is required.", code="bundle_manifest_incomplete")
    return value


def _required_sequence(payload: Mapping[str, Any], key: str) -> tuple[Any, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise LiveProviderBundleAdmissionError(f"{key} is required.", code="bundle_manifest_incomplete")
    return tuple(value)


def _as_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LiveProviderBundleAdmissionError(f"{name} must be an object.", code="bundle_manifest_invalid")
    return value


def _required_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LiveProviderBundleAdmissionError(f"{key} is required.", code="bundle_manifest_incomplete")
    return value


def _required_int(payload: Mapping[str, Any], key: str) -> int:
    return _positive_int(payload.get(key), key)


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise LiveProviderBundleAdmissionError(f"{name} must be a positive integer.")
    return value


def _non_negative_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise LiveProviderBundleAdmissionError(f"{name} must be a non-negative integer.")
    return value


def _required_sha256(payload: Mapping[str, Any], key: str) -> str:
    return _sha256_value(_required_str(payload, key).lower(), key)


def _sha256_value(value: str, name: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise LiveProviderBundleAdmissionError(f"{name} must be a lowercase sha256 hex digest.")
    return value


def _resolve_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base_dir / path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: str | Path) -> LiveProviderBundleConfig:
    return LiveProviderBundleConfig.from_manifest(path)


def _preflight_payload(path: str | Path) -> dict[str, Any]:
    config = _load_manifest(path)
    return config.preflight().to_dict()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only preflight for a default-off live provider bundle.")
    parser.add_argument("--manifest", required=True, help="Path to the offline live provider bundle manifest JSON.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)
    payload = _preflight_payload(args.manifest)
    if args.json:
        print(json.dumps(payload, sort_keys=True, indent=2))
    else:
        status = "available" if payload["available"] else "unavailable"
        print(f"live provider bundle: {status}")
        for failure in payload["failures"]:
            print(f"- {failure}")
    return 0 if payload["available"] else 2


__all__ = [
    "LiveProviderBundleAdmissionError",
    "LiveProviderBundleAsset",
    "LiveProviderBundleConfig",
    "LiveProviderBundleGolden",
    "LiveProviderBundlePackage",
    "LiveProviderBundlePreflight",
    "LiveProviderBundleRuntime",
    "SileroOnnxSpeechProvider",
    "WebRtcSpeechProvider",
    "WeSpeakerLiveEvidenceProvider",
    "build_live_runtime_factory",
    "compute_live_provider_bundle_hashes",
    "compute_live_provider_manifest_hash",
    "main",
]
