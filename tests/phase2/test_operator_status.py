from __future__ import annotations

import asyncio
import json
import os
import stat
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from _browser_workspace_fixtures import seed_workspace

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import (
    Phase2Store,
    create_phase2_app,
)
from moss_transcribe_diarize.app.phase2_admin import main as admin_main
from moss_transcribe_diarize.app.phase2_control import request_control
from moss_transcribe_diarize.app.phase2_control import (
    Phase2ControlError,
    Phase2ControlServer,
)
from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks
from moss_transcribe_diarize.app.phase2_lifecycle import AccountLifecycleSettlementError
from moss_transcribe_diarize.app.phase2_operator import (
    OPERATOR_EVENT_SCHEMA,
    OPERATOR_JOURNAL_LIMIT,
    OPERATOR_STATUS_SCHEMA,
    OperatorProjectionError,
    Phase2OperatorStatus,
    render_operator_status,
    serialize_operator_payload,
)
from moss_transcribe_diarize.app.live_lane_contract import LiveLane
from moss_transcribe_diarize.app.live_service_runtime import LiveServiceRuntime


FIXED_NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
FORBIDDEN_SENTINELS = (
    "meeting-title-sentinel",
    "transcript-sentinel",
    "private/audio/sentinel.mp3",
    "session-secret-sentinel",
    "voiceprint-label-sentinel",
    "voiceprint-vector-sentinel",
    "prompt-sentinel",
    "summary-sentinel",
)


class _NoOidc:
    async def begin(self, request):  # pragma: no cover - status never invokes OIDC.
        raise AssertionError(request)

    async def complete(self, request):  # pragma: no cover - status never invokes OIDC.
        raise AssertionError(request)


class _Journal:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def info(self, line: str) -> None:
        self.lines.append(line)


class _FakeFiles:
    def __init__(self, phases: dict[str, str] | None = None) -> None:
        self.phases = phases or {}

    def operator_snapshot(self) -> dict[str, str]:
        return dict(self.phases)


class _FakeLive:
    def __init__(self, meetings: dict[str, dict[str, object]] | None = None) -> None:
        self.meetings = meetings or {}
        self.queues: dict[str, int | bool] = {
            "batch": 0,
            "live_canonical": 0,
            "live_refinement": 0,
            "live_provisional": 0,
            "worker_busy": False,
        }
        self.runtime = SimpleNamespace(
            descriptor=SimpleNamespace(frame_samples=160, sample_rate=16000)
        )

    def operator_snapshot(self) -> dict[str, object]:
        return {"queues": dict(self.queues), "meetings": dict(self.meetings)}


class _MutableStore:
    def __init__(self) -> None:
        self.payload = {"accounts": [], "active_meetings": [], "audio": []}

    async def operator_snapshot(self) -> dict[str, object]:
        return json.loads(json.dumps(self.payload))


class _FakePresence:
    def snapshot(self, meeting_id: str) -> object:
        del meeting_id
        return SimpleNamespace(
            state="capturing",
            lanes={
                lane.value: SimpleNamespace(state="capturing", failure_code=None)
                for lane in LiveLane
            },
        )


class _FakeV2Sessions:
    def __init__(self) -> None:
        self.health = {lane: "active" for lane in LiveLane}

    def get(self, meeting_id: str) -> "_FakeV2Sessions":
        del meeting_id
        return self

    def snapshot(self) -> object:
        return SimpleNamespace(
            status="active",
            lanes={
                lane: SimpleNamespace(
                    health=health,
                    accepted_samples=160,
                    failure_code=("browser_track_ended" if health == "failed" else None),
                )
                for lane, health in self.health.items()
            },
        )


