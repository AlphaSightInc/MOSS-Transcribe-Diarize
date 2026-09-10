from __future__ import annotations

import asyncio
import copy
import struct
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from moss_transcribe_diarize.app.phase2 import Phase2Store
from tests.phase2._browser_workspace_fixtures import seed_workspace
from moss_transcribe_diarize.app.phase2_speaker_identity import (
    AccountSpeakerIdentity,
    SpeakerIdentityNotFound,
)


def evidence(
    speaker_id: str,
    *,
    seconds: float,
    centroid: tuple[float, ...] = (0.6, 0.8),
    provisional: bool = False,
):
    return SimpleNamespace(
        speaker_label=speaker_id,
        centroid=centroid,
        sample_seconds=seconds,
        exemplar_count=2,
        provisional=provisional,
        embedder_id="wespeaker:test-revision",
        embedder_state_sha="ab" * 32,
    )


@dataclass
class _FakeSpeakerMutation:
    document: dict[str, object]
    evidence: object | None
    transcript_version: int | None = None

    def mark_committed(self, transcript_version: int) -> None:
        self.transcript_version = transcript_version


@dataclass
class _FakeActiveMeeting:
    owner_key: tuple[str, int]
    document: dict[str, object]
    speaker_labels: dict[str, str]
    observations: dict[str, object] = field(default_factory=dict)
    active: bool = True
    transcript_version: int = 1


class FakeActiveMeetings:
    def __init__(self) -> None:
        self.meetings: dict[str, _FakeActiveMeeting] = {}
        self.evidence_reads = 0

    @asynccontextmanager
    async def voiceprint_labels(self, owner_key, changes):
        # These enrollment-unit fixtures never link a profile across meetings.
        # Real multi-meeting propagation is exercised through HTTP/runtime tests.
        assert not changes
        yield []

    def add(
        self,
        handle,
        document: dict[str, object],
        speaker_labels: dict[str, str],
    ) -> _FakeActiveMeeting:
        meeting = _FakeActiveMeeting(
            owner_key=handle.owner_key,
            document=copy.deepcopy(document),
            speaker_labels=dict(speaker_labels),
        )
        self.meetings[handle.meeting_id] = meeting
        return meeting

    @asynccontextmanager
    async def manual_speaker(self, handle, speaker_id: str, label: str):
        meeting = self.meetings.get(handle.meeting_id)
        if (
            meeting is None
            or meeting.owner_key != handle.owner_key
            or not meeting.active
            or speaker_id not in meeting.speaker_labels
        ):
            raise SpeakerIdentityNotFound(speaker_id)
        prior_label = meeting.speaker_labels[speaker_id]
        document = copy.deepcopy(meeting.document)
        for segment in document["segments"]:
            if segment["speaker"] == prior_label:
                segment["speaker"] = label
        self.evidence_reads += 1
        mutation = _FakeSpeakerMutation(
            document=document,
            evidence=meeting.observations.get(speaker_id),
        )
        yield mutation
        assert mutation.transcript_version is not None
        meeting.document = document
        meeting.speaker_labels[speaker_id] = label
        meeting.transcript_version = mutation.transcript_version


async def provision(database: Path):
    store = await Phase2Store.open(database)
    admitted_a = await seed_workspace(store, "sub-a")
    admitted_b = await seed_workspace(store, "sub-b")
    assert admitted_a is not None and admitted_b is not None
    account_a, _ = admitted_a
    account_b, _ = admitted_b
    return store, store.workspace(account_a), store.workspace(account_b)


async def active_meeting(workspace, active: FakeActiveMeetings, *, two_speakers: bool = False):
    handle = await workspace.create_meeting("live")
    segments: list[dict[str, object]] = [
        {"id": "seg_0001", "start": 0.0, "end": 1.0, "speaker": "S01", "text": "alpha"}
    ]
    labels = {"speaker-0001": "S01"}
    if two_speakers:
        segments.append(
            {"id": "seg_0002", "start": 1.0, "end": 2.0, "speaker": "S02", "text": "beta"}
        )
        labels["speaker-0002"] = "S02"
    document = {"segments": segments}
    assert await handle.commit_transcript(document) == 1
    return handle, active.add(handle, document, labels)


