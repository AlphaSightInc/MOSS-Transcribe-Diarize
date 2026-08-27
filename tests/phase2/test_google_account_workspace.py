from __future__ import annotations

import asyncio
import subprocess
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from authlib.integrations.base_client.errors import MismatchingStateError
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.errors import BadSignatureError, ExpiredTokenError, InvalidClaimError
from joserfc.jwk import RSAKey
from starlette.requests import Request

from moss_transcribe_diarize.app.phase2 import (
    GOOGLE_CALLBACK_URL,
    DEFAULT_PHASE2_DATABASE_PATH,
    OAUTH_COOKIE,
    SESSION_COOKIE,
    AuthlibGoogleOidc,
    GoogleIdentity,
    Phase2Store,
    SchemaVersionError,
    create_phase2_app,
)
from moss_transcribe_diarize.app import phase2_web_cli
from moss_transcribe_diarize.app.phase2_admin import execute, parse_args as parse_admin_args


@dataclass
class FakeGoogleRemote:
    responses: dict[str, dict[str, object] | Exception]
    start_calls: list[dict[str, object]]
    complete_calls: list[dict[str, object]]

    async def load_server_metadata(self) -> dict[str, str]:
        return {"issuer": "https://google.test"}

    async def authorize_redirect(self, request: Any, redirect_uri: str, **kwargs: object):
        self.start_calls.append({"redirect_uri": redirect_uri, **kwargs})
        request.session["fake-state"] = "correct-state"
        return RedirectResponse("https://accounts.google.test/choose", status_code=302)

    async def authorize_access_token(self, request: Any, **kwargs: object) -> dict[str, object]:
        self.complete_calls.append(dict(kwargs))
        if request.query_params.get("state") != request.session.get("fake-state"):
            raise ValueError("state does not match")
        result = self.responses[request.query_params["code"]]
        if isinstance(result, Exception):
            raise result
        return {"userinfo": result}


def identity(
    account_id: str = "google-sub-a",
    email: str = "person@example.com",
    *,
    verified: bool = True,
) -> dict[str, object]:
    return {
        "sub": account_id,
        "email": email,
        "name": "Person",
        "email_verified": verified,
    }


async def provision(database: Path, *emails: str) -> None:
    store = await Phase2Store.open(database)
    try:
        for email in emails:
            await store.allow_email(email)
    finally:
        await store.close()


def make_app(database: Path, responses: dict[str, dict[str, object] | Exception]):
    remote = FakeGoogleRemote(responses=responses, start_calls=[], complete_calls=[])
    app = create_phase2_app(
        database_path=database,
        oidc=AuthlibGoogleOidc(remote=remote, client_id="test-client-id"),
        oauth_cookie_secret="test-only-signed-oauth-cookie-secret",
    )
    return app, remote


def sign_in(client: TestClient, code: str) -> object:
    start = client.get("/auth/google", follow_redirects=False)
    assert start.status_code == 302
    return client.get(f"/auth/google/callback?state=correct-state&code={code}", follow_redirects=False)


def database_counts(database: Path) -> tuple[int, int]:
    connection = sqlite3.connect(database)
    try:
        accounts = connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        sessions = connection.execute("SELECT COUNT(*) FROM sign_in_sessions").fetchone()[0]
        return accounts, sessions
    finally:
        connection.close()


def test_authlib_172_google_client_is_openid_only_and_uses_s256_pkce():
    import authlib

    oidc = AuthlibGoogleOidc.configured(client_id="client-id", client_secret="client-secret")

    assert authlib.__version__ == "1.7.2"
    assert oidc._remote.client_kwargs == {
        "scope": "openid profile email",
        "code_challenge_method": "S256",
    }
    assert oidc._remote._server_metadata_url == "https://accounts.google.com/.well-known/openid-configuration"


