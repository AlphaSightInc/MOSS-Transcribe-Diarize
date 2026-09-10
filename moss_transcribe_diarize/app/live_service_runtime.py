from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from typing import Any, Awaitable, Callable, Mapping, Protocol, Sequence

from .live_adapters import LiveProviderError
from .live_arbiter import InferenceArbiter, InferenceArbiterBackpressure
from .live_coordinator import (
    CoordinatorRefinementResult,
    LiveCoordinator,
    LiveCoordinatorError,
    LiveIdentityPreparer,
    RollingWindowPlan,
    SpeechSignalProvider,
)
from .live_endpoint import EndpointPolicy, EndpointPolicyError
from .live_lane_contract import LiveV2Descriptor
from .live_span_bounds import LiveTranscriptDisposition
from .live_transcript_convergence import (
    TerminalDecodePlan,
    TerminalFinalization,
    TerminalOutcome,
)
from .live_session import (
    AudioFrame,
    FrameAck,
    LIVE_SAMPLE_RATE,
    LiveSession,
    LiveSessionBackpressure,
    LiveSessionClosed,
    LiveSessionFailed,
    LiveSnapshot,
)
LIVE_SERVICE_SCHEMA_VERSION = 1
LIVE_PROTOCOL_VERSION = "moss-live-service.v1"
_ROLLING_LOG = logging.getLogger("moss_transcribe_diarize.live.rolling")
_TERMINAL_LOG = logging.getLogger("moss_transcribe_diarize.live.terminal")

# The one disposition that means words the grammar rejected were published anyway. Read from
# the enum rather than spelled again here: a second spelling of a policy name is how a gate
# silently stops matching what the policy decides (`HARD_CAP_REASON` learned this in M1).
SALVAGED_DISPOSITION = LiveTranscriptDisposition.SALVAGED.value

# THE TERMINAL CONTRACT, in one place so it can be tested rather than remembered.
#
# `LiveServiceSnapshot.session.status` is the single field a client has to read to know a
# meeting is over. A client that stops polling on exactly these values -- and on nothing
# else -- stops on every way a live session can end: a clean stop, an explicit abort, the
# session's own failure, and the runtime terminal failures (provider error, helper lease
# expiry, stop-deadline overrun) that the session object itself is never told about.
# `snapshot.terminal_failure` says *why*; it is detail, not the signal to stop.
#
# Two things make that true and both are load-bearing: `_snapshot` projects a runtime
# terminal failure onto `status`, and `snapshot(since_version=...)` refuses to suppress a
# terminal snapshot as "unchanged" -- terminality does not move the version counter, so a
# gate that hid it would leave a caught-up reader polling a dead session forever.
LIVE_TERMINAL_SESSION_STATUSES = frozenset({"closed", "aborted", "failed"})


class LiveServiceFailureKind(str, Enum):
    INTEGRITY = "integrity"
    PROVIDER_CONFIG = "provider_config"
    IDENTITY_COMMIT = "identity_commit"
    RTF = "rtf"
    TRANSPORT_PACING = "transport_pacing"


@dataclass(frozen=True, slots=True)
class LiveServiceFailureRecord:
    kind: LiveServiceFailureKind
    code: str
    message: str
    retryable: bool = False
    detail: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("failure code must be non-empty.")
        if not self.message:
            raise ValueError("failure message must be non-empty.")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        payload["detail"] = None if self.detail is None else dict(self.detail)
        return payload


class LiveServiceError(RuntimeError):
    failure_kind = LiveServiceFailureKind.INTEGRITY

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        retryable: bool = False,
        detail: Mapping[str, Any] | None = None,
    ):
        super().__init__(message)
        self.failure = LiveServiceFailureRecord(
            kind=self.failure_kind,
            code=code or self.failure_kind.value,
            message=message,
            retryable=retryable,
            detail=detail,
        )


class LiveServiceIntegrityFailure(LiveServiceError):
    failure_kind = LiveServiceFailureKind.INTEGRITY


class LiveServiceProviderConfigFailure(LiveServiceError):
    failure_kind = LiveServiceFailureKind.PROVIDER_CONFIG


class LiveServiceIdentityCommitFailure(LiveServiceError):
    failure_kind = LiveServiceFailureKind.IDENTITY_COMMIT


class LiveServiceRtfFailure(LiveServiceError):
    failure_kind = LiveServiceFailureKind.RTF


class LiveServiceTransportPacingFailure(LiveServiceError):
    failure_kind = LiveServiceFailureKind.TRANSPORT_PACING


@dataclass(frozen=True, slots=True)
class LiveServiceBounds:
    max_frame_samples: int
    max_queue_depth: int
    max_retained_samples: int
    max_identity_speakers: int
    max_events: int
    hard_cap_samples: int | None = None
    stop_drain_deadline_seconds: float | None = None
    #: How many bytes of the meeting's mixed audio a session may retain so that a terminal
    #: convergence pass has something to run over (ADR-0003 D5 in memory). `None` -- the
    #: default -- is the opt-in posture of D2: no tape, and terminal convergence reports
    #: itself unavailable rather than running over a partial meeting.
    max_tape_bytes: int | None = None

    def __post_init__(self) -> None:
        _positive(self.max_frame_samples, "max_frame_samples")
        _positive(self.max_queue_depth, "max_queue_depth")
        _positive(self.max_retained_samples, "max_retained_samples")
        _positive(self.max_identity_speakers, "max_identity_speakers")
        _positive(self.max_events, "max_events")
        if self.hard_cap_samples is not None:
            _positive(self.hard_cap_samples, "hard_cap_samples")
        if self.max_tape_bytes is not None:
            _positive(self.max_tape_bytes, "max_tape_bytes")
        if self.stop_drain_deadline_seconds is not None and self.stop_drain_deadline_seconds < 0:
            raise ValueError("stop_drain_deadline_seconds must be non-negative when provided.")


@dataclass(frozen=True, slots=True)
class LiveServiceConfigHashes:
    endpoint_config_hash: str
    identity_config_hash: str
    decoder_config_hash: str
    combined_config_hash: str

    @classmethod
    def from_parts(
        cls,
        *,
        endpoint_config: Mapping[str, Any],
        identity_config: Mapping[str, Any],
        decoder_config: Mapping[str, Any],
    ) -> "LiveServiceConfigHashes":
        endpoint_hash = hash_config(endpoint_config)
        identity_hash = hash_config(identity_config)
        decoder_hash = hash_config(decoder_config)
        return cls(
            endpoint_config_hash=endpoint_hash,
            identity_config_hash=identity_hash,
            decoder_config_hash=decoder_hash,
            combined_config_hash=hash_config(
                {
                    "decoder": decoder_hash,
                    "endpoint": endpoint_hash,
                    "identity": identity_hash,
                }
            ),
        )

    def __post_init__(self) -> None:
        for name, value in (
            ("endpoint_config_hash", self.endpoint_config_hash),
            ("identity_config_hash", self.identity_config_hash),
            ("decoder_config_hash", self.decoder_config_hash),
            ("combined_config_hash", self.combined_config_hash),
        ):
            _sha256_hex(value, name)


@dataclass(frozen=True, slots=True)
class LiveServiceDescriptor:
    source_revision: str
    provider_name: str
    provider_revision: str
    provider_manifest_hash: str
    config_hashes: LiveServiceConfigHashes
    bounds: LiveServiceBounds
    schema_version: int = LIVE_SERVICE_SCHEMA_VERSION
    live_protocol_version: str = LIVE_PROTOCOL_VERSION
    live_protocol: LiveV2Descriptor = field(default_factory=LiveV2Descriptor)
    sample_rate: int = LIVE_SAMPLE_RATE
    frame_samples: int = LIVE_SAMPLE_RATE
    feature_enabled: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != LIVE_SERVICE_SCHEMA_VERSION:
            raise ValueError("unsupported live service descriptor schema_version.")
        if self.live_protocol_version != LIVE_PROTOCOL_VERSION:
            raise ValueError("unsupported live service protocol version.")
        if not isinstance(self.live_protocol, LiveV2Descriptor):
            raise ValueError("live_protocol must be LiveV2Descriptor.")
        if self.sample_rate != LIVE_SAMPLE_RATE:
            raise ValueError(f"live service audio must be {LIVE_SAMPLE_RATE} Hz.")
        _positive(self.frame_samples, "frame_samples")
        if self.frame_samples > self.bounds.max_frame_samples:
            raise ValueError("frame_samples must not exceed max_frame_samples.")
        for name, value in (
            ("source_revision", self.source_revision),
            ("provider_name", self.provider_name),
            ("provider_revision", self.provider_revision),
        ):
            if not value:
                raise ValueError(f"{name} must be non-empty.")
        _sha256_hex(self.provider_manifest_hash, "provider_manifest_hash")
        if not self.feature_enabled:
            raise ValueError("live service descriptor is only valid for an explicitly enabled runtime.")

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


