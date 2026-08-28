from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
import zipfile
from pathlib import Path

import pytest

from moss_transcribe_diarize import installed_candidate


ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "ops"
FRONTEND_ASSETS = ROOT / "moss_transcribe_diarize" / "app" / "frontend_assets"
INSTALLED_FRONTEND_PROBE = Path(__file__).with_name("_installed_frontend_probe.py")


def _shell_function(source: str, name: str) -> str:
    start = source.index(f"{name}() {{")
    end = source.index("\n}", start) + 2
    return source[start:end]


def test_deployment_has_one_tls_account_web_unit_and_no_legacy_profile():
    start = (OPS / "start-web.sh").read_text(encoding="utf-8")
    install = (OPS / "install-services.sh").read_text(encoding="utf-8")
    install_wsl = (OPS / "install-wsl.sh").read_text(encoding="utf-8")
    stage_account = (OPS / "stage-account-candidate.sh").read_text(encoding="utf-8")
    account_launcher = (OPS / "account-web-launcher.sh").read_text(encoding="utf-8")
    admin_launcher = (OPS / "account-admin-launcher.sh").read_text(encoding="utf-8")
    cutover_launcher = (OPS / "account-cutover-launcher.sh").read_text(encoding="utf-8")
    vllm_launcher = (OPS / "vllm-launcher.sh").read_text(encoding="utf-8")
    sqlite_build = (OPS / "build-account-sqlite.sh").read_text(encoding="utf-8")
    unit = (OPS / "systemd" / "moss-web.service").read_text(encoding="utf-8")
    vllm_unit = (OPS / "systemd" / "moss-vllm.service").read_text(encoding="utf-8")
    vllm_profile = (OPS / "moss-vllm.env.example").read_text(encoding="utf-8")
    account_profile = (OPS / "moss-account.env.example").read_text(encoding="utf-8")
    windows = (OPS / "configure-windows-network.ps1").read_text(encoding="utf-8")

    assert "account-current" in start
    assert 'exec "${ACCOUNT_CURRENT}/bin/mtd-account-web"' in start
    assert "bin/python\" -m moss_transcribe_diarize.app.phase2_web_cli" in account_launcher
    assert "bin/python\" -m moss_transcribe_diarize.app.phase2_admin" in admin_launcher
    assert "bin/python\" -m moss_transcribe_diarize.app.phase2_cutover_cli" in cutover_launcher
    assert "sqlite-3.53.4" in cutover_launcher and "LD_LIBRARY_PATH" in cutover_launcher
    assert 'account-admin-launcher.sh" "${RELEASE_STAGE}/bin/mtd-admin' in stage_account
    assert 'account-cutover-launcher.sh" "${RELEASE_STAGE}/bin/mtd-phase2-cutover' in stage_account
    assert "sqlite-3.53.4" in account_launcher
    assert "LD_LIBRARY_PATH" in account_launcher
    assert "stage-account-candidate.sh" in install_wsl
    assert '"${CHECKOUT}/ops/build-account-sqlite.sh"' in stage_account
    assert '"${SCRIPT_DIR}/build-account-sqlite.sh"' not in stage_account
    assert "/usr/bin/python3.12 -m venv" in stage_account
    assert "account-runtimes" in stage_account
    assert "candidate-checkouts" in stage_account
    assert "candidate-manifests" in stage_account
    assert "build_candidate.json" in stage_account
    assert "--frozen --extra acceptance --no-emit-project" in stage_account
    assert 'pip" install --require-hashes' in stage_account
    assert 'pip" install --no-deps' in stage_account
    assert 'ln -s "${RELEASE}" "${CHECKOUT}/.venv"' in stage_account
    assert "activation_state" in stage_account and "staged_inert" in stage_account
    assert "release_launcher_sha256" in stage_account
    assert "release_admin_launcher_sha256" in stage_account
    assert "release_cutover_launcher_sha256" in stage_account
    assert "release_vllm_launcher_sha256" in stage_account
    assert "web_unit_sha256" in stage_account
    assert "vllm_unit_sha256" in stage_account
    assert "reused candidate checkout is dirty" in stage_account
    assert "account-current" not in stage_account
    assert "${VENV_DIR}" not in stage_account
    assert "--editable \"${PROJECT_DIR}\"" in install_wsl  # GPU bootstrap only.
    assert "sqlite-autoconf-3530400.tar.gz" in sqlite_build
    assert "454e45f61c6bd75b7420e7190732dea03ce6639c63ada47bbc592f67fc340338" in sqlite_build
    assert "--port 7861" in account_launcher
    assert "MOSS_PHASE2_DATABASE" in account_launcher
    assert "MOSS_GOOGLE_CLIENT_SECRET_FILE" in account_launcher
    assert "MOSS_OAUTH_COOKIE_SECRET_FILE" in account_launcher
    assert "UNITS=\"moss-vllm.service moss-web.service\"" in install
    assert ".config/moss-transcribe-diarize" in install
    assert "service profile must be mode 0600" in install
    assert "reviewed Account release is not activated" in install
    assert "active release manifest is missing" in install
    assert "validated_candidate_artifacts" in install
    assert "${MANIFEST_CHECKOUT}/ops/systemd/${unit}" in install
    assert "${SCRIPT_DIR}/systemd/${unit}" not in install
    assert "ops/moss-account.env" not in install
    assert "moss-account.env" in unit
    assert "EnvironmentFile=%h/.config/moss-transcribe-diarize/vllm.env" in vllm_unit
    assert "account-current/bin/mtd-vllm" in vllm_unit
    assert "/mnt/d/" not in vllm_unit
    assert "MOSS_GPU_MEMORY_UTILIZATION=0.30" in vllm_profile
    assert "MOSS_MAX_MODEL_LEN=16384" in vllm_profile
    assert '"${MOSS_GPU_MEMORY_UTILIZATION:-0.38}"' in vllm_launcher
    assert '"${MOSS_MAX_MODEL_LEN:-16384}"' in vllm_launcher
    assert "~/.config/moss-transcribe-diarize/moss-account.env" in account_profile
    assert "Copy to ops/moss-account.env" not in account_profile
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
            str(OPS / "moss-vllm.env.example"),
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
    for script in (
        OPS / "start-web.sh",
        OPS / "install-services.sh",
        OPS / "install-wsl.sh",
        OPS / "build-account-sqlite.sh",
        OPS / "stage-account-candidate.sh",
        OPS / "account-web-launcher.sh",
        OPS / "account-admin-launcher.sh",
        OPS / "account-cutover-launcher.sh",
        OPS / "vllm-launcher.sh",
    ):
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
    cutover_help = subprocess.run(
        ["uv", "run", "--frozen", "mtd-phase2-cutover", "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert cutover_help.returncode == 0, cutover_help.stderr
    assert "{run,restore}" in cutover_help.stdout


def test_candidate_stage_traps_remove_owned_partials_and_allow_retry(tmp_path: Path):
    stage_source = (OPS / "stage-account-candidate.sh").read_text(encoding="utf-8")
    sqlite_source = (OPS / "build-account-sqlite.sh").read_text(encoding="utf-8")
    checkout_stage = tmp_path / "checkout.stage"
    release_stage = tmp_path / "release.stage"
    manifest_stage = tmp_path / "manifest.stage"
    sqlite_stage = tmp_path / "sqlite.stage"
    stage_probe = tmp_path / "stage-failure-probe.sh"
    stage_probe.write_text(
        "\n".join(
            (
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                _shell_function(stage_source, "cleanup_stages"),
                f'CHECKOUT_STAGE="{checkout_stage}"',
                f'RELEASE_STAGE="{release_stage}"',
                f'MANIFEST_STAGE="{manifest_stage}"',
                'mkdir -p "${CHECKOUT_STAGE}" "${RELEASE_STAGE}"',
                'touch "${MANIFEST_STAGE}"',
                'trap cleanup_stages EXIT',
                'false',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    sqlite_probe = tmp_path / "sqlite-failure-probe.sh"
    sqlite_probe.write_text(
        "\n".join(
            (
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                _shell_function(sqlite_source, "cleanup_build_root"),
                f'BUILD_ROOT="{sqlite_stage}"',
                'mkdir -p "${BUILD_ROOT}"',
                'trap cleanup_build_root EXIT',
                'false',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    stage_failed = subprocess.run(
        ["bash", str(stage_probe)],
        check=False,
        capture_output=True,
        text=True,
    )
    sqlite_failed = subprocess.run(
        ["bash", str(sqlite_probe)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert stage_failed.returncode != 0
    assert sqlite_failed.returncode != 0
    assert not checkout_stage.exists()
    assert not release_stage.exists()
    assert not manifest_stage.exists()
    assert not sqlite_stage.exists()

    checkout_final = tmp_path / "checkout"
    release_final = tmp_path / "release"
    manifest_final = tmp_path / "candidate.json"
    sqlite_final = tmp_path / "sqlite-prefix"
    retry = tmp_path / "retry-probe.sh"
    retry.write_text(
        "\n".join(
            (
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                _shell_function(stage_source, "cleanup_stages"),
                _shell_function(sqlite_source, "cleanup_build_root"),
                f'CHECKOUT_STAGE="{checkout_stage}"',
                f'RELEASE_STAGE="{release_stage}"',
                f'MANIFEST_STAGE="{manifest_stage}"',
                f'BUILD_ROOT="{sqlite_stage}"',
                'trap cleanup_stages EXIT',
                'mkdir -p "${CHECKOUT_STAGE}" "${RELEASE_STAGE}" "${BUILD_ROOT}/verified-prefix"',
                'printf complete > "${MANIFEST_STAGE}"',
                f'mv "${{CHECKOUT_STAGE}}" "{checkout_final}"',
                'CHECKOUT_STAGE=""',
                f'mv "${{RELEASE_STAGE}}" "{release_final}"',
                'RELEASE_STAGE=""',
                f'ln "${{MANIFEST_STAGE}}" "{manifest_final}"',
                'rm "${MANIFEST_STAGE}"',
                'MANIFEST_STAGE=""',
                f'mv "${{BUILD_ROOT}}/verified-prefix" "{sqlite_final}"',
                'rm -rf -- "${BUILD_ROOT}"',
                'BUILD_ROOT=""',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    retried = subprocess.run(
        ["bash", str(retry)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert retried.returncode == 0, retried.stderr
    assert checkout_final.is_dir()
    assert release_final.is_dir()
    assert manifest_final.read_text(encoding="utf-8") == "complete"
    assert sqlite_final.is_dir()


def test_candidate_manifest_failure_leaves_no_partial_and_retry_publishes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    stage = tmp_path / ".candidate.manifest.stage"
    final = tmp_path / "candidate.json"
    stage.touch(mode=0o600)
    real_write = installed_candidate.os.write
    writes = 0

    def fail_after_partial(fd: int, payload: object) -> int:
        nonlocal writes
        writes += 1
        if writes == 1:
            return real_write(fd, bytes(payload)[:3])
        raise OSError("injected manifest write failure")

    monkeypatch.setattr(installed_candidate.os, "write", fail_after_partial)
    with pytest.raises(OSError, match="injected manifest write failure"):
        installed_candidate.publish_candidate_manifest(stage, final, {"candidate": "one"})
    assert not stage.exists()
    assert not final.exists()

    monkeypatch.setattr(installed_candidate.os, "write", real_write)
    stage.touch(mode=0o600)
    installed_candidate.publish_candidate_manifest(stage, final, {"candidate": "one"})
    assert not stage.exists()
    assert final.read_text(encoding="utf-8") == '{\n  "candidate": "one"\n}\n'
    second = tmp_path / ".candidate.manifest.retry"
    second.touch(mode=0o600)
    with pytest.raises(FileExistsError):
        installed_candidate.publish_candidate_manifest(second, final, {"candidate": "two"})
    assert not second.exists()
    assert final.read_text(encoding="utf-8") == '{\n  "candidate": "one"\n}\n'


def test_staged_acceptance_lock_contains_the_full_test_runtime_and_inventory():
    exported = subprocess.run(
        [
            "uv",
            "export",
            "--frozen",
            "--extra",
            "acceptance",
            "--no-emit-project",
            "--format",
            "requirements-txt",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert exported.returncode == 0, exported.stderr
    requirements = exported.stdout.casefold()
    for package in (
        "pytest==",
        "playwright==",
        "pillow==",
        "torch==",
        "torchaudio==",
        "onnxruntime==1.23.2",
    ):
        assert package in requirements
    assert "--hash=sha256:" in requirements

    from moss_transcribe_diarize.phase2_acceptance import REQUIRED_PYTHON_TEST_FILES

    assert REQUIRED_PYTHON_TEST_FILES
    assert all((ROOT / relative).is_file() for relative in REQUIRED_PYTHON_TEST_FILES)


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
            str(INSTALLED_FRONTEND_PROBE),
            str(target),
            str(tmp_path / "installed.sqlite3"),
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(target)},
        check=False,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr

    venv = tmp_path / "wheel-command-venv"
    created = subprocess.run(
        [sys.executable, "-m", "venv", "--system-site-packages", str(venv)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert created.returncode == 0, created.stderr
    command_install = subprocess.run(
        [str(venv / "bin" / "pip"), "install", "--no-deps", str(wheel)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert command_install.returncode == 0, command_install.stderr
    command_smoke = subprocess.run(
        [str(venv / "bin" / "mtd-phase2-web"), "--help"],
        env={**os.environ, "PYTHONPATH": sysconfig.get_paths()["purelib"]},
        check=False,
        capture_output=True,
        text=True,
    )
    assert command_smoke.returncode == 0, command_smoke.stderr
    assert "--live-provider-manifest" in command_smoke.stdout
    cutover_smoke = subprocess.run(
        [str(venv / "bin" / "mtd-phase2-cutover"), "--help"],
        env={**os.environ, "PYTHONPATH": sysconfig.get_paths()["purelib"]},
        check=False,
        capture_output=True,
        text=True,
    )
    assert cutover_smoke.returncode == 0, cutover_smoke.stderr
    assert "{run,restore}" in cutover_smoke.stdout

    base_venv = tmp_path / "base-cutover-venv"
    base_created = subprocess.run(
        [sys.executable, "-m", "venv", str(base_venv)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert base_created.returncode == 0, base_created.stderr
    base_installed = subprocess.run(
        [str(base_venv / "bin" / "pip"), "install", "--no-deps", str(wheel)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert base_installed.returncode == 0, base_installed.stderr
    base_import = subprocess.run(
        [
            str(base_venv / "bin" / "python"),
            "-c",
            (
                "from moss_transcribe_diarize.phase2_g7_canary import "
                "validate_attended_g7; "
                "from moss_transcribe_diarize.app.phase2_cutover_cli import main"
            ),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert base_import.returncode == 0, base_import.stderr
    base_help = subprocess.run(
        [str(base_venv / "bin" / "mtd-phase2-cutover"), "--help"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert base_help.returncode == 0, base_help.stderr
    assert "{run,restore}" in base_help.stdout
