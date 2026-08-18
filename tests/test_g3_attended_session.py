"""Fail-closed launch coverage for the attended live-session helper."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "g3-attended-session.sh"


def _copied_helper_checkout(tmp_path: Path) -> tuple[Path, Path]:
    """Copy the helper into a disposable Git root so its startup cannot touch this checkout."""
    checkout = tmp_path / "checkout"
    script = checkout / "scripts" / HELPER.name
    script.parent.mkdir(parents=True)
    shutil.copy2(HELPER, script)
    subprocess.run(("git", "init", "-q", str(checkout)), check=True, timeout=15)
    return checkout, script


def _run_helper_with_available_hf_model(
    tmp_path: Path, *, vllm_base_url: str | None, curl_status: str | None
) -> tuple[subprocess.CompletedProcess[str], Path]:
    checkout, script = _copied_helper_checkout(tmp_path)
    home = tmp_path / "home"
    local_model = tmp_path / "local-hf-model"
    local_model.mkdir()
    (local_model / "config.json").write_text("{}")

    stub_bin = tmp_path / "stub-bin"
    stub_bin.mkdir()
    openssl_marker = tmp_path / "openssl-called"
    (stub_bin / "openssl").write_text(
        "#!/bin/sh\n"
        f"printf called > {openssl_marker}\n"
        "exit 97\n"
    )
    (stub_bin / "openssl").chmod(0o755)
    if curl_status is not None:
        curl = stub_bin / "curl"
        curl.write_text(f"#!/bin/sh\nprintf '%s' {curl_status}\n")
        curl.chmod(0o755)

    env = {key: value for key, value in os.environ.items() if not key.startswith("MOSS_")}
    env.update(
        {
            "HOME": str(home),
            "MOSS_HF_MODEL": str(local_model),
            "MOSS_LIVE_PROVIDER_MANIFEST": str(tmp_path / "manifest.json"),
            "MOSS_LIVE_HELPER_LEASE_SECONDS": "30",
            "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
        }
    )
    if vllm_base_url is not None:
        env["MOSS_VLLM_BASE_URL"] = vllm_base_url

    return (
        subprocess.run(
            ("/bin/bash", str(script)),
            cwd=checkout,
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        ),
        openssl_marker,
    )


@pytest.mark.parametrize(
    ("vllm_base_url", "curl_status"),
    [
        (None, None),
        ("http://127.0.0.1:18000/v1", "503"),
    ],
)
def test_g3_helper_refuses_to_select_hf_when_the_tunnel_is_absent_or_unhealthy(
    tmp_path: Path, vllm_base_url: str | None, curl_status: str | None
) -> None:
    result, openssl_marker = _run_helper_with_available_hf_model(
        tmp_path, vllm_base_url=vllm_base_url, curl_status=curl_status
    )

    assert result.returncode != 0
    assert "./scripts/moss-vllm-tunnel.sh" in result.stderr
    assert "using local HF model" not in result.stdout
    assert not openssl_marker.exists()


def test_g3_helper_has_no_local_model_backend_path() -> None:
    source = HELPER.read_text()

    assert "MOSS_HF_MODEL" not in source
    assert "--backend hf" not in source
