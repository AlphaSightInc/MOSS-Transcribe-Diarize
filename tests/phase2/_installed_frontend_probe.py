"""Probe the Account frontend strictly from an isolated wheel installation."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace

from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

import moss_transcribe_diarize.app.phase2 as phase2


class WheelOidc:
    async def begin(self, request):
        del request
        return RedirectResponse("/auth/google/callback", status_code=302)

    async def complete(self, request):
        del request
        return phase2.GoogleIdentity("wheel-browser", "person@example.com", "Person")


class IdleLiveRuntime:
    descriptor = SimpleNamespace(
        bounds=SimpleNamespace(
            max_frame_samples=4_000,
            max_retained_samples=16_000,
            max_tape_bytes=32_000,
        )
    )

    def _bind_publication_observer(self, observer):
        self.observer = observer

    def _unbind_publication_observer(self, observer):
        assert self.observer is observer
        self.observer = None

    def abort(self, session_id, reason):
        raise AssertionError((session_id, reason))


async def allow(database: Path) -> None:
    store = await phase2.Phase2Store.open(database)
    try:
        await store.allow_email("person@example.com")
    finally:
        await store.close()


def live_app(database: Path, runtime: IdleLiveRuntime):
    return phase2.create_phase2_app(
        database_path=database,
        oidc=WheelOidc(),
        oauth_cookie_secret="wheel-smoke-cookie-secret",
        live_runtime_factory=lambda: runtime,
        live_helper_lease_seconds=30,
    )


def main() -> None:
    expected_root = Path(sys.argv[1]).resolve()
    database = Path(sys.argv[2])
    assert Path(phase2.__file__).resolve().is_relative_to(expected_root)
    assets = Path(phase2.__file__).resolve().parent / "frontend_assets"
    runtime = IdleLiveRuntime()

    asyncio.run(allow(database))
    app = live_app(database, runtime)
    with TestClient(app, base_url="https://moss.test", follow_redirects=True) as client:
        workspace = client.get("/auth/google")
        assert workspace.status_code == 200
        assert 'data-workspace-section="live"' in workspace.text
        for relative in ("app.js", "styles.css", "worklets/lane-framer.js"):
            response = client.get("/static/" + relative)
            assert response.status_code == 200
            assert response.content == (assets / relative).read_bytes()

    for relative, replacement in (
        ("worklets/lane-framer.js", None),
        ("styles.css", b""),
    ):
        path = assets / relative
        original = path.read_bytes()
        if replacement is None:
            path.unlink()
        else:
            path.write_bytes(replacement)
        try:
            try:
                live_app(
                    database.with_name(relative.replace("/", "-") + ".sqlite3"),
                    runtime,
                )
            except RuntimeError as exc:
                assert str(exc) == (
                    "Live Account frontend assets are missing or empty: " + relative
                )
            else:
                raise AssertionError("incomplete Live assets must refuse startup")
            phase2.create_phase2_app(
                database_path=database.with_name("file-only.sqlite3"),
                oidc=WheelOidc(),
                oauth_cookie_secret="wheel-smoke-cookie-secret",
            )
        finally:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(original)


if __name__ == "__main__":
    main()
