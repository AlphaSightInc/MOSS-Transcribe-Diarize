from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
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
    LiveDraft,
)
from .app.live_lane_contract import LiveV2Descriptor
from .app.live_session import (
    AudioFrame,
    CanonicalCommit,
    EffectiveTranscriptSegment,
    FrameAck,
    LIVE_SAMPLE_RATE,
    LiveIdentitySnapshot,
    LiveSnapshot,
    PCM16_BYTES_PER_SAMPLE,
    ProvisionalSuffix,
)


REPLAY_ARTIFACT_SCHEMA_VERSION = 1
CANONICAL_DECODE_RTF_BOUND = 1.0

#: How long this client waits for a terminal pass it watched start, and how often it asks.
#:
#: Plan §12.3 puts the whole-meeting decode deliberately *behind* the stop response, so a
#: client that returns when `POST /stop` answers writes the **rolling** surface into its
#: artifacts and every paired comparison built on them scores the wrong transcript. The
#: waiting therefore belongs here, in the one client all the measurement drivers share,
#: rather than in a synchronous stop (which §12.3 M2 refuses: minutes of decode on a request
#: a browser holds open).
#:
#: The deadline is the instrument's patience, not the service's contract, which is why it is
#: generous: a terminal pass decodes the meeting through the same 150/120 `WindowedRunner`
#: file mode uses -- three windows for the longest audio this repo measures -- and the
#: measured whole-meeting decode of a 60-second meeting is ~2 s.
TERMINAL_FINALIZATION_DEADLINE_SECONDS = 300.0
TERMINAL_FINALIZATION_POLL_SECONDS = 0.5

#: The finalization statuses that are already an answer (plan §7.3). `running` is the only
#: one worth waiting on: `not_started` is a deployment that asked for no terminal pass,
#: `final` is one that landed, and `failed` / `unavailable` are passes that ended without a
#: surface. A client that waited on any of these four would wait for the deadline every time.
TERMINAL_FINALIZATION_SETTLED = frozenset(
    {"not_started", "final", "failed", "unavailable"}
)


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


class ServiceReplayEventLossFailure(ServiceReplayFailure):
    exit_code = 7
    failure_kind = "event_loss"


class ServiceReplayFinalizationTimeout(ServiceReplayFailure):
    """A terminal pass this client watched start had not ended within its deadline.

    Typed, and fatal to the run, on purpose. The alternative -- write the artifacts anyway
    and note the timeout in them -- is exactly the trap this wait exists to close: the
    surface in `trace.jsonl` would be the rolling one while every filename around it says
    the run completed, and a scorer would have to know to look. A run that could not see the
    terminal surface produced no terminal measurement, so it fails by name.
    """

    exit_code = 8
    failure_kind = "finalization_timeout"


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


def _drain_service_events(
    service: LiveReplayService,
    session_id: str,
    next_seq: int,
    sink: list[LiveServiceEvent],
) -> int:
    """Append every event published since `next_seq` and return the new cursor.

    The runtime holds events in a `deque(maxlen=bounds.max_events)`, so a client that
    waits until the session ends and then reads `since_seq=0` loses the oldest events of
    any session that emits more than the bound -- silently, because a truncated stream is
    still a well-formed one.  Every 5-minute trace this repo had was missing its first
    ~30 s for exactly that reason.  Draining once per accepted frame keeps the cursor
    inside the retention window regardless of how long the session runs, and a first
    returned sequence past the cursor is the one observable proof that it did not: the
    gap is raised rather than written into the artifact.
    """

    for event in service.events(session_id, since_seq=next_seq):
        if event.seq != next_seq:
            raise ServiceReplayEventLossFailure(
                f"service event sequence {next_seq} is unreadable (next available is "
                f"{event.seq}); the event stream was evicted before the replay client "
                f"read it and the trace would be incomplete."
            )
        sink.append(event)
        next_seq += 1
    return next_seq


