from __future__ import annotations

import hashlib
import importlib.util
import ipaddress
import json
import os
import platform
import plistlib
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "macos" / "MOSSCapture"
TIMEOUT = 8.0


def test_built_macos_app_cli_cross_real_uds_and_private_tls_server():
    if platform.system() != "Darwin":
        pytest.skip("macOS real UDS tracer is Darwin-only.")
    if importlib.util.find_spec("uvicorn") is None:
        pytest.fail("uvicorn is required for the Darwin real UDS tracer.")
    if importlib.util.find_spec("fastapi") is None:
        pytest.fail("fastapi is required for the Darwin real UDS tracer.")
    if shutil.which("openssl") is None:
        pytest.fail("openssl is required to create the per-test TLS certificate.")
    if shutil.which("codesign") is None:
        pytest.fail("codesign is required to ad-hoc sign the per-test app bundle.")

    private_ip = _private_non_loopback_ipv4()
    if private_ip is None:
        pytest.fail("Darwin real UDS tracer requires a private non-loopback IPv4 address.")

    bin_dir = _swift_bin_dir()
    app_exe = bin_dir / "MOSSCaptureApp"
    cli_exe = bin_dir / "mtd-capture"
    assert app_exe.is_file(), f"built app product missing: {app_exe}"
    assert cli_exe.is_file(), f"built CLI product missing: {cli_exe}"

    with tempfile.TemporaryDirectory(prefix="mtd5-", dir="/tmp") as tmp:
        tmp_path = Path(tmp)
        cert = tmp_path / "live.pem"
        key = tmp_path / "live.key"
        _make_certificate(cert=cert, key=key, private_ip=private_ip)
        cert_pin = _certificate_sha256(cert)
        port = _reserve_port()
        server_url = f"https://{private_ip}:{port}"
        loopback_url = f"https://127.0.0.1:{port}"
        server_script = _write_server_script(tmp_path)
        socket_path = tmp_path / "control.sock"
        store_path = tmp_path / "secrets.json"
        app_log = tmp_path / "app.log"
        server_log = tmp_path / "server.log"
        bundled_app_exe = _make_temp_app_bundle(app_exe, tmp_path)

        server = _start_server(
            server_script=server_script,
            host="0.0.0.0",
            port=port,
            cert=cert,
            key=key,
            cert_pin=cert_pin,
            log=server_log,
            tmp_path=tmp_path,
        )
        app = None
        try:
            _wait_for_https(f"{loopback_url}/api/runtime", server, server_log)
            pairing_payload = _issue_pairing(loopback_url)

            env = os.environ.copy()
            env.update(
                {
                    "MOSS_CAPTURE_CONTROL_SOCKET": str(socket_path),
                    "MOSS_CAPTURE_SECRET_STORE_PATH": str(store_path),
                    "MOSS_CAPTURE_SKIP_LAUNCH": "1",
                }
            )
            app = _start_app(bundled_app_exe, env=env, log=app_log, socket_path=socket_path)

            pair = _run_cli(cli_exe, ["pair", "--server", server_url], env=env, stdin=pairing_payload)
            assert pair.returncode == 0, pair.diagnostic
            pair_body = pair.json()
            assert pair_body["ok"] is True
            assert pair_body["sessionID"] == "macos-tracer-session"
            assert pair_body["portalURL"] == f"{server_url}/live"
            assert "?" not in pair_body["portalURL"]
            assert "#" not in pair_body["portalURL"]
            _assert_secret_absent(pair.output, pairing_payload.decode("utf-8"))

            persisted = _read_store(store_path)
            view_token = persisted["capture-view-token"]
            assert persisted["capture-certificate-pin"] == cert_pin
            assert persisted["capture-server-url"] == server_url
            assert persisted["capture-session-id"] == "macos-tracer-session"
            assert persisted["capture-device-id"]
            assert persisted["capture-bearer"]
            assert view_token
            _assert_secret_absent(pair.output, view_token)

            first_device_id = persisted["capture-device-id"]
            _terminate(app)
            app = None
            _remove_socket(socket_path)
            app = _start_app(bundled_app_exe, env=env, log=app_log, socket_path=socket_path)

            restarted = _read_store(store_path)
            assert restarted["capture-device-id"] == first_device_id
            start = _run_cli(cli_exe, ["start", "--label", "tracer"], env=env)
            if start.returncode == 0:
                body = start.json()
                assert body["ok"] is True
                assert body["running"] is True
                assert int(body["publishedFrameCount"]) > 0
                snapshot = _server_snapshot(
                    server_url=server_url,
                    session_id="macos-tracer-session",
                    bearer_token=persisted["capture-bearer"],
                )
                observed_samples = _assert_server_observed_lane_frames(snapshot)
                status = _run_cli(cli_exe, ["status"], env=env, timeout=5.0)
                assert status.returncode == 0, status.diagnostic
                status_body = status.json()
                assert status_body["ok"] is True
                assert status_body["running"] is True
                cleanup_started = time.monotonic()
                try:
                    cleanup_stop = _run_cli(cli_exe, ["stop"], env=env, timeout=5.0)
                    cleanup_elapsed = time.monotonic() - cleanup_started
                except subprocess.TimeoutExpired as exc:
                    pytest.fail(
                        "Darwin real UDS tracer requires the no-TCC path, but native start "
                        "succeeded and bounded cleanup stop timed out: "
                        f"publishedFrameCount={body.get('publishedFrameCount')}: {exc}"
                    )
                assert cleanup_elapsed < 5.0, cleanup_stop.diagnostic
                stop_body = cleanup_stop.json()
                assert cleanup_stop.returncode == 0, cleanup_stop.diagnostic
                assert stop_body["ok"] is True
                assert stop_body["running"] is False
                assert int(stop_body["publishedFrameCount"]) >= int(body["publishedFrameCount"])
                assert observed_samples > 0
            else:
                assert start.returncode == 70, start.diagnostic
                start_body = start.json()
                assert start_body["ok"] is False
                assert start_body["error"] != "missingCaptureConfiguration"
                assert "permissionDenied" in start_body["error"]

                stopped_at = time.monotonic()
                stop = _run_cli(cli_exe, ["stop"], env=env, timeout=5.0)
                assert time.monotonic() - stopped_at < 5.0
                assert stop.returncode == 70, stop.diagnostic
                assert stop.json() == {"ok": False, "error": "notRunning"}

                status = _run_cli(cli_exe, ["status"], env=env)
                assert status.returncode == 0, status.diagnostic
                assert status.json()["ok"] is True
        finally:
            if app is not None:
                _terminate(app)
            _terminate(server)
            _remove_socket(socket_path)
            if store_path.exists():
                store_path.unlink()
            assert not _pid_alive(server.pid)
            assert app is None or not _pid_alive(app.pid)
            assert not socket_path.exists()
            assert not store_path.exists()


