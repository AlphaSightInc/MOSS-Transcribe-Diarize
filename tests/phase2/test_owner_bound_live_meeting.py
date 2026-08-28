from __future__ import annotations

import asyncio
import base64
import json
import os
import sqlite3
import stat
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_endpoint import (
    EndpointPolicy,
    EndpointPolicyConfig,
    SpeechObservation,
)
from moss_transcribe_diarize.app.live_helper_presence import HELPER_HEALTH_SCHEMA
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceRuntime,
    _ManualTerminalScheduler,
    hash_config,
)
from moss_transcribe_diarize.app.live_session import (
    LIVE_SAMPLE_RATE,
    AudioFrame,
    FrozenSpan,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    LiveSessionClosed,
)
from moss_transcribe_diarize.app.live_transcript_convergence import TerminalTranscriptFinalizer
from moss_transcribe_diarize.app.phase2 import (
    GoogleIdentity,
    Phase2Store,
    SESSION_COOKIE,
    create_phase2_app,
)
from moss_transcribe_diarize.app.phase2_audio import (
    LiveMeetingAudioStages,
    MeetingAudioArchive,
    MeetingAudioCleanupError,
)
from moss_transcribe_diarize.app.phase2_admin import execute as execute_admin
from moss_transcribe_diarize.app.phase2_control import Phase2ControlError
from moss_transcribe_diarize.app.phase2_live import Phase2LiveMeetings


class NeverOidc:
    async def begin(self, request):  # pragma: no cover - stored sessions bypass OIDC.
        raise AssertionError("OIDC must not run")

    async def complete(self, request):  # pragma: no cover - stored sessions bypass OIDC.
        raise AssertionError("OIDC must not run")


class SpeechProvider:
    def __init__(self, speech: tuple[bool, ...]):
        self._speech = list(speech)

    def observe(
        self,
        *,
        frame: AudioFrame,
        start_sample: int,
        end_sample: int,
    ) -> tuple[SpeechObservation, ...]:
        del frame
        speech_present = self._speech.pop(0) if self._speech else False
        return (
            SpeechObservation(
                start_sample=start_sample,
                end_sample=end_sample,
                speech_present=speech_present,
            ),
        )


class Decoder:
    max_samples = 4_000

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        del pcm
        seconds = span.sample_count / LIVE_SAMPLE_RATE
        return InferenceTranscript(f"[0][S01]owner live words[{seconds:g}]")


class WholeMeetingStub:
    window_seconds = 150
    stride_seconds = 120

    def __init__(self, text: str):
        self.text = text

    def transcribe(self, audio_path, **kwargs):
        del kwargs
        with wave.open(str(audio_path), "rb") as handle:
            handle.readframes(handle.getnframes())
        return type(
            "Result",
            (),
            {
                "text": self.text,
                "generated_tokens": 3,
                "prompt_len": 0,
                "window_count": 1,
                "completed_windows": 1,
                "possibly_truncated": False,
            },
        )()


@dataclass
class Identity:
    def prepare(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        transcript: str,
        base_snapshot: LiveIdentitySnapshot,
    ) -> LiveIdentityPreparation:
        del pcm, transcript
        return LiveIdentityPreparation(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            base_snapshot_version=base_snapshot.version,
            proposed_snapshot=LiveIdentitySnapshot(
                version=base_snapshot.version + 1,
                canonical_speakers=base_snapshot.canonical_speakers or ("speaker-0001",),
            ),
            relabeled_transcript=(
                f"[0][S01]owner live words[{span.sample_count / LIVE_SAMPLE_RATE:g}]"
            ),
        )


def make_runtime(
    *,
    speech: tuple[bool, ...] = (True, False),
    terminal_text: str | None = None,
    terminal_scheduler: _ManualTerminalScheduler | None = None,
    max_tape_bytes: int = 32_000,
) -> LiveServiceRuntime:
    descriptor = LiveServiceDescriptor(
        source_revision="a" * 40,
        provider_name="phase2-live-test",
        provider_revision="test",
        provider_manifest_hash=hash_config({"provider": "phase2-live-test"}),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={"min_speech_samples": 1, "min_silence_samples": 1},
            identity_config={"max_speakers": 2},
            decoder_config={"max_samples": 4_000},
        ),
        bounds=LiveServiceBounds(
            max_frame_samples=4_000,
            max_queue_depth=4,
            max_retained_samples=16_000,
            max_identity_speakers=2,
            max_events=128,
            hard_cap_samples=4_000,
            max_tape_bytes=max_tape_bytes,
        ),
        frame_samples=2,
    )
    return LiveServiceRuntime(
        descriptor=descriptor,
        endpoint_policy_factory=lambda: EndpointPolicy(
            EndpointPolicyConfig(
                min_speech_samples=1,
                min_silence_samples=1,
                hard_cap_samples=4_000,
            )
        ),
        speech_provider_factory=lambda: SpeechProvider(speech),
        decoder_factory=Decoder,
        rolling_decoder_factory=None if terminal_text is None else Decoder,
        identity_preparer_factory=Identity,
        terminal_finalizer=(
            None
            if terminal_text is None
            else TerminalTranscriptFinalizer(runner=WholeMeetingStub(terminal_text))
        ),
        _terminal_scheduler=terminal_scheduler,
    )


async def provision(database: Path) -> dict[str, str]:
    store = await Phase2Store.open(database)
    try:
        for email in ("a@example.com", "b@example.com"):
            await store.allow_email(email)
        admitted_a = await store.admit(GoogleIdentity("sub-a", "a@example.com", "A"))
        observer_a = await store.admit(GoogleIdentity("sub-a", "a@example.com", "A"))
        admitted_b = await store.admit(GoogleIdentity("sub-b", "b@example.com", "B"))
        assert admitted_a is not None and observer_a is not None and admitted_b is not None
        return {
            "a": admitted_a[1],
            "a-observer": observer_a[1],
            "b": admitted_b[1],
        }
    finally:
        await store.close()


def make_app(
    database: Path,
    *,
    lease_seconds: float = 30.0,
    speech: tuple[bool, ...] = (True, False),
    terminal_text: str | None = None,
    terminal_scheduler: _ManualTerminalScheduler | None = None,
    max_tape_bytes: int = 32_000,
    audio_archive=None,
    control_socket: Path | None = None,
):
    return create_phase2_app(
        database_path=database,
        oidc=NeverOidc(),
        oauth_cookie_secret="test-cookie-secret",
        live_runtime_factory=lambda: make_runtime(
            speech=speech,
            terminal_text=terminal_text,
            terminal_scheduler=terminal_scheduler,
            max_tape_bytes=max_tape_bytes,
        ),
        live_helper_lease_seconds=lease_seconds,
        meeting_audio_root=database.parent / "meetings",
        file_audio_archive=audio_archive,
        control_socket_path=control_socket,
    )


def session(client: TestClient, session_id: str | None) -> None:
    client.cookies.clear()
    if session_id is not None:
        client.cookies.set(SESSION_COOKIE, session_id, domain="moss.test", path="/")


def v2_frame(sequence: int, lane: str) -> dict[str, object]:
    samples = 2
    return {
        "lane": lane,
        "sequence": sequence,
        "capture_timestamp_ns": sequence * samples * 1_000_000_000 // LIVE_SAMPLE_RATE,
        "device_epoch": 0,
        "pcm_base64": base64.b64encode(b"\0" * samples * 2).decode("ascii"),
        "sample_count": samples,
        "sample_rate": LIVE_SAMPLE_RATE,
        "silent": False,
        "discontinuity": False,
    }


def heartbeat(sequence: int = 0) -> dict[str, object]:
    lane = {
        "state": "capturing",
        "device_epoch": 0,
        "dropped_frames": 0,
        "discontinuities": 0,
        "failure_code": None,
    }
    return {
        "schema": HELPER_HEALTH_SCHEMA,
        "instance_id": "browser-test",
        "sequence": sequence,
        "sent_monotonic_ns": sequence + 1,
        "helper_version": "test",
        "state": "capturing",
        "lanes": {"system": dict(lane), "microphone": dict(lane)},
    }


async def prepare_crashed_live_meeting(
    database: Path,
    audio_root: Path,
    scenario: str,
) -> tuple[str, str]:
    store = await Phase2Store.open(database)
    archive = MeetingAudioArchive(audio_root)
    stages = LiveMeetingAudioStages(archive, max_bytes=32_000)
    try:
        await store.allow_email("a@example.com")
        admitted = await store.admit(GoogleIdentity("sub-a", "a@example.com", "A"))
        assert admitted is not None
        account, session_id = admitted
        handle = await store.workspace(account).create_meeting("live")
        await handle.commit_transcript(
            {"segments": [{"id": "seg_0001", "speaker": "S01", "text": "crash prefix"}]}
        )
        stages.reserve(account.account_id, handle.meeting_id)
        stage = stages.create(handle.meeting_id)
        if scenario != "zero":
            stage.append_mixed(
                pcm=b"\x01\x00" * 8,
                start_timestamp_ns=0,
                sample_count=8,
                sample_rate=LIVE_SAMPLE_RATE,
            )
        stages.release(handle.meeting_id)
        stage_path = stages.path(account.account_id, handle.meeting_id)
        if scenario == "torn":
            with stage_path.open("ab") as output:
                output.write(b"\xff")
                output.flush()
                os.fsync(output.fileno())
        if scenario == "orphan":
            archive.publish_live_prefix(
                account.account_id,
                handle.meeting_id,
                stage_path,
                partial=False,
            )
        elif scenario in {"metadata", "missing"}:
            audio = await handle.publish_audio(
                archive,
                stage_path,
                partial=False,
                raw_pcm=True,
            )
            assert audio.state == "available"
            if scenario == "missing":
                (audio_root / audio.relative_path).unlink()
        return session_id, handle.meeting_id
    finally:
        await store.close()


