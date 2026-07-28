"""Acceptance for the tracked live-service credential tools.

Two tools are covered, and they are coupled by one value: the SHA-256 over the leaf
certificate's DER bytes. `ops/generate-live-tls.sh` mints the material and prints that digest;
the live server derives the same digest from the same file at startup
(`web_cli._certificate_sha256`) and stamps it into every pairing payload; the Mac client
compares it against the leaf a TLS handshake actually offers
(`FullCertificatePinValidator`, 64 lowercase hex characters, nothing else accepted).
`ops/live-pair.sh` mints one payload and refuses to print it when the running service's digest
and the digest of the certificate on disk disagree.

Everything here runs against scratch paths. No certificate, key, service, port forward or
deployment file outside `tmp_path` is created or touched, and the one server these tests start
binds loopback only, on an ephemeral port, with material generated for the test.

Secrets: one node mints real pairing payloads. They are held in memory, asserted against
without being echoed into an assertion message, and the node then proves they reached no file
under the tool's HOME, TMPDIR or working directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pytest

from moss_transcribe_diarize.app.live_auth import (
    LiveAccessError,
    LiveAccessForbidden,
    LiveAccessRegistry,
    LivePeer,
)
from moss_transcribe_diarize.app.web_cli import _certificate_sha256


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops"
MAC_SCRIPTS = ROOT / "macos" / "scripts"
TIMEOUT = 60.0
SERVER_TIMEOUT = 60.0

# Fixture names, not deployment values: any DNS name and any private address exercises the
# same code. One node below runs the real deployment invocation on top of these.
FIXTURE_DNS = ("moss-live.fixture.invalid", "moss-live-alt.fixture.invalid")
FIXTURE_IPS = ("10.11.12.13", "100.64.7.7")


def run_tool(script: str, *args: str, env: dict[str, str] | None = None,
             cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return subprocess.run(
        ["/bin/bash", str(OPS / script), *args],
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        env=merged,
    )


def lines(completed: subprocess.CompletedProcess[str], prefix: str) -> list[str]:
    return [
        line[len(prefix):].strip()
        for line in completed.stdout.splitlines()
        if line.startswith(prefix)
    ]


def evidence(completed: subprocess.CompletedProcess[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in lines(completed, "evidence:"):
        key, _, value = line.partition("=")
        found[key] = value
    return found


def first_index(completed: subprocess.CompletedProcess[str], prefix: str) -> int:
    for index, line in enumerate(completed.stdout.splitlines()):
        if line.startswith(prefix):
            return index
    return -1


def tls_args(cert: Path, key: Path, *, dns: tuple[str, ...] = FIXTURE_DNS,
             ips: tuple[str, ...] = FIXTURE_IPS) -> list[str]:
    args: list[str] = []
    for name in dns:
        args += ["--dns", name]
    for address in ips:
        args += ["--ip", address]
    return args + ["--cert", str(cert), "--key", str(key)]


def generate(cert: Path, key: Path, *extra: str,
             env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return run_tool("generate-live-tls.sh", *tls_args(cert, key), *extra, env=env)


def identity(path: Path) -> tuple[int, int, bytes]:
    """Enough to prove a file was not rewritten: inode, mtime in ns, and its bytes."""
    stat_result = path.stat()
    return (stat_result.st_ino, stat_result.st_mtime_ns, path.read_bytes())


def decoded_certificate(cert: Path) -> dict[str, Any]:
    """An independent reader: CPython's own X.509 decoder, not the tool's openssl parsing."""
    return ssl._ssl._test_decode_cert(str(cert))  # type: ignore[attr-defined]


def decoded_sans(cert: Path) -> set[str]:
    spelling = {"DNS": "DNS", "IP Address": "IP"}
    return {
        f"{spelling[kind]}:{value}"
        for kind, value in decoded_certificate(cert)["subjectAltName"]
    }


def live_access_admits(address: str) -> bool:
    """Whether the live server would admit a peer at `address` at all.

    Asked through the registry's public surface rather than by importing its network table,
    so a change to that table shows up here as a disagreement with the tool. `issue_pairing`
    reads no state and writes none, so an absent state path stays absent.
    """
    registry = LiveAccessRegistry(
        state_path=Path(tempfile.gettempdir()) / f"unused-live-auth-{os.getpid()}.json",
        server_cert_sha256="ab" * 32,
    )
    try:
        registry.issue_pairing(LivePeer(address, "https"), now=0.0)
    except LiveAccessForbidden as exc:
        message = str(exc)
        # Those two are the admission refusals. Any other refusal (loopback-only, TLS-only)
        # means the peer was admitted first and rejected for a different reason.
        return not (
            "outside the private live network" in message or "invalid peer address" in message
        )
    except LiveAccessError:
        return True
    return True


# --------------------------------------------------------------------------------------
# ops/generate-live-tls.sh
# --------------------------------------------------------------------------------------


def test_generate_live_tls_installs_the_pin_the_client_and_the_server_both_derive(tmp_path: Path):
    live = tmp_path / "live"
    cert, key = live / "live.crt", live / "live.key"

    completed = generate(cert, key)

    assert completed.returncode == 0, completed.stderr
    assert cert.is_file() and key.is_file()
    facts = evidence(completed)

    # The pin is the only form the client accepts: 64 lowercase hex, no separators.
    assert re.fullmatch(r"[0-9a-f]{64}", facts["pin"]), facts["pin"]
    # ...and it is the digest the server will derive from this same file at startup.
    assert facts["pin"] == _certificate_sha256(cert)
    # ...and the digest of the DER bytes, computed here without either implementation.
    der = ssl.PEM_cert_to_DER_cert(cert.read_text(encoding="ascii"))
    assert facts["pin"] == hashlib.sha256(der).hexdigest()

    assert decoded_sans(cert) == {
        *(f"DNS:{name}" for name in FIXTURE_DNS),
        *(f"IP:{address}" for address in FIXTURE_IPS),
    }
    assert facts["subject_common_name"] == FIXTURE_DNS[0]
    assert facts["rotated"] == "true"
    assert facts["backup_certificate"] == "none"

    # The private key is not readable by anyone else; the certificate is public material.
    assert oct(key.stat().st_mode & 0o777) == "0o600"
    assert oct(cert.stat().st_mode & 0o777) == "0o644"
    assert oct(live.stat().st_mode & 0o777) == "0o700"
    assert facts["private_key_mode"] == "600"
    assert facts["certificate_mode"] == "644"

    not_after = datetime.strptime(facts["not_after"], "%b %d %H:%M:%S %Y %Z").replace(
        tzinfo=timezone.utc
    )
    lifetime_days = (not_after - datetime.now(timezone.utc)).days
    assert 823 <= lifetime_days <= 825, facts["not_after"]
    assert facts["validity_days"] == "825"


def test_generate_live_tls_material_serves_tls_and_offers_the_pinned_leaf(tmp_path: Path):
    """The pin has to match the certificate a handshake offers, which is what the client sees."""
    live = tmp_path / "live"
    cert, key = live / "live.crt", live / "live.key"
    facts = evidence(generate(cert, key))

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    # load_cert_chain is the same call uvicorn makes for --live-tls-certfile/--keyfile: a key
    # that did not belong to the certificate would fail right here.
    context.load_cert_chain(certfile=str(cert), keyfile=str(key))
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def serve() -> None:
        try:
            connection, _ = listener.accept()
            with context.wrap_socket(connection, server_side=True) as tls:
                tls.recv(1)
        except OSError:
            pass

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    try:
        offered = ssl.get_server_certificate(("127.0.0.1", port))
    finally:
        worker.join(timeout=5.0)
        listener.close()

    offered_pin = hashlib.sha256(ssl.PEM_cert_to_DER_cert(offered)).hexdigest()
    assert offered_pin == facts["pin"]


def test_generate_live_tls_re_run_does_not_rotate_the_pin_paired_clients_hold(tmp_path: Path):
    live = tmp_path / "live"
    cert, key = live / "live.crt", live / "live.key"
    first = evidence(generate(cert, key))
    before = (identity(cert), identity(key))

    # Same names in a different order, and a different --days: neither is a reason to rotate.
    completed = run_tool(
        "generate-live-tls.sh",
        *tls_args(cert, key, dns=tuple(reversed(FIXTURE_DNS)), ips=tuple(reversed(FIXTURE_IPS))),
        "--common-name", FIXTURE_DNS[0],
        "--days", "30",
    )

    assert completed.returncode == 0, completed.stderr
    assert lines(completed, "unchanged:"), completed.stdout
    assert lines(completed, "change:") == []
    assert (identity(cert), identity(key)) == before
    second = evidence(completed)
    assert second["pin"] == first["pin"]
    assert second["rotated"] == "false"


def test_generate_live_tls_refuses_a_name_change_without_rotate_then_rotates_reversibly(
    tmp_path: Path,
):
    live = tmp_path / "live"
    cert, key = live / "live.crt", live / "live.key"
    original = evidence(generate(cert, key))
    before = (identity(cert), identity(key))

    narrowed = tls_args(cert, key, dns=FIXTURE_DNS[:1], ips=FIXTURE_IPS[:1])
    refused = run_tool("generate-live-tls.sh", *narrowed)

    assert refused.returncode != 0
    assert "--rotate" in refused.stderr
    assert (identity(cert), identity(key)) == before, "a refusal must not touch the material"

    rotated = run_tool("generate-live-tls.sh", *narrowed, "--rotate")

    assert rotated.returncode == 0, rotated.stderr
    rollback_at = first_index(rotated, "rollback:")
    change_at = first_index(rotated, "change:")
    assert 0 <= rollback_at < change_at, rotated.stdout
    facts = evidence(rotated)
    assert facts["pin"] != original["pin"], "rotation must produce new material"
    assert decoded_sans(cert) == {f"DNS:{FIXTURE_DNS[0]}", f"IP:{FIXTURE_IPS[0]}"}
    backup_cert = Path(facts["backup_certificate"])
    backup_key = Path(facts["backup_private_key"])
    assert backup_cert.is_file() and backup_key.is_file()
    assert backup_cert.read_bytes() == before[0][2]
    assert backup_key.read_bytes() == before[1][2]

    rollback_command = lines(rotated, "rollback:")[0]
    executed = subprocess.run(
        ["/bin/bash", "-c", rollback_command], capture_output=True, text=True, timeout=TIMEOUT
    )

    assert executed.returncode == 0, executed.stderr
    assert cert.read_bytes() == before[0][2]
    assert key.read_bytes() == before[1][2]
    assert _certificate_sha256(cert) == original["pin"]
    assert not backup_cert.exists() and not backup_key.exists()


def test_generate_live_tls_refuses_a_half_installed_pair_without_rotate(tmp_path: Path):
    live = tmp_path / "live"
    cert, key = live / "live.crt", live / "live.key"
    generate(cert, key)
    cert.unlink()
    key_before = identity(key)

    refused = generate(cert, key)

    assert refused.returncode != 0
    assert "only one of" in refused.stderr
    assert identity(key) == key_before
    assert not cert.exists()

    replaced = generate(cert, key, "--rotate")

    assert replaced.returncode == 0, replaced.stderr
    assert cert.is_file()
    facts = evidence(replaced)
    assert facts["backup_certificate"] == "none"
    assert Path(facts["backup_private_key"]).is_file(), "the orphaned key is moved aside, not deleted"
    assert Path(facts["backup_private_key"]).read_bytes() == key_before[2]


def test_generate_live_tls_dry_run_writes_nothing_even_over_installed_material(tmp_path: Path):
    live = tmp_path / "live"
    cert, key = live / "live.crt", live / "live.key"

    empty = generate(cert, key, "--dry-run")

    assert empty.returncode == 0, empty.stderr
    assert not live.exists(), "a dry run must not even create the directory"
    plans = lines(empty, "plan:")
    assert len(plans) >= 4
    assert lines(empty, "rollback:"), empty.stdout
    assert lines(empty, "change:") == []
    assert first_index(empty, "plan:") < first_index(empty, "rollback:")

    generate(cert, key)
    before = (identity(cert), identity(key))
    over_existing = generate(cert, key, "--dry-run", "--rotate")

    assert over_existing.returncode == 0, over_existing.stderr
    assert lines(over_existing, "change:") == []
    assert (identity(cert), identity(key)) == before


def test_generate_live_tls_admits_exactly_the_addresses_live_access_admits(tmp_path: Path):
    cert, key = tmp_path / "live.crt", tmp_path / "live.key"
    ipv4_cases = (
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "172.15.0.1",
        "172.32.0.1",
        "192.168.68.38",
        "192.169.0.1",
        "100.64.0.8",
        "100.63.255.255",
        "100.128.0.1",
        "169.254.1.1",
        "8.8.8.8",
        "10.0.0.256",
        "10.0.0",
    )
    for address in ipv4_cases:
        completed = run_tool(
            "generate-live-tls.sh",
            "--dry-run", "--dns", FIXTURE_DNS[0], "--ip", address,
            "--cert", str(cert), "--key", str(key),
        )
        accepted = completed.returncode == 0
        expected = live_access_admits(address)
        assert accepted is expected, f"{address}: tool accepted={accepted}, server admits={expected}"
        if not accepted:
            assert "refusing" in completed.stderr or "--ip" in completed.stderr

    # IPv6 is refused although the server admits ULA and link-local peers. Narrower than the
    # server is safe (the name can still be added deliberately); wider would not be.
    ipv6 = run_tool(
        "generate-live-tls.sh",
        "--dry-run", "--dns", FIXTURE_DNS[0], "--ip", "fd7a:115c:a1e0::20",
        "--cert", str(cert), "--key", str(key),
    )
    assert ipv6.returncode != 0
    assert live_access_admits("fd7a:115c:a1e0::20") is True
    assert not cert.exists() and not key.exists()


def test_generate_live_tls_refuses_malformed_names_and_lifetimes(tmp_path: Path):
    cert, key = tmp_path / "live.crt", tmp_path / "live.key"
    paths = ["--cert", str(cert), "--key", str(key)]
    good_dns = ["--dns", FIXTURE_DNS[0]]
    good_ip = ["--ip", FIXTURE_IPS[0]]
    cases: tuple[tuple[str, list[str], str], ...] = (
        ("no names at all", [*paths, *good_ip], "--dns"),
        ("no addresses at all", [*paths, *good_dns], "--ip"),
        ("an address passed as a name", [*paths, "--dns", "10.0.0.5", *good_ip], "--ip"),
        ("a leading hyphen label", [*paths, "--dns", "-bad.invalid", *good_ip], "DNS name"),
        ("an empty label", [*paths, "--dns", "bad..invalid", *good_ip], "DNS name"),
        ("an over-long label", [*paths, "--dns", "a" * 64 + ".invalid", *good_ip], "DNS name"),
        ("an underscore", [*paths, "--dns", "bad_name.invalid", *good_ip], "DNS name"),
        ("a repeated name", [*paths, *good_dns, *good_dns, *good_ip], "repeated"),
        ("a repeated address", [*paths, *good_dns, *good_ip, *good_ip], "repeated"),
        (
            "a common name that is not one of the names",
            [*paths, *good_dns, *good_ip, "--common-name", "other.invalid"],
            "browser would not match",
        ),
        ("a lifetime past the accepted maximum", [*paths, *good_dns, *good_ip, "--days", "826"], "825"),
        ("a zero lifetime", [*paths, *good_dns, *good_ip, "--days", "0"], "at least 1"),
        ("a non-numeric lifetime", [*paths, *good_dns, *good_ip, "--days", "many"], "whole number"),
        ("one path for both files", ["--cert", str(cert), "--key", str(cert), *good_dns, *good_ip],
         "different paths"),
        ("an unknown flag", [*paths, *good_dns, *good_ip, "--sign-identity", "-"], "unknown argument"),
    )
    for label, args, expected in cases:
        completed = run_tool("generate-live-tls.sh", "--dry-run", *args)
        assert completed.returncode != 0, f"{label} was accepted"
        assert expected in completed.stderr, f"{label}: {completed.stderr}"
        assert completed.stdout.count("plan:") == 0, f"{label} planned before validating"
    assert not cert.exists() and not key.exists()


def test_generate_live_tls_installs_nothing_when_generation_fails(tmp_path: Path):
    """A failed generation leaves no half-installed material and no scratch residue."""
    live = tmp_path / "live"
    cert, key = live / "live.crt", live / "live.key"
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    real_openssl = shutil.which("openssl")
    assert real_openssl is not None
    # Everything except generation still works, so the failure lands exactly at `req -x509`.
    (stub_bin / "openssl").write_text(
        "#!/bin/bash\n"
        'if [ "$1" = "req" ]; then echo "stubbed openssl failure" >&2; exit 1; fi\n'
        f'exec {real_openssl} "$@"\n',
        encoding="utf-8",
    )
    (stub_bin / "openssl").chmod(0o755)
    scratch_tmp = tmp_path / "scratch-tmp"
    scratch_tmp.mkdir()

    completed = generate(
        cert, key,
        env={"PATH": f"{stub_bin}:{os.environ['PATH']}", "TMPDIR": str(scratch_tmp)},
    )

    assert completed.returncode != 0
    assert "could not generate" in completed.stderr
    assert not cert.exists() and not key.exists()
    assert list(scratch_tmp.iterdir()) == [], "the scratch workspace must be removed"


def test_generate_live_tls_runs_the_deployment_invocation_this_branch_documents(tmp_path: Path):
    """The exact D2 invocation, so a name or address the plan states cannot be refused later."""
    live = tmp_path / "live"
    cert, key = live / "live.crt", live / "live.key"

    completed = run_tool(
        "generate-live-tls.sh",
        "--dns", "ga0-alienware-rtx4070ti.tailnet.aisight.us",
        "--dns", "ga0-alienware-rtx4070ti.local",
        "--ip", "100.64.0.8",
        "--ip", "192.168.68.38",
        "--common-name", "ga0-alienware-rtx4070ti.tailnet.aisight.us",
        "--cert", str(cert),
        "--key", str(key),
    )

    assert completed.returncode == 0, completed.stderr
    assert decoded_sans(cert) == {
        "DNS:ga0-alienware-rtx4070ti.tailnet.aisight.us",
        "DNS:ga0-alienware-rtx4070ti.local",
        "IP:100.64.0.8",
        "IP:192.168.68.38",
    }
    assert evidence(completed)["pin"] == _certificate_sha256(cert)


# --------------------------------------------------------------------------------------
# ops/live-pair.sh
# --------------------------------------------------------------------------------------


class LiveServer:
    def __init__(self, process: subprocess.Popen[bytes], port: int, cert: Path, key: Path,
                 log: Path) -> None:
        self.process = process
        self.port = port
        self.cert = cert
        self.key = key
        self.log = log

    @property
    def url(self) -> str:
        return f"https://127.0.0.1:{self.port}"


def _write_server_script(path: Path) -> Path:
    path.write_text(
        """