@dataclass(frozen=True, slots=True)
class LiveServiceEvent:
    seq: int
    session_id: str
    kind: str
    snapshot_version: int
    payload: Mapping[str, Any]
    schema_version: int = LIVE_SERVICE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != LIVE_SERVICE_SCHEMA_VERSION:
            raise ValueError("unsupported live service event schema_version.")
        _non_negative(self.seq, "seq")
        _non_negative(self.snapshot_version, "snapshot_version")
        if not self.session_id:
            raise ValueError("session_id must be non-empty.")
        if not self.kind:
            raise ValueError("event kind must be non-empty.")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["payload"] = _jsonable(dict(self.payload))
        return payload


@dataclass(frozen=True, slots=True)
class LiveServiceSnapshot:
    session_id: str
    descriptor: LiveServiceDescriptor
    session: LiveSnapshot
    pending_work_items: int
    terminal_failure: LiveServiceFailureRecord | None = None
    schema_version: int = LIVE_SERVICE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != LIVE_SERVICE_SCHEMA_VERSION:
            raise ValueError("unsupported live service snapshot schema_version.")
        if not self.session_id:
            raise ValueError("session_id must be non-empty.")
        _non_negative(self.pending_work_items, "pending_work_items")

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


@dataclass(frozen=True, slots=True)
class LiveServiceCreateResult:
    session_id: str
    descriptor: LiveServiceDescriptor
    snapshot: LiveServiceSnapshot


@dataclass(frozen=True, slots=True)
class LiveServiceFrameResult:
    ack: FrameAck
    queued_item_ids: tuple[int, ...]
    snapshot: LiveServiceSnapshot

    def __post_init__(self) -> None:
        object.__setattr__(self, "queued_item_ids", tuple(self.queued_item_ids))


_CanonicalPumpCallback = Callable[[], Awaitable[None] | None]


class _CanonicalPumpScheduler(Protocol):
    @property
    def pending_signals(self) -> int:
        ...

    @property
    def in_flight(self) -> bool:
        ...

    def signal(self, callback: _CanonicalPumpCallback) -> None:
        ...


class _TransientCanonicalPumpScheduler:
    """Coalesced transient worker for production-owned canonical pumping."""

    def __init__(self):
        self._condition = threading.Condition()
        self._pending: _CanonicalPumpCallback | None = None
        self._worker: threading.Thread | None = None
        self._in_flight = False

    @property
    def pending_signals(self) -> int:
        with self._condition:
            return 1 if self._pending is not None else 0

    @property
    def in_flight(self) -> bool:
        with self._condition:
            return self._in_flight

    @property
    def worker_count(self) -> int:
        with self._condition:
            return 0 if self._worker is None or not self._worker.is_alive() else 1

    def signal(self, callback: _CanonicalPumpCallback) -> None:
        with self._condition:
            self._pending = callback
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._run, name="moss-live-canonical-pump", daemon=True)
            self._worker.start()

    def _run(self) -> None:
        while True:
            with self._condition:
                if self._pending is None:
                    self._worker = None
                    return
                callback = self._pending
                self._pending = None
                self._in_flight = True
            try:
                result = callback()
                if inspect.isawaitable(result):
                    asyncio.run(result)
            finally:
                with self._condition:
                    self._in_flight = False


class _ManualCanonicalPumpScheduler:
    """Deterministic scheduler adapter for runtime-interface tests."""

    def __init__(self):
        self._pending: _CanonicalPumpCallback | None = None
        self._in_flight = False

    @property
    def pending_signals(self) -> int:
        return 1 if self._pending is not None else 0

    @property
    def in_flight(self) -> bool:
        return self._in_flight

    def signal(self, callback: _CanonicalPumpCallback) -> None:
        self._pending = callback

    def run_one(self) -> bool:
        if self._in_flight:
            raise RuntimeError("manual canonical scheduler is already in flight.")
        if self._pending is None:
            return False
        callback = self._pending
        self._pending = None
        self._in_flight = True
        try:
            result = callback()
            if result is not None:
                raise RuntimeError("manual canonical scheduler callback must be synchronous.")
        finally:
            self._in_flight = False
        return True

    def drain(self) -> int:
        runs = 0
        while self.run_one():
            runs += 1
        return runs


class _TerminalScheduler(Protocol):
    """Where a meeting's terminal pass runs, so it is not the stop request that runs it.

    One method, and the runtime never learns which thread answered. Plan §12.3's last
    paragraph is the whole reason this seam exists: a 150/120 decode of a whole meeting is
    minutes of work, and the stop request must return the meeting's final accounting long
    before that. Injected rather than assumed so a test can hold the pass still and read the
    surface a reader sees *while* it runs -- the interval G-M4-6 is about.
    """

    def submit(self, callback: Callable[[], None]) -> None:
        ...


class _ThreadTerminalScheduler:
    """One daemon thread per terminal pass. No queue, no pool, no coalescing.

    Deliberately not the canonical pump's scheduler: that one keeps a single *pending*
    callback and replaces it, which is right for "pump whatever is ready" and wrong here --
    two meetings stopping together would leave one of them silently unfinalized. A terminal
    pass is one-shot, per meeting, and rare (a meeting ends once), so the cheapest correct
    thing is a thread that runs exactly one of them.
    """

    def submit(self, callback: Callable[[], None]) -> None:
        threading.Thread(
            target=callback, name="moss-live-terminal-finalization", daemon=True
        ).start()


class _ManualTerminalScheduler:
    """Deterministic scheduler adapter for runtime-interface tests and measured drivers."""

    def __init__(self):
        self._pending: deque[Callable[[], None]] = deque()

    @property
    def pending(self) -> int:
        return len(self._pending)

    def submit(self, callback: Callable[[], None]) -> None:
        self._pending.append(callback)

    def run_one(self) -> bool:
        if not self._pending:
            return False
        self._pending.popleft()()
        return True

    def drain(self) -> int:
        runs = 0
        while self.run_one():
            runs += 1
        return runs


@dataclass(slots=True)
class _RuntimeSession:
    session_id: str
    echo_mode: str
    descriptor: LiveServiceDescriptor
    session: LiveSession
    coordinator: LiveCoordinator
    arbiter: InferenceArbiter
    events: deque[LiveServiceEvent]
    next_event_seq: int = 0
    terminal_failure: LiveServiceFailureRecord | None = None
    work_changed: threading.Event = field(default_factory=threading.Event)
    drain_waiters: set[_DrainWaiter] = field(default_factory=set)
    canonical_timing: dict[int, "_CanonicalTiming"] = field(default_factory=dict)
    rolling_timing: dict[int, "_RollingTiming"] = field(default_factory=dict)
    # What the terminal pass inherits, captured at the moment rolling ends because that is
    # the only moment it is knowable -- `stop_rolling` is called under the lock in the
    # middle of `stop`, and the pass itself starts minutes of decoding later.
    terminal_plan: TerminalDecodePlan | None = None


@dataclass(slots=True)
class _CanonicalTiming:
    queued_ns: int
    started_ns: int | None = None


@dataclass(slots=True)
class _RollingTiming:
    """What the runtime knows about one admitted window between queue and completion.

    The window's own extent is kept here rather than read back off the work item because the
    completion event must describe the window even on the paths where the coordinator never
    hands the request back -- a witness dispatched after the meeting stopped, or one whose
    pump raised. Plan §7.4 asks every window for a completion record; a record that exists
    only when the happy path ran is an accounting that cannot be reconciled.
    """

    queued_ns: int
    window_index: int
    start_sample: int
    end_sample: int
    started_ns: int | None = None


@dataclass(frozen=True, slots=True)
class _DrainWaiter:
    loop: asyncio.AbstractEventLoop
    event: asyncio.Event


