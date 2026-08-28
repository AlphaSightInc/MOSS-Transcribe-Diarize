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
)


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
        stages = app.state.phase2_live.audio_stages
        original_discard = stages.discard
        attempts = 0

        def fail_once(account_id: str, target_meeting_id: str) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("injected transient stage cleanup failure")
            original_discard(account_id, target_meeting_id)

        stages.discard = fail_once
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
        assert meeting["audio"]["state"] == "available"
        meeting_dir = tmp_path / "meetings" / "sub-a" / meeting_id
        assert (meeting_dir / "audio.mp3").is_file()
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
        assert meeting["audio"]["state"] == "available"
        assert binding.terminal_persisted is False
        stage_path = tmp_path / "meetings" / "sub-a" / meeting_id / ".live-mix.pcm"
        assert stage_path.is_file()

    assert attempts >= 3
    restarted = make_app(database)
    with TestClient(restarted, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "interrupted"
        assert meeting["audio"]["state"] == "available"
        assert not stage_path.exists()


@pytest.mark.parametrize(
    ("scenario", "expected_state", "expected_name"),
    (
        ("zero", "unavailable", None),
        ("torn", "partial", "audio.partial.mp3"),
        ("orphan", "partial", "audio.partial.mp3"),
        ("metadata", "available", "audio.mp3"),
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
