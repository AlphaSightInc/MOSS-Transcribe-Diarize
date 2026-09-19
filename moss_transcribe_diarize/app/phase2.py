"""Browser-private workspace ownership and persistence."""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, AsyncIterator, Mapping

from starlette.requests import Request

from .phase2_audio import MeetingAudioArtifactSurvives, MeetingAudioCleanupError


SCHEMA_VERSION = 2
REQUIRED_SQLITE_RUNTIME = "3.53.4"
SESSION_COOKIE = "__Host-moss_session"
SESSION_COOKIE_MAX_AGE = 400 * 24 * 60 * 60
OPEN_WORKSPACE_ACCOUNT_ID = "__moss_open_workspace__"
OPEN_WORKSPACE_SESSION_ID = "__moss_open_workspace_session__"
DEFAULT_PHASE2_DATABASE_PATH = (
    Path.home() / ".local" / "share" / "moss-transcribe-diarize" / "phase2.sqlite3"
)
FRONTEND_ASSET_DIR = Path(__file__).resolve().parent / "frontend_assets"
_ASSET_VERSION_CACHE: dict[Path, tuple[tuple[int, int], str]] = {}


def _asset_content_version(path: Path) -> str:
    stat = path.stat()
    identity = (stat.st_mtime_ns, stat.st_size)
    cached = _ASSET_VERSION_CACHE.get(path)
    if cached is not None and cached[0] == identity:
        return cached[1]
    version = hashlib.sha256(path.read_bytes()).hexdigest()
    _ASSET_VERSION_CACHE[path] = (identity, version)
    return version


def _frontend_asset_url(asset_path: str) -> str:
    return f"/static/{asset_path}?v={_asset_content_version(FRONTEND_ASSET_DIR / asset_path)}"


class SchemaVersionError(RuntimeError):
    """The greenfield database exists but is not the one schema this product accepts."""


class SqliteRuntimeError(RuntimeError):
    """The Account process is not linked to the one accepted SQLite runtime."""


class AccountRevoked(PermissionError):
    """An Account lost authority before an owner-bound mutation committed."""


class MeetingNotSettled(RuntimeError):
    """A correction arrived before automatic processing settled."""


class PassageNotFound(KeyError):
    """A selected passage or target speaker is absent from this Meeting."""


@dataclass(frozen=True, slots=True)
class Account:
    account_id: str
    display_name: str
    authority_generation: int


@dataclass(frozen=True, slots=True)
class AccountRevokeTarget:
    account_id: str
    exists: bool
    account: Account | None


@dataclass(frozen=True, slots=True)
class MeetingAudio:
    state: str
    relative_path: str | None
    byte_count: int | None
    duration_ms: int | None
    format: str | None
    sample_rate_hz: int | None
    channels: int | None
    bit_rate_bps: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "relative_path": self.relative_path,
            "byte_count": self.byte_count,
            "duration_ms": self.duration_ms,
            "format": self.format,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "bit_rate_bps": self.bit_rate_bps,
        }


def _unavailable_meeting_audio() -> MeetingAudio:
    return MeetingAudio(
        state="unavailable",
        relative_path=None,
        byte_count=None,
        duration_ms=None,
        format=None,
        sample_rate_hz=None,
        channels=None,
        bit_rate_bps=None,
    )


@dataclass(frozen=True, slots=True)
class Meeting:
    meeting_id: str
    mode: str
    title: str | None
    status: str
    created_at_ms: int
    title_source: str = "automatic"
    transcript: dict[str, object] | None = None
    transcript_version: int = 0
    audio: MeetingAudio | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    notice: str | None = None
    needs_review: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.meeting_id,
            "mode": self.mode,
            "title": self.title,
            "title_source": self.title_source,
            "status": self.status,
            "created_at_ms": self.created_at_ms,
            "transcript": self.transcript,
            "transcript_version": self.transcript_version,
            "audio": None if self.audio is None else self.audio.to_dict(),
            **({"failure_code": self.failure_code, "failure_reason": self.failure_reason} if self.failure_code else {}),
            **({"notice": self.notice} if self.notice else {}),
            "needs_review": self.needs_review,
        }


@dataclass(frozen=True, slots=True)
class PassageSpeakerResult:
    meeting_id: str
    segment_ids: tuple[str, ...]
    speaker_id: str
    label: str
    transcript_version: int
    needs_review: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "meeting_id": self.meeting_id,
            "segment_ids": list(self.segment_ids),
            "speaker_id": self.speaker_id,
            "label": self.label,
            "transcript_version": self.transcript_version,
            "needs_review": self.needs_review,
        }