class LiveServiceRuntime:
    """Deep default-off runtime for isolated service-backed live sessions."""

    def __init__(
        self,
        *,
        descriptor: LiveServiceDescriptor,
        endpoint_policy_factory: Callable[[], EndpointPolicy],
        speech_provider_factory: Callable[[], SpeechSignalProvider],
        decoder_factory: Callable[[], Any],
        identity_preparer_factory: Callable[[], LiveIdentityPreparer],
        rolling_decoder_factory: Callable[[], Any] | None = None,
        terminal_finalizer: Any | None = None,
        session_id_factory: Callable[[], str] | None = None,
        _canonical_scheduler: _CanonicalPumpScheduler | None = None,
        _terminal_scheduler: _TerminalScheduler | None = None,
        monotonic_ns: Callable[[], int] | None = None,
    ):
        self.descriptor = descriptor
        self._endpoint_policy_factory = endpoint_policy_factory
        self._speech_provider_factory = speech_provider_factory
        self._decoder_factory = decoder_factory
        self._identity_preparer_factory = identity_preparer_factory
        # A decoder able to hear a whole rolling window, or nothing. The span decoder cannot
        # be reused for it: the deployed adapter is bounded at the *span* cap, and a
        # ten-second witness is four times that. No factory, no rolling convergence.
        self._rolling_decoder_factory = rolling_decoder_factory
        # The meeting's last listener, or nothing. Held once for the whole deployment rather
        # than built per session, because it is stateless by construction: it holds file
        # mode's own runner and file mode's own inference arguments, and `finalize` is a
        # function of the plan, the tape and the surface it is handed. A deployment that
        # names no finalizer never starts a terminal pass and every meeting reads
        # `not_started`, which is what the service does today.
        self._terminal_finalizer = terminal_finalizer
        self._session_id_factory = session_id_factory or (lambda: uuid.uuid4().hex)
        self._canonical_scheduler = _canonical_scheduler or _TransientCanonicalPumpScheduler()
        self._terminal_scheduler = _terminal_scheduler or _ThreadTerminalScheduler()
        self._monotonic_ns = monotonic_ns or time.monotonic_ns
        self._sessions: dict[str, _RuntimeSession] = {}
        self._lock = threading.RLock()
        self._ready_session_ids: deque[str] = deque()
        self._ready_session_set: set[str] = set()
        self._in_flight_session_ids: set[str] = set()
        self._in_flight_canonical_counts: dict[str, int] = {}
        self._publication_observer: (
            Callable[[str, LiveServiceSnapshot, tuple[LiveServiceEvent, ...]], None] | None
        ) = None

    def _bind_publication_observer(
        self,
        observer: Callable[[str, LiveServiceSnapshot, tuple[LiveServiceEvent, ...]], None],
    ) -> None:
        """Bind the one deployment-owned sink for raw snapshot/event advances.

        The callback runs under the runtime lock and may run on an inference thread. It must
        only hand immutable state to its owning event loop; persistence belongs outside this
        runtime so the measured inference and capture machinery remain unchanged.
        """

        with self._lock:
            if self._publication_observer is not None:
                raise RuntimeError("live publication observer is already bound.")
            self._publication_observer = observer

    def _unbind_publication_observer(
        self,
        observer: Callable[[str, LiveServiceSnapshot, tuple[LiveServiceEvent, ...]], None],
    ) -> None:
        """Remove exactly the deployment sink that was bound, under the runtime lock."""

        with self._lock:
            if self._publication_observer is not observer:
                raise RuntimeError("live publication observer binding does not match.")
            self._publication_observer = None

    def create(
        self,
        *,
        echo_mode: str | None = None,
        session_id: str | None = None,
    ) -> LiveServiceCreateResult:
        # `echo_mode` records the Account browser's headphones-vs-speakers preflight. Keep
        # the runtime usable by retained in-memory replay and measurement callers that do
        # not model a browser audio route; "unspecified" is their honest state.
        if echo_mode is None:
            echo_mode = "unspecified"
        elif not isinstance(echo_mode, str) or echo_mode not in {"headphones", "speakers"}:
            raise ValueError("echo_mode must be headphones or speakers.")
        with self._lock:
            session_id = session_id or self._new_session_id()
            if session_id in self._sessions:
                raise ValueError("live session id already exists.")
            endpoint_policy = self._endpoint_policy_factory()
            self._require_one_span_cap(endpoint_policy)
            session = LiveSession(max_retained_samples=self.descriptor.bounds.max_retained_samples)
            arbiter = InferenceArbiter(max_live_canonical_items=self.descriptor.bounds.max_queue_depth)
            coordinator = LiveCoordinator(
                session_key=session_id,
                session=session,
                endpoint_policy=endpoint_policy,
                speech_provider=self._speech_provider_factory(),
                decoder=self._decoder_factory(),
                identity_preparer=self._identity_preparer_factory(),
                arbiter=arbiter,
                rolling_decoder=(
                    None
                    if self._rolling_decoder_factory is None
                    else self._rolling_decoder_factory()
                ),
                tape_capacity_bytes=self.descriptor.bounds.max_tape_bytes,
            )
            state = _RuntimeSession(
                session_id=session_id,
                echo_mode=echo_mode,
                descriptor=self.descriptor,
                session=session,
                coordinator=coordinator,
                arbiter=arbiter,
                events=deque(maxlen=self.descriptor.bounds.max_events),
            )
            self._sessions[session_id] = state
            self._record_event(state, "session_created", {})
            snapshot = self._snapshot(state)
            return LiveServiceCreateResult(session_id=session_id, descriptor=self.descriptor, snapshot=snapshot)

    def accept_frame(
        self,
        session_id: str,
        frame: AudioFrame,
        *,
        retryable_queue_backpressure: bool = False,
    ) -> LiveServiceFrameResult:
        with self._lock:
            state = self._get(session_id)
            self._raise_terminal(state)
            queue_depth = self._pending_work_items(state)
            required_work_items = 0
            if (
                retryable_queue_backpressure
                and queue_depth < state.descriptor.bounds.max_queue_depth
            ):
                required_work_items = state.coordinator.preview_frame_work_items(frame)
            if (
                retryable_queue_backpressure
                and required_work_items > state.descriptor.bounds.max_queue_depth
            ):
                failure = LiveServiceTransportPacingFailure(
                    "frame canonical work exceeds total queue capacity.",
                    code="frame_work_exceeds_queue_capacity",
                    retryable=False,
                    detail={
                        "queue_depth": queue_depth,
                        "required_work_items": required_work_items,
                        "max_queue_depth": state.descriptor.bounds.max_queue_depth,
                    },
                )
                self._fail(state, failure.failure)
                raise failure
            # V2 retains the staged lane frame for an identical retry. Refuse before mono
            # admission mutates the session; legacy mono leaves this terminal policy disabled.
            if (
                retryable_queue_backpressure
                and (
                    queue_depth >= state.descriptor.bounds.max_queue_depth
                    or queue_depth + required_work_items > state.descriptor.bounds.max_queue_depth
                )
            ):
                raise LiveServiceTransportPacingFailure(
                    "live canonical queue is full.",
                    code="canonical_queue_full",
                    retryable=True,
                    detail={
                        "queue_depth": queue_depth,
                        "required_work_items": required_work_items,
                        "max_queue_depth": state.descriptor.bounds.max_queue_depth,
                    },
                )
            try:
                result = state.coordinator.accept_frame(frame)
            except InferenceArbiterBackpressure as exc:
                # A queue that is momentarily full is not a session fault, so on the v2
                # lane path this stays non-terminal. Every frame's frozen spans share one
                # bounded work reservation, preventing partial multi-span admission.
                if retryable_queue_backpressure:
                    raise LiveServiceTransportPacingFailure(
                        str(exc) or "live canonical queue is full.",
                        code="canonical_queue_full",
                        retryable=True,
                        detail={
                            "queue_depth": state.arbiter.snapshot().live_canonical,
                            "max_queue_depth": state.descriptor.bounds.max_queue_depth,
                            "overflow": "multi_span_frame",
                        },
                    ) from exc
                self._fail(state, self._failure_from_exception(exc))
                raise
            except Exception as exc:
                self._fail(state, self._failure_from_exception(exc))
                raise

            session_snapshot = state.session.snapshot()
            ack = FrameAck(
                sequence=frame.sequence,
                start_sample=result.accepted_start_sample,
                end_sample=result.accepted_end_sample,
                accepted_samples=session_snapshot.accepted_samples,
                retained_samples=session_snapshot.retained_samples,
                frozen_span_ids=tuple(span.id for span in result.frozen_spans),
            )
            self._record_event(
                state,
                "frame_accepted",
                {
                    "sequence": frame.sequence,
                    "start_sample": result.accepted_start_sample,
                    "end_sample": result.accepted_end_sample,
                    "queued_item_ids": result.queued_item_ids,
                },
            )
            for span in result.frozen_spans:
                self._record_event(
                    state,
                    "span_frozen",
                    {
                        "span_id": span.id,
                        "start_sample": span.start_sample,
                        "end_sample": span.end_sample,
                        "reason": span.reason,
                    },
                )
            for item_id in result.queued_item_ids:
                self._record_canonical_queued(state, item_id)
            self._record_rolling_queued(state, result.rolling_windows)
            # Unconditional: this frame may have queued a rolling window rather than a
            # canonical span, and `_mark_ready_locked` reads the arbiter itself rather than
            # trusting a caller's list of what it thinks it admitted.
            self._mark_ready_locked(state)
            return LiveServiceFrameResult(
                ack=ack,
                queued_item_ids=result.queued_item_ids,
                snapshot=self._snapshot(state),
            )

    def events(self, session_id: str, since_seq: int = 0) -> tuple[LiveServiceEvent, ...]:
        with self._lock:
            state = self._get(session_id)
            # The event endpoint is inclusive.  A reader with no rendered event uses -1,
            # which is the one cursor before the first valid event sequence (0).
            if int(since_seq) < -1:
                raise ValueError("since_seq must be at least -1.")
            return tuple(event for event in state.events if event.seq >= since_seq)

    def _events_with_observation(
        self,
        session_id: str,
        since_seq: int = 0,
    ) -> tuple[tuple[LiveServiceEvent, ...], int]:
        """Return events and their read instant from the runtime's monotonic clock."""

        with self._lock:
            state = self._get(session_id)
            if int(since_seq) < -1:
                raise ValueError("since_seq must be at least -1.")
            events = tuple(event for event in state.events if event.seq >= since_seq)
            return events, self._monotonic_ns()

    def snapshot(self, session_id: str, since_version: int | None = None) -> LiveServiceSnapshot | None:
        with self._lock:
            state = self._get(session_id)
            snapshot = self._snapshot(state)
            if (
                since_version is not None
                and snapshot.session.version <= since_version
                # Terminality is fenced *outside* the session's version counter: `_fail`
                # records the failure on the runtime while the session object -- which owns
                # `version` -- is never asked to transition, so the version a polling reader
                # already holds does not move when the meeting dies. Suppressing the body as
                # "unchanged" therefore withholds the one fact that ends the poll, and the
                # reader keeps asking a dead session for updates forever. That was the
                # observed outage shape, so the version gate must never hide it: a terminal
                # snapshot is always delivered, and the reader stops on the next read.
                and state.terminal_failure is None
            ):
                return None
            return snapshot

    def _identity_observations(self, session_id: str) -> tuple[object, ...]:
        """Return this live session's immutable, in-memory album observations."""

        with self._lock:
            return tuple(self._get(session_id).coordinator.journal_observations())

    def _operator_queue_snapshot(self) -> dict[str, int | bool]:
        """Aggregate content-free queue and worker facts under the runtime lock."""

        with self._lock:
            batch = 0
            live_canonical = 0
            live_refinement = 0
            live_provisional = 0
            for state in self._sessions.values():
                queues = state.arbiter.snapshot()
                batch += queues.batch
                live_canonical += queues.live_canonical
                live_refinement += queues.live_refinement
                live_provisional += queues.live_provisional
            return {
                "batch": batch,
                "live_canonical": live_canonical,
                "live_refinement": live_refinement,
                "live_provisional": live_provisional,
                "worker_busy": bool(self._in_flight_session_ids)
                or any(
                    state.session.snapshot().finalization_status == "running"
                    for state in self._sessions.values()
                ),
            }

    async def stop(self, session_id: str, deadline: float) -> LiveServiceSnapshot:
        loop = asyncio.get_running_loop()
        end_time = loop.time() + max(0.0, float(deadline))
        with self._lock:
            state = self._get(session_id)
        try:
            # `stop_endpoint` submits the final open partition and had no capacity
            # preflight, so stopping while the canonical queue was full raised straight
            # into the handler below and terminalized the session -- losing the tail span
            # on the most ordinary path there is (a user clicking Stop under load).
            # A full queue at stop is a pacing condition, not a session fault: drain and
            # retry within the caller's deadline, and only then time out.
            while True:
                with self._lock:
                    self._raise_terminal(state)
                    queue_depth = self._pending_work_items(state)
                    required_work_items = state.coordinator.preview_stop_work_items()
                    if required_work_items > state.descriptor.bounds.max_queue_depth:
                        raise TimeoutError(
                            "live service stop tail exceeds canonical queue capacity."
                        )
                    if (
                        queue_depth + required_work_items
                        > state.descriptor.bounds.max_queue_depth
                    ):
                        queued = None
                    else:
                        queued = state.coordinator.stop_endpoint()
                    if queued is not None:
                        for item_id in queued:
                            self._record_canonical_queued(state, item_id, reason="stop")
                        if self._has_unresolved_work_locked(state) and loop.time() >= end_time:
                            raise TimeoutError("live service stop deadline expired with unresolved work.")
                        if queued:
                            self._mark_ready_locked(state)
                        break
                if loop.time() >= end_time:
                    raise TimeoutError(
                        "live service stop deadline expired with a full canonical queue."
                    )
                await self._wait_for_drain(state, end_time=end_time)
            await self._wait_for_drain(state, end_time=end_time)
            with self._lock:
                # Rolling ends before the last identity sweep, for the sweep's own reason: a
                # revision applied after the sweep would carry labels the sweep never saw.
                state.terminal_plan = state.coordinator.stop_rolling()
                self._finalize_identity_locked(state)
            remaining = max(0.0, end_time - loop.time())
            snapshot = await state.session.stop(remaining)
        except Exception as exc:
            failure = self._failure_from_exception(exc)
            with self._lock:
                self._fail(state, failure)
            if not isinstance(exc, TimeoutError):
                raise
            raise
        with self._lock:
            snapshot = self._snapshot(state, session_snapshot=snapshot)
            if snapshot.session.accepted_samples != snapshot.session.accounted_samples or snapshot.pending_work_items:
                failure = LiveServiceIntegrityFailure(
                    "live service stop completed without exact accepted/accounted equality.",
                    code="stop_accounting_mismatch",
                ).failure
                self._fail(state, failure)
                raise LiveServiceIntegrityFailure(failure.message, code=failure.code)
        with self._lock:
            self._record_event(state, "session_closed", {"accepted_samples": snapshot.session.accepted_samples})
            # ADR-0003 D3 still ends the meeting's audio with the meeting -- but "the
            # meeting" now includes its last listener, so the release moves behind the
            # terminal pass and happens on every one of its endings (plan §12.3 step 7).
            # When no pass is scheduled nothing has changed: the tape is released here, in
            # the stop that created it.
            if not self._begin_terminal_locked(state):
                self._release_tape_locked(state)
            return self._snapshot(state)

    async def abort(
        self,
        session_id: str,
        reason: str,
        *,
        detail: Mapping[str, Any] | None = None,
    ) -> LiveServiceSnapshot:
        """End the session on a caller's say-so, recording what the caller knows.

        `detail` is how an aborting caller hands the runtime the facts only it has -- the
        helper coordinator's per-lane failure codes, for one. It reaches the
        `session_aborted` event and the session's terminal failure record, so the journal
        names the cause and not merely the effect.
        """

        reason = reason or "aborted"
        self._fence_session(session_id, reason, detail=detail)
        with self._lock:
            state = self._get(session_id)
        snapshot = await state.session.abort(reason)
        with self._lock:
            return self._snapshot(state, session_snapshot=snapshot)

    def _fence_session(
        self,
        session_id: str,
        reason: str,
        *,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        """Synchronously terminalize one raw session before its owner first awaits."""

        reason = reason or "aborted"
        with self._lock:
            state = self._get(session_id)
            self._discard_session_queued_work_locked(state)
            if state.terminal_failure is None:
                self._fail(
                    state,
                    LiveServiceTransportPacingFailure(
                        reason,
                        code="aborted",
                        detail=detail,
                    ).failure,
                    event_kind="session_aborted",
                )

    def _discard_session_queued_work_locked(self, state: _RuntimeSession) -> None:
        """Discard one terminal session's queued Live work and its owned accounting.

        This runs under the runtime lock before `abort` first awaits. The arbiter removes
        exactly the not-yet-dispatched items; an in-flight provider request remains truthful
        in `_in_flight_*` until its existing completion path rejects the late result and
        closes that accounting. Ready scheduling is global, so only this session's marker is
        removed and peer callbacks remain runnable.
        """

        discarded = state.arbiter.discard_live_queued()
        if not discarded:
            return
        self._ready_session_set.discard(state.session_id)
        self._ready_session_ids = deque(
            session_id
            for session_id in self._ready_session_ids
            if session_id != state.session_id
        )
        for item in discarded:
            if item.kind == InferenceArbiter.LIVE_CANONICAL:
                state.canonical_timing.pop(item.id, None)
                self._record_event(
                    state,
                    "canonical_discarded",
                    {
                        "item_id": item.id,
                        "reason": "session_terminal",
                        "span_count": item.weight,
                    },
                )
            elif item.kind == InferenceArbiter.LIVE_REFINEMENT:
                self._record_rolling_completed(state, item.id, "session_terminal", None)
        state.work_changed.set()
        self._notify_drain_waiters_locked(state)

    def _finalize_identity_locked(self, state: _RuntimeSession) -> None:
        """Run ADR-0002's final sweep for a meeting that reached a clean stop.

        Placed after the drain and before `session.stop` so the stop response already carries
        the corrected transcript; a closed session is revisable anyway, so this is ordering
        for the reader's benefit rather than a requirement.

        **The abort path deliberately does not do this.** Terminal viewers retain read-only access,
        but abort is the path that must do as little as possible; it publishes the failure and the
        transcript already committed rather than starting a new identity sweep during teardown.

        The event is recorded whether or not anything changed. "The last sweep ran and found
        nothing" and "the last sweep never ran" are opposite facts about a meeting, and the
        only way to tell them apart after the fact is a line that appears either way.
        """

        if state.terminal_failure is not None:
            return
        result = state.coordinator.finalize_identity()
        self._record_event(
            state,
            "identity_finalized",
            {
                "identity_revision_version": result.identity_revision_version,
                "identity_revision_spans": result.identity_revision_spans,
                "identity_revision_units": result.identity_revision_units,
                "identity_revision_merges": result.identity_revision_merges,
                "identity_revision_refusals": dict(result.identity_revision_refusals),
            },
        )

    # ------------------------------------------------------------------ terminal (plan E4)

    def _begin_terminal_locked(self, state: _RuntimeSession) -> bool:
        """Start the meeting's last listener, or say why this meeting gets none.

        Answers whether a pass was scheduled -- which is the same question as "does the tape
        still belong to someone", so the caller knows whether to release it.

        Three meetings get no pass, and only the first is silent. A deployment that named no
        finalizer is the service as it shipped before E4 and every meeting reads
        `not_started`. A deployment that named one but kept no tape, or ran no rolling
        witness to hand the pass its extent, gets `unavailable` and a reason: "nobody tried"
        and "there was nothing to try on" are different facts about a meeting, and a reader
        who is shown neither cannot tell them apart.
        """

        if self._terminal_finalizer is None:
            return False
        plan = state.terminal_plan
        tape = state.coordinator.tape
        if plan is None or tape is None:
            # One word, two reasons. `unavailable` is what a reader needs -- there will be no
            # terminal surface for this meeting -- and it is taken from the outcome enum so
            # the status vocabulary keeps one author; the reason carries which of the two
            # preconditions was missing, because that is the deployment's to fix.
            reason = "no_retained_tape" if tape is None else "no_terminal_plan"
            status = state.session.note_finalization(
                TerminalOutcome.TAPE_UNAVAILABLE.finalization_status
            )
            self._record_event(
                state,
                "terminal_finalization_failed",
                {"reason": reason, "finalization_status": status, "applied": False},
            )
            return False
        status = state.session.note_finalization("running")
        self._record_event(
            state,
            "terminal_finalization_started",
            {
                "epoch": plan.epoch,
                "end_sample": plan.end_sample,
                "rolling_through_sample": plan.rolling_through_sample,
                "rolling_status": plan.rolling_status.value,
                "rolling_windows_completed": plan.windows_completed,
                "rolling_windows_failed": plan.windows_failed,
                "finalization_status": status,
            },
        )
        self._terminal_scheduler.submit(lambda: self._run_terminal(state, plan, tape))
        return True

    def _run_terminal(self, state: _RuntimeSession, plan: TerminalDecodePlan, tape: Any) -> None:
        """Decode the whole meeting, off the stop request's clock (plan §12.3).

        Shaped like the refinement pump and for the same reason: read under the lock, decode
        outside it, publish under it again. The decode is minutes long and the surface it
        replaces is being polled the entire time, so holding the lock across it would freeze
        every reader of the meeting it is trying to improve.

        Nothing here is terminal for the session. A meeting that was captured succeeded; the
        worst a failed last listener can do is leave the rolling surface exactly where it
        already was, with a word for why (plan §5.2, PRD E4 exit).
        """

        finalization: TerminalFinalization | None = None
        try:
            with self._lock:
                snapshot = state.session.snapshot()
            finalization = self._terminal_finalizer.finalize(
                plan=plan,
                tape=tape,
                base_text_revision_version=snapshot.text_revision_version,
                base_surface=snapshot.effective_transcript,
                canonical_speakers=snapshot.identity_snapshot.canonical_speakers,
            )
        except Exception:
            # Counts and names only, never the words -- the rule every listener in this
            # runtime follows. The adapter answers with a named refusal for the failures it
            # expects, so reaching here means a defect, and a defect is still not the
            # meeting's problem.
            _TERMINAL_LOG.warning("live terminal finalization failed", exc_info=True)
        with self._lock:
            try:
                self._publish_terminal_locked(state, finalization)
            finally:
                # The tape outlives the meeting by exactly one listener (Appendix B Q10).
                # In the `finally` because every ending owes it: a refused proposal, a
                # defect, and a published surface all end the only reason the audio was
                # kept.
                self._release_tape_locked(state)
                state.work_changed.set()
                self._notify_drain_waiters_locked(state)

    def _publish_terminal_locked(
        self, state: _RuntimeSession, finalization: TerminalFinalization | None
    ) -> None:
        """Offer the pass's proposal to the session and put what happened on the stream."""

        if finalization is None:
            state.session.note_finalization("failed")
            self._record_event(
                state,
                "terminal_finalization_failed",
                {"reason": "finalizer_defect", "finalization_status": "failed", "applied": False},
            )
            return
        payload = dict(finalization.accounting.to_dict())
        outcome = None
        if finalization.proposal is None:
            # The pass named its own ending -- no tape, no answer, no words in the answer --
            # and `TerminalOutcome` already maps each to the word a reader is told.
            status = state.session.note_finalization(payload["finalization_status"])
        elif state.terminal_failure is not None:
            # The meeting died between the stop that scheduled this pass and its answer.
            # A dead meeting's surface is not revised; it is reported.
            payload["reason"] = "session_terminal"
            status = state.session.note_finalization("failed")
        else:
            outcome = state.session.apply_text_revision(finalization.proposal)
            # Refused is a failure of this pass, not of the meeting: `already_finalized`,
            # a stale version, an interval the session does not recognise. The rolling
            # surface stays exactly where it was, which is the PRD's E4-exit requirement.
            status = (
                state.session.snapshot().finalization_status
                if outcome.applied
                else state.session.note_finalization("failed")
            )
        payload.update(
            {
                "finalization_status": status,
                "applied": bool(outcome is not None and outcome.applied),
                "refusal": None if outcome is None else outcome.refusal,
                "text_revision_version": state.session.snapshot().text_revision_version,
                "canonical_through_sample": state.session.snapshot().canonical_through_sample,
            }
        )
        if outcome is not None:
            # The same two events the rolling producer writes, for the same seam: a reader
            # counting revisions does not have to know which listener proposed one. Recorded
            # before the terminal event because it happened first -- the terminal event's
            # status is only true once the revision has landed or been refused.
            self._record_event(
                state,
                "text_revision_applied" if outcome.applied else "text_revision_refused",
                {
                    "source": "terminal",
                    "item_id": None,
                    "window_index": None,
                    "start_sample": finalization.proposal.start_sample,
                    "end_sample": finalization.proposal.end_sample,
                    "revised_segments": outcome.revised_segments,
                    "refusal": outcome.refusal,
                    "text_revision_version": outcome.version,
                    "canonical_through_sample": outcome.canonical_through_sample,
                    "finalization_status": status,
                },
            )
        self._record_event(
            state,
            "terminal_finalization_completed"
            if payload["applied"]
            else "terminal_finalization_failed",
            payload,
        )

    def _require_one_span_cap(self, endpoint_policy: EndpointPolicy) -> None:
        """Refuse a provider config that declares the span cap twice with two values.

        The endpoint policy is the only thing that closes a span, so
        `bounds_config.hard_cap_samples` is a declaration of what the policy must do rather
        than a second mechanism. The manifest finalizer already requires the two sections to
        agree at write time; checking it here means a manifest that reached the host by any
        other route is refused at session creation instead of running with an uncapped
        policy, which would let one span grow until retention backpressures.
        """

        declared = self.descriptor.bounds.hard_cap_samples
        enforced = endpoint_policy.config.hard_cap_samples
        if declared != enforced:
            raise ValueError(
                "live provider config declares two different span caps: "
                f"bounds_config.hard_cap_samples={declared} but "
                f"endpoint_config.hard_cap_samples={enforced}."
            )

    def _new_session_id(self) -> str:
        session_id = self._session_id_factory()
        if not session_id:
            raise ValueError("session_id_factory returned an empty id.")
        if session_id in self._sessions:
            raise ValueError(f"duplicate live session id {session_id}.")
        return session_id

    def _get(self, session_id: str) -> _RuntimeSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"unknown live service session {session_id}") from exc

    def _snapshot(
        self,
        state: _RuntimeSession,
        *,
        session_snapshot: LiveSnapshot | None = None,
    ) -> LiveServiceSnapshot:
        session = session_snapshot or state.session.snapshot()
        # A runtime failure fences the session before the lower-level session object always
        # gets a chance to transition itself.  The public snapshot is the client contract,
        # so it must report that terminal state immediately instead of advertising "active"
        # beside a terminal_failure record.
        #
        # It only projects over a status that is still *running*.  A session that already
        # reached an end of its own -- closed, aborted, failed -- has the authoritative
        # account of how the meeting finished, and a teardown that lands after it (the
        # helper lease expiring minutes after a clean stop aborts the mono runtime) must
        # not rewrite "closed" into "failed" and tell an operator a finished meeting died.
        # The failure itself is still on the same snapshot, as `terminal_failure`.
        if state.terminal_failure is not None and session.status not in LIVE_TERMINAL_SESSION_STATUSES:
            session = replace(
                session,
                status="failed",
                failure_reason=state.terminal_failure.message,
            )
        return LiveServiceSnapshot(
            session_id=state.session_id,
            descriptor=state.descriptor,
            session=session,
            pending_work_items=self._pending_work_items(state),
            terminal_failure=state.terminal_failure,
        )

    def _pending_work_items(self, state: _RuntimeSession) -> int:
        in_flight = self._in_flight_canonical_counts.get(state.session_id, 0)
        return (
            state.arbiter.snapshot().live_canonical
            + in_flight
        )

    def _has_unresolved_work_locked(self, state: _RuntimeSession) -> bool:
        """Is there work whose result the session has not seen yet?

        Rolling witnesses count, and `pending_work_items` deliberately does not count them:
        that number is the *canonical* queue depth the transport paces against
        `max_queue_depth`, and a rolling window is not something a client may be asked to
        slow down for. Here the question is different -- a stop that did not wait for the
        window already decoding would discard the last correction of every meeting.
        """

        queues = state.arbiter.snapshot()
        return bool(
            self._pending_work_items(state)
            or state.session.snapshot().pending_span_ids
            or queues.live_refinement
            or queues.live_refinement_running
        )

    async def _wait_for_drain(self, state: _RuntimeSession, *, end_time: float) -> None:
        loop = asyncio.get_running_loop()
        waiter = _DrainWaiter(loop=loop, event=asyncio.Event())
        while True:
            timeout: float
            with self._lock:
                self._raise_terminal(state)
                if not self._has_unresolved_work_locked(state):
                    return
                remaining = end_time - loop.time()
                if remaining <= 0:
                    raise TimeoutError("live service stop deadline expired with unresolved work.")
                state.work_changed.clear()
                waiter.event.clear()
                state.drain_waiters.add(waiter)
                self._raise_terminal(state)
                if not self._has_unresolved_work_locked(state):
                    state.drain_waiters.discard(waiter)
                    return
                timeout = end_time - loop.time()
                if timeout <= 0:
                    state.drain_waiters.discard(waiter)
                    raise TimeoutError("live service stop deadline expired with unresolved work.")
            try:
                await asyncio.wait_for(waiter.event.wait(), timeout=timeout)
            except asyncio.TimeoutError as exc:
                raise TimeoutError("live service stop deadline expired with unresolved work.") from exc
            finally:
                with self._lock:
                    state.drain_waiters.discard(waiter)

    def _mark_ready_locked(self, state: _RuntimeSession) -> None:
        if state.terminal_failure is not None:
            return
        if state.session_id in self._in_flight_session_ids or state.session_id in self._ready_session_set:
            return
        queues = state.arbiter.snapshot()
        if queues.live_canonical <= 0 and queues.live_refinement <= 0:
            return
        self._ready_session_ids.append(state.session_id)
        self._ready_session_set.add(state.session_id)
        self._canonical_scheduler.signal(self._drain_ready_sessions)

    def _drain_ready_sessions(self) -> None:
        while self._pump_next_ready_session(raise_errors=False):
            pass

    def _pump_next_ready_session(self, *, raise_errors: bool) -> bool:
        with self._lock:
            while self._ready_session_ids:
                session_id = self._ready_session_ids.popleft()
                self._ready_session_set.remove(session_id)
                state = self._sessions.get(session_id)
                if state is None or state.terminal_failure is not None:
                    continue
                if state.session_id in self._in_flight_session_ids:
                    continue
                item = state.arbiter.next_work()
                if item is None:
                    if state.session.snapshot().pending_span_ids:
                        failure = LiveServiceIdentityCommitFailure(
                            "live service has unresolved frozen spans without queued work.",
                            code="unqueued_frozen_span",
                        ).failure
                        self._fail(state, failure)
                        if raise_errors:
                            raise LiveServiceIdentityCommitFailure(failure.message, code=failure.code)
                    continue
                if item.kind == InferenceArbiter.LIVE_REFINEMENT:
                    # A witness holds the session's single in-flight inference slot for as
                    # long as it decodes, exactly as a span does. That is not an oversight:
                    # one in-flight MOSS request per harness is the deployment contract, so
                    # the rolling cost is a serial cost and plan §10.6 must measure it as one.
                    self._in_flight_session_ids.add(state.session_id)
                    timing = state.rolling_timing.get(item.id)
                    if timing is not None:
                        timing.started_ns = self._monotonic_ns()
                    span_count = 0
                    break
                try:
                    span_count = state.coordinator.work_item_span_count(item)
                except Exception as exc:
                    self._fail(state, self._failure_from_exception(exc))
                    if raise_errors:
                        raise
                    continue
                self._in_flight_session_ids.add(state.session_id)
                self._in_flight_canonical_counts[state.session_id] = span_count
                started_ns = self._monotonic_ns()
                timing = state.canonical_timing.get(item.id)
                if timing is None:
                    timing = _CanonicalTiming(queued_ns=started_ns)
                    state.canonical_timing[item.id] = timing
                timing.started_ns = started_ns
                self._record_event(
                    state,
                    "canonical_started",
                    {
                        "item_id": item.id,
                        "runtime_monotonic_ns": started_ns,
                        "queue_wait_ms": _elapsed_ms(timing.queued_ns, started_ns),
                    },
                )
                break
            else:
                return False
        if item.kind == InferenceArbiter.LIVE_REFINEMENT:
            self._process_refinement_item(state, item)
        else:
            self._process_in_flight_item(state, item, span_count, raise_errors=raise_errors)
        return True

    def _process_refinement_item(self, state: _RuntimeSession, item: Any) -> None:
        """Decode one rolling window and offer it to the session, or give up on rolling.

        Shaped like the canonical pump -- capture under the lock, decode outside it, publish
        under it again -- because a ten-second decode held under the runtime lock would stall
        frame acceptance for the whole meeting.

        Nothing here is terminal, and that is the difference from the canonical pump. The
        base path is the meeting; the witness is an improvement to it, and ADR-0005 D1 gives
        the session the last word on every revision precisely so a second listener cannot
        take the first one down. A decode that failed is already an empty outcome by the time
        it arrives here (`decode_refinement` names it), so what is left to catch is a defect
        -- and a defect ends *rolling*, with the surface and the base path untouched.
        """

        outcome = "defect"
        result: CoordinatorRefinementResult | None = None
        try:
            with self._lock:
                if state.terminal_failure is not None:
                    outcome = "session_terminal"
                    return
                request = state.coordinator.capture_refinement_item(item)
            if request is None:
                outcome = "not_awaited"
                return
            decode = state.coordinator.decode_refinement(request)
            with self._lock:
                if state.terminal_failure is not None:
                    outcome = "session_terminal"
                    return
                result = state.coordinator.submit_refinement(decode, item)
                outcome = (
                    "applied"
                    if result.applied
                    else "refused"
                    if result.proposed
                    else "no_proposal"
                )
        except Exception:
            # Counts and names only, never the words: the same rule the identity finalizer
            # follows. Rolling stops for this session so the defect cannot repeat every
            # window; the transcript keeps everything both listeners had already published.
            _ROLLING_LOG.warning("live rolling refinement failed", exc_info=True)
            with self._lock:
                try:
                    state.coordinator.stop_rolling()
                except Exception:
                    _ROLLING_LOG.warning("live rolling refinement stop failed", exc_info=True)
        finally:
            with self._lock:
                state.coordinator.release_refinement(item)
                # The completion event comes before the windows this completion planned, so
                # the stream reads in the order the work actually happened: this window
                # answered, its revision landed, and *that* made the next window ownable.
                self._record_rolling_completed(state, item.id, outcome, result)
                if result is not None:
                    self._record_rolling_queued(state, result.rolling_windows)
                self._in_flight_session_ids.discard(state.session_id)
                state.work_changed.set()
                self._notify_drain_waiters_locked(state)
                if state.terminal_failure is None:
                    self._mark_ready_locked(state)

    def _process_in_flight_item(
        self,
        state: _RuntimeSession,
        item: Any,
        span_count: int,
        *,
        raise_errors: bool,
    ) -> None:
        try:
            for span_index in range(span_count):
                with self._lock:
                    if state.terminal_failure is not None:
                        return
                    work = state.coordinator.capture_work_item(item, span_index=span_index)
                prepared = state.coordinator.prepare_work_item(work)
                with self._lock:
                    if state.terminal_failure is not None:
                        return
                    result = state.coordinator.submit_prepared_work(prepared)
                    self._in_flight_canonical_counts[state.session_id] = span_count - span_index - 1
                    processed_ns = self._monotonic_ns()
                    timing = state.canonical_timing.get(item.id)
                    queued_ns = timing.queued_ns if timing is not None else processed_ns
                    started_ns = (
                        timing.started_ns
                        if timing is not None and timing.started_ns is not None
                        else processed_ns
                    )
                    self._record_event(
                        state,
                        "canonical_processed",
                        {
                            "item_id": item.id,
                            "runtime_monotonic_ns": processed_ns,
                            "queue_wait_ms": _elapsed_ms(queued_ns, started_ns),
                            "canonical_processing_elapsed_ms": _elapsed_ms(
                                started_ns, processed_ns
                            ),
                            "queued_to_processed_ms": _elapsed_ms(queued_ns, processed_ns),
                            "batch_index": span_index,
                            "batch_size": span_count,
                            "span_id": result.span_id,
                            "submitted": result.submitted,
                            "identity_status": result.identity_status,
                            "identity_reason": result.identity_reason,
                            "submission_refusal": result.submission_refusal,
                            "empty_reason": result.empty_reason,
                            "committed_samples": result.committed_samples,
                            "canonical_decode_elapsed_sec": result.canonical_decode_elapsed_sec,
                            "frozen_span_sample_count": result.frozen_span_sample_count,
                            "frozen_span_duration_sec": result.frozen_span_duration_sec,
                            "canonical_decode_rtf": result.canonical_decode_rtf,
                            "canonical_decode_token_cap": result.canonical_decode_token_cap,
                            "canonical_decode_capped": result.canonical_decode_capped,
                            "canonical_decode_generated_tokens": result.canonical_decode_generated_tokens,
                            "canonical_decode_salvage": result.canonical_decode_salvage,
                            "identity_revision_version": result.identity_revision_version,
                            "identity_revision_spans": result.identity_revision_spans,
                            "identity_revision_units": result.identity_revision_units,
                            "identity_revision_merges": result.identity_revision_merges,
                            "identity_revision_refusals": dict(result.identity_revision_refusals),
                            "rolling_status": result.rolling_status,
                        },
                    )
                    if result.canonical_decode_salvage == SALVAGED_DISPOSITION:
                        # Plan §7.4 names the repair as its own event rather than leaving it
                        # a field on a span record: salvage publishes words the grammar had
                        # rejected, and how often that happens is a policy measurement, not
                        # a detail of one span.
                        self._record_event(
                            state,
                            "decode_salvaged",
                            {
                                "span_id": result.span_id,
                                "disposition": result.canonical_decode_salvage,
                                "committed_samples": result.committed_samples,
                                "frozen_span_sample_count": result.frozen_span_sample_count,
                                "canonical_decode_generated_tokens": result.canonical_decode_generated_tokens,
                            },
                        )
                    self._record_rolling_queued(state, result.rolling_windows)
                    if not result.submitted:
                        failure = LiveServiceIdentityCommitFailure(
                            f"canonical work did not atomically publish: {result.submission_refusal}.",
                            code="canonical_not_submitted",
                            detail={
                                "span_id": result.span_id,
                                "identity_status": result.identity_status,
                                "identity_reason": result.identity_reason,
                                "submission_refusal": result.submission_refusal,
                            },
                        ).failure
                        self._fail(state, failure)
                        if raise_errors:
                            raise LiveServiceIdentityCommitFailure(
                                failure.message,
                                code=failure.code,
                                detail=failure.detail,
                            )
                        return
        except Exception as exc:
            with self._lock:
                self._fail(state, self._failure_from_exception(exc))
            if raise_errors:
                raise
        finally:
            with self._lock:
                self._in_flight_session_ids.discard(state.session_id)
                self._in_flight_canonical_counts.pop(state.session_id, None)
                state.canonical_timing.pop(item.id, None)
                state.work_changed.set()
                self._notify_drain_waiters_locked(state)
                if state.terminal_failure is None:
                    # `_mark_ready_locked` asks the arbiter itself, so this covers the window
                    # this span's own commit just made plannable as well as the next span.
                    self._mark_ready_locked(state)

    def _record_event(self, state: _RuntimeSession, kind: str, payload: Mapping[str, Any]) -> None:
        event = LiveServiceEvent(
            seq=state.next_event_seq,
            session_id=state.session_id,
            kind=kind,
            snapshot_version=state.session.snapshot().version,
            payload=payload,
        )
        state.events.append(event)
        state.next_event_seq += 1
        state.work_changed.set()
        self._notify_drain_waiters_locked(state)
        if self._publication_observer is not None:
            self._publication_observer(
                state.session_id,
                self._snapshot(state),
                tuple(state.events),
            )

    def _record_canonical_queued(
        self,
        state: _RuntimeSession,
        item_id: int,
        *,
        reason: str | None = None,
    ) -> None:
        queued_ns = self._monotonic_ns()
        state.canonical_timing[item_id] = _CanonicalTiming(queued_ns=queued_ns)
        payload: dict[str, Any] = {
            "item_id": item_id,
            "runtime_monotonic_ns": queued_ns,
        }
        if reason is not None:
            payload["reason"] = reason
        self._record_event(state, "canonical_queued", payload)

    def _record_rolling_queued(
        self, state: _RuntimeSession, plans: Sequence[RollingWindowPlan]
    ) -> None:
        """Announce every window the converger planned, admitted or not (plan §7.4).

        A refused admission gets an event with `item_id` null and no timing entry: nothing
        will ever complete it, so matching it with a completion would make the accounting lie.
        The counterpart property -- one completion per admitted window -- is what lets a soak
        read queue depth and stale/coalesced counts straight off the stream.
        """

        for plan in plans:
            queued_ns = self._monotonic_ns()
            if plan.item_id is not None:
                state.rolling_timing[plan.item_id] = _RollingTiming(
                    queued_ns=queued_ns,
                    window_index=plan.window_index,
                    start_sample=plan.start_sample,
                    end_sample=plan.end_sample,
                )
            self._record_event(
                state,
                "rolling_decode_queued",
                {
                    "item_id": plan.item_id,
                    "admitted": plan.item_id is not None,
                    "window_index": plan.window_index,
                    "start_sample": plan.start_sample,
                    "end_sample": plan.end_sample,
                    "window_samples": plan.sample_count,
                    "runtime_monotonic_ns": queued_ns,
                },
            )

    def _record_rolling_completed(
        self,
        state: _RuntimeSession,
        item_id: int,
        outcome: str,
        result: CoordinatorRefinementResult | None,
    ) -> None:
        """Close one window's account, on every path a dispatched window can end on.

        `outcome` names which path that was; the decode measurements are `None` on the paths
        where no decode happened, rather than zero, because a window nobody was waiting for
        did not decode ten seconds of audio in no time.
        """

        completed_ns = self._monotonic_ns()
        timing = state.rolling_timing.pop(item_id, None)
        window_index = timing.window_index if timing is not None else None
        start_sample = timing.start_sample if timing is not None else None
        end_sample = timing.end_sample if timing is not None else None
        if result is not None:
            window_index = result.window_index
            start_sample = result.start_sample
            end_sample = result.end_sample
        started_ns = timing.started_ns if timing is not None and timing.started_ns is not None else completed_ns
        queued_ns = timing.queued_ns if timing is not None else started_ns
        owned_start = None if result is None else result.owned_start_sample
        owned_end = None if result is None else result.owned_end_sample
        payload: dict[str, Any] = {
            "item_id": item_id,
            "outcome": outcome,
            "window_index": window_index,
            "start_sample": start_sample,
            "end_sample": end_sample,
            "window_samples": None if start_sample is None or end_sample is None else end_sample - start_sample,
            "owned_start_sample": owned_start,
            "owned_end_sample": owned_end,
            "owned_samples": None if owned_start is None or owned_end is None else owned_end - owned_start,
            "queue_wait_ms": _elapsed_ms(queued_ns, started_ns),
            "queued_to_completed_ms": _elapsed_ms(queued_ns, completed_ns),
            "runtime_monotonic_ns": completed_ns,
            "rolling_decode_elapsed_sec": None if result is None else result.decode_elapsed_sec,
            "rolling_decode_rtf": None if result is None else result.decode_rtf,
            "rolling_decode_token_cap": None if result is None else result.decode_token_cap,
            "rolling_decode_capped": None if result is None else result.decode_capped,
            "rolling_decode_generated_tokens": None if result is None else result.decode_generated_tokens,
            "decode_failure": None if result is None else result.decode_failure,
            "proposed": False if result is None else result.proposed,
            "applied": False if result is None else result.applied,
            "refusal": None if result is None else result.refusal,
            "revised_segments": 0 if result is None else result.revised_segments,
            "rolling_status": self._rolling_status(state) if result is None else result.rolling_status,
            "windows_planned": None if result is None else result.windows_planned,
            "windows_completed": None if result is None else result.windows_completed,
            "windows_failed": None if result is None else result.windows_failed,
            "proposal_refusals": None if result is None else result.proposal_refusals,
            "last_proposal_refusal": None if result is None else result.last_proposal_refusal,
            "stale_completions": None if result is None else result.stale_completions,
            "decoded_audio_samples": None if result is None else result.decoded_audio_samples,
            "retained_samples": None if result is None else result.retained_samples,
            "retained_high_water_samples": None if result is None else result.retained_high_water_samples,
            "admission_refusals": None if result is None else result.admission_refusals,
            "normalization_merged_segments": (
                None if result is None else result.normalization_merged_segments
            ),
            "normalization_dropped_segments": (
                None if result is None else result.normalization_dropped_segments
            ),
            "normalization_displaced_samples": (
                None if result is None else result.normalization_displaced_samples
            ),
        }
        self._record_event(state, "rolling_decode_completed", payload)
        if result is None or not result.proposed:
            return
        self._record_event(
            state,
            "text_revision_applied" if result.applied else "text_revision_refused",
            {
                "source": "rolling",
                "item_id": item_id,
                "window_index": result.window_index,
                "start_sample": result.owned_start_sample,
                "end_sample": result.owned_end_sample,
                "revised_segments": result.revised_segments,
                "refusal": result.refusal,
                "text_revision_version": result.text_revision_version,
                "canonical_through_sample": result.canonical_through_sample,
                "finalization_status": state.session.snapshot().finalization_status,
            },
        )

    def _rolling_status(self, state: _RuntimeSession) -> str | None:
        accounting = state.coordinator.rolling_accounting()
        return None if accounting is None else accounting.status.value

    def _notify_drain_waiters_locked(self, state: _RuntimeSession) -> None:
        for waiter in tuple(state.drain_waiters):
            waiter.loop.call_soon_threadsafe(waiter.event.set)

    def _fail(
        self,
        state: _RuntimeSession,
        failure: LiveServiceFailureRecord,
        *,
        event_kind: str = "terminal_failure",
    ) -> None:
        if state.terminal_failure is not None:
            return
        state.terminal_failure = failure
        self._record_event(state, event_kind, {"failure": failure.to_dict()})
        # A meeting that ended badly keeps no audio either: there is no terminal pass to
        # run over it, and ADR-0003 D3's horizon is the meeting rather than its outcome.
        self._release_tape_locked(state)

    def _release_tape_locked(self, state: _RuntimeSession) -> None:
        """End the meeting's audio and put its accounting on the stream (ADR-0003 D3).

        The accounting is recorded rather than the audio's absence assumed: "zero tapes
        survive a session" is only evidence if a reader outside the process can see each
        one released, with the sample count, byte high-water and digest it was released
        with. Counts and digests only -- a tape event may not carry a meeting's words, and
        it has none to carry.
        """

        accounting = state.coordinator.release_tape()
        if accounting is None:
            return
        self._record_event(state, "session_tape_released", accounting.to_dict())

    def _raise_terminal(self, state: _RuntimeSession) -> None:
        if state.terminal_failure is not None:
            raise _error_from_failure(state.terminal_failure)

    def _failure_from_exception(self, exc: Exception) -> LiveServiceFailureRecord:
        """Turn an exception into a failure record that still names what raised it.

        Every arm carries `error_type`, because the code answers *which policy refused* and
        not *what happened*. A decode failure is named by a stable code rather than by its
        class name -- a new subclass, and `LiveProviderTransientError` was one, must not
        silently rename a failure the operator reads -- and the facts the decode seam
        already knows travel with it instead of only inside its sentence.
        """

        if isinstance(exc, LiveServiceError):
            return exc.failure
        if isinstance(exc, (LiveSessionBackpressure, InferenceArbiterBackpressure, TimeoutError)):
            return LiveServiceTransportPacingFailure(
                _failure_message(exc),
                code="backpressure_or_deadline",
                detail=_exception_detail(exc),
            ).failure
        if isinstance(exc, (LiveSessionFailed, LiveCoordinatorError, EndpointPolicyError)):
            return LiveServiceIdentityCommitFailure(
                _failure_message(exc),
                code="identity_commit_failed",
                detail=_exception_detail(exc),
            ).failure
        if isinstance(exc, LiveProviderError):
            return LiveServiceIntegrityFailure(
                _failure_message(exc),
                code="canonical_decode_failed",
                detail=_exception_detail(exc, **exc.detail),
            ).failure
        if isinstance(exc, (LiveSessionClosed, ValueError)):
            return LiveServiceIntegrityFailure(
                _failure_message(exc),
                code="integrity_error",
                detail=_exception_detail(exc),
            ).failure
        return LiveServiceIntegrityFailure(
            _failure_message(exc),
            code=exc.__class__.__name__,
            detail=_exception_detail(exc),
        ).failure