class _ShutdownRuntime:
    def __init__(self) -> None:
        self.descriptor = SimpleNamespace(
            frame_samples=160,
            sample_rate=16_000,
            bounds=SimpleNamespace(
                max_tape_bytes=32_000,
                max_queue_depth=4,
                max_retained_samples=32_000,
                max_frame_samples=160,
            ),
        )

    def _bind_publication_observer(self, observer: object) -> None:
        self.observer = observer

    def _unbind_publication_observer(self, observer: object) -> None:
        assert self.observer is observer

    def _operator_queue_snapshot(self) -> dict[str, int | bool]:
        return {
            "batch": 0,
            "live_canonical": 0,
            "live_refinement": 0,
            "live_provisional": 0,
            "worker_busy": False,
        }

    async def abort(self, session_id: str, reason: str) -> None:
        del session_id, reason


def _active_live_source() -> dict[str, object]:
    return {
        "accounts": [
            {
                "account_id": "person@example.com",
                "display_name": "Person",
                "enabled": 1,
                "sign_in_sessions": 1,
                "active_live": 1,
                "active_file": 0,
                "meetings": 1,
                "transcripts": 0,
                "voiceprints": 0,
                "final_summaries": 0,
                "audio_available_count": 0,
                "audio_available_bytes": 0,
                "audio_partial_count": 0,
                "audio_partial_bytes": 0,
                "audio_unavailable_count": 0,
            }
        ],
        "active_meetings": [
            {
                "account_id": "person@example.com",
                "meeting_id": "active-live-id",
                "mode": "live",
                "status": "active",
                "created_at_ms": int(FIXED_NOW.timestamp() * 1000),
            }
        ],
        "audio": [],
    }


async def _seed_content_store(database: Path) -> tuple[Phase2Store, str, str]:
    store = await Phase2Store.open(database)
    admitted = await seed_workspace(store, "workspace-a")
    assert admitted is not None
    account, _ = admitted
    workspace = store.workspace(account)
    live = await workspace.create_meeting("live")
    file = await workspace.create_meeting("file")
    await live.rename("meeting-title-sentinel")
    await live.commit_transcript(
        {"segments": [{"speaker": "Speaker_1", "text": "transcript-sentinel"}]}
    )
    now_ms = int(FIXED_NOW.timestamp() * 1000)
    async with store._mutation():
        await store._connection.execute(
            "INSERT INTO sign_in_sessions(session_id, account_id, created_at_ms) VALUES (?, ?, ?)",
            ("session-secret-sentinel", account.account_id, now_ms),
        )
        await store._connection.execute(
            """
            INSERT INTO meeting_audio(
                account_id, meeting_id, state, relative_path, byte_count, duration_ms,
                format, sample_rate_hz, channels, bit_rate_bps, updated_at_ms
            ) VALUES (?, ?, 'available', ?, 123, 1000, 'mp3', 16000, 1, 48000, ?)
            """,
            (account.account_id, file.meeting_id, "private/audio/sentinel.mp3", now_ms),
        )
        await store._connection.execute(
            """
            INSERT INTO voiceprints(
                account_id, voiceprint_id, label, revision, created_at_ms, updated_at_ms
            ) VALUES (?, 'voiceprint-id-sentinel', 'voiceprint-label-sentinel', 1, ?, ?)
            """,
            (account.account_id, now_ms, now_ms),
        )
        await store._connection.execute(
            """
            INSERT INTO voiceprint_samples(
                account_id, voiceprint_id, sample_id, vector, source_meeting_id, created_at_ms
            ) VALUES (?, 'voiceprint-id-sentinel', 'sample-sentinel', ?, ?, ?)
            """,
            (
                account.account_id,
                b"voiceprint-vector-sentinel",
                live.meeting_id,
                now_ms,
            ),
        )
        await store._connection.execute(
            """
            INSERT INTO llm_artifacts(
                account_id, meeting_id, artifact_id, kind, state, document_json,
                provenance_json, created_at_ms, updated_at_ms
            ) VALUES (?, ?, 'artifact-sentinel', 'final_summary', 'current', ?, ?, ?, ?)
            """,
            (
                account.account_id,
                live.meeting_id,
                json.dumps({"summary": "summary-sentinel"}),
                json.dumps({"prompt": "prompt-sentinel"}),
                now_ms,
                now_ms,
            ),
        )
    return store, live.meeting_id, file.meeting_id