from __future__ import annotations

import importlib.util
import socket
import sys
from pathlib import Path

import uvicorn

root = Path(sys.argv[1])
cert = sys.argv[2]
key = sys.argv[3]
pin = sys.argv[4]
state = Path(sys.argv[5])
runs = Path(sys.argv[6])
port_file = Path(sys.argv[7])

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
    live_server_cert_sha256=pin,
    live_helper_lease_seconds=30.0,
    live_runtime_factory=lambda: helpers.make_live_runtime(session_id="pairing-session"),
)

listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind(("127.0.0.1", 0))
listener.listen(socket.SOMAXCONN)
port_file.write_text(str(listener.getsockname()[1]), encoding="ascii")

uvicorn.Server(
    uvicorn.Config(app, host="127.0.0.1", port=0, ssl_certfile=cert, ssl_keyfile=key,
                   proxy_headers=False, log_level="warning")
).run(sockets=[listener])
""".lstrip(),
        encoding="utf-8",
    )
    return path


@pytest.fixture(scope="module")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveServer]:
    if shutil.which("curl") is None:
        pytest.fail("curl is required: ops/live-pair.sh mints through it.")
    tmp_path = tmp_path_factory.mktemp("live-pair-server")
    cert, key = tmp_path / "live.crt", tmp_path / "live.key"
    # The server serves material generated by the tool under test.
    generated = run_tool("generate-live-tls.sh", *tls_args(cert, key))
    assert generated.returncode == 0, generated.stderr
    pin = evidence(generated)["pin"]
    script = _write_server_script(tmp_path / "live_server.py")
    port_file = tmp_path / "server.port"
    log = tmp_path / "server.log"
    process: subprocess.Popen[bytes] | None = None
    try:
        with log.open("ab") as handle:
            process = subprocess.Popen(
                [sys.executable, str(script), str(ROOT), str(cert), str(key), pin,
                 str(tmp_path / "live-auth.json"), str(tmp_path / "runs"), str(port_file)],
                cwd=str(ROOT),
                stdout=handle,
                stderr=subprocess.STDOUT,
                close_fds=True,
            )
        deadline = time.monotonic() + SERVER_TIMEOUT
        port: int | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"live server exited early: {log.read_text(errors='replace')}")
            if port_file.exists():
                port = int(port_file.read_text(encoding="ascii"))
                break
            time.sleep(0.05)
        if port is None:
            pytest.fail(f"live server never reported a port: {log.read_text(errors='replace')}")
        context = ssl._create_unverified_context()
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"https://127.0.0.1:{port}/api/live/descriptor", context=context, timeout=2.0
                ) as response:
                    assert response.status == 200
                    break
            except (urllib.error.URLError, ConnectionError, ssl.SSLError, OSError):
                time.sleep(0.1)
        else:
            pytest.fail(f"live server never answered: {log.read_text(errors='replace')}")
        yield LiveServer(process, port, cert, key, log)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10.0)


def _payload_lines(completed: subprocess.CompletedProcess[str]) -> list[str]:
    return lines(completed, "payload:")


def test_live_pair_mints_one_payload_bound_to_the_served_certificate(
    live_server: LiveServer, tmp_path: Path
):
    home = tmp_path / "home"
    scratch_tmp = tmp_path / "tmp"
    workdir = tmp_path / "cwd"
    for directory in (home, scratch_tmp, workdir):
        directory.mkdir()
    env = {"HOME": str(home), "TMPDIR": str(scratch_tmp)}

    first = run_tool(
        "live-pair.sh", "--url", live_server.url, "--cert", str(live_server.cert),
        env=env, cwd=workdir,
    )
    second = run_tool(
        "live-pair.sh", "--url", live_server.url, "--cert", str(live_server.cert),
        env=env, cwd=workdir,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert len(_payload_lines(first)) == 1, "the payload must be printed exactly once"
    assert len(_payload_lines(second)) == 1
    payloads = (_payload_lines(first)[0], _payload_lines(second)[0])

    pin = _certificate_sha256(live_server.cert)
    for payload in payloads:
        prefix, secret, embedded_pin = payload.split(".")
        assert prefix == "mtd1"
        assert len(secret) >= 32, "a pairing secret this short would not be one"
        assert embedded_pin == pin, "the payload must be bound to the served certificate"
    assert payloads[0] != payloads[1], "each mint must be a fresh single-use secret"

    facts = evidence(first)
    assert facts["pin"] == pin
    assert facts["payload_matches_certificate"] == "true"
    assert facts["single_use"] == "true"
    assert 0 < int(facts["expires_in_seconds"]) <= 300
    assert first_index(first, "rollback:") < first_index(first, "payload:")

    # No evidence line and no error stream may carry the secret.
    secrets = tuple(payload.split(".")[1] for payload in payloads)
    for completed in (first, second):
        assert all(secret not in completed.stderr for secret in secrets)
    for value in facts.values():
        assert all(secret not in value for secret in secrets)

    leaked: list[str] = []
    for root, _, files in os.walk(tmp_path):
        for name in files:
            candidate = Path(root) / name
            try:
                blob = candidate.read_bytes()
            except OSError:
                continue
            if any(secret.encode("ascii") in blob for secret in secrets):
                leaked.append(str(candidate))
    assert leaked == [], f"the payload reached a file: {leaked}"

    # The server persists devices, never pairing secrets, so its state holds none either.
    state = live_server.cert.parent / "live-auth.json"
    if state.exists():
        blob = state.read_bytes()
        assert all(secret.encode("ascii") not in blob for secret in secrets)


def test_live_pair_refuses_when_the_service_serves_other_material_than_the_file(
    live_server: LiveServer, tmp_path: Path
):
    """The rotated-but-not-restarted case, which would otherwise fail as a pin error on the Mac."""
    other_cert, other_key = tmp_path / "live.crt", tmp_path / "live.key"
    generated = run_tool("generate-live-tls.sh", *tls_args(other_cert, other_key))
    assert generated.returncode == 0, generated.stderr

    completed = run_tool(
        "live-pair.sh", "--url", live_server.url, "--cert", str(other_cert)
    )

    assert completed.returncode != 0
    assert _payload_lines(completed) == [], "a mismatch must not print the payload"
    assert "restart the live service" in completed.stderr
    assert _certificate_sha256(other_cert) in completed.stderr, "the operator needs both digests"
    assert _certificate_sha256(live_server.cert) in completed.stderr


def test_live_pair_sends_nothing_when_the_url_or_the_certificate_is_wrong(tmp_path: Path):
    cert, key = tmp_path / "live.crt", tmp_path / "live.key"
    assert run_tool("generate-live-tls.sh", *tls_args(cert, key)).returncode == 0
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    marker = tmp_path / "curl-was-called"
    (stub_bin / "curl").write_text(
        f'#!/bin/bash\nprintf "%s\\n" "$@" >>"{marker}"\nexit 0\n', encoding="utf-8"
    )
    (stub_bin / "curl").chmod(0o755)
    env = {"PATH": f"{stub_bin}:{os.environ['PATH']}"}
    cases: tuple[tuple[str, list[str], str], ...] = (
        ("a LAN address", ["--url", "https://192.168.68.38:7861"], "loopback"),
        ("a tailnet address", ["--url", "https://100.64.0.8:7861"], "loopback"),
        ("a hostname", ["--url", "https://ga0-alienware-rtx4070ti.local:7861"], "loopback"),
        ("plaintext", ["--url", "http://127.0.0.1:7861"], "TLS-only"),
        ("a URL with a path", ["--url", "https://127.0.0.1:7861/api/live"], "without a path"),
        ("a missing certificate", ["--cert", str(tmp_path / "absent.crt")], "not found"),
        ("a non-numeric timeout", ["--timeout", "soon"], "whole number"),
        ("an unknown flag", ["--rotate"], "unknown argument"),
    )
    for label, args, expected in cases:
        completed = run_tool(
            "live-pair.sh", "--cert", str(cert), *args, env=env
        )
        assert completed.returncode != 0, f"{label} was accepted"
        assert expected in completed.stderr, f"{label}: {completed.stderr}"
        assert _payload_lines(completed) == []
    assert not marker.exists(), "a refused invocation must not reach the network"

    dry = run_tool("live-pair.sh", "--dry-run", "--cert", str(cert), env=env)

    assert dry.returncode == 0, dry.stderr
    assert _payload_lines(dry) == []
    assert not marker.exists(), "a dry run must not mint anything"
    assert lines(dry, "plan:"), dry.stdout
    assert lines(dry, "rollback:"), dry.stdout
    assert evidence(dry)["pin"] == _certificate_sha256(cert)


# --------------------------------------------------------------------------------------
# one output discipline across both host families
# --------------------------------------------------------------------------------------


def test_ops_and_mac_tool_libraries_speak_one_output_vocabulary():
    """The two libraries are separate files on purpose; the vocabulary must not diverge."""
    program = (
        'plan "step"; rollback "undo"; change "moved"; unchanged "why"; '
        'evidence "key" "value"; ( die "boom" ) 2>&1; dry_run && echo "dry" || echo "wet"'
    )
    outputs = []
    for library in (OPS / "moss-ops-lib.sh", MAC_SCRIPTS / "moss-tool-lib.sh"):
        completed = subprocess.run(
            ["/bin/bash", "-c", f'. "{library}"; {program}'],
            capture_output=True, text=True, timeout=TIMEOUT, cwd=str(ROOT),
        )
        assert completed.returncode == 0, completed.stderr
        outputs.append(completed.stdout)
    assert outputs[0] == outputs[1]
    assert outputs[0].splitlines() == [
        "plan: step",
        "rollback: undo",
        "change: moved",
        "unchanged: why",
        "evidence: key=value",
        "error: boom",
        "wet",
    ]
