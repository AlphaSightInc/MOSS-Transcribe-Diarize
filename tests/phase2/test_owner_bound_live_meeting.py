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

from _browser_workspace_fixtures import seed_workspace

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
    Phase2Store,
    SESSION_COOKIE,
    create_phase2_app,
)
from moss_transcribe_diarize.app.phase2_audio import (
    LiveMeetingAudioStages,
    MeetingAudioArchive,
    MeetingAudioCleanupError,
)
from moss_transcribe_diarize.app.phase2_admin import (
    execute as execute_admin,
    execute_interrupt,
)
from moss_transcribe_diarize.app.phase2_control import Phase2ControlError
from moss_transcribe_diarize.app.phase2_live import Phase2LiveMeetings



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


class HeldDecoder:
    max_samples = 4_000

    def __init__(self, started: threading.Event, release: threading.Event):
        self.started = started
        self.release = release

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        del span, pcm
        self.started.set()
        assert self.release.wait(timeout=5), "test did not release held Live inference"
        return InferenceTranscript("[0][S01]late inference result[0.000125]")


class HoldSecondDecoder:
    max_samples = 4_000

    def __init__(
        self,
        second_started: threading.Event,
        release_second: threading.Event,
        second_finished: threading.Event,
    ) -> None:
        self.second_started = second_started
        self.release_second = release_second
        self.second_finished = second_finished
        self.calls = 0

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        del pcm
        self.calls += 1
        if self.calls == 2:
            self.second_started.set()
            assert self.release_second.wait(timeout=5), "test did not release second inference"
            self.second_finished.set()
        seconds = span.sample_count / LIVE_SAMPLE_RATE
        return InferenceTranscript(f"[0][S01]ordered inference[{seconds:g}]")


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
    def fork_lane(self):
        # A lane gets its own preparer; held-event fixtures retain their shared controls.
        from copy import copy
        return copy(self)

    def prepare_revision(self, **kwargs):
        from dataclasses import replace
        return replace(self.prepare(**kwargs), relabeled_transcript=kwargs['transcript'])

    def prepare(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        transcript: str,
        base_snapshot: LiveIdentitySnapshot,
        allowed_speakers: tuple[str, ...] | None = None,
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


class EligibleIdentity(Identity):
    def journal_observations(self):
        return (
            SimpleNamespace(
                speaker_label="speaker-0001",
                centroid=(0.6, 0.8),
                sample_seconds=2.0,
                exemplar_count=2,
                provisional=False,
                embedder_id="wespeaker:test-revision",
                embedder_state_sha="ab" * 32,
            ),
        )


class ControlledIdentity(Identity):
    def __init__(self, state: dict[str, float]) -> None:
        self.state = state

    def journal_observations(self):
        return (
            SimpleNamespace(
                speaker_label="speaker-0001",
                centroid=(1.0, 0.0),
                sample_seconds=self.state["seconds"],
                exemplar_count=2,
                provisional=False,
                embedder_id="wespeaker:test-revision",
                embedder_state_sha="ab" * 32,
            ),
        )


def make_runtime(
    *,
    speech: tuple[bool, ...] = (True, False),
    terminal_text: str | None = None,
    terminal_scheduler: _ManualTerminalScheduler | None = None,
    max_tape_bytes: int = 32_000,
    decoder_factory=Decoder,
    identity_factory=Identity,
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
        decoder_factory=decoder_factory,
        rolling_decoder_factory=None if terminal_text is None else Decoder,
        identity_preparer_factory=identity_factory,
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
        admitted_a = await seed_workspace(store, "sub-a")
        observer_a = await seed_workspace(store, "sub-a")
        admitted_b = await seed_workspace(store, "sub-b")
        assert admitted_a is not None and observer_a is not None and admitted_b is not None
        return {
            "a": admitted_a[1],
            "a-observer": observer_a[1],
            "b": admitted_b[1],
        }
    finally:
        await store.close()


async def force_historical_authority_loss(store: Phase2Store, email: str) -> None:
    """Inject the pre-#18 authority-first state for #17 recovery regressions only."""

    target = await store.account_revoke_target(email)
    assert target.account is not None
    account = target.account
    now = int(time.time() * 1_000)
    async with store._mutation():
        await store._connection.execute(
            """
            UPDATE accounts SET enabled = 0,
                authority_generation = authority_generation + 1, updated_at_ms = ?
            WHERE account_id = ? AND authority_generation = ?
            """,
            (now, account.account_id, account.authority_generation),
        )
        await store._connection.execute(
            "DELETE FROM sign_in_sessions WHERE account_id = ?", (account.account_id,)
        )
        await store._connection.execute(
            """
            UPDATE meetings SET status = 'interrupted', updated_at_ms = ?
            WHERE account_id = ? AND status = 'active'
            """,
            (now, account.account_id),
        )


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
    decoder_factory=Decoder,
    identity_factory=Identity,
):
    return create_phase2_app(
        database_path=database,
        live_runtime_factory=lambda: make_runtime(
            speech=speech,
            terminal_text=terminal_text,
            terminal_scheduler=terminal_scheduler,
            max_tape_bytes=max_tape_bytes,
            decoder_factory=decoder_factory,
            identity_factory=identity_factory,
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
        # Lifecycle tests need one decoded voice. Digital zero now correctly skips ASR.
        "pcm_base64": base64.b64encode((b"\x01\x00" if lane == "system" else b"\0\0") * samples).decode("ascii"),
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
        admitted = await seed_workspace(store, "sub-a")
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
        # Another tab shares the same browser credential, not a separate sign-in.
        assert sessions["a-observer"] == sessions["a"]

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
        assert stopped.status_code == 200, stopped.text
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
            app.state.phase2_store.revoke_account,
            "sub-a",
        ) is True
        assert client.get(f"/api/meetings/{meeting_id}/audio/download").status_code == 401


def test_saved_live_transcript_keeps_attributed_id_and_omits_unattributed_id():
    from moss_transcribe_diarize.app.phase2_live import _transcript_document

    snapshot = SimpleNamespace(
        descriptor=SimpleNamespace(sample_rate=16000),
        session=SimpleNamespace(
            identity_snapshot=SimpleNamespace(canonical_speakers=("canonical-a",)),
            effective_transcript=(
                SimpleNamespace(start_sample=0, end_sample=16000, canonical_speaker="canonical-a", text="Named speech"),
                SimpleNamespace(start_sample=16000, end_sample=32000, canonical_speaker=None, text="Unattributed speech"),
            ),
        ),
    )
    assert _transcript_document(snapshot, {"canonical-a": "Alex"}) == {"segments": [
        {"id": "seg_0001", "start": 0.0, "end": 1.0, "speaker_entity_id": "canonical-a", "speaker": "Alex", "text": "Named speech"},
        {"id": "seg_0002", "start": 1.0, "end": 2.0, "speaker": "S00", "text": "Unattributed speech"},
    ]}


def test_manual_speaker_name_route_relabels_and_enrolls_only_the_owner_voiceprint(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database, identity_factory=EligibleIdentity)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        assert client.post(
            f"/api/live/sessions/{meeting_id}/heartbeat",
            json=heartbeat(),
        ).status_code == 200
        feed_two_lane_span(client, meeting_id)
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] == 1)

        named = client.put(
            f"/api/meetings/{meeting_id}/speakers/speaker-0001/name",
            json={"label": "  Alex  "},
        )
        assert named.status_code == 200
        assert named.json() == {
            "meeting_id": meeting_id,
            "speaker_id": "speaker-0001",
            "label": "Alex",
            "voiceprint_id": named.json()["voiceprint_id"],
            "enrollment": "enrolled",
            "transcript_version": 2,
        }
        assert isinstance(named.json()["voiceprint_id"], str)
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["transcript"]["segments"][0]["speaker"] == "Alex"
        assert meeting["transcript"]["segments"][0]["speaker_entity_id"] == "speaker-0001"
        live = client.get(f"/api/live/sessions/{meeting_id}/snapshot").json()
        assert live["speaker_labels"] == {"speaker-0001": "Alex"}
        assert live["speaker_label_revision"] == 1
        owner_bank = client.get("/api/voiceprints").json()
        assert owner_bank == {
            "voiceprints": [
                {
                    "id": named.json()["voiceprint_id"],
                    "label": "Alex",
                    "embedder_id": "wespeaker:test-revision",
                    "embedding_dimension": 2,
                    "revision": 1,
                    "sample_count": 1,
                }
            ]
        }

        session(client, sessions["b"])
        assert client.get("/api/voiceprints").json() == {"voiceprints": []}
        foreign = client.put(
            f"/api/meetings/{meeting_id}/speakers/speaker-0001/name",
            json={"label": "foreign"},
        )
        assert foreign.status_code == 404
        session(client, sessions["a"])
        assert client.get("/api/voiceprints").json() == owner_bank
        assert client.put(
            f"/api/meetings/{meeting_id}/speakers/not-a-speaker/name",
            json={"label": "nobody"},
        ).status_code == 404

        stopped = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        assert stopped.status_code == 200, stopped.text
        final_meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert final_meeting["transcript"]["segments"][0]["speaker"] == "Alex"
        assert final_meeting["transcript"]["segments"][0]["speaker_entity_id"] == "speaker-0001"
        assert client.get("/api/voiceprints").json() == owner_bank