def test_real_store_projection_reconciles_counts_and_excludes_content(tmp_path: Path):
    async def exercise() -> None:
        database = tmp_path / "moss.sqlite3"
        store, live_id, file_id = await _seed_content_store(database)
        journal = _Journal()
        live = _FakeLive(
            {
                live_id: {
                    "session_status": "active",
                    "pending_canonical": 2,
                    "pending_limit": 4,
                    "persistence_failure": None,
                    "terminal_error": None,
                }
            }
        )
        live.queues["live_canonical"] = 2
        operator = Phase2OperatorStatus(
            store,
            database_path=database,
            audio_root=tmp_path / "meetings",
            live=live,
            files=_FakeFiles({file_id: "running"}),
            now=lambda: FIXED_NOW,
            monotonic_ns=lambda: 1_000_000_000,
            journal_logger=journal,
        )
        try:
            await operator.start()
            status = await operator.snapshot()
            assert status["schema"] == OPERATOR_STATUS_SCHEMA
            assert status["capacity"] == {
                "live": {"active": 1, "limit": 4},
                "file": {"active": 1},
                "inference_worker": "busy",
                "queues": {
                    "live_canonical": 2,
                    "live_refinement": 0,
                    "live_provisional": 0,
                    "batch": 0,
                },
                "backpressured_meetings": 0,
            }
            account = status["accounts"][0]
            assert account["account_id"] == "workspace-a"
            assert account["sign_in_sessions"] == 2
            assert account["active_meetings"] == {"live": 1, "file": 1}
            assert account["logical"] == {
                "meetings": 2,
                "transcripts": 1,
                "voiceprints": 1,
                "final_summaries": 1,
            }
            assert account["audio"]["available"] == {"count": 1, "bytes": 123}
            active = {row["meeting_id"]: row for row in status["active_meetings"]}
            assert "work_phase" not in active[file_id]
            assert active[live_id]["capture"]["pending_canonical"] == {
                "count": 2,
                "limit": 4,
            }
            encoded = json.dumps(status, sort_keys=True)
            journal_text = "\n".join(journal.lines)
            for sentinel in FORBIDDEN_SENTINELS:
                assert sentinel not in encoded
                assert sentinel not in journal_text
            assert "person@example.com" not in journal_text
        finally:
            await store.close()

    asyncio.run(exercise())


def test_transition_journal_deduplicates_bounds_and_restarts_without_history(
    tmp_path: Path,
):
    async def exercise() -> None:
        store = _MutableStore()
        live = _FakeLive()
        journal = _Journal()
        operator = Phase2OperatorStatus(
            store,
            database_path=tmp_path / "moss.sqlite3",
            audio_root=tmp_path / "meetings",
            live=live,
            files=_FakeFiles(),
            now=lambda: FIXED_NOW,
            journal_logger=journal,
        )
        await operator.start()
        assert [json.loads(line)["code"] for line in journal.lines] == ["service_ready"]
        await operator.snapshot()
        assert len(journal.lines) == 1
        live.queues["live_canonical"] = 1
        await operator.snapshot(
            operator_mutation="accounts.revoke",
            mutation_outcome="succeeded",
        )
        codes = [json.loads(line)["code"] for line in journal.lines]
        assert codes[-2:] == ["queue_depth_changed", "operator_mutation"]
        assert all("@" not in line and "meeting_id" not in line for line in journal.lines)

        for index in range(OPERATOR_JOURNAL_LIMIT + 8):
            live.queues["live_canonical"] = index % 2
            await operator.snapshot()
        assert len(operator._recent_events) == OPERATOR_JOURNAL_LIMIT

        restarted_journal = _Journal()
        restarted = Phase2OperatorStatus(
            store,
            database_path=tmp_path / "moss.sqlite3",
            audio_root=tmp_path / "meetings",
            live=live,
            files=_FakeFiles(),
            now=lambda: FIXED_NOW,
            journal_logger=restarted_journal,
        )
        await restarted.start()
        assert [json.loads(line)["code"] for line in restarted_journal.lines] == [
            "service_ready"
        ]
        await restarted.stop()
        assert json.loads(restarted_journal.lines[-1])["code"] == "readiness_changed"

    asyncio.run(exercise())


