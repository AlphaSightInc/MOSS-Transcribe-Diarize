"""Offline WP13 operator tools: no production DNS, certificate issuance or signals."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import threading

import pytest

from ops.tls import renew, verify

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('offset,expected', [(-1, False), (0, True), (1, True)])
def test_expiry_alarm_has_exact_21_day_boundary(offset, expected):
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    expiry = now + timedelta(days=21, seconds=offset)
    assert verify.expiry_ok([{'not_after': expiry.isoformat()}], now) is expected
    assert not verify.expiry_ok([], now)
    assert not verify.expiry_ok([{'not_after': (now + timedelta(days=60)).isoformat()},
                                 {'not_after': (now - timedelta(seconds=1)).isoformat()}], now)


def test_parse_openssl_metadata_and_chain():
    parsed = verify.parse_metadata('subject=CN=moss\nissuer=CN=issuer\nserial=01\nnotAfter=Dec  9 21:32:04 2026 GMT\n')
    assert parsed == {'subject': 'CN=moss', 'issuer': 'CN=issuer', 'serial': '01',
                      'not_after': '2026-12-09T21:32:04+00:00'}
    assert len(verify.certificates('noise\n-----BEGIN CERTIFICATE-----\nYQ==\n-----END CERTIFICATE-----\n' * 2)) == 2
    with pytest.raises(ValueError): verify.certificates('connection refused')


@pytest.mark.parametrize('profile', ['MOSS_ACME_EMAIL=person@example.test\n',
                                      '# comment\nMOSS_ACME_EMAIL="person@example.test"\n'])
def test_contact_literal_assignment(profile):
    assert renew.parse_contact(profile) == 'person@example.test'


@pytest.mark.parametrize('profile', ['MOSS_ACME_EMAIL=$(whoami)@example.test',
                                      'MOSS_ACME_EMAIL=one@example.test\nOTHER=two', 'EMAIL=one@example.test'])
def test_contact_does_not_execute_shell(profile):
    with pytest.raises(ValueError): renew.parse_contact(profile)


@pytest.mark.parametrize('args', [[], ['--dry-run']])
def test_dry_run_never_reads_prerequisites_or_executes(args, monkeypatch, capsys):
    def forbidden(*a, **kw): raise AssertionError('dry-run performed IO')
    monkeypatch.setattr(renew, 'apply', forbidden)
    monkeypatch.setattr(renew, 'command', forbidden)
    monkeypatch.setattr(Path, 'read_text', forbidden)
    assert renew.main(args) == 0
    assert json.loads(capsys.readouterr().out)['effects'] == 0


@pytest.fixture
def pair(tmp_path):
    cert, key = tmp_path / 'test.crt', tmp_path / 'test.key'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '30',
                    '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost',
                    '-keyout', str(key), '-out', str(cert)], capture_output=True, check=True)
    return cert, key


def test_verifier_real_socket_untrusted_then_trusted_then_wrong_name(pair, monkeypatch):
    cert, key = pair
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0)); listener.listen(); listener.settimeout(.1)
    port = listener.getsockname()[1]
    stop = threading.Event()
    def serve():
        while not stop.is_set():
            try: raw, _ = listener.accept()
            except socket.timeout: continue
            try:
                with context.wrap_socket(raw, server_side=True) as connection:
                    connection.recv(1)
            except (ssl.SSLError, OSError): raw.close()
    thread = threading.Thread(target=serve); thread.start()
    try:
        observed = verify.inspect('localhost', port, connect_host='127.0.0.1')
        assert not observed['ok'] and not observed['trusted'] and observed['expiry_ok']
        assert len(observed['chain']) == 1
        original = ssl.create_default_context
        def trusted():
            ctx = original(); ctx.load_verify_locations(cafile=cert); return ctx
        monkeypatch.setattr(ssl, 'create_default_context', trusted)
        der = ssl.PEM_cert_to_DER_cert(cert.read_text())
        observed = verify.inspect('localhost', port, connect_host='127.0.0.1', expected_der=der)
        assert observed['ok'] and observed['matches_expected_leaf']
        mismatch = verify.inspect('localhost', port, connect_host='127.0.0.1', expected_der=b'other')
        assert renew.needs_reload(mismatch)
        wrong = verify.inspect('wrong.example.test', port, connect_host='127.0.0.1')
        assert not wrong['ok'] and not wrong['trusted']
    finally:
        stop.set(); thread.join(timeout=2); listener.close()
        assert not thread.is_alive()


def test_renew_retry_converges_both_ports_without_redundant_reload(tmp_path, pair, monkeypatch):
    user = tmp_path / 'operator'
    cfg = user / '.config/moss-transcribe-diarize'; cfg.mkdir(parents=True)
    for name, text in [('netlify-token', 'private-sentinel'), ('certificate.env', 'MOSS_ACME_EMAIL=private@example.test')]:
        p = cfg / name; p.write_text(text); p.chmod(0o600)
    root = user / '.local/share/moss-transcribe-diarize/acme/production/certificates'
    root.mkdir(parents=True)
    for source, suffix in zip(pair, ['crt', 'key']): shutil.copy(source, root / f'{renew.HOST}.{suffix}')
    calls = []
    current = {7861: True, 7862: False}  # prior partial activation, files already renewed
    def command(args, *, env=None):
        calls.append(args)
        if args[-1] == '--version': return 'lego version 5.3.1'
        if 'show' in args: return '/bin/kill -HUP $MAINPID'
        if args[1] == 'run':
            assert env['NETLIFY_TOKEN_FILE'] == str(cfg / 'netlify-token')
            assert 'NETLIFY_TOKEN' not in env
            assert args[args.index('--dns.resolvers')+1] == '1.1.1.1:53,8.8.8.8:53'
        if 'reload' in args: current[dict(renew.SERVICES)[args[-1]]] = True
        return ''
    def inspect(host, port, **kw):
        assert kw['expected_der'] == ssl.PEM_cert_to_DER_cert(pair[0].read_text())
        return {'ok': True, 'matches_expected_leaf': current[port]}
    monkeypatch.setattr(renew, 'command', command)
    monkeypatch.setattr(renew, 'inspect', inspect)
    monkeypatch.setenv('NETLIFY_TOKEN', 'must-not-pass-through')
    renew.apply(user); renew.apply(user)
    assert [args for args in calls if 'reload' in args] == [['systemctl', '--user', 'reload', 'moss-internal.service']]
    assert len([args for args in calls if len(args)>1 and args[1]=='run']) == 2
    assert all('restart' not in args for args in calls)


def test_provider_failure_does_not_print_private_output(monkeypatch, capsys):
    def failure(*a, **kw):
        raise subprocess.CalledProcessError(1, ['private-sentinel'], output='private-sentinel')
    monkeypatch.setattr(renew, 'apply', failure)
    assert renew.main(['--apply']) == 1
    output = capsys.readouterr()
    assert 'private-sentinel' not in output.out + output.err
    assert json.loads(output.out)['event'] == 'renewal_failed'


def test_verify_layout_current_tree():
    subprocess.run(['bash', str(ROOT / 'scripts/check_verify_layout.sh')], check=True)


def test_verify_layout_rejects_root_copy(tmp_path):
    (tmp_path / 'scripts').mkdir()
    shutil.copy(ROOT / 'scripts/check_verify_layout.sh', tmp_path / 'scripts')
    (tmp_path / 'VERIFY.md').write_text('wrong location')
    result = subprocess.run(['bash', str(tmp_path / 'scripts/check_verify_layout.sh')], capture_output=True, text=True)
    assert result.returncode == 1
    assert 'docs/verify/<wp>/' in result.stderr


def test_unqualified_live_web_refuses_before_issuer(tmp_path, pair, monkeypatch):
    cfg = tmp_path / '.config/moss-transcribe-diarize'; cfg.mkdir(parents=True)
    for name, text in [('netlify-token', 'private'), ('certificate.env', 'MOSS_ACME_EMAIL=private@example.test')]:
        path = cfg / name; path.write_text(text); path.chmod(0o600)
    certs = tmp_path / '.local/share/moss-transcribe-diarize/acme/production/certificates'
    certs.mkdir(parents=True)
    for source, suffix in zip(pair, ['crt', 'key']): shutil.copy(source, certs / f'{renew.HOST}.{suffix}')
    calls = []
    def command(args, **kw):
        calls.append(args)
        if args[-1] == '--version': return 'lego version 5.3.1'
        if 'show' in args:
            assert 'moss-live-web.service' in args
            return ''  # observed live unit has no reload action
        return ''
    monkeypatch.setattr(renew, 'command', command)
    with pytest.raises(ValueError, match='qualified_reload_required'):
        renew.apply(tmp_path)
    assert not any('run' in args or 'reload' in args for args in calls)
