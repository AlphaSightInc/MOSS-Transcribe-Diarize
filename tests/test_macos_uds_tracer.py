from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import ipaddress
import json
import os
import platform
import plistlib
import re
import shutil
import socket
import ssl
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "macos" / "MOSSCapture"
TIMEOUT = 8.0
BUILD_TIMEOUT = 120.0
ALLOWED_PEER_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")
)
# App Transport Security exempts "local networking" — the RFC 1918 ranges and link-local — from
# its CA-chain requirement, and applies in full to everything else. It also applies to an `.app`
# bundle and not to a bare executable, and it overrides a URLSession delegate that has already
# accepted the leaf. Production dials this range (the tailnet), so a tracer that only ever binds
# an RFC 1918 address proves a transport production never takes.
NON_EXEMPT_PEER_NETWORK = ipaddress.ip_network("100.64.0.0/10")

# The one fixed path in this tracer. Everything else the tracer touches — certificate,
# server, port, UDS, secret store, artifacts — stays per-test temporary. The lab app is
# installed once, its identity evidence is captured on that first install, and every later
# node re-asserts the recorded evidence instead of rebuilding: rebuilding at the same path
# and bundle identifier is not continuity proof.
LAB_ROOT = PACKAGE_ROOT / ".build" / "idea044-lab"
LAB_BUNDLE = LAB_ROOT / "MOSSCapture.app"
LAB_EXECUTABLE_NAME = "MOSSCaptureApp"
LAB_EVIDENCE = LAB_ROOT / "first-install-evidence.json"
LAB_LOCK = LAB_ROOT / "install.lock"
LAB_LOCK_TIMEOUT = 180.0
LAB_EVIDENCE_SCHEMA = "idea044-lab-bundle-evidence.v1"
LAB_BUNDLE_IDENTIFIER = "com.alphasight.moss.capture"
LAB_USAGE_DESCRIPTION_KEYS = (
    "NSAudioCaptureUsageDescription",
    "NSMicrophoneUsageDescription",
)
# The declaration that lets the app's pinned transport reach a peer ATS does not exempt. No test
# on one host can observe its effect — every server this tracer starts is reached over loopback,
# which ATS exempts unconditionally — so the bundle carrying it is what the tracer can gate.
LAB_TRANSPORT_SECURITY_KEY = "NSAppTransportSecurity"


