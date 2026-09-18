#!/usr/bin/env python3
"""Read-only TLS chain/hostname/expiry check. No HTTP requests or custom trust bypass."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import socket
import ssl
import subprocess

MIN_DAYS = 21
PEM_PATTERN = r'-----BEGIN CERTIFICATE-----\s+.*?-----END CERTIFICATE-----'


def certificates(text):
    certs = re.findall(PEM_PATTERN, text, re.DOTALL)
    if not certs:
        raise ValueError('no_certificates')
    return certs


def parse_metadata(text):
    fields = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
    expiry = datetime.fromtimestamp(ssl.cert_time_to_seconds(fields['notAfter']), timezone.utc)
    return {'subject': fields['subject'], 'issuer': fields['issuer'],
            'serial': fields['serial'], 'not_after': expiry.isoformat()}


def metadata(pem):
    result = subprocess.run(['openssl', 'x509', '-noout', '-subject', '-issuer', '-serial',
                             '-enddate', '-nameopt', 'RFC2253'],
                            input=pem, capture_output=True, text=True, timeout=10, check=True)
    return parse_metadata(result.stdout)


def days_remaining(not_after, now):
    return (datetime.fromisoformat(not_after) - now).total_seconds() / 86400


def expiry_ok(chain, now):
    return bool(chain) and all(days_remaining(cert['not_after'], now) >= MIN_DAYS for cert in chain)


def inspect(host, port, *, connect_host=None, expected_der=None):
    """Normal Python system roots establish trust; openssl captures diagnostic chain.

    The second connection must return the same leaf before its chain can describe
    the verified connection. A failed trust check never becomes a pass just because
    the diagnostic connection returned a parseable certificate.
    """
    now = datetime.now(timezone.utc)
    result = {'host': host, 'port': port, 'observed_at': now.isoformat(),
              'trusted': False, 'minimum_days': MIN_DAYS, 'chain': [], 'ok': False}
    address = connect_host or host
    verified_der = None
    try:
        with socket.create_connection((address, port), timeout=10) as raw:
            with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as tls:
                verified_der = tls.getpeercert(binary_form=True)
                result['trusted'] = True
    except ssl.SSLCertVerificationError as exc:
        result['trust_error'] = exc.verify_message
    except (OSError, ssl.SSLError) as exc:
        result['trust_error'] = type(exc).__name__
    try:
        endpoint = f'[{address}]:{port}' if ':' in address else f'{address}:{port}'
        probe = subprocess.run(['openssl', 's_client', '-connect', endpoint,
                                '-servername', host, '-showcerts'], input='',
                               capture_output=True, text=True, timeout=15)
        pems = certificates(probe.stdout)
        result['chain'] = [metadata(pem) for pem in pems]
        if expected_der is not None:
            result['matches_expected_leaf'] = expected_der == ssl.PEM_cert_to_DER_cert(pems[0])
        result['leaf_days_remaining'] = round(days_remaining(result['chain'][0]['not_after'], now), 6)
        result['expiry_ok'] = expiry_ok(result['chain'], now)
        result['same_verified_leaf'] = verified_der == ssl.PEM_cert_to_DER_cert(pems[0])
        result['ok'] = result['trusted'] and result['same_verified_leaf'] and result['expiry_ok']
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        result['chain_error'] = type(exc).__name__
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host', help='Canonical DNS hostname; used for SNI and hostname verification')
    parser.add_argument('port', type=int)
    parser.add_argument('--connect-host', help='Optional transport address; does not change the verified name')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    result = inspect(args.host, args.port, connect_host=args.connect_host)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