@pytest.mark.parametrize("ending", ["stop", "abort"])
def test_terminal_action_clears_unfulfilled_manual_name_but_preserves_transcript_text(
    tmp_path: Path,
    ending: str,
):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    evidence_state = {"seconds": 1.5}
    app = make_app(database, identity_factory=lambda: ControlledIdentity(evidence_state))

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] == 1)

        named = client.put(
            f"/api/meetings/{meeting_id}/speakers/speaker-0001/name",
            json={"label": "Pending name"},
        )
        assert named.status_code == 200
        assert named.json()["enrollment"] == "pending"
        assert named.json()["voiceprint_id"] is None
        assert app.state.phase2_speaker_identity.pending_count == 1
        assert client.get("/api/voiceprints").json() == {"voiceprints": []}

        # Newly eligible final-tail evidence must not complete the pending enrollment.
        evidence_state["seconds"] = 2.0
        terminal = client.post(
            f"/api/live/sessions/{meeting_id}/{ending}",
            json={"deadline": 2.0} if ending == "stop" else {"reason": "test abort"},
        )
        assert terminal.status_code == 200
        assert app.state.phase2_speaker_identity.pending_count == 0
        meeting = client.get(f"/api/meetings/{meeting_id}").json()
        assert meeting["transcript"]["segments"][0]["speaker"] == "Pending name"
        assert client.get("/api/voiceprints").json() == {"voiceprints": []}


def test_first_later_eligible_live_centroid_completes_pending_exactly_once(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    evidence_state = {"seconds": 1.5}
    app = make_app(
        database,
        speech=(True, False, True, False, True, False),
        identity_factory=lambda: ControlledIdentity(evidence_state),
    )

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] == 1)
        named = client.put(
            f"/api/meetings/{meeting_id}/speakers/speaker-0001/name",
            json={"label": "Later eligible"},
        )
        assert named.json()["enrollment"] == "pending"
        assert client.get("/api/voiceprints").json() == {"voiceprints": []}

        evidence_state["seconds"] = 2.0
        feed_two_lane_pairs(client, meeting_id, range(3, 6))
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] >= 3)
        enrolled = client.get("/api/voiceprints").json()["voiceprints"]
        assert [(item["label"], item["sample_count"]) for item in enrolled] == [
            ("Later eligible", 1)
        ]
        assert app.state.phase2_speaker_identity.pending_count == 0

        feed_two_lane_pairs(client, meeting_id, range(6, 9))
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] >= 4)
        assert client.get("/api/voiceprints").json()["voiceprints"] == enrolled


