#!/usr/bin/env python3
"""Prepared two-port renewal. Default/dry-run is offline; --apply requires host authority."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import ssl
import stat
import subprocess
import time

try:
    from .verify import certificates, inspect
except ImportError:  # Direct operator command.
    from verify import certificates, inspect

HOST = 'ga0-alienware-rtx4070ti.tailnet.aisight.us'
SERVICES = (('moss-live-web.service', 7861), ('moss-internal.service', 7862))


def parse_contact(text):
    """The existing certificate.env contract is one literal assignment, not shell."""
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if len(lines) != 1 or not lines[0].startswith('MOSS_ACME_EMAIL='):
        raise ValueError('invalid_contact_file')
    value = lines[0].split('=', 1)[1].strip().strip('\"\'')
    if '@' not in value or any(c.isspace() for c in value) or any(c in value for c in '$`'):
        raise ValueError('invalid_contact_file')
    return value


def needs_reload(observed):
    return not (observed['ok'] and observed['matches_expected_leaf'])


def event(name, **fields):
    print(json.dumps({'event': name, **fields}), flush=True)


def command(args, *, env=None):
    # Never forward provider output, command arguments, contact address or secrets.
    result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=540)
    if result.returncode:
        raise RuntimeError('command_failed')
    return result.stdout


def apply(user_dir):
    config = user_dir / '.config/moss-transcribe-diarize'
    runtime = user_dir / '.local/share/moss-transcribe-diarize'
    acme = runtime / 'acme'
    root = acme / 'production'
    cert = root / 'certificates' / f'{HOST}.crt'
    key = cert.with_suffix('.key')
    # Renewal only: initial issuance and service wiring belong to the attended runbook.
    if not cert.is_file() or not key.is_file():
        raise ValueError('initial_issuance_required')
    token = config / 'netlify-token'
    profile = config / 'certificate.env'
    for path in (token, profile):
        if stat.S_IMODE(path.stat().st_mode) != 0o600 or path.stat().st_size == 0:
            raise ValueError('private_prerequisite_missing')
    contact = parse_contact(profile.read_text())
    lego = str(user_dir / '.local/bin/lego')
    if not command([lego, '--version']).startswith('lego version 5.'):
        raise ValueError('lego_v5_required')
    for unit, _ in SERVICES:
        command(['systemctl', '--user', 'is-active', '--quiet', unit])
        reload_action = command(['systemctl', '--user', 'show', unit, '--property=ExecReload', '--value'])
        if 'kill -HUP' not in reload_action:
            raise ValueError('qualified_reload_required')
    # Share the legacy command's lock, including retries after partial activation.
    with (acme / 'operation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        env = dict(os.environ)
        env.pop('NETLIFY_TOKEN', None)
        env['NETLIFY_TOKEN_FILE'] = str(token)
        command([lego, 'run', '--accept-tos', '--email', contact, '--domains', HOST,
                 '--dns', 'netlify', '--dns.resolvers', '1.1.1.1:53,8.8.8.8:53',
                 '--server', 'letsencrypt', '--path', str(root), '--no-random-sleep'], env=env)
        key.chmod(0o600)
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(cert, key)
        desired = ssl.PEM_cert_to_DER_cert(certificates(cert.read_text())[0])
        failed = []
        for unit, port in SERVICES:
            observed = inspect(HOST, port, connect_host='127.0.0.1', expected_der=desired)
            if needs_reload(observed):
                command(['systemctl', '--user', 'reload', unit])
                # Existing ops command's bounded handshake wait; not an issuance retry.
                for _ in range(10):
                    observed = inspect(HOST, port, connect_host='127.0.0.1', expected_der=desired)
                    if not needs_reload(observed):
                        break
                    time.sleep(1)
                event('reload_checked', port=port, ok=not needs_reload(observed))
            else:
                event('already_current', port=port)
            if needs_reload(observed):
                failed.append(port)
        if failed:
            raise RuntimeError('served_certificate_not_confirmed')
        event('renewal_verified', ports=[port for _, port in SERVICES])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Offline plan only (default); not ACME staging')
    mode.add_argument('--apply', action='store_true', help='Authorized host execution: DNS, files, SIGHUP')
    args = parser.parse_args(argv)
    if not args.apply:
        event('dry_run', host=HOST, ports=[port for _, port in SERVICES],
              actions=['lego_due_renewal', 'reload_mismatched_listeners', 'verify_both'],
              effects=0, prerequisites_checked=False)
        return 0
    try:
        import pwd
        os.umask(0o077)
        apply(Path(pwd.getpwuid(os.getuid()).pw_dir))
    except (OSError, ValueError, RuntimeError, ssl.SSLError, subprocess.SubprocessError) as exc:
        # Controlled labels only; library exceptions can contain credentials or paths.
        event('renewal_failed', error_type=type(exc).__name__)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
