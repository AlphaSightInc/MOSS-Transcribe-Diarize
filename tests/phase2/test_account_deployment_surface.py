from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "ops"


def test_deployment_has_one_tls_account_web_unit_and_no_legacy_profile():
    start = (OPS / "start-web.sh").read_text(encoding="utf-8")
    install = (OPS / "install-services.sh").read_text(encoding="utf-8")
    unit = (OPS / "systemd" / "moss-web.service").read_text(encoding="utf-8")
    windows = (OPS / "configure-windows-network.ps1").read_text(encoding="utf-8")

    assert 'bin/mtd-phase2-web"' in start
    assert "--port 7861" in start
    assert "MOSS_PHASE2_DATABASE" in start
    assert "MOSS_GOOGLE_CLIENT_SECRET_FILE" in start
    assert "MOSS_OAUTH_COOKIE_SECRET_FILE" in start
    assert "UNITS=\"moss-vllm.service moss-web.service\"" in install
    assert "moss-account.env" in unit
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
