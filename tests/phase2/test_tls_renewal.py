from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_real_tls_rotation_preserves_held_request_and_rejects_invalid_pair():
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("_tls_reload_probe.py"))],
        cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout.strip().splitlines()[-1])
    assert observed["initial_serial"] == "01"
    assert observed["renewed_serial"] == observed["after_invalid_serial"] == "02"
    assert observed["held_request_survived"] is True
    assert "tls_certificate_reload_rejected" in result.stderr


def test_service_reload_does_not_restart_web_or_model():
    unit = (ROOT / "ops/systemd/moss-web.service").read_text()
    assert "ExecReload=/bin/kill -HUP $MAINPID" in unit


@pytest.mark.parametrize("mode", ["--check", "--staging", "--issue", "--renew"])
def test_certificate_command_uses_private_dns_file_and_never_restarts(tmp_path, mode):
    user_dir = tmp_path / "operator"
    binary_dir = tmp_path / "bin"; binary_dir.mkdir()
    config = user_dir / ".config/moss-transcribe-diarize"; config.mkdir(parents=True)
    (config / "netlify-token").write_text("dummy-private-key")
    (config / "certificate.env").write_text("MOSS_ACME_EMAIL=operator@example.test\n")
    hostname = "ga0-alienware-rtx4070ti.tailnet.aisight.us"
    certs = user_dir / ".local/share/moss-transcribe-diarize/acme/production/certificates"
    certs.mkdir(parents=True); (certs / f"{hostname}.crt").write_text("fixture")
    log = tmp_path / "commands.jsonl"
    command = f'''#!{sys.executable}
import json, os, pathlib, subprocess, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["TLS_TEST_LOG"], "a") as output:
    output.write(json.dumps([name, args]) + "\\n")
if name == "getent": print("operator:x:1000:1000::" + os.environ["TLS_TEST_USER_DIR"] + ":/bin/bash")
elif name == "stat": print("600")
elif name == "lego":
    assert os.environ.get("NETLIFY_TOKEN") is None
    if args == ["--version"]: print("lego version 5.3.1 linux/amd64")
    else:
        assert pathlib.Path(os.environ["NETLIFY_TOKEN_FILE"]).read_text() == "dummy-private-key"
        assert args[0] == "run" and args[args.index("--dns")+1] == "netlify"
        # Headscale MagicDNS answers SOA with NOTIMP, so lego must be pointed at public
        # resolvers or it cannot find the zone to write the challenge record.
        assert args[args.index("--dns.resolvers")+1] == "1.1.1.1:53,8.8.8.8:53"
        certs = pathlib.Path(args[args.index("--path")+1]) / "certificates"; certs.mkdir(parents=True, exist_ok=True)
        for suffix in ("crt", "key"): (certs / (args[args.index("--domains")+1] + "." + suffix)).write_text("fixture")
elif name == "systemctl":
    assert "restart" not in args and "moss-vllm.service" not in args
    if "show" in args: print("/bin/kill -HUP $MAINPID")
elif name == "openssl":
    if args[0] == "x509" and "-in" not in args: sys.stdin.read()
    print("serial=123")
elif name == "timeout": sys.exit(subprocess.run(args[1:]).returncode)
'''
    for name in ("getent", "stat", "flock", "systemctl", "openssl", "timeout"):
        path = binary_dir / name; path.write_text(command); path.chmod(0o700)
    lego = user_dir / ".local/bin/lego"; lego.parent.mkdir(parents=True)
    lego.write_text(command); lego.chmod(0o700)
    env = {**os.environ, "PATH": str(binary_dir) + os.pathsep + os.environ["PATH"],
           "TLS_TEST_LOG": str(log), "TLS_TEST_USER_DIR": str(user_dir)}
    env.pop("NETLIFY_TOKEN", None)
    result = subprocess.run(["bash", str(ROOT / "ops/manage-certificate.sh"), mode], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "dummy-private-key" not in result.stdout + result.stderr + log.read_text()
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    issuance = [args for name, args in rows if name == "lego" and args != ["--version"]]
    assert len(issuance) == (0 if mode == "--check" else 1)
    controls = [args for name, args in rows if name == "systemctl"]
    if mode == "--renew": assert ["--user", "reload", "moss-web.service"] in controls
    else: assert controls == []
    if mode == "--staging":
        assert issuance[0][issuance[0].index("--server")+1] == "letsencrypt-staging"
        assert issuance[0][issuance[0].index("--path")+1].endswith("/staging")


def test_certificate_command_missing_private_input_does_not_invoke_lego(tmp_path):
    binary = tmp_path / "getent"
    binary.write_text(f"#!/bin/sh\nprintf 'operator:x:1:1::{tmp_path}/missing:/bin/bash\\n'\n")
    binary.chmod(0o700)
    result = subprocess.run(["bash", str(ROOT / "ops/manage-certificate.sh"), "--issue"],
        env={**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"]}, capture_output=True, text=True)
    assert result.returncode == 1
    assert "Missing/non-private certificate prerequisite" in result.stderr
