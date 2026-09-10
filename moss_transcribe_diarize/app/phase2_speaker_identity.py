"""Account-private manual Speaker naming and Voiceprint enrollment."""

from __future__ import annotations

import asyncio
import json
import math
import secrets
import struct
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .phase2 import AccountRevoked, _now_ms


# ADR-0009 fixes this floor from the measured production album. It is not inferred here.
VOICEPRINT_ENROLLMENT_SECONDS = 2.0


class SpeakerIdentityNotFound(KeyError):
    """The owner-bound active Meeting Speaker does not exist in this Account scope."""


@dataclass(frozen=True, slots=True)
class Voiceprint:
    voiceprint_id: str
    label: str
    embedder_id: str
    embedding_dimension: int
    revision: int
    sample_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.voiceprint_id,
            "label": self.label,
            "embedder_id": self.embedder_id,
            "embedding_dimension": self.embedding_dimension,
            "revision": self.revision,
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True, slots=True)
class ManualNameResult:
    meeting_id: str
    speaker_id: str
    label: str
    voiceprint_id: str | None
    enrollment: str
    transcript_version: int

    def to_dict(self) -> dict[str, object]:
        return {
            "meeting_id": self.meeting_id,
            "speaker_id": self.speaker_id,
            "label": self.label,
            "voiceprint_id": self.voiceprint_id,
            "enrollment": self.enrollment,
            "transcript_version": self.transcript_version,
        }


@dataclass(frozen=True, slots=True)
class _EligibleEvidence:
    vector: tuple[float, ...]
    embedder_id: str


@dataclass(frozen=True, slots=True)
class _PendingEnrollment:
    owner_key: tuple[str, int]
    meeting_id: str
    speaker_id: str
    label: str