def test_lab_app_bundle_is_one_immutable_first_install_reused_across_nodes():
    if platform.system() != "Darwin":
        pytest.skip("macOS lab bundle inventory is Darwin-only.")
    if shutil.which("codesign") is None:
        pytest.fail("codesign is required to ad-hoc sign the fixed lab app bundle.")

    lab = _lab_bundle()

    assert lab.bundle == LAB_BUNDLE
    assert lab.bundle.is_relative_to(PACKAGE_ROOT / ".build")
    assert lab.bundle.name == "MOSSCapture.app"
    assert lab.executable == LAB_BUNDLE / "Contents" / "MacOS" / LAB_EXECUTABLE_NAME
    assert lab.executable.is_file()

    evidence = lab.evidence
    assert evidence["schema"] == LAB_EVIDENCE_SCHEMA
    assert evidence["bundle_path"] == LAB_BUNDLE.relative_to(ROOT).as_posix()
    assert evidence["bundle_identifier"] == LAB_BUNDLE_IDENTIFIER
    assert evidence["bundle_executable"] == LAB_EXECUTABLE_NAME

    # Both usage strings ship in the lab bundle, byte-identical to the product Info.plist,
    # so the permission prompts the coordinator drives are the shipped ones.
    product_info = plistlib.loads((PACKAGE_ROOT / "Resources" / "Info.plist").read_bytes())
    for key in LAB_USAGE_DESCRIPTION_KEYS:
        description = evidence["usage_descriptions"][key]
        assert description.strip()
        assert description == product_info[key]

    # And so does the transport declaration, which is the only reason a signed bundle can reach
    # the live server: ATS applies to bundles, not to bare executables, and overrides the pinning
    # delegate's acceptance of the self-signed leaf. Keep it un-siblinged — NSAllowsLocalNetworking
    # or either NSAllowsArbitraryLoadsIn* key makes the OS ignore NSAllowsArbitraryLoads.
    transport = evidence["app_transport_security"]
    assert transport == product_info[LAB_TRANSPORT_SECURITY_KEY]
    assert transport == {"NSAllowsArbitraryLoads": True}

    assert re.fullmatch(r"[0-9a-f]{64}", evidence["product_info_plist_sha256"])
    assert evidence["product_info_plist_sha256"] == _product_info_plist_sha256()
    assert re.fullmatch(r"[0-9a-f]{64}", evidence["executable_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", evidence["bundle_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", evidence["built_product"]["sha256"])
    assert evidence["designated_requirement"].startswith("designated =>")
    assert set(evidence["bundle_inventory"]) == {
        "Contents/Info.plist",
        f"Contents/MacOS/{LAB_EXECUTABLE_NAME}",
        "Contents/_CodeSignature/CodeResources",
    }
    assert (
        evidence["bundle_inventory"][f"Contents/MacOS/{LAB_EXECUTABLE_NAME}"]
        == evidence["executable_sha256"]
    )

    # The installed executable carries the built product's Mach-O identity, and the ad-hoc
    # signature is over the bundle — not over the bare SwiftPM product.
    assert _macho_uuid(lab.executable) == evidence["built_product"]["macho_uuid"]

    # Re-entering the install path must reuse, never reinstall: the evidence file itself is
    # written once, so an unchanged inode, mtime and payload is the continuity proof.
    before_stat = LAB_EVIDENCE.stat()
    before_bytes = LAB_EVIDENCE.read_bytes()
    reused = _install_or_reuse_lab_bundle()
    after_stat = LAB_EVIDENCE.stat()
    assert reused.evidence == evidence
    assert LAB_EVIDENCE.read_bytes() == before_bytes
    assert (after_stat.st_ino, after_stat.st_mtime_ns) == (
        before_stat.st_ino,
        before_stat.st_mtime_ns,
    )

    # And the same recorded hashes still describe the bundle on disk.
    _assert_lab_bundle_unchanged(lab)


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

    lab = _lab_bundle()

    tmp_root: Path | None = None
    with tempfile.TemporaryDirectory(prefix="mtd5-", dir="/tmp") as tmp:
        tmp_path = Path(tmp)
        tmp_root = tmp_path
        cert = tmp_path / "live.pem"
        key = tmp_path / "live.key"
        _make_certificate(cert=cert, key=key, private_ip=private_ip)
        cert_pin = _certificate_sha256(cert)
        server_script = _write_server_script(tmp_path)
        socket_path = tmp_path / "control.sock"
        store_path = tmp_path / "secrets.json"
        artifact_dir = tmp_path / "artifacts"
        app_log = tmp_path / "app.log"
        server_log = tmp_path / "server.log"
        pasteboard_name = f"com.alphasight.moss.capture.tracer.{os.getpid()}.{time.monotonic_ns()}"
        bundled_app_exe = lab.executable
        _assert_bundled_product_identity(
            bundled_app_exe,
            built_product=app_exe,
            expected_bundle=LAB_BUNDLE,
        )
        _assert_lab_bundle_unchanged(lab)

        server = None
        app = None
        try:
            server, port = _start_server(
                server_script=server_script,
                host="0.0.0.0",
                cert=cert,
                key=key,
                cert_pin=cert_pin,
                log=server_log,
                tmp_path=tmp_path,
            )
            server_url = f"https://{private_ip}:{port}"
            loopback_url = f"https://127.0.0.1:{port}"
            runtime = _wait_for_https(f"{loopback_url}/api/runtime", server, server_log)
            _assert_production_server_runtime(runtime)
            pairing_payload = _issue_pairing(loopback_url)

            env = os.environ.copy()
            env.update(
                {
                    "MOSS_CAPTURE_CONTROL_SOCKET": str(socket_path),
                    "MOSS_CAPTURE_SECRET_STORE_PATH": str(store_path),
                    "MOSS_CAPTURE_PASTEBOARD_NAME": pasteboard_name,
                    "MOSS_CAPTURE_SKIP_LAUNCH": "1",
                }
            )
            app = _start_app(bundled_app_exe, env=env, log=app_log, socket_path=socket_path)
            initial_store = _read_store(store_path)
            control_secret = initial_store["local-control-secret"]
            status_artifact = _assert_uds_product_server_identity(
                socket_path,
                expected_pid=app.pid,
                control_secret=control_secret,
            )
            _write_secret_clean_artifact(
                artifact_dir,
                "status-response.bin",
                status_artifact,
                secrets=(control_secret,),
            )

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
            for secret in (
                control_secret,
                pairing_payload.decode("utf-8"),
                cert_pin,
                persisted["capture-bearer"],
                view_token,
            ):
                _assert_secret_absent(pair.output, secret)

            first_device_id = persisted["capture-device-id"]
            auth_state = json.loads((tmp_path / "live-auth.json").read_text(encoding="utf-8"))
            assert set(auth_state["devices"]) == {first_device_id}
            _terminate(app)
            app = None
            _remove_socket(socket_path)
            app = _start_app(bundled_app_exe, env=env, log=app_log, socket_path=socket_path)
            restarted_status = _assert_uds_product_server_identity(
                socket_path,
                expected_pid=app.pid,
                control_secret=control_secret,
            )
            _write_secret_clean_artifact(
                artifact_dir,
                "status-after-restart.bin",
                restarted_status,
                secrets=(
                    control_secret,
                    pairing_payload.decode("utf-8"),
                    cert_pin,
                    persisted["capture-bearer"],
                    persisted["capture-view-token"],
                ),
            )

            restarted = _read_store(store_path)
            assert restarted["capture-device-id"] == first_device_id
            start = _run_cli(cli_exe, ["start", "--label", "tracer"], env=env)
            if start.returncode != 0:
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
            else:
                start_body = start.json()
                assert start_body["ok"] is True
                assert start_body["running"] is True
                snapshot = _wait_for_server_observed_dual_lane_frames(
                    server_url=server_url,
                    session_id="macos-tracer-session",
                    bearer_token=restarted["capture-bearer"],
                )
                _assert_server_observed_dual_lane_frames(snapshot)

                status = _run_cli(cli_exe, ["status"], env=env, timeout=5.0)
                assert status.returncode == 0, status.diagnostic
                assert status.json()["ok"] is True
                assert status.json()["running"] is True

                stopped_at = time.monotonic()
                stop = _run_cli(cli_exe, ["stop"], env=env, timeout=5.0)
                assert time.monotonic() - stopped_at < 5.0
                assert stop.returncode == 0, stop.diagnostic
                assert stop.json()["ok"] is True
                assert stop.json()["running"] is False

            _replace_store_value(
                store_path,
                key="capture-certificate-pin",
                value="0" * 64,
            )
            second_pairing_payload = _issue_pairing(loopback_url)
            # Typed the way an operator types it: paste, Return, Ctrl-D. The trailing newline is
            # part of ending the input, not part of the payload, and it must survive the whole
            # real path - stdin, the UDS hop, the app's parse and the HTTPS body the server
            # actually reads. Feeding the clean bytes here would only ever prove the machine's
            # own round trip.
            second_pair = _run_cli(
                cli_exe,
                ["pair", "--server", server_url],
                env=env,
                stdin=second_pairing_payload + b"\n",
            )
            assert second_pair.returncode == 0, second_pair.diagnostic
            _assert_secret_absent(
                second_pair.output,
                second_pairing_payload.decode("utf-8"),
            )
            repinned = _read_store(store_path)
            assert repinned["capture-device-id"] == first_device_id
            assert repinned["capture-certificate-pin"] == cert_pin
            assert repinned["capture-session-id"] == "macos-tracer-session-repin"
            for secret in (
                control_secret,
                second_pairing_payload.decode("utf-8"),
                cert_pin,
                repinned["capture-bearer"],
                repinned["capture-view-token"],
            ):
                _assert_secret_absent(second_pair.output, secret)
            auth_state = json.loads((tmp_path / "live-auth.json").read_text(encoding="utf-8"))
            assert set(auth_state["devices"]) == {first_device_id}

            handoff = _run_cli(cli_exe, ["handoff"], env=env)
            assert handoff.returncode == 0, handoff.diagnostic
            handoff_body = handoff.json()
            assert handoff_body == {
                "ok": True,
                "sessionID": "macos-tracer-session-repin",
                "portalURL": f"{server_url}/live",
                "viewAuthority": "copied-to-pasteboard",
            }
            for secret in (
                control_secret,
                second_pairing_payload.decode("utf-8"),
                cert_pin,
                repinned["capture-bearer"],
                repinned["capture-view-token"],
            ):
                _assert_secret_absent(handoff.output, secret)
            _assert_named_pasteboard_matches_store(
                pasteboard_name=pasteboard_name,
                store_path=store_path,
            )

            status = _run_cli(cli_exe, ["status"], env=env)
            assert status.returncode == 0, status.diagnostic
            assert status.json()["ok"] is True
            _write_secret_clean_artifact(
                artifact_dir,
                "cli-status-output.bin",
                status.output,
                secrets=(
                    control_secret,
                    pairing_payload.decode("utf-8"),
                    second_pairing_payload.decode("utf-8"),
                    cert_pin,
                    persisted["capture-bearer"],
                    persisted["capture-view-token"],
                    repinned["capture-bearer"],
                    repinned["capture-view-token"],
                ),
            )
            assert sorted(path.name for path in artifact_dir.iterdir()) == [
                "cli-status-output.bin",
                "status-after-restart.bin",
                "status-response.bin",
            ]
        finally:
            if app is not None:
                _terminate(app)
            if server is not None:
                _terminate(server)
            _remove_socket(socket_path)
            if store_path.exists():
                store_path.unlink()
            assert server is None or not _pid_alive(server.pid)
            assert app is None or not _pid_alive(app.pid)
            assert not socket_path.exists()
            assert not store_path.exists()
    assert tmp_root is not None and not tmp_root.exists()
    # Running the app out of the fixed lab bundle must not have mutated it.
    _assert_lab_bundle_unchanged(lab)


def test_bundled_app_on_the_production_address_range_still_refuses_an_unpinned_leaf():
    """The bundle pairs over the address range production dials, and still pins what it gets.

    Two things this node deliberately does *not* claim. It does not observe App Transport
    Security: the server is on this host, so however the peer address is written the connection
    is routed over loopback, which ATS exempts unconditionally. Measured on MacStudio
    2026-07-28 — bundled probe to this host's own 100.64.0.1 → 200, to the remote 100.64.0.8 →
    NSURLErrorDomain -1200 / _kCFStreamErrorCodeKey -9802. So no single-host test can be the
    ATS regression gate; the product Info.plist declaration is gated by shape instead, in
    test_lab_app_bundle_is_one_immutable_first_install_reused_across_nodes.

    What it does prove is the other half of that declaration's safety case. Turning ATS off
    hands the whole trust decision to PinnedCertificateURLSessionDelegate, so phase two serves a
    certificate the pairing payload's pin does not describe and the client must refuse it —
    non-vacuously, because phase one already paired against the same code path and the only
    thing that changed is the leaf.
    """
    if platform.system() != "Darwin":
        pytest.skip("macOS App Transport Security tracer is Darwin-only.")
    for module in ("uvicorn", "fastapi"):
        if importlib.util.find_spec(module) is None:
            pytest.fail(f"{module} is required for the Darwin ATS tracer.")
    for tool in ("openssl", "codesign"):
        if shutil.which(tool) is None:
            pytest.fail(f"{tool} is required for the Darwin ATS tracer.")

    peer_ip = _non_ats_exempt_ipv4()
    if peer_ip is None:
        # Not a skip: silently falling back to whatever address ifconfig lists first is how the
        # sibling node came to exercise only RFC 1918 for this product's whole life.
        pytest.fail(
            f"this node needs an address in {NON_EXEMPT_PEER_NETWORK} on this host — it is the "
            "range production dials. Bring the tailnet interface up."
        )

    cli_exe = _swift_bin_dir() / "mtd-capture"
    assert cli_exe.is_file(), f"built CLI product missing: {cli_exe}"
    lab = _lab_bundle()

    with tempfile.TemporaryDirectory(prefix="mtd5-ats-", dir="/tmp") as tmp:
        tmp_path = Path(tmp)
        server_script = _write_server_script(tmp_path)
        socket_path = tmp_path / "control.sock"
        store_path = tmp_path / "secrets.json"
        app_log = tmp_path / "app.log"
        env = os.environ.copy()
        env.update(
            {
                "MOSS_CAPTURE_CONTROL_SOCKET": str(socket_path),
                "MOSS_CAPTURE_SECRET_STORE_PATH": str(store_path),
                "MOSS_CAPTURE_SKIP_LAUNCH": "1",
            }
        )

        served = tmp_path / "served"
        served.mkdir()
        cert = served / "live.pem"
        key = served / "live.key"
        _make_certificate(cert=cert, key=key, private_ip=peer_ip)
        cert_pin = _certificate_sha256(cert)

        # A second, never-served certificate: the pin the client is handed in phase two.
        other = tmp_path / "other"
        other.mkdir()
        other_cert = other / "live.pem"
        _make_certificate(cert=other_cert, key=other / "live.key", private_ip=peer_ip)
        other_pin = _certificate_sha256(other_cert)
        assert other_pin != cert_pin

        app = None
        honest = None
        mismatched = None
        try:
            app = _start_app(lab.executable, env=env, log=app_log, socket_path=socket_path)

            # Phase one — the production transport must work at all.
            honest_dir = tmp_path / "honest"
            honest_dir.mkdir()
            honest, honest_port = _start_server(
                server_script=server_script,
                host="0.0.0.0",
                cert=cert,
                key=key,
                cert_pin=cert_pin,
                log=honest_dir / "server.log",
                tmp_path=honest_dir,
            )
            _wait_for_https(
                f"https://127.0.0.1:{honest_port}/api/runtime",
                honest,
                honest_dir / "server.log",
            )
            payload = _issue_pairing(f"https://127.0.0.1:{honest_port}")
            server_url = f"https://{peer_ip}:{honest_port}"
            pair = _run_cli(cli_exe, ["pair", "--server", server_url], env=env, stdin=payload)
            assert pair.returncode == 0, (
                "the bundled app could not pair over the production address range: "
                f"{pair.diagnostic}"
            )
            body = pair.json()
            assert body["ok"] is True
            assert body["portalURL"] == f"{server_url}/live"
            paired = _read_store(store_path)
            assert paired["capture-server-url"] == server_url
            assert paired["capture-certificate-pin"] == cert_pin
            assert paired["capture-bearer"]
            _assert_secret_absent(pair.output, payload.decode("utf-8"))
            _assert_secret_absent(pair.output, paired["capture-bearer"])
            _terminate(honest)
            honest = None

            # Phase two — same transport, but the served leaf is not the pinned one. Phase one
            # is what makes this non-vacuous: the only thing that changed is the certificate.
            mismatched_dir = tmp_path / "mismatched"
            mismatched_dir.mkdir()
            mismatched, mismatched_port = _start_server(
                server_script=server_script,
                host="0.0.0.0",
                cert=cert,
                key=key,
                cert_pin=other_pin,
                log=mismatched_dir / "server.log",
                tmp_path=mismatched_dir,
            )
            _wait_for_https(
                f"https://127.0.0.1:{mismatched_port}/api/runtime",
                mismatched,
                mismatched_dir / "server.log",
            )
            mismatched_payload = _issue_pairing(f"https://127.0.0.1:{mismatched_port}")
            assert mismatched_payload.decode("utf-8").endswith(f".{other_pin}")
            refused = _run_cli(
                cli_exe,
                ["pair", "--server", f"https://{peer_ip}:{mismatched_port}"],
                env=env,
                stdin=mismatched_payload,
            )
            assert refused.returncode != 0, (
                "the pinned transport accepted a leaf its pin does not describe: "
                f"{refused.diagnostic}"
            )
            # A refusal the operator cannot name is how the ATS block survived a whole merge.
            # This is the same shape of failure — URLSession cancels the task, so the error that
            # comes back is an NSURLErrorDomain code the app has never reasoned about — measured
            # here through the real process rather than through a stub.
            refusal = refused.json()
            assert refusal["ok"] is False, refused.diagnostic
            assert refusal["error"] == "control_failed", refused.diagnostic
            detail = refusal["errorDetail"]
            assert detail["domain"] == "NSURLErrorDomain", refused.diagnostic
            # -999 is NSURLErrorCancelled: the pinning delegate cancelled the challenge, so *this
            # client* refused the leaf. That is exactly the distinction the operator could not
            # make before — a connection the OS refused instead arrives as -1200 with an
            # underlying stream code. Same bare `control_failed` for both; different detail.
            assert detail["code"] == -999, refused.diagnostic
            # Omitted, not zeroed: a cancelled challenge has no underlying reason to report.
            assert "underlyingCode" not in detail, refused.diagnostic
            # Numbers and one constant: the detail names the fault without naming the deployment.
            assert set(detail) == {"domain", "code"}, refused.diagnostic
            assert str(peer_ip) not in json.dumps(detail), refused.diagnostic
            # The refusal is the client's: the server would have accepted this payload, since the
            # pin it carries is the one that server was configured with.
            unchanged = _read_store(store_path)
            assert unchanged["capture-certificate-pin"] == cert_pin
            assert unchanged["capture-bearer"] == paired["capture-bearer"]
            assert unchanged["capture-server-url"] == server_url
            _assert_secret_absent(refused.output, mismatched_payload.decode("utf-8"))
        finally:
            if app is not None:
                _terminate(app)
            for process in (honest, mismatched):
                if process is not None:
                    _terminate(process)
            _remove_socket(socket_path)
            if store_path.exists():
                store_path.unlink()
        assert not socket_path.exists()
    _assert_lab_bundle_unchanged(lab)


def test_permission_denial_contract_isolated_from_real_capture_path():
    if platform.system() != "Darwin":
        pytest.skip("macOS permission-denial CLI harness is Darwin-only.")

    cli_exe = _swift_bin_dir() / "mtd-capture"
    assert cli_exe.is_file(), f"built CLI product missing: {cli_exe}"
    with tempfile.TemporaryDirectory(prefix="mtd5-denied-", dir="/tmp") as tmp:
        tmp_path = Path(tmp)
        socket_path = tmp_path / "control.sock"
        store_path = tmp_path / "secrets.json"
        control_secret = "isolated-denial-control-secret"
        store_path.write_text(
            json.dumps({"values": {"local-control-secret": control_secret}}),
            encoding="utf-8",
        )
        store_path.chmod(0o600)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(socket_path))
        socket_path.chmod(0o600)
        server.listen(1)
        errors: list[BaseException] = []
        thread = threading.Thread(
            target=_serve_permission_denial_once,
            args=(server, control_secret, errors),
            daemon=True,
        )
        thread.start()
        env = os.environ.copy()
        env.update(
            {
                "MOSS_CAPTURE_CONTROL_SOCKET": str(socket_path),
                "MOSS_CAPTURE_SECRET_STORE_PATH": str(store_path),
                "MOSS_CAPTURE_SKIP_LAUNCH": "1",
            }
        )
        try:
            start = _run_cli(cli_exe, ["start", "--label", "denied-harness"], env=env)
            if start.returncode == 0:
                pytest.fail("isolated permission-denial harness accepted capture start")
            assert start.returncode == 70, start.diagnostic
            assert start.json() == {
                "ok": False,
                "error": 'permissionDenied("microphone")',
            }
        finally:
            server.close()
            thread.join(timeout=2.0)
        assert not thread.is_alive()
        assert not errors


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


_SWIFT_BIN_DIR: Path | None = None


def _swift_bin_dir() -> Path:
    global _SWIFT_BIN_DIR
    if _SWIFT_BIN_DIR is not None:
        return _SWIFT_BIN_DIR
    for product in ("MOSSCaptureApp", "mtd-capture"):
        subprocess.run(
            [
                "swift",
                "build",
                "--package-path",
                str(PACKAGE_ROOT),
                "--product",
                product,
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=BUILD_TIMEOUT,
        )
    completed = subprocess.run(
        ["swift", "build", "--package-path", str(PACKAGE_ROOT), "--show-bin-path"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=BUILD_TIMEOUT,
    )
    _SWIFT_BIN_DIR = Path(completed.stdout.strip())
    return _SWIFT_BIN_DIR


class _LabBundle:
    """The one immutable first-install app bundle at the fixed lab path."""

    def __init__(self, *, bundle: Path, evidence: dict[str, Any]):
        self.bundle = bundle
        self.executable = bundle / "Contents" / "MacOS" / LAB_EXECUTABLE_NAME
        self.evidence = evidence


_LAB_BUNDLE: _LabBundle | None = None
_LAB_LOCK_HANDLE: Any = None


def _lab_bundle() -> _LabBundle:
    """Install the lab bundle once per checkout, then reuse and re-assert it."""
    global _LAB_BUNDLE
    if _LAB_BUNDLE is None:
        _LAB_BUNDLE = _install_or_reuse_lab_bundle()
    else:
        _assert_lab_bundle_unchanged(_LAB_BUNDLE)
    return _LAB_BUNDLE


def _acquire_lab_lock() -> None:
    """Hold the fixed lab path exclusively for this process, released on exit."""
    global _LAB_LOCK_HANDLE
    if _LAB_LOCK_HANDLE is not None:
        return
    LAB_ROOT.mkdir(parents=True, exist_ok=True)
    handle = LAB_LOCK.open("a+b")
    deadline = time.monotonic() + LAB_LOCK_TIMEOUT
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            if time.monotonic() >= deadline:
                handle.close()
                pytest.fail(
                    f"another process still holds the lab bundle lock: {LAB_LOCK}"
                )
            time.sleep(0.1)
            continue
        _LAB_LOCK_HANDLE = handle
        return


def _install_or_reuse_lab_bundle() -> _LabBundle:
    _acquire_lab_lock()
    built_exe = _swift_bin_dir() / LAB_EXECUTABLE_NAME
    built_product = _built_product_identity(built_exe)
    recorded = _read_lab_evidence()
    # The bundle's inputs are the built executable *and* the product Info.plist: the plist is
    # copied in verbatim, so a plist-only edit changes the installed bundle without changing the
    # Mach-O identity. Reusing across it would fail the continuity assertions instead of
    # reinstalling, and would leave the tracer running a bundle the product no longer describes.
    if (
        recorded is not None
        and recorded["built_product"] == built_product
        and recorded.get("product_info_plist_sha256") == _product_info_plist_sha256()
    ):
        lab = _LabBundle(bundle=LAB_BUNDLE, evidence=recorded)
        _assert_lab_bundle_unchanged(lab)
        return lab
    return _first_install_lab_bundle(built_exe, built_product)


def _product_info_plist_sha256() -> str:
    return hashlib.sha256((PACKAGE_ROOT / "Resources" / "Info.plist").read_bytes()).hexdigest()


def _built_product_identity(built_product: Path) -> dict[str, str]:
    assert built_product.is_file(), f"built app product missing: {built_product}"
    return {
        "macho_uuid": _macho_uuid(built_product),
        "sha256": hashlib.sha256(built_product.read_bytes()).hexdigest(),
    }


def _read_lab_evidence() -> dict[str, Any] | None:
    if not LAB_EVIDENCE.is_file() or not LAB_BUNDLE.is_dir():
        return None
    try:
        recorded = json.loads(LAB_EVIDENCE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(recorded, dict) or recorded.get("schema") != LAB_EVIDENCE_SCHEMA:
        return None
    return recorded


def _first_install_lab_bundle(built_exe: Path, built_product: dict[str, str]) -> _LabBundle:
    if LAB_EVIDENCE.exists():
        LAB_EVIDENCE.unlink()
    if LAB_BUNDLE.exists():
        shutil.rmtree(LAB_BUNDLE)

    contents = LAB_BUNDLE / "Contents"
    macos = contents / "MacOS"
    macos.mkdir(parents=True)
    bundled_exe = macos / LAB_EXECUTABLE_NAME
    shutil.copy2(built_exe, bundled_exe)
    os.chmod(bundled_exe, 0o755)

    info = plistlib.loads((PACKAGE_ROOT / "Resources" / "Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == LAB_BUNDLE_IDENTIFIER
    for key in LAB_USAGE_DESCRIPTION_KEYS:
        assert info.get(key, "").strip(), f"product Info.plist lacks {key}"
    assert info.get(LAB_TRANSPORT_SECURITY_KEY), (
        f"product Info.plist lacks {LAB_TRANSPORT_SECURITY_KEY}: the bundle would not reach the "
        "live server at all"
    )
    info.update({"CFBundleExecutable": LAB_EXECUTABLE_NAME, "CFBundlePackageType": "APPL"})
    (contents / "Info.plist").write_bytes(plistlib.dumps(info, sort_keys=False))

    subprocess.run(
        ["codesign", "--force", "--sign", "-", str(LAB_BUNDLE)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        timeout=TIMEOUT,
    )

    evidence = _observe_lab_bundle(built_product)
    staging = LAB_EVIDENCE.with_suffix(".json.partial")
    staging.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    staging.chmod(0o600)
    staging.replace(LAB_EVIDENCE)
    return _LabBundle(bundle=LAB_BUNDLE, evidence=evidence)


def _observe_lab_bundle(built_product: dict[str, str]) -> dict[str, Any]:
    """Everything the tracer asserts about the installed bundle, read from disk."""
    info = plistlib.loads((LAB_BUNDLE / "Contents" / "Info.plist").read_bytes())
    executable = LAB_BUNDLE / "Contents" / "MacOS" / LAB_EXECUTABLE_NAME
    inventory = _lab_bundle_inventory()
    return {
        "schema": LAB_EVIDENCE_SCHEMA,
        "bundle_path": LAB_BUNDLE.relative_to(ROOT).as_posix(),
        "bundle_identifier": info["CFBundleIdentifier"],
        "bundle_executable": info["CFBundleExecutable"],
        "usage_descriptions": {key: info.get(key, "") for key in LAB_USAGE_DESCRIPTION_KEYS},
        "app_transport_security": info.get(LAB_TRANSPORT_SECURITY_KEY),
        "product_info_plist_sha256": _product_info_plist_sha256(),
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "bundle_sha256": _digest_inventory(inventory),
        "bundle_inventory": inventory,
        "designated_requirement": _designated_requirement(LAB_BUNDLE),
        "built_product": built_product,
    }


def _lab_bundle_inventory() -> dict[str, str]:
    inventory: dict[str, str] = {}
    for path in sorted(LAB_BUNDLE.rglob("*")):
        assert not path.is_symlink(), f"unexpected symlink in lab bundle: {path}"
        if path.is_file():
            relative = path.relative_to(LAB_BUNDLE).as_posix()
            inventory[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return inventory


def _digest_inventory(inventory: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(inventory):
        digest.update(f"{relative}\0{inventory[relative]}\0".encode("utf-8"))
    return digest.hexdigest()


def _designated_requirement(bundle: Path) -> str:
    completed = subprocess.run(
        ["codesign", "-d", "-r", "-", str(bundle)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )
    assert completed.returncode == 0, completed.stderr
    for line in (completed.stdout + completed.stderr).splitlines():
        # An implicit requirement is emitted commented out, e.g. `# designated => cdhash H"…"`.
        candidate = line.strip().removeprefix("#").strip()
        if candidate.startswith("designated =>"):
            return candidate
    raise AssertionError(
        f"codesign -d -r - reported no designated requirement: "
        f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    )


def _assert_lab_bundle_unchanged(lab: _LabBundle) -> None:
    """Re-assert the first-install evidence; a rebuild is not continuity proof."""
    recorded = _read_lab_evidence()
    assert recorded is not None, f"lab bundle evidence disappeared: {LAB_EVIDENCE}"
    assert recorded == lab.evidence
    observed = _observe_lab_bundle(recorded["built_product"])
    assert observed == recorded, (
        "fixed lab bundle changed after its first install: "
        f"{sorted(key for key in observed if observed[key] != recorded.get(key))}"
    )
    verified = subprocess.run(
        ["codesign", "--verify", "--strict", str(LAB_BUNDLE)],
        cwd=ROOT,
        capture_output=True,
        timeout=TIMEOUT,
    )
    assert verified.returncode == 0, verified.stderr.decode("utf-8", errors="replace")


def _local_ipv4_addresses() -> list[ipaddress.IPv4Address]:
    completed = subprocess.run(
        ["ifconfig"],
        check=True,
        capture_output=True,
        text=True,
        timeout=3.0,
    )
    addresses: list[ipaddress.IPv4Address] = []
    for line in completed.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == "inet":
            try:
                address = ipaddress.ip_address(parts[1])
            except ValueError:
                continue
            if isinstance(address, ipaddress.IPv4Address):
                addresses.append(address)
    return addresses


def _private_non_loopback_ipv4() -> str | None:
    for address in _local_ipv4_addresses():
        if any(address in network for network in ALLOWED_PEER_NETWORKS):
            return str(address)
    return None


def _non_ats_exempt_ipv4() -> str | None:
    """A peer address ATS does not treat as local networking — what production dials."""
    for address in _local_ipv4_addresses():
        if address in NON_EXEMPT_PEER_NETWORK:
            return str(address)
    return None


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
import inspect
import socket
import sys
from pathlib import Path

import uvicorn

root = Path(sys.argv[1])
host = sys.argv[2]
cert = sys.argv[3]
key = sys.argv[4]
cert_pin = sys.argv[5]
state = Path(sys.argv[6])
runs = Path(sys.argv[7])
port_file = Path(sys.argv[8])

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
session_ids = iter(("macos-tracer-session", "macos-tracer-session-repin"))
app.state.live_runtime._session_id_factory = lambda: next(session_ids)

server_source = Path(inspect.getsourcefile(create_app)).resolve()
assert create_app.__module__ == "moss_transcribe_diarize.app.server"
assert server_source == (root / "moss_transcribe_diarize" / "app" / "server.py").resolve()

listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind((host, 0))
listener.listen(socket.SOMAXCONN)
port_file.write_text(str(listener.getsockname()[1]), encoding="ascii")

config = uvicorn.Config(
    app,
    host=host,
    port=0,
    ssl_certfile=cert,
    ssl_keyfile=key,
    proxy_headers=False,
    log_level="warning",
)
uvicorn.Server(config).run(sockets=[listener])
""".lstrip(),
        encoding="utf-8",
    )
    return script


def _start_server(
    *,
    server_script: Path,
    host: str,
    cert: Path,
    key: Path,
    cert_pin: str,
    log: Path,
    tmp_path: Path,
) -> tuple[subprocess.Popen[bytes], int]:
    port_file = tmp_path / "server.port"
    process = None
    try:
        with log.open("ab") as handle:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(server_script),
                    str(ROOT),
                    host,
                    str(cert),
                    str(key),
                    cert_pin,
                    str(tmp_path / "live-auth.json"),
                    str(tmp_path / "runs"),
                    str(port_file),
                ],
                cwd=ROOT,
                stdout=handle,
                stderr=subprocess.STDOUT,
                close_fds=True,
            )
        deadline = time.monotonic() + TIMEOUT
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(
                    f"uvicorn exited before binding with {process.returncode}: "
                    f"{log.read_text(errors='replace')}"
                )
            if port_file.exists():
                port = int(port_file.read_text(encoding="ascii"))
                assert 0 < port < 65_536
                return process, port
            time.sleep(0.05)
        pytest.fail(f"uvicorn did not report its bound port: {log.read_text(errors='replace')}")
    except BaseException:
        if process is not None:
            _terminate(process)
        raise


def _wait_for_https(
    url: str,
    process: subprocess.Popen[bytes],
    log: Path,
) -> dict[str, Any]:
    deadline = time.monotonic() + TIMEOUT
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail(f"uvicorn exited early with {process.returncode}: {log.read_text(errors='replace')}")
        try:
            return _json_request("GET", url)
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


def _assert_server_observed_dual_lane_frames(snapshot: dict[str, Any]) -> int:
    v2_session = snapshot["v2_session"]
    assert v2_session["status"] == "active"
    lanes = v2_session["lanes"]
    observed_samples = 0
    for lane_name in ("system", "microphone"):
        accepted = int(lanes[lane_name]["accepted_samples"])
        assert accepted > 0, f"server observed no native samples for {lane_name}"
        observed_samples += accepted
    return observed_samples


def _wait_for_server_observed_dual_lane_frames(
    *,
    server_url: str,
    session_id: str,
    bearer_token: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + TIMEOUT
    last_snapshot: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last_snapshot = _server_snapshot(
            server_url=server_url,
            session_id=session_id,
            bearer_token=bearer_token,
        )
        lanes = last_snapshot["v2_session"]["lanes"]
        if all(int(lanes[lane]["accepted_samples"]) > 0 for lane in ("system", "microphone")):
            return last_snapshot
        time.sleep(0.1)
    pytest.fail(f"server did not observe native samples on both lanes: {last_snapshot}")


def _assert_production_server_runtime(runtime: dict[str, Any]) -> None:
    assert {"ffmpeg", "model", "inference", "live"}.issubset(runtime)
    live = runtime["live"]
    assert live["enabled"] is True
    descriptor = live["descriptor"]
    assert descriptor["schema_version"] == 1
    assert descriptor["source_revision"] == "eda5e69faf0e0251383029295f7e8875a2a1a4f6"
    assert descriptor["provider_name"] == "api-fake"
    assert descriptor["live_protocol_version"] == "moss-live-service.v1"


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
    app = None
    try:
        with log.open("ab") as handle:
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
                pytest.fail(
                    f"MOSSCaptureApp exited early with {app.returncode}: "
                    f"{log.read_text(errors='replace')}"
                )
            if socket_path.exists():
                mode = stat.S_IMODE(socket_path.stat().st_mode)
                assert mode == 0o600
                return app
            time.sleep(0.05)
        pytest.fail(f"MOSSCaptureApp did not bind UDS: {log.read_text(errors='replace')}")
    except BaseException:
        if app is not None:
            _terminate(app)
        _remove_socket(socket_path)
        raise


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


def _replace_store_value(path: Path, *, key: str, value: str) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    document["values"][key] = value
    path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    path.chmod(0o600)


def _assert_secret_absent(output: bytes, secret: str) -> None:
    assert secret
    assert secret.encode("utf-8") not in output
    try:
        decoded = json.loads(output)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    assert all(secret not in value for value in _json_strings(decoded))


def _json_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _json_strings(key)
            yield from _json_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _json_strings(item)


def _assert_bundled_product_identity(
    executable: Path,
    *,
    built_product: Path,
    expected_bundle: Path,
) -> None:
    assert executable.resolve().is_relative_to(expected_bundle.resolve())
    assert _macho_uuid(executable) == _macho_uuid(built_product)
    verified = subprocess.run(
        ["codesign", "--verify", "--strict", str(expected_bundle)],
        cwd=ROOT,
        capture_output=True,
        timeout=TIMEOUT,
    )
    assert verified.returncode == 0, verified.stderr.decode("utf-8", errors="replace")


def _macho_uuid(executable: Path) -> str:
    completed = subprocess.run(
        ["dwarfdump", "--uuid", str(executable)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )
    assert completed.returncode == 0, completed.stderr
    fields = completed.stdout.split()
    assert len(fields) >= 2 and fields[0] == "UUID:", completed.stdout
    return fields[1]


def _assert_uds_product_server_identity(
    socket_path: Path,
    *,
    expected_pid: int,
    control_secret: str,
) -> bytes:
    request_body = json.dumps(
        {"secret": control_secret, "request": {"command": "status"}},
        separators=(",", ":"),
    ).encode("utf-8")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2.0)
        client.connect(str(socket_path))
        peer_pid = struct.unpack("i", client.getsockopt(0, 0x002, 4))[0]
        assert peer_pid == expected_pid
        client.sendall(struct.pack(">I", len(request_body)) + request_body)
        length = struct.unpack(">I", _recv_exact(client, 4))[0]
        assert 0 < length <= 65_536
        response_body = _recv_exact(client, length)
    response = json.loads(response_body.decode("utf-8"))
    assert response["ok"] is True
    assert response["running"] is False
    _assert_secret_absent(response_body, control_secret)
    return response_body


def _recv_exact(stream: socket.socket, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        chunk = stream.recv(count - len(chunks))
        assert chunk
        chunks.extend(chunk)
    return bytes(chunks)


def _serve_permission_denial_once(
    server: socket.socket,
    control_secret: str,
    errors: list[BaseException],
) -> None:
    try:
        connection, _ = server.accept()
        with connection:
            connection.settimeout(2.0)
            length = struct.unpack(">I", _recv_exact(connection, 4))[0]
            assert 0 < length <= 65_536
            envelope = json.loads(_recv_exact(connection, length).decode("utf-8"))
            assert envelope["secret"] == control_secret
            assert envelope["request"]["command"] == "start"
            response = json.dumps(
                {
                    "ok": False,
                    "error": 'permissionDenied("microphone")',
                },
                separators=(",", ":"),
            ).encode("utf-8")
            connection.sendall(struct.pack(">I", len(response)) + response)
    except BaseException as exc:  # noqa: BLE001
        errors.append(exc)


def _assert_named_pasteboard_matches_store(
    *,
    pasteboard_name: str,
    store_path: Path,
) -> None:
    program = """
import AppKit
import Foundation

let name = NSPasteboard.Name(CommandLine.arguments[1])
let store = URL(fileURLWithPath: CommandLine.arguments[2])
let document = try JSONSerialization.jsonObject(with: Data(contentsOf: store)) as! [String: Any]
let values = document["values"] as! [String: String]
let pasteboard = NSPasteboard(name: name)
guard pasteboard.string(forType: .string) == values["capture-view-token"] else {
    Foundation.exit(1)
}
pasteboard.clearContents()
""".strip()
    completed = subprocess.run(
        ["swift", "-e", program, pasteboard_name, str(store_path)],
        cwd=ROOT,
        capture_output=True,
        timeout=BUILD_TIMEOUT,
    )
    assert completed.returncode == 0, (
        f"named pasteboard did not contain persisted view authority: "
        f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    )
    assert completed.stdout == b""


def _write_secret_clean_artifact(
    artifact_dir: Path,
    name: str,
    payload: bytes,
    *,
    secrets: tuple[str, ...],
) -> None:
    for secret in secrets:
        _assert_secret_absent(payload, secret)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / name).write_bytes(payload)


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