class Phase2Store:
    """One SQLite connection hidden behind AccountWorkspace ownership operations."""

    def __init__(self, connection: Any):
        self._connection = connection
        self._write_lock = asyncio.Lock()

    @classmethod
    async def open(cls, database_path: str | Path) -> "Phase2Store":
        if sqlite3.sqlite_version != REQUIRED_SQLITE_RUNTIME:
            raise SqliteRuntimeError(
                "Refusing SQLite runtime "
                f"{sqlite3.sqlite_version}; exactly {REQUIRED_SQLITE_RUNTIME} is required."
            )
        try:
            import aiosqlite
        except ImportError as exc:  # pragma: no cover - package dependency is definitive.
            raise RuntimeError("Install aiosqlite 0.22.1 to enable Phase-2 persistence.") from exc

        path_text = str(database_path)
        is_memory = path_text == ":memory:"
        path = None if is_memory else Path(database_path)
        existed = False if is_memory else path.exists()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(path_text)
        connection.row_factory = aiosqlite.Row
        store = cls(connection)
        try:
            # An old database is refused as found.  In particular, do not ask SQLite to switch
            # journal modes before proving that this file is schema v2: WAL setup itself mutates
            # a pre-existing database and can create sidecar files.
            version = await store.user_version()
            if existed and version != SCHEMA_VERSION:
                raise SchemaVersionError(
                    f"Refusing existing database with user_version={version}; expected {SCHEMA_VERSION}."
                )

            await connection.execute("PRAGMA journal_mode=WAL")
            await connection.execute("PRAGMA foreign_keys=ON")
            await connection.execute("PRAGMA synchronous=FULL")
            if not existed and version == 0:
                await store._initialize_schema()
            elif version != SCHEMA_VERSION:
                raise SchemaVersionError(
                    f"Refusing existing database with user_version={version}; expected {SCHEMA_VERSION}."
                )
            # Additive outcome storage for existing schema-v2 workspaces; no data rewrite.
            await connection.execute("""CREATE TABLE IF NOT EXISTS meeting_outcomes (
                account_id TEXT NOT NULL, meeting_id TEXT NOT NULL,
                failure_code TEXT, failure_reason TEXT, notice TEXT,
                PRIMARY KEY(account_id, meeting_id),
                FOREIGN KEY(account_id, meeting_id) REFERENCES meetings(account_id, meeting_id)
                    ON DELETE CASCADE
            )""")
            await connection.commit()
            return store
        except BaseException:
            await connection.close()
            raise

    async def close(self) -> None:
        await self._connection.close()

    async def user_version(self) -> int:
        async with self._external_read():
            cursor = await self._connection.execute("PRAGMA user_version")
            row = await cursor.fetchone()
            await cursor.close()
        return int(row[0])

    async def table_names(self) -> set[str]:
        async with self._external_read():
            cursor = await self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return {str(row[0]) for row in rows}

    async def sqlite_settings(self) -> dict[str, object]:
        settings: dict[str, object] = {}
        async with self._external_read():
            for name in ("journal_mode", "foreign_keys", "synchronous"):
                cursor = await self._connection.execute(f"PRAGMA {name}")
                row = await cursor.fetchone()
                await cursor.close()
                settings[name] = row[0]
        return settings

    async def _initialize_schema(self) -> None:
        await self._connection.executescript(
            """
            CREATE TABLE accounts (
                account_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
                authority_generation INTEGER NOT NULL,
                created_at_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL
            );
            CREATE TABLE sign_in_sessions (
                session_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                created_at_ms INTEGER NOT NULL,
                FOREIGN KEY(account_id) REFERENCES accounts(account_id)
            );
            CREATE TABLE meetings (
                account_id TEXT NOT NULL,
                meeting_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                title TEXT,
                title_source TEXT NOT NULL DEFAULT 'automatic'
                    CHECK(title_source IN ('automatic', 'manual')),
                status TEXT NOT NULL,
                created_at_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL,
                PRIMARY KEY(account_id, meeting_id),
                FOREIGN KEY(account_id) REFERENCES accounts(account_id)
            );
            CREATE TABLE meeting_transcripts (
                account_id TEXT NOT NULL,
                meeting_id TEXT NOT NULL,
                document_json TEXT NOT NULL,
                version INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL,
                PRIMARY KEY(account_id, meeting_id),
                FOREIGN KEY(account_id, meeting_id)
                    REFERENCES meetings(account_id, meeting_id)
            );
            CREATE TABLE meeting_speakers (
                account_id TEXT NOT NULL,
                meeting_id TEXT NOT NULL,
                speaker_id TEXT NOT NULL,
                label TEXT,
                voiceprint_id TEXT,
                PRIMARY KEY(account_id, meeting_id, speaker_id),
                FOREIGN KEY(account_id, meeting_id)
                    REFERENCES meetings(account_id, meeting_id),
                FOREIGN KEY(account_id, voiceprint_id)
                    REFERENCES voiceprints(account_id, voiceprint_id)
            );
            CREATE TABLE meeting_audio (
                account_id TEXT NOT NULL,
                meeting_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('available', 'partial', 'unavailable')),
                relative_path TEXT,
                byte_count INTEGER,
                duration_ms INTEGER,
                format TEXT,
                sample_rate_hz INTEGER,
                channels INTEGER,
                bit_rate_bps INTEGER,
                updated_at_ms INTEGER NOT NULL,
                PRIMARY KEY(account_id, meeting_id),
                CHECK(
                    (state = 'unavailable'
                        AND relative_path IS NULL
                        AND byte_count IS NULL
                        AND duration_ms IS NULL
                        AND format IS NULL
                        AND sample_rate_hz IS NULL
                        AND channels IS NULL
                        AND bit_rate_bps IS NULL)
                    OR
                    (state IN ('available', 'partial')
                        AND relative_path IS NOT NULL
                        AND byte_count > 0
                        AND duration_ms > 0
                        AND format = 'mp3'
                        AND sample_rate_hz = 16000
                        AND channels = 1
                        AND bit_rate_bps = 48000)
                ),
                FOREIGN KEY(account_id, meeting_id)
                    REFERENCES meetings(account_id, meeting_id)
            );
            CREATE TABLE voiceprints (
                account_id TEXT NOT NULL,
                voiceprint_id TEXT NOT NULL,
                label TEXT NOT NULL,
                embedder_id TEXT NOT NULL,
                embedding_dimension INTEGER NOT NULL CHECK(embedding_dimension > 0),
                revision INTEGER NOT NULL,
                created_at_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL,
                PRIMARY KEY(account_id, voiceprint_id),
                FOREIGN KEY(account_id) REFERENCES accounts(account_id)
            );
            CREATE TABLE voiceprint_samples (
                account_id TEXT NOT NULL,
                voiceprint_id TEXT NOT NULL,
                sample_id TEXT NOT NULL,
                vector BLOB NOT NULL,
                source_meeting_id TEXT,
                created_at_ms INTEGER NOT NULL,
                PRIMARY KEY(account_id, voiceprint_id, sample_id),
                FOREIGN KEY(account_id, voiceprint_id)
                    REFERENCES voiceprints(account_id, voiceprint_id),
                FOREIGN KEY(account_id, source_meeting_id)
                    REFERENCES meetings(account_id, meeting_id)
            );
            CREATE TABLE llm_artifacts (
                account_id TEXT NOT NULL,
                meeting_id TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                state TEXT NOT NULL,
                document_json TEXT,
                provenance_json TEXT,
                created_at_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL,
                PRIMARY KEY(account_id, meeting_id, artifact_id),
                FOREIGN KEY(account_id, meeting_id)
                    REFERENCES meetings(account_id, meeting_id)
            );
            CREATE INDEX sign_in_sessions_account ON sign_in_sessions(account_id);
            CREATE INDEX meetings_account_created ON meetings(account_id, created_at_ms DESC);
            PRAGMA user_version = 2;
            """
        )
        await self._connection.commit()

    @asynccontextmanager
    async def _mutation(self) -> AsyncIterator[None]:
        async with self._write_lock:
            await self._connection.execute("BEGIN")
            try:
                yield
            except BaseException:
                await self._connection.rollback()
                raise
            else:
                await self._connection.commit()

    @asynccontextmanager
    async def _external_read(self) -> AsyncIterator[None]:
        """Keep request-facing reads outside another coroutine's uncommitted transaction."""

        async with self._write_lock:
            yield

    async def operator_snapshot(self) -> dict[str, object]:
        """Read durable operator aggregates once; Account content never crosses this seam."""

        async with self._external_read():
            cursor = await self._connection.execute(
                """
                SELECT a.account_id, a.display_name, a.enabled,
                       (SELECT COUNT(*) FROM sign_in_sessions s
                        WHERE s.account_id = a.account_id) AS sign_in_sessions,
                       (SELECT COUNT(*) FROM meetings m
                        WHERE m.account_id = a.account_id AND m.mode = 'live'
                          AND m.status = 'active') AS active_live,
                       (SELECT COUNT(*) FROM meetings m
                        WHERE m.account_id = a.account_id AND m.mode = 'file'
                          AND m.status = 'active') AS active_file,
                       (SELECT COUNT(*) FROM meetings m
                        WHERE m.account_id = a.account_id) AS meetings,
                       (SELECT COUNT(*) FROM meeting_transcripts t
                        WHERE t.account_id = a.account_id) AS transcripts,
                       (SELECT COUNT(*) FROM voiceprints v
                        WHERE v.account_id = a.account_id) AS voiceprints,
                       (SELECT COUNT(*) FROM llm_artifacts l
                        WHERE l.account_id = a.account_id
                          AND l.kind = 'final_summary') AS final_summaries,
                       (SELECT COUNT(*) FROM meeting_audio ma
                        WHERE ma.account_id = a.account_id
                          AND ma.state = 'available') AS audio_available_count,
                       COALESCE((SELECT SUM(ma.byte_count) FROM meeting_audio ma
                        WHERE ma.account_id = a.account_id
                          AND ma.state = 'available'), 0) AS audio_available_bytes,
                       (SELECT COUNT(*) FROM meeting_audio ma
                        WHERE ma.account_id = a.account_id
                          AND ma.state = 'partial') AS audio_partial_count,
                       COALESCE((SELECT SUM(ma.byte_count) FROM meeting_audio ma
                        WHERE ma.account_id = a.account_id
                          AND ma.state = 'partial'), 0) AS audio_partial_bytes,
                       (SELECT COUNT(*) FROM meeting_audio ma
                        WHERE ma.account_id = a.account_id
                          AND ma.state = 'unavailable') AS audio_unavailable_count
                FROM accounts a
                ORDER BY a.account_id
                """
            )
            accounts = [dict(row) for row in await cursor.fetchall()]
            await cursor.close()
            cursor = await self._connection.execute(
                """
                SELECT a.account_id, m.meeting_id, m.mode, m.status,
                       m.created_at_ms
                FROM meetings m
                JOIN accounts a ON a.account_id = m.account_id
                WHERE m.status = 'active'
                ORDER BY m.created_at_ms, m.meeting_id
                """
            )
            active_meetings = [dict(row) for row in await cursor.fetchall()]
            await cursor.close()
            cursor = await self._connection.execute(
                """
                SELECT state, COUNT(*) AS count, COALESCE(SUM(byte_count), 0) AS bytes
                FROM meeting_audio
                GROUP BY state
                """
            )
            audio = [dict(row) for row in await cursor.fetchall()]
            await cursor.close()
        return {
            "accounts": accounts,
            "active_meetings": active_meetings,
            "audio": audio,
        }

    async def operator_has_active_meeting(self, meeting_id: str) -> bool:
        """Distinguish terminal/no-change from an active row missing its process owner."""

        async with self._external_read():
            cursor = await self._connection.execute(
                "SELECT 1 FROM meetings WHERE meeting_id = ? AND status = 'active' LIMIT 1",
                (meeting_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
        return row is not None

    async def revoke_account(self, account_id: str) -> bool:
        """Direct store primitive retained for offline recovery/tests, not the host CLI."""

        target = await self.account_revoke_target(account_id)
        return await self.finalize_account_revoke(target)

    async def account_revoke_target(self, account_id: str) -> AccountRevokeTarget:
        if not account_id:
            raise ValueError("Workspace ID is required.")
        async with self._external_read():
            cursor = await self._connection.execute(
                """
                SELECT account_id, display_name, authority_generation
                FROM accounts WHERE account_id = ? AND enabled = 1
                """,
                (account_id,),
            )
            account_row = await cursor.fetchone()
            await cursor.close()
        if account_row is None:
            return AccountRevokeTarget(account_id, False, None)
        return AccountRevokeTarget(
            account_id,
            True,
            Account(
                account_id=account_row["account_id"],
                display_name=account_row["display_name"],
                authority_generation=int(account_row["authority_generation"]),
            ),
        )

    async def finalize_account_revoke(self, target: AccountRevokeTarget) -> bool:
        """Make authority loss durable only after the lifecycle owner drains work."""

        if not target.exists:
            return False
        now = _now_ms()
        async with self._mutation():
            account = target.account
            if account is not None:
                cursor = await self._connection.execute(
                    """
                    SELECT COUNT(*) AS active_count FROM meetings
                    WHERE account_id = ? AND status = 'active'
                    """,
                    (account.account_id,),
                )
                active_count = int((await cursor.fetchone())["active_count"])
                await cursor.close()
                if active_count != 0:
                    raise RuntimeError(
                        "Account revoke requires every Meeting to be durably terminal."
                    )
                cursor = await self._connection.execute(
                    """
                    UPDATE accounts
                    SET enabled = 0,
                        authority_generation = authority_generation + 1,
                        updated_at_ms = ?
                    WHERE account_id = ? AND enabled = 1 AND authority_generation = ?
                    """,
                    (now, account.account_id, account.authority_generation),
                )
                changed = cursor.rowcount
                await cursor.close()
                if changed != 1:
                    raise AccountRevoked("Account authority changed during revoke.")
                await self._connection.execute(
                    "DELETE FROM sign_in_sessions WHERE account_id = ?", (account.account_id,)
                )
            return True

    async def list_accounts(self) -> list[dict[str, object]]:
        async with self._external_read():
            cursor = await self._connection.execute(
                "SELECT account_id, enabled FROM accounts ORDER BY account_id"
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return [{"account_id": row["account_id"], "enabled": bool(row["enabled"])} for row in rows]

    async def recover_active_meetings(
        self,
        *,
        audio_archive: Any | None = None,
        live_audio_stages: Any | None = None,
    ) -> None:
        """The product process never resumes capture that was active before startup."""

        if live_audio_stages is not None and audio_archive is None:
            raise ValueError("Live audio startup recovery requires an archive.")
        if audio_archive is not None:
            await self._recover_active_file_meetings(audio_archive)
        if audio_archive is not None and live_audio_stages is not None:
            await self._recover_active_live_meetings(
                audio_archive,
                live_audio_stages,
            )

        await self._assert_no_active_meetings()

    async def recover_active_account_meetings(
        self,
        account: Account,
        *,
        audio_archive: Any,
        live_audio_stages: Any | None,
    ) -> None:
        """Settle residual rows through their fixed File/Live recovery paths."""

        await self._recover_active_file_meetings(audio_archive, account=account)
        if live_audio_stages is not None:
            await self._recover_active_live_meetings(
                audio_archive,
                live_audio_stages,
                account=account,
            )
        await self._assert_no_active_meetings(account.account_id)

    async def _recover_active_live_meetings(
        self,
        audio_archive: Any,
        live_audio_stages: Any,
        *,
        account: Account | None = None,
    ) -> None:
        if account is None:
            async with self._external_read():
                cursor = await self._connection.execute(
                    """
                    SELECT m.account_id, m.meeting_id,
                           ma.state AS audio_state,
                           ma.relative_path AS audio_relative_path,
                           ma.byte_count AS audio_byte_count
                    FROM meetings m
                    LEFT JOIN meeting_audio ma
                      ON ma.account_id = m.account_id AND ma.meeting_id = m.meeting_id
                    WHERE m.mode = 'live' AND m.status = 'interrupted'
                    ORDER BY m.created_at_ms, m.meeting_id
                    """
                )
                interrupted_rows = await cursor.fetchall()
                await cursor.close()
        else:
            interrupted_rows = ()
        if account is None:
            for row in interrupted_rows:
                if row["audio_state"] in {"available", "partial"}:
                    await asyncio.to_thread(
                        audio_archive.discard_staged,
                        row["account_id"],
                        row["meeting_id"],
                    )
                    resolved = audio_archive.resolve(
                        row["account_id"],
                        row["meeting_id"],
                        row["audio_relative_path"],
                        int(row["audio_byte_count"]),
                    )
                    if resolved is None:
                        await asyncio.to_thread(
                            audio_archive.discard_stored,
                            row["account_id"],
                            row["meeting_id"],
                            row["audio_relative_path"],
                        )
                        await self._mark_interrupted_meeting_audio_unavailable(
                            row["account_id"],
                            row["meeting_id"],
                        )
                    elif row["audio_state"] == "available":
                        if not await self._downgrade_interrupted_live_audio_to_partial(
                            row["account_id"], row["meeting_id"]
                        ):
                            raise RuntimeError(
                                "Interrupted Live Meeting audio truth changed during recovery."
                            )
                else:
                    await asyncio.to_thread(
                        audio_archive.discard_unrecorded,
                        row["account_id"],
                        row["meeting_id"],
                    )
                await asyncio.to_thread(
                    live_audio_stages.discard,
                    row["account_id"],
                    row["meeting_id"],
                )

        async with self._external_read():
            cursor = await self._connection.execute(
                """
                SELECT m.account_id, m.meeting_id, a.authority_generation
                FROM meetings m
                JOIN accounts a ON a.account_id = m.account_id AND a.enabled = 1
                WHERE m.mode = 'live' AND m.status = 'active'
                  AND (? IS NULL OR m.account_id = ?)
                ORDER BY m.created_at_ms, m.meeting_id
                """,
                (
                    None if account is None else account.account_id,
                    None if account is None else account.account_id,
                ),
            )
            rows = await cursor.fetchall()
            await cursor.close()
        for row in rows:
            handle = MeetingHandle(
                self,
                row["account_id"],
                int(row["authority_generation"]),
                row["meeting_id"],
            )
            await handle.recover_interrupted_audio(audio_archive, live_audio_stages)
            await handle.finish("interrupted")

    async def _recover_active_file_meetings(
        self,
        audio_archive: Any,
        *,
        account: Account | None = None,
    ) -> None:
        """Reconcile canonical File artifact paths before making a crashed row terminal."""

        async with self._external_read():
            cursor = await self._connection.execute(
                """
                SELECT m.account_id, m.meeting_id, a.authority_generation
                FROM meetings m
                JOIN accounts a ON a.account_id = m.account_id AND a.enabled = 1
                WHERE m.mode = 'file' AND m.status = 'active'
                  AND (? IS NULL OR m.account_id = ?)
                ORDER BY m.created_at_ms, m.meeting_id
                """,
                (
                    None if account is None else account.account_id,
                    None if account is None else account.account_id,
                ),
            )
            rows = await cursor.fetchall()
            await cursor.close()
        for row in rows:
            handle = MeetingHandle(
                self,
                row["account_id"],
                int(row["authority_generation"]),
                row["meeting_id"],
            )
            await handle.recover_interrupted_file_audio(audio_archive)
            await handle.finish("interrupted")

    async def _assert_no_active_meetings(self, account_id: str | None = None) -> None:
        async with self._external_read():
            cursor = await self._connection.execute(
                """
                SELECT COUNT(*) AS active_count FROM meetings
                WHERE status = 'active' AND (? IS NULL OR account_id = ?)
                """,
                (account_id, account_id),
            )
            active_count = int((await cursor.fetchone())["active_count"])
            await cursor.close()
        if active_count != 0:
            raise RuntimeError("Active Meeting recovery did not reach durable terminal truth.")

    async def _mark_interrupted_meeting_audio_unavailable(
        self,
        account_id: str,
        meeting_id: str,
    ) -> None:
        """Reconcile terminal Live artifact truth without reviving captured authority."""

        now = _now_ms()
        async with self._mutation():
            cursor = await self._connection.execute(
                """
                UPDATE meeting_audio
                SET state = 'unavailable', relative_path = NULL, byte_count = NULL,
                    duration_ms = NULL, format = NULL, sample_rate_hz = NULL,
                    channels = NULL, bit_rate_bps = NULL, updated_at_ms = ?
                WHERE account_id = ? AND meeting_id = ?
                  AND state IN ('available', 'partial')
                  AND EXISTS (
                    SELECT 1 FROM meetings
                    WHERE account_id = ? AND meeting_id = ?
                      AND mode = 'live' AND status = 'interrupted'
                  )
                """,
                (now, account_id, meeting_id, account_id, meeting_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Interrupted Live Meeting audio truth changed during recovery.")

    async def _downgrade_interrupted_live_audio_to_partial(
        self,
        account_id: str,
        meeting_id: str,
    ) -> bool:
        """Keep verified MP3 metadata while making interrupted completeness truthful."""

        now = _now_ms()
        async with self._mutation():
            cursor = await self._connection.execute(
                """
                UPDATE meeting_audio
                SET state = 'partial', updated_at_ms = ?
                WHERE account_id = ? AND meeting_id = ? AND state = 'available'
                  AND EXISTS (
                    SELECT 1 FROM meetings
                    WHERE account_id = ? AND meeting_id = ?
                      AND mode = 'live' AND status = 'interrupted'
                  )
                """,
                (now, account_id, meeting_id, account_id, meeting_id),
            )
            return cursor.rowcount == 1

    async def bootstrap_browser(
        self,
        session_id: str | None,
        *,
        open_workspace: bool = False,
    ) -> tuple[Account, str]:
        """Open this browser's workspace, or atomically create its first owner/credential.

        Private mode is called only by explicit bootstrap. In-flight private work never
        creates an owner when its credential disappears. Invalid private credentials do
        not revive ownership.
        """

        if open_workspace:
            account = await self.account_for_session(OPEN_WORKSPACE_SESSION_ID)
            if account is not None:
                return account, OPEN_WORKSPACE_SESSION_ID
            now = _now_ms()
            async with self._mutation():
                await self._connection.execute(
                    """INSERT OR IGNORE INTO accounts(
                        account_id, display_name, enabled, authority_generation,
                        created_at_ms, updated_at_ms
                    ) VALUES (?, ?, 1, 0, ?, ?)""",
                    (OPEN_WORKSPACE_ACCOUNT_ID, "Open workspace", now, now),
                )
                await self._connection.execute(
                    """INSERT OR IGNORE INTO sign_in_sessions(
                        session_id, account_id, created_at_ms
                    ) VALUES (?, ?, ?)""",
                    (OPEN_WORKSPACE_SESSION_ID, OPEN_WORKSPACE_ACCOUNT_ID, now),
                )
            account = await self.account_for_session(OPEN_WORKSPACE_SESSION_ID)
            if account is None:
                raise AccountRevoked("Open workspace is no longer available.")
            return account, OPEN_WORKSPACE_SESSION_ID
        if session_id:
            account = await self.account_for_session(session_id)
            if account is None:
                raise AccountRevoked("Workspace credential is no longer valid.")
            return account, session_id
        account = Account(secrets.token_urlsafe(24), "This browser", 0)
        session_id = secrets.token_urlsafe(32)
        now = _now_ms()
        async with self._mutation():
            await self._connection.execute(
                """INSERT INTO accounts(
                    account_id, display_name, enabled, authority_generation,
                    created_at_ms, updated_at_ms
                ) VALUES (?, ?, 1, 0, ?, ?)""",
                (account.account_id, account.display_name, now, now),
            )
            await self._connection.execute(
                "INSERT INTO sign_in_sessions(session_id, account_id, created_at_ms) VALUES (?, ?, ?)",
                (session_id, account.account_id, now),
            )
        return account, session_id

    async def account_for_session(self, session_id: str | None) -> Account | None:
        if not session_id:
            return None
        async with self._external_read():
            cursor = await self._connection.execute(
                """
                SELECT a.account_id, a.display_name, a.authority_generation
                FROM sign_in_sessions s
                JOIN accounts a ON a.account_id = s.account_id
                WHERE s.session_id = ? AND a.enabled = 1
                """,
                (session_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
        if row is None:
            return None
        return Account(
            account_id=row["account_id"],
            display_name=row["display_name"],
            authority_generation=int(row["authority_generation"]),
        )

    def workspace(self, account: Account) -> "AccountWorkspace":
        return AccountWorkspace(self, account)

    async def _list_meetings(self, account_id: str, authority_generation: int) -> list[Meeting]:
        async with self._external_read():
            cursor = await self._connection.execute(
                """
                SELECT m.meeting_id, m.mode, m.title, m.title_source,
                       m.status, m.created_at_ms,
                       mo.failure_code, mo.failure_reason, mo.notice,
                       t.document_json, t.version AS transcript_version,
                       ma.state AS audio_state, ma.relative_path AS audio_relative_path,
                       ma.byte_count AS audio_byte_count, ma.duration_ms AS audio_duration_ms,
                       ma.format AS audio_format, ma.sample_rate_hz AS audio_sample_rate_hz,
                       ma.channels AS audio_channels, ma.bit_rate_bps AS audio_bit_rate_bps
                FROM meetings m
                JOIN accounts a ON a.account_id = m.account_id
                    AND a.enabled = 1 AND a.authority_generation = ?
                LEFT JOIN meeting_outcomes mo
                    ON mo.account_id = m.account_id AND mo.meeting_id = m.meeting_id
                LEFT JOIN meeting_transcripts t
                    ON t.account_id = m.account_id AND t.meeting_id = m.meeting_id
                LEFT JOIN meeting_audio ma
                    ON ma.account_id = m.account_id AND ma.meeting_id = m.meeting_id
                WHERE m.account_id = ?
                ORDER BY CASE WHEN m.status = 'active' THEN 0 ELSE 1 END,
                         m.created_at_ms DESC, m.meeting_id DESC
                """,
                (authority_generation, account_id),
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return [_meeting_from_row(row) for row in rows]

    async def _create_meeting(
        self,
        account_id: str,
        authority_generation: int,
        mode: str,
    ) -> "MeetingHandle":
        if mode not in {"live", "file"}:
            raise ValueError("mode must be live or file.")
        meeting_id = secrets.token_urlsafe(18)
        now = _now_ms()
        async with self._mutation():
            cursor = await self._connection.execute(
                """
                INSERT INTO meetings(
                    account_id, meeting_id, mode, title, title_source,
                    status, created_at_ms, updated_at_ms
                )
                SELECT account_id, ?, ?, NULL, 'automatic', 'active', ?, ?
                FROM accounts
                WHERE account_id = ? AND enabled = 1 AND authority_generation = ?
                """,
                (meeting_id, mode, now, now, account_id, authority_generation),
            )
            if cursor.rowcount != 1:
                raise AccountRevoked("Account is revoked.")
        return MeetingHandle(self, account_id, authority_generation, meeting_id)

    async def _open_meeting(
        self,
        account_id: str,
        authority_generation: int,
        meeting_id: str,
    ) -> "MeetingHandle | None":
        async with self._external_read():
            cursor = await self._connection.execute(
                """
                SELECT 1 FROM meetings m
                JOIN accounts a ON a.account_id = m.account_id
                    AND a.enabled = 1 AND a.authority_generation = ?
                WHERE m.account_id = ? AND m.meeting_id = ?
                """,
                (authority_generation, account_id, meeting_id),
            )
            row = await cursor.fetchone()
            await cursor.close()
        return (
            MeetingHandle(self, account_id, authority_generation, meeting_id)
            if row is not None
            else None
        )

    async def _meeting_snapshot(
        self,
        account_id: str,
        authority_generation: int,
        meeting_id: str,
    ) -> Meeting:
        async with self._external_read():
            cursor = await self._connection.execute(
                """
                SELECT m.meeting_id, m.mode, m.title, m.title_source,
                       m.status, m.created_at_ms,
                       mo.failure_code, mo.failure_reason, mo.notice,
                       t.document_json, t.version AS transcript_version,
                       ma.state AS audio_state, ma.relative_path AS audio_relative_path,
                       ma.byte_count AS audio_byte_count, ma.duration_ms AS audio_duration_ms,
                       ma.format AS audio_format, ma.sample_rate_hz AS audio_sample_rate_hz,
                       ma.channels AS audio_channels, ma.bit_rate_bps AS audio_bit_rate_bps
                FROM meetings m
                JOIN accounts a ON a.account_id = m.account_id
                    AND a.enabled = 1 AND a.authority_generation = ?
                LEFT JOIN meeting_outcomes mo
                    ON mo.account_id = m.account_id AND mo.meeting_id = m.meeting_id
                LEFT JOIN meeting_transcripts t
                    ON t.account_id = m.account_id AND t.meeting_id = m.meeting_id
                LEFT JOIN meeting_audio ma
                    ON ma.account_id = m.account_id AND ma.meeting_id = m.meeting_id
                WHERE m.account_id = ? AND m.meeting_id = ?
                """,
                (authority_generation, account_id, meeting_id),
            )
            row = await cursor.fetchone()
            await cursor.close()
        if row is None:  # A handle is never permitted to escape its Account query.
            raise KeyError(meeting_id)
        return _meeting_from_row(row)

    async def _rename_meeting(
        self,
        account_id: str,
        authority_generation: int,
        meeting_id: str,
        title: str,
    ) -> str:
        normalized = title.strip()
        if not normalized:
            raise ValueError("Meeting title must not be empty.")
        now = _now_ms()
        async with self._mutation():
            cursor = await self._connection.execute(
                """
                UPDATE meetings
                SET title = ?, title_source = 'manual', updated_at_ms = ?
                WHERE account_id = ? AND meeting_id = ?
                  AND EXISTS (
                    SELECT 1 FROM accounts
                    WHERE account_id = ? AND enabled = 1 AND authority_generation = ?
                  )
                """,
                (
                    normalized,
                    now,
                    account_id,
                    meeting_id,
                    account_id,
                    authority_generation,
                ),
            )
            if cursor.rowcount != 1:
                raise AccountRevoked("Meeting authority is revoked or interrupted.")
        return normalized

    async def _reassign_passages(
        self,
        account_id: str,
        authority_generation: int,
        meeting_id: str,
        segment_ids: tuple[str, ...],
        *,
        speaker_id: str | None,
        label: str | None,
    ) -> PassageSpeakerResult:
        selected = tuple(dict.fromkeys(value.strip() for value in segment_ids if value.strip()))
        if not selected or len(selected) != len(segment_ids):
            raise ValueError("Select at least one unique passage.")
        if (speaker_id is None) == (label is None):
            raise ValueError("Choose one existing speaker or enter one new person.")

        now = _now_ms()
        async with self._mutation():
            cursor = await self._connection.execute(
                """
                SELECT m.status, t.document_json, mo.failure_code, mo.notice
                FROM meetings m
                JOIN accounts a ON a.account_id = m.account_id
                    AND a.enabled = 1 AND a.authority_generation = ?
                LEFT JOIN meeting_transcripts t
                    ON t.account_id = m.account_id AND t.meeting_id = m.meeting_id
                LEFT JOIN meeting_outcomes mo
                    ON mo.account_id = m.account_id AND mo.meeting_id = m.meeting_id
                WHERE m.account_id = ? AND m.meeting_id = ?
                """,
                (authority_generation, account_id, meeting_id),
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row is None:
                raise AccountRevoked("Meeting authority is revoked or interrupted.")
            status = str(row["status"])
            if status == "active":
                raise MeetingNotSettled(
                    "Wait for automatic processing to settle before correcting speakers."
                )
            if row["document_json"] is None:
                raise PassageNotFound("Meeting transcript has no passages.")
            document = json.loads(row["document_json"])
            segments = document.get("segments")
            if not isinstance(segments, list):
                raise PassageNotFound("Meeting transcript has no passages.")
            identified = [
                segment
                for segment in segments
                if isinstance(segment, dict) and isinstance(segment.get("id"), str)
            ]
            by_id = {str(segment["id"]): segment for segment in identified}
            if len(by_id) != len(identified):
                raise ValueError("Meeting transcript passage identity is ambiguous.")
            if any(value not in by_id for value in selected):
                raise PassageNotFound("Selected passage was not found.")

            if speaker_id is not None:
                target_id = speaker_id.strip()
                if not target_id or _is_unknown_speaker_value(target_id):
                    raise PassageNotFound("Existing speaker was not found.")
                target = next(
                    (
                        segment
                        for segment in segments
                        if isinstance(segment, dict)
                        and _segment_speaker_id(segment) == target_id
                    ),
                    None,
                )
                if target is None:
                    raise PassageNotFound("Existing speaker was not found.")
                target_label = str(target.get("speaker") or "").strip()
                if not target_label:
                    raise PassageNotFound("Existing speaker was not found.")
            else:
                target_label = label.strip() if label is not None else ""
                if not target_label:
                    raise ValueError("New person name must not be empty.")
                if _is_unknown_speaker_value(target_label):
                    raise ValueError(
                        "Choose a person name that is not an uncertainty label."
                    )
                target_id = f"manual-{secrets.token_urlsafe(12)}"

            for passage_id in selected:
                segment = by_id[passage_id]
                segment["speaker_entity_id"] = target_id
                segment["speaker"] = target_label

            document_json = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
            await self._connection.execute(
                """
                INSERT INTO meeting_speakers(
                    account_id, meeting_id, speaker_id, label, voiceprint_id
                ) VALUES (?, ?, ?, ?, NULL)
                ON CONFLICT(account_id, meeting_id, speaker_id) DO UPDATE SET
                    label = excluded.label
                """,
                (account_id, meeting_id, target_id, target_label),
            )
            await self._connection.execute(
                """
                UPDATE meeting_transcripts
                SET document_json = ?, version = version + 1, updated_at_ms = ?
                WHERE account_id = ? AND meeting_id = ?
                """,
                (document_json, now, account_id, meeting_id),
            )
            await self._connection.execute(
                """
                UPDATE meetings SET updated_at_ms = ?
                WHERE account_id = ? AND meeting_id = ?
                """,
                (now, account_id, meeting_id),
            )
            version_cursor = await self._connection.execute(
                """
                SELECT version FROM meeting_transcripts
                WHERE account_id = ? AND meeting_id = ?
                """,
                (account_id, meeting_id),
            )
            version_row = await version_cursor.fetchone()
            await version_cursor.close()
            return PassageSpeakerResult(
                meeting_id=meeting_id,
                segment_ids=selected,
                speaker_id=target_id,
                label=target_label,
                transcript_version=int(version_row["version"]),
                needs_review=_meeting_needs_review(
                    status, document, row["failure_code"], row["notice"]
                ),
            )

    async def _commit_transcript(
        self,
        account_id: str,
        authority_generation: int,
        meeting_id: str,
        document: Mapping[str, object],
        *,
        terminal: bool,
    ) -> int:
        document_json = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
        now = _now_ms()
        async with self._mutation():
            cursor = await self._connection.execute(
                """
                UPDATE meetings
                SET status = ?, updated_at_ms = ?
                WHERE account_id = ? AND meeting_id = ? AND status = 'active'
                  AND EXISTS (
                    SELECT 1 FROM accounts
                    WHERE account_id = ? AND enabled = 1 AND authority_generation = ?
                  )
                """,
                (
                    "completed" if terminal else "active",
                    now,
                    account_id,
                    meeting_id,
                    account_id,
                    authority_generation,
                ),
            )
            if cursor.rowcount != 1:
                raise AccountRevoked("Meeting authority is revoked or interrupted.")
            await self._connection.execute(
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
            version_cursor = await self._connection.execute(
                """
                SELECT version FROM meeting_transcripts
                WHERE account_id = ? AND meeting_id = ?
                """,
                (account_id, meeting_id),
            )
            row = await version_cursor.fetchone()
            await version_cursor.close()
            return int(row["version"])

    async def _finish_meeting(
        self,
        account_id: str,
        authority_generation: int,
        meeting_id: str,
        status: str,
        *, failure_code: str | None = None, failure_reason: str | None = None,
        notice: str | None = None,
    ) -> None:
        if status not in {"completed", "failed", "interrupted"}:
            raise ValueError("Meeting terminal status is invalid.")
        now = _now_ms()
        async with self._mutation():
            cursor = await self._connection.execute(
                """
                UPDATE meetings
                SET status = ?, updated_at_ms = ?
                WHERE account_id = ? AND meeting_id = ? AND status = 'active'
                  AND EXISTS (
                    SELECT 1 FROM accounts
                    WHERE account_id = ? AND enabled = 1 AND authority_generation = ?
                  )
                """,
                (status, now, account_id, meeting_id, account_id, authority_generation),
            )
            if cursor.rowcount != 1:
                raise AccountRevoked("Meeting authority is revoked or interrupted.")

            if failure_code or notice:
                await self._connection.execute(
                    "INSERT INTO meeting_outcomes VALUES (?, ?, ?, ?, ?)",
                    (account_id, meeting_id, failure_code, failure_reason, notice),
                )

    async def _finish_meeting_with_transcript(
        self,
        account_id: str,
        authority_generation: int,
        meeting_id: str,
        document: Mapping[str, object],
        status: str,
        *, notice: str | None = None,
    ) -> int:
        """Atomically publish a last transcript revision and its terminal Meeting state."""

        if status not in {"completed", "failed", "interrupted"}:
            raise ValueError("Meeting terminal status is invalid.")
        document_json = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
        now = _now_ms()
        async with self._mutation():
            cursor = await self._connection.execute(
                """
                UPDATE meetings
                SET status = ?, updated_at_ms = ?
                WHERE account_id = ? AND meeting_id = ? AND status = 'active'
                  AND EXISTS (
                    SELECT 1 FROM accounts
                    WHERE account_id = ? AND enabled = 1 AND authority_generation = ?
                  )
                """,
                (status, now, account_id, meeting_id, account_id, authority_generation),
            )
            if cursor.rowcount != 1:
                raise AccountRevoked("Meeting authority is revoked or interrupted.")
            await self._connection.execute(
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
            if notice:
                await self._connection.execute(
                    "INSERT INTO meeting_outcomes VALUES (?, ?, ?, ?, ?)",
                    (account_id, meeting_id, None, None, notice),
                )
            version_cursor = await self._connection.execute(
                """
                SELECT version FROM meeting_transcripts
                WHERE account_id = ? AND meeting_id = ?
                """,
                (account_id, meeting_id),
            )
            row = await version_cursor.fetchone()
            await version_cursor.close()
            return int(row["version"])

    async def _commit_meeting_audio(
        self,
        account_id: str,
        authority_generation: int,
        meeting_id: str,
        audio: MeetingAudio,
    ) -> None:
        now = _now_ms()
        async with self._mutation():
            cursor = await self._connection.execute(
                """
                UPDATE meetings
                SET updated_at_ms = ?
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
            await self._connection.execute(
                """
                INSERT INTO meeting_audio(
                    account_id, meeting_id, state, relative_path, byte_count, duration_ms,
                    format, sample_rate_hz, channels, bit_rate_bps, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, meeting_id) DO UPDATE SET
                    state = excluded.state,
                    relative_path = excluded.relative_path,
                    byte_count = excluded.byte_count,
                    duration_ms = excluded.duration_ms,
                    format = excluded.format,
                    sample_rate_hz = excluded.sample_rate_hz,
                    channels = excluded.channels,
                    bit_rate_bps = excluded.bit_rate_bps,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (
                    account_id,
                    meeting_id,
                    audio.state,
                    audio.relative_path,
                    audio.byte_count,
                    audio.duration_ms,
                    audio.format,
                    audio.sample_rate_hz,
                    audio.channels,
                    audio.bit_rate_bps,
                    now,
                ),
            )

    async def _meeting_audio(
        self,
        account_id: str,
        authority_generation: int,
        meeting_id: str,
    ) -> MeetingAudio | None:
        async with self._external_read():
            cursor = await self._connection.execute(
                """
                SELECT ma.state AS audio_state, ma.relative_path AS audio_relative_path,
                       ma.byte_count AS audio_byte_count, ma.duration_ms AS audio_duration_ms,
                       ma.format AS audio_format, ma.sample_rate_hz AS audio_sample_rate_hz,
                       ma.channels AS audio_channels, ma.bit_rate_bps AS audio_bit_rate_bps
                FROM meetings m
                JOIN accounts a ON a.account_id = m.account_id
                    AND a.enabled = 1 AND a.authority_generation = ?
                LEFT JOIN meeting_audio ma
                    ON ma.account_id = m.account_id AND ma.meeting_id = m.meeting_id
                WHERE m.account_id = ? AND m.meeting_id = ?
                """,
                (authority_generation, account_id, meeting_id),
            )
            row = await cursor.fetchone()
            await cursor.close()
        if row is None:
            raise AccountRevoked("Meeting authority is revoked or interrupted.")
        return _meeting_audio_from_row(row)

    async def _mark_meeting_audio_unavailable(
        self,
        account_id: str,
        authority_generation: int,
        meeting_id: str,
    ) -> None:
        now = _now_ms()
        async with self._mutation():
            cursor = await self._connection.execute(
                """
                UPDATE meeting_audio
                SET state = 'unavailable', relative_path = NULL, byte_count = NULL,
                    duration_ms = NULL, format = NULL, sample_rate_hz = NULL,
                    channels = NULL, bit_rate_bps = NULL, updated_at_ms = ?
                WHERE account_id = ? AND meeting_id = ?
                  AND EXISTS (
                    SELECT 1 FROM accounts
                    WHERE account_id = ? AND enabled = 1 AND authority_generation = ?
                  )
                """,
                (now, account_id, meeting_id, account_id, authority_generation),
            )
            if cursor.rowcount != 1:
                raise AccountRevoked("Meeting authority is revoked or interrupted.")

    async def _downgrade_meeting_audio_to_partial(
        self,
        account_id: str,
        authority_generation: int,
        meeting_id: str,
    ) -> None:
        now = _now_ms()
        async with self._mutation():
            cursor = await self._connection.execute(
                """
                UPDATE meeting_audio
                SET state = 'partial', updated_at_ms = ?
                WHERE account_id = ? AND meeting_id = ? AND state = 'available'
                  AND EXISTS (
                    SELECT 1 FROM meetings
                    WHERE account_id = ? AND meeting_id = ? AND status = 'active'
                  )
                  AND EXISTS (
                    SELECT 1 FROM accounts
                    WHERE account_id = ? AND enabled = 1 AND authority_generation = ?
                  )
                """,
                (
                    now,
                    account_id,
                    meeting_id,
                    account_id,
                    meeting_id,
                    account_id,
                    authority_generation,
                ),
            )
            if cursor.rowcount != 1:
                raise AccountRevoked("Meeting authority is revoked or interrupted.")


class AccountWorkspace:
    """The only public persistence authority opened by a valid MOSS session."""

    def __init__(self, store: Phase2Store, account: Account):
        self._store = store
        self._account = account

    @property
    def owner_key(self) -> tuple[str, int]:
        """Captured Account authority for deeper owner-bound modules."""

        return self._account.account_id, self._account.authority_generation

    async def list_meetings(self) -> list[Meeting]:
        return await self._store._list_meetings(
            self._account.account_id,
            self._account.authority_generation,
        )

    async def create_meeting(self, mode: str) -> "MeetingHandle":
        return await self._store._create_meeting(
            self._account.account_id,
            self._account.authority_generation,
            mode,
        )

    async def open_meeting(self, meeting_id: str) -> "MeetingHandle | None":
        return await self._store._open_meeting(
            self._account.account_id,
            self._account.authority_generation,
            meeting_id,
        )


class MeetingHandle:
    """A Meeting locator that is already bound to its owner and cannot be rebound by callers."""

    def __init__(
        self,
        store: Phase2Store,
        account_id: str,
        authority_generation: int,
        meeting_id: str,
    ):
        self._store = store
        self._account_id = account_id
        self._authority_generation = authority_generation
        self.meeting_id = meeting_id

    @property
    def owner_key(self) -> tuple[str, int]:
        """Captured Account authority for process-owned lifecycle registries."""

        return self._account_id, self._authority_generation

    async def snapshot(self) -> Meeting:
        return await self._store._meeting_snapshot(
            self._account_id,
            self._authority_generation,
            self.meeting_id,
        )

    async def rename(self, title: str) -> str:
        return await self._store._rename_meeting(
            self._account_id,
            self._authority_generation,
            self.meeting_id,
            title,
        )

    async def reassign_passages(
        self,
        segment_ids: tuple[str, ...],
        *,
        speaker_id: str | None = None,
        label: str | None = None,
    ) -> PassageSpeakerResult:
        return await self._store._reassign_passages(
            self._account_id,
            self._authority_generation,
            self.meeting_id,
            segment_ids,
            speaker_id=speaker_id,
            label=label,
        )

    async def commit_transcript(
        self,
        document: Mapping[str, object],
        *,
        terminal: bool = False,
    ) -> int:
        return await self._store._commit_transcript(
            self._account_id,
            self._authority_generation,
            self.meeting_id,
            document,
            terminal=terminal,
        )

    async def finish(self, status: str, *, failure_code: str | None = None,
                     failure_reason: str | None = None, notice: str | None = None) -> None:
        await self._store._finish_meeting(
            self._account_id,
            self._authority_generation,
            self.meeting_id,
            status, **{key: value for key, value in {"failure_code": failure_code,
                "failure_reason": failure_reason, "notice": notice}.items() if value is not None},
        )

    async def finish_with_transcript(
        self,
        document: Mapping[str, object],
        status: str,
        *, notice: str | None = None,
    ) -> int:
        return await self._store._finish_meeting_with_transcript(
            self._account_id,
            self._authority_generation,
            self.meeting_id,
            document,
            status,
            **({"notice": notice} if notice else {}),
        )

    async def publish_audio(
        self,
        archive: Any,
        source_path: str | Path,
        *,
        partial: bool = False,
        raw_pcm: bool = False,
    ) -> MeetingAudio:
        try:
            if raw_pcm:
                publication = await asyncio.to_thread(
                    archive.publish_live_prefix,
                    self._account_id,
                    self.meeting_id,
                    source_path,
                    partial=partial,
                )
            else:
                publication = await asyncio.to_thread(
                    archive.publish,
                    self._account_id,
                    self.meeting_id,
                    source_path,
                )
        except MeetingAudioCleanupError:
            raise
        except Exception:
            audio = _unavailable_meeting_audio()
            await self._store._commit_meeting_audio(
                self._account_id,
                self._authority_generation,
                self.meeting_id,
                audio,
            )
            return audio

        audio = MeetingAudio(
            state="partial" if partial else "available",
            relative_path=publication.relative_path,
            byte_count=publication.byte_count,
            duration_ms=publication.duration_ms,
            format=publication.format,
            sample_rate_hz=publication.sample_rate_hz,
            channels=publication.channels,
            bit_rate_bps=publication.bit_rate_bps,
        )
        try:
            await self._store._commit_meeting_audio(
                self._account_id,
                self._authority_generation,
                self.meeting_id,
                audio,
            )
        except AccountRevoked:
            try:
                await asyncio.to_thread(archive.discard, publication)
            except Exception:
                pass
            raise
        except Exception:
            try:
                await asyncio.to_thread(archive.discard, publication)
            except MeetingAudioArtifactSurvives:
                await self._store._commit_meeting_audio(
                    self._account_id,
                    self._authority_generation,
                    self.meeting_id,
                    audio,
                )
                return audio
            unavailable = _unavailable_meeting_audio()
            await self._store._commit_meeting_audio(
                self._account_id,
                self._authority_generation,
                self.meeting_id,
                unavailable,
            )
            return unavailable
        except BaseException:
            try:
                await asyncio.to_thread(archive.discard, publication)
            except Exception:
                pass
            raise
        return audio

    async def recover_interrupted_audio(self, archive: Any, stages: Any) -> MeetingAudio:
        """Settle one canonical active Live record without filesystem search or resume."""

        existing = await self.audio()
        if existing is not None and existing.state in {"available", "partial"}:
            await asyncio.to_thread(
                archive.discard_staged,
                self._account_id,
                self.meeting_id,
            )
            if self.resolve_audio(archive, existing) is None:
                await asyncio.to_thread(self.discard_audio, archive, existing)
                await self.mark_audio_unavailable()
                existing = _unavailable_meeting_audio()
            elif existing.state == "available":
                await self._store._downgrade_meeting_audio_to_partial(
                    self._account_id,
                    self._authority_generation,
                    self.meeting_id,
                )
                existing = replace(existing, state="partial")
            await asyncio.to_thread(stages.discard, self._account_id, self.meeting_id)
            return existing
        if existing is not None and existing.state == "unavailable":
            await asyncio.to_thread(
                archive.discard_unrecorded,
                self._account_id,
                self.meeting_id,
            )
            await asyncio.to_thread(stages.discard, self._account_id, self.meeting_id)
            return existing

        await asyncio.to_thread(
            archive.discard_unrecorded,
            self._account_id,
            self.meeting_id,
        )
        prefix = await asyncio.to_thread(
            stages.prefix,
            self._account_id,
            self.meeting_id,
            expected_samples=None,
        )
        if prefix is None:
            recovered = await self.record_audio_unavailable()
        else:
            recovered = await self.publish_audio(
                archive,
                prefix.path,
                partial=True,
                raw_pcm=True,
            )
        await asyncio.to_thread(stages.discard, self._account_id, self.meeting_id)
        return recovered

    async def recover_interrupted_file_audio(self, archive: Any) -> MeetingAudio:
        """Reconcile one active File artifact before an interruption becomes terminal."""

        existing = await self.audio()
        if existing is not None and existing.state in {"available", "partial"}:
            await asyncio.to_thread(
                archive.discard_staged,
                self._account_id,
                self.meeting_id,
            )
            if self.resolve_audio(archive, existing) is None:
                await asyncio.to_thread(self.discard_audio, archive, existing)
                await self.mark_audio_unavailable()
                return _unavailable_meeting_audio()
            if existing.state == "available":
                await self.downgrade_active_audio_to_partial()
                return replace(existing, state="partial")
            return existing

        await asyncio.to_thread(
            archive.discard_unrecorded,
            self._account_id,
            self.meeting_id,
        )
        if existing is not None and existing.state == "unavailable":
            return existing
        return await self.record_audio_unavailable()

    async def record_audio_unavailable(self) -> MeetingAudio:
        audio = _unavailable_meeting_audio()
        await self._store._commit_meeting_audio(
            self._account_id,
            self._authority_generation,
            self.meeting_id,
            audio,
        )
        return audio

    async def audio(self) -> MeetingAudio | None:
        return await self._store._meeting_audio(
            self._account_id,
            self._authority_generation,
            self.meeting_id,
        )

    async def mark_audio_unavailable(self) -> None:
        await self._store._mark_meeting_audio_unavailable(
            self._account_id,
            self._authority_generation,
            self.meeting_id,
        )

    async def downgrade_active_audio_to_partial(self) -> None:
        """Preserve verified bytes while making an active interruption truthful."""

        await self._store._downgrade_meeting_audio_to_partial(
            self._account_id,
            self._authority_generation,
            self.meeting_id,
        )

    async def downgrade_interrupted_audio_to_partial(self) -> bool:
        """System recovery only: reconcile a captured Live row after authority loss."""

        return await self._store._downgrade_interrupted_live_audio_to_partial(
            self._account_id,
            self.meeting_id,
        )

    def resolve_audio(self, archive: Any, audio: MeetingAudio) -> Path | None:
        if audio.relative_path is None or audio.byte_count is None:
            return None
        return archive.resolve(
            self._account_id,
            self.meeting_id,
            audio.relative_path,
            audio.byte_count,
        )

    def discard_audio(self, archive: Any, audio: MeetingAudio) -> None:
        if audio.relative_path is None:
            raise MeetingAudioCleanupError("Meeting audio path is unavailable.")
        archive.discard_stored(
            self._account_id,
            self.meeting_id,
            audio.relative_path,
        )


def create_phase2_app(
    *,
    database_path: str | Path,
    file_runner: Any | None = None,
    file_work_root: str | Path | None = None,
    file_inference_options: Mapping[str, object] | None = None,
    live_runtime_factory: Any | None = None,
    live_helper_lease_seconds: float | None = None,
    url_acquirer: Any | None = None,
    meeting_audio_root: str | Path | None = None,
    file_audio_archive: Any | None = None,
    control_socket_path: str | Path | None = None,
    llm_upstreams: str | None = None,
    open_workspace: bool = False,
    inference_scheduler: Any | None = None,
):
    """Create the sole Phase-2 product surface: `/`, auth, and Account-owned meetings."""

    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import (
            FileResponse,
            HTMLResponse,
            JSONResponse,
            Response,
            StreamingResponse,
        )
    except ImportError as exc:  # pragma: no cover - package dependency is definitive.
        raise RuntimeError("Install FastAPI to run the Phase-2 app.") from exc

    from .phase2_audio import LiveMeetingAudioStages, MeetingAudioArchive
    from .phase2_file import (
        DEFAULT_PHASE2_FILE_WORK_ROOT,
        FileUploadRejected,
        FileUploadTimeout,
        admit_file_upload,
        require_upload_capacity,
    )
    from .phase2_lifecycle import AccountLifecycleUnavailable
    from .phase2_speaker_identity import AccountSpeakerIdentity, SpeakerIdentityNotFound

    resolved_work_root = Path(file_work_root or DEFAULT_PHASE2_FILE_WORK_ROOT).expanduser()
    audio_archive = file_audio_archive or MeetingAudioArchive(
        meeting_audio_root or resolved_work_root.parent / "meetings"
    )
    # The fixed Live stage path remains recoverable even when this process was started
    # without a Live runtime. No capture can reserve this recovery-only instance.
    live_audio_stages = LiveMeetingAudioStages(audio_archive, max_bytes=2)
    file_tasks = None
    if file_runner is not None:
        from .phase2_file import FileMeetingTasks
        from .phase2_url import UrlMediaAcquirer

        file_tasks = FileMeetingTasks(
            file_runner,
            resolved_work_root,
            **dict(file_inference_options or {}),
            url_acquirer=url_acquirer or UrlMediaAcquirer(),
            audio_archive=audio_archive,
            inference_scheduler=inference_scheduler,
        )

    phase2_live = None
    if live_runtime_factory is not None:
        if live_helper_lease_seconds is None or live_helper_lease_seconds <= 0:
            raise ValueError(
                "live_helper_lease_seconds must be positive when Live mode is enabled."
            )
        from .phase2_live import Phase2LiveMeetings

        live_runtime = live_runtime_factory()
        max_tape_bytes = live_runtime.descriptor.bounds.max_tape_bytes
        if max_tape_bytes is None:
            raise ValueError("Phase-2 Live audio requires bounds_config.max_tape_bytes.")
        live_audio_stages = LiveMeetingAudioStages(
            audio_archive,
            max_bytes=max_tape_bytes,
        )
        phase2_live = Phase2LiveMeetings(
            live_runtime,
            audio_archive=audio_archive,
            audio_stages=live_audio_stages,
        )
    elif live_helper_lease_seconds is not None:
        raise ValueError("live_runtime_factory is required when a Live helper lease is set.")

    live_control = None

    @asynccontextmanager
    async def lifespan(app: Any) -> AsyncIterator[None]:
        store = await Phase2Store.open(database_path)
        control_server = None
        operator_status = None
        lifecycle = None
        speaker_identity = None
        try:
            await store.recover_active_meetings(
                audio_archive=audio_archive,
                live_audio_stages=live_audio_stages,
            )
            from .phase2_summary import recover_summaries
            await recover_summaries(store)
            if file_tasks is not None:
                file_tasks.clear_transient_work()
            app.state.phase2_store = store
            app.state.phase2_file_tasks = file_tasks
            app.state.phase2_audio_archive = audio_archive
            speaker_identity = AccountSpeakerIdentity(
                store, phase2_live,
                file_evidence=getattr(getattr(file_runner, "identity_resolver", None),
                                      "enrollment_observation", None),
                audio_archive=audio_archive,
            )
            app.state.phase2_speaker_identity = speaker_identity
            if phase2_live is not None:
                phase2_live.bind_speaker_identity(speaker_identity)
            from .phase2_lifecycle import AccountLifecycle

            lifecycle = AccountLifecycle(
                store,
                live=phase2_live,
                files=file_tasks,
                audio_archive=audio_archive,
                live_audio_stages=live_audio_stages,
            )
            if live_control is not None:
                lifecycle.bind_live_control(live_control)
            app.state.phase2_lifecycle = lifecycle
            if phase2_live is not None:
                phase2_live.start()
            if control_socket_path is not None:
                from .phase2_control import Phase2ControlServer
                from .phase2_operator import Phase2OperatorStatus

                operator_status = Phase2OperatorStatus(
                    store,
                    database_path=database_path,
                    audio_root=audio_archive.root,
                    live=phase2_live,
                    files=file_tasks,
                    v2_sessions=getattr(app.state, "live_v2_sessions", None),
                    helper_presence=getattr(app.state, "live_helper_presence", None),
                    capture_observations=getattr(
                        app.state,
                        "live_capture_observations",
                        None,
                    ),
                )
                await operator_status.start()
                app.state.phase2_operator_status = operator_status
                control_server = Phase2ControlServer(
                    control_socket_path,
                    lifecycle,
                    operator_status,
                )
                await control_server.start()
                app.state.phase2_control = control_server
            yield
        finally:
            try:
                if control_server is not None:
                    await control_server.stop()
                if speaker_identity is not None:
                    await speaker_identity.shutdown()
                if lifecycle is not None:
                    await lifecycle.shutdown()
                try:
                    if phase2_live is not None:
                        try:
                            await phase2_live.shutdown()
                        finally:
                            if speaker_identity is not None:
                                phase2_live.unbind_speaker_identity(speaker_identity)
                    if file_tasks is not None:
                        await file_tasks.stop()
                finally:
                    if operator_status is not None:
                        await operator_status.stop()
            finally:
                await store.close()

    app = FastAPI(
        title="MOSS",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    from ..installed_candidate import installed_candidate_identity

    packaged_candidate = installed_candidate_identity()
    if packaged_candidate is not None:
        @app.middleware("http")
        async def report_packaged_candidate(request: Any, call_next: Any):
            response = await call_next(request)
            response.headers["X-MOSS-Candidate-SHA"] = packaged_candidate["git_sha"]
            return response
    @app.middleware("http")
    async def workspace_request_boundary(request: Request, call_next: Any):
        # Browser writes must originate here. Cookie possession remains the owner
        # authority; this also prevents cross-site creation of unwanted workspaces.
        origin = request.headers.get("origin")
        expected_origin = f"{request.url.scheme}://{request.url.netloc}"
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin is not None and origin != expected_origin:
            return JSONResponse({"detail": "Same-origin request required."}, status_code=403)
        if open_workspace:
            account, session_id = await request.app.state.phase2_store.bootstrap_browser(
                request.cookies.get(SESSION_COOKIE),
                open_workspace=True,
            )
            request.state.phase2_account = account
            request.state.phase2_session_id = session_id
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if open_workspace:
            set_session_cookie(response, request.state.phase2_session_id)
        return response
    frontend_dir = FRONTEND_ASSET_DIR
    required_live_assets = ("app.js", "styles.css", "worklets/lane-framer.js")
    invalid_live_assets = (
        tuple(
            relative
            for relative in required_live_assets
            if not (frontend_dir / relative).is_file()
            or (frontend_dir / relative).stat().st_size == 0
        )
        if phase2_live is not None
        else ()
    )
    if invalid_live_assets:
        raise RuntimeError(
            "Live Account frontend assets are missing or empty: "
            + ", ".join(invalid_live_assets)
        )
    live_frontend_available = phase2_live is not None
    static_assets = frozenset(
        {
            "app.js",
            "styles.css",
            "logo-mark.svg",
            "worklets/lane-framer.js",
            "fonts/Fraunces-600.woff2",
            "fonts/Fraunces-700.woff2",
            "fonts/IBMPlexMono-400.woff2",
            "fonts/IBMPlexMono-500.woff2",
            "fonts/Inter-400.woff2",
            "fonts/Inter-500.woff2",
            "fonts/Inter-600.woff2",
            "fonts/Inter-700.woff2",
            "fonts/SourceSerif4-400.woff2",
            "fonts/SourceSerif4-500.woff2",
            "fonts/SourceSerif4-600.woff2",
        }
    )

    @app.get("/static/{asset_path:path}", include_in_schema=False)
    async def static_asset(asset_path: str):
        if asset_path not in static_assets:
            raise HTTPException(status_code=404, detail="Asset not found.")
        path = frontend_dir / asset_path
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Asset not found.")
        return FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})

    @app.exception_handler(AccountRevoked)
    async def account_revoked(_: Request, __: AccountRevoked):
        return JSONResponse({"detail": "Workspace credential is unavailable."}, status_code=401)

    @app.exception_handler(AccountLifecycleUnavailable)
    async def account_lifecycle_unavailable(_: Request, __: AccountLifecycleUnavailable):
        return JSONResponse({"detail": "Account lifecycle is changing."}, status_code=409)

    async def require_account(request: Request) -> Account:
        account = getattr(request.state, "phase2_account", None)
        if account is None:
            account = await request.app.state.phase2_store.account_for_session(
                request.cookies.get(SESSION_COOKIE)
            )
        if account is None:
            raise HTTPException(status_code=401, detail="Workspace credential is unavailable.")
        return account

    def set_session_cookie(response: Response, session_id: str) -> Response:
        response.set_cookie(
            SESSION_COOKIE,
            session_id,
            max_age=SESSION_COOKIE_MAX_AGE,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
        return response

    def request_session_id(request: Request) -> str | None:
        return getattr(request.state, "phase2_session_id", None) or request.cookies.get(
            SESSION_COOKIE
        )

    from .phase2_summary import attach_summary_routes
    attach_summary_routes(app, require_account)
    from .phase2_llm import attach_llm_routes
    attach_llm_routes(app, require_account, llm_upstreams)

    if phase2_live is not None:
        from .phase2_live import attach_phase2_live_routes

        live_control = attach_phase2_live_routes(
            app,
            phase2_live,
            require_account=require_account,
            live_helper_lease_seconds=float(live_helper_lease_seconds),
        )

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        account = getattr(request.state, "phase2_account", None)
        if account is None:
            account = await request.app.state.phase2_store.account_for_session(
                request.cookies.get(SESSION_COOKIE)
            )
        if account is None:
            return HTMLResponse(
                _bootstrap_html(unavailable=bool(request.cookies.get(SESSION_COOKIE))),
                headers={"Cache-Control": "no-store"},
            )
        workspace = request.app.state.phase2_store.workspace(account)
        meetings = await workspace.list_meetings()
        response = HTMLResponse(
            _workspace_html(account, meetings, live_enabled=live_frontend_available),
            headers={"Cache-Control": "no-store"},
        )
        if open_workspace:
            return response
        return set_session_cookie(response, request.cookies[SESSION_COOKIE])

    @app.post("/api/workspace/bootstrap")
    async def bootstrap_workspace(request: Request):
        account, session_id = await request.app.state.phase2_store.bootstrap_browser(
            request.cookies.get(SESSION_COOKIE),
            open_workspace=open_workspace,
        )
        response = JSONResponse(
            {"workspace_id": account.account_id, "display_name": account.display_name}
        )
        if open_workspace:
            return response
        return set_session_cookie(response, session_id)

    @app.get("/api/auth/session")
    async def auth_session(request: Request):
        account = await require_account(request)
        response = JSONResponse({"workspace_id": account.account_id, "display_name": account.display_name})
        if open_workspace:
            return response
        return set_session_cookie(response, request.cookies[SESSION_COOKIE])

    @app.get("/api/meetings")
    async def list_meetings(request: Request):
        account = await require_account(request)
        workspace = request.app.state.phase2_store.workspace(account)
        meetings = await workspace.list_meetings()
        return {"meetings": [meeting.to_dict() for meeting in meetings]}

    @app.post("/api/meetings/file/admission", status_code=204)
    async def preflight_file_meeting(request: Request):
        await require_account(request)
        tasks = request.app.state.phase2_file_tasks
        if tasks is None:
            raise HTTPException(status_code=503, detail="File transcription is unavailable.")
        try:
            payload = await request.json()
        except ValueError:
            raise HTTPException(status_code=400, detail="File size must be a nonnegative integer.") from None
        size = payload.get("file_bytes") if isinstance(payload, dict) else None
        if type(size) is not int or size < 0:
            raise HTTPException(status_code=400, detail="File size must be a nonnegative integer.")
        try:
            # File.size is a lower bound: multipart overhead is checked by actual
            # upload admission again. This does not reserve storage or create work.
            require_upload_capacity(size, tasks.work_root)
        except FileUploadRejected as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.post("/api/meetings/file", status_code=201)
    async def create_file_meeting(request: Request):
        if request.app.state.phase2_file_tasks is None:
            raise HTTPException(status_code=503, detail="File transcription is unavailable.")
        try:
            session_id = request_session_id(request)
            async with request.app.state.phase2_lifecycle.admit_creation(
                session_id or "",
            ) as account:
                file_tasks = request.app.state.phase2_file_tasks
                admit_file_upload(request, file_tasks.work_root)
                form = await request.form()
                upload = form.get("file")
                if upload is None or not hasattr(upload, "read"):
                    raise ValueError("Missing upload file.")
                handle = await file_tasks.accept(
                    request.app.state.phase2_store.workspace(account),
                    upload,
                )
            return (await handle.snapshot()).to_dict()
        except FileUploadRejected as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except FileUploadTimeout as exc:
            raise HTTPException(status_code=408, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except AccountRevoked:
            raise
        except AccountLifecycleUnavailable:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Upload could not be accepted.") from exc

    @app.post("/api/meetings/url", status_code=201)
    async def create_url_meeting(request: Request):
        if request.app.state.phase2_file_tasks is None:
            raise HTTPException(status_code=503, detail="File transcription is unavailable.")
        try:
            session_id = request_session_id(request)
            async with request.app.state.phase2_lifecycle.admit_creation(
                session_id or "",
            ) as account:
                payload = await request.json()
                source_url = payload.get("url") if isinstance(payload, dict) else None
                if not isinstance(source_url, str):
                    raise ValueError("Missing media URL.")
                handle = await request.app.state.phase2_file_tasks.accept_url(
                    request.app.state.phase2_store.workspace(account),
                    source_url,
                )
            return (await handle.snapshot()).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except AccountRevoked:
            raise
        except AccountLifecycleUnavailable:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="URL could not be accepted.") from exc

    @app.get("/api/meetings/{meeting_id}")
    async def open_meeting(meeting_id: str, request: Request):
        account = await require_account(request)
        handle = await request.app.state.phase2_store.workspace(account).open_meeting(meeting_id)
        if handle is None:
            raise HTTPException(status_code=404, detail="Meeting not found.")
        return (await handle.snapshot()).to_dict()

    @app.put("/api/meetings/{meeting_id}/title")
    async def rename_meeting(meeting_id: str, request: Request):
        account = await require_account(request)
        handle = await request.app.state.phase2_store.workspace(account).open_meeting(meeting_id)
        if handle is None:
            raise HTTPException(status_code=404, detail="Meeting not found.")
        try:
            payload = await request.json()
            title = payload.get("title") if isinstance(payload, dict) else None
            if not isinstance(title, str):
                raise ValueError("Meeting title is required.")
            normalized = await handle.rename(title)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"id": meeting_id, "title": normalized, "title_source": "manual"}

    @app.put("/api/meetings/{meeting_id}/speakers/{speaker_id}/name")
    async def name_meeting_speaker(
        meeting_id: str,
        speaker_id: str,
        request: Request,
    ):
        account = await require_account(request)
        workspace = request.app.state.phase2_store.workspace(account)
        handle = await workspace.open_meeting(meeting_id)
        if handle is None:
            raise HTTPException(status_code=404, detail="Meeting Speaker not found.")
        try:
            payload = await request.json()
            label = payload.get("label") if isinstance(payload, dict) else None
            if not isinstance(label, str):
                raise ValueError("Speaker label is required.")
            save_voiceprint = payload.get("save_voiceprint", True)
            if not isinstance(save_voiceprint, bool):
                raise ValueError("save_voiceprint must be a boolean.")
            result = await request.app.state.phase2_speaker_identity.bank(
                workspace
            ).name_speaker(handle, speaker_id, label, save_voiceprint=save_voiceprint)
        except SpeakerIdentityNotFound as exc:
            raise HTTPException(status_code=404, detail="Meeting Speaker not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result.to_dict()

    @app.put("/api/meetings/{meeting_id}/passages/speaker")
    async def reassign_meeting_passages(meeting_id: str, request: Request):
        account = await require_account(request)
        handle = await request.app.state.phase2_store.workspace(account).open_meeting(meeting_id)
        if handle is None:
            raise HTTPException(status_code=404, detail="Meeting not found.")
        try:
            payload = await request.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("segment_ids"), list):
                raise ValueError("Passage selection is required.")
            raw_segment_ids = payload["segment_ids"]
            if not all(isinstance(value, str) for value in raw_segment_ids):
                raise ValueError("Passage selection is invalid.")
            speaker_id = payload.get("speaker_id")
            label = payload.get("label")
            if speaker_id is not None and not isinstance(speaker_id, str):
                raise ValueError("Existing speaker is invalid.")
            if label is not None and not isinstance(label, str):
                raise ValueError("New person name is invalid.")
            result = await handle.reassign_passages(
                tuple(raw_segment_ids), speaker_id=speaker_id, label=label
            )
        except MeetingNotSettled as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PassageNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
        except AccountRevoked as exc:
            raise HTTPException(status_code=404, detail="Meeting not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result.to_dict()

    @app.get("/api/voiceprints")
    async def list_voiceprints(request: Request):
        account = await require_account(request)
        workspace = request.app.state.phase2_store.workspace(account)
        voiceprints = await request.app.state.phase2_speaker_identity.bank(
            workspace
        ).list_voiceprints()
        return {"voiceprints": [voiceprint.to_dict() for voiceprint in voiceprints]}

    @app.put("/api/voiceprints/{voiceprint_id}/name")
    async def rename_voiceprint(voiceprint_id: str, request: Request):
        account = await require_account(request)
        bank = request.app.state.phase2_speaker_identity.bank(request.app.state.phase2_store.workspace(account))
        try:
            payload = await request.json()
            label = payload.get("label") if isinstance(payload, dict) else None
            if not isinstance(label, str):
                raise ValueError("Voiceprint label is required.")
            return await bank.rename_voiceprint(voiceprint_id, label)
        except SpeakerIdentityNotFound as exc:
            raise HTTPException(status_code=404, detail="Voiceprint not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/voiceprints/{voiceprint_id}")
    async def delete_voiceprint(voiceprint_id: str, request: Request):
        account = await require_account(request)
        bank = request.app.state.phase2_speaker_identity.bank(request.app.state.phase2_store.workspace(account))
        try:
            return await bank.delete_voiceprint(voiceprint_id)
        except SpeakerIdentityNotFound as exc:
            raise HTTPException(status_code=404, detail="Voiceprint not found.") from exc

    @app.get("/api/meetings/{meeting_id}/audio/download")
    async def download_meeting_audio(meeting_id: str, request: Request):
        account = await require_account(request)
        handle = await request.app.state.phase2_store.workspace(account).open_meeting(meeting_id)
        if handle is None:
            raise HTTPException(status_code=404, detail="Meeting not found.")
        audio = await handle.audio()
        if audio is None or audio.state not in {"available", "partial"}:
            raise HTTPException(status_code=404, detail="Meeting audio is unavailable.")
        archive = request.app.state.phase2_audio_archive
        path = handle.resolve_audio(archive, audio)
        if path is None:
            try:
                await asyncio.to_thread(handle.discard_audio, archive, audio)
            except MeetingAudioCleanupError:
                raise HTTPException(
                    status_code=503,
                    detail="Meeting audio cannot be reconciled safely.",
                ) from None
            await handle.mark_audio_unavailable()
            raise HTTPException(status_code=404, detail="Meeting audio is unavailable.")

        def whole_file():
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    yield chunk

        suffix = ".partial.mp3" if audio.state == "partial" else ".mp3"
        return StreamingResponse(
            whole_file(),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="meeting-{meeting_id}{suffix}"'
                ),
                "Content-Length": str(audio.byte_count),
                "Cache-Control": "private, no-store",
            },
        )

    return app


def _now_ms() -> int:
    return int(time.time() * 1000)


def _is_unknown_speaker_value(value: object) -> bool:
    """Normalize and identify the product's reserved uncertainty vocabulary."""

    normalized = " ".join(value.split()).casefold() if isinstance(value, str) else ""
    if normalized in {"", "s00", "unknown", "speaker uncertain", "preview"}:
        return True
    prefix = "speaker_"
    return normalized.startswith(prefix) and normalized.removeprefix(prefix).isdigit()


def _segment_speaker_id(segment: Mapping[str, object]) -> str | None:
    entity = segment.get("speaker_entity_id")
    if isinstance(entity, str) and entity.strip():
        normalized = entity.strip()
        return None if _is_unknown_speaker_value(normalized) else normalized
    speaker = segment.get("speaker")
    if isinstance(speaker, str) and speaker.strip():
        normalized = speaker.strip()
        return None if _is_unknown_speaker_value(normalized) else normalized
    return None


def _settled_transcript(document: dict[str, object]) -> dict[str, object]:
    for segment in document.get("segments", []):
        if not isinstance(segment, dict):
            continue
        # Storage tests and interrupted imports may retain a non-renderable record with no
        # speaker field at all. It is not a passage whose identity can be presented or edited.
        if "speaker" not in segment:
            continue
        if _segment_speaker_id(segment) is None:
            segment["speaker_entity_id"] = "S00"
            segment["speaker"] = "Speaker uncertain"
    return document


def _meeting_needs_review(
    status: str,
    document: Mapping[str, object] | None,
    failure_code: str | None,
    notice: str | None,
) -> bool:
    if status == "active":
        return False
    if status != "completed" or failure_code or notice:
        return True
    if document is None:
        return False
    return any(
        isinstance(segment, dict) and _segment_speaker_id(segment) is None
        for segment in document.get("segments", [])
    )


def _meeting_from_row(row: Any) -> Meeting:
    document_json = row["document_json"]
    status = str(row["status"])
    transcript = None if document_json is None else json.loads(document_json)
    needs_review = _meeting_needs_review(
        status, transcript, row["failure_code"], row["notice"]
    )
    if transcript is not None and status != "active":
        transcript = _settled_transcript(transcript)
    return Meeting(
        meeting_id=row["meeting_id"],
        mode=row["mode"],
        title=row["title"],
        status=status,
        created_at_ms=int(row["created_at_ms"]),
        title_source=row["title_source"],
        transcript=transcript,
        transcript_version=0 if row["transcript_version"] is None else int(row["transcript_version"]),
        audio=_meeting_audio_from_row(row),
        failure_code=row["failure_code"], failure_reason=row["failure_reason"], notice=row["notice"],
        needs_review=needs_review,
    )


def _meeting_audio_from_row(row: Any) -> MeetingAudio | None:
    state = row["audio_state"]
    if state is None:
        return None
    return MeetingAudio(
        state=state,
        relative_path=row["audio_relative_path"],
        byte_count=None if row["audio_byte_count"] is None else int(row["audio_byte_count"]),
        duration_ms=(
            None if row["audio_duration_ms"] is None else int(row["audio_duration_ms"])
        ),
        format=row["audio_format"],
        sample_rate_hz=(
            None
            if row["audio_sample_rate_hz"] is None
            else int(row["audio_sample_rate_hz"])
        ),
        channels=None if row["audio_channels"] is None else int(row["audio_channels"]),
        bit_rate_bps=(
            None if row["audio_bit_rate_bps"] is None else int(row["audio_bit_rate_bps"])
        ),
    )


def _bootstrap_html(*, unavailable: bool) -> str:
    message = (
        "Workspace unavailable. Existing work has not been reassigned. Contact the operator."
        if unavailable else "Opening this browser's workspace…"
    )
    script = "" if unavailable else """
<script>
const status = document.querySelector('[data-workspace-status]');
(async () => {
  if (!navigator.locks) throw new Error('Use Chrome with trusted HTTPS to open this workspace.');
  await navigator.locks.request('moss-workspace-bootstrap', async () => {
    const current = await fetch('/api/auth/session', {cache: 'no-store'});
    if (current.status === 401) {
      const created = await fetch('/api/workspace/bootstrap', {method: 'POST'});
      if (!created.ok) throw new Error('Workspace unavailable. Contact the operator.');
      const verified = await fetch('/api/auth/session', {cache: 'no-store'});
      if (!verified.ok) throw new Error('Allow cookies for this site, then reload.');
    } else if (!current.ok) {
      throw new Error('Workspace unavailable. Reload when the server is ready.');
    }
  });
  location.replace('/');
})().catch(error => { status.textContent = error.message; });
</script>"""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MOSS</title></head>
<body><main data-auth-state="bootstrap"><h1>MOSS</h1><p data-workspace-status>{message}</p>
<p>History belongs to this browser profile. Clearing site data loses automatic access.</p>
<noscript>Enable JavaScript to open this browser's workspace.</noscript></main>{script}</body></html>"""


def _workspace_html(
    account: Account,
    meetings: list[Meeting],
    *,
    live_enabled: bool = False,
) -> str:
    history = "".join(_meeting_history_card(meeting) for meeting in meetings)
    empty = "<p data-history=\"empty\">No meetings yet.</p>" if not meetings else ""
    styles_url = _frontend_asset_url("styles.css")
    app_url = _frontend_asset_url("app.js")
    worklet_head = (
        f'<meta name="moss-worklet-url" content="{_frontend_asset_url("worklets/lane-framer.js")}">'
        if live_enabled
        else ""
    )
    live_head = (
        '<meta name="moss-authority" content="account">'
        f'{worklet_head}'
        f'<link rel="stylesheet" href="{styles_url}">'
    )
    live_body = (
        '<section id="workspace-live" data-workspace-section="live" data-live-capture="account">'
        '<h2 class="phase2-workspace-heading">Live transcription</h2><div id="app"></div></section>'
        if live_enabled
        else ""
    )
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>MOSS</title>{live_head}</head>
<body class=\"phase2-workspace\"><main data-auth-state=\"signed-in\"><header><span data-workspace-name>{html.escape(account.display_name)}</span>
<small style="color: var(--muted)">History stays with this browser profile. Clearing site data loses automatic access.</small></header>
<nav class="workspace-nav" aria-label="Workspace">
<a href="#workspace-file">Files &amp; URLs</a>
{('<a href="#workspace-live">Live / Transcript &amp; export</a>' if live_enabled else '')}
<a href="#workspace-history">Meeting history</a><a href="#workspace-voiceprints">Voiceprints</a>
</nav>
<section data-workspace=\"account\"><h1>Your meetings</h1>
<section id=\"workspace-file\" data-workspace-section=\"file\"><h2 class=\"phase2-workspace-heading\">File transcription</h2>
<form data-file-upload=\"form\" class="control-section" style="max-width: 680px; gap: 16px"><label class="field"><span class="field-label">Audio or video files</span><input name=\"file\" type=\"file\" multiple></label>
<label class="field"><span class="field-label">Media URLs, one per line</span><textarea name=\"urls\"></textarea></label>
<button type=\"submit\" class="btn btn-primary" style="align-self: flex-start">Transcribe files and URLs</button></form><p data-file-upload=\"status\" role=\"status\"></p><ul data-file-upload=\"results\"></ul></section>
{live_body}
<section id=\"workspace-history\" data-workspace-section=\"history\"><h2 class=\"phase2-workspace-heading\">Meeting history</h2>
<div id=\"meeting-history-app\" data-history-root>{empty}{history}</div>
<section id="workspace-voiceprints" data-workspace-section="voiceprints"><h2 class="phase2-workspace-heading">Private voice bank</h2><div id="voiceprint-bank-app"></div></section></section>
</section></main>
<script type="module" src="{app_url}"></script>
</body></html>"""


def _meeting_history_card(meeting: Meeting) -> str:
    meeting_id = html.escape(meeting.meeting_id)
    if meeting.audio is not None and meeting.audio.state in {"available", "partial"}:
        label = "Download partial audio" if meeting.audio.state == "partial" else "Download audio"
        audio_action = (
            f'<a data-audio-download href="/api/meetings/{meeting_id}/audio/download">{label}</a>'
        )
    elif meeting.audio is not None and meeting.audio.state == "unavailable":
        audio_action = "<span data-audio-unavailable>Audio unavailable</span>"
    else:
        audio_action = ""
    title = html.escape(meeting.title or meeting.mode.title() + " meeting")
    return (
        f'<article data-meeting-card><button type="button" data-open-meeting="{meeting_id}">'
        f"{title} — {html.escape(meeting.status)}</button>{audio_action}</article>"
    )
