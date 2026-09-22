#!/usr/bin/env python3
"""THROWAWAY: exercise rows 5 -> 10 -> 8 with real Chromium and a P2 stub."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import runpy
import signal
import socket
import subprocess
import sys
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path('/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python')
MANIFEST = Path('/Users/gao/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json')
MODEL = Path('/Users/gao/.cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/e8681d68e7042738ffca8ac8212bc8fcb1131ab8')
CORPUS = ROOT / 'evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s'
STACK_PORT = 17851
STUB_PORT = 19453
PROXY_PORT = 19454


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', port))
        except OSError:
            return False
    return True


def listener_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(.5)
        return probe.connect_ex(('127.0.0.1', port)) == 0


def stop(process: subprocess.Popen[bytes] | None) -> None:
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=15)


def wait_ready(process: subprocess.Popen[bytes], url: str) -> float:
    from tools.qualify.run import ready_descriptor

    started = time.monotonic()
    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError('local_stack_start_failed')
        try:
            if ready_descriptor(url).get('source_revision'):
                return time.monotonic() - started
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError('local_stack_not_ready')


def wait_stub(process: subprocess.Popen[bytes]) -> None:
    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError('p2_stub_start_failed')
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{STUB_PORT}/v1/models', timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(.1)
    raise RuntimeError('p2_stub_not_ready')


def load_workspace():
    path = ROOT / 'tests/e2e/verify_workspace.py'
    spec = importlib.util.spec_from_file_location('i4b_verify_workspace', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('workspace_import_unavailable')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--loopback', action='store_true', required=True)
    parser.add_argument('--out', type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out = args.out.resolve()
    if out.exists():
        raise SystemExit('REFUSE: output exists')
    if not (PYTHON.is_file() and MANIFEST.is_file() and MODEL.is_dir() and (CORPUS / 'audio.wav').is_file()):
        raise SystemExit('REFUSE: prescribed runtime inputs unavailable')
    if not all(port_is_free(port) for port in (STACK_PORT, STUB_PORT, PROXY_PORT)):
        raise SystemExit('REFUSE: owned loopback port occupied')
    out.mkdir(parents=True)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH='.', MOSS_TEST_REAL_SQLITE='1')
    for name in ('OPENROUTER_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'MOSS_LLM_UPSTREAMS'):
        environment.pop(name, None)
    result = {
        'schema_version': 1,
        'mode': 'real_chromium_media_source_p2_loopback',
        'rows_requested': [4, 10, 8],
        'decoder_requests_real': 0,
        'ports': {'stack': STACK_PORT, 'stub': STUB_PORT, 'proxy': PROXY_PORT},
        'raw_playwright_errors': [],
        'check_sequence': [],
    }
    stub = stack = proxy = None
    try:
        stub = subprocess.Popen(
            [str(PYTHON), str(ROOT / 'prototypes/round5-p2/loopback_vllm_stub.py'), '--port', str(STUB_PORT), '--out', str(out / 'p2-stub')],
            cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
        wait_stub(stub)
        from tools.qualify.decoder import Decoder
        proxy = Decoder(PROXY_PORT, STUB_PORT, 250, out / 'decoder-proxy.jsonl')
        proxy.start()
        launch = runpy.run_path(str(ROOT / 'prototypes/feature-rows/launch.py'))
        runtime = out / 'runtime'
        runtime.mkdir()
        cert, key = launch['_certificate'](runtime)
        from tools.qualify.run import local_stack_command
        stack_log = (runtime / 'stack.log').open('wb')
        try:
            stack = subprocess.Popen(
                local_stack_command(
                    state=runtime / 'state', cert=cert, key=key, port=STACK_PORT,
                    manifest=MANIFEST, vllm_base_url=f'http://127.0.0.1:{PROXY_PORT}/v1',
                    max_requests=250, model=MODEL,
                ),
                cwd=ROOT, env=environment, stdout=stack_log, stderr=subprocess.STDOUT, start_new_session=True,
            )
            result['stack_ready_seconds'] = round(wait_ready(stack, f'https://127.0.0.1:{STACK_PORT}'), 3)
            workspace = load_workspace()
            original_fresh = workspace.Harness._fresh_row10_context
            original_check = workspace.Harness.check
            original_bank = workspace.Harness.bank
            original_interrupted = workspace.Harness.interrupted

            async def capture_fresh(harness):
                try:
                    return await original_fresh(harness)
                except Exception as exc:
                    result['raw_playwright_errors'].append({'type': type(exc).__name__, 'message': str(exc)})
                    (out / 'raw-playwright-errors.json').write_text(json.dumps(result['raw_playwright_errors'], indent=2) + '\n')
                    raise

            async def capture_check(harness, number, function):
                result['check_sequence'].append(number)
                return await original_check(harness, number, function)

            async def capture_bank(harness):
                try:
                    return await original_bank(harness)
                except Exception as exc:
                    result['raw_playwright_errors'].append({'type': type(exc).__name__, 'message': str(exc)})
                    (out / 'raw-playwright-errors.json').write_text(json.dumps(result['raw_playwright_errors'], indent=2) + '\n')
                    raise

            async def capture_interrupted(harness):
                result['row8_second_live_before_lookup'] = harness.state['meetings'].get('second_live')
                return await original_interrupted(harness)

            workspace.Harness._fresh_row10_context = capture_fresh
            workspace.Harness.check = capture_check
            workspace.Harness.bank = capture_bank
            workspace.Harness.interrupted = capture_interrupted
            result['workspace_exit_code'] = workspace.main([
                '--base', f'https://127.0.0.1:{STACK_PORT}', '--allow-local-self-signed',
                '--corpus', str(CORPUS), '--output', str(out / 'workspace'), '--rows', '4,10,8',
            ])
        finally:
            stack_log.close()
    except Exception as exc:
        result['prototype_exception'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        stop(stack)
        if proxy is not None:
            result['proxy'] = asdict(proxy.snapshot())
            proxy.close()
        stop(stub)

    workspace_result = out / 'workspace/results.json'
    rows = json.loads(workspace_result.read_text()).get('rows', {}) if workspace_result.is_file() else {}
    result['rows'] = {
        number: {key: rows.get(number, {}).get(key) for key in ('status', 'reason_code', 'exception', 'meeting')}
        for number in ('5', '10', '8')
    }
    p2_requests = out / 'p2-stub/requests.jsonl'
    result['p2_stub_requests'] = sum(1 for _ in p2_requests.open()) if p2_requests.is_file() else 0
    result['listeners_after'] = {name: listener_open(port) for name, port in result['ports'].items()}
    ordered = all(number in result['check_sequence'] for number in (5, 10, 8)) and (
        result['check_sequence'].index(5) < result['check_sequence'].index(10) < result['check_sequence'].index(8)
    )
    result['status'] = 'SUPPORTED' if (
        ordered and not result['raw_playwright_errors'] and result['rows']['10']['exception'] is None
        and result.get('row8_second_live_before_lookup') and not any(result['listeners_after'].values())
    ) else 'FALSIFIED'
    (out / 'result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['status'] == 'SUPPORTED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