class AccountSpeakerIdentity:
    """One deep module for owner-bound naming, private listing, and pending enrollment."""

    def __init__(self, store: Any, active_meetings: Any):
        self._store = store
        self._active_meetings = active_meetings
        self._pending: dict[tuple[str, int, str, str], _PendingEnrollment] = {}
        self._lock = asyncio.Lock()

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def bank(self, workspace: Any) -> "AccountVoiceprintBank":
        return AccountVoiceprintBank(self, workspace.owner_key)

    async def observe(self, handle: Any, observations: Sequence[object]) -> int:
        """Complete pending samples from current in-memory album observations exactly once."""

        async with self._lock:
            return await self._observe_locked(handle, observations)

    async def _observe_locked(self, handle: Any, observations: Sequence[object]) -> int:
        owner_key = handle.owner_key
        meeting_id = handle.meeting_id
        pending = tuple(
            intent
            for intent in self._pending.values()
            if intent.owner_key == owner_key and intent.meeting_id == meeting_id
        )
        if not pending:
            return 0
        by_speaker = {
            str(observation.speaker_label): observation
            for observation in observations
            if isinstance(getattr(observation, "speaker_label", None), str)
        }
        completed = 0
        for intent in pending:
            evidence = _eligible_evidence(by_speaker.get(intent.speaker_id))
            if evidence is None:
                continue
            key = _pending_key(intent.owner_key, intent.meeting_id, intent.speaker_id)
            current = self._pending.get(key)
            if current != intent:
                continue
            if await self._complete_pending(intent, evidence):
                completed += 1
            self._pending.pop(key, None)
        return completed

    async def clear_meeting(self, handle: Any) -> int:
        """Forget unfulfilled intent; transcript and any completed Voiceprint stay durable."""

        async with self._lock:
            keys = tuple(
                key
                for key, intent in self._pending.items()
                if intent.owner_key == handle.owner_key
                and intent.meeting_id == handle.meeting_id
            )
            for key in keys:
                self._pending.pop(key, None)
            return len(keys)

    async def _name_speaker(
        self,
        owner_key: tuple[str, int],
        handle: Any,
        speaker_id: str,
        label: str,
    ) -> ManualNameResult:
        async with self._lock:
            return await self._name_speaker_locked(
                owner_key,
                handle,
                speaker_id,
                label,
            )

    async def _name_speaker_locked(
        self,
        owner_key: tuple[str, int],
        handle: Any,
        speaker_id: str,
        label: str,
    ) -> ManualNameResult:
        if handle.owner_key != owner_key:
            raise SpeakerIdentityNotFound(speaker_id)
        normalized = label.strip()
        if not normalized:
            raise ValueError("Speaker label must not be empty.")
        if not speaker_id:
            raise SpeakerIdentityNotFound(speaker_id)

        try:
            async with self._active_meetings.manual_speaker(
                handle,
                speaker_id,
                normalized,
            ) as active:
                evidence = _eligible_evidence(active.evidence)
                voiceprint_id, transcript_version = await self._persist_manual_name(
                    owner_key,
                    handle.meeting_id,
                    speaker_id,
                    normalized,
                    active.document,
                    evidence,
                )
                active.mark_committed(transcript_version)
        except SpeakerIdentityNotFound:
            raise
        except KeyError as exc:
            raise SpeakerIdentityNotFound(speaker_id) from exc

        key = _pending_key(owner_key, handle.meeting_id, speaker_id)
        if evidence is None:
            self._pending[key] = _PendingEnrollment(
                owner_key=owner_key,
                meeting_id=handle.meeting_id,
                speaker_id=speaker_id,
                label=normalized,
            )
            enrollment = "pending"
        else:
            self._pending.pop(key, None)
            enrollment = "enrolled"
        return ManualNameResult(
            meeting_id=handle.meeting_id,
            speaker_id=speaker_id,
            label=normalized,
            voiceprint_id=voiceprint_id,
            enrollment=enrollment,
            transcript_version=transcript_version,
        )

    async def _persist_manual_name(
        self,
        owner_key: tuple[str, int],
        meeting_id: str,
        speaker_id: str,
        label: str,
        document: Mapping[str, object],
        evidence: _EligibleEvidence | None,
    ) -> tuple[str | None, int]:
        account_id, authority_generation = owner_key
        document_json = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
        now = _now_ms()
        async with self._store._mutation():
            cursor = await self._store._connection.execute(
                """
                UPDATE meetings SET updated_at_ms = ?
                WHERE account_id = ? AND meeting_id = ? AND status = 'active'
                  AND EXISTS (
                    SELECT 1 FROM accounts
                    WHERE account_id = ? AND enabled = 1 AND authority_generation = ?
                  )
                """,
                (now, account_id, meeting_id, account_id, authority_generation),
            )
            if cursor.rowcount != 1:
                raise AccountRevoked("Meeting authority is revoked or interrupted.")

            speaker_cursor = await self._store._connection.execute(
                """
                SELECT voiceprint_id FROM meeting_speakers
                WHERE account_id = ? AND meeting_id = ? AND speaker_id = ?
                """,
                (account_id, meeting_id, speaker_id),
            )
            speaker_row = await speaker_cursor.fetchone()
            await speaker_cursor.close()
            voiceprint_id = None if speaker_row is None else speaker_row["voiceprint_id"]

            if voiceprint_id is not None:
                await self._rename_linked_voiceprint(
                    account_id,
                    str(voiceprint_id),
                    label,
                    now,
                )
            if evidence is not None:
                if voiceprint_id is None:
                    voiceprint_id = secrets.token_urlsafe(18)
                    await self._store._connection.execute(
                        """
                        INSERT INTO voiceprints(
                            account_id, voiceprint_id, label, embedder_id,
                            embedding_dimension, revision, created_at_ms, updated_at_ms
                        ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                        """,
                        (
                            account_id,
                            voiceprint_id,
                            label,
                            evidence.embedder_id,
                            len(evidence.vector),
                            now,
                            now,
                        ),
                    )
                else:
                    await self._assert_compatible_voiceprint(
                        account_id,
                        str(voiceprint_id),
                        evidence,
                    )
                await self._upsert_sample(
                    account_id,
                    str(voiceprint_id),
                    meeting_id,
                    speaker_id,
                    evidence,
                    now,
                )

            await self._store._connection.execute(
                """
                INSERT INTO meeting_speakers(
                    account_id, meeting_id, speaker_id, label, voiceprint_id
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(account_id, meeting_id, speaker_id) DO UPDATE SET
                    label = excluded.label,
                    voiceprint_id = excluded.voiceprint_id
                """,
                (account_id, meeting_id, speaker_id, label, voiceprint_id),
            )
            await self._store._connection.execute(
                """
                INSERT INTO meeting_transcripts(
                    account_id, meeting_id, document_json, version, updated_at_ms
                ) VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(account_id, meeting_id) DO UPDATE SET
                    document_json = excluded.document_json,
                    version = meeting_transcripts.version + 1,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (account_id, meeting_id, document_json, now),
            )
            version_cursor = await self._store._connection.execute(
                """
                SELECT version FROM meeting_transcripts
                WHERE account_id = ? AND meeting_id = ?
                """,
                (account_id, meeting_id),
            )
            version_row = await version_cursor.fetchone()
            await version_cursor.close()
            return (
                None if voiceprint_id is None else str(voiceprint_id),
                int(version_row["version"]),
            )

    async def _complete_pending(
        self,
        intent: _PendingEnrollment,
        evidence: _EligibleEvidence,
    ) -> bool:
        account_id, authority_generation = intent.owner_key
        now = _now_ms()
        async with self._store._mutation():
            meeting_cursor = await self._store._connection.execute(
                """
                SELECT 1 FROM meetings
                WHERE account_id = ? AND meeting_id = ? AND status = 'active'
                  AND EXISTS (
                    SELECT 1 FROM accounts
                    WHERE account_id = ? AND enabled = 1 AND authority_generation = ?
                  )
                """,
                (
                    account_id,
                    intent.meeting_id,
                    account_id,
                    authority_generation,
                ),
            )
            meeting_row = await meeting_cursor.fetchone()
            await meeting_cursor.close()
            if meeting_row is None:
                return False

            speaker_cursor = await self._store._connection.execute(
                """
                SELECT label, voiceprint_id FROM meeting_speakers
                WHERE account_id = ? AND meeting_id = ? AND speaker_id = ?
                """,
                (account_id, intent.meeting_id, intent.speaker_id),
            )
            speaker_row = await speaker_cursor.fetchone()
            await speaker_cursor.close()
            if speaker_row is None or str(speaker_row["label"]) != intent.label:
                return False

            voiceprint_id = speaker_row["voiceprint_id"]
            if voiceprint_id is None:
                voiceprint_id = secrets.token_urlsafe(18)
                await self._store._connection.execute(
                    """
                    INSERT INTO voiceprints(
                        account_id, voiceprint_id, label, embedder_id,
                        embedding_dimension, revision, created_at_ms, updated_at_ms
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        account_id,
                        voiceprint_id,
                        intent.label,
                        evidence.embedder_id,
                        len(evidence.vector),
                        now,
                        now,
                    ),
                )
                await self._store._connection.execute(
                    """
                    UPDATE meeting_speakers SET voiceprint_id = ?
                    WHERE account_id = ? AND meeting_id = ? AND speaker_id = ?
                    """,
                    (
                        voiceprint_id,
                        account_id,
                        intent.meeting_id,
                        intent.speaker_id,
                    ),
                )
            else:
                await self._assert_compatible_voiceprint(
                    account_id,
                    str(voiceprint_id),
                    evidence,
                )
            await self._upsert_sample(
                account_id,
                str(voiceprint_id),
                intent.meeting_id,
                intent.speaker_id,
                evidence,
                now,
            )
            return True

    async def _rename_linked_voiceprint(
        self,
        account_id: str,
        voiceprint_id: str,
        label: str,
        now: int,
    ) -> None:
        cursor = await self._store._connection.execute(
            """
            UPDATE voiceprints
            SET label = ?, revision = revision + 1, updated_at_ms = ?
            WHERE account_id = ? AND voiceprint_id = ?
            """,
            (label, now, account_id, voiceprint_id),
        )
        if cursor.rowcount != 1:
            raise SpeakerIdentityNotFound(voiceprint_id)

    async def _assert_compatible_voiceprint(
        self,
        account_id: str,
        voiceprint_id: str,
        evidence: _EligibleEvidence,
    ) -> None:
        cursor = await self._store._connection.execute(
            """
            SELECT embedder_id, embedding_dimension FROM voiceprints
            WHERE account_id = ? AND voiceprint_id = ?
            """,
            (account_id, voiceprint_id),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            raise SpeakerIdentityNotFound(voiceprint_id)
        if (
            str(row["embedder_id"]) != evidence.embedder_id
            or int(row["embedding_dimension"]) != len(evidence.vector)
        ):
            raise ValueError("Voiceprint requires re-enrollment for this embedder.")

    async def _upsert_sample(
        self,
        account_id: str,
        voiceprint_id: str,
        meeting_id: str,
        speaker_id: str,
        evidence: _EligibleEvidence,
        now: int,
    ) -> None:
        sample_id = f"{meeting_id}:{speaker_id}"
        vector = struct.pack(f"<{len(evidence.vector)}f", *evidence.vector)
        await self._store._connection.execute(
            """
            INSERT INTO voiceprint_samples(
                account_id, voiceprint_id, sample_id, vector,
                source_meeting_id, created_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, voiceprint_id, sample_id) DO UPDATE SET
                vector = excluded.vector,
                source_meeting_id = excluded.source_meeting_id,
                created_at_ms = excluded.created_at_ms
            """,
            (account_id, voiceprint_id, sample_id, vector, meeting_id, now),
        )

    async def _list_voiceprints(
        self,
        owner_key: tuple[str, int],
    ) -> list[Voiceprint]:
        account_id, authority_generation = owner_key
        async with self._store._external_read():
            cursor = await self._store._connection.execute(
                """
                SELECT v.voiceprint_id, v.label, v.embedder_id,
                       v.embedding_dimension, v.revision,
                       COUNT(s.sample_id) AS sample_count
                FROM voiceprints v
                JOIN accounts a ON a.account_id = v.account_id
                    AND a.enabled = 1 AND a.authority_generation = ?
                LEFT JOIN voiceprint_samples s
                    ON s.account_id = v.account_id
                    AND s.voiceprint_id = v.voiceprint_id
                WHERE v.account_id = ?
                GROUP BY v.account_id, v.voiceprint_id
                ORDER BY v.created_at_ms, v.voiceprint_id
                """,
                (authority_generation, account_id),
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return [
            Voiceprint(
                voiceprint_id=str(row["voiceprint_id"]),
                label=str(row["label"]),
                embedder_id=str(row["embedder_id"]),
                embedding_dimension=int(row["embedding_dimension"]),
                revision=int(row["revision"]),
                sample_count=int(row["sample_count"]),
            )
            for row in rows
        ]


class AccountVoiceprintBank:
    """An Account-authorized view of the identity module; no Account ID crosses callers."""

    def __init__(
        self,
        identity: AccountSpeakerIdentity,
        owner_key: tuple[str, int],
    ) -> None:
        self._identity = identity
        self._owner_key = owner_key

    async def name_speaker(
        self,
        handle: Any,
        speaker_id: str,
        label: str,
    ) -> ManualNameResult:
        return await self._identity._name_speaker(
            self._owner_key,
            handle,
            speaker_id,
            label,
        )

    async def list_voiceprints(self) -> list[Voiceprint]:
        return await self._identity._list_voiceprints(self._owner_key)


def _eligible_evidence(observation: object | None) -> _EligibleEvidence | None:
    if observation is None or bool(getattr(observation, "provisional", True)):
        return None
    try:
        seconds = float(getattr(observation, "sample_seconds"))
        vector = tuple(float(value) for value in getattr(observation, "centroid"))
    except (TypeError, ValueError):
        return None
    embedder_id = getattr(observation, "embedder_id", None)
    if (
        seconds < VOICEPRINT_ENROLLMENT_SECONDS
        or not vector
        or not all(math.isfinite(value) for value in vector)
        or not isinstance(embedder_id, str)
        or not embedder_id
    ):
        return None
    return _EligibleEvidence(vector=vector, embedder_id=embedder_id)


def _pending_key(
    owner_key: tuple[str, int],
    meeting_id: str,
    speaker_id: str,
) -> tuple[str, int, str, str]:
    return owner_key[0], owner_key[1], meeting_id, speaker_id


__all__ = [
    "AccountSpeakerIdentity",
    "AccountVoiceprintBank",
    "ManualNameResult",
    "SpeakerIdentityNotFound",
    "VOICEPRINT_ENROLLMENT_SECONDS",
    "Voiceprint",
]
