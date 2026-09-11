"""Workspace persistence, lifecycle and packaging regressions.

Google/OIDC/allowlist/logout tests were retired by ADR-0013. The replacement
bootstrap, privacy, old-schema and revocation contract lives in test_browser_workspace.py.
"""
from __future__ import annotations

import asyncio
import os
import stat
import subprocess
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from _browser_workspace_fixtures import seed_workspace

from moss_transcribe_diarize.app import phase2, phase2_web_cli
from moss_transcribe_diarize.app.phase2 import (
    DEFAULT_PHASE2_DATABASE_PATH, Phase2Store, SchemaVersionError, create_phase2_app,
)
from moss_transcribe_diarize.app.phase2_admin import parse_args as parse_admin_args
from moss_transcribe_diarize.app.phase2_control import (
    DEFAULT_PHASE2_CONTROL_SOCKET_PATH, Phase2ControlError, Phase2ControlServer, request_control,
)
from moss_transcribe_diarize.app.phase2_lifecycle import AccountLifecycle, MeetingLifecycleSettlementError


def control_socket_path() -> Path:
    return Path("/tmp") / f"moss-workspace-{os.getpid()}-{time.time_ns()}.sock"


def make_app(database, *, control_socket=None):
    return create_phase2_app(database_path=database, control_socket_path=control_socket)


