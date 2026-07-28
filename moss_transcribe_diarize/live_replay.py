from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moss_transcribe_diarize.transcript_parser import parse_transcript

from .app.live_adapters import InferenceTranscript
from .app.live_arbiter import InferenceArbiter
from .app.live_coordinator import LiveCoordinator
from .app.live_endpoint import EndpointPolicy, EndpointPolicyConfig, SpeechObservation
from .app.live_identity import BoundedCausalIdentityPreparer, LiveIdentityConfig, LiveSpeakerEvidence
from .app.live_session import AudioFrame, FrozenSpan, LIVE_SAMPLE_RATE, PCM16_BYTES_PER_SAMPLE
from .app.live_session import LiveIdentitySnapshot, LiveSession


TRACE_SCHEMA_VERSION = 1
SUMMARY_SCHEMA_VERSION = 1
EVALUATOR_SCHEMA_VERSION = 1
ROOT = Path(__file__).resolve().parents[1]


class ReplayFailure(RuntimeError):
    exit_code = 2
    failure_kind = "integrity"


class ReplayProviderFailure(ReplayFailure):
    exit_code = 3
    failure_kind = "provider"


class ReplayIdentityFailure(ReplayFailure):
    exit_code = 4
    failure_kind = "identity"


class ReplayRtfFailure(ReplayFailure):
    exit_code = 5
    failure_kind = "rtf"


@dataclass(frozen=True, slots=True)
class ReplayOutputs:
    trace_path: Path
    summary_path: Path
    evaluator_path: Path


@dataclass(frozen=True, slots=True)
class _ReplayFrame:
    sequence: int
    pcm: bytes
    sample_count: int
    observations: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class _DecodeSpec:
    transcript: str
    decode_seconds: float | None
    evidence: tuple[LiveSpeakerEvidence, ...]


class _Trace:
    def __init__(self):
        self.events: list[dict[str, Any]] = []

    def add(self, event: str, **payload: Any) -> None:
        self.events.append(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "seq": len(self.events),
                "event": event,
                **_jsonable(payload),
            }
        )

    def write(self, path: Path) -> None:
        path.write_text(
            "".join(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for event in self.events),
            encoding="utf-8",
        )


class _ManifestSpeechProvider:
    def __init__(self, frames: dict[int, _ReplayFrame]):
        self._frames = frames

    def observe(self, *, frame: AudioFrame, start_sample: int, end_sample: int) -> tuple[SpeechObservation, ...]:
        try:
            replay_frame = self._frames[frame.sequence]
        except KeyError as exc:
            raise ReplayFailure(f"missing replay observations for frame {frame.sequence}") from exc
        observations: list[SpeechObservation] = []
        offset = 0
        for spec in replay_frame.observations:
            sample_count = _positive_int(spec.get("sample_count"), "observation sample_count")
            start_offset = _non_negative_int(spec.get("start_offset", offset), "observation start_offset")
            observation_start = start_sample + start_offset
            observation_end = observation_start + sample_count
            observations.append(
                SpeechObservation(
                    start_sample=observation_start,
                    end_sample=observation_end,
                    speech_present=bool(spec.get("speech_present", False)),
                    confidence=_optional_float(spec.get("confidence"), "observation confidence"),
                    provider_endpoint_sample=_optional_absolute_sample(
                        spec.get("provider_endpoint_offset"),
                        start_sample,
                        "provider_endpoint_offset",
                    ),
                    provider_reason=_optional_str(spec.get("provider_reason")),
                )
            )
            offset = start_offset + sample_count
        if start_sample + offset != end_sample:
            raise ReplayFailure(f"frame {frame.sequence} observations do not exactly cover accepted PCM")
        return tuple(observations)


