"""The small Phase-2 ownership and sign-in foundation.

Phase 1's global JobManager is deliberately not imported here.  This module starts with
the only authority Phase 2 permits: a verified Google identity opens one AccountWorkspace.
"""

from __future__ import annotations

import asyncio
import html
import json
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Mapping, Protocol

from starlette.requests import Request

from .phase2_audio import MeetingAudioArtifactSurvives, MeetingAudioCleanupError


SCHEMA_VERSION = 1
OAUTH_COOKIE = "__Host-moss_oauth"
SESSION_COOKIE = "__Host-moss_session"
OAUTH_COOKIE_MAX_AGE = 10 * 60
SESSION_COOKIE_MAX_AGE = 400 * 24 * 60 * 60
GOOGLE_CALLBACK_URL = "https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861/auth/google/callback"
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
DEFAULT_PHASE2_DATABASE_PATH = (
    Path.home() / ".local" / "share" / "moss-transcribe-diarize" / "phase2.sqlite3"
)


class SchemaVersionError(RuntimeError):
    """The greenfield database exists but is not the one schema this product accepts."""


class GoogleOidcRejected(ValueError):
    """Google/Authlib rejected the temporary authorization transaction."""


class AccountRevoked(PermissionError):
    """An Account lost authority before an owner-bound mutation committed."""


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    account_id: str
    email: str
    display_name: str


@dataclass(frozen=True, slots=True)
class Account:
    account_id: str
    email: str
    display_name: str
    authority_generation: int


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
        }


class GoogleOidc(Protocol):
    async def begin(self, request: Any) -> Any: ...

    async def complete(self, request: Any) -> GoogleIdentity: ...


class AuthlibGoogleOidc:
    """Authlib's OIDC verifier, kept at the one external-identity boundary.

    Authlib persists state, nonce, and the generated S256 code verifier in the signed
    temporary Starlette session.  The token returned by Google stays local to ``complete``;
    only the verified identity below crosses into MOSS persistence.
    """

    def __init__(
        self,
        *,
        remote: Any,
        callback_url: str = GOOGLE_CALLBACK_URL,
        client_id: str | None = None,
    ):
        self._remote = remote
        self._callback_url = callback_url
        self._client_id = client_id if client_id is not None else remote.client_id

    @classmethod
    def configured(
        cls,
        *,
        client_id: str,
        client_secret: str,
        callback_url: str = GOOGLE_CALLBACK_URL,
    ) -> "AuthlibGoogleOidc":
        try:
            from authlib.integrations.starlette_client import OAuth
        except ImportError as exc:  # pragma: no cover - package dependency is definitive.
            raise RuntimeError("Install Authlib 1.7.2 to enable Google sign-in.") from exc

        oauth = OAuth()
        oauth.register(
            name="google",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=GOOGLE_DISCOVERY_URL,
            client_kwargs={
                "scope": "openid profile email",
                "code_challenge_method": "S256",
            },
        )
        return cls(
            remote=oauth.create_client("google"),
            callback_url=callback_url,
            client_id=client_id,
        )

    async def begin(self, request: Any) -> Any:
        return await self._remote.authorize_redirect(
            request,
            self._callback_url,
            prompt="select_account",
            access_type="online",
        )

    async def complete(self, request: Any) -> GoogleIdentity:
        try:
            token = await self._remote.authorize_access_token(
                request,
                leeway=0,
                claims_options={
                    "iss": {"values": list(GOOGLE_ISSUERS)},
                    "aud": {"value": self._client_id},
                },
            )
            claims = token["userinfo"]
        except Exception as exc:  # Authlib raises provider-specific OAuth/JWT errors.
            raise GoogleOidcRejected("Google could not verify this sign-in.") from exc

        if not isinstance(claims, Mapping):
            raise GoogleOidcRejected("Google returned no verified identity.")
        account_id = claims.get("sub")
        email = claims.get("email")
        display_name = claims.get("name")
        if not isinstance(account_id, str) or not account_id.strip():
            raise GoogleOidcRejected("Google returned no verified subject.")
        if not isinstance(email, str) or not normalize_email(email):
            raise GoogleOidcRejected("Google returned no email.")
        if claims.get("email_verified") is not True:
            raise GoogleOidcRejected("Google email is not verified.")
        return GoogleIdentity(
            account_id=account_id,
            email=normalize_email(email),
            display_name=display_name if isinstance(display_name, str) else "",
        )