class _CLIResult:
    def __init__(self, completed: subprocess.CompletedProcess[bytes]):
        self.returncode = completed.returncode
        self.stdout = completed.stdout
        self.stderr = completed.stderr
        self.output = completed.stdout + completed.stderr
        self.diagnostic = (
            f"exit={completed.returncode} stdout={completed.stdout!r} stderr={completed.stderr!r}"
        )

    def json(self) -> dict[str, Any]:
        try:
            return json.loads(self.stdout.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise AssertionError(self.diagnostic) from exc


def _swift_bin_dir() -> Path:
    completed = subprocess.run(
        ["swift", "build", "--package-path", str(PACKAGE_ROOT), "--show-bin-path"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )
    return Path(completed.stdout.strip())


def _make_temp_app_bundle(app_exe: Path, tmp_path: Path) -> Path:
    bundle_id = f"com.alphasight.moss.capture.tracer.{os.getpid()}.{time.monotonic_ns()}"
    bundle = tmp_path / "MOSSCaptureTracer.app"
    contents = bundle / "Contents"
    macos = contents / "MacOS"
    macos.mkdir(parents=True)
    bundled_exe = macos / "MOSSCaptureApp"
    shutil.copy2(app_exe, bundled_exe)
    os.chmod(bundled_exe, 0o755)

    source_info = plistlib.loads((PACKAGE_ROOT / "Resources" / "Info.plist").read_bytes())
    source_info.update(
        {
            "CFBundleIdentifier": bundle_id,
            "CFBundleExecutable": "MOSSCaptureApp",
            "CFBundlePackageType": "APPL",
        }
    )
    (contents / "Info.plist").write_bytes(plistlib.dumps(source_info, sort_keys=False))

    subprocess.run(
        ["codesign", "--force", "--sign", "-", str(bundle)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        timeout=TIMEOUT,
    )
    return bundled_exe


def _private_non_loopback_ipv4() -> str | None:
    completed = subprocess.run(
        ["ifconfig"],
        check=True,
        capture_output=True,
        text=True,
        timeout=3.0,
    )
    for line in completed.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == "inet":
            try:
                address = ipaddress.ip_address(parts[1])
            except ValueError:
                continue
            if address.version == 4 and address.is_private and not address.is_loopback:
                return str(address)
    return None


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return int(sock.getsockname()[1])


def _make_certificate(*, cert: Path, key: Path, private_ip: str) -> None:
    config = cert.with_suffix(".cnf")
    config.write_text(
        "\n".join(
            [
                "[req]",
                "distinguished_name=dn",
                "x509_extensions=v3_req",
                "prompt=no",
                "[dn]",
                "CN=moss-tracer",
                "[v3_req]",
                "subjectAltName=@alt_names",
                "[alt_names]",
                f"IP.1={private_ip}",
                "IP.2=127.0.0.1",
                "DNS.1=localhost",
                "",
            ]
        ),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-sha256",
            "-config",
            str(config),
        ],
        check=True,
        capture_output=True,
        timeout=TIMEOUT,
    )
    os.chmod(key, 0o600)
    os.chmod(cert, 0o600)


def _certificate_sha256(cert: Path) -> str:
    data = cert.read_bytes()
    der = ssl.PEM_cert_to_DER_cert(data.decode("ascii"))
    return hashlib.sha256(der).hexdigest()


def _write_server_script(tmp_path: Path) -> Path:
    script = tmp_path / "live_server.py"
    script.write_text(
        """
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import uvicorn

root = Path(sys.argv[1])
host = sys.argv[2]
port = int(sys.argv[3])
cert = sys.argv[4]
key = sys.argv[5]
cert_pin = sys.argv[6]
state = Path(sys.argv[7])
runs = Path(sys.argv[8])

sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location("moss_live_api_helpers", root / "tests" / "test_live_api.py")
helpers = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(helpers)

from moss_transcribe_diarize.app.server import create_app

app = create_app(
    model_path="fake-model",
    runs_dir=runs,
    live_enabled=True,
    live_auth_state_path=state,
    live_server_cert_sha256=cert_pin,
    live_helper_lease_seconds=30.0,
    live_runtime_factory=lambda: helpers.make_live_runtime(
        max_retained_samples=16_000_000,
        session_id="macos-tracer-session",
    ),
)

uvicorn.run(
    app,
    host=host,
    port=port,
    ssl_certfile=cert,
    ssl_keyfile=key,
    proxy_headers=False,
    log_level="warning",
)
""".lstrip(),
        encoding="utf-8",
    )
    return script


def _start_server(
    *,
    server_script: Path,
    host: str,
    port: int,
    cert: Path,
    key: Path,
    cert_pin: str,
    log: Path,
    tmp_path: Path,
) -> subprocess.Popen[bytes]:
    handle = log.open("ab")
    return subprocess.Popen(
        [
            sys.executable,
            str(server_script),
            str(ROOT),
            host,
            str(port),
            str(cert),
            str(key),
            cert_pin,
            str(tmp_path / "live-auth.json"),
            str(tmp_path / "runs"),
        ],
        cwd=ROOT,
        stdout=handle,
        stderr=subprocess.STDOUT,
        close_fds=True,
    )


def _wait_for_https(url: str, process: subprocess.Popen[bytes], log: Path) -> None:
    deadline = time.monotonic() + TIMEOUT
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail(f"uvicorn exited early with {process.returncode}: {log.read_text(errors='replace')}")
        try:
            _json_request("GET", url)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.05)
    pytest.fail(f"uvicorn did not become ready: {last_error}; log={log.read_text(errors='replace')}")


def _issue_pairing(loopback_url: str) -> bytes:
    response = _json_request("POST", f"{loopback_url}/api/live/pairing-codes")
    payload = response["pairing_payload"]
    assert isinstance(payload, str)
    return payload.encode("utf-8")


def _server_snapshot(*, server_url: str, session_id: str, bearer_token: str) -> dict[str, Any]:
    return _json_request(
        "GET",
        f"{server_url}/api/live/sessions/{session_id}/snapshot?since_version=0",
        bearer_token=bearer_token,
    )


def _assert_server_observed_lane_frames(snapshot: dict[str, Any]) -> int:
    v2_session = snapshot["v2_session"]
    assert v2_session["status"] == "active"
    lanes = v2_session["lanes"]
    observed_samples = 0
    observed_lanes = 0
    for lane_name in ("system", "microphone"):
        accepted = int(lanes[lane_name]["accepted_samples"])
        if accepted > 0:
            observed_lanes += 1
            observed_samples += accepted
    assert observed_lanes >= 1
    return observed_samples


def _json_request(method: str, url: str, *, bearer_token: str | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, method=method)
    if bearer_token is not None:
        request.add_header("Authorization", f"Bearer {bearer_token}")
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, context=context, timeout=2.0) as response:
        return json.loads(response.read().decode("utf-8"))


