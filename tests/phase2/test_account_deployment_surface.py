from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "ops"
FRONTEND_ASSETS = ROOT / "moss_transcribe_diarize" / "app" / "frontend_assets"


def test_deployment_has_one_tls_account_web_unit_and_no_legacy_profile():
    start = (OPS / "start-web.sh").read_text(encoding="utf-8")
    start_vllm = (OPS / "start-vllm.sh").read_text(encoding="utf-8")
    install = (OPS / "install-services.sh").read_text(encoding="utf-8")
    unit = (OPS / "systemd" / "moss-web.service").read_text(encoding="utf-8")
    vllm_unit = (OPS / "systemd" / "moss-vllm.service").read_text(encoding="utf-8")
    profile = (OPS / "moss-account.env.example").read_text(encoding="utf-8")
    windows = (OPS / "configure-windows-network.ps1").read_text(encoding="utf-8")

    assert 'bin/mtd-phase2-web"' in start
    assert "--port 7861" in start
    assert "MOSS_PHASE2_DATABASE" in start
    assert "MOSS_GOOGLE_CLIENT_SECRET_FILE" in start
    assert "MOSS_OAUTH_COOKIE_SECRET_FILE" in start
    assert "UNITS=\"moss-vllm.service moss-web.service\"" in install
    assert "moss-account.env" in unit
    assert (
        "EnvironmentFile=/mnt/d/Coding/MOSS-Transcribe-Diarize/ops/moss-account.env"
        in vllm_unit
    )
    assert "moss.env" not in vllm_unit
    assert "MOSS_GPU_MEMORY_UTILIZATION=0.30" in profile
    assert "MOSS_MAX_MODEL_LEN=16384" in profile
    assert '"${MOSS_GPU_MEMORY_UTILIZATION:-0.38}"' in start_vllm
    assert '"${MOSS_MAX_MODEL_LEN:-16384}"' in start_vllm
    propagated = subprocess.run(
        [
            "bash",
            "-c",
            (
                'set -a; source "$1"; '
                'printf "%s %s %s" "$MOSS_GPU_MEMORY_UTILIZATION" '
                '"$MOSS_MAX_MODEL_LEN" "$MOSS_MAX_NUM_SEQS"'
            ),
            "bash",
            str(OPS / "moss-account.env.example"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert propagated.returncode == 0, propagated.stderr
    assert propagated.stdout == "0.30 16384 2"
    assert "$port = 7861" in windows
    for retired in (
        "mtd-subtitle-web",
        "moss-live-web.service",
        "moss-live.env",
        "MOSS_LIVE_AUTH_STATE",
        "MOSS_LIVE_SHARED_TOKEN_FILE",
        "MOSS_LIVE_VECTOR_JOURNAL_PATH",
        "MOSS_LIVE_RETENTION_ROOT",
        "Port        = 7860",
    ):
        assert retired not in "\n".join((start, install, unit, windows))

    assert not (OPS / "systemd" / "moss-live-web.service").exists()
    assert not (OPS / "moss-live.env.example").exists()
    assert not (OPS / "live-pair.sh").exists()
    assert not (OPS / "generate-live-tls.sh").exists()


def test_account_shell_entrypoints_parse_without_running_or_loading_models():
    for script in (OPS / "start-web.sh", OPS / "install-services.sh", OPS / "install-wsl.sh"):
        parsed = subprocess.run(
            ["bash", "-n", str(script)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert parsed.returncode == 0, parsed.stderr

    helped = subprocess.run(
        ["uv", "run", "--frozen", "mtd-phase2-web", "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert helped.returncode == 0, helped.stderr
    assert "--google-client-id" in helped.stdout
    assert "--live-provider-manifest" in helped.stdout


def test_account_frontend_has_one_generated_location_and_is_installed_in_wheel(
    tmp_path: Path,
):
    vite = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert '"../moss_transcribe_diarize/app/frontend_assets"' in vite
    assert "ProjectResources/Frontend" not in vite
    assert not (ROOT / "ProjectResources" / "Frontend").exists()

    public = ROOT / "frontend" / "public"
    for source in public.rglob("*"):
        if source.is_file():
            assert (FRONTEND_ASSETS / source.relative_to(public)).read_bytes() == source.read_bytes()

    build_source = tmp_path / "source"
    build_source.mkdir()
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(ROOT / name, build_source / name)
    shutil.copytree(
        ROOT / "moss_transcribe_diarize",
        build_source / "moss_transcribe_diarize",
    )
    wheel_dir = tmp_path / "wheel"
    built = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(wheel_dir)],
        cwd=build_source,
        check=False,
        capture_output=True,
        text=True,
    )
    assert built.returncode == 0, built.stderr
    wheels = tuple(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1
    wheel = wheels[0]
    prefix = "moss_transcribe_diarize/app/frontend_assets/"
    with zipfile.ZipFile(wheel) as archive:
        packaged_assets = {
            name.removeprefix(prefix)
            for name in archive.namelist()
            if name.startswith(prefix) and not name.endswith("/")
        }
    expected_assets = {
        path.relative_to(FRONTEND_ASSETS).as_posix()
        for path in FRONTEND_ASSETS.rglob("*")
        if path.is_file()
    }
    assert packaged_assets == expected_assets

    target = tmp_path / "installed"
    installed = subprocess.run(
        ["uv", "pip", "install", "--target", str(target), "--no-deps", str(wheel)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert installed.returncode == 0, installed.stderr
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                f"""
                from pathlib import Path
                from fastapi.testclient import TestClient
                import moss_transcribe_diarize.app.phase2 as phase2

                expected_root = Path({str(target)!r}).resolve()
                assert Path(phase2.__file__).resolve().is_relative_to(expected_root)

                class NeverOidc:
                    async def begin(self, request):
                        raise AssertionError("OIDC must not run")
                    async def complete(self, request):
                        raise AssertionError("OIDC must not run")

                app = phase2.create_phase2_app(
                    database_path=Path({str(tmp_path / 'installed.sqlite3')!r}),
                    oidc=NeverOidc(),
                    oauth_cookie_secret="wheel-smoke-cookie-secret",
                )
                with TestClient(app, base_url="https://moss.test") as client:
                    bundle = client.get("/static/app.js")
                    assert bundle.status_code == 200
                    assert "Live" in bundle.text
                    assert "Microphone" in bundle.text
                    assert client.get("/static/worklets/lane-framer.js").status_code == 200
                """
            ),
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(target)},
        check=False,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr
