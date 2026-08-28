from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
import threading
import time
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
    hash_config,
)
from moss_transcribe_diarize.app.live_session import (
    LIVE_SAMPLE_RATE,
    AudioFrame,
    FrozenSpan,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
)
from moss_transcribe_diarize.app.phase2 import (
    GoogleIdentity,
    Phase2Store,
    SESSION_COOKIE,
    create_phase2_app,
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


def make_runtime(*, speech: tuple[bool, ...] = (True, False)) -> LiveServiceRuntime:
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
        identity_preparer_factory=Identity,
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
):
    return create_phase2_app(
        database_path=database,
        oidc=NeverOidc(),
        oauth_cookie_secret="test-cookie-secret",
        live_runtime_factory=lambda: make_runtime(speech=speech),
        live_helper_lease_seconds=lease_seconds,
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
    app = make_app(database)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, None)
        assert client.get("/api/live/descriptor").status_code == 401

        session(client, sessions["a"])
        workspace = client.get("/")
        assert 'data-live-capture="account"' in workspace.text
        assert '<meta name="moss-authority" content="account">' in workspace.text
        assert "Capture bearer" not in workspace.text
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
        assert stopped.json()["snapshot"]["session"]["status"] == "closed"
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["status"] == "completed"
        # Stop drains the mixer's intentionally held tail, producing one final accepted revision.
        assert meeting["transcript_version"] == 2
        assert meeting["transcript"]["segments"][0]["speaker"] == "S01"
        assert meeting["transcript"]["segments"][0]["text"] == "owner live words"
        assert client.post(
            f"/api/live/sessions/{meeting_id}/frames",
            json=v2_frame(3, "system"),
        ).status_code == 409


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