def test_cancelled_manual_name_joins_commit_publication_and_pending_before_next_revision(tmp_path):
    database = tmp_path / "moss.sqlite3"
    sessions = asyncio.run(provision(database))
    evidence_state = {"seconds": 1.5}
    app = make_app(
        database, speech=(True, False, True, False),
        identity_factory=lambda: ControlledIdentity(evidence_state),
    )
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] == 1)
        async def cancel_after_commit():
            store = app.state.phase2_store
            identity = app.state.phase2_speaker_identity
            owner = await store.account_for_session(sessions["a"])
            workspace = store.workspace(owner)
            handle = await workspace.open_meeting(meeting_id)
            committed, release = asyncio.Event(), asyncio.Event()
            original = store._connection.commit
            async def held_commit():
                await original()
                committed.set()
                await release.wait()
            store._connection.commit = held_commit
            try:
                caller = asyncio.create_task(identity.bank(workspace).name_speaker(
                    handle, "speaker-0001", "Surviving name",
                ))
                await asyncio.wait_for(committed.wait(), timeout=3)
                caller.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await caller
                assert identity._naming_tasks
                assert all(not task.cancelled() for task in identity._naming_tasks)
                release.set()
                await identity.shutdown()
                binding = app.state.phase2_live._bindings[meeting_id]
                assert binding.speaker_labels == {"speaker-0001": "Surviving name"}
                assert binding.durable_version == 2
                assert identity.pending_count == 1
            finally:
                release.set()
                store._connection.commit = original
        client.portal.call(cancel_after_commit)
        feed_two_lane_pairs(client, meeting_id, range(3, 6))
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] >= 3)
        saved = client.get(f"/api/meetings/{meeting_id}").json()
        assert {segment["speaker"] for segment in saved["transcript"]["segments"]} == {"Surviving name"}


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
        assert stopped.status_code == 200, stopped.text
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
        second_binding = live._bindings[second]
        original_second_commit = second_binding.handle.commit_transcript
        admitted_commit_entered = threading.Event()
        release_admitted_commit = threading.Event()

        async def held_second_commit(document, *, terminal=False):
            admitted_commit_entered.set()
            assert await asyncio.to_thread(release_admitted_commit.wait, 5)
            return await original_second_commit(document, terminal=terminal)

        second_binding.handle.commit_transcript = held_second_commit
        feed_two_lane_span(client, second)
        assert admitted_commit_entered.wait(timeout=2)
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
                    execute_admin(socket, "revoke", "sub-a")
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
        assert second_binding.publication_fenced is True
        release_admitted_commit.set()
        deadline = time.monotonic() + 2
        while second_binding.worker is not None and not second_binding.worker.done():
            if time.monotonic() >= deadline:
                raise AssertionError("fenced publication worker did not quiesce")
            time.sleep(0.01)
        connection = sqlite3.connect(database)
        try:
            assert connection.execute(
                "SELECT version FROM meeting_transcripts WHERE meeting_id = ?",
                (second,),
            ).fetchone() == (1,)
        finally:
            connection.close()
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
        assert asyncio.run(execute_admin(socket, "revoke", "sub-a")) == {
            "account_id": "sub-a",
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


def test_revoke_joins_admitted_commit_and_skips_queued_second_publication(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i18-durable-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    app = make_app(
        database,
        control_socket=socket,
        speech=(True, False, True, False),
    )

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        binding = app.state.phase2_live._bindings[meeting_id]
        original_commit = binding.handle.commit_transcript
        commit_started = threading.Event()
        release_commit = threading.Event()
        admitted_document: dict[str, object] | None = None

        async def held_commit(document, *, terminal=False):
            nonlocal admitted_document
            admitted_document = document
            commit_started.set()
            assert await asyncio.to_thread(release_commit.wait, 5)
            return await original_commit(document, terminal=terminal)

        binding.handle.commit_transcript = held_commit
        feed_two_lane_span(client, meeting_id)
        assert commit_started.wait(timeout=2)
        assert admitted_document is not None
        feed_two_lane_pairs(client, meeting_id, range(3, 6))
        raw = app.state.phase2_live.runtime.snapshot(meeting_id)
        assert raw is not None
        assert len(raw.session.effective_transcript) > len(admitted_document["segments"])
        outcome: dict[str, object] = {}

        def revoke() -> None:
            try:
                outcome["result"] = asyncio.run(
                    execute_admin(socket, "revoke", "sub-a")
                )
            except Exception as exc:  # pragma: no cover - asserted below.
                outcome["error"] = exc

        worker = threading.Thread(target=revoke)
        worker.start()
        deadline = time.monotonic() + 2
        while not binding.publication_fenced:
            if time.monotonic() >= deadline:
                raise AssertionError("Account result fence was not installed")
            time.sleep(0.01)
        assert binding.worker is not None and not binding.worker.cancelled()
        release_commit.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert outcome == {
            "result": {"account_id": "sub-a", "revoked": True},
        }

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
        audio_state = connection.execute(
            "SELECT state FROM meeting_audio WHERE meeting_id = ?", (meeting_id,)
        ).fetchone()[0]
    finally:
        connection.close()
    assert (status, version, json.loads(document)) == (
        "interrupted",
        1,
        admitted_document,
    )
    assert audio_state in {"partial", "unavailable"}


def test_operator_interrupt_joins_admitted_live_commit_and_skips_late_result(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i20-live-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    second_decode_started = threading.Event()
    release_second_decode = threading.Event()
    second_decode_finished = threading.Event()
    app = make_app(
        database,
        control_socket=socket,
        speech=(True, False, True, False, True, False),
        decoder_factory=lambda: HoldSecondDecoder(
            second_decode_started,
            release_second_decode,
            second_decode_finished,
        ),
    )

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        target = client.post("/api/live/sessions").json()["id"]
        peer = client.post("/api/live/sessions").json()["id"]
        binding = app.state.phase2_live._bindings[target]
        peer_binding = app.state.phase2_live._bindings[peer]
        original_commit = binding.handle.commit_transcript
        commit_started = threading.Event()
        release_commit = threading.Event()
        admitted_document: dict[str, object] | None = None

        async def held_commit(document, *, terminal=False):
            nonlocal admitted_document
            admitted_document = document
            commit_started.set()
            assert await asyncio.to_thread(release_commit.wait, 5)
            return await original_commit(document, terminal=terminal)

        binding.handle.commit_transcript = held_commit
        feed_two_lane_span(client, target)
        assert commit_started.wait(timeout=2)
        assert admitted_document is not None
        feed_two_lane_pairs(client, target, range(3, 6))
        assert second_decode_started.wait(timeout=2)
        live = app.state.phase2_live
        runtime = live.runtime
        with runtime._lock:
            target_state = runtime._sessions[target]
            target_state.arbiter.submit_batch(
                key="unrelated-batch",
                payload={"kind": "batch"},
            )
            canonical = target_state.arbiter.submit_live_canonical(
                key=f"{target}:queued-canonical",
                payload={"kind": "canonical"},
            )
            runtime._record_canonical_queued(target_state, canonical.item_id)
            refinement = target_state.arbiter.submit_live_refinement(
                coalesce_key=f"{target}:queued-refinement",
                payload={"kind": "refinement"},
            )
            target_state.rolling_timing[refinement.item_id] = SimpleNamespace(
                queued_ns=runtime._monotonic_ns(),
                started_ns=None,
                window_index=9,
                start_sample=0,
                end_sample=2,
            )
            target_state.arbiter.submit_live_provisional(
                coalesce_key=f"{target}:queued-provisional",
                payload={"kind": "provisional"},
            )
            queued_canonical_ids = {
                item.id for item in target_state.arbiter._live_canonical
            }
            queued_refinement_ids = {
                item.id for item in target_state.arbiter._live_refinement.values()
            }
        feed_two_lane_span(client, peer)
        aggregate_before = live.operator_snapshot()["queues"]
        assert aggregate_before["live_canonical"] >= 2
        assert aggregate_before["live_refinement"] == 1
        assert aggregate_before["live_provisional"] == 1
        assert aggregate_before["batch"] == 1

        outcome: dict[str, object] = {}

        def interrupt() -> None:
            outcome["result"] = asyncio.run(execute_interrupt(socket, target))

        worker = threading.Thread(target=interrupt)
        worker.start()
        deadline = time.monotonic() + 2
        while not binding.publication_fenced:
            if time.monotonic() >= deadline:
                raise AssertionError("operator Live result fence was not installed")
            time.sleep(0.01)
        assert peer_binding.publication_fenced is False
        assert worker.is_alive()
        deadline = time.monotonic() + 2
        while runtime.snapshot(target).terminal_failure is None:
            if time.monotonic() >= deadline:
                raise AssertionError("raw runtime fence was not installed synchronously")
            time.sleep(0.005)
        with runtime._lock:
            target_queues = runtime._sessions[target].arbiter.snapshot()
        aggregate_after_claim = live.operator_snapshot()["queues"]
        assert (
            target_queues.live_canonical,
            target_queues.live_refinement,
            target_queues.live_provisional,
        ) == (0, 0, 0)
        assert aggregate_after_claim["live_canonical"] == 1
        assert aggregate_after_claim["live_refinement"] == 0
        assert aggregate_after_claim["live_provisional"] == 0
        assert aggregate_after_claim["batch"] == 1
        target_events = runtime.events(target)
        canonical_discarded = [
            event for event in target_events if event.kind == "canonical_discarded"
        ]
        assert {event.payload["item_id"] for event in canonical_discarded} == queued_canonical_ids
        assert queued_canonical_ids.isdisjoint(
            {
                event.payload["item_id"]
                for event in target_events
                if event.kind == "canonical_started"
            }
        )
        refinement_terminal = [
            event
            for event in target_events
            if event.kind == "rolling_decode_completed"
            and event.payload["outcome"] == "session_terminal"
        ]
        assert {
            event.payload["item_id"] for event in refinement_terminal
        } == queued_refinement_ids
        accounted_before_release = runtime.snapshot(target).session.accounted_samples
        release_second_decode.set()
        assert second_decode_finished.wait(timeout=2)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            peer_raw = runtime.snapshot(peer)
            if peer_raw.session.accounted_samples > 0 and peer_raw.pending_work_items == 0:
                break
            time.sleep(0.005)
        else:  # pragma: no cover - the assertion above owns the timeout.
            raise AssertionError("peer work did not complete while owner commit stayed held")
        assert runtime.snapshot(target).session.accounted_samples == accounted_before_release
        assert worker.is_alive()
        release_commit.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert outcome == {
            "result": {"meeting_id": target, "interrupted": True},
        }
        assert asyncio.run(execute_interrupt(socket, target)) == {
            "meeting_id": target,
            "interrupted": False,
        }
        assert client.get("/api/auth/session").status_code == 200
        target_meeting = client.get(f"/api/meetings/{target}").json()
        assert target_meeting["status"] == "interrupted"
        assert target_meeting["transcript"] == admitted_document
        public_events = client.get(f"/api/live/sessions/{target}/events").json()["events"]
        assert {
            event["payload"]["item_id"]
            for event in public_events if event["kind"] == "canonical_discarded"
        } == queued_canonical_ids
        assert target_meeting["audio"]["state"] in {"partial", "unavailable"}
        assert client.get(f"/api/meetings/{peer}").json()["status"] == "active"
        assert client.post(
            f"/api/live/sessions/{peer}/heartbeat",
            json=heartbeat(),
        ).status_code == 200
        assert client.post(
            f"/api/live/sessions/{target}/frames",
            json=v2_frame(6, "system"),
        ).status_code == 409

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
            (target,),
        ).fetchone()
    finally:
        connection.close()
    assert (status, version, json.loads(document)) == (
        "interrupted",
        1,
        admitted_document,
    )


def test_operator_interrupt_returns_durable_while_held_live_inference_is_later_discarded(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i20-held-live-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    decode_started = threading.Event()
    release_decode = threading.Event()
    app = make_app(
        database,
        control_socket=socket,
        decoder_factory=lambda: HeldDecoder(decode_started, release_decode),
    )

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        target = client.post("/api/live/sessions").json()["id"]
        peer = client.post("/api/live/sessions").json()["id"]
        feed_errors: list[BaseException] = []

        def feed() -> None:
            try:
                feed_two_lane_span(client, target)
            except BaseException as exc:  # pragma: no cover - asserted empty below.
                feed_errors.append(exc)

        feeder = threading.Thread(target=feed)
        feeder.start()
        assert decode_started.wait(timeout=2)
        live = app.state.phase2_live
        runtime = live.runtime
        with runtime._lock:
            target_state = runtime._sessions[target]
            target_state.arbiter.submit_live_canonical(
                key=f"{target}:queued-canonical",
                payload={"kind": "canonical"},
            )
            target_state.arbiter.submit_live_refinement(
                coalesce_key=f"{target}:queued-refinement",
                payload={"kind": "refinement"},
            )
            target_state.arbiter.submit_live_provisional(
                coalesce_key=f"{target}:queued-provisional",
                payload={"kind": "provisional"},
            )
            target_queues = target_state.arbiter.snapshot()
        feed_two_lane_span(client, peer)
        aggregate_before = live.operator_snapshot()["queues"]
        assert (
            target_queues.live_canonical,
            target_queues.live_refinement,
            target_queues.live_provisional,
        ) == (1, 1, 1)
        assert (
            aggregate_before["live_canonical"],
            aggregate_before["live_refinement"],
            aggregate_before["live_provisional"],
        ) == (2, 1, 1)

        result = asyncio.run(execute_interrupt(socket, target))
        assert result == {"meeting_id": target, "interrupted": True}
        with runtime._lock:
            target_after = runtime._sessions[target].arbiter.snapshot()
        aggregate_after = live.operator_snapshot()["queues"]
        assert (
            target_after.live_canonical,
            target_after.live_refinement,
            target_after.live_provisional,
        ) == (0, 0, 0)
        assert (
            aggregate_after["live_canonical"],
            aggregate_after["live_refinement"],
            aggregate_after["live_provisional"],
        ) == (1, 0, 0)
        assert asyncio.run(execute_interrupt(socket, target)) == {
            "meeting_id": target,
            "interrupted": False,
        }
        durable = client.get(f"/api/meetings/{target}").json()
        assert durable["status"] == "interrupted"
        assert durable["transcript"] is None
        assert durable["audio"]["state"] in {"partial", "unavailable"}
        assert client.get(f"/api/meetings/{peer}").json()["status"] == "active"

        release_decode.set()
        feeder.join(timeout=5)
        assert not feeder.is_alive()
        assert feed_errors == []
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            peer_raw = runtime.snapshot(peer)
            if peer_raw.session.accounted_samples > 0 and peer_raw.pending_work_items == 0:
                break
            time.sleep(0.005)
        else:  # pragma: no cover - the assertion above owns the timeout.
            raise AssertionError("peer Live work did not complete")
        after_late_result = client.get(f"/api/meetings/{target}").json()
        assert after_late_result["status"] == "interrupted"
        assert after_late_result["transcript"] is None
        assert runtime.snapshot(target).session.accounted_samples == 0
        assert client.post(
            f"/api/live/sessions/{peer}/heartbeat",
            json=heartbeat(),
        ).status_code == 200


def test_operator_interrupt_downgrades_verified_complete_live_audio_without_reencoding(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i20-live-audio-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    app = make_app(database, control_socket=socket)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        live = app.state.phase2_live
        binding = live._bindings[meeting_id]
        stage = live.audio_stages.create(meeting_id)
        stage.append_mixed(
            pcm=b"\x01\x00" * 1600,
            start_timestamp_ns=0,
            sample_count=1600,
            sample_rate=LIVE_SAMPLE_RATE,
        )
        live.audio_stages.release(meeting_id)
        stage_path = live.audio_stages.path("sub-a", meeting_id)
        async def publish_complete_audio():
            return await binding.handle.publish_audio(
                live.audio_archive,
                stage_path,
                partial=False,
                raw_pcm=True,
            )

        available = client.portal.call(publish_complete_audio)
        assert available.state == "available"
        artifact = database.parent / "meetings" / available.relative_path
        original_bytes = artifact.read_bytes()
        original = available.to_dict()

        assert asyncio.run(execute_interrupt(socket, meeting_id)) == {
            "meeting_id": meeting_id,
            "interrupted": True,
        }
        terminal = client.get(f"/api/meetings/{meeting_id}").json()
        assert terminal["status"] == "interrupted"
        assert terminal["audio"] == {**original, "state": "partial"}
        assert artifact.read_bytes() == original_bytes
        assert not stage_path.exists()


def test_revoke_joins_real_commit_before_binding_coroutine_resumes(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i18-commit-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    app = make_app(database, control_socket=socket)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        binding = app.state.phase2_live._bindings[meeting_id]
        connection = app.state.phase2_store._connection
        original_commit = connection.commit
        original_target = app.state.phase2_store.account_revoke_target
        real_commit_completed = threading.Event()
        release_commit_result = threading.Event()
        target_resolved = threading.Event()
        release_target = threading.Event()
        hold_once = True

        async def commit_then_hold():
            nonlocal hold_once
            await original_commit()
            if hold_once:
                hold_once = False
                real_commit_completed.set()
                assert await asyncio.to_thread(release_commit_result.wait, 5)

        async def resolve_target_then_hold(email):
            target = await original_target(email)
            target_resolved.set()
            assert await asyncio.to_thread(release_target.wait, 5)
            return target

        connection.commit = commit_then_hold
        app.state.phase2_store.account_revoke_target = resolve_target_then_hold
        outcome: dict[str, object] = {}

        def revoke() -> None:
            try:
                outcome["result"] = asyncio.run(
                    execute_admin(socket, "revoke", "sub-a")
                )
            except Exception as exc:  # pragma: no cover - asserted below.
                outcome["error"] = exc

        worker = threading.Thread(target=revoke)
        worker.start()
        assert target_resolved.wait(timeout=2)
        feed_two_lane_span(client, meeting_id)
        assert real_commit_completed.wait(timeout=2)
        durable_connection = sqlite3.connect(database)
        try:
            held_version, held_document = durable_connection.execute(
                """
                SELECT version, document_json FROM meeting_transcripts
                WHERE meeting_id = ?
                """,
                (meeting_id,),
            ).fetchone()
        finally:
            durable_connection.close()
        assert held_version == 1
        assert binding.durable_version == 0
        assert binding.durable_document == {"segments": []}
        release_target.set()
        deadline = time.monotonic() + 2
        while not binding.publication_fenced:
            if time.monotonic() >= deadline:
                raise AssertionError("Account result fence was not installed")
            time.sleep(0.01)
        assert worker.is_alive()
        assert binding.worker is not None and not binding.worker.cancelled()
        release_commit_result.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert outcome == {
            "result": {"account_id": "sub-a", "revoked": True},
        }

    durable_connection = sqlite3.connect(database)
    try:
        status, version, final_document = durable_connection.execute(
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
        durable_connection.close()
    assert (status, version, json.loads(final_document)) == (
        "interrupted",
        1,
        json.loads(held_document),
    )


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

        assert asyncio.run(execute_admin(socket, "revoke", "sub-a")) == {
            "account_id": "sub-a",
            "revoked": True,
        }
        session(client, sessions["a"])
        assert client.get("/api/auth/session").status_code == 401
        session(client, sessions["a-observer"])
        assert client.get("/api/auth/session").status_code == 401
        session(client, sessions["b"])
        assert client.get(f"/api/live/sessions/{other_meeting}/snapshot").status_code == 200

        async def fresh_session() -> tuple[int, str]:
            admitted = await app.state.phase2_store.bootstrap_browser(None)
            assert admitted is not None
            return admitted[0].authority_generation, admitted[1]

        generation, new_session = client.portal.call(fresh_session)
        assert generation == 0
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


@pytest.mark.parametrize("hold_identity_cleanup", [False, True])
def test_failure_fence_closes_publication_before_joining_accepted_stop(hold_identity_cleanup):
    async def exercise():
        live = Phase2LiveMeetings(object(), audio_archive=None, audio_stages=None)
        completed = asyncio.Event()
        identity_lock = asyncio.Lock()
        if hold_identity_cleanup:
            await identity_lock.acquire()
        async def clear_identity(_handle):
            async with identity_lock:
                pass
        live._speaker_identity = SimpleNamespace(clear_meeting=clear_identity)
        binding = SimpleNamespace(
            terminal_persisted=False, raw_stop_attempt=SimpleNamespace(completed=completed),
            capture_fenced=False, publication_fenced=False, queue=asyncio.Queue(),
            raw_event_high_water=-1, handle=SimpleNamespace(meeting_id="m"),
            persistence_failure=None, durable_document={},
        )
        async def abort(*_args):
            return None
        async def settle(*_args, **_kwargs):
            pass
        live.runtime = SimpleNamespace(snapshot=lambda _: None, events=lambda _: (), abort=abort)
        live._bindings["m"] = binding
        live._accepting_publications = True
        live._settle_terminal = settle
        fence = asyncio.create_task(live._fence(binding, "transcript_persistence_failed"))
        await asyncio.sleep(0)
        live._accept_raw("m", None, (SimpleNamespace(seq=1),))
        observed = (binding.publication_fenced, binding.capture_fenced, binding.queue.qsize())
        completed.set()
        if hold_identity_cleanup:
            live._accept_raw("m", None, (SimpleNamespace(seq=2),))
            assert binding.queue.qsize() == 0
            identity_lock.release()
        await fence
        assert observed == (True, False, 0)
    asyncio.run(exercise())


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
        assert stopped.status_code == 200, stopped.text
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
        assert stopped.status_code == 200, stopped.text
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


def test_account_result_fence_joins_terminal_audio_thread_instead_of_cancelling(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i18-terminal-fence-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    app = make_app(database, control_socket=socket)

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        binding = app.state.phase2_live._bindings[meeting_id]
        archive = app.state.phase2_audio_archive
        original_publish = archive.publish_live_prefix
        publish_started = threading.Event()
        release_publish = threading.Event()
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
            outcomes["stop"] = client.post(
                f"/api/live/sessions/{meeting_id}/stop",
                json={"deadline": 2.0},
            )

        def revoke() -> None:
            outcomes["revoke"] = asyncio.run(
                execute_admin(socket, "revoke", "sub-a")
            )

        stop_thread = threading.Thread(target=stop_meeting)
        stop_thread.start()
        assert publish_started.wait(timeout=2)
        revoke_thread = threading.Thread(target=revoke)
        revoke_thread.start()
        deadline = time.monotonic() + 2
        while not binding.publication_fenced:
            if time.monotonic() >= deadline:
                raise AssertionError("Account result fence was not installed")
            time.sleep(0.01)
        assert revoke_thread.is_alive()
        assert binding.worker is not None and not binding.worker.cancelled()
        assert client.get("/api/auth/session").status_code == 200

        release_publish.set()
        stop_thread.join(timeout=5)
        revoke_thread.join(timeout=5)
        assert not stop_thread.is_alive() and not revoke_thread.is_alive()
        assert outcomes["stop"].status_code == 200
        assert outcomes["revoke"] == {"account_id": "sub-a", "revoked": True}
        assert publish_count == 1

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT status FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == ("completed",)
        audio = connection.execute(
            "SELECT state, byte_count FROM meeting_audio WHERE meeting_id = ?",
            (meeting_id,),
        ).fetchone()
        assert audio is not None and audio[0] == "available"
        byte_count = audio[1]
    finally:
        connection.close()
    retained = tmp_path / "meetings" / "sub-a" / meeting_id / "audio.mp3"
    assert retained.is_file() and retained.stat().st_size == byte_count
    assert sorted(
        path.name for path in retained.parent.iterdir() if path.suffix == ".mp3"
    ) == ["audio.mp3"]


def test_control_shutdown_joins_service_owned_revoke_and_terminal_audio(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i18-shutdown-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    app = make_app(database, control_socket=socket)
    client = TestClient(app, base_url="https://moss.test")
    client.__enter__()
    session(client, sessions["a"])
    meeting_id = client.post("/api/live/sessions").json()["id"]
    feed_two_lane_span(client, meeting_id)
    binding = app.state.phase2_live._bindings[meeting_id]
    stages = app.state.phase2_live.audio_stages
    stage_path = stages.path("sub-a", meeting_id)
    archive = app.state.phase2_audio_archive
    original_publish = archive.publish_live_prefix
    publish_started = threading.Event()
    release_publish = threading.Event()
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
        except BaseException as exc:  # pragma: no cover - asserted below.
            outcomes["stop_error"] = exc

    def revoke() -> None:
        try:
            outcomes["revoke"] = asyncio.run(
                execute_admin(socket, "revoke", "sub-a")
            )
        except BaseException as exc:
            outcomes["revoke_error"] = exc

    stop_thread = threading.Thread(target=stop_meeting)
    stop_thread.start()
    assert publish_started.wait(timeout=2)
    revoke_thread = threading.Thread(target=revoke)
    revoke_thread.start()
    deadline = time.monotonic() + 2
    while not binding.publication_fenced:
        if time.monotonic() >= deadline:
            raise AssertionError("Account result fence was not installed")
        time.sleep(0.01)

    shutdown_errors: list[BaseException] = []

    def shutdown() -> None:
        try:
            client.__exit__(None, None, None)
        except BaseException as exc:  # pragma: no cover - asserted empty below.
            shutdown_errors.append(exc)

    shutdown_thread = threading.Thread(target=shutdown)
    shutdown_thread.start()
    time.sleep(0.05)
    assert shutdown_thread.is_alive()
    assert stage_path.is_file()
    assert binding.worker is not None and not binding.worker.cancelled()

    release_publish.set()
    stop_thread.join(timeout=5)
    revoke_thread.join(timeout=5)
    shutdown_thread.join(timeout=5)
    assert not stop_thread.is_alive()
    assert not revoke_thread.is_alive()
    assert not shutdown_thread.is_alive()
    assert shutdown_errors == []
    assert "stop_error" not in outcomes
    assert outcomes["stop"].status_code == 200
    assert isinstance(outcomes.get("revoke_error"), Phase2ControlError)
    assert publish_count == 1
    assert not stage_path.exists()

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT status FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == ("completed",)
        assert connection.execute(
            "SELECT state FROM meeting_audio WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == ("available",)
        assert connection.execute(
            "SELECT enabled, authority_generation FROM accounts WHERE account_id = 'sub-a'"
        ).fetchone() == (0, 1)
    finally:
        connection.close()
    meeting_dir = tmp_path / "meetings" / "sub-a" / meeting_id
    assert sorted(path.name for path in meeting_dir.glob("*.mp3")) == ["audio.mp3"]


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
        assert stopped.status_code == 200, stopped.text
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
        assert stopped.status_code == 200, stopped.text
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
        assert stopped.status_code == 200, stopped.text
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
        assert stopped.status_code == 200, stopped.text
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
            admitted = await seed_workspace(store, "sub-a")
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


def test_interrupted_live_meeting_reconciles_missing_metadata_artifact(
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
            archive = MeetingAudioArchive(audio_root)
            stages = LiveMeetingAudioStages(archive, max_bytes=32_000)
            await store.recover_active_meetings(
                audio_archive=archive,
                live_audio_stages=stages,
            )
            admitted = await seed_workspace(store, "sub-a")
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
            admitted = await seed_workspace(store, "sub-a")
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


def test_revoke_recovers_unregistered_live_row_after_transient_create_cleanup_refusal(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i18-transient-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    app = make_app(database, control_socket=socket)

    with TestClient(
        app,
        base_url="https://moss.test",
        raise_server_exceptions=False,
    ) as client:
        session(client, sessions["a"])
        stages = app.state.phase2_live.audio_stages
        original_discard = stages.discard
        attempts = 0

        def fail_once(account_id: str, meeting_id: str) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("injected transient stage cleanup failure")
            original_discard(account_id, meeting_id)

        def refuse_create(*, echo_mode: str | None, session_id: str) -> None:
            del echo_mode, session_id
            raise ValueError("injected runtime creation refusal")

        stages.discard = fail_once
        app.state.phase2_live.runtime.create = refuse_create
        assert client.post("/api/live/sessions").status_code == 400
        connection = sqlite3.connect(database)
        try:
            meeting_id, status = connection.execute(
                "SELECT meeting_id, status FROM meetings WHERE account_id = 'sub-a'"
            ).fetchone()
        finally:
            connection.close()
        assert status == "active"
        assert stages.path("sub-a", meeting_id).is_file()

        assert asyncio.run(execute_admin(socket, "revoke", "sub-a")) == {
            "account_id": "sub-a",
            "revoked": True,
        }
        assert attempts == 2
        assert not stages.path("sub-a", meeting_id).exists()

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT status FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == ("interrupted",)
        assert connection.execute(
            "SELECT state FROM meeting_audio WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == ("unavailable",)
        assert connection.execute(
            "SELECT enabled, authority_generation FROM accounts WHERE account_id = 'sub-a'"
        ).fetchone() == (0, 1)
    finally:
        connection.close()


def test_persistent_unregistered_live_cleanup_blocks_revoke_until_restart_retry(
    tmp_path: Path,
):
    database = tmp_path / "moss.sqlite3"
    socket = Path("/tmp") / f"moss-i18-persistent-{os.getpid()}-{time.time_ns()}.sock"
    sessions = asyncio.run(provision(database))
    app = make_app(database, control_socket=socket)

    with TestClient(
        app,
        base_url="https://moss.test",
        raise_server_exceptions=False,
    ) as client:
        session(client, sessions["a"])
        stages = app.state.phase2_live.audio_stages

        def always_fail(account_id: str, meeting_id: str) -> None:
            del account_id, meeting_id
            raise OSError("injected persistent stage cleanup failure")

        def refuse_create(*, echo_mode: str | None, session_id: str) -> None:
            del echo_mode, session_id
            raise ValueError("injected runtime creation refusal")

        stages.discard = always_fail
        app.state.phase2_live.runtime.create = refuse_create
        assert client.post("/api/live/sessions").status_code == 400
        connection = sqlite3.connect(database)
        try:
            meeting_id = connection.execute(
                "SELECT meeting_id FROM meetings WHERE account_id = 'sub-a'"
            ).fetchone()[0]
        finally:
            connection.close()
        with pytest.raises(Phase2ControlError, match="account_settlement_failed"):
            asyncio.run(execute_admin(socket, "revoke", "sub-a"))
        connection = sqlite3.connect(database)
        try:
            assert connection.execute(
                "SELECT status FROM meetings WHERE meeting_id = ?", (meeting_id,)
            ).fetchone() == ("active",)
            assert connection.execute(
                "SELECT enabled, authority_generation FROM accounts WHERE account_id = 'sub-a'"
            ).fetchone() == (1, 0)
            assert connection.execute(
                "SELECT COUNT(*) FROM sign_in_sessions WHERE account_id = 'sub-a'"
            ).fetchone() == (1,)
        finally:
            connection.close()

    restarted = make_app(database, control_socket=socket)
    with TestClient(restarted, base_url="https://moss.test"):
        assert asyncio.run(execute_admin(socket, "revoke", "sub-a")) == {
            "account_id": "sub-a",
            "revoked": True,
        }

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT status FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ).fetchone() == ("interrupted",)
        assert connection.execute(
            "SELECT enabled, authority_generation FROM accounts WHERE account_id = 'sub-a'"
        ).fetchone() == (0, 1)
        assert connection.execute(
            "SELECT COUNT(*) FROM sign_in_sessions WHERE account_id = 'sub-a'"
        ).fetchone() == (0,)
    finally:
        connection.close()


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
                await force_historical_authority_loss(store, "sub-a")
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
                await force_historical_authority_loss(store, "sub-a")
            return await original_commit(*args, **kwargs)

        store._commit_meeting_audio = revoke_before_metadata
        stopped = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        assert stopped.status_code == 200, stopped.text
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
            await force_historical_authority_loss(store, "sub-a")
            return await original_finish(document, status)

        binding.handle.finish_with_transcript = revoke_before_terminal_tuple
        stopped = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        assert stopped.status_code == 200, stopped.text
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
        client.portal.call(
            force_historical_authority_loss,
            app.state.phase2_store,
            "sub-a",
        )
        client.portal.call(
            app.state.phase2_live._fence,
            binding,
            "meeting_authority_revoked",
        )
        stage_path = tmp_path / "meetings" / "sub-a" / meeting_id / ".live-mix.pcm"
        assert stage_path.is_file()
        assert binding.terminal_persisted is False

    restarted = make_app(database)
    with TestClient(restarted, base_url="https://moss.test") as client:
        assert not stage_path.exists()
        session(client, sessions["a"])
        assert client.get(f"/api/meetings/{meeting_id}").status_code == 401
        # The revoked workspace remains inaccessible; recovery is verified at storage.
        with sqlite3.connect(database) as connection:
            assert connection.execute(
                "SELECT status FROM meetings WHERE meeting_id=?", (meeting_id,)
            ).fetchone() == ("interrupted",)
            assert connection.execute(
                "SELECT COUNT(*) FROM meeting_audio WHERE meeting_id=?", (meeting_id,)
            ).fetchone() == (0,)


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
            admitted = await seed_workspace(store, "sub-a")
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


@pytest.mark.parametrize('retry', [False, True])
def test_http_stop_timeout_is_pending_and_finishes_durably(tmp_path, retry):
    database = tmp_path / 'moss.sqlite3'
    sessions = asyncio.run(provision(database))
    entered, release = threading.Event(), threading.Event()
    app = make_app(database, decoder_factory=lambda: HeldDecoder(entered, release))
    with TestClient(app, base_url='https://moss.test') as client:
        session(client, sessions['a'])
        meeting_id = client.post('/api/live/sessions').json()['id']
        feed_two_lane_span(client, meeting_id)
        assert entered.wait(1)
        try:
            pending = client.post(f'/api/live/sessions/{meeting_id}/stop', json={})
            assert pending.status_code == 202
            assert pending.json()['code'] == 'stop_in_progress'
            assert pending.json()['retryable'] is True
            assert app.state.phase2_live.runtime.snapshot(meeting_id).terminal_failure is None
            if retry:
                timer = threading.Timer(0.05, release.set)
                timer.start()
                try:
                    completed = client.post(f'/api/live/sessions/{meeting_id}/stop', json={'deadline': 2})
                    assert completed.status_code == 200, completed.text
                finally:
                    timer.cancel()
            else:
                release.set()
            final = wait_snapshot(client, meeting_id, lambda body: body['snapshot']['session']['status'] == 'closed')
            assert final['snapshot']['terminal_failure'] is None
            assert client.get(f'/api/meetings/{meeting_id}').json()['status'] == 'completed'
        finally:
            release.set()


def test_http_stop_bounds_wait_for_terminal_finalizer(tmp_path):
    database = tmp_path / 'moss.sqlite3'
    sessions = asyncio.run(provision(database))
    scheduler = _ManualTerminalScheduler()
    app = make_app(database, terminal_text='[0][S01]final words[0.000375]', terminal_scheduler=scheduler)
    with TestClient(app, base_url='https://moss.test') as client:
        session(client, sessions['a'])
        meeting_id = client.post('/api/live/sessions').json()['id']
        feed_two_lane_span(client, meeting_id)
        pending = client.post(f'/api/live/sessions/{meeting_id}/stop', json={'deadline': 0.05})
        assert pending.status_code == 202, pending.text
        assert pending.json()['code'] == 'stop_in_progress'
        assert scheduler.pending == 1
        assert scheduler.run_one()
        final = wait_snapshot(client, meeting_id, lambda body: body['snapshot']['session']['finalization_status'] == 'final')
        assert final['snapshot']['terminal_failure'] is None