def test_same_phase_lane_failure_emits_bounded_capture_health_edge(tmp_path: Path):
    async def exercise() -> None:
        store = _MutableStore()
        store.payload = _active_live_source()
        live = _FakeLive(
            {
                "active-live-id": {
                    "session_status": "active",
                    "pending_canonical": 0,
                    "pending_limit": 4,
                    "persistence_failure": None,
                    "terminal_error": None,
                }
            }
        )
        v2 = _FakeV2Sessions()
        journal = _Journal()
        operator = Phase2OperatorStatus(
            store,
            database_path=tmp_path / "moss.sqlite3",
            audio_root=tmp_path / "meetings",
            live=live,
            files=_FakeFiles(),
            v2_sessions=v2,
            helper_presence=_FakePresence(),
            now=lambda: FIXED_NOW,
            journal_logger=journal,
        )
        await operator.start()
        before = await operator.snapshot()
        assert before["active_meetings"][0]["capture"]["phase"] == "recording"
        before_events = len(journal.lines)

        v2.health[LiveLane.MICROPHONE] = "failed"
        after = await operator.snapshot()
        assert after["active_meetings"][0]["capture"]["phase"] == "recording"
        events = [json.loads(line) for line in journal.lines[before_events:]]
        assert [event["code"] for event in events] == ["capture_health_changed"]
        assert events[0]["context"] == {
            "starting": 0,
            "awaiting_audio": 0,
            "recording": 1,
            "stopped": 0,
            "failed": 0,
            "healthy_lanes": 1,
            "degraded_lanes": 0,
            "failed_lanes": 1,
            "inactive_lanes": 0,
            "unknown_lanes": 0,
        }
        assert "active-live-id" not in journal.lines[-1]
        assert "person@example.com" not in journal.lines[-1]

    asyncio.run(exercise())


def test_allowlist_serializer_rejects_content_fields_and_human_uses_same_projection():
    with pytest.raises(OperatorProjectionError, match="title"):
        serialize_operator_payload(
            "status",
            {"schema": OPERATOR_STATUS_SCHEMA, "title": "forbidden"},
        )
    with pytest.raises(OperatorProjectionError, match="meeting_id"):
        serialize_operator_payload(
            "event",
            {
                "schema": OPERATOR_EVENT_SCHEMA,
                "meeting_id": "forbidden",
            },
        )
    with pytest.raises(OperatorProjectionError, match="context"):
        serialize_operator_payload(
            "event",
            {
                "schema": OPERATOR_EVENT_SCHEMA,
                "sequence": 0,
                "occurred_at_utc": "2026-08-28T12:00:00Z",
                "kind": "operator_mutation",
                "code": "operator_mutation",
                "severity": "info",
                "terminal": False,
                "retryable": False,
                "occurrence_count": 1,
                "context": {
                    "command": "accounts.revoke",
                    "outcome": "succeeded",
                    "state": "summary sentinel",
                },
            },
        )


def test_failed_operator_command_projects_bounded_safe_error_context(tmp_path: Path):
    class FailingLifecycle:
        async def revoke_account(self, email: str):
            del email
            raise ValueError("raw failure with transcript-sentinel")

        async def list_accounts(self):
            return []

    async def exercise() -> None:
        socket = Path("/tmp") / f"moss-i19-failure-{os.getpid()}-{time.time_ns()}.sock"
        journal = _Journal()
        operator = Phase2OperatorStatus(
            _MutableStore(),
            database_path=tmp_path / "moss.sqlite3",
            audio_root=tmp_path / "meetings",
            live=None,
            files=None,
            now=lambda: FIXED_NOW,
            journal_logger=journal,
        )
        await operator.start()
        server = Phase2ControlServer(socket, FailingLifecycle(), operator)
        await server.start()
        try:
            with pytest.raises(Phase2ControlError, match="invalid_request"):
                await request_control(socket, "accounts.revoke", "person@example.com")
            status = await request_control(socket, "status")
            assert status["latest_error"] == {
                "occurred_at_utc": "2026-08-28T12:00:00.000Z",
                "subsystem": "operator_control",
                "code": "invalid_request",
                "severity": "error",
                "terminal": False,
                "retryable": True,
                "occurrence_count": 1,
                "context": {"command": "accounts.revoke"},
            }
            injected = json.loads(json.dumps(status))
            injected["latest_error"]["context"]["state"] = "summary sentinel"
            with pytest.raises(OperatorProjectionError, match="context"):
                serialize_operator_payload("status", injected)
            wrong_scope = json.loads(json.dumps(status))
            wrong_scope["state"] = "ready"
            with pytest.raises(OperatorProjectionError, match="status fields"):
                serialize_operator_payload("status", wrong_scope)
            serialized = json.dumps(status, sort_keys=True) + "\n" + "\n".join(journal.lines)
            assert "transcript-sentinel" not in serialized
            assert "person@example.com" not in "\n".join(journal.lines)
        finally:
            await server.stop()
            await operator.stop()

    asyncio.run(exercise())