def test_exact_floor_names_immediately_and_stores_one_centroid_sample(tmp_path: Path):
    async def exercise() -> None:
        database = tmp_path / "moss.sqlite3"
        store, workspace_a, _ = await provision(database)
        active = FakeActiveMeetings()
        identity = AccountSpeakerIdentity(store, active)
        try:
            handle, meeting = await active_meeting(workspace_a, active)
            meeting.observations["speaker-0001"] = evidence(
                "speaker-0001",
                seconds=2.0,
            )

            result = await identity.bank(workspace_a).name_speaker(
                handle,
                "speaker-0001",
                "  Alex  ",
            )

            assert result.enrollment == "enrolled"
            assert result.label == "Alex"
            assert result.voiceprint_id is not None
            assert result.transcript_version == 2
            assert active.evidence_reads == 1
            assert meeting.document["segments"][0]["speaker"] == "Alex"
            assert (await handle.snapshot()).transcript == meeting.document

            voiceprints = await identity.bank(workspace_a).list_voiceprints()
            assert [(item.voiceprint_id, item.label, item.sample_count) for item in voiceprints] == [
                (result.voiceprint_id, "Alex", 1)
            ]
            assert voiceprints[0].embedder_id == "wespeaker:test-revision"
            assert voiceprints[0].embedding_dimension == 2

            cursor = await store._connection.execute(
                "SELECT vector, source_meeting_id FROM voiceprint_samples"
            )
            row = await cursor.fetchone()
            await cursor.close()
            assert struct.unpack("<2f", row["vector"]) == pytest.approx((0.6, 0.8))
            assert row["source_meeting_id"] == handle.meeting_id

            meeting.observations["speaker-0001"] = evidence(
                "speaker-0001",
                seconds=3.0,
                centroid=(0.0, 1.0),
            )
            renamed = await identity.bank(workspace_a).name_speaker(
                handle,
                "speaker-0001",
                "Alexandra",
            )
            assert renamed.voiceprint_id == result.voiceprint_id
            assert renamed.enrollment == "enrolled"
            assert (await identity.bank(workspace_a).list_voiceprints())[0].sample_count == 1
            cursor = await store._connection.execute("SELECT vector FROM voiceprint_samples")
            replaced = await cursor.fetchone()
            await cursor.close()
            assert struct.unpack("<2f", replaced["vector"]) == pytest.approx((0.0, 1.0))
        finally:
            await store.close()

    asyncio.run(exercise())


def test_below_floor_pending_is_replaceable_and_first_eligible_centroid_completes_once(
    tmp_path: Path,
):
    async def exercise() -> None:
        store, workspace_a, _ = await provision(tmp_path / "moss.sqlite3")
        active = FakeActiveMeetings()
        identity = AccountSpeakerIdentity(store, active)
        try:
            handle, meeting = await active_meeting(workspace_a, active)
            meeting.observations["speaker-0001"] = evidence("speaker-0001", seconds=1.99)
            first = await identity.bank(workspace_a).name_speaker(
                handle,
                "speaker-0001",
                "First label",
            )
            assert first.enrollment == "pending"
            assert first.voiceprint_id is None
            assert identity.pending_count == 1
            assert await identity.bank(workspace_a).list_voiceprints() == []

            replacement = await identity.bank(workspace_a).name_speaker(
                handle,
                "speaker-0001",
                "Latest label",
            )
            assert replacement.enrollment == "pending"
            assert identity.pending_count == 1
            assert meeting.document["segments"][0]["speaker"] == "Latest label"

            eligible = evidence(
                "speaker-0001",
                seconds=2.0,
                centroid=(1.0, 0.0),
            )
            assert await identity.observe(handle, (eligible,)) == 1
            assert await identity.observe(handle, (eligible,)) == 0
            assert identity.pending_count == 0
            voiceprints = await identity.bank(workspace_a).list_voiceprints()
            assert [(item.label, item.sample_count) for item in voiceprints] == [
                ("Latest label", 1)
            ]
        finally:
            await store.close()

    asyncio.run(exercise())


def test_duplicate_labels_create_distinct_voiceprints_and_never_select_identity(tmp_path: Path):
    async def exercise() -> None:
        store, workspace_a, _ = await provision(tmp_path / "moss.sqlite3")
        active = FakeActiveMeetings()
        identity = AccountSpeakerIdentity(store, active)
        try:
            handle, meeting = await active_meeting(workspace_a, active, two_speakers=True)
            for speaker_id, vector in (
                ("speaker-0001", (1.0, 0.0)),
                ("speaker-0002", (0.0, 1.0)),
            ):
                meeting.observations[speaker_id] = evidence(
                    speaker_id,
                    seconds=2.5,
                    centroid=vector,
                )
            first = await identity.bank(workspace_a).name_speaker(
                handle, "speaker-0001", "anonymous"
            )
            second = await identity.bank(workspace_a).name_speaker(
                handle, "speaker-0002", "anonymous"
            )

            assert first.voiceprint_id != second.voiceprint_id
            assert [item.label for item in await identity.bank(workspace_a).list_voiceprints()] == [
                "anonymous",
                "anonymous",
            ]
        finally:
            await store.close()

    asyncio.run(exercise())


