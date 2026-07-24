from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .app.live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceCreateResult,
    LiveServiceDescriptor,
    LiveServiceError,
    LiveServiceEvent,
    LiveServiceFailureKind,
    LiveServiceFailureRecord,
    LiveServiceFrameResult,
    LiveServiceRuntime,
    LiveServiceSnapshot,
)
from .app.live_session import (
    AudioFrame,
    CanonicalCommit,
    FrameAck,
    LIVE_SAMPLE_RATE,
    LiveIdentitySnapshot,
    LiveSnapshot,
    PCM16_BYTES_PER_SAMPLE,
    ProvisionalSuffix,
)


REPLAY_ARTIFACT_SCHEMA_VERSION = 1


class ServiceReplayFailure(RuntimeError):
    exit_code = 2
    failure_kind = "integrity"


class ServiceReplayProviderConfigFailure(ServiceReplayFailure):
    exit_code = 3
    failure_kind = "provider_config"


class ServiceReplayIdentityCommitFailure(ServiceReplayFailure):
    exit_code = 4
    failure_kind = "identity_commit"


class ServiceReplayRtfFailure(ServiceReplayFailure):
    exit_code = 5
    failure_kind = "rtf"


class ServiceReplayTransportFailure(ServiceReplayFailure):
    exit_code = 6
    failure_kind = "transport_pacing"


@dataclass(frozen=True, slots=True)
class ServiceReplayOutputs:
    manifest_path: Path
    trace_path: Path
    summary_path: Path
    evaluator_path: Path


class LiveReplayService(Protocol):
    def create(self) -> LiveServiceCreateResult:
        ...

    def accept_frame(self, session_id: str, frame: AudioFrame) -> LiveServiceFrameResult:
        ...

    def events(self, session_id: str, since_seq: int = 0) -> tuple[LiveServiceEvent, ...]:
        ...

    def snapshot(self, session_id: str, since_version: int | None = None) -> LiveServiceSnapshot | None:
        ...

    async def stop(self, session_id: str, deadline: float) -> LiveServiceSnapshot:
        ...

    async def abort(self, session_id: str, reason: str) -> LiveServiceSnapshot:
        ...