def test_failed_active_live_revoke_keeps_uds_status_and_shutdown_snapshot_safe(
    tmp_path: Path,
):
    async def exercise() -> None:
        socket = Path("/tmp") / f"moss-i19-live-failure-{os.getpid()}-{time.time_ns()}.sock"
        store = _MutableStore()
        store.payload = _active_live_source()
        live = _FakeLive(
            {
                "active-live-id": {
                    "session_status": "active",
                    "pending_canonical": 0,
                    "pending_limit": 4,
                    "persistence_failure": None,
                    "terminal_error": None,
                    "transcript": "transcript-sentinel",
                    "source_url": "https://source.invalid/sentinel",
                }
            }
        )
        journal = _Journal()
        operator = Phase2OperatorStatus(
            store,
            database_path=tmp_path / "moss.sqlite3",
            audio_root=tmp_path / "meetings",
            live=live,
            files=_FakeFiles(),
            now=lambda: FIXED_NOW,
            journal_logger=journal,
        )

        class FailedRevokeLifecycle:
            async def revoke_account(self, email: str) -> bool:
                assert email == "person@example.com"
                live.meetings["active-live-id"]["persistence_failure"] = (
                    "Account revoked by operator"
                )
                raise AccountLifecycleSettlementError(
                    "raw failure transcript-sentinel"
                )

        await operator.start()
        server = Phase2ControlServer(socket, FailedRevokeLifecycle(), operator)
        await server.start()
        try:
            with pytest.raises(Phase2ControlError, match="account_settlement_failed"):
                await request_control(socket, "accounts.revoke", "person@example.com")
            status = await request_control(socket, "status")
            assert status["active_meetings"][0]["safe_error"] == {
                "subsystem": "persistence",
                "code": "meeting_authority_revoked",
                "severity": "error",
                "terminal": False,
                "retryable": True,
            }
            assert status["latest_error"]["code"] == "meeting_authority_revoked"
            safe_error = status["active_meetings"][0]["safe_error"]
            rendered = render_operator_status(status)
            assert (
                "safe_error=subsystem=persistence code=meeting_authority_revoked "
                "severity=error terminal=false retryable=true"
            ) in rendered
            for key in ("subsystem", "code", "severity", "terminal", "retryable"):
                expected = str(safe_error[key]).lower() if isinstance(safe_error[key], bool) else str(safe_error[key])
                assert f"{key}={expected}" in rendered
        finally:
            await server.stop()

        await operator.stop()
        final_status = await operator.snapshot()
        assert final_status["readiness"] == "stopping"
        assert final_status["latest_error"]["code"] == "meeting_authority_revoked"
        serialized = json.dumps(final_status, sort_keys=True) + "\n" + "\n".join(
            journal.lines
        )
        for forbidden in (
            "Account revoked by operator",
            "raw failure transcript-sentinel",
            "transcript-sentinel",
            "https://source.invalid/sentinel",
            "person@example.com",
            "active-live-id",
        ):
            if forbidden == "person@example.com" or forbidden == "active-live-id":
                assert forbidden not in "\n".join(journal.lines)
            else:
                assert forbidden not in serialized

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("service shutdown", "service_shutdown"),
        ("unsupported prose transcript-sentinel", "live_persistence_failed"),
    ],
)
def test_lifecycle_persistence_prose_maps_to_safe_error_token(
    tmp_path: Path,
    reason: str,
    expected: str,
):
    async def exercise() -> None:
        store = _MutableStore()
        store.payload = _active_live_source()
        live = _FakeLive(
            {
                "active-live-id": {
                    "session_status": "active",
                    "pending_canonical": 0,
                    "pending_limit": 4,
                    "persistence_failure": reason,
                    "terminal_error": None,
                }
            }
        )
        journal = _Journal()
        operator = Phase2OperatorStatus(
            store,
            database_path=tmp_path / "moss.sqlite3",
            audio_root=tmp_path / "meetings",
            live=live,
            files=_FakeFiles(),
            now=lambda: FIXED_NOW,
            journal_logger=journal,
        )
        await operator.start()
        await operator.stop()
        status = await operator.snapshot()
        assert status["latest_error"]["code"] == expected
        emitted = json.dumps(status, sort_keys=True) + "\n" + "\n".join(journal.lines)
        assert reason not in emitted

    asyncio.run(exercise())


