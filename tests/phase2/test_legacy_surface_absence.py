from __future__ import annotations

import sys
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import create_phase2_app


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ASSETS = ROOT / "moss_transcribe_diarize" / "app" / "frontend_assets"
RETIRED_MODULES = (
    "cli",
    "jobs",
    "live_auth",
    "live_portal",
    "live_vector_journal",
    "phase1_creation_quiesce",
    "phase1_quiesce_cli",
    "server",
    "web_cli",
)
RETIRED_SENTINELS = (
    "/api/jobs",
    "captureBearer",
    "view_token",
    "pairing_payload",
    "mtd-subtitle-web",
    "mtd-phase1-quiesce",
    "MOSS_LIVE_SHARED_TOKEN",
    "MOSS_LIVE_AUTH_STATE",
    "MOSS_LIVE_VECTOR_JOURNAL",
    "MOSS_LIVE_RETENTION",
    "from .jobs import",
    "from .server import",
    "from .web_cli import",
    "from .live_auth import",
    "from .live_portal import",
    "from .live_vector_journal import",
    "from .phase1_creation_quiesce import",
)


class NeverOidc:
    async def begin(self, request):
        del request
        raise AssertionError("OIDC must not run")

    async def complete(self, request):
        del request
        raise AssertionError("OIDC must not run")


def _retired_hits(payload: str) -> tuple[str, ...]:
    return tuple(value for value in RETIRED_SENTINELS if value in payload)


def test_only_account_routes_and_allowlisted_static_assets_are_reachable(tmp_path: Path):
    app = create_phase2_app(
        database_path=tmp_path / "moss.sqlite3",
        oidc=NeverOidc(),
        oauth_cookie_secret="cookie-secret",
    )
    retired_requests = (
        ("get", "/studio"),
        ("get", "/live"),
        ("get", "/api/runtime"),
        ("post", "/api/jobs"),
        ("post", "/api/jobs/anything/rerun"),
        ("post", "/api/live/pairing-codes"),
        ("post", "/api/live/pairings"),
        ("delete", "/api/live/devices/device"),
        ("get", "/static/index.html"),
        ("get", "/static/mic-check.html"),
    )
    implicit_framework_routes = (
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/openapi.json",
    )

    registered_paths = {route.path for route in app.routes}
    assert not registered_paths.intersection(implicit_framework_routes)

    with TestClient(app, base_url="https://moss.test") as client:
        for method, path in retired_requests:
            assert client.request(method, path).status_code == 404, path
        for path in implicit_framework_routes:
            assert client.get(path).status_code == 404, path
            assert client.head(path).status_code == 404, path
        assert client.get("/").status_code == 200


def test_package_has_only_account_commands_and_no_retired_import_targets():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    script_block = pyproject.split("[project.scripts]", 1)[1].split("[", 1)[0]
    assert script_block.strip().splitlines() == [
        'mtd-admin = "moss_transcribe_diarize.app.phase2_admin:main"',
        'mtd-phase2-cutover = "moss_transcribe_diarize.app.phase2_cutover_cli:main"',
        'mtd-phase2-web = "moss_transcribe_diarize.app.phase2_web_cli:main"',
    ]
    for module in RETIRED_MODULES:
        assert not (ROOT / "moss_transcribe_diarize" / "app" / f"{module}.py").exists()
        assert f"moss_transcribe_diarize.app.{module}" not in sys.modules
    assert not (ROOT / "macos" / "MOSSCapture" / "Package.swift").exists()

    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import moss_transcribe_diarize.app.phase2_web_cli; "
                "forbidden="
                + repr(tuple(f"moss_transcribe_diarize.app.{name}" for name in RETIRED_MODULES))
                + "; assert not set(forbidden).intersection(sys.modules)"
            ),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr


def test_production_bundle_contains_no_retired_authority_or_job_fallback():
    bundle = (FRONTEND_ASSETS / "app.js").read_text(encoding="utf-8")
    source_map = (FRONTEND_ASSETS / "app.js.map").read_text(encoding="utf-8")
    assert _retired_hits(bundle) == ()
    assert _retired_hits(source_map) == ()
    assert _retired_hits("prefix captureBearer suffix") == ("captureBearer",)


def test_product_source_config_and_executable_scripts_have_no_retired_seam():
    roots = (
        ROOT / "moss_transcribe_diarize",
        ROOT / "frontend" / "src",
        ROOT / "ops",
        ROOT / "scripts",
    )
    suffixes = {".py", ".ts", ".tsx", ".sh", ".ps1", ".service", ".example"}
    sources = [ROOT / "pyproject.toml"]
    for root in roots:
        sources.extend(
            path for path in root.rglob("*") if path.is_file() and path.suffix in suffixes
        )

    hits = {
        str(path.relative_to(ROOT)): _retired_hits(path.read_text(encoding="utf-8"))
        for path in sources
        if _retired_hits(path.read_text(encoding="utf-8"))
    }
    assert hits == {}