def test_clear_or_process_restart_drops_pending_but_preserves_named_transcript(tmp_path: Path):
    async def exercise() -> None:
        database = tmp_path / "moss.sqlite3"
        store, workspace_a, _ = await provision(database)
        active = FakeActiveMeetings()
        identity = AccountSpeakerIdentity(store, active)
        handle, meeting = await active_meeting(workspace_a, active)
        meeting.observations["speaker-0001"] = evidence("speaker-0001", seconds=1.0)
        await identity.bank(workspace_a).name_speaker(handle, "speaker-0001", "Durable name")
        assert identity.pending_count == 1
        await identity.clear_meeting(handle)
        assert identity.pending_count == 0
        assert await identity.observe(handle, (evidence("speaker-0001", seconds=3.0),)) == 0
        assert await identity.bank(workspace_a).list_voiceprints() == []
        assert (await handle.snapshot()).transcript["segments"][0]["speaker"] == "Durable name"
        await store.close()

        restarted = await Phase2Store.open(database)
        try:
            admitted = await seed_workspace(restarted, "sub-a")
            assert admitted is not None
            account, _ = admitted
            restarted_identity = AccountSpeakerIdentity(restarted, FakeActiveMeetings())
            assert await restarted_identity.bank(restarted.workspace(account)).list_voiceprints() == []
            reopened = await restarted.workspace(account).open_meeting(handle.meeting_id)
            assert reopened is not None
            assert (await reopened.snapshot()).transcript["segments"][0]["speaker"] == "Durable name"
        finally:
            await restarted.close()

    asyncio.run(exercise())


def test_foreign_workspace_returns_not_found_and_mutates_nothing(tmp_path: Path):
    async def exercise() -> None:
        store, workspace_a, workspace_b = await provision(tmp_path / "moss.sqlite3")
        active = FakeActiveMeetings()
        identity = AccountSpeakerIdentity(store, active)
        try:
            handle, meeting = await active_meeting(workspace_a, active)
            meeting.observations["speaker-0001"] = evidence("speaker-0001", seconds=2.0)

            with pytest.raises(SpeakerIdentityNotFound):
                await identity.bank(workspace_b).name_speaker(
                    handle,
                    "speaker-0001",
                    "foreign mutation",
                )

            assert await identity.bank(workspace_b).list_voiceprints() == []
            assert await identity.bank(workspace_a).list_voiceprints() == []
            assert (await handle.snapshot()).transcript["segments"][0]["speaker"] == "S01"
            for table in ("meeting_speakers", "voiceprints", "voiceprint_samples"):
                cursor = await store._connection.execute(f"SELECT COUNT(*) FROM {table}")
                row = await cursor.fetchone()
                await cursor.close()
                assert row[0] == 0
        finally:
            await store.close()

    asyncio.run(exercise())


def test_completed_voiceprint_and_sample_survive_store_restart(tmp_path: Path):
    async def exercise() -> None:
        database = tmp_path / "moss.sqlite3"
        store, workspace_a, _ = await provision(database)
        active = FakeActiveMeetings()
        identity = AccountSpeakerIdentity(store, active)
        handle, meeting = await active_meeting(workspace_a, active)
        meeting.observations["speaker-0001"] = evidence("speaker-0001", seconds=2.0)
        created = await identity.bank(workspace_a).name_speaker(
            handle,
            "speaker-0001",
            "Persistent voice",
        )
        await store.close()

        restarted = await Phase2Store.open(database)
        try:
            admitted = await seed_workspace(restarted, "sub-a")
            assert admitted is not None
            account, _ = admitted
            restarted_identity = AccountSpeakerIdentity(restarted, FakeActiveMeetings())
            voiceprints = await restarted_identity.bank(
                restarted.workspace(account)
            ).list_voiceprints()
            assert [item.to_dict() for item in voiceprints] == [
                {
                    "id": created.voiceprint_id,
                    "label": "Persistent voice",
                    "embedder_id": "wespeaker:test-revision",
                    "embedding_dimension": 2,
                    "revision": 1,
                    "sample_count": 1,
                }
            ]
        finally:
            await restarted.close()

    asyncio.run(exercise())
