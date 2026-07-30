from __future__ import annotations

import argparse
import hashlib
import importlib
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
from .live_identity_album import (
    ALBUM_ADMISSION_SECONDS,
    ALBUM_BIRTH_MIN_SECONDS,
    ALBUM_EXEMPLARS_PER_SPEAKER,
    FingerprintAlbum,
    cosine_similarity,
)
from .live_identity_sweep import LiveIdentitySweeper, SweepRevision
from .live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceProviderConfigFailure,
    LiveServiceRuntime,
    hash_config,
)
from .live_session import (
    AudioFrame,
    FrozenSpan,
    LIVE_SAMPLE_RATE,
    LiveIdentitySnapshot,
    PCM16_BYTES_PER_SAMPLE,
)
from .speaker_identity import TierBAssetSpec, WeSpeakerResNet152LmAdapter


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
RUNTIME_BACKEND_BY_SPEECH_PROVIDER = {
    "silero_onnx": "onnxruntime-cpu",
    "webrtc": "webrtc-cpu",
}


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
    identity_provider: dict[str, Any]
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
            identity_provider=dict(_optional_mapping(payload, "identity_provider")),
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
            "speech_provider_kind": self.speech_provider.get("kind"),
            "identity_provider_kind": self.identity_provider.get("kind"),
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

    identity_encoder = _identity_encoder(config)

    def factory() -> LiveServiceRuntime:
        return LiveServiceRuntime(
            descriptor=descriptor,
            endpoint_policy_factory=lambda: EndpointPolicy(_endpoint_config(config.endpoint_config)),
            speech_provider_factory=lambda: _speech_provider(config),
            decoder_factory=lambda: RunnerBoundedWavInference(
                runner,
                max_samples=_positive_int(config.decoder_config.get("max_samples"), "decoder_config.max_samples"),
            ),
            identity_preparer_factory=lambda: _identity_preparer(config, encoder=identity_encoder),
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
        "identity_provider": config.identity_provider,
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
            "identity_provider": hash_config(config.identity_provider),
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
    """WebRTC speech observation adapter with injected binary VAD.

    WebRTC's VAD accepts exactly one frame of 10, 20 or 30 ms per call and raises for any
    other length. The accepted-sample stream it observes is not obliged to arrive in whole
    VAD frames: the mixer emits ``floor((safe_end_ns - cursor_ns) * rate / 1e9)`` samples,
    which is an arbitrary integer as soon as the two capture lanes are not aligned on the
    frame grid -- i.e. on essentially every real capture. This adapter therefore tiles the
    *stream*, not each accepted range: the VAD is called only with exactly ``frame_samples``
    of real contiguous audio, and a tail that does not complete a frame is carried into the
    next call. The coordinator still requires gap-free coverage of the accepted range now,
    so a carried tail is reported with the last decided frame's answer (silence before any
    frame has been decided) and no confidence, and the samples themselves are decided for
    real once the frame completes.
    """

    #: Frame lengths webrtcvad accepts, in milliseconds.
    VAD_FRAME_MILLISECONDS = (10, 20, 30)

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
        accepted = tuple(sample_rate * ms // 1000 for ms in self.VAD_FRAME_MILLISECONDS)
        if frame_samples not in accepted:
            raise LiveProviderBundleAdmissionError(
                "webrtc frame_samples must be one of "
                f"{list(accepted)} samples ({list(self.VAD_FRAME_MILLISECONDS)} ms at {sample_rate} Hz)."
            )
        if not (callable(vad) or callable(getattr(vad, "is_speech", None))):
            raise LiveProviderBundleAdmissionError("webrtc vad must be callable or expose is_speech().")
        self._vad = vad
        self.frame_samples = int(frame_samples)
        self.sample_rate = int(sample_rate)
        self.provider_reason = provider_reason
        self._carried_pcm = bytearray()
        self._carried_voiced = False

    def observe(
        self,
        *,
        frame: AudioFrame,
        start_sample: int,
        end_sample: int,
    ) -> tuple[SpeechObservation, ...]:
        if frame.sample_rate != self.sample_rate:
            raise LiveProviderBundleAdmissionError("webrtc frame sample_rate mismatch.")
        if end_sample <= start_sample:
            raise LiveProviderBundleAdmissionError("webrtc accepted range must advance.")
        frame_bytes = self.frame_samples * PCM16_BYTES_PER_SAMPLE
        total_bytes = (end_sample - start_sample) * PCM16_BYTES_PER_SAMPLE
        if len(frame.pcm) < total_bytes:
            raise LiveProviderBundleAdmissionError("webrtc frame pcm is shorter than the accepted range.")

        observations: list[SpeechObservation] = []
        cursor = start_sample
        byte_cursor = 0

        if self._carried_pcm:
            taken = min(frame_bytes - len(self._carried_pcm), total_bytes)
            self._carried_pcm += frame.pcm[:taken]
            byte_cursor = taken
            if len(self._carried_pcm) == frame_bytes:
                decided = self._decide(bytes(self._carried_pcm))
                self._carried_pcm.clear()
            else:
                decided = None
            cursor = self._append(observations, cursor, taken // PCM16_BYTES_PER_SAMPLE, decided)

        while total_bytes - byte_cursor >= frame_bytes:
            byte_end = byte_cursor + frame_bytes
            decided = self._decide(frame.pcm[byte_cursor:byte_end])
            cursor = self._append(observations, cursor, self.frame_samples, decided)
            byte_cursor = byte_end

        if byte_cursor < total_bytes:
            self._carried_pcm += frame.pcm[byte_cursor:total_bytes]
            cursor = self._append(
                observations,
                cursor,
                (total_bytes - byte_cursor) // PCM16_BYTES_PER_SAMPLE,
                None,
            )
        return tuple(observations)

    def _decide(self, piece: bytes) -> bool:
        voiced = bool(_call_webrtc_vad(self._vad, piece, self.sample_rate))
        self._carried_voiced = voiced
        return voiced

    def _append(
        self,
        observations: list[SpeechObservation],
        cursor: int,
        piece_samples: int,
        decided: bool | None,
    ) -> int:
        voiced = self._carried_voiced if decided is None else decided
        observations.append(
            SpeechObservation(
                start_sample=cursor,
                end_sample=cursor + piece_samples,
                speech_present=voiced,
                confidence=None if decided is None else (1.0 if voiced else 0.0),
                provider_reason=(
                    f"{self.provider_reason}_carried" if decided is None else self.provider_reason
                ),
            )
        )
        return cursor + piece_samples


# A span's vectors are reconciled against the very next preparation, so one entry would do;
# the slack absorbs a reordering without ever letting the map track the meeting's length.
_PENDING_SPAN_LIMIT = 8


class WeSpeakerLiveEvidenceProvider:
    """Live evidence adapter over the pinned file-mode WeSpeaker encoder seam."""

    def __init__(
        self,
        *,
        encoder: Any,
        canonical_embedding: Callable[[LiveIdentitySnapshot, str], Sequence[float] | None] | None = None,
        min_segment_samples: int = 1,
        birth_min_seconds: float = ALBUM_BIRTH_MIN_SECONDS,
        album: FingerprintAlbum | None = None,
        sweeper: LiveIdentitySweeper | None = None,
    ):
        if min_segment_samples <= 0:
            raise LiveProviderBundleAdmissionError("wespeaker min_segment_samples must be positive.")
        if not callable(getattr(encoder, "embed", None)):
            raise LiveProviderBundleAdmissionError("wespeaker encoder must expose embed().")
        if (
            isinstance(birth_min_seconds, bool)
            or not isinstance(birth_min_seconds, (int, float))
            or not math.isfinite(birth_min_seconds)
            or birth_min_seconds <= 0.0
        ):
            raise LiveProviderBundleAdmissionError(
                "wespeaker birth_min_seconds must be positive and finite."
            )
        self.encoder = encoder
        self._canonical_embedding = canonical_embedding
        self.min_segment_samples = int(min_segment_samples)
        self.birth_min_seconds = float(birth_min_seconds)
        # ADR-0002's reference-vector policy. The ADR names `canonical_embedding` as the
        # injection point; the album is passed as its own collaborator because it owns the
        # *write* side too -- replacing latest-span overwrite is an admission decision, and
        # splitting reading from writing across two objects is what let a 0.5 s fragment
        # overwrite a good prototype in the first place.
        self._album = album
        # ADR-0002 step 3. The sweeper retains the *same* vectors the album is offered, because
        # this is the only object in the live path that ever holds one -- but it retains them on
        # a wider rule: the album hears assignments, the sweeper hears every embedded unit,
        # including the ones an abstention left unlabelled. A sweeper with no album has nothing
        # to re-match against, so the two are constructed together or not at all.
        self._sweeper = sweeper
        self._pending_vectors: dict[int, dict[str, tuple[tuple[float, ...], float]]] = {}
        self._canonical_vectors: dict[str, tuple[float, ...]] = {}

    def score(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        segments: tuple[TranscriptSegment, ...],
        base_snapshot: LiveIdentitySnapshot,
    ) -> tuple[LiveSpeakerEvidence, ...]:
        self._reconcile_committed_vectors(base_snapshot)
        if self._sweeper is not None:
            # The cadence fires *before* this span's own evidence is retained, and the meeting
            # time is the span's start. Both halves of that matter: a sweep that could see the
            # span currently being prepared would propose a label for it before the live path
            # had assigned one, and every one of those would be a correction to a transcript
            # nobody had read yet.
            self._sweeper.maybe_sweep(meeting_seconds=span.start_sample / LIVE_SAMPLE_RATE)
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
        # The album's admission gate is a duration, so the seconds of speech that produced each
        # vector travel with it: the encoder sees the intervals, nothing downstream does.
        self._pending_vectors[span.id] = {
            speaker: (vector, _intervals_duration(intervals_by_speaker[speaker]))
            for speaker, vector in local_vectors.items()
        }
        if self._sweeper is not None:
            # Retained unlabelled, now, rather than only when a preparation reconciles it. An
            # abstained span never reconciles -- that is what `_forget_stale_pending` is for --
            # and an abstained span is precisely the one a later sweep has something to say
            # about, so retaining only what was already labelled would make the sweep unable to
            # improve the spans the live path found hardest.
            for speaker, (vector, duration_sec) in self._pending_vectors[span.id].items():
                self._sweeper.record(
                    span_id=span.id,
                    local_speaker=speaker,
                    canonical_speaker=None,
                    vector=vector,
                    duration_sec=duration_sec,
                )
        self._forget_stale_pending()
        if not base_snapshot.canonical_speakers:
            return ()
        evidence: list[LiveSpeakerEvidence] = []
        for local_speaker, local_vector in sorted(local_vectors.items()):
            for canonical_speaker in base_snapshot.canonical_speakers:
                canonical_vector = self._canonical_vector(base_snapshot, canonical_speaker)
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

    def birth_deferrals(
        self,
        *,
        span_id: int,
        candidates: Sequence[str],
    ) -> tuple[tuple[str, float], ...]:
        """Which of a span's would-be births this stack will not enrol, and the seconds behind each.

        `BoundedCausalIdentityPreparer` owns what a deferral means. The birth floor is
        deliberately separate from the album's enrollment floor: real 9-clip replay showed
        that making a 2.0 s enrollment floor gate cold-start births collapses one clip, while
        1.0 s births preserve the accepted corpus result. A sub-enrollment birth therefore
        gets only the album's provisional stand-in until 2.0 s evidence retires it.

        A speaker whose evidence the encoder was never asked for reports **0.0 s**, not
        absence: `_speaker_intervals_by_label` drops every segment below
        `min_segment_samples`, so a local speaker present in the transcript and missing from
        the pending map is exactly the fragment case -- the one that minted 14 of 16
        canonical speakers in a certification run.

        No album means no admission gate, so nothing is deferred. That is not a loophole: the
        deployed bundle always builds one, and the album-less stacks are the pre-ADR-0002
        overwrite policy and the harness control that measures it. Deferring there would
        change a baseline instead of a behaviour.
        """

        if self._album is None:
            return ()
        floor = self.birth_min_seconds
        pending = self._pending_vectors.get(span_id, {})
        deferred: list[tuple[str, float]] = []
        for local_speaker in candidates:
            observation = pending.get(local_speaker)
            seconds = 0.0 if observation is None else observation[1]
            if seconds < floor:
                deferred.append((local_speaker, seconds))
        return tuple(deferred)

    def finalize_identity(self, *, base_snapshot: LiveIdentitySnapshot) -> None:
        """Settle the meeting's last preparation, then sweep once more, in that order.

        ADR-0002's final sweep. Both halves are here rather than in the caller because both
        are facts about retained evidence, and the order between them is load-bearing: a
        span's vectors acquire their canonical speaker when the *next* span's preparation
        reconciles them, so at session end the last span is still retained unlabelled. A
        sweep run before that reconcile would re-match the last span against the album and
        propose a `labelled` correction for a span the live path had already labelled --
        a rewrite that changes nothing, reported as if it had.

        Sweeping unconditionally is the point of the call: `maybe_sweep` is paced by the
        following span's start, so the meeting's last interval has nothing to trigger it, and
        that interval is where the accuracy harness (`tests/live_identity_accuracy.py`)
        measures essentially all of the sweep's gain.
        What it produces is left for `take_identity_revision` exactly as a cadence sweep
        leaves it -- this makes a correction available and never publishes one.
        """

        self._reconcile_committed_vectors(base_snapshot)
        if self._sweeper is not None:
            self._sweeper.sweep_now()

    def take_identity_revision(self) -> SweepRevision | None:
        """The newest unpublished sweep result, or `None` when this stack cannot sweep.

        The provider is where a vector lives, so it is where the sweeper lives; publishing a
        correction is somebody else's job entirely. This exists so that the object holding the
        evidence never has to know what a transcript is.
        """

        return None if self._sweeper is None else self._sweeper.take_revision()

    def _canonical_vector(
        self,
        snapshot: LiveIdentitySnapshot,
        speaker: str,
    ) -> Sequence[float] | None:
        if self._canonical_embedding is not None:
            return self._canonical_embedding(snapshot, speaker)
        if self._album is not None:
            return self._album.reference(speaker)
        return self._canonical_vectors.get(speaker)

    def _forget_stale_pending(self) -> None:
        """Bound the pending map; only the newest span is ever reconciled against.

        A span whose preparation abstains or fails is never popped, so without this the map
        grows for the length of the meeting -- and abstains are the *designed* outcome for an
        ambiguous identity, so a long meeting produces plenty of them.
        """

        while len(self._pending_vectors) > _PENDING_SPAN_LIMIT:
            del self._pending_vectors[min(self._pending_vectors)]

    def _reconcile_committed_vectors(self, snapshot: LiveIdentitySnapshot) -> None:
        diagnostics = dict(snapshot.diagnostics)
        if diagnostics.get("status") != "prepared":
            return
        try:
            span_id = int(diagnostics["span_id"])
        except (KeyError, TypeError, ValueError):
            return
        pending = self._pending_vectors.pop(span_id, None)
        if pending is None:
            return
        for assignment in diagnostics.get("assignments", "").split(","):
            if "->" not in assignment:
                continue
            local_speaker, canonical_speaker = assignment.split("->", 1)
            observation = pending.get(local_speaker)
            if observation is None:
                continue
            vector, duration_sec = observation
            if self._sweeper is not None:
                # The same unit again, now carrying the label the live path gave it. The ledger
                # answers `replaced`, the unit count does not move, and the retained evidence
                # now says what a reader was shown -- which is what a correction is measured
                # against.
                self._sweeper.record(
                    span_id=span_id,
                    local_speaker=local_speaker,
                    canonical_speaker=canonical_speaker,
                    vector=vector,
                    duration_sec=duration_sec,
                )
            if self._album is None:
                self._canonical_vectors[canonical_speaker] = vector
                continue
            self._album.observe(
                canonical_speaker=canonical_speaker,
                vector=vector,
                duration_sec=duration_sec,
                span_id=span_id,
            )


def _speech_provider(config: LiveProviderBundleConfig):
    payload = config.speech_provider
    kind = _required_str(payload, "kind")
    if kind == "silero_onnx":
        package_import = _required_declared_import(config, payload, field="speech_provider")
        asset = _required_named_asset(config, payload, key="asset_name", field="speech_provider")
        factory_name = _required_str(payload, "factory")
        module = importlib.import_module(package_import)
        factory = getattr(module, factory_name, None)
        if not callable(factory):
            raise LiveProviderBundleAdmissionError(
                f"speech_provider.factory is not callable: {package_import}.{factory_name}",
                code="bundle_provider_factory",
            )
        engine = factory(
            model_path=str(asset.path),
            backend=config.runtime.backend,
            device=config.runtime.device,
            intra_op_threads=config.runtime.intra_op_threads,
            inter_op_threads=config.runtime.inter_op_threads,
        )
        infer = engine if callable(engine) else getattr(engine, "speech_score", None)
        if not callable(infer):
            raise LiveProviderBundleAdmissionError(
                "silero provider factory must return a callable or expose speech_score().",
                code="bundle_provider_factory",
            )
        return SileroOnnxSpeechProvider(
            infer=infer,
            threshold=_required_probability(payload, "threshold", field="speech_provider"),
            provider_reason=str(payload.get("provider_reason") or "silero_onnx_observation"),
        )
    if kind == "webrtc":
        package_import = _required_declared_import(config, payload, field="speech_provider")
        factory_name = _required_str(payload, "factory")
        module = importlib.import_module(package_import)
        factory = getattr(module, factory_name, None)
        if not callable(factory):
            raise LiveProviderBundleAdmissionError(
                f"speech_provider.factory is not callable: {package_import}.{factory_name}",
                code="bundle_provider_factory",
            )
        mode = _non_negative_int(payload.get("mode"), "speech_provider.mode")
        vad = factory(mode)
        return WebRtcSpeechProvider(
            vad=vad,
            frame_samples=_positive_int(payload.get("frame_samples"), "speech_provider.frame_samples"),
            provider_reason=str(payload.get("provider_reason") or "webrtc_observation"),
        )
    return _reject_removed_static_provider(payload)


def _reject_removed_static_provider(payload: Mapping[str, Any]):
    kind = _required_str(payload, "kind")
    if kind != "static_observation":
        raise LiveProviderBundleAdmissionError(f"unsupported speech provider kind: {kind}", code="bundle_provider_kind")
    raise LiveProviderBundleAdmissionError(
        "static_observation is an unwired stub and cannot enable live mode.",
        code="bundle_provider_kind",
    )


def _identity_encoder(config: LiveProviderBundleConfig):
    payload = config.identity_provider
    kind = _required_str(payload, "kind")
    if kind != "wespeaker_resnet152_lm":
        raise LiveProviderBundleAdmissionError(
            f"unsupported identity provider kind: {kind}",
            code="bundle_identity_provider_kind",
        )
    importlib.import_module(_required_declared_import(config, payload, field="identity_provider"))
    state_asset = _required_named_asset(config, payload, key="state_asset_name", field="identity_provider")
    embedding_dimension = config.runtime.embedding_dimension
    if embedding_dimension is None:
        raise LiveProviderBundleAdmissionError(
            "runtime.embedding_dimension is required for live identity.",
            code="bundle_embedding_dimension",
        )
    spec = TierBAssetSpec(
        provider=kind,
        revision=_required_str(payload, "revision"),
        state_sha256=state_asset.sha256,
        embedding_dimension=embedding_dimension,
        frontend_version=_required_str(payload, "frontend_version"),
    )
    return WeSpeakerResNet152LmAdapter(state_asset.path, spec=spec, device=config.runtime.device)


def _identity_preparer(
    config: LiveProviderBundleConfig,
    *,
    encoder: Any,
) -> BoundedCausalIdentityPreparer:
    """One session's identity stack: the matcher's config, the album, and the sweeper.

    The config is built once and handed to both halves deliberately. A sweep re-matches with
    `assign_speakers`, the very function the live path assigns with (N-sweep decision 2), so a
    sweeper holding a second `LiveIdentityConfig` would be a second calibration -- the exact
    thing candidate 63 removed one layer up, where the album could be measured at one pair of
    thresholds and deployed at another.
    """

    identity_config = _identity_config(config.identity_config)
    return BoundedCausalIdentityPreparer(
        config=identity_config,
        evidence_provider=_identity_evidence_provider(
            config,
            encoder=encoder,
            identity_config=identity_config,
        ),
    )


def _identity_evidence_provider(
    config: LiveProviderBundleConfig,
    *,
    encoder: Any,
    identity_config: LiveIdentityConfig,
) -> WeSpeakerLiveEvidenceProvider:
    """The album and the sweeper are built here together, and the config is not optional.

    ADR-0002 classes the album shipped without the retrospective sweep as a terminal-state
    failure, so a code path that could produce one without the other would be a way to ship the
    documented failure by omission. Requiring the config rather than defaulting it is what makes
    that unwritable: there is no argument list that yields an album and no sweeper.
    """

    album = _fingerprint_album(config.identity_provider)
    return WeSpeakerLiveEvidenceProvider(
        encoder=encoder,
        min_segment_samples=_positive_int(
            config.identity_provider.get("min_segment_samples"),
            "identity_provider.min_segment_samples",
        ),
        birth_min_seconds=_birth_min_seconds(config.identity_provider),
        album=album,
        sweeper=LiveIdentitySweeper(album=album, config=identity_config),
    )


def _fingerprint_album(payload: Mapping[str, Any]) -> FingerprintAlbum:
    """ADR-0002's parameters as code defaults, overridable by a manifest that names them.

    The deployed manifest is generated and hash-covered, so requiring new keys would refuse the
    document that is running today. Absent keys mean ADR-0002 §7's measured starting values, and
    the ADR's recalibration against album centroid statistics stays a manifest edit rather than a
    code change.
    """

    admission = payload.get("album_admission_seconds")
    exemplars = payload.get("album_exemplars_per_speaker")
    return FingerprintAlbum(
        admission_seconds=(
            ALBUM_ADMISSION_SECONDS
            if admission is None
            else _positive_float(admission, "identity_provider.album_admission_seconds")
        ),
        exemplars_per_speaker=(
            ALBUM_EXEMPLARS_PER_SPEAKER
            if exemplars is None
            else _positive_int(exemplars, "identity_provider.album_exemplars_per_speaker")
        ),
    )


def _birth_min_seconds(payload: Mapping[str, Any]) -> float:
    value = payload.get("birth_min_seconds")
    return (
        ALBUM_BIRTH_MIN_SECONDS
        if value is None
        else _positive_float(value, "identity_provider.birth_min_seconds")
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


def _intervals_duration(intervals: list[tuple[float, float]]) -> float:
    return sum(end - start for start, end in intervals)


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
    """The album's similarity rule, wrapped back into this module's typed refusals.

    The arithmetic lives beside the album because a retrospective sweep has to score voices the
    same way the live matcher does, and two implementations of "how alike are these voices" is
    exactly the hazard `tests/live_identity_accuracy.py` was built to rule out. The two
    admission errors are kept distinct here: they are this provider's older contract.
    """

    if len(left) != len(right):
        raise LiveProviderBundleAdmissionError("wespeaker evidence vector dimensions must match.")
    score = cosine_similarity(left, right)
    if score is None:
        raise LiveProviderBundleAdmissionError("wespeaker evidence vectors must be non-zero.")
    return score


def _collect_preflight_failures(config: LiveProviderBundleConfig) -> list[str]:
    failures: list[str] = []
    if config.runtime.device != "cpu":
        failures.append("runtime.device must be cpu")
    for name in ("intra_op_threads", "inter_op_threads"):
        if getattr(config.runtime, name) <= 0:
            failures.append(f"runtime.{name} must be positive")
    if not config.packages:
        failures.append("packages must declare every provider import")
    if not config.assets:
        failures.append("assets must declare every provider asset")
    failures.extend(_package_failures(config.packages))
    failures.extend(_asset_failures(config.assets + (config.golden.input,)))
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
        _validate_provider_references(config)
    except Exception as exc:
        failures.append(str(exc))
    if failures:
        return failures
    try:
        speech_provider = _speech_provider(config)
        identity_encoder = _identity_encoder(config)
        failures.extend(_golden_failures(config, speech_provider=speech_provider, identity_encoder=identity_encoder))
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
        parent_import = package.import_name.split(".", 1)[0]
        if "." in package.import_name and importlib.util.find_spec(parent_import) is None:
            failures.append(f"package import is not available: {package.import_name}")
            continue
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


def _golden_failures(
    config: LiveProviderBundleConfig,
    *,
    speech_provider: Any,
    identity_encoder: Any,
) -> list[str]:
    golden = config.golden
    frame = _read_golden_frame(golden.input.path)
    observations = speech_provider.observe(
        frame=frame,
        start_sample=0,
        end_sample=frame.sample_count,
    )
    identity_preflight = identity_encoder.preflight(fixture_path=golden.input.path)
    if not identity_preflight.available:
        return [f"identity provider golden preflight failed: {identity_preflight.reason}"]
    embedding = _vector_values(
        identity_encoder.embed(
            golden.input.path,
            [(0.0, frame.sample_count / float(LIVE_SAMPLE_RATE))],
        )
    )
    if len(embedding) != config.runtime.embedding_dimension:
        return ["runtime.embedding_dimension mismatch"]
    actual_identity = (
        f"{_required_str(config.speech_provider, 'kind')}"
        f"+{_required_str(config.identity_provider, 'kind')}:golden-v1"
    )
    if golden.expected_output_identity != actual_identity:
        return ["golden expected_output_identity mismatch"]
    actual = hash_config(
        {
            "schema_version": 1,
            "output_identity": actual_identity,
            "speech_observations": [asdict(item) for item in observations],
            "identity_embedding": list(embedding),
        }
    )
    if actual != golden.expected_output_sha256:
        return ["golden expected_output_sha256 mismatch"]
    return []


def _validate_provider_references(config: LiveProviderBundleConfig) -> None:
    speech_kind = _required_str(config.speech_provider, "kind")
    expected_backend = RUNTIME_BACKEND_BY_SPEECH_PROVIDER.get(speech_kind)
    if expected_backend is None:
        _reject_removed_static_provider(config.speech_provider)
    if config.runtime.backend != expected_backend:
        raise LiveProviderBundleAdmissionError(
            f"runtime.backend must be {expected_backend} for {speech_kind}.",
            code="bundle_runtime_backend",
        )
    speech_import = _required_declared_import(config, config.speech_provider, field="speech_provider")
    identity_import = _required_declared_import(config, config.identity_provider, field="identity_provider")
    declared_imports = {package.import_name for package in config.packages}
    used_imports = {speech_import, identity_import}
    if declared_imports != used_imports:
        raise LiveProviderBundleAdmissionError(
            "packages must contain exactly the imports consumed by speech_provider and identity_provider.",
            code="bundle_package_coverage",
        )
    state_asset = _required_named_asset(
        config,
        config.identity_provider,
        key="state_asset_name",
        field="identity_provider",
    )
    used_assets = {state_asset.name}
    if speech_kind == "silero_onnx":
        used_assets.add(
            _required_named_asset(
                config,
                config.speech_provider,
                key="asset_name",
                field="speech_provider",
            ).name
        )
    declared_assets = {asset.name for asset in config.assets}
    if declared_assets != used_assets:
        raise LiveProviderBundleAdmissionError(
            "assets must contain exactly the files consumed by speech_provider and identity_provider.",
            code="bundle_asset_coverage",
        )
    _positive_int(config.identity_provider.get("min_segment_samples"), "identity_provider.min_segment_samples")
    _birth_min_seconds(config.identity_provider)


def _read_golden_frame(path: Path) -> AudioFrame:
    try:
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            sample_count = wav.getnframes()
            pcm = wav.readframes(sample_count)
    except (OSError, wave.Error) as exc:
        raise LiveProviderBundleAdmissionError(
            "golden.input must be a readable 16 kHz mono PCM16 WAV.",
            code="bundle_golden_input",
        ) from exc
    if channels != 1 or sample_width != 2 or sample_rate != LIVE_SAMPLE_RATE or sample_count <= 0:
        raise LiveProviderBundleAdmissionError(
            "golden.input must be a non-empty 16 kHz mono PCM16 WAV.",
            code="bundle_golden_input",
        )
    return AudioFrame(
        sequence=0,
        pcm=pcm,
        sample_count=sample_count,
        sample_rate=sample_rate,
    )


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
        "identity_provider": config.identity_provider,
        "schema_version": config.schema_version,
    }


def _hash_mapping(payload: Mapping[str, Any]) -> dict[str, str]:
    return {str(key): _sha256_value(str(value), f"config_hashes.{key}") for key, value in payload.items()}


def _required_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise LiveProviderBundleAdmissionError(f"{key} is required.", code="bundle_manifest_incomplete")
    return value


def _optional_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key, {})
    if not isinstance(value, Mapping):
        raise LiveProviderBundleAdmissionError(f"{key} must be an object.", code="bundle_manifest_invalid")
    return value


def _required_sequence(payload: Mapping[str, Any], key: str) -> tuple[Any, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise LiveProviderBundleAdmissionError(f"{key} is required.", code="bundle_manifest_incomplete")
    return tuple(value)


def _required_declared_import(
    config: LiveProviderBundleConfig,
    payload: Mapping[str, Any],
    *,
    field: str,
) -> str:
    import_name = _required_str(payload, "package_import")
    if import_name not in {package.import_name for package in config.packages}:
        raise LiveProviderBundleAdmissionError(
            f"{field}.package_import is not declared in packages: {import_name}",
            code="bundle_provider_package",
        )
    return import_name


def _required_named_asset(
    config: LiveProviderBundleConfig,
    payload: Mapping[str, Any],
    *,
    key: str,
    field: str,
) -> LiveProviderBundleAsset:
    name = _required_str(payload, key)
    matches = [asset for asset in config.assets if asset.name == name]
    if len(matches) != 1:
        raise LiveProviderBundleAdmissionError(
            f"{field}.{key} must reference exactly one declared asset: {name}",
            code="bundle_provider_asset",
        )
    return matches[0]


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


def _positive_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LiveProviderBundleAdmissionError(f"{name} must be a positive number.")
    if not math.isfinite(value) or value <= 0.0:
        raise LiveProviderBundleAdmissionError(f"{name} must be a positive number.")
    return float(value)


def _non_negative_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise LiveProviderBundleAdmissionError(f"{name} must be a non-negative integer.")
    return value


def _required_probability(payload: Mapping[str, Any], key: str, *, field: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise LiveProviderBundleAdmissionError(f"{field}.{key} must be numeric.")
    probability = float(value)
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise LiveProviderBundleAdmissionError(f"{field}.{key} must be between 0 and 1.")
    return probability


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