class HttpLiveReplayService:
    def __init__(self, *, base_url: str, timeout_seconds: float = 10.0):
        if not base_url:
            raise ValueError("base_url must be non-empty.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)

    def create(self) -> LiveServiceCreateResult:
        payload = self._json("POST", "/api/live/sessions")
        return LiveServiceCreateResult(
            session_id=str(payload["id"]),
            descriptor=_descriptor_from_dict(payload["descriptor"]),
            snapshot=_snapshot_from_dict(payload["snapshot"]),
        )

    def accept_frame(self, session_id: str, frame: AudioFrame) -> LiveServiceFrameResult:
        payload = self._json(
            "POST",
            f"/api/live/sessions/{urllib.parse.quote(session_id, safe='')}/frames",
            {
                "sequence": frame.sequence,
                "sample_rate": frame.sample_rate,
                "sample_count": frame.sample_count,
                "pcm_base64": base64.b64encode(frame.pcm).decode("ascii"),
            },
        )
        snapshot_payload = self._json(
            "GET",
            f"/api/live/sessions/{urllib.parse.quote(session_id, safe='')}/snapshot",
        )["snapshot"]
        return LiveServiceFrameResult(
            ack=_frame_ack_from_dict(payload["ack"]),
            queued_item_ids=tuple(int(item) for item in payload.get("queued_item_ids", ())),
            snapshot=_snapshot_from_dict(snapshot_payload),
        )

    def events(self, session_id: str, since_seq: int = 0) -> tuple[LiveServiceEvent, ...]:
        query = urllib.parse.urlencode({"since_seq": int(since_seq)})
        payload = self._json(
            "GET",
            f"/api/live/sessions/{urllib.parse.quote(session_id, safe='')}/events?{query}",
        )
        return tuple(_event_from_dict(item) for item in payload["events"])

    def snapshot(self, session_id: str, since_version: int | None = None) -> LiveServiceSnapshot | None:
        query = "" if since_version is None else "?" + urllib.parse.urlencode({"since_version": int(since_version)})
        payload = self._json(
            "GET",
            f"/api/live/sessions/{urllib.parse.quote(session_id, safe='')}/snapshot{query}",
        )
        snapshot = payload["snapshot"]
        return None if snapshot is None else _snapshot_from_dict(snapshot)

    async def stop(self, session_id: str, deadline: float) -> LiveServiceSnapshot:
        payload = await asyncio.to_thread(
            self._json,
            "POST",
            f"/api/live/sessions/{urllib.parse.quote(session_id, safe='')}/stop",
            {"deadline": float(deadline)},
        )
        return _snapshot_from_dict(payload["snapshot"])

    async def abort(self, session_id: str, reason: str) -> LiveServiceSnapshot:
        payload = await asyncio.to_thread(
            self._json,
            "POST",
            f"/api/live/sessions/{urllib.parse.quote(session_id, safe='')}/abort",
            {"reason": reason},
        )
        return _snapshot_from_dict(payload["snapshot"])

    def _json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return _load_json_bytes(response.read())
        except urllib.error.HTTPError as exc:
            body = exc.read()
            response_payload = _load_json_bytes(body) if body else {}
            if exc.code == 404 and path.startswith("/api/live"):
                raise ServiceReplayProviderConfigFailure("live service routes are disabled.") from exc
            if isinstance(response_payload, dict) and isinstance(response_payload.get("failure"), dict):
                raise _replay_failure_from_service(_failure_from_dict(response_payload["failure"])) from exc
            detail = response_payload.get("detail") if isinstance(response_payload, dict) else str(exc)
            if exc.code in {408, 429, 502, 503, 504}:
                raise ServiceReplayTransportFailure(str(detail)) from exc
            raise ServiceReplayIdentityCommitFailure(str(detail)) from exc
        except (TimeoutError, OSError) as exc:
            raise ServiceReplayTransportFailure(f"ambiguous HTTP live replay result: {exc}") from exc


class InMemoryLiveReplayService:
    def __init__(self, runtime: LiveServiceRuntime):
        self.runtime = runtime

    def create(self) -> LiveServiceCreateResult:
        return self.runtime.create()

    def accept_frame(self, session_id: str, frame: AudioFrame) -> LiveServiceFrameResult:
        return self.runtime.accept_frame(session_id, frame)

    def events(self, session_id: str, since_seq: int = 0) -> tuple[LiveServiceEvent, ...]:
        return self.runtime.events(session_id, since_seq=since_seq)

    def snapshot(self, session_id: str, since_version: int | None = None) -> LiveServiceSnapshot | None:
        return self.runtime.snapshot(session_id, since_version=since_version)

    async def stop(self, session_id: str, deadline: float) -> LiveServiceSnapshot:
        return await self.runtime.stop(session_id, deadline)

    async def abort(self, session_id: str, reason: str) -> LiveServiceSnapshot:
        return await self.runtime.abort(session_id, reason)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay 16 kHz mono PCM16 audio through an explicitly enabled live service runtime."
    )
    parser.add_argument("--base-url", required=True, help="Opt-in live service base URL.")
    parser.add_argument("--audio", required=True, help="16 kHz mono PCM16 WAV input.")
    parser.add_argument("--out-dir", required=True, help="Directory for replay artifacts.")
    parser.add_argument("--pace", type=float, default=1.0, help="Replay pace multiplier.")
    parser.add_argument("--max-pacing-lag", type=float, default=1.0, help="Maximum allowed pacing lag in seconds.")
    parser.add_argument("--runs", type=int, default=1, help="Number of replay runs.")
    parser.add_argument("--expect-revision", required=True, help="Expected service source revision.")
    parser.add_argument("--expect-provider-hash", required=True, help="Expected provider manifest hash.")
    parser.add_argument("--expect-config-hash", required=True, help="Expected combined configuration hash.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run_service_replay(
            service=HttpLiveReplayService(base_url=args.base_url),
            audio_path=Path(args.audio),
            out_dir=Path(args.out_dir),
            pace=args.pace,
            max_pacing_lag=args.max_pacing_lag,
            runs=args.runs,
            expect_revision=args.expect_revision,
            expect_provider_hash=args.expect_provider_hash,
            expect_config_hash=args.expect_config_hash,
        )
    except ServiceReplayFailure as exc:
        print(f"live service replay failed [{exc.failure_kind}]: {exc}", file=sys.stderr)
        return exc.exit_code
    except LiveServiceError as exc:
        failure = exc.failure
        print(f"live service replay failed [{failure.kind.value}]: {failure.message}", file=sys.stderr)
        return _exit_code_for_service_failure(failure.kind)
    except Exception as exc:
        print(f"live service replay failed [integrity]: {exc}", file=sys.stderr)
        return ServiceReplayFailure.exit_code
    return 0