class _ManifestDecoder:
    def __init__(self, decodes: dict[tuple[int, int], _DecodeSpec], *, max_samples: int, max_rtf: float | None):
        self.max_samples = max_samples
        self._decodes = decodes
        self._max_rtf = max_rtf

    def preflight(self):
        raise AssertionError("live replay uses manifest preflight before coordinator construction")

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        del pcm
        if span.sample_count > self.max_samples:
            raise ReplayProviderFailure("canonical span exceeds replay decoder max_samples")
        try:
            spec = self._decodes[(span.start_sample, span.end_sample)]
        except KeyError as exc:
            raise ReplayProviderFailure(f"missing decode for span {span.start_sample}:{span.end_sample}") from exc
        if spec.decode_seconds is not None and self._max_rtf is not None:
            audio_seconds = span.sample_count / float(LIVE_SAMPLE_RATE)
            if audio_seconds <= 0:
                raise ReplayFailure("span duration must be positive for RTF")
            rtf = spec.decode_seconds / audio_seconds
            if rtf > self._max_rtf:
                raise ReplayRtfFailure(f"span {span.id} RTF {rtf:.6g} exceeds max_rtf {self._max_rtf:.6g}")
        return InferenceTranscript(spec.transcript)


class _ManifestEvidenceProvider:
    def __init__(self, decodes: dict[tuple[int, int], _DecodeSpec]):
        self._decodes = decodes

    def score(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        segments,
        base_snapshot: LiveIdentitySnapshot,
    ) -> tuple[LiveSpeakerEvidence, ...]:
        del pcm, segments, base_snapshot
        spec = self._decodes.get((span.start_sample, span.end_sample))
        return () if spec is None else spec.evidence


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay ordered live PCM through the default-off live-session substrate without enabling any service."
    )
    parser.add_argument("--manifest", required=True, help="Replay manifest JSON.")
    parser.add_argument("--out-dir", required=True, help="Directory for trace.jsonl, summary.json, and evaluator.jsonl.")
    parser.add_argument("--service-state", default=None, help="Optional read-only JSON service-state file to record in preflight.")
    parser.add_argument("--expect-revision", default=None, help="Require the manifest revision to match this value.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        outputs = run_replay(
            manifest_path=Path(args.manifest),
            out_dir=Path(args.out_dir),
            service_state_path=None if args.service_state is None else Path(args.service_state),
            expect_revision=args.expect_revision,
        )
    except ReplayFailure as exc:
        print(f"live replay failed [{exc.failure_kind}]: {exc}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:
        print(f"live replay failed [integrity]: {exc}", file=sys.stderr)
        return ReplayFailure.exit_code
    print(
        json.dumps(
            {
                "trace": str(outputs.trace_path),
                "summary": str(outputs.summary_path),
                "evaluator": str(outputs.evaluator_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def run_replay(
    *,
    manifest_path: Path,
    out_dir: Path,
    service_state_path: Path | None = None,
    expect_revision: str | None = None,
) -> ReplayOutputs:
    manifest_path = manifest_path.expanduser().resolve()
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "trace.jsonl"
    summary_path = out_dir / "summary.json"
    evaluator_path = out_dir / "evaluator.jsonl"
    trace = _Trace()
    summary: dict[str, Any] | None = None

    try:
        manifest = _load_json(manifest_path)
        if int(manifest.get("schema_version", 0)) != 1:
            raise ReplayFailure("manifest schema_version must be 1")
        revision = _required_str(manifest.get("revision"), "manifest revision")
        if expect_revision is not None and revision != expect_revision:
            raise ReplayFailure("manifest revision does not match --expect-revision")

        provider = _preflight_provider(manifest.get("provider"), manifest_path.parent)
        config = _required_mapping(manifest.get("config"), "config")
        service_state = _service_state(manifest, manifest_path.parent, service_state_path)
        config_hash = _hash_payload(
            {
                "revision": revision,
                "provider": provider,
                "config": config,
                "frames": _frame_fingerprints(manifest.get("frames"), manifest_path.parent),
                "decodes": manifest.get("decodes", []),
            }
        )
        trace.add(
            "preflight",
            revision=revision,
            git_revision=_git_revision(),
            config_hash=config_hash,
            provider=provider,
            service_state=service_state,
        )

        frames = _load_frames(manifest.get("frames"), manifest_path.parent)
        decodes = _load_decodes(manifest.get("decodes"))
        if config.get("session_hard_cap_samples") is not None:
            # Refused rather than ignored: a manifest carrying this key was written against a
            # session that closed its own spans, and it would replay differently now that the
            # endpoint policy is the only authority for a span boundary.
            raise ReplayFailure(
                "session_hard_cap_samples is no longer a replay knob; declare the span cap once "
                "as endpoint_policy.hard_cap_samples"
            )
        session = LiveSession(
            max_retained_samples=_positive_int(config.get("max_retained_samples"), "max_retained_samples"),
        )
        endpoint = EndpointPolicy(_endpoint_config(config.get("endpoint_policy")))
        decoder = _ManifestDecoder(
            decodes,
            max_samples=_positive_int(config.get("max_decode_samples"), "max_decode_samples"),
            max_rtf=_optional_float(config.get("max_rtf"), "max_rtf"),
        )
        identity = BoundedCausalIdentityPreparer(
            config=_identity_config(config.get("identity")),
            evidence_provider=_ManifestEvidenceProvider(decodes),
        )
        arbiter = InferenceArbiter()
        coordinator = LiveCoordinator(
            session_key=_required_str(manifest.get("session_key", "replay"), "session_key"),
            session=session,
            endpoint_policy=endpoint,
            speech_provider=_ManifestSpeechProvider({frame.sequence: frame for frame in frames}),
            decoder=decoder,
            identity_preparer=identity,
            arbiter=arbiter,
        )

        for replay_frame in frames:
            result = coordinator.accept_frame(
                AudioFrame(
                    sequence=replay_frame.sequence,
                    pcm=replay_frame.pcm,
                    sample_count=replay_frame.sample_count,
                )
            )
            trace.add(
                "frame_accepted",
                sequence=replay_frame.sequence,
                start_sample=result.accepted_start_sample,
                end_sample=result.accepted_end_sample,
                endpoint_spans=[_endpoint_span_payload(span) for span in result.endpoint_spans],
                frozen_spans=[_frozen_span_payload(span) for span in result.frozen_spans],
                queued_item_ids=list(result.queued_item_ids),
            )
            _process_ready_work(coordinator, arbiter, trace)

        queued = coordinator.flush_endpoint()
        trace.add("endpoint_flushed", queued_item_ids=list(queued))
        _process_ready_work(coordinator, arbiter, trace)

        snapshot = session.snapshot()
        if snapshot.accepted_samples != snapshot.accounted_samples:
            raise ReplayFailure("replay ended without exact accepted/accounted equality")
        summary = _summary_payload(
            status="passed",
            revision=revision,
            config_hash=config_hash,
            provider=provider,
            service_state=service_state,
            snapshot=snapshot,
            failure=None,
        )
        _write_evaluator(evaluator_path, snapshot.committed)
        trace.add("summary", status="passed", accepted_samples=snapshot.accepted_samples, committed_samples=snapshot.committed_samples)
        return ReplayOutputs(trace_path=trace_path, summary_path=summary_path, evaluator_path=evaluator_path)
    except ReplayFailure as exc:
        trace.add("failure", status="failed", failure_kind=exc.failure_kind, reason=str(exc))
        summary = {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "status": "failed",
            "failure": {"kind": exc.failure_kind, "reason": str(exc)},
        }
        raise
    finally:
        trace.write(trace_path)
        if summary is not None:
            summary["files"] = {
                "trace": str(trace_path),
                "summary": str(summary_path),
                "evaluator": str(evaluator_path),
            }
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _process_ready_work(coordinator: LiveCoordinator, arbiter: InferenceArbiter, trace: _Trace) -> None:
    while True:
        item = arbiter.next_work()
        if item is None:
            return
        result = coordinator.process_work_item(item)
        trace.add(
            "work_processed",
            item_id=item.id,
            span_id=result.span_id,
            submitted=result.submitted,
            identity_status=result.identity_status,
            committed_samples=result.committed_samples,
        )
        if not result.submitted:
            raise ReplayIdentityFailure(f"identity preparation for span {result.span_id} was {result.identity_status}")


def _preflight_provider(raw: Any, base_dir: Path) -> dict[str, Any]:
    provider = _required_mapping(raw, "provider")
    assets = provider.get("assets", [])
    if not isinstance(assets, list):
        raise ReplayProviderFailure("provider assets must be a list")
    verified_assets = []
    for raw_asset in assets:
        asset = _required_mapping(raw_asset, "provider asset")
        name = _required_str(asset.get("name"), "provider asset name")
        path = _resolve_path(_required_str(asset.get("path"), f"provider asset {name} path"), base_dir)
        expected = _required_str(asset.get("sha256"), f"provider asset {name} sha256").lower()
        if len(expected) != 64:
            raise ReplayProviderFailure(f"provider asset {name} sha256 must be 64 hex characters")
        if not path.is_file():
            raise ReplayProviderFailure(f"provider asset {name} is not preinstalled at {path}")
        actual = _sha256(path)
        if actual != expected:
            raise ReplayProviderFailure(f"provider asset {name} checksum mismatch")
        verified_assets.append({"name": name, "path": str(path), "sha256": actual})
    return {
        "name": _required_str(provider.get("name"), "provider name"),
        "revision": _required_str(provider.get("revision"), "provider revision"),
        "assets": verified_assets,
    }


def _load_frames(raw: Any, base_dir: Path) -> tuple[_ReplayFrame, ...]:
    if not isinstance(raw, list) or not raw:
        raise ReplayFailure("frames must be a non-empty list")
    frames: list[_ReplayFrame] = []
    expected_sequence = 0
    for raw_frame in raw:
        frame = _required_mapping(raw_frame, "frame")
        sequence = _non_negative_int(frame.get("sequence"), "frame sequence")
        if sequence != expected_sequence:
            raise ReplayFailure(f"expected frame sequence {expected_sequence}, got {sequence}")
        pcm, sample_count = _load_pcm_frame(frame, base_dir)
        observations = frame.get("observations")
        if not isinstance(observations, list) or not observations:
            raise ReplayFailure(f"frame {sequence} observations must be a non-empty list")
        frames.append(_ReplayFrame(sequence, pcm, sample_count, tuple(observations)))
        expected_sequence += 1
    return tuple(frames)


def _load_pcm_frame(frame: dict[str, Any], base_dir: Path) -> tuple[bytes, int]:
    if "pcm_hex" in frame:
        pcm = bytes.fromhex(_required_str(frame["pcm_hex"], "pcm_hex"))
        sample_count = len(pcm) // PCM16_BYTES_PER_SAMPLE
    else:
        path = _resolve_path(_required_str(frame.get("pcm_path"), "frame pcm_path"), base_dir)
        pcm, sample_count = _read_wav_pcm(path)
    declared = frame.get("sample_count")
    if declared is not None and _positive_int(declared, "frame sample_count") != sample_count:
        raise ReplayFailure("frame sample_count does not match PCM")
    expected_sha = frame.get("sha256")
    if expected_sha is not None and _required_str(expected_sha, "frame sha256").lower() != hashlib.sha256(pcm).hexdigest():
        raise ReplayFailure("frame PCM checksum mismatch")
    return pcm, sample_count


def _load_decodes(raw: Any) -> dict[tuple[int, int], _DecodeSpec]:
    if not isinstance(raw, list) or not raw:
        raise ReplayProviderFailure("decodes must be a non-empty list")
    decodes: dict[tuple[int, int], _DecodeSpec] = {}
    for raw_decode in raw:
        decode = _required_mapping(raw_decode, "decode")
        start_sample = _non_negative_int(decode.get("start_sample"), "decode start_sample")
        end_sample = _positive_int(decode.get("end_sample"), "decode end_sample")
        if end_sample <= start_sample:
            raise ReplayProviderFailure("decode end_sample must advance")
        key = (start_sample, end_sample)
        if key in decodes:
            raise ReplayProviderFailure(f"duplicate decode for span {start_sample}:{end_sample}")
        transcript = _required_str(decode.get("transcript"), "decode transcript")
        if not tuple(parse_transcript(transcript)):
            raise ReplayProviderFailure(f"decode {start_sample}:{end_sample} transcript is not parseable")
        decodes[key] = _DecodeSpec(
            transcript=transcript,
            decode_seconds=_optional_float(decode.get("decode_seconds"), "decode_seconds"),
            evidence=_load_evidence(decode.get("evidence", [])),
        )
    return decodes


def _load_evidence(raw: Any) -> tuple[LiveSpeakerEvidence, ...]:
    if not isinstance(raw, list):
        raise ReplayProviderFailure("decode evidence must be a list")
    evidence: list[LiveSpeakerEvidence] = []
    for item in raw:
        mapping = _required_mapping(item, "identity evidence")
        evidence.append(
            LiveSpeakerEvidence(
                local_speaker=_required_str(mapping.get("local_speaker"), "local_speaker"),
                canonical_speaker=_required_str(mapping.get("canonical_speaker"), "canonical_speaker"),
                score=_float(mapping.get("score"), "score"),
                evidence_id=str(mapping.get("evidence_id", "")),
            )
        )
    return tuple(evidence)


def _endpoint_config(raw: Any) -> EndpointPolicyConfig:
    config = _required_mapping(raw, "endpoint_policy")
    return EndpointPolicyConfig(
        min_speech_samples=_non_negative_int(config.get("min_speech_samples"), "min_speech_samples"),
        min_silence_samples=_non_negative_int(config.get("min_silence_samples"), "min_silence_samples"),
        pre_speech_padding_samples=_non_negative_int(config.get("pre_speech_padding_samples", 0), "pre_speech_padding_samples"),
        post_speech_padding_samples=_non_negative_int(config.get("post_speech_padding_samples", 0), "post_speech_padding_samples"),
        hard_cap_samples=_optional_positive_int(config.get("hard_cap_samples"), "endpoint hard_cap_samples"),
    )


def _identity_config(raw: Any) -> LiveIdentityConfig:
    config = _required_mapping(raw, "identity")
    return LiveIdentityConfig(
        max_speakers=_positive_int(config.get("max_speakers"), "max_speakers"),
        min_match_score=_float(config.get("min_match_score"), "min_match_score"),
        min_match_margin=_float(config.get("min_match_margin"), "min_match_margin"),
    )


def _service_state(manifest: dict[str, Any], base_dir: Path, override: Path | None) -> dict[str, Any]:
    path = override
    if path is None and manifest.get("service_state_path") is not None:
        path = _resolve_path(_required_str(manifest["service_state_path"], "service_state_path"), base_dir)
    if path is not None:
        return _load_json(path.expanduser().resolve())
    state = manifest.get("service_state", {})
    if not isinstance(state, dict):
        raise ReplayFailure("service_state must be a JSON object")
    return state


def _summary_payload(
    *,
    status: str,
    revision: str,
    config_hash: str,
    provider: dict[str, Any],
    service_state: dict[str, Any],
    snapshot,
    failure: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": status,
        "revision": revision,
        "config_hash": config_hash,
        "provider": provider,
        "service_state": service_state,
        "accepted_samples": snapshot.accepted_samples,
        "accounted_samples": snapshot.accounted_samples,
        "committed_samples": snapshot.committed_samples,
        "committed_prefix_hash": snapshot.committed_prefix_hash,
        "identity_snapshot": {
            "version": snapshot.identity_snapshot.version,
            "canonical_speakers": list(snapshot.identity_snapshot.canonical_speakers),
            "diagnostics": [list(item) for item in snapshot.identity_snapshot.diagnostics],
        },
        "committed_spans": [
            {
                "span_id": commit.span_id,
                "start_sample": commit.start_sample,
                "end_sample": commit.end_sample,
                "identity_snapshot_version": commit.identity_snapshot_version,
                "prefix_hash": commit.prefix_hash,
            }
            for commit in snapshot.committed
        ],
        "failure": failure,
    }


def _write_evaluator(path: Path, committed) -> None:
    rows: list[dict[str, Any]] = []
    for commit in committed:
        span_offset = commit.start_sample / float(LIVE_SAMPLE_RATE)
        for segment in parse_transcript(commit.transcript):
            rows.append(
                {
                    "schema_version": EVALUATOR_SCHEMA_VERSION,
                    "span_id": commit.span_id,
                    "start": round(span_offset + segment.start, 6),
                    "end": round(span_offset + segment.end, 6),
                    "speaker": segment.speaker,
                    "text": segment.text,
                }
            )
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _frame_fingerprints(raw: Any, base_dir: Path) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ReplayFailure("frames must be a list")
    fingerprints: list[dict[str, Any]] = []
    for item in raw:
        frame = _required_mapping(item, "frame")
        if "pcm_hex" in frame:
            pcm = bytes.fromhex(_required_str(frame["pcm_hex"], "pcm_hex"))
            sample_count = len(pcm) // PCM16_BYTES_PER_SAMPLE
        else:
            pcm, sample_count = _read_wav_pcm(_resolve_path(_required_str(frame.get("pcm_path"), "frame pcm_path"), base_dir))
        fingerprints.append(
            {
                "sequence": frame.get("sequence"),
                "sample_count": sample_count,
                "sha256": hashlib.sha256(pcm).hexdigest(),
                "observations": frame.get("observations", []),
            }
        )
    return fingerprints


def _read_wav_pcm(path: Path) -> tuple[bytes, int]:
    if not path.is_file():
        raise ReplayFailure(f"PCM file does not exist: {path}")
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != PCM16_BYTES_PER_SAMPLE or wav.getframerate() != LIVE_SAMPLE_RATE:
            raise ReplayFailure("replay WAV must be 16 kHz mono PCM16")
        frames = wav.getnframes()
        pcm = wav.readframes(frames)
    if len(pcm) != frames * PCM16_BYTES_PER_SAMPLE:
        raise ReplayFailure("WAV PCM byte count does not match frame count")
    return pcm, frames


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReplayFailure(f"JSON file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReplayFailure(f"invalid JSON file: {path}") from exc
    if not isinstance(data, dict):
        raise ReplayFailure(f"JSON file must contain an object: {path}")
    return data


def _resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _endpoint_span_payload(span) -> dict[str, Any]:
    return {"start_sample": span.start_sample, "end_sample": span.end_sample, "reason": span.reason}


def _frozen_span_payload(span: FrozenSpan) -> dict[str, Any]:
    return {"id": span.id, "epoch": span.epoch, "start_sample": span.start_sample, "end_sample": span.end_sample, "reason": span.reason}


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(_jsonable(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_revision() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _required_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReplayFailure(f"{name} must be a JSON object")
    return value


def _required_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReplayFailure(f"{name} must be a non-empty string")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _positive_int(value: Any, name: str) -> int:
    result = _non_negative_int(value, name)
    if result <= 0:
        raise ReplayFailure(f"{name} must be positive")
    return result


def _optional_positive_int(value: Any, name: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, name)


def _non_negative_int(value: Any, name: str) -> int:
    if not isinstance(value, int):
        raise ReplayFailure(f"{name} must be an integer")
    if value < 0:
        raise ReplayFailure(f"{name} must be non-negative")
    return value


def _float(value: Any, name: str) -> float:
    if not isinstance(value, (int, float)):
        raise ReplayFailure(f"{name} must be numeric")
    return float(value)


def _optional_float(value: Any, name: str) -> float | None:
    if value is None:
        return None
    return _float(value, name)


def _optional_absolute_sample(value: Any, base_sample: int, name: str) -> int | None:
    if value is None:
        return None
    return base_sample + _non_negative_int(value, name)


if __name__ == "__main__":
    raise SystemExit(main())