def test_request_reads_wait_for_terminal_transaction_commit_or_rollback(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"

    async def exercise() -> None:
        store = await Phase2Store.open(database)
        original_execute = store._connection.execute
        try:
            admitted = await seed_workspace(store, "sub-a")
            assert admitted is not None
            account, session_id = admitted
            workspace = store.workspace(account)
            handle = await workspace.create_meeting("live")
            prefix = {"segments": [{"speaker": "S01", "text": "durable prefix"}]}
            terminal = {"segments": [{"speaker": "S01", "text": "terminal final"}]}
            assert await handle.commit_transcript(prefix) == 1

            status_updated = asyncio.Event()
            release = asyncio.Event()
            fail_after_status = True

            async def held_execute(sql: str, parameters: object = None):
                cursor = (
                    await original_execute(sql)
                    if parameters is None
                    else await original_execute(sql, parameters)
                )
                normalized = " ".join(sql.lower().split())
                if (
                    normalized.startswith("update meetings set status = ?, updated_at_ms = ?")
                    and isinstance(parameters, tuple)
                    and parameters[0] == "completed"
                    and parameters[3] == handle.meeting_id
                ):
                    status_updated.set()
                    await release.wait()
                    if fail_after_status:
                        raise RuntimeError("injected rollback between terminal writes")
                return cursor

            store._connection.execute = held_execute

            async def concurrent_reads():
                snapshot_task = asyncio.create_task(handle.snapshot())
                list_task = asyncio.create_task(workspace.list_meetings())
                auth_task = asyncio.create_task(store.account_for_session(session_id))
                await asyncio.sleep(0)
                assert not snapshot_task.done()
                assert not list_task.done()
                assert not auth_task.done()
                return snapshot_task, list_task, auth_task

            rollback_task = asyncio.create_task(
                handle.finish_with_transcript(terminal, "completed")
            )
            await status_updated.wait()
            rollback_reads = await concurrent_reads()
            release.set()
            with pytest.raises(RuntimeError, match="injected rollback"):
                await rollback_task
            rolled_back, rollback_list, rollback_account = await asyncio.gather(*rollback_reads)
            assert (rolled_back.status, rolled_back.transcript_version, rolled_back.transcript) == (
                "active",
                1,
                prefix,
            )
            assert rollback_list == [rolled_back]
            assert rollback_account == account

            status_updated = asyncio.Event()
            release = asyncio.Event()
            fail_after_status = False
            commit_task = asyncio.create_task(
                handle.finish_with_transcript(terminal, "completed")
            )
            await status_updated.wait()
            commit_reads = await concurrent_reads()
            release.set()
            assert await commit_task == 2
            committed, commit_list, commit_account = await asyncio.gather(*commit_reads)
            assert (committed.status, committed.transcript_version, committed.transcript) == (
                "completed",
                2,
                terminal,
            )
            assert commit_list == [committed]
            assert commit_account == account
        finally:
            store._connection.execute = original_execute
            await store.close()

    asyncio.run(exercise())


def test_schema_v2_contains_exact_ownership_tables_and_settings(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"

    async def exercise():
        store = await Phase2Store.open(database)
        try:
            assert await store.user_version() == 2
            assert await store.table_names() == {
                "accounts",
                "sign_in_sessions",
                "meetings",
                "meeting_transcripts",
                "meeting_speakers",
                "meeting_audio",
                "voiceprints",
                "voiceprint_samples",
                "llm_artifacts",
            }
            cursor = await store._connection.execute("PRAGMA table_info(meetings)")
            meeting_columns = {row[1] for row in await cursor.fetchall()}
            await cursor.close()
            assert "title_source" in meeting_columns
            cursor = await store._connection.execute("PRAGMA table_info(voiceprints)")
            voiceprint_columns = {row[1] for row in await cursor.fetchall()}
            await cursor.close()
            assert {"embedder_id", "embedding_dimension"} <= voiceprint_columns
            settings = await store.sqlite_settings()
            assert settings == {"journal_mode": "wal", "foreign_keys": 1, "synchronous": 2}
        finally:
            await store.close()

    asyncio.run(exercise())


def test_existing_non_v2_database_is_refused_without_mutating_its_bytes_or_creating_sidecars(
    tmp_path: Path,
):
    database = tmp_path / "not-v1.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE sentinel(value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel(value) VALUES ('preserve me')")
        connection.execute("PRAGMA user_version = 7")
        connection.commit()
    finally:
        connection.close()
    before = database.read_bytes()
    sidecars = [database.with_name(f"{database.name}{suffix}") for suffix in ("-wal", "-shm", "-journal")]
    assert not any(path.exists() for path in sidecars)

    async def exercise():
        with pytest.raises(SchemaVersionError, match="user_version=7"):
            await Phase2Store.open(database)

    asyncio.run(exercise())
    assert database.read_bytes() == before
    assert not any(path.exists() for path in sidecars)


def test_wrong_sqlite_runtime_is_refused_before_database_or_parent_creation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    database = tmp_path / "not-created" / "phase2.sqlite3"
    monkeypatch.setattr(phase2, "REQUIRED_SQLITE_RUNTIME", "3.53.4")
    monkeypatch.setattr(phase2.sqlite3, "sqlite_version", "3.53.1")

    with pytest.raises(phase2.SqliteRuntimeError, match="exactly 3.53.4"):
        asyncio.run(Phase2Store.open(database))

    assert not database.parent.exists()


def test_composite_ownership_foreign_keys_reject_cross_account_children(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"

    async def exercise():
        store = await Phase2Store.open(database)
        try:
            account_a, _ = (await seed_workspace(store, "sub-a"))
            account_b, _ = (await seed_workspace(store, "sub-b"))
            meeting_b = await store.workspace(account_b).create_meeting("file")
            with pytest.raises(sqlite3.IntegrityError):
                await store._connection.execute(
                    """
                    INSERT INTO meeting_transcripts(account_id, meeting_id, document_json, version, updated_at_ms)
                    VALUES (?, ?, '{}', 1, 1)
                    """,
                    (account_a.account_id, meeting_b.meeting_id),
                )
            await store._connection.rollback()
        finally:
            await store.close()

    asyncio.run(exercise())


def test_product_app_startup_interrupts_existing_active_meetings(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"

    async def create_active_meeting() -> None:
        store = await Phase2Store.open(database)
        try:
            account, _ = (await seed_workspace(store, "sub-a"))
            await store.workspace(account).create_meeting("live")
        finally:
            await store.close()

    asyncio.run(create_active_meeting())
    app = make_app(database)
    with TestClient(app, base_url="https://moss.test"):
        pass

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT status FROM meetings").fetchone()[0] == "interrupted"
    finally:
        connection.close()


def test_control_socket_is_private_single_owner_and_removed_on_shutdown(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    socket = control_socket_path()
    app = make_app(database, control_socket=socket)

    with TestClient(app, base_url="https://moss.test"):
        assert stat.S_IMODE(socket.stat().st_mode) == 0o600
        contender = make_app(tmp_path / "contender.sqlite3", control_socket=socket)
        with pytest.raises(Phase2ControlError, match="Another product process"):
            with TestClient(contender, base_url="https://moss.test"):
                pass
        assert asyncio.run(request_control(socket, "accounts.list")) == []

    assert not socket.exists()
    with pytest.raises(Phase2ControlError, match="unavailable"):
        asyncio.run(request_control(socket, "accounts.list"))


def test_control_socket_refuses_non_socket_path_without_mutation(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    control_path = control_socket_path()
    control_path.write_text("operator-owned", encoding="utf-8")
    app = make_app(database, control_socket=control_path)

    with pytest.raises(Phase2ControlError, match="not a Unix socket"):
        with TestClient(app, base_url="https://moss.test"):
            pass
    assert control_path.read_text(encoding="utf-8") == "operator-owned"


def test_control_shutdown_cancels_held_command_and_removes_socket() -> None:
    socket = control_socket_path()

    class HeldLifecycle:
        def __init__(self) -> None:
            self.started = asyncio.Event()

        async def revoke_account(self, email: str) -> bool:
            del email
            self.started.set()
            await asyncio.Event().wait()
            return True

    async def exercise() -> None:
        lifecycle = HeldLifecycle()
        server = Phase2ControlServer(socket, lifecycle)
        await server.start()
        request = asyncio.create_task(
            request_control(socket, "accounts.revoke", "person@example.com")
        )
        await lifecycle.started.wait()
        await asyncio.wait_for(server.stop(), timeout=1.0)
        result = await asyncio.gather(request, return_exceptions=True)
        assert len(result) == 1 and isinstance(result[0], Phase2ControlError)
        assert not socket.exists()

    asyncio.run(exercise())


def test_mtd_admin_account_commands_share_the_product_default_control_socket():
    with pytest.raises(SystemExit):
        parse_admin_args(["accounts", "allow", "workspace-a"])
    assert parse_admin_args(["accounts", "list"]).socket == str(
        DEFAULT_PHASE2_CONTROL_SOCKET_PATH
    )
    assert parse_admin_args(["accounts", "revoke", "person@example.com"]).socket == str(
        DEFAULT_PHASE2_CONTROL_SOCKET_PATH
    )


def test_mtd_admin_meeting_interrupt_uses_one_content_free_control_command():
    parsed = parse_admin_args(["meetings", "interrupt", "opaque-meeting"])
    assert parsed.socket == str(DEFAULT_PHASE2_CONTROL_SOCKET_PATH)
    assert parsed.area == "meetings"
    assert parsed.command == "interrupt"
    assert parsed.meeting_id == "opaque-meeting"

    socket = control_socket_path()

    class Lifecycle:
        async def interrupt_meeting(self, meeting_id: str) -> bool:
            assert meeting_id == "opaque-meeting"
            return True

    async def exercise() -> None:
        server = Phase2ControlServer(socket, Lifecycle())
        await server.start()
        try:
            assert await request_control(
                socket,
                "meetings.interrupt",
                meeting_id="opaque-meeting",
            ) == {"meeting_id": "opaque-meeting", "interrupted": True}
        finally:
            await server.stop()

    asyncio.run(exercise())


def test_active_meeting_without_process_owner_fails_interrupt_instead_of_claiming_no_change():
    socket = control_socket_path()

    class Lifecycle:
        async def interrupt_meeting(self, meeting_id: str) -> bool:
            assert meeting_id == "active-without-owner"
            raise MeetingLifecycleSettlementError("content sentinel must not cross")

    async def exercise() -> None:
        server = Phase2ControlServer(socket, Lifecycle())
        await server.start()
        try:
            with pytest.raises(Phase2ControlError) as failure:
                await request_control(
                    socket,
                    "meetings.interrupt",
                    meeting_id="active-without-owner",
                )
            assert str(failure.value) == "meeting_settlement_failed"
            assert "content sentinel" not in str(failure.value)
        finally:
            await server.stop()

    asyncio.run(exercise())


def test_mtd_admin_help_does_not_import_optional_model_runtime():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys

class NoModelRuntime:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'torch' or fullname.startswith('torch.'):
            raise AssertionError('mtd-admin imported torch')
        if fullname == 'transformers' or fullname.startswith('transformers.'):
            raise AssertionError('mtd-admin imported transformers')
        return None

sys.meta_path.insert(0, NoModelRuntime())
from moss_transcribe_diarize.app.phase2_admin import main
main(['--help'])
""",
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Host-local MOSS Phase-2 administration" in result.stdout


def test_packaged_phase2_tls_entrypoint_constructs_the_account_app(monkeypatch, tmp_path: Path):
    seen: dict[str, object] = {}
    file_runner = object()
    live_runtime_factory = object()
    app = object()

    monkeypatch.setattr(phase2_web_cli, "_build_file_runner", lambda args: file_runner)
    monkeypatch.setattr(
        phase2_web_cli,
        "_build_live_runtime_factory",
        lambda args, received_file_runner: (
            live_runtime_factory
            if received_file_runner is file_runner
            else pytest.fail("Live terminal finalizer did not receive the File runner")
        ),
    )

    def fake_create_app(**kwargs: object):
        seen["app"] = kwargs
        return app

    monkeypatch.setattr(phase2_web_cli, "create_phase2_app", fake_create_app)

    class FakeConfig(dict):
        def get_loop_factory(self):
            seen["uvicorn_loop_selected"] = True
            return None

    class FakeUvicorn:
        @staticmethod
        def Config(received_app: object, **kwargs: object):
            seen["uvicorn"] = FakeConfig(app=received_app, **kwargs)
            return seen["uvicorn"]

    from moss_transcribe_diarize.app import tls_reload

    async def fake_serve(config):
        assert config is seen["uvicorn"]
        seen["reload_enabled"] = True

    monkeypatch.setattr(tls_reload, "serve_with_certificate_reload", fake_serve)

    monkeypatch.setitem(sys.modules, "uvicorn", FakeUvicorn)
    phase2_web_cli.main(
        [
            "--tls-certfile",
            "/etc/moss/cert.pem",
            "--tls-keyfile",
            "/etc/moss/key.pem",
            "--llm-upstreams",
            "[]",
            "--prompt",
            "deployed prompt",
            "--max-len",
            "16384",
            "--max-new-tokens",
            "12000",
            "--decoding",
            "greedy",
            "--temperature",
            "1.0",
            "--live-provider-manifest",
            "/etc/moss/live-provider.json",
            "--live-helper-lease-seconds",
            "30",
        ]
    )

    assert seen["app"] == {
        "database_path": DEFAULT_PHASE2_DATABASE_PATH,
        "llm_upstreams": "[]",
        "file_runner": file_runner,
        "file_work_root": phase2_web_cli.DEFAULT_PHASE2_FILE_WORK_ROOT,
        "meeting_audio_root": phase2_web_cli.DEFAULT_PHASE2_MEETING_AUDIO_ROOT,
        "file_inference_options": {
            "prompt": "deployed prompt",
            "max_length": 16384,
            "max_new_tokens": 12000,
            "decoding": "greedy",
            "temperature": 1.0,
        },
        "live_runtime_factory": live_runtime_factory,
        "live_helper_lease_seconds": 30.0,
        "control_socket_path": DEFAULT_PHASE2_CONTROL_SOCKET_PATH,
    }
    assert seen["uvicorn"] == {
        "app": app,
        "host": "0.0.0.0",
        "port": 7861,
        "ssl_certfile": "/etc/moss/cert.pem",
        "ssl_keyfile": "/etc/moss/key.pem",
        "proxy_headers": False,
        "access_log": False,
    }
    assert seen["reload_enabled"] is True
    assert seen["uvicorn_loop_selected"] is True


def test_phase2_live_cli_keeps_live_decode_separate_and_shares_file_only_with_finalizer(
    monkeypatch,
):
    from moss_transcribe_diarize.app import live_provider_bundle, runner_composition

    seen: dict[str, object] = {}
    config = object()
    file_runner = object()
    runtime_factory = object()

    class Config:
        @staticmethod
        def from_manifest(path: str):
            seen["manifest"] = path
            return config

    class LiveRunner:
        def __init__(self, **kwargs):
            seen["live_args"] = kwargs

    monkeypatch.setattr(runner_composition, "LazyLiveRunner", LiveRunner)
    monkeypatch.setattr(
        runner_composition,
        "build_terminal_finalizer",
        lambda **kwargs: ("terminal", kwargs),
    )

    def build(received_config, canonical_runner, **kwargs):
        seen["bundle"] = (received_config, canonical_runner, kwargs)
        return runtime_factory

    monkeypatch.setattr(live_provider_bundle, "LiveProviderBundleConfig", Config)
    monkeypatch.setattr(live_provider_bundle, "build_live_runtime_factory", build)
    args = SimpleNamespace(
        live_provider_manifest="/etc/moss/live-provider.json",
        live_helper_lease_seconds=30.0,
        model="fake-model",
        device="cpu",
        dtype="float32",
        backend="hf",
        vllm_base_url=None,
        vllm_model=None,
        vllm_api_key="EMPTY",
        vllm_timeout=600.0,
        prompt="prompt",
        max_len=16384,
        max_new_tokens=12000,
        decoding="greedy",
        temperature=1.0,
    )

    assert phase2_web_cli._build_live_runtime_factory(args, file_runner) is runtime_factory
    received_config, canonical_runner, kwargs = seen["bundle"]
    assert received_config is config
    assert isinstance(canonical_runner, LiveRunner)
    assert canonical_runner is not file_runner
    assert kwargs == {
        "draft_lane_seconds": None,
        "terminal_finalizer": (
            "terminal",
            {
                "runner": file_runner,
                "prompt": "prompt",
                "max_length": 16384,
                "max_new_tokens": 12000,
                "decoding": "greedy",
                "temperature": 1.0,
                "max_length_cap": None,
            },
        ),
    }