def test_authlib_172_offline_prototype_rejects_signed_claim_failures_before_admission():
    """A deterministic real-Authlib prototype; see prototypes/phase2-authlib-validation/NOTES.md."""

    issuer = "https://offline-issuer.test"
    client_id = "offline-moss-client"
    signing_key = RSAKey.generate_key(2048, private=True)
    oidc = AuthlibGoogleOidc.configured(client_id=client_id, client_secret="test-secret")
    remote = oidc._remote
    remote.server_metadata = {
        "_loaded_at": 0,
        "issuer": issuer,
        "jwks": {"keys": [signing_key.as_dict(private=False)]},
        "id_token_signing_alg_values_supported": ["RS256"],
    }
    claims_options = {
        "iss": {"values": [issuer]},
        "aud": {"value": client_id},
    }

    def signed_id_token(**overrides: object) -> dict[str, object]:
        now = int(time.time())
        claims: dict[str, object] = {
            "iss": issuer,
            "sub": "offline-subject",
            "aud": client_id,
            "exp": now + 60,
            "iat": now,
            "nonce": "offline-nonce",
        }
        claims.update(overrides)
        return {"id_token": jwt.encode({"alg": "RS256"}, claims, signing_key)}

    async def exercise() -> dict[str, str]:
        outcomes: dict[str, str] = {}

        claims = await remote.parse_id_token(
            signed_id_token(),
            nonce="offline-nonce",
            leeway=0,
            claims_options=claims_options,
        )
        outcomes["valid"] = str(claims["sub"])

        cases = {
            "issuer": (signed_id_token(iss="https://wrong-issuer.test"), InvalidClaimError),
            # OIDC requires azp when aud has multiple values; a mismatching azp is Authlib's
            # deterministic audience/authorized-party rejection path.
            "audience": (signed_id_token(aud="wrong-client"), InvalidClaimError),
            "authorized_party": (
                signed_id_token(aud=[client_id, "another-client"], azp="wrong-client"),
                InvalidClaimError,
            ),
            "expiry": (signed_id_token(exp=int(time.time()) - 1), ExpiredTokenError),
            "nonce": (signed_id_token(nonce="wrong-nonce"), InvalidClaimError),
        }
        for name, (token, expected) in cases.items():
            with pytest.raises(expected):
                await remote.parse_id_token(
                    token,
                    nonce="offline-nonce",
                    leeway=0,
                    claims_options=claims_options,
                )
            outcomes[name] = expected.__name__

        wrong_key = RSAKey.generate_key(2048, private=True)
        with pytest.raises(BadSignatureError):
            await remote.parse_id_token(
                {
                    "id_token": jwt.encode(
                        {"alg": "RS256"},
                        {
                            "iss": issuer,
                            "sub": "offline-subject",
                            "aud": client_id,
                            "exp": int(time.time()) + 60,
                            "iat": int(time.time()),
                            "nonce": "offline-nonce",
                        },
                        wrong_key,
                    )
                },
                nonce="offline-nonce",
                leeway=0,
                claims_options=claims_options,
            )
        outcomes["signature"] = BadSignatureError.__name__

        async def network_must_not_run(**_: object) -> object:
            raise AssertionError("bad state reached the token endpoint")

        remote.fetch_access_token = network_must_not_run
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "scheme": "https",
                "path": "/auth/google/callback",
                "raw_path": b"/auth/google/callback",
                "query_string": b"code=offline-code&state=wrong-state",
                "headers": [],
                "server": ("moss.test", 443),
                "client": ("127.0.0.1", 1),
                "session": {},
            }
        )
        with pytest.raises(MismatchingStateError):
            await remote.authorize_access_token(request)
        outcomes["state"] = MismatchingStateError.__name__
        return outcomes

    outcomes = asyncio.run(exercise())
    print(outcomes)
    assert outcomes == {
        "valid": "offline-subject",
        "issuer": "InvalidClaimError",
        "audience": "InvalidClaimError",
        "authorized_party": "InvalidClaimError",
        "expiry": "ExpiredTokenError",
        "nonce": "InvalidClaimError",
        "signature": "BadSignatureError",
        "state": "MismatchingStateError",
    }


