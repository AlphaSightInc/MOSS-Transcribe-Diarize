#!/bin/bash
# Run on the presenter's MacBook: scripts/demo-precheck.sh EXPECTED_FULL_SHA
# Local verification only: MOSS_DEMO_ORIGIN and MOSS_DEMO_MACSTUDIO_BASE may
# override targets. MOSS_DEMO_RTX4090_BASE and MOSS_DEMO_OPENROUTER_API_KEY
# opt into fallback and external-provider probes. TLS is never bypassed.
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' 'NO-GO: python3 is missing'
  exit 1
fi
exec python3 - "$@" <<'PY'
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r'[0-9a-fA-F]{40}', sys.argv[1]):
        print('Usage: scripts/demo-precheck.sh EXPECTED_FULL_40_CHARACTER_SHA')
        print('NO-GO: expected full candidate SHA is required')
        return 1
    expected = sys.argv[1].lower()
    if not shutil.which('curl'):
        print('NO-GO: curl is missing')
        return 1
    origin = os.environ.get('MOSS_DEMO_ORIGIN', 'https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861').rstrip('/')
    models = [('macstudio', 'qwen/qwen3.6-35b-a3b', os.environ.get(
        'MOSS_DEMO_MACSTUDIO_BASE', 'http://macstudio.tailnet.aisight.us:1234/v1').rstrip('/'))]
    fallback_base = os.environ.get('MOSS_DEMO_RTX4090_BASE', '').strip().rstrip('/')
    if fallback_base:
        models.append(('rtx4090', 'qwen38-27b-mtp', fallback_base))
    openrouter_key = os.environ.get('MOSS_DEMO_OPENROUTER_API_KEY', '').strip()
    openrouter_base = 'https://openrouter.ai/api/v1'
    openrouter_model = 'google/gemini-2.5-flash'
    if urlsplit(origin).scheme != 'https':
        print('NO-GO: workspace origin must use trusted HTTPS')
        return 1
    if any(urlsplit(url).scheme not in ('http', 'https') for _, _, url in models):
        print('NO-GO: upstream bases must use HTTP or HTTPS')
        return 1
    failures = []
    print('Workspace:', origin, '| expected SHA:', expected, flush=True)

    def report(name, okay, detail):
        print(('PASS' if okay else 'FAIL') + ' ' + name + ': ' + detail, flush=True)
        if not okay:
            failures.append(name + ' (' + detail + ')')

    with tempfile.TemporaryDirectory(prefix='moss-demo-precheck-') as directory:
        root = Path(directory)
        cookies = root / 'cookies'
        sequence = 0

        def request(url, *, method='GET', payload=None, workspace=False, bearer_key=None):
            nonlocal sequence
            sequence += 1
            body, headers = root / f'{sequence}.json', root / f'{sequence}.headers'
            command = ['curl', '--disable', '--silent', '--show-error', '--connect-timeout', '5',
                       '--max-time', '30', '--proto', '=http,https', '--request', method,
                       '--output', str(body), '--dump-header', str(headers),
                       '--write-out', '%{http_code}\n%{time_total}\n']
            if workspace:
                command += ['--cookie', str(cookies), '--cookie-jar', str(cookies)]
            data = None
            if payload is not None:
                command += ['--header', 'Content-Type: application/json', '--data-binary', '@-']
                data = json.dumps(payload)
            if bearer_key:
                command += ['--header', 'Authorization: Bearer ' + bearer_key]
            command.append(url)
            started = time.monotonic()
            try:
                result = subprocess.run(command, input=data, text=True, capture_output=True, timeout=35)
            except subprocess.TimeoutExpired:
                return None, {}, None, f'{time.monotonic()-started:.3f} s; curl did not exit after its 30 s deadline'
            if result.returncode:
                reasons = {28: '30 s request deadline or 5 s connection deadline exceeded',
                           60: 'certificate is not trusted', 7: 'connection failed', 6: 'name resolution failed'}
                return None, {}, None, f'{time.monotonic()-started:.3f} s; ' + reasons.get(result.returncode, 'curl exit ' + str(result.returncode))
            values = result.stdout.splitlines()
            status, latency = int(values[0]), float(values[1])
            fields = {}
            for line in headers.read_text(errors='replace').splitlines():
                if ':' in line:
                    key, value = line.split(':', 1)
                    fields[key.lower()] = value.strip()
            try:
                document = json.loads(body.read_text())
            except (ValueError, UnicodeError):
                document = None
            return status, fields, document, f'{latency:.3f} s'

        status, headers, _, elapsed = request(origin + '/', workspace=True)
        host_ok = status == 200
        report('trusted host', host_ok, f'HTTP {status}, {elapsed}' if status else elapsed)
        actual = headers.get('x-moss-candidate-sha', '')
        report('candidate identity', host_ok and actual.lower() == expected,
               ('SHA ' + actual) if actual else 'X-MOSS-Candidate-SHA absent; identity unverified')
        if host_ok:
            status, _, _, elapsed = request(origin + '/api/workspace/bootstrap', method='POST', workspace=True)
            bootstrap_ok = status == 200
            report('bootstrap', bootstrap_ok, f'HTTP {status}, {elapsed}' if status else elapsed)
            if bootstrap_ok:
                status, _, document, elapsed = request(origin + '/api/llm/models', workspace=True)
                data = document.get('data', []) if isinstance(document, dict) else []
                listed = {(row.get('upstream'), row.get('id')) for row in data if isinstance(row, dict)} if isinstance(data, list) else set()
                missing = [model for name, model, _ in models if (name, model) not in listed]
                report('relay models', status == 200 and not missing,
                       (f'{len(models)} expected relay model(s) listed, ' + elapsed) if status == 200 and not missing
                       else f'HTTP {status}; missing: {", ".join(missing) or "invalid model response"}; {elapsed}')
            else:
                report('relay models', False, 'not checked: bootstrap failed')
        else:
            report('bootstrap / relay models', False, 'not checked: trusted host check failed')

        # Deliberately sequential: primary first, then fallback. Never go through the
        # relay here: its 2048-token minimum would defeat the 16-token health probe.
        for name, model, base in models:
            print(f'Probe {name}: {base} / {model}', flush=True)
            status, _, document, elapsed = request(base + '/chat/completions', method='POST', payload={
                'model': model, 'messages': [{'role': 'user', 'content': 'Reply with exactly: ready'}],
                'max_tokens': 16, 'stream': False, 'temperature': 0,
                'chat_template_kwargs': {'enable_thinking': False},
            })
            try:
                content = document['choices'][0]['message']['content']
                nonempty = isinstance(content, str) and bool(content.strip())
            except (KeyError, IndexError, TypeError):
                nonempty = False
            okay = status == 200 and nonempty
            report(name, okay, f'HTTP {status}, {elapsed}' + ('' if nonempty else '; no answer content') if status else elapsed)
        if openrouter_key:
            print(f'Probe openrouter: {openrouter_base} / {openrouter_model}', flush=True)
            status, _, document, elapsed = request(openrouter_base + '/chat/completions', method='POST', bearer_key=openrouter_key, payload={
                'model': openrouter_model, 'messages': [{'role': 'user', 'content': 'Reply with JSON: {"ready": true}'}],
                'max_tokens': 16, 'stream': False, 'temperature': 0,
                'response_format': {'type': 'json_object'},
            })
            try:
                content = document['choices'][0]['message']['content']
                nonempty = isinstance(content, str) and bool(content.strip())
            except (KeyError, IndexError, TypeError):
                nonempty = False
            okay = status == 200 and nonempty
            report('openrouter', okay, f'HTTP {status}, {elapsed}' + ('' if nonempty else '; no answer content') if status else elapsed)
    print('GO' if not failures else 'NO-GO: ' + '; '.join(failures), flush=True)
    return int(bool(failures))


try:
    sys.exit(main())
except (OSError, ValueError, TypeError) as error:
    print('NO-GO: local precheck error (' + type(error).__name__ + ')', flush=True)
    sys.exit(1)
PY