def test_runtime_exception_class_code_keeps_uds_status_available_and_safe(
    tmp_path: Path,
):
    async def exercise() -> None:
        failure = LiveServiceRuntime._failure_from_exception(
            object(), RuntimeError("raw terminal transcript-sentinel")
        )
        assert failure.code == "RuntimeError"
        store = _MutableStore()
        store.payload = _active_live_source()
        live = _FakeLive(
            {
                "active-live-id": {
                    "session_status": "failed",
                    "pending_canonical": 0,
                    "pending_limit": 4,
                    "persistence_failure": None,
                    "terminal_error": {
                        "subsystem": "live",
                        "code": failure.code,
                        "severity": "error",
                        "terminal": True,
                        "retryable": failure.retryable,
                    },
                }
            }
        )
        journal = _Journal()
        operator = Phase2OperatorStatus(
            store,
            database_path=tmp_path / "moss.sqlite3",
            audio_root=tmp_path / "meetings",
            live=live,
            files=_FakeFiles(),
            now=lambda: FIXED_NOW,
            journal_logger=journal,
        )
        socket = Path("/tmp") / f"moss-i19-terminal-{os.getpid()}-{time.time_ns()}.sock"
        server = Phase2ControlServer(socket, SimpleNamespace(), operator)
        await operator.start()
        await server.start()
        try:
            status = await request_control(socket, "status")
            assert status["latest_error"]["code"] == "live_terminal_failure"
            assert status["active_meetings"][0]["safe_error"]["code"] == (
                "live_terminal_failure"
            )
            emitted = json.dumps(status, sort_keys=True) + "\n" + "\n".join(journal.lines)
            assert "RuntimeError" not in emitted
            assert "raw terminal transcript-sentinel" not in emitted
        finally:
            await server.stop()

        live.meetings["active-live-id"]["terminal_error"]["code"] = (
            "canonical_decode_failed"
        )
        preserved = await operator.snapshot()
        assert preserved["latest_error"]["code"] == "canonical_decode_failed"

    asyncio.run(exercise())


def test_post_mutation_observation_failure_does_not_rewrite_account_result(tmp_path: Path):
    class Lifecycle:
        async def revoke_account(self, email: str):
            return True

    class FailedObservation:
        async def snapshot(self, **kwargs: object):
            del kwargs
            raise RuntimeError("observability unavailable")

    async def exercise() -> None:
        socket = Path("/tmp") / f"moss-i19-observe-{os.getpid()}-{time.time_ns()}.sock"
        server = Phase2ControlServer(socket, Lifecycle(), FailedObservation())
        await server.start()
        try:
            assert await request_control(
                socket,
                "accounts.revoke",
                "person@example.com",
            ) == {"account_id": "person@example.com", "revoked": True}
        finally:
            await server.stop()

    asyncio.run(exercise())