def normalize_email(value: str) -> str:
    """The exact-email policy's only normalization; aliases deliberately remain distinct."""

    return value.strip().lower()


class Phase2Store:
    """One SQLite connection hidden behind AccountWorkspace ownership operations."""

    def __init__(self, connection: Any):
        self._connection = connection
        self._write_lock = asyncio.Lock()

    @classmethod
    async def open(cls, database_path: str | Path) -> "Phase2Store":
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
            # journal modes before proving that this file is schema v1: WAL setup itself mutates
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
            CREATE TABLE account_allowlist (
                email TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
                bound_account_id TEXT,
                created_at_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL
            );
            CREATE TABLE accounts (
                account_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
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
            PRAGMA user_version = 1;
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

    async def allow_email(self, email: str) -> None:
        normalized = _required_email(email)
        now = _now_ms()
        async with self._mutation():
            await self._connection.execute(
                """
                INSERT INTO account_allowlist(email, enabled, bound_account_id, created_at_ms, updated_at_ms)
                VALUES (?, 1, NULL, ?, ?)
                ON CONFLICT(email) DO UPDATE SET enabled = 1, updated_at_ms = excluded.updated_at_ms
                """,
                (normalized, now, now),
            )

    async def list_allowlist(self) -> list[dict[str, object]]:
        async with self._external_read():
            cursor = await self._connection.execute(
                "SELECT email, enabled FROM account_allowlist ORDER BY email"
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return [{"email": row["email"], "enabled": bool(row["enabled"])} for row in rows]

    async def revoke_email(self, email: str) -> bool:
        normalized = _required_email(email)
        now = _now_ms()
        async with self._mutation():
            cursor = await self._connection.execute(
                "SELECT bound_account_id FROM account_allowlist WHERE email = ?", (normalized,)
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row is None:
                return False
            account_id = row["bound_account_id"]
            if account_id is not None:
                # An Account may have changed email after more than one allowed callback.  A
                # revoke is Account authority, so another already-bound email cannot restore it.
                await self._connection.execute(
                    """
                    UPDATE account_allowlist SET enabled = 0, updated_at_ms = ?
                    WHERE bound_account_id = ?
                    """,
                    (now, account_id),
                )
                await self._connection.execute(
                    """
                    UPDATE accounts
                    SET enabled = 0,
                        authority_generation = authority_generation + 1,
                        updated_at_ms = ?
                    WHERE account_id = ?
                    """,
                    (now, account_id),
                )
                await self._connection.execute(
                    "DELETE FROM sign_in_sessions WHERE account_id = ?", (account_id,)
                )
                await self._connection.execute(
                    """
                    UPDATE meetings SET status = 'interrupted', updated_at_ms = ?
                    WHERE account_id = ? AND status = 'active'
                    """,
                    (now, account_id),
                )
            else:
                await self._connection.execute(
                    "UPDATE account_allowlist SET enabled = 0, updated_at_ms = ? WHERE email = ?",
                    (now, normalized),
                )
            return True

    async def recover_active_meetings(
        self,
        *,
        audio_archive: Any | None = None,
        live_audio_stages: Any | None = None,
    ) -> None:
        """The product process never resumes capture that was active before startup."""

        if (audio_archive is None) != (live_audio_stages is None):
            raise ValueError("Live audio startup recovery requires archive and stages together.")
        if audio_archive is not None:
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
            for row in interrupted_rows:
                if row["audio_state"] in {"available", "partial"}:
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
                    ORDER BY m.created_at_ms, m.meeting_id
                    """
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

        now = _now_ms()
        async with self._mutation():
            await self._connection.execute(
                "UPDATE meetings SET status = 'interrupted', updated_at_ms = ? WHERE status = 'active'",
                (now,),
            )

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

    async def admit(self, identity: GoogleIdentity) -> tuple[Account, str] | None:
        """Atomically bind an allowed verified subject and issue its opaque MOSS session."""

        email = _required_email(identity.email)
        account_id = identity.account_id.strip()
        if not account_id:
            raise ValueError("Google subject is required.")
        now = _now_ms()
        async with self._mutation():
            cursor = await self._connection.execute(
                "SELECT enabled, bound_account_id FROM account_allowlist WHERE email = ?", (email,)
            )
            allowlist = await cursor.fetchone()
            await cursor.close()
            if allowlist is None or not bool(allowlist["enabled"]):
                return None
            bound_account_id = allowlist["bound_account_id"]
            if bound_account_id is not None and bound_account_id != account_id:
                return None

            cursor = await self._connection.execute(
                "SELECT account_id FROM accounts WHERE email = ?", (email,)
            )
            email_owner = await cursor.fetchone()
            await cursor.close()
            if email_owner is not None and email_owner["account_id"] != account_id:
                return None

            cursor = await self._connection.execute(
                "SELECT account_id, authority_generation FROM accounts WHERE account_id = ?",
                (account_id,),
            )
            account_row = await cursor.fetchone()
            await cursor.close()
            if account_row is None:
                authority_generation = 0
                await self._connection.execute(
                    """
                    INSERT INTO accounts(
                        account_id, email, display_name, enabled, authority_generation,
                        created_at_ms, updated_at_ms
                    )
                    VALUES (?, ?, ?, 1, ?, ?, ?)
                    """,
                    (account_id, email, identity.display_name, authority_generation, now, now),
                )
            else:
                authority_generation = int(account_row["authority_generation"])
                await self._connection.execute(
                    """
                    UPDATE accounts SET email = ?, display_name = ?, enabled = 1, updated_at_ms = ?
                    WHERE account_id = ?
                    """,
                    (email, identity.display_name, now, account_id),
                )
            if bound_account_id is None:
                await self._connection.execute(
                    "UPDATE account_allowlist SET bound_account_id = ?, updated_at_ms = ? WHERE email = ?",
                    (account_id, now, email),
                )
            session_id = secrets.token_urlsafe(32)
            await self._connection.execute(
                "INSERT INTO sign_in_sessions(session_id, account_id, created_at_ms) VALUES (?, ?, ?)",
                (session_id, account_id, now),
            )
            return Account(
                account_id=account_id,
                email=email,
                display_name=identity.display_name,
                authority_generation=authority_generation,
            ), session_id

    async def account_for_session(self, session_id: str | None) -> Account | None:
        if not session_id:
            return None
        async with self._external_read():
            cursor = await self._connection.execute(
                """
                SELECT a.account_id, a.email, a.display_name, a.authority_generation
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
            email=row["email"],
            display_name=row["display_name"],
            authority_generation=int(row["authority_generation"]),
        )

    async def revoke_session(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        async with self._mutation():
            cursor = await self._connection.execute(
                "DELETE FROM sign_in_sessions WHERE session_id = ?", (session_id,)
            )
            return cursor.rowcount == 1

    def workspace(self, account: Account) -> "AccountWorkspace":
        return AccountWorkspace(self, account)

    async def _list_meetings(self, account_id: str, authority_generation: int) -> list[Meeting]:
        async with self._external_read():
            cursor = await self._connection.execute(
                """
                SELECT m.meeting_id, m.mode, m.title, m.title_source,
                       m.status, m.created_at_ms,
                       t.document_json, t.version AS transcript_version,
                       ma.state AS audio_state, ma.relative_path AS audio_relative_path,
                       ma.byte_count AS audio_byte_count, ma.duration_ms AS audio_duration_ms,
                       ma.format AS audio_format, ma.sample_rate_hz AS audio_sample_rate_hz,
                       ma.channels AS audio_channels, ma.bit_rate_bps AS audio_bit_rate_bps
                FROM meetings m
                JOIN accounts a ON a.account_id = m.account_id
                    AND a.enabled = 1 AND a.authority_generation = ?
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
                       t.document_json, t.version AS transcript_version,
                       ma.state AS audio_state, ma.relative_path AS audio_relative_path,
                       ma.byte_count AS audio_byte_count, ma.duration_ms AS audio_duration_ms,
                       ma.format AS audio_format, ma.sample_rate_hz AS audio_sample_rate_hz,
                       ma.channels AS audio_channels, ma.bit_rate_bps AS audio_bit_rate_bps
                FROM meetings m
                JOIN accounts a ON a.account_id = m.account_id
                    AND a.enabled = 1 AND a.authority_generation = ?
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

    async def _finish_meeting_with_transcript(
        self,
        account_id: str,
        authority_generation: int,
        meeting_id: str,
        document: Mapping[str, object],
        status: str,
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


class AccountWorkspace:
    """The only public persistence authority opened by a valid MOSS session."""

    def __init__(self, store: Phase2Store, account: Account):
        self._store = store
        self._account = account

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

    async def finish(self, status: str) -> None:
        await self._store._finish_meeting(
            self._account_id,
            self._authority_generation,
            self.meeting_id,
            status,
        )

    async def finish_with_transcript(
        self,
        document: Mapping[str, object],
        status: str,
    ) -> int:
        return await self._store._finish_meeting_with_transcript(
            self._account_id,
            self._authority_generation,
            self.meeting_id,
            document,
            status,
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
            if self.resolve_audio(archive, existing) is None:
                await asyncio.to_thread(self.discard_audio, archive, existing)
                await self.mark_audio_unavailable()
                existing = _unavailable_meeting_audio()
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
    oidc: GoogleOidc,
    oauth_cookie_secret: str,
    file_runner: Any | None = None,
    file_work_root: str | Path | None = None,
    file_inference_options: Mapping[str, object] | None = None,
    live_runtime_factory: Any | None = None,
    live_helper_lease_seconds: float | None = None,
    url_acquirer: Any | None = None,
    meeting_audio_root: str | Path | None = None,
    file_audio_archive: Any | None = None,
):
    """Create the sole Phase-2 product surface: `/`, auth, and Account-owned meetings."""

    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import (
            HTMLResponse,
            JSONResponse,
            RedirectResponse,
            Response,
            StreamingResponse,
        )
        from fastapi.staticfiles import StaticFiles
        from starlette.middleware.sessions import SessionMiddleware
    except ImportError as exc:  # pragma: no cover - package dependency is definitive.
        raise RuntimeError("Install FastAPI and itsdangerous to run the Phase-2 app.") from exc

    if not oauth_cookie_secret:
        raise ValueError("oauth_cookie_secret is required.")

    from .phase2_audio import LiveMeetingAudioStages, MeetingAudioArchive
    from .phase2_file import DEFAULT_PHASE2_FILE_WORK_ROOT

    resolved_work_root = Path(file_work_root or DEFAULT_PHASE2_FILE_WORK_ROOT).expanduser()
    audio_archive = file_audio_archive or MeetingAudioArchive(
        meeting_audio_root or resolved_work_root.parent / "meetings"
    )
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

    @asynccontextmanager
    async def lifespan(app: Any) -> AsyncIterator[None]:
        store = await Phase2Store.open(database_path)
        try:
            await store.recover_active_meetings(
                audio_archive=audio_archive if phase2_live is not None else None,
                live_audio_stages=(
                    None if phase2_live is None else phase2_live.audio_stages
                ),
            )
            if file_tasks is not None:
                file_tasks.clear_transient_work()
            app.state.phase2_store = store
            app.state.phase2_file_tasks = file_tasks
            app.state.phase2_audio_archive = audio_archive
            if phase2_live is not None:
                phase2_live.start()
            yield
        finally:
            if phase2_live is not None:
                await phase2_live.shutdown()
            if file_tasks is not None:
                await file_tasks.stop()
            await store.close()

    app = FastAPI(title="MOSS", lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=oauth_cookie_secret,
        session_cookie=OAUTH_COOKIE,
        max_age=OAUTH_COOKIE_MAX_AGE,
        same_site="lax",
        https_only=True,
    )
    frontend_dir = Path(__file__).resolve().parents[2] / "ProjectResources" / "Frontend"
    live_frontend_available = bool(
        phase2_live is not None and (frontend_dir / "index.html").is_file()
    )
    if live_frontend_available:
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.exception_handler(AccountRevoked)
    async def account_revoked(_: Request, __: AccountRevoked):
        return JSONResponse({"detail": "Sign in required."}, status_code=401)

    async def require_account(request: Request) -> Account:
        account = await request.app.state.phase2_store.account_for_session(
            request.cookies.get(SESSION_COOKIE)
        )
        if account is None:
            raise HTTPException(status_code=401, detail="Sign in required.")
        return account

    def clear_oauth_transaction(request: Request, response: Response) -> Response:
        request.session.clear()
        response.delete_cookie(
            OAUTH_COOKIE,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
        return response

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

    if phase2_live is not None:
        from .phase2_live import attach_phase2_live_routes

        attach_phase2_live_routes(
            app,
            phase2_live,
            require_account=require_account,
            live_helper_lease_seconds=float(live_helper_lease_seconds),
        )

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        account = await request.app.state.phase2_store.account_for_session(
            request.cookies.get(SESSION_COOKIE)
        )
        if account is None:
            state = request.query_params.get("auth")
            if state == "revoked" or request.cookies.get(SESSION_COOKIE):
                return HTMLResponse(_signed_out_html("revoked"), headers={"Cache-Control": "no-store"})
            if state == "denied":
                return HTMLResponse(_signed_out_html("denied"), headers={"Cache-Control": "no-store"})
            if state == "error":
                return HTMLResponse(_signed_out_html("error"), headers={"Cache-Control": "no-store"})
            return HTMLResponse(_signed_out_html("signed-out"), headers={"Cache-Control": "no-store"})
        workspace = request.app.state.phase2_store.workspace(account)
        meetings = await workspace.list_meetings()
        response = HTMLResponse(
            _workspace_html(account, meetings, live_enabled=live_frontend_available),
            headers={"Cache-Control": "no-store"},
        )
        return set_session_cookie(response, request.cookies[SESSION_COOKIE])

    @app.get("/auth/google")
    async def google_start(request: Request):
        return await oidc.begin(request)

    @app.get("/auth/google/callback")
    async def google_callback(request: Request):
        try:
            identity = await oidc.complete(request)
        except GoogleOidcRejected:
            return clear_oauth_transaction(request, RedirectResponse("/?auth=error", status_code=303))
        try:
            admitted = await request.app.state.phase2_store.admit(identity)
        except Exception:
            response = JSONResponse({"detail": "Sign-in could not be saved."}, status_code=500)
            return clear_oauth_transaction(request, response)
        if admitted is None:
            return clear_oauth_transaction(request, RedirectResponse("/?auth=denied", status_code=303))
        _, session_id = admitted
        response = clear_oauth_transaction(request, RedirectResponse("/", status_code=303))
        return set_session_cookie(response, session_id)

    @app.post("/auth/logout")
    async def logout(request: Request):
        await require_account(request)
        await request.app.state.phase2_store.revoke_session(request.cookies.get(SESSION_COOKIE))
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(
            SESSION_COOKIE,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
        return response

    @app.get("/api/auth/session")
    async def auth_session(request: Request):
        account = await require_account(request)
        response = JSONResponse({"email": account.email, "display_name": account.display_name})
        return set_session_cookie(response, request.cookies[SESSION_COOKIE])

    @app.get("/api/meetings")
    async def list_meetings(request: Request):
        account = await require_account(request)
        workspace = request.app.state.phase2_store.workspace(account)
        meetings = await workspace.list_meetings()
        return {"meetings": [meeting.to_dict() for meeting in meetings]}

    @app.post("/api/meetings/file", status_code=201)
    async def create_file_meeting(request: Request):
        account = await require_account(request)
        if request.app.state.phase2_file_tasks is None:
            raise HTTPException(status_code=503, detail="File transcription is unavailable.")
        try:
            form = await request.form()
            upload = form.get("file")
            if upload is None or not hasattr(upload, "read"):
                raise ValueError("Missing upload file.")
            handle = await request.app.state.phase2_file_tasks.accept(
                request.app.state.phase2_store.workspace(account),
                upload,
            )
            return (await handle.snapshot()).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except AccountRevoked:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Upload could not be accepted.") from exc

    @app.post("/api/meetings/url", status_code=201)
    async def create_url_meeting(request: Request):
        account = await require_account(request)
        if request.app.state.phase2_file_tasks is None:
            raise HTTPException(status_code=503, detail="File transcription is unavailable.")
        try:
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


def _required_email(value: str) -> str:
    normalized = normalize_email(value)
    if not normalized:
        raise ValueError("email is required.")
    return normalized


def _now_ms() -> int:
    return int(time.time() * 1000)


def _meeting_from_row(row: Any) -> Meeting:
    document_json = row["document_json"]
    return Meeting(
        meeting_id=row["meeting_id"],
        mode=row["mode"],
        title=row["title"],
        status=row["status"],
        created_at_ms=int(row["created_at_ms"]),
        title_source=row["title_source"],
        transcript=None if document_json is None else json.loads(document_json),
        transcript_version=0 if row["transcript_version"] is None else int(row["transcript_version"]),
        audio=_meeting_audio_from_row(row),
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


def _signed_out_html(state: str) -> str:
    if state == "revoked":
        message = "Access revoked — partial meeting preserved. Sign in with an allowed Google account."
    elif state == "denied":
        message = "Account not allowed — use another Google account or contact the operator."
    elif state == "error":
        message = "Google sign-in could not be verified. Start again."
    else:
        message = "Sign in to open your private Account workspace."
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>MOSS</title></head>
<body><main data-auth-state=\"{state}\"><h1>MOSS</h1><p>{message}</p>
<a data-action=\"google-sign-in\" href=\"/auth/google\">Sign in with Google</a></main></body></html>"""


def _workspace_html(
    account: Account,
    meetings: list[Meeting],
    *,
    live_enabled: bool = False,
) -> str:
    history = "".join(_meeting_history_card(meeting) for meeting in meetings)
    empty = "<p data-history=\"empty\">No meetings yet.</p>" if not meetings else ""
    live_head = (
        '<meta name="moss-authority" content="account">'
        '<link rel="stylesheet" href="/static/styles.css">'
        if live_enabled
        else ""
    )
    live_body = (
        '<section data-workspace-section="live" data-live-capture="account">'
        '<h2 class="phase2-workspace-heading">Live transcription</h2><div id="app"></div></section>'
        '<script type="module" src="/static/app.js"></script>'
        if live_enabled
        else ""
    )
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>MOSS</title>{live_head}</head>
<body class=\"phase2-workspace\"><main data-auth-state=\"signed-in\"><header><span data-account-email>{html.escape(account.email)}</span>
<form action=\"/auth/logout\" method=\"post\"><button>Sign out</button></form></header>
<section data-workspace=\"account\"><h1>Your meetings</h1>
<section data-workspace-section=\"file\"><h2 class=\"phase2-workspace-heading\">File transcription</h2>
<form data-file-upload=\"form\"><input name=\"file\" type=\"file\" multiple>
<label>Media URLs, one per line<textarea name=\"urls\"></textarea></label>
<button type=\"submit\">Transcribe files and URLs</button></form><p data-file-upload=\"status\"></p></section>
{live_body}
<section data-workspace-section=\"history\"><h2 class=\"phase2-workspace-heading\">Meeting history</h2>
<div id=\"meeting-history-app\" data-history-root>{empty}{history}</div></section>
</section></main>
<script>
const uploadForm = document.querySelector('[data-file-upload="form"]');
const uploadStatus = document.querySelector('[data-file-upload="status"]');
async function submitItem(path, options) {{
  try {{
    return (await fetch(path, options)).ok;
  }} catch {{
    return false;
  }}
}}
uploadForm.addEventListener('submit', async (event) => {{
  event.preventDefault();
  const files = Array.from(uploadForm.elements.file.files);
  const urls = uploadForm.elements.urls.value.split(/\\r?\\n/).map(value => value.trim()).filter(Boolean);
  let accepted = 0;
  let failed = 0;
  for (const file of files) {{
    uploadStatus.textContent = `Submitting ${{accepted + failed + 1}} of ${{files.length + urls.length}}…`;
    const body = new FormData();
    body.append('file', file, file.name);
    (await submitItem('/api/meetings/file', {{method: 'POST', body}})) ? accepted++ : failed++;
  }}
  for (const url of urls) {{
    uploadStatus.textContent = `Submitting ${{accepted + failed + 1}} of ${{files.length + urls.length}}…`;
    (await submitItem('/api/meetings/url', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{url}}),
    }})) ? accepted++ : failed++;
  }}
  uploadStatus.textContent = `${{accepted}} accepted; ${{failed}} rejected. Accepted work continues on the server.`;
  if (accepted > 0) location.reload();
}});
</script></body></html>"""


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