def _start_app(
    app_exe: Path,
    *,
    env: dict[str, str],
    log: Path,
    socket_path: Path,
) -> subprocess.Popen[bytes]:
    if socket_path.exists():
        pytest.fail(f"refusing doubled app over existing socket: {socket_path}")
    handle = log.open("ab")
    app = subprocess.Popen(
        [str(app_exe)],
        cwd=ROOT,
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        close_fds=True,
    )
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        if app.poll() is not None:
            pytest.fail(f"MOSSCaptureApp exited early with {app.returncode}: {log.read_text(errors='replace')}")
        if socket_path.exists():
            mode = stat.S_IMODE(socket_path.stat().st_mode)
            assert mode == 0o600
            return app
        time.sleep(0.05)
    pytest.fail(f"MOSSCaptureApp did not bind UDS: {log.read_text(errors='replace')}")


def _run_cli(
    cli_exe: Path,
    args: list[str],
    *,
    env: dict[str, str],
    stdin: bytes = b"",
    timeout: float = TIMEOUT,
) -> _CLIResult:
    completed = subprocess.run(
        [str(cli_exe), *args],
        cwd=ROOT,
        env=env,
        input=stdin,
        capture_output=True,
        timeout=timeout,
    )
    return _CLIResult(completed)


def _read_store(path: Path) -> dict[str, str]:
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
    data = json.loads(path.read_text(encoding="utf-8"))
    values = data["values"]
    assert isinstance(values, dict)
    return values


def _assert_secret_absent(output: bytes, secret: str) -> None:
    assert secret.encode("utf-8") not in output


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3.0)


def _remove_socket(path: Path) -> None:
    if path.exists():
        path.unlink()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True