def test_status_uses_existing_private_socket_and_cli_human_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i19-{os.getpid()}-{time.time_ns()}.sock"
    app = create_phase2_app(
        database_path=database,
        meeting_audio_root=tmp_path / "meetings",
        control_socket_path=socket,
    )
    with TestClient(app, base_url="https://moss.test"):
        assert stat.S_IMODE(socket.stat().st_mode) == 0o600
        status = asyncio.run(request_control(socket, "status"))
        assert status["schema"] == OPERATOR_STATUS_SCHEMA
        assert status["readiness"] == "ready"
        assert "Readiness: ready" in render_operator_status(status)

        admin_main(["--socket", str(socket), "status", "--json"])
        machine = json.loads(capsys.readouterr().out)
        assert machine["schema"] == OPERATOR_STATUS_SCHEMA
        admin_main(["--socket", str(socket), "status"])
        human = capsys.readouterr().out
        assert "Readiness: ready" in human
        assert "Queues:" in human
    assert not socket.exists()


def test_shutdown_journal_observes_service_owned_revoke_after_handler_cancellation(
    tmp_path: Path,
):
    async def provision(database: Path) -> None:
        store = await Phase2Store.open(database)
        try:
            assert await seed_workspace(store, "account-a") is not None
        finally:
            await store.close()

    database = tmp_path / "moss.sqlite3"
    asyncio.run(provision(database))
    socket = Path("/tmp") / f"moss-i19-shutdown-{os.getpid()}-{time.time_ns()}.sock"
    app = create_phase2_app(
        database_path=database,
        meeting_audio_root=tmp_path / "meetings",
        control_socket_path=socket,
    )
    entered = threading.Event()
    release = threading.Event()
    request_result: list[object] = []

    with TestClient(app, base_url="https://moss.test"):
        store = app.state.phase2_store
        original_finalize = store.finalize_account_revoke

        async def held_finalize(target):
            entered.set()
            assert await asyncio.to_thread(release.wait, 5)
            return await original_finalize(target)

        store.finalize_account_revoke = held_finalize

        def request_revoke() -> None:
            try:
                request_result.append(
                    asyncio.run(
                        request_control(socket, "accounts.revoke", "account-a")
                    )
                )
            except BaseException as exc:
                request_result.append(exc)

        requester = threading.Thread(target=request_revoke)
        requester.start()
        assert entered.wait(timeout=2)

        def release_after_socket_removal() -> None:
            deadline = time.monotonic() + 3
            while socket.exists() and time.monotonic() < deadline:
                time.sleep(0.005)
            release.set()

        releaser = threading.Thread(target=release_after_socket_removal)
        releaser.start()

    requester.join(timeout=2)
    releaser.join(timeout=2)
    assert len(request_result) == 1
    assert isinstance(request_result[0], Phase2ControlError)
    events = list(app.state.phase2_operator_status._recent_events)
    authority = [event for event in events if event["kind"] == "account_authority"]
    assert authority[-1]["context"] == {
        "enabled_accounts": 0,
        "sign_in_sessions": 0,
    }
    assert events[-1]["kind"] in {"readiness", "account_authority"}
    assert any(
        event["kind"] == "readiness" and event["context"] == {"state": "stopping"}
        for event in events
    )
    assert "person@example.com" not in json.dumps(events, sort_keys=True)