def wait_snapshot(
    client: TestClient,
    meeting_id: str,
    predicate,
    *,
    timeout: float = 5.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    payload: dict[str, object] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/live/sessions/{meeting_id}/snapshot")
        assert response.status_code == 200
        payload = response.json()
        if predicate(payload):
            return payload
        time.sleep(0.01)
    raise AssertionError(f"Live snapshot did not reach expected state: {payload}")


def feed_two_lane_span(client: TestClient, meeting_id: str) -> None:
    url = f"/api/live/sessions/{meeting_id}/frames"
    # The compatibility mixer deliberately holds one frame per lane for replay alignment.
    # Three lane pairs therefore publish two mono frames: speech, then endpointing silence.
    for sequence in range(3):
        assert client.post(url, json=v2_frame(sequence, "system")).status_code == 200
        assert client.post(url, json=v2_frame(sequence, "microphone")).status_code == 200


def feed_two_lane_pairs(client: TestClient, meeting_id: str, sequences: range) -> None:
    url = f"/api/live/sessions/{meeting_id}/frames"
    for sequence in sequences:
        assert client.post(url, json=v2_frame(sequence, "system")).status_code == 200
        assert client.post(url, json=v2_frame(sequence, "microphone")).status_code == 200


def test_signed_in_two_lane_live_meeting_is_owner_bound_memory_polled_and_durable(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(
        database,
        terminal_text="[0][S01]terminal owner words[0.000375]",
    )

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, None)
        assert client.get("/api/live/descriptor").status_code == 401

        session(client, sessions["a"])
        workspace = client.get("/")
        assert 'data-live-capture="account"' in workspace.text
        assert '<meta name="moss-authority" content="account">' in workspace.text
        assert "Capture bearer" not in workspace.text
        assert client.post("/api/live/pairing-codes").status_code == 404
        assert client.post("/api/live/pairings").status_code == 404
        assert client.delete("/api/live/sessions/unknown/view").status_code == 404
        assert client.delete("/api/live/devices/unknown").status_code == 404
        bypass = client.post("/api/meetings", json={"mode": "live"})
        assert bypass.status_code == 405
        assert client.get("/api/meetings").json() == {"meetings": []}
        created = client.post("/api/live/sessions", json={"echo_mode": "speakers"})
        assert created.status_code == 201
        assert set(created.json()) == {"id", "descriptor", "snapshot"}
        meeting_id = created.json()["id"]

        session(client, sessions["a-observer"])
        assert client.get(f"/api/live/sessions/{meeting_id}/snapshot").status_code == 200
        assert client.get(f"/api/live/sessions/{meeting_id}/events?since_seq=-1").status_code == 200
        assert client.post(f"/api/live/sessions/{meeting_id}/stop").status_code == 403

        session(client, sessions["b"])
        assert client.get(f"/api/live/sessions/{meeting_id}/snapshot").status_code == 404
        assert client.post(f"/api/live/sessions/{meeting_id}/abort").status_code == 404
        session(client, None)
        assert client.get(f"/api/live/sessions/{meeting_id}/snapshot").status_code == 401

        session(client, sessions["a"])
        assert client.post(
            f"/api/live/sessions/{meeting_id}/heartbeat", json=heartbeat()
        ).status_code == 200
        feed_two_lane_span(client, meeting_id)
        published = wait_snapshot(
            client,
            meeting_id,
            lambda body: bool(body["snapshot"]["session"]["effective_transcript"]),
        )
        assert published["meeting_transcript_version"] == 1
        assert published["snapshot"]["session"]["effective_transcript"][0]["text"] == (
            "owner live words"
        )
        raw_session = app.state.phase2_live.runtime._sessions[meeting_id]
        accepted_samples = raw_session.session.snapshot().accepted_samples
        staged_path = database.parent / "meetings" / "sub-a" / meeting_id / ".live-mix.pcm"
        assert staged_path.read_bytes() == raw_session.coordinator.tape.read(
            start_sample=0,
            end_sample=accepted_samples,
        )

        statements: list[str] = []
        client.portal.call(
            app.state.phase2_store._connection.set_trace_callback,
            statements.append,
        )
        session(client, sessions["a-observer"])
        for index in range(8):
            route = "snapshot" if index % 2 == 0 else "events?since_seq=-1"
            assert client.get(f"/api/live/sessions/{meeting_id}/{route}").status_code == 200
        client.portal.call(app.state.phase2_store._connection.set_trace_callback, None)
        normalized = [" ".join(statement.lower().split()) for statement in statements]
        assert len([statement for statement in normalized if statement.startswith("select")]) == 8
        assert all("sign_in_sessions" in statement and "accounts" in statement for statement in normalized)
        assert not any(" meetings" in statement or "meeting_transcripts" in statement for statement in normalized)
        assert not any(
            statement.startswith(("insert", "update", "delete", "replace"))
            for statement in normalized
        )

        session(client, sessions["a"])
        stopped = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        assert stopped.status_code == 200
        assert stopped.json()["raw_terminal_status"] == "closed"
        assert stopped.json()["snapshot"]["session"]["status"] == "closed"
        assert stopped.json()["snapshot"]["session"]["finalization_status"] == "final"
        terminal = client.get(f"/api/live/sessions/{meeting_id}/snapshot").json()
        assert terminal["snapshot"]["session"]["status"] == "closed"
        assert terminal["snapshot"]["session"]["effective_transcript"][0]["text"] == (
            "terminal owner words"
        )
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "completed"
        assert meeting["transcript_version"] == 3
        assert meeting["transcript"]["segments"][0]["speaker"] == "S01"
        assert meeting["transcript"]["segments"][0]["text"] == "terminal owner words"
        assert meeting["audio"]["state"] == "available"
        assert {
            key: meeting["audio"][key]
            for key in (
                "format",
                "sample_rate_hz",
                "channels",
                "bit_rate_bps",
            )
        } == {
            "format": "mp3",
            "sample_rate_hz": 16_000,
            "channels": 1,
            "bit_rate_bps": 48_000,
        }
        assert not staged_path.exists()
        retained = database.parent / "meetings" / "sub-a" / meeting_id / "audio.mp3"
        assert stat.S_IMODE(retained.parent.parent.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(retained.parent.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(retained.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(retained.stat().st_mode) == 0o600
        with pytest.raises(wave.Error):
            wave.open(str(retained), "rb")

        session(client, sessions["b"])
        assert client.get(f"/api/meetings/{meeting_id}/audio/download").status_code == 404
        session(client, None)
        assert client.get(f"/api/meetings/{meeting_id}/audio/download").status_code == 401
        session(client, sessions["a"])
        download = client.get(f"/api/meetings/{meeting_id}/audio/download")
        assert download.status_code == 200
        assert download.content == retained.read_bytes()
        assert download.headers["content-disposition"].endswith(f'meeting-{meeting_id}.mp3"')
        assert client.post(
            f"/api/live/sessions/{meeting_id}/frames",
            json=v2_frame(3, "system"),
        ).status_code == 409
        assert client.portal.call(
            app.state.phase2_store.revoke_email,
            "a@example.com",
        ) is True
        assert client.get(f"/api/meetings/{meeting_id}/audio/download").status_code == 401


def test_shutdown_unbinds_late_terminal_finalizer_after_durable_interruption(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    terminal_scheduler = _ManualTerminalScheduler()
    app = make_app(
        database,
        terminal_text="[0][S01]late terminal words[0.000375]",
        terminal_scheduler=terminal_scheduler,
    )

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        wait_snapshot(
            client,
            meeting_id,
            lambda body: body["meeting_transcript_version"] == 1,
        )
        stopped = client.portal.call(
            app.state.phase2_live.runtime.stop,
            meeting_id,
            2.0,
        )
        assert stopped.session.finalization_status == "running"
        app.state.live_tapes.release(meeting_id)
        assert terminal_scheduler.pending == 1
        binding = app.state.phase2_live._bindings[meeting_id]

    durable_version_after_shutdown = binding.durable_version
    public_after_shutdown = binding.public_snapshot
    assert public_after_shutdown is not None
    assert public_after_shutdown.session.status == "closed"
    assert public_after_shutdown.terminal_failure is not None

    # The runtime's last listener still owns tape cleanup, but no longer owns a web-loop sink.
    assert terminal_scheduler.run_one() is True
    assert binding.durable_version == durable_version_after_shutdown
    assert binding.public_snapshot == public_after_shutdown
    assert "session_tape_released" in {
        event.kind for event in app.state.phase2_live.runtime.events(meeting_id)
    }

    connection = sqlite3.connect(database)
    try:
        durable = connection.execute(
            """
            SELECT m.status, t.version, t.document_json
            FROM meetings m
            LEFT JOIN meeting_transcripts t
              ON t.account_id = m.account_id AND t.meeting_id = m.meeting_id
            WHERE m.meeting_id = ?
            """,
            (meeting_id,),
        ).fetchone()
    finally:
        connection.close()
    assert durable is not None
    assert durable[0] == "interrupted"
    assert durable[1] == durable_version_after_shutdown
    assert "late terminal words" not in (durable[2] or "")
    connection = sqlite3.connect(database)
    try:
        audio = connection.execute(
            "SELECT state FROM meeting_audio WHERE meeting_id = ?", (meeting_id,)
        ).fetchone()
    finally:
        connection.close()
    assert audio == ("partial",)


def test_stop_tail_persistence_failure_fences_pending_finalizer_on_last_durable_prefix(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    terminal_scheduler = _ManualTerminalScheduler()
    app = make_app(
        database,
        terminal_text="[0][S01]undurable terminal words[0.000375]",
        terminal_scheduler=terminal_scheduler,
    )

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        durable_prefix = wait_snapshot(
            client,
            meeting_id,
            lambda body: body["meeting_transcript_version"] == 1,
        )
        binding = app.state.phase2_live._bindings[meeting_id]

        async def fail_stop_tail_commit(document, *, terminal=False):
            del document, terminal
            raise sqlite3.OperationalError("injected Stop-tail persistence failure")

        binding.handle.commit_transcript = fail_stop_tail_commit
        stopped = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        assert stopped.status_code == 200
        failed = client.get(f"/api/live/sessions/{meeting_id}/snapshot").json()
        assert failed["persistence_failure"] == "transcript_persistence_failed"
        assert failed["snapshot"]["session"]["status"] == "closed"
        assert failed["snapshot"]["session"]["finalization_status"] == "running"
        assert failed["snapshot"]["terminal_failure"] is not None
        assert failed["snapshot"]["session"]["effective_transcript"] == (
            durable_prefix["snapshot"]["session"]["effective_transcript"]
        )
        assert binding.capture_fenced is True
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "interrupted"
        assert meeting["transcript_version"] == 1
        assert meeting["audio"]["state"] == "partial"
        assert not (
            database.parent / "meetings" / "sub-a" / meeting_id / ".live-mix.pcm"
        ).exists()
        assert terminal_scheduler.pending == 1

        public_before_late_finalizer = binding.public_snapshot
        assert terminal_scheduler.run_one() is True
        time.sleep(0.01)
        assert binding.public_snapshot == public_before_late_finalizer
        meeting_after = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting_after == meeting
        assert "undurable terminal words" not in json.dumps(meeting_after)


def test_raw_stop_latch_shares_only_the_inflight_attempt():
    first_snapshot = object()

    class Runtime:
        def __init__(self):
            self.calls = 0
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def stop(self, session_id, deadline):
            del session_id, deadline
            self.calls += 1
            if self.calls == 1:
                self.entered.set()
                await self.release.wait()
                return first_snapshot
            raise LiveSessionClosed("already closed")

    async def scenario():
        runtime = Runtime()
        live = Phase2LiveMeetings(runtime, audio_archive=None, audio_stages=None)
        binding = SimpleNamespace(raw_stop_attempt=None, handle=SimpleNamespace(meeting_id="m"))
        live._bindings["m"] = binding

        foreign_intent = live.begin_stop("m")
        first_intent = live.begin_stop("m")
        assert foreign_intent is not None and first_intent is not None
        assert foreign_intent.attempt is first_intent.attempt
        live.release_stop(foreign_intent)
        assert binding.raw_stop_attempt is first_intent.attempt
        assert first_intent.attempt.entrants == 1

        first = asyncio.create_task(live.stop(binding, 1.0, first_intent))
        await runtime.entered.wait()
        concurrent_intent = live.begin_stop("m")
        assert concurrent_intent is not None
        concurrent = asyncio.create_task(live.stop(binding, 1.0, concurrent_intent))
        runtime.release.set()
        assert await asyncio.gather(first, concurrent) == [first_snapshot, first_snapshot]
        assert runtime.calls == 1
        assert binding.raw_stop_attempt is None
        live.release_stop(first_intent)
        live.release_stop(concurrent_intent)
        assert first_intent.attempt.entrants == 0

        sequential_intent = live.begin_stop("m")
        assert sequential_intent is not None
        with pytest.raises(LiveSessionClosed, match="already closed"):
            await live.stop(binding, 1.0, sequential_intent)
        live.release_stop(sequential_intent)
        assert runtime.calls == 2
        assert binding.raw_stop_attempt is None

    asyncio.run(scenario())


def test_raw_stop_latch_clears_after_timeout_so_retry_reaches_runtime():
    retried_snapshot = object()

    class Runtime:
        def __init__(self):
            self.calls = 0

        async def stop(self, session_id, deadline):
            del session_id, deadline
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("first Stop timed out")
            return retried_snapshot

    async def scenario():
        runtime = Runtime()
        live = Phase2LiveMeetings(runtime, audio_archive=None, audio_stages=None)
        binding = SimpleNamespace(raw_stop_attempt=None, handle=SimpleNamespace(meeting_id="m"))
        live._bindings["m"] = binding

        first_intent = live.begin_stop("m")
        assert first_intent is not None
        with pytest.raises(TimeoutError, match="first Stop timed out"):
            await live.stop(binding, 0.0, first_intent)
        live.release_stop(first_intent)
        assert binding.raw_stop_attempt is None

        retry_intent = live.begin_stop("m")
        assert retry_intent is not None
        assert await live.stop(binding, 1.0, retry_intent) is retried_snapshot
        live.release_stop(retry_intent)
        assert runtime.calls == 2
        assert binding.raw_stop_attempt is None

    asyncio.run(scenario())


def test_raw_stop_latch_all_unauthorized_entrants_release_once():
    live = Phase2LiveMeetings(object(), audio_archive=None, audio_stages=None)
    binding = SimpleNamespace(raw_stop_attempt=None)
    live._bindings["m"] = binding

    anonymous = live.begin_stop("m")
    foreign = live.begin_stop("m")
    assert anonymous is not None and foreign is not None
    attempt = anonymous.attempt
    assert foreign.attempt is attempt and attempt.entrants == 2

    live.release_stop(anonymous)
    live.release_stop(anonymous)
    assert attempt.entrants == 1
    assert binding.raw_stop_attempt is attempt
    live.release_stop(foreign)
    assert attempt.entrants == 0
    assert attempt.completed.is_set()
    assert binding.raw_stop_attempt is None


def test_logout_drains_live_create_through_transport_registration(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        adapter = app.state.live_transport_control._adapter
        original_publication = adapter.publication
        publication_entered = threading.Event()
        release_publication = threading.Event()
        held = False
        outcome: dict[str, object] = {}

        async def hold_initial_publication(
            authority,
            meeting_id,
            *,
            wait_for_durability,
        ):
            nonlocal held
            if not held and wait_for_durability is False:
                held = True
                publication_entered.set()
                assert await asyncio.to_thread(release_publication.wait, 5)
            return await original_publication(
                authority,
                meeting_id,
                wait_for_durability=wait_for_durability,
            )

        adapter.publication = hold_initial_publication

        def create() -> None:
            outcome["create"] = client.post("/api/live/sessions")

        def logout() -> None:
            outcome["logout"] = client.post("/auth/logout", follow_redirects=False)

        create_worker = threading.Thread(target=create)
        create_worker.start()
        assert publication_entered.wait(timeout=2)
        logout_worker = threading.Thread(target=logout)
        logout_worker.start()
        time.sleep(0.05)
        assert logout_worker.is_alive()
        release_publication.set()
        create_worker.join(timeout=5)
        logout_worker.join(timeout=5)
        assert not create_worker.is_alive() and not logout_worker.is_alive()
        created = outcome["create"]
        logged_out = outcome["logout"]
        assert created.status_code == 201
        assert logged_out.status_code == 303
        meeting_id = created.json()["id"]

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT status FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ).fetchone()[0] == "completed"
    finally:
        connection.close()


def test_logout_stops_every_origin_live_before_revoking_only_that_session(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        first = client.post("/api/live/sessions").json()["id"]
        second = client.post("/api/live/sessions").json()["id"]
        session(client, sessions["a-observer"])
        observed = client.post("/api/live/sessions").json()["id"]
        session(client, sessions["a"])

        logout = client.post("/auth/logout", follow_redirects=False)
        assert logout.status_code == 303
        assert client.cookies.get(SESSION_COOKIE) is None
        assert client.get("/api/auth/session").status_code == 401
        session(client, sessions["a-observer"])
        assert client.get("/api/auth/session").status_code == 200
        assert client.get(f"/api/live/sessions/{observed}/snapshot").status_code == 200

        meetings = {meeting["id"]: meeting for meeting in client.get("/api/meetings").json()["meetings"]}
        assert meetings[first]["status"] == "completed"
        assert meetings[second]["status"] == "completed"
        assert meetings[observed]["status"] == "active"


def test_logout_stop_failure_keeps_cookie_session_and_reopens_creation(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        control = app.state.phase2_live_control
        original_stop = control.stop

        async def refuse_stop(authority, session_id, deadline, intent=None):
            del authority, session_id, deadline, intent
            raise RuntimeError("injected durable Stop refusal")

        control.stop = refuse_stop
        logout = client.post("/auth/logout", follow_redirects=False)
        assert logout.status_code == 503
        assert client.cookies.get(SESSION_COOKIE) == sessions["a"]
        assert client.get("/api/auth/session").status_code == 200
        control.stop = original_stop
        assert client.post("/api/live/sessions").status_code == 201
        assert client.post(
            f"/api/live/sessions/{meeting_id}/abort",
            json={"reason": "test cleanup"},
        ).status_code == 200


def test_concurrent_logout_settles_before_account_revoke_disables_authority(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i18-concurrent-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    app = make_app(database, control_socket=socket)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        control = app.state.phase2_live_control
        original_stop = control.stop
        stop_entered = threading.Event()
        release_stop = threading.Event()
        outcome: dict[str, object] = {}

        async def held_stop(authority, session_id, deadline, intent=None):
            stop_entered.set()
            assert await asyncio.to_thread(release_stop.wait, 5)
            return await original_stop(authority, session_id, deadline, intent)

        control.stop = held_stop

        def logout() -> None:
            try:
                outcome["logout"] = client.portal.call(
                    app.state.phase2_lifecycle.logout,
                    sessions["a"],
                )
            except Exception as exc:
                outcome["logout_error"] = exc

        def revoke() -> None:
            try:
                outcome["revoke"] = asyncio.run(
                    execute_admin(socket, "revoke", "a@example.com")
                )
            except Exception as exc:
                outcome["revoke_error"] = exc

        logout_worker = threading.Thread(target=logout)
        logout_worker.start()
        assert stop_entered.wait(timeout=2)
        revoke_worker = threading.Thread(target=revoke)
        revoke_worker.start()
        time.sleep(0.05)
        assert revoke_worker.is_alive()
        release_stop.set()
        logout_worker.join(timeout=5)
        revoke_worker.join(timeout=5)
        assert not logout_worker.is_alive() and not revoke_worker.is_alive()
        assert outcome == {
            "logout": True,
            "revoke": {"email": "a@example.com", "revoked": True},
        }
        session(client, sessions["a"])
        assert client.get("/api/auth/session").status_code == 401

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT status FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ).fetchone()[0] == "completed"
    finally:
        connection.close()


def test_revoke_fences_all_live_before_first_settlement_await(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i18-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    app = make_app(database, control_socket=socket)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        first = client.post("/api/live/sessions").json()["id"]
        second = client.post("/api/live/sessions").json()["id"]
        live = app.state.phase2_live
        original_interrupt = live.interrupt_binding
        first_settlement_entered = threading.Event()
        release_failure = threading.Event()
        outcome: dict[str, object] = {}

        async def fail_first(binding, control, reason):
            if binding.handle.meeting_id == first:
                first_settlement_entered.set()
                assert await asyncio.to_thread(release_failure.wait, 5)
                raise RuntimeError("injected first settlement failure")
            return await original_interrupt(binding, control, reason)

        live.interrupt_binding = fail_first

        def revoke() -> None:
            try:
                outcome["result"] = asyncio.run(
                    execute_admin(socket, "revoke", "a@example.com")
                )
            except Exception as exc:
                outcome["error"] = exc

        worker = threading.Thread(target=revoke)
        worker.start()
        assert first_settlement_entered.wait(timeout=2)
        # Every target was synchronously fenced before the first terminal await failed.
        assert client.post(
            f"/api/live/sessions/{second}/frames",
            json=v2_frame(0, "system"),
        ).status_code == 409
        assert app.state.phase2_live._bindings[second].authority_closing is True
        assert client.get("/api/auth/session").status_code == 200
        release_failure.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert isinstance(outcome.get("error"), Phase2ControlError)
        assert str(outcome["error"]) == "account_settlement_failed"
        assert client.get("/api/auth/session").status_code == 200
        live.interrupt_binding = original_interrupt

    # A failed revoke never reopens the uncertain generation in-process.  Normal startup
    # recovery settles its rows; a fresh lifecycle can then retry and disable authority last.
    restarted = make_app(database, control_socket=socket)
    with TestClient(restarted, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        assert client.get("/api/auth/session").status_code == 200
        assert asyncio.run(execute_admin(socket, "revoke", "a@example.com")) == {
            "email": "a@example.com",
            "revoked": True,
        }
        assert client.get("/api/auth/session").status_code == 401

    connection = sqlite3.connect(database)
    try:
        statuses = dict(connection.execute("SELECT meeting_id, status FROM meetings"))
    finally:
        connection.close()
    assert statuses[first] == "interrupted"
    assert statuses[second] == "interrupted"


def test_control_revoke_returns_after_durable_interrupt_and_fresh_generation(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i18-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    app = make_app(database, control_socket=socket)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        revoked_meeting = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, revoked_meeting)
        session(client, sessions["b"])
        other_meeting = client.post("/api/live/sessions").json()["id"]

        assert asyncio.run(execute_admin(socket, "revoke", "a@example.com")) == {
            "email": "a@example.com",
            "revoked": True,
        }
        session(client, sessions["a"])
        assert client.get("/api/auth/session").status_code == 401
        session(client, sessions["a-observer"])
        assert client.get("/api/auth/session").status_code == 401
        session(client, sessions["b"])
        assert client.get(f"/api/live/sessions/{other_meeting}/snapshot").status_code == 200

        assert asyncio.run(execute_admin(socket, "allow", "a@example.com")) == {
            "email": "a@example.com",
            "enabled": True,
        }

        async def fresh_session() -> tuple[int, str]:
            admitted = await app.state.phase2_store.admit(
                GoogleIdentity("sub-a", "a@example.com", "A")
            )
            assert admitted is not None
            return admitted[0].authority_generation, admitted[1]

        generation, new_session = client.portal.call(fresh_session)
        assert generation == 1
        session(client, new_session)
        assert client.get(f"/api/live/sessions/{revoked_meeting}/snapshot").status_code == 404
        assert client.post("/api/live/sessions").status_code == 201

    connection = sqlite3.connect(database)
    try:
        rows = dict(connection.execute("SELECT meeting_id, status FROM meetings"))
        revoked_audio = connection.execute(
            "SELECT state FROM meeting_audio WHERE meeting_id = ?", (revoked_meeting,)
        ).fetchone()
    finally:
        connection.close()
    assert rows[revoked_meeting] == "interrupted"
    assert revoked_audio == ("partial",)
    assert rows[other_meeting] == "interrupted"  # normal service shutdown, not Account revoke


def test_raw_stop_latch_cancelled_entrant_releases_only_its_claim():
    live = Phase2LiveMeetings(object(), audio_archive=None, audio_stages=None)
    binding = SimpleNamespace(raw_stop_attempt=None)
    live._bindings["m"] = binding

    cancelled = live.begin_stop("m")
    owner = live.begin_stop("m")
    assert cancelled is not None and owner is not None
    live.release_stop(cancelled)
    assert owner.attempt.entrants == 1
    assert binding.raw_stop_attempt is owner.attempt
    live.release_stop(owner)
    assert binding.raw_stop_attempt is None


@pytest.mark.parametrize(
    ("entrant_key", "rejection_status"),
    ((None, 401), ("b", 404)),
    ids=("anonymous-first", "foreign-first"),
)
def test_pre_auth_stop_entrant_cannot_clear_joined_owner_attempt(
    tmp_path: Path,
    entrant_key: str | None,
    rejection_status: int,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] == 1)
        binding = app.state.phase2_live._bindings[meeting_id]
        store = app.state.phase2_store
        runtime = app.state.phase2_live.runtime

        entrant_session = None if entrant_key is None else sessions[entrant_key]
        entrant_auth_entered = threading.Event()
        release_entrant_auth = threading.Event()
        owner_auth_entered = threading.Event()
        release_owner_auth = threading.Event()
        raw_stop_entered = threading.Event()
        release_raw_stop = threading.Event()
        fence_started = threading.Event()
        original_account_for_session = store.account_for_session
        original_runtime_stop = runtime.stop
        original_runtime_abort = runtime.abort
        abort_raw_statuses: list[str] = []
        outcomes: dict[str, object] = {}

        async def held_account_for_session(session_id):
            if session_id == entrant_session:
                entrant_auth_entered.set()
                await asyncio.to_thread(release_entrant_auth.wait)
            elif session_id == sessions["a"]:
                owner_auth_entered.set()
                await asyncio.to_thread(release_owner_auth.wait)
            return await original_account_for_session(session_id)

        async def held_runtime_stop(session_id, deadline):
            raw_stop_entered.set()
            await asyncio.to_thread(release_raw_stop.wait)
            return await original_runtime_stop(session_id, deadline)

        async def observed_runtime_abort(session_id, reason, *, detail=None):
            snapshot = runtime.snapshot(session_id)
            assert snapshot is not None
            abort_raw_statuses.append(snapshot.session.status)
            return await original_runtime_abort(session_id, reason, detail=detail)

        store.account_for_session = held_account_for_session
        runtime.stop = held_runtime_stop
        runtime.abort = observed_runtime_abort
        client.cookies.clear()

        def stop_request(name: str, session_id: str | None) -> None:
            headers = {} if session_id is None else {
                "cookie": f"{SESSION_COOKIE}={session_id}"
            }
            try:
                outcomes[name] = client.post(
                    f"/api/live/sessions/{meeting_id}/stop",
                    json={"deadline": 2.0},
                    headers=headers,
                )
            except BaseException as exc:  # pragma: no cover - assertion reports thread error.
                outcomes[f"{name}_error"] = exc

        entrant_thread = threading.Thread(
            target=stop_request,
            args=("entrant", entrant_session),
        )
        entrant_thread.start()
        assert entrant_auth_entered.wait(timeout=2)

        owner_thread = threading.Thread(
            target=stop_request,
            args=("owner", sessions["a"]),
        )
        owner_thread.start()
        assert owner_auth_entered.wait(timeout=2)

        release_entrant_auth.set()
        entrant_thread.join(timeout=2)
        assert not entrant_thread.is_alive()
        assert "entrant_error" not in outcomes
        assert outcomes["entrant"].status_code == rejection_status
        attempt = binding.raw_stop_attempt
        assert attempt is not None and attempt.entrants == 1 and not attempt.started

        def fence_meeting() -> None:
            fence_started.set()
            try:
                client.portal.call(
                    app.state.phase2_live._fence,
                    binding,
                    "transcript_persistence_failed",
                )
            except BaseException as exc:  # pragma: no cover - assertion reports thread error.
                outcomes["fence_error"] = exc

        fence_thread = threading.Thread(target=fence_meeting)
        fence_thread.start()
        assert fence_started.wait(timeout=2)
        release_owner_auth.set()
        assert raw_stop_entered.wait(timeout=2)
        time.sleep(0.01)
        assert fence_thread.is_alive()
        assert abort_raw_statuses == []

        release_raw_stop.set()
        owner_thread.join(timeout=5)
        fence_thread.join(timeout=5)
        assert not owner_thread.is_alive() and not fence_thread.is_alive()
        assert "owner_error" not in outcomes and "fence_error" not in outcomes
        assert outcomes["owner"].status_code == 200
        assert abort_raw_statuses == ["closed"]
        assert binding.raw_stop_attempt is None
        meeting = client.get(
            f"/api/meetings/{meeting_id}",
            headers={"cookie": f"{SESSION_COOKIE}={sessions['a']}"},
        ).json()
        assert meeting["status"] == "interrupted"
        assert meeting["audio"]["state"] == "partial"
        assert not (
            database.parent / "meetings" / "sub-a" / meeting_id / ".live-mix.pcm"
        ).exists()


def test_concurrent_public_stops_share_the_inflight_raw_outcome(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] == 1)
        runtime = app.state.phase2_live.runtime
        original_runtime_stop = runtime.stop
        original_adapter_stop = app.state.phase2_live.stop
        raw_stop_entered = threading.Event()
        shared_stop_entered = threading.Event()
        release_raw_stop = threading.Event()
        second_finished = threading.Event()
        raw_calls = 0
        adapter_calls = 0
        outcomes: dict[str, object] = {}

        async def held_runtime_stop(session_id, deadline):
            nonlocal raw_calls
            raw_calls += 1
            raw_stop_entered.set()
            await asyncio.to_thread(release_raw_stop.wait)
            return await original_runtime_stop(session_id, deadline)

        async def observed_adapter_stop(binding, deadline, intent):
            nonlocal adapter_calls
            adapter_calls += 1
            if adapter_calls == 2:
                shared_stop_entered.set()
            return await original_adapter_stop(binding, deadline, intent)

        runtime.stop = held_runtime_stop
        app.state.phase2_live.stop = observed_adapter_stop

        def stop_request(name: str) -> None:
            try:
                outcomes[name] = client.post(
                    f"/api/live/sessions/{meeting_id}/stop",
                    json={"deadline": 2.0},
                )
            except BaseException as exc:  # pragma: no cover - assertion reports thread error.
                outcomes[f"{name}_error"] = exc
            finally:
                if name == "second":
                    second_finished.set()

        first = threading.Thread(target=stop_request, args=("first",))
        first.start()
        assert raw_stop_entered.wait(timeout=2)
        second = threading.Thread(target=stop_request, args=("second",))
        second.start()
        second_shared = shared_stop_entered.wait(timeout=2)
        second_returned_before_raw = second_finished.is_set()

        release_raw_stop.set()
        first.join(timeout=5)
        second.join(timeout=5)
        assert not first.is_alive() and not second.is_alive()
        assert second_shared
        assert not second_returned_before_raw
        assert "first_error" not in outcomes and "second_error" not in outcomes
        assert outcomes["first"].status_code == outcomes["second"].status_code == 200
        assert outcomes["first"].json()["raw_terminal_status"] == "closed"
        assert outcomes["second"].json()["raw_terminal_status"] == "closed"
        assert raw_calls == 1
        assert adapter_calls == 2

        sequential = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        assert sequential.status_code == 409


@pytest.mark.parametrize("terminal", ("failed", "aborted"))
def test_public_stop_keeps_preexisting_v2_terminal_states_as_conflicts(
    tmp_path: Path,
    terminal: str,
):
    from moss_transcribe_diarize.app.live_lane_contract import LiveLane

    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        v2_session = app.state.live_v2_sessions.get(meeting_id)
        if terminal == "failed":
            v2_session.fail_lane(LiveLane.MICROPHONE, "probe_failure")
            client.portal.call(v2_session.stop, 0.0)
        else:
            v2_session.abort("probe_abort")

        response = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        assert response.status_code == 409
        assert response.json()["failure"]["code"] == "v2_session_terminal"
        assert response.json()["v2_session"]["status"] == terminal


def test_helper_lease_loss_interrupts_without_client_terminal_request_and_never_resumes(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database, lease_seconds=0.03)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        wait_snapshot(
            client,
            meeting_id,
            lambda body: body["meeting_transcript_version"] == 1,
        )
        assert client.post(
            f"/api/live/sessions/{meeting_id}/heartbeat", json=heartbeat()
        ).status_code == 200
        terminal = wait_snapshot(
            client,
            meeting_id,
            lambda body: body["snapshot"]["session"]["status"] in {"failed", "aborted"},
        )
        assert terminal["meeting_transcript_version"] == 1
        assert terminal["snapshot"]["session"]["effective_transcript"][0]["text"] == (
            "owner live words"
        )
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "interrupted"
        assert meeting["transcript_version"] == 1
        assert client.post(
            f"/api/live/sessions/{meeting_id}/frames",
            json=v2_frame(3, "system"),
        ).status_code == 409


def test_create_arms_abandonment_lease_before_first_heartbeat(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database, lease_seconds=0.02)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        created = client.post("/api/live/sessions")
        assert created.status_code == 201
        meeting_id = created.json()["id"]

        terminal = wait_snapshot(
            client,
            meeting_id,
            lambda body: body["snapshot"]["session"]["status"] in {"failed", "aborted"},
        )
        assert terminal["meeting_transcript_version"] == 0
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "interrupted"
        assert meeting["transcript"] is None
        assert meeting["audio"]["state"] == "unavailable"
        assert client.post(
            f"/api/live/sessions/{meeting_id}/frames",
            json=v2_frame(0, "system"),
        ).status_code == 409


def test_persistence_failure_keeps_undurable_words_private_and_publishes_durable_terminal(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        binding = app.state.phase2_live._bindings[meeting_id]

        async def fail_commit(document, *, terminal=False):
            del document, terminal
            raise sqlite3.OperationalError("injected write failure")

        binding.handle.commit_transcript = fail_commit
        feed_two_lane_span(client, meeting_id)
        terminal = wait_snapshot(
            client,
            meeting_id,
            lambda body: body["persistence_failure"] == "transcript_persistence_failed",
        )
        assert terminal["snapshot"]["session"]["status"] == "aborted"
        assert terminal["snapshot"]["session"]["effective_transcript"] == []
        assert terminal["meeting_transcript_version"] == 0
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "interrupted"
        assert meeting["transcript"] is None
        assert meeting["audio"]["state"] == "partial"


def test_live_stage_bound_degrades_normal_stop_to_partial_without_losing_transcript(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database, max_tape_bytes=4)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] == 1)
        stopped = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        assert stopped.status_code == 200
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "completed"
        assert meeting["transcript"]["segments"][0]["text"] == "owner live words"
        assert meeting["audio"]["state"] == "partial"
        assert meeting["audio"]["duration_ms"] > 0
        meeting_dir = database.parent / "meetings" / "sub-a" / meeting_id
        assert (meeting_dir / "audio.partial.mp3").is_file()
        assert not (meeting_dir / ".live-mix.pcm").exists()


def test_terminal_audio_cleanup_precedes_atomic_final_transcript_and_status(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(
        database,
        terminal_text="[0][S01]atomic terminal words[0.000375]",
    )

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] == 1)
        binding = app.state.phase2_live._bindings[meeting_id]
        original_finish = binding.handle.finish_with_transcript
        observed: list[tuple[str, str, str]] = []
        stage_path = tmp_path / "meetings" / "sub-a" / meeting_id / ".live-mix.pcm"

        async def observe_atomic_finish(document, status):
            before = await binding.handle.snapshot()
            assert before.audio is not None and before.audio.state == "available"
            assert not stage_path.exists()
            observed.append(
                (
                    before.status,
                    before.transcript["segments"][0]["text"],
                    document["segments"][0]["text"],
                )
            )
            return await original_finish(document, status)

        binding.handle.finish_with_transcript = observe_atomic_finish
        stopped = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        assert stopped.status_code == 200
        assert observed == [("active", "owner live words", "atomic terminal words")]
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert (meeting["status"], meeting["transcript"]["segments"][0]["text"]) == (
            "completed",
            "atomic terminal words",
        )
        assert meeting["audio"]["state"] == "available"


def test_concurrent_fence_waits_for_one_terminal_audio_publication(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        binding = app.state.phase2_live._bindings[meeting_id]
        archive = app.state.phase2_audio_archive
        original_publish = archive.publish_live_prefix
        publish_started = threading.Event()
        release_publish = threading.Event()
        fence_started = threading.Event()
        publish_count = 0
        outcomes: dict[str, object] = {}

        def held_publish(*args, **kwargs):
            nonlocal publish_count
            publish_count += 1
            publish_started.set()
            assert release_publish.wait(timeout=5)
            return original_publish(*args, **kwargs)

        archive.publish_live_prefix = held_publish

        def stop_meeting() -> None:
            try:
                outcomes["stop"] = client.post(
                    f"/api/live/sessions/{meeting_id}/stop",
                    json={"deadline": 2.0},
                )
            except BaseException as exc:  # pragma: no cover - assertion reports thread error.
                outcomes["stop_error"] = exc

        def fence_meeting() -> None:
            fence_started.set()
            try:
                client.portal.call(
                    app.state.phase2_live._fence,
                    binding,
                    "service shutdown",
                )
            except BaseException as exc:  # pragma: no cover - assertion reports thread error.
                outcomes["fence_error"] = exc

        stop_thread = threading.Thread(target=stop_meeting)
        stop_thread.start()
        assert publish_started.wait(timeout=2)
        fence_thread = threading.Thread(target=fence_meeting)
        fence_thread.start()
        assert fence_started.wait(timeout=2)
        release_publish.set()
        stop_thread.join(timeout=5)
        fence_thread.join(timeout=5)
        assert not stop_thread.is_alive() and not fence_thread.is_alive()
        assert "stop_error" not in outcomes and "fence_error" not in outcomes
        assert outcomes["stop"].status_code == 200
        assert publish_count == 1

        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "completed"
        assert meeting["audio"]["state"] == "available"
        retained = tmp_path / "meetings" / "sub-a" / meeting_id / "audio.mp3"
        assert retained.is_file() and retained.stat().st_size == meeting["audio"]["byte_count"]
        assert sorted(
            path.name for path in retained.parent.iterdir() if path.suffix == ".mp3"
        ) == ["audio.mp3"]


def test_failed_terminal_can_only_retain_partial_audio(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        binding = app.state.phase2_live._bindings[meeting_id]

        async def settle_failed() -> None:
            snapshot = app.state.phase2_live.runtime.snapshot(meeting_id)
            assert snapshot is not None
            await app.state.phase2_live._settle_terminal(
                binding,
                snapshot,
                app.state.phase2_live.runtime.events(meeting_id),
                "failed",
            )

        client.portal.call(settle_failed)
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "failed"
        assert meeting["audio"]["state"] == "partial"
        meeting_dir = tmp_path / "meetings" / "sub-a" / meeting_id
        assert (meeting_dir / "audio.partial.mp3").is_file()
        assert not (meeting_dir / "audio.mp3").exists()


def test_live_encode_failure_preserves_transcript_and_finishes_audio_unavailable(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    archive = MeetingAudioArchive(tmp_path / "meetings", ffmpeg="", ffprobe="")
    app = make_app(database, audio_archive=archive)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        stopped = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        assert stopped.status_code == 200
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "completed"
        assert meeting["transcript"]["segments"][0]["text"] == "owner live words"
        assert meeting["audio"]["state"] == "unavailable"
        meeting_dir = tmp_path / "meetings" / "sub-a" / meeting_id
        assert not (meeting_dir / ".live-mix.pcm").exists()
        assert not tuple(meeting_dir.glob("*.mp3"))


def test_live_stage_create_refusal_preserves_transcript_and_finishes_unavailable(
    tmp_path: Path,
):
    class RefuseFirstDirectory(MeetingAudioArchive):
        def __init__(self, root: Path) -> None:
            super().__init__(root)
            self.refuse_once = True

        def _ensure_private_directory(self, path: Path) -> None:
            if self.refuse_once:
                self.refuse_once = False
                raise OSError("injected Live stage create refusal")
            super()._ensure_private_directory(path)

    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    archive = RefuseFirstDirectory(tmp_path / "meetings")
    app = make_app(database, audio_archive=archive)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        stopped = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        assert stopped.status_code == 200
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "completed"
        assert meeting["transcript"]["segments"][0]["text"] == "owner live words"
        assert meeting["audio"]["state"] == "unavailable"
        meeting_dir = tmp_path / "meetings" / "sub-a" / meeting_id
        assert not (meeting_dir / ".live-mix.pcm").exists()
        assert not tuple(meeting_dir.glob("*.mp3"))


def test_transient_live_stage_cleanup_failure_recovers_truth_and_finishes_interrupted(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        binding = app.state.phase2_live._bindings[meeting_id]
        stages = app.state.phase2_live.audio_stages
        original_discard = stages.discard
        store = app.state.phase2_store
        original_downgrade = store._downgrade_meeting_audio_to_partial
        attempts = 0
        downgrade_observation: dict[str, object] = {}

        def fail_once(account_id: str, target_meeting_id: str) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("injected transient stage cleanup failure")
            original_discard(account_id, target_meeting_id)

        stages.discard = fail_once

        async def observe_downgrade(*args, **kwargs):
            before = await binding.handle.snapshot()
            assert before.audio is not None and before.audio.relative_path is not None
            retained = tmp_path / "meetings" / before.audio.relative_path
            downgrade_observation["before"] = before.audio.to_dict()
            downgrade_observation["bytes_before"] = retained.read_bytes()
            result = await original_downgrade(*args, **kwargs)
            after = await binding.handle.snapshot()
            assert after.audio is not None
            downgrade_observation["after"] = after.audio.to_dict()
            downgrade_observation["bytes_after"] = retained.read_bytes()
            return result

        store._downgrade_meeting_audio_to_partial = observe_downgrade
        stopped = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        assert stopped.status_code == 200
        failed = client.get(f"/api/live/sessions/{meeting_id}/snapshot").json()
        assert failed["persistence_failure"] == "audio_terminal_recovery_failed"
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "interrupted"
        assert meeting["transcript"]["segments"][0]["text"] == "owner live words"
        assert meeting["audio"]["state"] == "partial"
        meeting_dir = tmp_path / "meetings" / "sub-a" / meeting_id
        assert (meeting_dir / "audio.mp3").is_file()
        before_audio = downgrade_observation["before"]
        after_audio = downgrade_observation["after"]
        assert before_audio["state"] == "available"
        assert after_audio["state"] == "partial"
        assert {key: value for key, value in before_audio.items() if key != "state"} == {
            key: value for key, value in after_audio.items() if key != "state"
        }
        assert downgrade_observation["bytes_before"] == downgrade_observation["bytes_after"]
        assert not (meeting_dir / ".live-mix.pcm").exists()
        assert attempts == 2


def test_persistent_live_stage_cleanup_failure_stays_active_until_startup_recovers(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        binding = app.state.phase2_live._bindings[meeting_id]
        stages = app.state.phase2_live.audio_stages
        attempts = 0

        def always_fail(account_id: str, target_meeting_id: str) -> None:
            nonlocal attempts
            del account_id, target_meeting_id
            attempts += 1
            raise OSError("injected persistent stage cleanup failure")

        stages.discard = always_fail
        stopped = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        assert stopped.status_code == 200
        failed = client.get(f"/api/live/sessions/{meeting_id}/snapshot").json()
        assert failed["persistence_failure"] == "audio_terminal_recovery_failed"
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "active"
        assert meeting["audio"]["state"] == "partial"
        assert binding.terminal_persisted is False
        stage_path = tmp_path / "meetings" / "sub-a" / meeting_id / ".live-mix.pcm"
        assert stage_path.is_file()

    assert attempts >= 3
    restarted = make_app(database)
    with TestClient(restarted, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "interrupted"
        assert meeting["audio"]["state"] == "partial"
        assert not stage_path.exists()


@pytest.mark.parametrize(
    ("scenario", "expected_state", "expected_name"),
    (
        ("zero", "unavailable", None),
        ("torn", "partial", "audio.partial.mp3"),
        ("orphan", "partial", "audio.partial.mp3"),
        ("metadata", "partial", "audio.mp3"),
        ("missing", "unavailable", None),
    ),
)
def test_restart_recovers_only_canonical_active_live_stage_and_reconciles_artifact_truth(
    tmp_path: Path,
    scenario: str,
    expected_state: str,
    expected_name: str | None,
):
    database = tmp_path / "moss.sqlite3"
    audio_root = tmp_path / "meetings"
    session_id, meeting_id = asyncio.run(
        prepare_crashed_live_meeting(database, audio_root, scenario)
    )
    metadata_before = None
    bytes_before = None
    if scenario == "metadata":
        connection = sqlite3.connect(database)
        try:
            metadata_before = connection.execute(
                """
                SELECT relative_path, byte_count, duration_ms, format,
                       sample_rate_hz, channels, bit_rate_bps
                FROM meeting_audio WHERE meeting_id = ?
                """,
                (meeting_id,),
            ).fetchone()
        finally:
            connection.close()
        assert metadata_before is not None
        bytes_before = (audio_root / metadata_before[0]).read_bytes()
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, session_id)
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "interrupted"
        assert meeting["transcript"]["segments"][0]["text"] == "crash prefix"
        assert meeting["audio"]["state"] == expected_state
        meeting_dir = audio_root / "sub-a" / meeting_id
        assert not (meeting_dir / ".live-mix.pcm").exists()
        retained = tuple(path.name for path in meeting_dir.glob("*.mp3"))
        assert retained == (() if expected_name is None else (expected_name,))
        if expected_state in {"available", "partial"}:
            downloaded = client.get(f"/api/meetings/{meeting_id}/audio/download")
            assert downloaded.status_code == 200
            assert downloaded.content == (meeting_dir / expected_name).read_bytes()
            if scenario == "metadata":
                assert tuple(
                    meeting["audio"][key]
                    for key in (
                        "relative_path",
                        "byte_count",
                        "duration_ms",
                        "format",
                        "sample_rate_hz",
                        "channels",
                        "bit_rate_bps",
                    )
                ) == metadata_before
                assert downloaded.content == bytes_before
        else:
            assert client.get(f"/api/meetings/{meeting_id}/audio/download").status_code == 404


def test_restart_between_live_meeting_row_and_stage_marks_unavailable_without_search(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"

    async def create_row_only() -> tuple[str, str]:
        store = await Phase2Store.open(database)
        try:
            await store.allow_email("a@example.com")
            admitted = await store.admit(GoogleIdentity("sub-a", "a@example.com", "A"))
            assert admitted is not None
            account, session_id = admitted
            handle = await store.workspace(account).create_meeting("live")
            return session_id, handle.meeting_id
        finally:
            await store.close()

    session_id, meeting_id = asyncio.run(create_row_only())
    app = make_app(database)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, session_id)
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "interrupted"
        assert meeting["transcript"] is None
        assert meeting["audio"]["state"] == "unavailable"
        assert client.get(f"/api/meetings/{meeting_id}/audio/download").status_code == 404
    assert not (tmp_path / "meetings" / "sub-a" / meeting_id).exists()


def test_interrupted_reallowed_live_meeting_reconciles_missing_metadata_artifact(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    audio_root = tmp_path / "meetings"
    _, meeting_id = asyncio.run(
        prepare_crashed_live_meeting(database, audio_root, "metadata")
    )
    retained = audio_root / "sub-a" / meeting_id / "audio.mp3"
    retained.unlink()

    async def revoke_and_reallow() -> str:
        store = await Phase2Store.open(database)
        try:
            assert await store.revoke_email("a@example.com") is True
            await store.allow_email("a@example.com")
            admitted = await store.admit(GoogleIdentity("sub-a", "a@example.com", "A"))
            assert admitted is not None
            return admitted[1]
        finally:
            await store.close()

    reallowed_session = asyncio.run(revoke_and_reallow())
    app = make_app(database)
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, reallowed_session)
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "interrupted"
        assert meeting["audio"]["state"] == "unavailable"
        assert client.get(f"/api/meetings/{meeting_id}/audio/download").status_code == 404
    meeting_dir = audio_root / "sub-a" / meeting_id
    assert not (meeting_dir / ".live-mix.pcm").exists()
    assert not tuple(meeting_dir.glob("*.mp3"))


def test_interrupted_live_artifact_cleanup_uncertainty_preserves_metadata_and_stage(
    tmp_path: Path,
):
    class UncertainArchive(MeetingAudioArchive):
        def resolve(
            self,
            account_id: str,
            meeting_id: str,
            relative_path: str,
            byte_count: int,
        ) -> None:
            del account_id, meeting_id, relative_path, byte_count
            return None

        def discard_stored(
            self,
            account_id: str,
            meeting_id: str,
            relative_path: str,
        ) -> None:
            del account_id, meeting_id, relative_path
            raise MeetingAudioCleanupError("injected artifact cleanup uncertainty")

    database = tmp_path / "moss.sqlite3"
    audio_root = tmp_path / "meetings"
    session_id, meeting_id = asyncio.run(
        prepare_crashed_live_meeting(database, audio_root, "metadata")
    )

    async def interrupt_then_attempt_recovery():
        store = await Phase2Store.open(database)
        try:
            account = await store.account_for_session(session_id)
            assert account is not None
            workspace = store.workspace(account)
            handle = await workspace.open_meeting(meeting_id)
            assert handle is not None
            await handle.finish("interrupted")
        finally:
            await store.close()

        uncertain = UncertainArchive(audio_root)
        stages = LiveMeetingAudioStages(uncertain, max_bytes=32_000)
        reopened = await Phase2Store.open(database)
        try:
            with pytest.raises(MeetingAudioCleanupError):
                await reopened.recover_active_meetings(
                    audio_archive=uncertain,
                    live_audio_stages=stages,
                )
            account = await reopened.account_for_session(session_id)
            assert account is not None
            handle = await reopened.workspace(account).open_meeting(meeting_id)
            assert handle is not None
            return await handle.snapshot()
        finally:
            await reopened.close()

    snapshot = asyncio.run(interrupt_then_attempt_recovery())
    meeting_dir = audio_root / "sub-a" / meeting_id
    assert snapshot.status == "interrupted"
    assert snapshot.audio is not None and snapshot.audio.state == "available"
    assert (meeting_dir / "audio.mp3").is_file()
    assert (meeting_dir / ".live-mix.pcm").is_file()


def test_runtime_create_refusal_with_cleanup_uncertainty_recovers_on_restart(
    tmp_path: Path,
):
    class RejectCreateRuntime:
        def create(self, *, echo_mode: str | None, session_id: str) -> None:
            del echo_mode, session_id
            raise ValueError("injected runtime creation refusal")

    class PersistentDiscardFailure:
        def __init__(self, stages: LiveMeetingAudioStages) -> None:
            self.stages = stages
            self.attempts = 0

        def __getattr__(self, name: str):
            return getattr(self.stages, name)

        def discard(self, account_id: str, meeting_id: str) -> None:
            del account_id, meeting_id
            self.attempts += 1
            raise OSError("injected persistent stage cleanup failure")

    database = tmp_path / "moss.sqlite3"
    audio_root = tmp_path / "meetings"

    async def refuse_then_recover():
        archive = MeetingAudioArchive(audio_root)
        stages = LiveMeetingAudioStages(archive, max_bytes=32_000)
        persistent = PersistentDiscardFailure(stages)
        store = await Phase2Store.open(database)
        try:
            await store.allow_email("a@example.com")
            admitted = await store.admit(GoogleIdentity("sub-a", "a@example.com", "A"))
            assert admitted is not None
            account, session_id = admitted
            workspace = store.workspace(account)
            live = Phase2LiveMeetings(
                RejectCreateRuntime(),
                audio_archive=archive,
                audio_stages=persistent,
            )
            with pytest.raises(ValueError, match="runtime creation refusal"):
                await live.create(
                    account=account,
                    workspace=workspace,
                    origin_session=session_id,
                    echo_mode=None,
                )
            meetings = await workspace.list_meetings()
            assert len(meetings) == 1
            meeting_id = meetings[0].meeting_id
            assert meetings[0].status == "active"
            assert persistent.attempts == 1
            assert stages.path(account.account_id, meeting_id).is_file()
        finally:
            await store.close()

        reopened_archive = MeetingAudioArchive(audio_root)
        reopened_stages = LiveMeetingAudioStages(reopened_archive, max_bytes=32_000)
        reopened = await Phase2Store.open(database)
        try:
            await reopened.recover_active_meetings(
                audio_archive=reopened_archive,
                live_audio_stages=reopened_stages,
            )
            account = await reopened.account_for_session(session_id)
            assert account is not None
            handle = await reopened.workspace(account).open_meeting(meeting_id)
            assert handle is not None
            return await handle.snapshot(), reopened_stages.path(account.account_id, meeting_id)
        finally:
            await reopened.close()

    snapshot, stage_path = asyncio.run(refuse_then_recover())
    assert snapshot.status == "interrupted"
    assert snapshot.audio is not None and snapshot.audio.state == "unavailable"
    assert not stage_path.exists()


def test_public_snapshot_waits_for_the_serialized_transcript_commit(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        binding = app.state.phase2_live._bindings[meeting_id]
        original_commit = binding.handle.commit_transcript
        commit_started = threading.Event()
        release_commit = threading.Event()

        async def held_commit(document, *, terminal=False):
            commit_started.set()
            released = await asyncio.to_thread(release_commit.wait, 5)
            assert released, "test did not release held transcript commit"
            return await original_commit(document, terminal=terminal)

        binding.handle.commit_transcript = held_commit
        feed_two_lane_span(client, meeting_id)
        assert commit_started.wait(timeout=2)
        raw = app.state.phase2_live.runtime.snapshot(meeting_id)
        assert raw is not None and raw.session.effective_transcript
        held = client.get(f"/api/live/sessions/{meeting_id}/snapshot").json()
        assert held["meeting_transcript_version"] == 0
        assert held["snapshot"]["session"]["effective_transcript"] == []

        release_commit.set()
        durable = wait_snapshot(
            client,
            meeting_id,
            lambda body: body["meeting_transcript_version"] == 1,
        )
        assert durable["snapshot"]["session"]["effective_transcript"][0]["text"] == (
            "owner live words"
        )
        assert client.post(
            f"/api/live/sessions/{meeting_id}/abort",
            json={"reason": "test complete"},
        ).status_code == 200


def test_account_revoke_fences_a_queued_revision_and_returns_401(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database, speech=(True, False, True, False))

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] == 1)
        binding = app.state.phase2_live._bindings[meeting_id]
        stages = app.state.phase2_live.audio_stages
        original_discard = stages.discard
        cleanup_attempts = 0

        def fail_first_cleanup(account_id: str, target_meeting_id: str) -> None:
            nonlocal cleanup_attempts
            cleanup_attempts += 1
            if cleanup_attempts == 1:
                raise OSError("injected transient revoked-stage cleanup failure")
            original_discard(account_id, target_meeting_id)

        stages.discard = fail_first_cleanup
        original_commit = binding.handle.commit_transcript
        commit_started = threading.Event()
        release_commit = threading.Event()

        async def held_late_commit(document, *, terminal=False):
            commit_started.set()
            released = await asyncio.to_thread(release_commit.wait, 5)
            assert released, "test did not release held late commit"
            return await original_commit(document, terminal=terminal)

        binding.handle.commit_transcript = held_late_commit
        feed_two_lane_pairs(client, meeting_id, range(3, 6))
        assert commit_started.wait(timeout=2)

        async def revoke() -> None:
            store = await Phase2Store.open(database)
            try:
                assert await store.revoke_email("a@example.com") is True
            finally:
                await store.close()

        asyncio.run(revoke())
        release_commit.set()
        assert client.get(f"/api/live/sessions/{meeting_id}/snapshot").status_code == 401
        deadline = time.monotonic() + 2
        while not binding.capture_fenced and time.monotonic() < deadline:
            time.sleep(0.01)
        assert binding.capture_fenced is True
        while not binding.terminal_persisted and time.monotonic() < deadline:
            time.sleep(0.01)
        assert binding.terminal_persisted is True
        assert cleanup_attempts == 2

    connection = sqlite3.connect(database)
    try:
        status, version, document = connection.execute(
            """
            SELECT m.status, t.version, t.document_json
            FROM meetings m
            JOIN meeting_transcripts t
              ON t.account_id = m.account_id AND t.meeting_id = m.meeting_id
            WHERE m.meeting_id = ?
            """,
            (meeting_id,),
        ).fetchone()
    finally:
        connection.close()
    assert (status, version) == ("interrupted", 1)
    assert len(json.loads(document)["segments"]) == 1
    meeting_dir = database.parent / "meetings" / "sub-a" / meeting_id
    assert not (meeting_dir / ".live-mix.pcm").exists()
    assert not tuple(meeting_dir.glob("*.mp3"))


@pytest.mark.parametrize(
    ("recovery_failures", "cleanup_verified"),
    ((1, True), (None, False)),
)
def test_revoke_after_mp3_publish_cleans_or_fences_unrecorded_artifact(
    tmp_path: Path,
    recovery_failures: int | None,
    cleanup_verified: bool,
):
    class RefusingRevokedCleanup(MeetingAudioArchive):
        def __init__(self, root: Path) -> None:
            super().__init__(root)
            self.publication_cleanup_attempts = 0
            self.recovery_cleanup_attempts = 0

        def discard(self, publication) -> None:
            del publication
            self.publication_cleanup_attempts += 1
            raise MeetingAudioCleanupError("injected publication cleanup refusal")

        def discard_unrecorded(self, account_id: str, target_meeting_id: str) -> None:
            self.recovery_cleanup_attempts += 1
            if (
                recovery_failures is None
                or self.recovery_cleanup_attempts <= recovery_failures
            ):
                raise MeetingAudioCleanupError("injected revoked recovery cleanup refusal")
            super().discard_unrecorded(account_id, target_meeting_id)

    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    archive = RefusingRevokedCleanup(tmp_path / "meetings")
    app = make_app(database, audio_archive=archive)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        binding = app.state.phase2_live._bindings[meeting_id]
        store = app.state.phase2_store
        original_commit = store._commit_meeting_audio
        revoked = False

        async def revoke_before_metadata(*args, **kwargs):
            nonlocal revoked
            if not revoked:
                revoked = True
                assert await store.revoke_email("a@example.com") is True
            return await original_commit(*args, **kwargs)

        store._commit_meeting_audio = revoke_before_metadata
        stopped = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        assert stopped.status_code == 200
        meeting_dir = tmp_path / "meetings" / "sub-a" / meeting_id
        assert archive.publication_cleanup_attempts == 1
        assert archive.recovery_cleanup_attempts == 2
        assert binding.terminal_persisted is cleanup_verified
        assert (meeting_dir / "audio.mp3").exists() is not cleanup_verified
        assert (meeting_dir / ".live-mix.pcm").exists() is not cleanup_verified
        if cleanup_verified:
            assert binding.unrecorded_cleanup_required is False
        else:
            assert binding.unrecorded_cleanup_required is True
            assert binding.persistence_failure == "meeting_authority_revoked"

        connection = sqlite3.connect(database)
        try:
            status = connection.execute(
                "SELECT status FROM meetings WHERE meeting_id = ?",
                (meeting_id,),
            ).fetchone()[0]
            audio_rows = connection.execute(
                "SELECT COUNT(*) FROM meeting_audio WHERE meeting_id = ?",
                (meeting_id,),
            ).fetchone()[0]
        finally:
            connection.close()
        assert status == "interrupted"
        assert audio_rows == 0

    if cleanup_verified:
        assert binding.terminal_persisted is True
        assert not (meeting_dir / "audio.mp3").exists()
        assert not (meeting_dir / ".live-mix.pcm").exists()
    else:
        # Shutdown retries the same remembered unrecorded-artifact obligation; a
        # persistent refusal still cannot make terminal settlement eligible.
        assert archive.recovery_cleanup_attempts >= 4
        assert binding.terminal_persisted is False
        assert binding.unrecorded_cleanup_required is True
        assert (meeting_dir / "audio.mp3").is_file()
        assert (meeting_dir / ".live-mix.pcm").is_file()


def test_revoke_after_audio_settlement_downgrades_before_terminal_publication(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(
        database,
        terminal_text="[0][S01]revoked terminal words[0.000375]",
    )
    observed: dict[str, object] = {}

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] == 1)
        binding = app.state.phase2_live._bindings[meeting_id]
        store = app.state.phase2_store
        original_finish = binding.handle.finish_with_transcript

        async def revoke_before_terminal_tuple(document, status):
            before = await binding.handle.snapshot()
            assert before.audio is not None and before.audio.relative_path is not None
            retained = tmp_path / "meetings" / before.audio.relative_path
            observed["audio"] = before.audio.to_dict()
            observed["bytes"] = retained.read_bytes()
            observed["raw_absent"] = not (
                tmp_path / "meetings" / "sub-a" / meeting_id / ".live-mix.pcm"
            ).exists()
            assert await store.revoke_email("a@example.com") is True
            return await original_finish(document, status)

        binding.handle.finish_with_transcript = revoke_before_terminal_tuple
        stopped = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        assert stopped.status_code == 200
        assert binding.terminal_persisted is True
        assert binding.persistence_failure == "meeting_authority_revoked"

    connection = sqlite3.connect(database)
    try:
        row = connection.execute(
            """
            SELECT m.status, t.document_json, ma.state, ma.relative_path, ma.byte_count,
                   ma.duration_ms, ma.format, ma.sample_rate_hz, ma.channels, ma.bit_rate_bps
            FROM meetings m
            JOIN meeting_transcripts t
              ON t.account_id = m.account_id AND t.meeting_id = m.meeting_id
            JOIN meeting_audio ma
              ON ma.account_id = m.account_id AND ma.meeting_id = m.meeting_id
            WHERE m.meeting_id = ?
            """,
            (meeting_id,),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    before_audio = observed["audio"]
    assert row[0] == "interrupted"
    assert json.loads(row[1])["segments"][0]["text"] == "owner live words"
    assert row[2] == "partial"
    assert row[3:] == tuple(
        before_audio[key]
        for key in (
            "relative_path",
            "byte_count",
            "duration_ms",
            "format",
            "sample_rate_hz",
            "channels",
            "bit_rate_bps",
        )
    )
    retained = tmp_path / "meetings" / row[3]
    assert retained.name == "audio.mp3"
    assert retained.read_bytes() == observed["bytes"]
    assert observed["raw_absent"] is True


def test_revoked_live_stage_cleanup_failure_is_reconciled_from_canonical_row_on_startup(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] == 1)
        binding = app.state.phase2_live._bindings[meeting_id]
        stages = app.state.phase2_live.audio_stages

        def always_fail(account_id: str, target_meeting_id: str) -> None:
            del account_id, target_meeting_id
            raise OSError("injected persistent revoked-stage cleanup failure")

        stages.discard = always_fail
        assert client.portal.call(
            app.state.phase2_store.revoke_email,
            "a@example.com",
        ) is True
        client.portal.call(
            app.state.phase2_live._fence,
            binding,
            "meeting_authority_revoked",
        )
        stage_path = tmp_path / "meetings" / "sub-a" / meeting_id / ".live-mix.pcm"
        assert stage_path.is_file()
        assert binding.terminal_persisted is False

    async def reallow() -> str:
        store = await Phase2Store.open(database)
        try:
            await store.allow_email("a@example.com")
            admitted = await store.admit(GoogleIdentity("sub-a", "a@example.com", "A"))
            assert admitted is not None
            return admitted[1]
        finally:
            await store.close()

    reallowed_session = asyncio.run(reallow())
    restarted = make_app(database)
    with TestClient(restarted, base_url="https://moss.test") as client:
        assert not stage_path.exists()
        session(client, reallowed_session)
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "interrupted"
        # Issue #18 owns moving cleanup before generation fencing; #17 must not
        # invent metadata after the captured authority was revoked.
        assert meeting["audio"] is None


def test_revoked_stage_cleanup_task_remains_owned_across_caller_cancellation(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        binding = app.state.phase2_live._bindings[meeting_id]
        stages = app.state.phase2_live.audio_stages
        original_discard = stages.discard
        cleanup_started = threading.Event()
        release_cleanup = threading.Event()

        def held_cleanup(account_id: str, target_meeting_id: str) -> None:
            cleanup_started.set()
            assert release_cleanup.wait(timeout=5)
            original_discard(account_id, target_meeting_id)

        stages.discard = held_cleanup

        async def cancel_caller() -> None:
            caller = asyncio.create_task(
                app.state.phase2_live._discard_stage_after_authority_loss(binding)
            )
            assert await asyncio.to_thread(cleanup_started.wait, 2)
            caller.cancel()
            with pytest.raises(asyncio.CancelledError):
                await caller
            owned = binding.authority_cleanup_task
            assert owned is not None and not owned.done()
            release_cleanup.set()
            assert await app.state.phase2_live._discard_stage_after_authority_loss(binding)
            assert owned.done()

        client.portal.call(cancel_caller)
        assert not (
            tmp_path / "meetings" / "sub-a" / meeting_id / ".live-mix.pcm"
        ).exists()


def test_terminal_transcript_and_status_roll_back_or_commit_as_one_tuple(tmp_path: Path):
    async def exercise() -> None:
        database = tmp_path / "atomic.sqlite3"
        store = await Phase2Store.open(database)
        try:
            await store.allow_email("a@example.com")
            admitted = await store.admit(GoogleIdentity("sub-a", "a@example.com", "A"))
            assert admitted is not None
            handle = await store.workspace(admitted[0]).create_meeting("live")
            old = {"segments": [{"id": "seg_0001", "text": "old"}]}
            final = {"segments": [{"id": "seg_0001", "text": "final"}]}
            assert await handle.commit_transcript(old) == 1
            await store._connection.execute(
                """
                CREATE TRIGGER refuse_terminal_document
                BEFORE UPDATE OF document_json ON meeting_transcripts
                WHEN NEW.document_json LIKE '%final%'
                BEGIN SELECT RAISE(ABORT, 'injected terminal write failure'); END
                """
            )
            await store._connection.commit()
            with pytest.raises(sqlite3.IntegrityError, match="injected terminal write failure"):
                await handle.finish_with_transcript(final, "completed")
            rolled_back = await handle.snapshot()
            assert (rolled_back.status, rolled_back.transcript_version, rolled_back.transcript) == (
                "active",
                1,
                old,
            )
            await store._connection.execute("DROP TRIGGER refuse_terminal_document")
            await store._connection.commit()
            assert await handle.finish_with_transcript(final, "completed") == 2
            committed = await handle.snapshot()
            assert (committed.status, committed.transcript_version, committed.transcript) == (
                "completed",
                2,
                final,
            )
        finally:
            await store.close()

    asyncio.run(exercise())