def test_schema_v1_contains_exact_ownership_tables_and_settings(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"

    async def exercise():
        store = await Phase2Store.open(database)
        try:
            assert await store.user_version() == 1
            assert await store.table_names() == {
                "account_allowlist",
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
            settings = await store.sqlite_settings()
            assert settings == {"journal_mode": "wal", "foreign_keys": 1, "synchronous": 2}
        finally:
            await store.close()

    asyncio.run(exercise())


def test_existing_non_v1_database_is_refused_without_mutating_its_bytes_or_creating_sidecars(
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


def test_composite_ownership_foreign_keys_reject_cross_account_children(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"

    async def exercise():
        store = await Phase2Store.open(database)
        try:
            await store.allow_email("a@example.com")
            await store.allow_email("b@example.com")
            account_a, _ = (await store.admit(GoogleIdentity("sub-a", "a@example.com", "A")))
            account_b, _ = (await store.admit(GoogleIdentity("sub-b", "b@example.com", "B")))
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


def test_allowed_callback_binds_subject_issues_opaque_cookie_and_opens_empty_workspace(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    asyncio.run(provision(database, "person+qa@example.com"))
    app, remote = make_app(database, {"allowed": identity(email=" Person+qa@EXAMPLE.com ")})

    with TestClient(app, base_url="https://moss.test") as client:
        start = client.get("/auth/google", follow_redirects=False)
        assert start.status_code == 302
        oauth_set_cookie = "\n".join(start.headers.get_list("set-cookie")).lower()
        assert f"{OAUTH_COOKIE.lower()}=" in oauth_set_cookie
        assert "max-age=600" in oauth_set_cookie
        assert "secure" in oauth_set_cookie and "httponly" in oauth_set_cookie and "samesite=lax" in oauth_set_cookie
        assert "domain=" not in oauth_set_cookie
        response = client.get("/auth/google/callback?state=correct-state&code=allowed", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        assert remote.start_calls == [
            {
                "redirect_uri": GOOGLE_CALLBACK_URL,
                "prompt": "select_account",
                "access_type": "online",
            }
        ]
        assert remote.complete_calls == [
            {
                "leeway": 0,
                "claims_options": {
                    "iss": {"values": ["https://google.test"]},
                    "aud": {"value": "test-client-id"},
                },
            }
        ]
        session_cookie = client.cookies.get(SESSION_COOKIE)
        assert session_cookie is not None
        assert "google-sub-a" not in session_cookie
        assert "person" not in session_cookie
        set_cookie = "\n".join(response.headers.get_list("set-cookie")).lower()
        assert f"{SESSION_COOKIE.lower()}=" in set_cookie
        assert "secure" in set_cookie and "httponly" in set_cookie and "samesite=lax" in set_cookie
        assert "domain=" not in set_cookie
        assert client.get("/api/auth/session").json() == {
            "email": "person+qa@example.com",
            "display_name": "Person",
        }
        assert client.get("/api/meetings").json() == {"meetings": []}
        workspace = client.get("/")
        assert workspace.status_code == 200
        assert 'data-auth-state="signed-in"' in workspace.text
        assert 'data-history="empty"' in workspace.text

    assert database_counts(database) == (1, 1)


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(ValueError("bad signature"), id="signature"),
        pytest.param(ValueError("bad issuer"), id="issuer"),
        pytest.param(ValueError("bad audience"), id="audience"),
        pytest.param(ValueError("expired"), id="expiry"),
        pytest.param(ValueError("bad state"), id="state"),
        pytest.param(ValueError("bad nonce"), id="nonce"),
    ],
)
def test_authlib_rejections_leave_no_account_or_session(tmp_path: Path, failure: Exception):
    database = tmp_path / "moss.sqlite3"
    asyncio.run(provision(database, "person@example.com"))
    app, _ = make_app(database, {"rejected": failure})

    with TestClient(app, base_url="https://moss.test") as client:
        response = sign_in(client, "rejected")
        assert response.status_code == 303
        assert response.headers["location"] == "/?auth=error"
        assert client.cookies.get(SESSION_COOKIE) is None
        assert client.cookies.get(OAUTH_COOKIE) is None

    assert database_counts(database) == (0, 0)


def test_unverified_or_disallowed_callback_leaves_no_account_or_session(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    asyncio.run(provision(database, "allowed@example.com"))
    app, _ = make_app(
        database,
        {
            "unverified": identity(verified=False),
            "denied": identity(email="not-allowed@example.com"),
        },
    )

    with TestClient(app, base_url="https://moss.test") as client:
        invalid = sign_in(client, "unverified")
        assert invalid.headers["location"] == "/?auth=error"
        denied = sign_in(client, "denied")
        assert denied.headers["location"] == "/?auth=denied"
        page = client.get(denied.headers["location"])
        assert 'data-auth-state="denied"' in page.text
        assert "Account not allowed" in page.text

    assert database_counts(database) == (0, 0)


def test_email_cannot_transfer_an_account_and_same_subject_can_change_to_allowed_email(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    asyncio.run(provision(database, "first@example.com", "second@example.com"))
    app, _ = make_app(
        database,
        {
            "first": identity("sub-a", "first@example.com"),
            "conflict": identity("sub-b", "first@example.com"),
            "changed": identity("sub-a", "second@example.com"),
        },
    )

    with TestClient(app, base_url="https://moss.test") as client:
        assert sign_in(client, "first").status_code == 303
        client.post("/auth/logout")
        assert sign_in(client, "conflict").headers["location"] == "/?auth=denied"
        assert sign_in(client, "changed").status_code == 303
        assert client.get("/api/auth/session").json()["email"] == "second@example.com"

    assert database_counts(database) == (1, 1)


def test_sign_out_revokes_only_this_browser_and_restart_keeps_other_session(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    asyncio.run(provision(database, "person@example.com"))
    app, _ = make_app(database, {"one": identity(), "two": identity()})

    with TestClient(app, base_url="https://moss.test") as first, TestClient(
        app, base_url="https://moss.test"
    ) as second:
        assert sign_in(first, "one").status_code == 303
        assert sign_in(second, "two").status_code == 303
        survivor_cookie = second.cookies.get(SESSION_COOKIE)
        active = first.post("/api/meetings", json={"mode": "live"}).json()
        assert first.post("/auth/logout").status_code == 204
        assert first.get("/api/auth/session").status_code == 401
        assert second.get("/api/auth/session").status_code == 200

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT status FROM meetings WHERE meeting_id = ?", (active["id"],)
        ).fetchone()[0] == "interrupted"
    finally:
        connection.close()

    restarted, _ = make_app(database, {})
    with TestClient(restarted, base_url="https://moss.test") as after_restart:
        after_restart.cookies.set(SESSION_COOKIE, survivor_cookie, domain="moss.test", path="/")
        assert after_restart.get("/api/auth/session").status_code == 200


def test_product_app_startup_interrupts_existing_active_meetings(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"

    async def create_active_meeting() -> None:
        store = await Phase2Store.open(database)
        try:
            await store.allow_email("person@example.com")
            account, _ = (await store.admit(GoogleIdentity("sub-a", "person@example.com", "Person")))
            await store.workspace(account).create_meeting("live")
        finally:
            await store.close()

    asyncio.run(create_active_meeting())
    app, _ = make_app(database, {})
    with TestClient(app, base_url="https://moss.test"):
        pass

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT status FROM meetings").fetchone()[0] == "interrupted"
    finally:
        connection.close()


def test_account_workspace_hides_foreign_meeting_and_all_unauthenticated_content_is_401(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    asyncio.run(provision(database, "a@example.com", "b@example.com"))
    app, _ = make_app(
        database,
        {"a": identity("sub-a", "a@example.com"), "b": identity("sub-b", "b@example.com")},
    )

    with TestClient(app, base_url="https://moss.test") as a, TestClient(
        app, base_url="https://moss.test"
    ) as b, TestClient(app, base_url="https://moss.test") as anonymous:
        created = sign_in(a, "a")
        assert created.status_code == 303
        meeting = a.post("/api/meetings", json={"mode": "file"})
        assert meeting.status_code == 201
        meeting_id = meeting.json()["id"]
        assert sign_in(b, "b").status_code == 303
        assert b.get("/api/meetings").json() == {"meetings": []}
        assert b.get(f"/api/meetings/{meeting_id}").status_code == 404
        assert anonymous.get("/api/auth/session").status_code == 401
        assert anonymous.get("/api/meetings").status_code == 401
        assert anonymous.get(f"/api/meetings/{meeting_id}").status_code == 401
        assert anonymous.get("/studio").status_code == 404
        assert anonymous.get("/live").status_code == 404
        assert anonymous.get("/api/jobs").status_code == 404


def test_revoked_account_loses_every_session_and_meetings_are_interrupted(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    asyncio.run(provision(database, "person@example.com"))
    app, _ = make_app(database, {"one": identity(), "two": identity()})

    with TestClient(app, base_url="https://moss.test") as first, TestClient(
        app, base_url="https://moss.test"
    ) as second:
        sign_in(first, "one")
        sign_in(second, "two")
        meeting = first.post("/api/meetings", json={"mode": "live"}).json()
        assert asyncio.run(execute(database, "revoke", "person@example.com")) == {
            "email": "person@example.com",
            "revoked": True,
        }
        assert first.get("/api/meetings").status_code == 401
        assert second.get("/api/meetings").status_code == 401
        revoked_page = first.get("/")
        assert 'data-auth-state="revoked"' in revoked_page.text
        assert "Access revoked" in revoked_page.text

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT status FROM meetings WHERE meeting_id = ?", (meeting["id"],)).fetchone()[0] == "interrupted"
    finally:
        connection.close()


def test_revoking_one_bound_email_disables_all_bound_emails_until_explicit_reallow(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"
    asyncio.run(provision(database, "first@example.com", "second@example.com"))
    app, _ = make_app(
        database,
        {
            "first": identity("sub-a", "first@example.com"),
            "second": identity("sub-a", "second@example.com"),
        },
    )

    with TestClient(app, base_url="https://moss.test") as client:
        assert sign_in(client, "first").status_code == 303
        assert client.post("/auth/logout").status_code == 204
        assert sign_in(client, "second").status_code == 303
        assert asyncio.run(execute(database, "revoke", "first@example.com")) == {
            "email": "first@example.com",
            "revoked": True,
        }
        assert sign_in(client, "second").headers["location"] == "/?auth=denied"

    assert asyncio.run(execute(database, "list")) == [
        {"email": "first@example.com", "enabled": False},
        {"email": "second@example.com", "enabled": False},
    ]


def test_host_local_allow_list_and_revoke_commands_normalize_only_trim_and_case(tmp_path: Path):
    database = tmp_path / "moss.sqlite3"

    assert asyncio.run(execute(database, "allow", " Person+tag@EXAMPLE.com ")) == {
        "email": "person+tag@example.com",
        "enabled": True,
    }
    assert asyncio.run(execute(database, "list")) == [
        {"email": "person+tag@example.com", "enabled": True}
    ]
    assert asyncio.run(execute(database, "revoke", "person+tag@example.com")) == {
        "email": "person+tag@example.com",
        "revoked": True,
    }


def test_mtd_admin_account_commands_share_the_product_default_database():
    assert parse_admin_args(["accounts", "allow", "person@example.com"]).database == str(
        DEFAULT_PHASE2_DATABASE_PATH
    )
    assert parse_admin_args(["accounts", "list"]).database == str(DEFAULT_PHASE2_DATABASE_PATH)
    assert parse_admin_args(["accounts", "revoke", "person@example.com"]).database == str(
        DEFAULT_PHASE2_DATABASE_PATH
    )


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


def test_top_level_legacy_model_exports_remain_importable():
    from moss_transcribe_diarize import (
        MossTranscribeDiarizeConfig,
        MossTranscribeDiarizeForConditionalGeneration,
        MossTranscribeDiarizeModel,
        MossTranscribeDiarizePreTrainedModel,
        MossTranscribeDiarizeProcessor,
        VQAdaptor,
    )
    from moss_transcribe_diarize.configuration_moss_transcribe_diarize import (
        MossTranscribeDiarizeConfig as DirectConfig,
    )

    assert MossTranscribeDiarizeConfig is DirectConfig
    assert {
        MossTranscribeDiarizeForConditionalGeneration.__name__,
        MossTranscribeDiarizeModel.__name__,
        MossTranscribeDiarizePreTrainedModel.__name__,
        MossTranscribeDiarizeProcessor.__name__,
        VQAdaptor.__name__,
    } == {
        "MossTranscribeDiarizeForConditionalGeneration",
        "MossTranscribeDiarizeModel",
        "MossTranscribeDiarizePreTrainedModel",
        "MossTranscribeDiarizeProcessor",
        "VQAdaptor",
    }


def test_packaged_phase2_tls_entrypoint_constructs_the_account_app(monkeypatch, tmp_path: Path):
    client_secret = tmp_path / "google-client-secret"
    oauth_secret = tmp_path / "oauth-cookie-secret"
    client_secret.write_text("test-client-secret\n", encoding="utf-8")
    oauth_secret.write_text("test-oauth-secret\n", encoding="utf-8")
    seen: dict[str, object] = {}
    oidc = object()
    app = object()

    monkeypatch.setattr(
        phase2_web_cli.AuthlibGoogleOidc,
        "configured",
        lambda **kwargs: seen.setdefault("oidc", kwargs) and oidc,
    )

    def fake_create_app(**kwargs: object):
        seen["app"] = kwargs
        return app

    monkeypatch.setattr(phase2_web_cli, "create_phase2_app", fake_create_app)

    class FakeUvicorn:
        @staticmethod
        def run(received_app: object, **kwargs: object) -> None:
            seen["uvicorn"] = {"app": received_app, **kwargs}

    monkeypatch.setitem(sys.modules, "uvicorn", FakeUvicorn)
    phase2_web_cli.main(
        [
            "--google-client-id",
            "test-client-id",
            "--google-client-secret-file",
            str(client_secret),
            "--oauth-cookie-secret-file",
            str(oauth_secret),
            "--tls-certfile",
            "/etc/moss/cert.pem",
            "--tls-keyfile",
            "/etc/moss/key.pem",
        ]
    )

    assert seen["oidc"] == {"client_id": "test-client-id", "client_secret": "test-client-secret"}
    assert seen["app"] == {
        "database_path": DEFAULT_PHASE2_DATABASE_PATH,
        "oidc": oidc,
        "oauth_cookie_secret": "test-oauth-secret",
    }
    assert seen["uvicorn"] == {
        "app": app,
        "host": "0.0.0.0",
        "port": 7861,
        "ssl_certfile": "/etc/moss/cert.pem",
        "ssl_keyfile": "/etc/moss/key.pem",
        "proxy_headers": False,
    }