def _exception_detail(exc: Exception, **extra: Any) -> dict[str, Any]:
    return {"error_type": exc.__class__.__name__, **extra}


def active_live_session_count(runtime: LiveServiceRuntime) -> int:
    """Content-free process-local drain truth without widening the runtime operation set."""

    with runtime._lock:
        snapshots = (runtime._snapshot(state).session for state in runtime._sessions.values())
        return sum(
            snapshot.status not in LIVE_TERMINAL_SESSION_STATUSES
            or snapshot.finalization_status == "running"
            for snapshot in snapshots
        )


def _failure_message(exc: Exception) -> str:
    """The exception's message, or its type when it carries none.

    A `LiveServiceFailureRecord` refuses an empty message, so an exception raised with no
    arguments would have made the failure path itself raise -- losing the failure instead
    of reporting it. The type is a poor message and a far better answer than none.
    """

    return str(exc).strip() or exc.__class__.__name__


def _elapsed_ms(start_ns: int, end_ns: int) -> float:
    """A server-local monotonic duration; never a cross-host timestamp subtraction."""

    return max(0, end_ns - start_ns) / 1_000_000


def _error_from_failure(failure: LiveServiceFailureRecord) -> LiveServiceError:
    error_type: type[LiveServiceError]
    if failure.kind == LiveServiceFailureKind.PROVIDER_CONFIG:
        error_type = LiveServiceProviderConfigFailure
    elif failure.kind == LiveServiceFailureKind.IDENTITY_COMMIT:
        error_type = LiveServiceIdentityCommitFailure
    elif failure.kind == LiveServiceFailureKind.RTF:
        error_type = LiveServiceRtfFailure
    elif failure.kind == LiveServiceFailureKind.TRANSPORT_PACING:
        error_type = LiveServiceTransportPacingFailure
    else:
        error_type = LiveServiceIntegrityFailure
    return error_type(
        failure.message,
        code=failure.code,
        retryable=failure.retryable,
        detail=failure.detail,
    )


def hash_config(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(_jsonable(dict(payload)), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _positive(value: int, name: str) -> None:
    if int(value) <= 0:
        raise ValueError(f"{name} must be positive.")


def _non_negative(value: int, name: str) -> None:
    if int(value) < 0:
        raise ValueError(f"{name} must be non-negative.")


def _sha256_hex(value: str, name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be a lowercase sha256 hex digest.")
