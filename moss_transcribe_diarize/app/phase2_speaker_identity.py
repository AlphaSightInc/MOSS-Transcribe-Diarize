"""Account-private manual Speaker naming and Voiceprint enrollment."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import secrets
import struct
from contextlib import asynccontextmanager, nullcontext
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .phase2 import AccountRevoked, _is_unknown_speaker_value, _now_ms
from .phase2_voiceprint_match import VoiceprintProfile, match_voiceprint, normalized_mean


# ADR-0009 fixes this floor from the measured production album. It is not inferred here.
VOICEPRINT_ENROLLMENT_SECONDS = 2.0
_LOG = logging.getLogger("moss_transcribe_diarize.phase2.speaker_identity")


class SpeakerIdentityNotFound(KeyError):
    """The owner-bound Meeting Speaker does not exist in this Account scope."""


@dataclass(frozen=True, slots=True)
class Voiceprint:
    voiceprint_id: str
    label: str
    embedder_id: str
    embedding_dimension: int
    revision: int
    sample_count: int
    compatibility: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.voiceprint_id,
            "label": self.label,
            "embedder_id": self.embedder_id,
            "embedding_dimension": self.embedding_dimension,
            "revision": self.revision,
            "sample_count": self.sample_count,
            **({"compatibility": self.compatibility} if self.compatibility is not None else {}),
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

    def __init__(self, store: Any, active_meetings: Any, *, file_evidence=None,
                 live_evidence=None, audio_archive=None):
        self._store = store
        self._active_meetings = active_meetings
        self._file_evidence = file_evidence
        self._live_evidence = live_evidence
        self._audio_archive = audio_archive
        self._pending: dict[tuple[str, int, str, str], _PendingEnrollment] = {}
        self._lock = asyncio.Lock()
        self._naming_tasks: set[asyncio.Task[ManualNameResult]] = set()
        # Saved-audio fingerprints (issue #15): one at a time, never under the bank lock.
        self._enrollment_lock = asyncio.Lock()
        self._saved_enrollments: dict[tuple[str, int, str, str], asyncio.Task[None]] = {}
        # Prepared matches never survive process exit; startup interrupts Live.
        self._bank_revisions: dict[tuple[str, int], int] = {}
        self._manual_speakers: set[tuple[str, int, str, str]] = set()
        self._auto_links: dict[tuple[str, int, str, str], tuple[str, str] | None] = {}

    async def shutdown(self) -> None:
        """Join accepted naming before Live settlement or SQLite shutdown."""
        if self._naming_tasks:
            await asyncio.gather(*tuple(self._naming_tasks), return_exceptions=True)

    def _naming_done(self, task: asyncio.Task[ManualNameResult]) -> None:
        self._naming_tasks.discard(task)
        if not task.cancelled():
            task.exception()

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
                self._advance_revision(owner_key)
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
        *, save_voiceprint: bool = True,
    ) -> ManualNameResult:
        task = asyncio.create_task(
            self._name_speaker_serial(owner_key, handle, speaker_id, label, save_voiceprint=save_voiceprint),
            name="phase2-manual-speaker-name",
        )
        self._naming_tasks.add(task)
        task.add_done_callback(self._naming_done)
        return await asyncio.shield(task)

    async def _name_speaker_serial(
        self, owner_key, handle, speaker_id, label, *, save_voiceprint=True,
    ) -> ManualNameResult:
        async with self._lock:
            return await self._name_speaker_locked(
                owner_key,
                handle,
                speaker_id,
                label,
                save_voiceprint=save_voiceprint,
            )

    async def _name_speaker_locked(
        self,
        owner_key: tuple[str, int],
        handle: Any,
        speaker_id: str,
        label: str,
        *, save_voiceprint: bool = True,
    ) -> ManualNameResult:
        if handle.owner_key != owner_key:
            raise SpeakerIdentityNotFound(speaker_id)
        normalized = label.strip()
        if not normalized:
            raise ValueError("Speaker label must not be empty.")
        if not speaker_id or _is_unknown_speaker_value(speaker_id):
            raise SpeakerIdentityNotFound(speaker_id)

        live_naming = True
        saved_enrollment = None
        try:
            if self._active_meetings is None:
                raise SpeakerIdentityNotFound(speaker_id)
            async with self._active_meetings.manual_speaker(
                handle,
                speaker_id,
                normalized,
            ) as active:
                evidence = _eligible_evidence(active.evidence) if save_voiceprint else None
                voiceprint_id, transcript_version, was_linked = await self._persist_manual_name(
                    owner_key,
                    handle.meeting_id,
                    speaker_id,
                    normalized,
                    active.document,
                    evidence,
                    save_voiceprint=save_voiceprint,
                )
                active.mark_committed(transcript_version)
        except KeyError as exc:
            # Capture may have finished before this request acquired the binding.
            # Only durable terminal truth can replace the active naming path.
            meeting = await handle.snapshot()
            if meeting.status == "active" or meeting.transcript is None:
                raise SpeakerIdentityNotFound(speaker_id) from exc
            document = json.loads(json.dumps(meeting.transcript))
            segments = document["segments"]
            # Older/file documents use their original speaker token as identity.
            # Freeze it for every row before any display label can be edited.
            for segment in segments:
                if (
                    "speaker_entity_id" not in segment
                    and not _is_unknown_speaker_value(segment.get("speaker"))
                ):
                    segment["speaker_entity_id"] = segment["speaker"]
            addressed = [s for s in segments if s.get("speaker_entity_id") == speaker_id]
            if not addressed:
                raise SpeakerIdentityNotFound(speaker_id) from exc
            for segment in addressed:
                segment["speaker"] = normalized
            evidence = None
            evidence_provider = (self._file_evidence if meeting.mode == 'file' else
                                 self._live_evidence if meeting.mode == 'live'
                                 and meeting.status == 'completed' else None)
            if save_voiceprint and evidence_provider is not None:
                audio = await handle.audio()
                path = None if audio is None else handle.resolve_audio(self._audio_archive, audio)
                if path is not None:
                    intervals = (addressed if meeting.mode == 'file' else
                                 _unoverlapped_speaker_rows(segments, speaker_id))
                    # The floor is necessary for any admitted evidence, so refusing here
                    # answers now what the fingerprint would answer minutes later.
                    if sum(row['end'] - row['start'] for row in intervals
                           ) >= VOICEPRINT_ENROLLMENT_SECONDS:
                        # Fingerprinting costs ~3-4 s of CPU per minute of this speaker's
                        # speech (issue #15), so it runs after the name is durable.
                        saved_enrollment = (evidence_provider, path, intervals, meeting.status)
            live_naming = False
            voiceprint_id, transcript_version, was_linked = await self._persist_manual_name(
                owner_key, handle.meeting_id, speaker_id, normalized, document, evidence,
                save_voiceprint=save_voiceprint, status=meeting.status,
            )

        key = _pending_key(owner_key, handle.meeting_id, speaker_id)
        if not save_voiceprint:
            self._pending.pop(key, None)
            enrollment = "not_requested"
        elif not live_naming and saved_enrollment is None:
            self._pending.pop(key, None)
            enrollment = "enrolled" if voiceprint_id is not None else "unavailable"
        elif evidence is None:
            self._pending[key] = _PendingEnrollment(
                owner_key=owner_key,
                meeting_id=handle.meeting_id,
                speaker_id=speaker_id,
                label=normalized,
            )
            enrollment = "pending"
            if saved_enrollment is not None and key not in self._saved_enrollments:
                # A running fingerprint of this speaker completes the latest intent.
                task = asyncio.create_task(self._enroll_saved(key, *saved_enrollment),
                                           name="phase2-saved-voiceprint")
                self._saved_enrollments[key] = task
                self._naming_tasks.add(task)
                task.add_done_callback(self._naming_done)
        else:
            self._pending.pop(key, None)
            enrollment = "enrolled"
        self._advance_revision(owner_key)
        self._manual_speakers.add(key)
        if was_linked:
            await self._change_voiceprint_locked(owner_key, voiceprint_id, normalized, exclude_meeting=handle.meeting_id)
        return ManualNameResult(
            meeting_id=handle.meeting_id,
            speaker_id=speaker_id,
            label=normalized,
            voiceprint_id=voiceprint_id,
            enrollment=enrollment,
            transcript_version=transcript_version,
        )

    async def _enroll_saved(self, key, provider, path, intervals, status) -> None:
        """Fingerprint a saved meeting's speaker after naming returned; write under the bank lock."""
        evidence = None
        try:
            async with self._enrollment_lock:
                if key in self._pending:
                    evidence = _eligible_evidence(await asyncio.to_thread(provider, path, intervals))
        except Exception:
            _LOG.warning("saved-meeting voiceprint fingerprint failed", exc_info=True)
        async with self._lock:
            self._saved_enrollments.pop(key, None)
            # Renaming again updates this intent; naming without a voiceprint or deleting
            # the linked voiceprint removes it. Only the name current at commit is used.
            intent = self._pending.pop(key, None)
            if intent is None or evidence is None:
                return
            try:
                if await self._complete_pending(intent, evidence, status=status):
                    self._advance_revision(intent.owner_key)
            except Exception:
                _LOG.warning("saved-meeting voiceprint enrollment failed", exc_info=True)

    async def _persist_manual_name(
        self,
        owner_key: tuple[str, int],
        meeting_id: str,
        speaker_id: str,
        label: str,
        document: Mapping[str, object],
        evidence: _EligibleEvidence | None,
        *, save_voiceprint: bool = True, status: str = "active",
    ) -> tuple[str | None, int, bool]:
        account_id, authority_generation = owner_key
        document_json = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
        now = _now_ms()
        async with self._store._mutation():
            cursor = await self._store._connection.execute(
                """
                UPDATE meetings SET updated_at_ms = ?
                WHERE account_id = ? AND meeting_id = ? AND status = ?
                  AND EXISTS (
                    SELECT 1 FROM accounts
                    WHERE account_id = ? AND enabled = 1 AND authority_generation = ?
                  )
                """,
                (now, account_id, meeting_id, status, account_id, authority_generation),
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
            voiceprint_id = None if speaker_row is None or not save_voiceprint else speaker_row["voiceprint_id"]
            was_linked = voiceprint_id is not None

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
                was_linked,
            )

    async def _complete_pending(
        self,
        intent: _PendingEnrollment,
        evidence: _EligibleEvidence,
        *, status: str = "active",
    ) -> bool:
        account_id, authority_generation = intent.owner_key
        now = _now_ms()
        async with self._store._mutation():
            meeting_cursor = await self._store._connection.execute(
                """
                SELECT 1 FROM meetings
                WHERE account_id = ? AND meeting_id = ? AND status = ?
                  AND EXISTS (
                    SELECT 1 FROM accounts
                    WHERE account_id = ? AND enabled = 1 AND authority_generation = ?
                  )
                """,
                (
                    account_id,
                    intent.meeting_id,
                    status,
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

    def _advance_revision(self, owner_key: tuple[str, int]) -> int:
        revision = self._bank_revisions.get(owner_key, 0) + 1
        self._bank_revisions[owner_key] = revision
        return revision

    async def _profiles(self, owner_key):
        async with self._store._external_read():
            cursor = await self._store._connection.execute(
                "SELECT v.voiceprint_id,v.label,v.embedder_id,v.embedding_dimension,s.vector "
                "FROM voiceprints v JOIN accounts a USING(account_id) "
                "JOIN voiceprint_samples s USING(account_id,voiceprint_id) "
                "WHERE v.account_id=? AND a.enabled=1 AND a.authority_generation=? ORDER BY v.voiceprint_id,s.sample_id",
                owner_key,
            )
            rows = await cursor.fetchall()
            await cursor.close()
        grouped = {}
        for row in rows:
            profile_id = str(row["voiceprint_id"])
            group = grouped.setdefault(profile_id, (row, []))
            blob = row["vector"]
            dimension = int(row["embedding_dimension"])
            group[1].append(struct.unpack(f"<{dimension}f", blob) if len(blob) == dimension * 4 else ())
        profiles = []
        for profile_id, (row, samples) in grouped.items():
            vector = normalized_mean(samples)
            if vector is not None:
                profiles.append(VoiceprintProfile(profile_id, str(row["label"]), str(row["embedder_id"]), vector))
        return tuple(profiles)

    async def prepare_matches(self, handle, observations):
        """Freeze a bounded group; a bank change invalidates it before publication."""
        async with self._lock:
            profiles = await self._profiles(handle.owner_key)
            return (handle.owner_key, self._bank_revisions.get(handle.owner_key, 0), tuple(
                (observation.speaker_label, match_voiceprint(observation, profiles)) for observation in observations
            ))

    @asynccontextmanager
    async def publication(self, handle, observations, *, prepared=None):
        """Keep bank revision stable through durable transcript/publication.

        The publisher holds this lock before its binding lock. A delete/rename
        therefore either wins before preparation or waits until this publication
        is durable; an explicitly prepared stale group yields no changes.
        """
        async with self._lock:
            if prepared is None:
                profiles = await self._profiles(handle.owner_key) if observations else ()
                decisions = tuple((o.speaker_label, match_voiceprint(o, profiles)) for o in observations)
            else:
                owner, revision, decisions = prepared
                if owner != handle.owner_key or revision != self._bank_revisions.get(owner, 0):
                    yield {}
                    return
            changes = {}
            pending_links = {}
            for speaker_id, profile in decisions:
                key = _pending_key(handle.owner_key, handle.meeting_id, speaker_id)
                if key in self._manual_speakers:
                    continue
                link = None if profile is None else (profile.voiceprint_id, profile.label)
                if self._auto_links.get(key) == link:
                    continue
                changes[speaker_id] = None if profile is None else profile.label
                pending_links[key] = link
            if pending_links:
                async with self._store._mutation():
                    cursor = await self._store._connection.execute(
                        "SELECT 1 FROM meetings m JOIN accounts a USING(account_id) "
                        "WHERE m.account_id=? AND m.meeting_id=? AND m.status='active' "
                        "AND a.enabled=1 AND a.authority_generation=?",
                        (handle.owner_key[0], handle.meeting_id, handle.owner_key[1]),
                    )
                    allowed = await cursor.fetchone()
                    await cursor.close()
                    if allowed is None:
                        raise AccountRevoked("Meeting authority is revoked or interrupted.")
                    for key, link in pending_links.items():
                        if link is None:
                            await self._store._connection.execute(
                                "DELETE FROM meeting_speakers WHERE account_id=? AND meeting_id=? AND speaker_id=?",
                                (key[0], key[2], key[3]),
                            )
                        else:
                            await self._store._connection.execute(
                                "INSERT INTO meeting_speakers(account_id,meeting_id,speaker_id,label,voiceprint_id) "
                                "VALUES(?,?,?,?,?) ON CONFLICT(account_id,meeting_id,speaker_id) DO UPDATE SET "
                                "label=excluded.label,voiceprint_id=excluded.voiceprint_id",
                                (key[0], key[2], key[3], link[1], link[0]),
                            )
            yield changes
            self._auto_links.update(pending_links)

    async def _change_voiceprint(self, owner_key, voiceprint_id, label):
        task = asyncio.create_task(self._change_voiceprint_serial(owner_key, voiceprint_id, label),
                                   name="phase2-voiceprint-mutation")
        self._naming_tasks.add(task)
        task.add_done_callback(self._naming_done)
        return await asyncio.shield(task)

    async def _change_voiceprint_serial(self, owner_key, voiceprint_id, label):
        async with self._lock:
            return await self._change_voiceprint_locked(owner_key, voiceprint_id, label)

    async def _change_voiceprint_locked(self, owner_key, voiceprint_id, label, *, exclude_meeting=None):
        if label is not None:
            label = label.strip()
            if not label:
                raise ValueError("Voiceprint label must not be empty.")
        account_id, generation = owner_key
        async with self._store._external_read():
            cursor = await self._store._connection.execute(
                "SELECT v.voiceprint_id FROM voiceprints v JOIN accounts a USING(account_id) "
                "WHERE v.account_id=? AND v.voiceprint_id=? AND a.enabled=1 AND a.authority_generation=?",
                (account_id, voiceprint_id, generation),
            )
            found = await cursor.fetchone()
            await cursor.close()
            if found is None:
                raise SpeakerIdentityNotFound(voiceprint_id)
            cursor = await self._store._connection.execute(
                "SELECT meeting_id,speaker_id FROM meeting_speakers WHERE account_id=? AND voiceprint_id=?",
                (account_id, voiceprint_id),
            )
            links = await cursor.fetchall()
            await cursor.close()
        changes = {}
        # Deleting the biometric profile unlinks it, not the user's recorded name.
        # Future recognition cannot use it; stopped and manually recorded text stays.
        if label is not None:
            for link in links:
                if str(link["meeting_id"]) == exclude_meeting:
                    continue
                changes.setdefault(str(link["meeting_id"]), {})[str(link["speaker_id"])] = label
        projection = nullcontext([]) if self._active_meetings is None else self._active_meetings.voiceprint_labels(owner_key, changes)
        async with projection as publications:
            now = _now_ms()
            async with self._store._mutation():
                cursor = await self._store._connection.execute(
                    "SELECT 1 FROM accounts WHERE account_id=? AND enabled=1 AND authority_generation=?",
                    owner_key,
                )
                authorized = await cursor.fetchone()
                await cursor.close()
                if authorized is None:
                    raise AccountRevoked("Workspace authority is revoked.")
                if label is None:
                    await self._store._connection.execute(
                        "UPDATE meeting_speakers SET voiceprint_id=NULL WHERE account_id=? AND voiceprint_id=?",
                        (account_id, voiceprint_id),
                    )
                    await self._store._connection.execute(
                        "DELETE FROM voiceprint_samples WHERE account_id=? AND voiceprint_id=?", (account_id, voiceprint_id)
                    )
                    await self._store._connection.execute(
                        "DELETE FROM voiceprints WHERE account_id=? AND voiceprint_id=?", (account_id, voiceprint_id)
                    )
                else:
                    await self._rename_linked_voiceprint(account_id, voiceprint_id, label, now)
                    for publication in publications:
                        meeting_id = publication.handle.meeting_id
                        await self._store._connection.execute(
                            "UPDATE meeting_speakers SET label=? WHERE account_id=? AND meeting_id=? AND voiceprint_id=?",
                            (label, account_id, meeting_id, voiceprint_id),
                        )
                        cursor = await self._store._connection.execute(
                            "UPDATE meeting_transcripts SET document_json=?,version=version+1,updated_at_ms=? "
                            "WHERE account_id=? AND meeting_id=? RETURNING version",
                            (json.dumps(publication.document, ensure_ascii=False, separators=(",", ":")), now, account_id, meeting_id),
                        )
                        row = await cursor.fetchone()
                        await cursor.close()
                        if row is None:
                            raise SpeakerIdentityNotFound(meeting_id)
                        publication.transcript_version = int(row["version"])
            for link in links:
                key = _pending_key(owner_key, str(link["meeting_id"]), str(link["speaker_id"]))
                pending = self._pending.get(key)
                if pending is not None:
                    if label is None:
                        self._pending.pop(key, None)
                    else:
                        self._pending[key] = _PendingEnrollment(owner_key, pending.meeting_id, pending.speaker_id, label)
            revision = self._advance_revision(owner_key)
        return {"id": voiceprint_id, "label": label, "deleted": label is None, "bank_revision": revision}

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
        runtime = getattr(self._active_meetings, "runtime", None)
        current_embedder = getattr(runtime, "_voiceprint_embedder_identity", None)
        return [
            Voiceprint(
                voiceprint_id=str(row["voiceprint_id"]),
                label=str(row["label"]),
                embedder_id=str(row["embedder_id"]),
                embedding_dimension=int(row["embedding_dimension"]),
                revision=int(row["revision"]),
                sample_count=int(row["sample_count"]),
                compatibility=(None if current_embedder is None else "compatible"
                    if (str(row["embedder_id"]), int(row["embedding_dimension"])) == current_embedder
                    else "re_enrollment_required"),
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
        *, save_voiceprint: bool = True,
    ) -> ManualNameResult:
        return await self._identity._name_speaker(
            self._owner_key,
            handle,
            speaker_id,
            label,
            save_voiceprint=save_voiceprint,
        )

    async def list_voiceprints(self) -> list[Voiceprint]:
        return await self._identity._list_voiceprints(self._owner_key)

    async def rename_voiceprint(self, voiceprint_id: str, label: str):
        return await self._identity._change_voiceprint(self._owner_key, voiceprint_id, label)

    async def delete_voiceprint(self, voiceprint_id: str):
        return await self._identity._change_voiceprint(self._owner_key, voiceprint_id, None)


def _unoverlapped_speaker_rows(segments: Sequence[Mapping[str, object]],
                                speaker_id: str) -> list[dict[str, float]]:
    """Use only saved row time owned by this speaker, across both capture lanes."""
    owned = sorted((float(row['start']), float(row['end'])) for row in segments
                   if row.get('speaker_entity_id') == speaker_id)
    competing = sorted((float(row['start']), float(row['end'])) for row in segments
                       if row.get('speaker_entity_id') != speaker_id)
    selected: list[tuple[float, float]] = []
    for start, end in owned:
        pieces = [(start, end)]
        for cut_start, cut_end in competing:
            pieces = [(lo, hi) for left, right in pieces
                      for lo, hi in ((left, min(right, cut_start)),
                                     (max(left, cut_end), right)) if hi > lo]
            if not pieces:
                break
        selected.extend(pieces)
    merged: list[tuple[float, float]] = []
    for start, end in sorted(selected):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return [{'start': start, 'end': end} for start, end in merged]


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