def run_service_replay(
    *,
    service: LiveReplayService,
    audio_path: Path,
    out_dir: Path,
    pace: float,
    max_pacing_lag: float,
    runs: int,
    expect_revision: str,
    expect_provider_hash: str,
    expect_config_hash: str,
    monotonic=time.monotonic,
    sleep=time.sleep,
) -> ServiceReplayOutputs:
    if pace <= 0:
        raise ServiceReplayFailure("pace must be positive.")
    if max_pacing_lag < 0:
        raise ServiceReplayFailure("max_pacing_lag must be non-negative.")
    if runs <= 0:
        raise ServiceReplayFailure("runs must be positive.")

    pcm = _read_mono_pcm16_wav(audio_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "replay-manifest.json"
    audio_samples = len(pcm) // PCM16_BYTES_PER_SAMPLE
    manifest: dict[str, Any] = {
        "schema_version": REPLAY_ARTIFACT_SCHEMA_VERSION,
        "artifact_schema_versions": {
            "evaluator": REPLAY_ARTIFACT_SCHEMA_VERSION,
            "manifest": REPLAY_ARTIFACT_SCHEMA_VERSION,
            "summary": REPLAY_ARTIFACT_SCHEMA_VERSION,
            "trace": REPLAY_ARTIFACT_SCHEMA_VERSION,
        },
        "audio": {
            "path": str(audio_path),
            "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
            "sample_rate": LIVE_SAMPLE_RATE,
            "sample_count": audio_samples,
            "bytes": len(pcm),
            "duration_seconds": audio_samples / LIVE_SAMPLE_RATE,
        },
        "cli": {
            "expect_config_hash": expect_config_hash,
            "expect_provider_hash": expect_provider_hash,
            "expect_revision": expect_revision,
            "max_pacing_lag": max_pacing_lag,
            "pace": pace,
            "runs": runs,
        },
        "expected_service": {
            "combined_config_hash": expect_config_hash,
            "provider_manifest_hash": expect_provider_hash,
            "source_revision": expect_revision,
        },
        "run_artifacts": [
            {
                "run_index": index,
                "trace": f"run-{index:03d}/trace.jsonl",
                "summary": f"run-{index:03d}/summary.json",
                "evaluator": f"run-{index:03d}/evaluator.jsonl",
            }
            for index in range(1, runs + 1)
        ],
        "runs": runs,
        "pace": pace,
        "max_pacing_lag": max_pacing_lag,
        "expect_revision": expect_revision,
        "expect_provider_hash": expect_provider_hash,
        "expect_config_hash": expect_config_hash,
    }

    last_trace = out_dir / "run-001" / "trace.jsonl"
    last_summary = out_dir / "run-001" / "summary.json"
    last_evaluator = out_dir / "run-001" / "evaluator.jsonl"
    for run_index in range(1, runs + 1):
        run_dir = out_dir / f"run-{run_index:03d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        last_trace = run_dir / "trace.jsonl"
        last_summary = run_dir / "summary.json"
        last_evaluator = run_dir / "evaluator.jsonl"
        trace: list[dict[str, Any]] = []
        summary: dict[str, Any] = {
            "schema_version": REPLAY_ARTIFACT_SCHEMA_VERSION,
            "run_index": run_index,
            "status": "failed",
            "failure_kind": None,
            "frame_count": 0,
            "accepted_samples": 0,
            "accounted_samples": 0,
        }
        session_id: str | None = None
        try:
            created = service.create()
            session_id = created.session_id
            descriptor = created.descriptor
            if run_index == 1:
                manifest["descriptor"] = descriptor.to_dict()
                manifest["frame_samples"] = descriptor.frame_samples
                manifest["frame_count"] = _frame_count(audio_samples, descriptor.frame_samples)
                _write_json(manifest_path, manifest)
            _validate_descriptor(
                descriptor,
                expect_revision=expect_revision,
                expect_provider_hash=expect_provider_hash,
                expect_config_hash=expect_config_hash,
            )

            trace.append(
                {
                    "schema_version": REPLAY_ARTIFACT_SCHEMA_VERSION,
                    "seq": len(trace),
                    "kind": "session_created",
                    "session_id": session_id,
                    "snapshot_version": created.snapshot.session.version,
                }
            )
            start_time = float(monotonic())
            offset = 0
            sequence = 0
            while offset < audio_samples:
                sample_count = min(descriptor.frame_samples, audio_samples - offset)
                scheduled = start_time + (offset / (LIVE_SAMPLE_RATE * pace))
                now = float(monotonic())
                if now < scheduled:
                    sleep(scheduled - now)
                    now = float(monotonic())
                lag = now - scheduled
                if lag > max_pacing_lag:
                    raise ServiceReplayTransportFailure(
                        f"pacing lag {lag:.6f}s exceeded bound {max_pacing_lag:.6f}s."
                    )
                byte_start = offset * PCM16_BYTES_PER_SAMPLE
                byte_end = byte_start + sample_count * PCM16_BYTES_PER_SAMPLE
                result = service.accept_frame(
                    session_id,
                    AudioFrame(
                        sequence=sequence,
                        pcm=pcm[byte_start:byte_end],
                        sample_count=sample_count,
                    ),
                )
                if result.ack.sequence != sequence or result.ack.start_sample != offset:
                    raise ServiceReplayTransportFailure("service acknowledged an unexpected frame sequence or offset.")
                trace.append(
                    {
                        "schema_version": REPLAY_ARTIFACT_SCHEMA_VERSION,
                        "seq": len(trace),
                        "kind": "frame_accepted",
                        "frame_sequence": sequence,
                        "scheduled_sample": offset,
                        "sample_count": sample_count,
                        "observed_monotonic_offset": now - start_time,
                        "pacing_lag": lag,
                        "ack": _jsonable(result.ack),
                        "queued_item_ids": list(result.queued_item_ids),
                    }
                )
                offset += sample_count
                sequence += 1

            snapshot = asyncio.run(service.stop(session_id, deadline=5.0))
            for event in service.events(session_id, since_seq=0):
                trace.append(
                    {
                        "schema_version": REPLAY_ARTIFACT_SCHEMA_VERSION,
                        "seq": len(trace),
                        "kind": "service_event",
                        "event": event.to_dict(),
                    }
                )
            summary.update(
                {
                    "status": "succeeded",
                    "frame_count": sequence,
                    "accepted_samples": snapshot.session.accepted_samples,
                    "accounted_samples": snapshot.session.accounted_samples,
                    "committed_prefix_hash": snapshot.session.committed_prefix_hash,
                }
            )
            trace.append(
                {
                    "schema_version": REPLAY_ARTIFACT_SCHEMA_VERSION,
                    "seq": len(trace),
                    "kind": "terminal",
                    "status": "succeeded",
                    "snapshot": snapshot.to_dict(),
                }
            )
        except ServiceReplayFailure as exc:
            summary["failure_kind"] = exc.failure_kind
            trace.append(
                {
                    "schema_version": REPLAY_ARTIFACT_SCHEMA_VERSION,
                    "seq": len(trace),
                    "kind": "terminal",
                    "status": "failed",
                    "failure_kind": exc.failure_kind,
                    "message": str(exc),
                }
            )
            abort_snapshot = _abort_after_failure(service, session_id, str(exc))
            if abort_snapshot is not None:
                trace[-1]["snapshot"] = abort_snapshot.to_dict()
            _write_run_artifacts(last_trace, last_summary, last_evaluator, trace, summary)
            if not manifest_path.exists():
                _write_json(manifest_path, manifest)
            raise
        except LiveServiceError as exc:
            replay_exc = _replay_failure_from_service(exc.failure)
            summary["failure_kind"] = replay_exc.failure_kind
            trace.append(
                {
                    "schema_version": REPLAY_ARTIFACT_SCHEMA_VERSION,
                    "seq": len(trace),
                    "kind": "terminal",
                    "status": "failed",
                    "failure_kind": replay_exc.failure_kind,
                    "service_failure": exc.failure.to_dict(),
                }
            )
            abort_snapshot = _abort_after_failure(service, session_id, exc.failure.message)
            if abort_snapshot is not None:
                trace[-1]["snapshot"] = abort_snapshot.to_dict()
            _write_run_artifacts(last_trace, last_summary, last_evaluator, trace, summary)
            if not manifest_path.exists():
                _write_json(manifest_path, manifest)
            raise replay_exc from exc
        _write_run_artifacts(last_trace, last_summary, last_evaluator, trace, summary)

    if not manifest_path.exists():
        _write_json(manifest_path, manifest)
    return ServiceReplayOutputs(
        manifest_path=manifest_path,
        trace_path=last_trace,
        summary_path=last_summary,
        evaluator_path=last_evaluator,
    )


def _exit_code_for_service_failure(kind: LiveServiceFailureKind) -> int:
    if kind == LiveServiceFailureKind.PROVIDER_CONFIG:
        return ServiceReplayProviderConfigFailure.exit_code
    if kind == LiveServiceFailureKind.IDENTITY_COMMIT:
        return ServiceReplayIdentityCommitFailure.exit_code
    if kind == LiveServiceFailureKind.RTF:
        return ServiceReplayRtfFailure.exit_code
    if kind == LiveServiceFailureKind.TRANSPORT_PACING:
        return ServiceReplayTransportFailure.exit_code
    return ServiceReplayFailure.exit_code


def _read_mono_pcm16_wav(path: Path) -> bytes:
    try:
        with wave.open(str(path), "rb") as wav:
            if wav.getnchannels() != 1:
                raise ServiceReplayFailure("audio must be mono.")
            if wav.getframerate() != LIVE_SAMPLE_RATE:
                raise ServiceReplayFailure(f"audio must be {LIVE_SAMPLE_RATE} Hz.")
            if wav.getsampwidth() != PCM16_BYTES_PER_SAMPLE:
                raise ServiceReplayFailure("audio must be PCM16.")
            return wav.readframes(wav.getnframes())
    except wave.Error as exc:
        raise ServiceReplayFailure(f"audio must be a readable WAV file: {exc}") from exc


def _validate_descriptor(
    descriptor: LiveServiceDescriptor,
    *,
    expect_revision: str,
    expect_provider_hash: str,
    expect_config_hash: str,
) -> None:
    if descriptor.source_revision != expect_revision:
        raise ServiceReplayProviderConfigFailure("service source revision mismatch.")
    if descriptor.provider_manifest_hash != expect_provider_hash:
        raise ServiceReplayProviderConfigFailure("service provider manifest hash mismatch.")
    if descriptor.config_hashes.combined_config_hash != expect_config_hash:
        raise ServiceReplayProviderConfigFailure("service configuration hash mismatch.")


def _frame_count(sample_count: int, frame_samples: int) -> int:
    return (sample_count + frame_samples - 1) // frame_samples if sample_count else 0


def _abort_after_failure(
    service: LiveReplayService,
    session_id: str | None,
    reason: str,
) -> LiveServiceSnapshot | None:
    if session_id is None:
        return None
    try:
        return asyncio.run(service.abort(session_id, reason))
    except Exception:
        return None


def _write_run_artifacts(
    trace_path: Path,
    summary_path: Path,
    evaluator_path: Path,
    trace: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    summary = _summary_from_trace(trace, summary)
    trace_path.write_text(
        "".join(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n" for item in trace),
        encoding="utf-8",
    )
    _write_json(summary_path, summary)
    evaluator_path.write_text(
        "".join(
            json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n"
            for item in _evaluator_records_from_summary(summary)
        ),
        encoding="utf-8",
    )


def _summary_from_trace(trace: list[dict[str, Any]], seed: dict[str, Any]) -> dict[str, Any]:
    summary = dict(seed)
    frame_events = [item for item in trace if item.get("kind") == "frame_accepted"]
    terminal = next((item for item in reversed(trace) if item.get("kind") == "terminal"), None)
    terminal_snapshot = terminal.get("snapshot") if isinstance(terminal, dict) else None
    session_snapshot = terminal_snapshot.get("session") if isinstance(terminal_snapshot, dict) else None

    accepted_samples = summary.get("accepted_samples", 0)
    if frame_events:
        accepted_samples = int(frame_events[-1]["ack"]["accepted_samples"])
    if isinstance(session_snapshot, dict):
        accepted_samples = int(session_snapshot["accepted_samples"])

    accounted_samples = summary.get("accounted_samples", 0)
    committed_prefix_hash = summary.get("committed_prefix_hash")
    if isinstance(session_snapshot, dict):
        accounted_samples = int(session_snapshot["accounted_samples"])
        committed_prefix_hash = str(session_snapshot["committed_prefix_hash"])

    summary.update(
        {
            "trace_schema_version": REPLAY_ARTIFACT_SCHEMA_VERSION,
            "trace_event_count": len(trace),
            "terminal_seq": None if terminal is None else int(terminal["seq"]),
            "status": summary["status"] if terminal is None else str(terminal["status"]),
            "failure_kind": None if terminal is None else terminal.get("failure_kind"),
            "frame_count": len(frame_events),
            "scheduled_sample_offsets": [int(item["scheduled_sample"]) for item in frame_events],
            "accepted_samples": accepted_samples,
            "accounted_samples": accounted_samples,
            "exact_accounting": accepted_samples == accounted_samples,
        }
    )
    if committed_prefix_hash is not None:
        summary["committed_prefix_hash"] = committed_prefix_hash
    return summary


def _evaluator_records_from_summary(summary: dict[str, Any]) -> list[dict[str, Any]]:
    base = {
        "schema_version": REPLAY_ARTIFACT_SCHEMA_VERSION,
        "run_index": summary["run_index"],
    }
    return [
        {
            **base,
            "kind": "terminal_outcome",
            "status": summary["status"],
            "failure_kind": summary["failure_kind"],
            "terminal_seq": summary["terminal_seq"],
        },
        {
            **base,
            "kind": "frame_sequence",
            "frame_count": summary["frame_count"],
            "scheduled_sample_offsets": summary["scheduled_sample_offsets"],
        },
        {
            **base,
            "kind": "sample_accounting",
            "accepted_samples": summary["accepted_samples"],
            "accounted_samples": summary["accounted_samples"],
            "exact_accounting": summary["exact_accounting"],
            "committed_prefix_hash": summary.get("committed_prefix_hash"),
        },
    ]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json_bytes(data: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ServiceReplayTransportFailure("HTTP live replay returned non-JSON data.") from exc
    if not isinstance(payload, dict):
        raise ServiceReplayTransportFailure("HTTP live replay returned a non-object envelope.")
    return payload


def _replay_failure_from_service(failure: LiveServiceFailureRecord) -> ServiceReplayFailure:
    if failure.kind == LiveServiceFailureKind.PROVIDER_CONFIG:
        return ServiceReplayProviderConfigFailure(failure.message)
    if failure.kind == LiveServiceFailureKind.IDENTITY_COMMIT:
        return ServiceReplayIdentityCommitFailure(failure.message)
    if failure.kind == LiveServiceFailureKind.RTF:
        return ServiceReplayRtfFailure(failure.message)
    if failure.kind == LiveServiceFailureKind.TRANSPORT_PACING:
        return ServiceReplayTransportFailure(failure.message)
    return ServiceReplayFailure(failure.message)


def _descriptor_from_dict(payload: dict[str, Any]) -> LiveServiceDescriptor:
    return LiveServiceDescriptor(
        source_revision=str(payload["source_revision"]),
        provider_name=str(payload["provider_name"]),
        provider_revision=str(payload["provider_revision"]),
        provider_manifest_hash=str(payload["provider_manifest_hash"]),
        config_hashes=LiveServiceConfigHashes(**payload["config_hashes"]),
        bounds=LiveServiceBounds(**payload["bounds"]),
        schema_version=int(payload.get("schema_version", 1)),
        live_protocol_version=str(payload.get("live_protocol_version", "moss-live-service.v1")),
        sample_rate=int(payload.get("sample_rate", LIVE_SAMPLE_RATE)),
        frame_samples=int(payload.get("frame_samples", LIVE_SAMPLE_RATE)),
        feature_enabled=bool(payload.get("feature_enabled", True)),
    )


def _failure_from_dict(payload: dict[str, Any]) -> LiveServiceFailureRecord:
    return LiveServiceFailureRecord(
        kind=LiveServiceFailureKind(payload["kind"]),
        code=str(payload["code"]),
        message=str(payload["message"]),
        retryable=bool(payload.get("retryable", False)),
        detail=payload.get("detail"),
    )


def _event_from_dict(payload: dict[str, Any]) -> LiveServiceEvent:
    return LiveServiceEvent(
        seq=int(payload["seq"]),
        session_id=str(payload["session_id"]),
        kind=str(payload["kind"]),
        snapshot_version=int(payload["snapshot_version"]),
        payload=payload.get("payload") or {},
        schema_version=int(payload.get("schema_version", 1)),
    )


def _snapshot_from_dict(payload: dict[str, Any]) -> LiveServiceSnapshot:
    return LiveServiceSnapshot(
        session_id=str(payload["session_id"]),
        descriptor=_descriptor_from_dict(payload["descriptor"]),
        session=_live_snapshot_from_dict(payload["session"]),
        pending_work_items=int(payload["pending_work_items"]),
        terminal_failure=None if payload.get("terminal_failure") is None else _failure_from_dict(payload["terminal_failure"]),
        schema_version=int(payload.get("schema_version", 1)),
    )


def _live_snapshot_from_dict(payload: dict[str, Any]) -> LiveSnapshot:
    provisional = payload.get("provisional")
    return LiveSnapshot(
        status=str(payload["status"]),
        epoch=int(payload["epoch"]),
        version=int(payload["version"]),
        accepted_samples=int(payload["accepted_samples"]),
        accounted_samples=int(payload["accounted_samples"]),
        retained_samples=int(payload["retained_samples"]),
        committed_samples=int(payload["committed_samples"]),
        committed_prefix_hash=str(payload["committed_prefix_hash"]),
        identity_snapshot=_identity_snapshot_from_dict(payload["identity_snapshot"]),
        committed=tuple(_commit_from_dict(item) for item in payload.get("committed", ())),
        provisional=None if provisional is None else ProvisionalSuffix(**provisional),
        next_frame_sequence=int(payload["next_frame_sequence"]),
        frozen_until_sample=int(payload["frozen_until_sample"]),
        pending_span_ids=tuple(int(item) for item in payload.get("pending_span_ids", ())),
        failure_reason=payload.get("failure_reason"),
    )


def _identity_snapshot_from_dict(payload: dict[str, Any]) -> LiveIdentitySnapshot:
    return LiveIdentitySnapshot(
        version=int(payload.get("version", 0)),
        canonical_speakers=tuple(str(item) for item in payload.get("canonical_speakers", ())),
        diagnostics=tuple((str(left), str(right)) for left, right in payload.get("diagnostics", ())),
    )


def _commit_from_dict(payload: dict[str, Any]) -> CanonicalCommit:
    return CanonicalCommit(
        span_id=int(payload["span_id"]),
        start_sample=int(payload["start_sample"]),
        end_sample=int(payload["end_sample"]),
        transcript=str(payload["transcript"]),
        prefix_hash=str(payload["prefix_hash"]),
        identity_snapshot_version=int(payload["identity_snapshot_version"]),
    )


def _frame_ack_from_dict(payload: dict[str, Any]) -> FrameAck:
    return FrameAck(
        sequence=int(payload["sequence"]),
        start_sample=int(payload["start_sample"]),
        end_sample=int(payload["end_sample"]),
        accepted_samples=int(payload["accepted_samples"]),
        retained_samples=int(payload["retained_samples"]),
        frozen_span_ids=tuple(int(item) for item in payload.get("frozen_span_ids", ())),
    )


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dataclass_fields__"):
        return {field: _jsonable(getattr(value, field)) for field in value.__dataclass_fields__}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


if __name__ == "__main__":
    raise SystemExit(main())