def _await_terminal_finalization(
    service: LiveReplayService,
    session_id: str,
    *,
    stop_snapshot: LiveServiceSnapshot,
    next_event_seq: int,
    sink: list[LiveServiceEvent],
    deadline_seconds: float,
    poll_seconds: float,
    monotonic,
    sleep,
) -> tuple[LiveServiceSnapshot, int, dict[str, Any]]:
    """Hold the run open until the meeting's last listener has answered.

    The stop response already says which of the two meetings this is: `_begin_terminal_locked`
    publishes `running` under the same lock that builds that snapshot, so a `running` stop
    response means a pass was scheduled and this client has not yet seen its surface, and any
    other status means there is nothing to come back for. Nothing here asks the service to
    behave differently -- the wait is one reader polling a contract that already exists.

    Draining events on every poll rather than once at the end is `_drain_service_events`'s
    argument applied to the new interval: the terminal decode is minutes long on the longest
    audio this repo measures, the runtime holds events in a bounded deque, and a client that
    slept through the interval and then read from its old cursor would be told the stream had
    moved on. Polls also keep the *snapshot* fresh, which is what the trace ultimately carries.

    Returns the snapshot the run should report, the advanced event cursor, and the record of
    what the wait did -- including the deadline it was given, so an artifact reader can tell a
    pass that was quick from one that merely fit.
    """

    started = float(monotonic())
    snapshot = stop_snapshot
    status = snapshot.session.finalization_status
    polls = 0
    while status not in TERMINAL_FINALIZATION_SETTLED:
        elapsed = float(monotonic()) - started
        if elapsed >= deadline_seconds:
            raise ServiceReplayFinalizationTimeout(
                f"terminal finalization was still {status!r} after {elapsed:.3f}s "
                f"(deadline {deadline_seconds:.3f}s); the run observed the rolling surface "
                f"only and has no terminal measurement to report."
            )
        sleep(poll_seconds)
        next_event_seq = _drain_service_events(service, session_id, next_event_seq, sink)
        polled = service.snapshot(session_id)
        polls += 1
        if polled is None:
            raise ServiceReplayFailure(
                "the service stopped answering for a session whose terminal finalization "
                "was still running; the terminal surface is unobservable."
            )
        snapshot = polled
        status = snapshot.session.finalization_status
    next_event_seq = _drain_service_events(service, session_id, next_event_seq, sink)
    return (
        snapshot,
        next_event_seq,
        {
            "stop_finalization_status": stop_snapshot.session.finalization_status,
            "finalization_status": status,
            "waited": polls > 0,
            "polls": polls,
            "elapsed_seconds": round(float(monotonic()) - started, 6),
            "deadline_seconds": deadline_seconds,
            "poll_seconds": poll_seconds,
            "text_revision_version": snapshot.session.text_revision_version,
        },
    )


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
    finalization_deadline: float = TERMINAL_FINALIZATION_DEADLINE_SECONDS,
    monotonic=time.monotonic,
    sleep=time.sleep,
) -> ServiceReplayOutputs:
    if pace <= 0:
        raise ServiceReplayFailure("pace must be positive.")
    if max_pacing_lag < 0:
        raise ServiceReplayFailure("max_pacing_lag must be non-negative.")
    if runs <= 0:
        raise ServiceReplayFailure("runs must be positive.")
    if finalization_deadline <= 0:
        raise ServiceReplayFailure("finalization_deadline must be positive.")

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
            "finalization_deadline": finalization_deadline,
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
            service_event_log: list[LiveServiceEvent] = []
            next_event_seq = _drain_service_events(service, session_id, 0, service_event_log)
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
                next_event_seq = _drain_service_events(
                    service, session_id, next_event_seq, service_event_log
                )

            stop_snapshot = asyncio.run(service.stop(session_id, deadline=5.0))
            next_event_seq = _drain_service_events(
                service, session_id, next_event_seq, service_event_log
            )
            snapshot, next_event_seq, finalization_wait = _await_terminal_finalization(
                service,
                session_id,
                stop_snapshot=stop_snapshot,
                next_event_seq=next_event_seq,
                sink=service_event_log,
                deadline_seconds=finalization_deadline,
                poll_seconds=TERMINAL_FINALIZATION_POLL_SECONDS,
                monotonic=monotonic,
                sleep=sleep,
            )
            service_events = tuple(service_event_log)
            for event in service_events:
                trace.append(
                    {
                        "schema_version": REPLAY_ARTIFACT_SCHEMA_VERSION,
                        "seq": len(trace),
                        "kind": "service_event",
                        "event": event.to_dict(),
                    }
                )
            trace.append(
                {
                    "schema_version": REPLAY_ARTIFACT_SCHEMA_VERSION,
                    "seq": len(trace),
                    "kind": "terminal_finalization_wait",
                    **finalization_wait,
                }
            )
            rtf_evaluation = _canonical_decode_rtf_evaluation(service_events)
            summary.update(rtf_evaluation)
            trace.append(
                {
                    "schema_version": REPLAY_ARTIFACT_SCHEMA_VERSION,
                    "seq": len(trace),
                    "kind": "canonical_decode_rtf_evaluation",
                    **rtf_evaluation,
                }
            )
            if not rtf_evaluation["canonical_decode_rtf_passed"]:
                if rtf_evaluation["canonical_decode_rtf_invalid_count"]:
                    raise ServiceReplayRtfFailure("canonical decoder RTF event payload invalid.")
                p95 = rtf_evaluation["canonical_decode_rtf_p95"]
                raise ServiceReplayRtfFailure(
                    f"canonical decoder p95 RTF {p95:.6g} exceeded strict bound "
                    f"{rtf_evaluation['canonical_decode_rtf_bound']:.6g}."
                )
            summary.update(
                {
                    "status": "succeeded",
                    "frame_count": sequence,
                    "accepted_samples": snapshot.session.accepted_samples,
                    "accounted_samples": snapshot.session.accounted_samples,
                    "committed_prefix_hash": snapshot.session.committed_prefix_hash,
                    # Which surface the artifacts beside this file carry. A scorer that reads
                    # `final` is reading a terminal transcript; anything else and the run's
                    # live arm is the rolling one, by the service's own word rather than by
                    # the scorer's assumption.
                    "finalization_status": finalization_wait["finalization_status"],
                    "finalization_waited": finalization_wait["waited"],
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


def _canonical_decode_rtf_evaluation(events: tuple[LiveServiceEvent, ...]) -> dict[str, Any]:
    measurements: list[dict[str, Any]] = []
    invalid_measurements: list[dict[str, Any]] = []
    declared_unknown_measurements: list[dict[str, Any]] = []
    for event in events:
        if event.kind != "canonical_processed":
            continue
        payload = dict(event.payload)
        try:
            common = {
                "event_seq": event.seq,
                "span_id": _required_int(payload, "span_id"),
                "frozen_span_sample_count": _required_positive_int(payload, "frozen_span_sample_count"),
                "frozen_span_duration_sec": _required_positive_finite_float(payload, "frozen_span_duration_sec"),
            }
            if (
                "canonical_decode_elapsed_sec" in payload
                and "canonical_decode_rtf" in payload
                and payload["canonical_decode_elapsed_sec"] is None
                and payload["canonical_decode_rtf"] is None
            ):
                declared_unknown_measurements.append(
                    {
                        **common,
                        "canonical_decode_elapsed_sec": None,
                        "canonical_decode_rtf": None,
                    }
                )
                continue
            measurement = {
                **common,
                "canonical_decode_elapsed_sec": _required_finite_non_negative_float(
                    payload, "canonical_decode_elapsed_sec"
                ),
                "canonical_decode_rtf": _required_finite_non_negative_float(payload, "canonical_decode_rtf"),
            }
        except ServiceReplayRtfFailure as exc:
            invalid_measurements.append(_invalid_canonical_decode_rtf_measurement(event, payload, str(exc)))
            continue
        measurements.append(measurement)

    values = [item["canonical_decode_rtf"] for item in measurements]
    p95 = _nearest_rank_p95(values) if values else None
    return {
        "canonical_decode_rtf_values": values,
        "canonical_decode_rtf_measurements": measurements,
        "canonical_decode_rtf_span_ids": [item["span_id"] for item in measurements],
        "canonical_decode_rtf_p95": p95,
        "canonical_decode_rtf_bound": CANONICAL_DECODE_RTF_BOUND,
        "canonical_decode_rtf_invalid_measurements": invalid_measurements,
        "canonical_decode_rtf_invalid_count": len(invalid_measurements),
        "canonical_decode_rtf_declared_unknown_measurements": declared_unknown_measurements,
        "canonical_decode_rtf_declared_unknown_count": len(declared_unknown_measurements),
        "canonical_decode_rtf_passed": not invalid_measurements and (p95 is None or p95 < CANONICAL_DECODE_RTF_BOUND),
    }


def _nearest_rank_p95(values: list[float]) -> float:
    if not values:
        raise ValueError("nearest-rank p95 requires at least one value.")
    rank = math.ceil(0.95 * len(values)) - 1
    return sorted(values)[rank]


def _required_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ServiceReplayRtfFailure(f"canonical decoder RTF event field {key} must be an integer.")
    return value


def _required_positive_int(payload: dict[str, Any], key: str) -> int:
    value = _required_int(payload, key)
    if value <= 0:
        raise ServiceReplayRtfFailure(f"canonical decoder RTF event field {key} must be positive.")
    return value


def _invalid_canonical_decode_rtf_measurement(
    event: LiveServiceEvent,
    payload: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    span_id = payload.get("span_id")
    if isinstance(span_id, bool) or not isinstance(span_id, int):
        span_id = None
    return {
        "event_seq": event.seq,
        "span_id": span_id,
        "message": message,
        "payload_fields": sorted(str(key) for key in payload),
    }


def _required_finite_non_negative_float(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ServiceReplayRtfFailure(f"canonical decoder RTF event field {key} must be finite and non-negative.")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ServiceReplayRtfFailure(f"canonical decoder RTF event field {key} must be finite and non-negative.")
    return value


def _required_positive_finite_float(payload: dict[str, Any], key: str) -> float:
    value = _required_finite_non_negative_float(payload, key)
    if value <= 0:
        raise ServiceReplayRtfFailure(f"canonical decoder RTF event field {key} must be positive.")
    return value


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
        {
            **base,
            "kind": "canonical_decode_rtf",
            "values": summary.get("canonical_decode_rtf_values", []),
            "measurements": summary.get("canonical_decode_rtf_measurements", []),
            "span_ids": summary.get("canonical_decode_rtf_span_ids", []),
            "p95": summary.get("canonical_decode_rtf_p95"),
            "bound": summary.get("canonical_decode_rtf_bound", CANONICAL_DECODE_RTF_BOUND),
            "passed": summary.get("canonical_decode_rtf_passed"),
            "invalid_measurements": summary.get("canonical_decode_rtf_invalid_measurements", []),
            "invalid_count": summary.get("canonical_decode_rtf_invalid_count", 0),
            "declared_unknown_measurements": summary.get(
                "canonical_decode_rtf_declared_unknown_measurements", []
            ),
            "declared_unknown_count": summary.get("canonical_decode_rtf_declared_unknown_count", 0),
        },
    ]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
        live_protocol=_live_protocol_from_dict(payload.get("live_protocol")),
        sample_rate=int(payload.get("sample_rate", LIVE_SAMPLE_RATE)),
        frame_samples=int(payload.get("frame_samples", LIVE_SAMPLE_RATE)),
        feature_enabled=bool(payload.get("feature_enabled", True)),
    )


def _live_protocol_from_dict(payload: Any) -> LiveV2Descriptor:
    return LiveV2Descriptor() if payload is None else LiveV2Descriptor.from_dict(payload)


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


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
        draft=LiveDraft(**payload["draft"]) if payload.get("draft") is not None else None,
        draft_stats=payload.get("draft_stats"),
        identity_counts=payload.get("identity_counts"),
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
        label_revision_version=int(payload.get("label_revision_version", 0)),
        text_revision_version=int(payload.get("text_revision_version", 0)),
        canonical_through_sample=int(payload.get("canonical_through_sample", 0)),
        effective_transcript=tuple(
            _effective_segment_from_dict(item) for item in payload.get("effective_transcript", ())
        ),
        finalization_status=str(payload.get("finalization_status", "not_started")),
    )


def _effective_segment_from_dict(payload: dict[str, Any]) -> EffectiveTranscriptSegment:
    return EffectiveTranscriptSegment(
        start_sample=int(payload["start_sample"]),
        end_sample=int(payload["end_sample"]),
        text=str(payload["text"]),
        canonical_speaker=_optional_str(payload.get("canonical_speaker")),
        authority=str(payload["authority"]),
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
        revised_transcript=_optional_str(payload.get("revised_transcript")),
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
