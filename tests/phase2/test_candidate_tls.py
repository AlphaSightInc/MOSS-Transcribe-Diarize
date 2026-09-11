from __future__ import annotations

import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from moss_transcribe_diarize import phase2_cutover as cutover


def openssl(root, *args):
    subprocess.run(("openssl", *args), cwd=root, check=True, capture_output=True)


@pytest.fixture
def certificates(tmp_path):
    # A private test root substitutes for installed system roots only in this test.
    openssl(tmp_path, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=Test root", "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign", "-keyout", "root.key", "-out", "root.crt")
    for name, issuer in (("intermediate", "root"), ("leaf", "intermediate")):
        openssl(tmp_path, "req", "-new", "-newkey", "rsa:2048", "-nodes", "-subj", f"/CN={name}",
                "-keyout", f"{name}.key", "-out", f"{name}.csr")
        extensions = ("basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n"
                      if name == "intermediate" else
                      "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n"
                      "extendedKeyUsage=serverAuth\nsubjectAltName=DNS:localhost\n")
        (tmp_path / "extensions").write_text(extensions + "subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n")
        openssl(tmp_path, "x509", "-req", "-in", f"{name}.csr", "-CA", f"{issuer}.crt",
                "-CAkey", f"{issuer}.key", "-CAcreateserial", "-days", "1", "-extfile", "extensions", "-out", f"{name}.crt")
    (tmp_path / "chain.crt").write_bytes((tmp_path / "leaf.crt").read_bytes() + (tmp_path / "intermediate.crt").read_bytes())
    openssl(tmp_path, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
            "-keyout", "self.key", "-out", "self.crt")
    return tmp_path


@pytest.mark.parametrize("kind", ["ca", "self_signed"])
@pytest.mark.parametrize("fault", [None, "hostname", "release"])
def test_candidate_tls_real_chain_and_self_signed_keep_hostname_and_release_checks(monkeypatch, certificates, kind, fault):
    root = certificates
    cert = root / ("chain.crt" if kind == "ca" else "self.crt")
    key = root / ("leaf.key" if kind == "ca" else "self.key")
    monkeypatch.setenv("SSL_CERT_FILE", str(root / "root.crt"))
    monkeypatch.setenv("SSL_CERT_DIR", str(root / "empty-roots"))
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("X-MOSS-Candidate-SHA", "wrong" if fault == "release" else "candidate")
            self.end_headers()
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = "127.0.0.1" if fault == "hostname" else "localhost"
    monkeypatch.setattr(cutover, "G7_PRODUCTION_ORIGIN", f"https://{host}:{server.server_port}")
    contexts = []
    original = ssl.create_default_context
    def verified_context(**kwargs):
        value = original(**kwargs)
        assert value.check_hostname and value.verify_mode == ssl.CERT_REQUIRED
        contexts.append(kwargs)
        return value
    monkeypatch.setattr(cutover.ssl, "create_default_context", verified_context)
    ops = object.__new__(cutover.SystemCutoverOps)
    ops.account_profile = {"MOSS_TLS_CERTFILE": str(cert)}
    try:
        if fault:
            with pytest.raises(RuntimeError, match="unavailable" if fault == "hostname" else "wrong release"):
                ops._candidate_status("candidate")
        else:
            ops._candidate_status("candidate")
        assert contexts == ([{}, {"cafile": str(cert)}] if kind == "self_signed" or fault == "hostname" else [{}])
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_candidate_probe_does_not_retry_non_certificate_failure(monkeypatch):
    contexts = []
    original = ssl.create_default_context
    def context(**kwargs):
        contexts.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(cutover.ssl, "create_default_context", context)
    def unavailable(*args, **kwargs):
        raise cutover.urllib.error.URLError(ConnectionRefusedError("connection refused"))
    monkeypatch.setattr(cutover.urllib.request, "urlopen", unavailable)
    ops = object.__new__(cutover.SystemCutoverOps)
    ops.account_profile = {"MOSS_TLS_CERTFILE": "must-not-be-read"}
    with pytest.raises(cutover.RuntimeViewUnavailable, match="connection refused"):
        ops._candidate_status("candidate")
    assert contexts == [{}]