def test_lifespan_observes_held_live_shutdown_failure_before_final_status(
    tmp_path: Path,
):
    async def provision(database: Path):
        store = await Phase2Store.open(database)
        try:
            admitted = await seed_workspace(store, "account-a")
            assert admitted is not None
            return admitted[0]
        finally:
            await store.close()

    database = tmp_path / "moss.sqlite3"
    account = asyncio.run(provision(database))
    socket = Path("/tmp") / f"moss-i19-owner-stop-{os.getpid()}-{time.time_ns()}.sock"
    runtime = _ShutdownRuntime()
    app = create_phase2_app(
        database_path=database,
        live_runtime_factory=lambda: runtime,
        live_helper_lease_seconds=30.0,
        meeting_audio_root=tmp_path / "meetings",
        control_socket_path=socket,
    )
    trace: list[str] = []
    entered = threading.Event()
    release = threading.Event()

    with TestClient(app, base_url="https://moss.test") as client:
        async def create_live_meeting():
            workspace = app.state.phase2_store.workspace(account)
            return await workspace.create_meeting("live")

        handle = client.portal.call(create_live_meeting)
        binding = SimpleNamespace(
            terminal_persisted=False,
            public_snapshot=None,
            persistence_failure=None,
            queue=SimpleNamespace(put_nowait=lambda value: None),
            worker=None,
        )
        live = app.state.phase2_live
        live._bindings[handle.meeting_id] = binding

        async def held_failed_fence(target: object, reason: str) -> None:
            assert target is binding
            assert reason == "service shutdown"
            trace.append("live_shutdown_started")
            entered.set()
            assert await asyncio.to_thread(release.wait, 5)
            binding.persistence_failure = reason
            trace.append("live_shutdown_settled")

        live._fence = held_failed_fence
        operator = app.state.phase2_operator_status
        original_stop = operator.stop

        async def traced_operator_stop() -> None:
            trace.append("operator_stop_started")
            await original_stop()
            trace.append("operator_stop_finished")

        operator.stop = traced_operator_stop

        def release_settlement() -> None:
            assert entered.wait(timeout=5)
            assert "operator_stop_started" not in trace
            release.set()

        releaser = threading.Thread(target=release_settlement)
        releaser.start()

    releaser.join(timeout=2)
    assert not releaser.is_alive()
    assert trace == [
        "live_shutdown_started",
        "live_shutdown_settled",
        "operator_stop_started",
        "operator_stop_finished",
    ]
    assert operator._readiness == "stopping"
    assert operator._latest_error["code"] == "service_shutdown"
    events = list(operator._recent_events)
    assert any(
        event["kind"] == "safe_error"
        and event["context"] == {"subsystem": "persistence", "state": "service_shutdown"}
        for event in events
    )
    assert "service shutdown" not in json.dumps(events, sort_keys=True)
    assert not socket.exists()


class _HeldAcquirer:
    def __init__(self) -> None:
        self.release = asyncio.Event()

    async def acquire(self, source_url: str, staging_dir: Path) -> Path:
        del source_url
        await self.release.wait()
        path = staging_dir / "input.media"
        path.write_bytes(b"media")
        return path


class _HeldRunner:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def transcribe(self, input_path: Path, **options: object):
        del input_path, options
        self.started.set()
        assert self.release.wait(timeout=5)
        return SimpleNamespace(text="[0][S01]words[1]")


class _FileHandle:
    meeting_id = "file-meeting-id"
    owner_key = ("account-id", 0)

    async def commit_transcript(self, document: object) -> None:
        del document

    async def record_audio_unavailable(self) -> None:
        return None

    async def finish(self, status: str) -> None:
        del status


class _Workspace:
    async def create_meeting(self, mode: str) -> _FileHandle:
        assert mode == "file"
        return _FileHandle()


def test_file_registry_reports_url_acquisition_queued_then_inference_running(tmp_path: Path):
    async def exercise() -> None:
        runner = _HeldRunner()
        acquirer = _HeldAcquirer()
        tasks = FileMeetingTasks(
            runner,
            tmp_path / "file-work",
            url_acquirer=acquirer,
        )
        handle = await tasks.accept_url(_Workspace(), "https://example.com/audio.wav")
        assert tasks.operator_snapshot() == {handle.meeting_id: "queued"}
        acquirer.release.set()
        assert await asyncio.to_thread(runner.started.wait, 2)
        for _ in range(100):
            if tasks.operator_snapshot().get(handle.meeting_id) == "running":
                break
            await asyncio.sleep(0.001)
        assert tasks.operator_snapshot() == {handle.meeting_id: "running"}
        runner.release.set()
        await tasks.stop()
        assert tasks.operator_snapshot() == {}

    asyncio.run(exercise())
