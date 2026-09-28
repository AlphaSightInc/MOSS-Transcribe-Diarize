"""THROWAWAY E2E DOM replay at 1.0x through production live session HTTP ingress.

Run: python prototypes/gemini-live/e2e/run.py --stub --system WAV --mic WAV --out DIR
Or use --stack-url URL with an already running Gemini stack. No physical devices.
"""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
import signal
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
from tests.e2e.verify_demo_lanes import Client
from tap_proxy import TapProxy
from visual_metrics import compute as compute_visual_metrics

EVIDENCE = Path('/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P64')
SOURCE_MANIFEST = Path.home() / '.local/share/moss-transcribe-diarize/live/live-provider-manifest.json'
HOST_CONFIG_HASH = '431efb3f5c0c3d0b685a8121b4e72eee08fc8072001f6d9b178e924321d7a265'
HOST_MAX_TAPE_BYTES = 19_200_000  # H1 #3 deployed descriptor, raw/deployed-observations.json:343
BASE_SHA = '8d8fb682884bd29369879698d8233a1b281b77d7'
SILENCE_RMS = 1e-4  # frontend/src/capture/captureClient.ts:175


def candidate_manifest(destination: Path) -> str:
    from moss_transcribe_diarize.app.live_manifest_finalizer import (
        LiveIdentityRecalibration, LiveManifestRetune, finalize_payload,
    )
    from moss_transcribe_diarize.app.live_provider_bundle import (
        LiveProviderBundleConfig, compute_live_provider_manifest_hash,
    )
    payload = json.loads(SOURCE_MANIFEST.read_text())
    if payload['config_hashes']['combined_config_hash'] != HOST_CONFIG_HASH:
        raise RuntimeError('local provider config differs from host receipt')
    for asset in [*payload['assets'], payload['golden']['input']]:
        asset['path'] = str((SOURCE_MANIFEST.parent / asset['path']).resolve())
    bounds, identity, provider = (payload[key] for key in
                                  ('bounds_config', 'identity_config', 'identity_provider'))
    # The local August manifest has 9.6 MB; H1 #3's frozen host descriptor has 19.2 MB.
    # This bound is absent from the combined config digest, so bind it explicitly.
    bounds['max_tape_bytes'] = HOST_MAX_TAPE_BYTES
    final, _ = finalize_payload(
        payload, source_revision=BASE_SHA,
        retune=LiveManifestRetune(
            hard_cap_samples=bounds['hard_cap_samples'],
            max_retained_samples=bounds['max_retained_samples'],
            frame_samples=bounds['frame_samples'],
            max_tape_bytes=bounds.get('max_tape_bytes')),
        identity=LiveIdentityRecalibration(
            min_match_score=identity['min_match_score'],
            min_match_margin=identity['min_match_margin'],
            album_admission_seconds=provider['album_admission_seconds'],
            birth_min_seconds=provider['birth_min_seconds']))
    destination.write_text(json.dumps(final, indent=2) + '\n')
    destination.chmod(0o600)
    return compute_live_provider_manifest_hash(LiveProviderBundleConfig.from_manifest(destination))


def read_wav(path: Path) -> bytes:
    if str(path) == 'silence':
        return b''
    with wave.open(str(path), 'rb') as source:
        assert (source.getframerate(), source.getnchannels(), source.getsampwidth()) == (16000, 1, 2)
        return source.readframes(source.getnframes())


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=20)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def event_drain(base: str, jar: dict, meeting: str, out: Path,
                stop: threading.Event, state: dict) -> None:
    client = Client(base, ssl._create_unverified_context())
    client._jar = dict(jar)
    cursor = -1
    next_snapshot = 0.0
    try:
        while True:
            events = client.call('GET', f'/api/live/sessions/{meeting}/events?since_seq={cursor}').get('events', [])
            with out.open('a', encoding='utf-8') as stream:
                for event in events:
                    seq = int(event['seq'])
                    if seq < cursor:
                        continue
                    stream.write(json.dumps({'observed_monotonic_ns': time.monotonic_ns(),
                                             'event': event}, ensure_ascii=False) + '\n')
                    cursor = seq + 1
                    state['events'] += 1
            if time.monotonic() >= next_snapshot:
                snapshot = client.call('GET', f'/api/live/sessions/{meeting}/snapshot')
                with out.with_name('service-snapshots.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps({'observed_monotonic_ns': time.monotonic_ns(),
                                             'snapshot': snapshot}, ensure_ascii=False) + '\n')
                state['snapshots'] += 1
                next_snapshot = time.monotonic() + .25
            if stop.is_set():
                break
            stop.wait(.1)
    except Exception as exc:
        state['error_type'] = type(exc).__name__


def dom_rows(page) -> list[dict]:
    return page.evaluate('''() => Array.from(document.querySelectorAll('article.utt')).map((node, order) => {
      const label = node.querySelector('.utt-speaker-label')?.textContent?.trim() || '';
      return {order, label, uncertain: label === 'Speaker uncertain',
        text: node.querySelector('.utt-text')?.textContent?.trim() || '',
        speaker_id: node.querySelector('.utt-speaker')?.getAttribute('data-speaker-id'),
        state: node.getAttribute('data-state'), lane: node.getAttribute('data-source-lane'),
        start: node.getAttribute('data-turn-start'), end: node.getAttribute('data-turn-end'),
        target_keys: node.getAttribute('data-target-keys'),
        segments: JSON.parse(node.getAttribute('data-segments') || '[]')};
    })''')


def filmstrip_capture(base: str, jar: dict, meeting: str, out: Path,
                      stop: threading.Event, ready: threading.Event, state: dict) -> None:
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as browser_runtime:
            browser = browser_runtime.chromium.launch(
                headless=True,
                executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
            context = browser.new_context(ignore_https_errors=True, viewport={'width': 1440, 'height': 900},
                                          device_scale_factor=1)
            try:
                context.add_cookies([{'name': name, 'value': value, 'url': base, 'secure': True}
                                     for name, value in jar.items()])
                page = context.new_page()
                page.goto(base, wait_until='domcontentloaded')
                page.locator('[data-boot="ready"]').wait_for(timeout=30000)
                page.evaluate('''id => document.dispatchEvent(new CustomEvent(
                  'moss:observe-live-meeting', {detail:{meetingId:id}}))''', meeting)
                ready.set()
                start = time.monotonic()
                tick = 0
                while not stop.is_set():
                    stop.wait(max(0, start + tick * .25 - time.monotonic()))
                    if stop.is_set():
                        break
                    rows = dom_rows(page)
                    state['nonempty'] += bool(rows)
                    with out.open('a', encoding='utf-8') as stream:
                        stream.write(json.dumps({'observed_monotonic_ns': time.monotonic_ns(),
                                                 'rows': rows}, ensure_ascii=False) + '\n')
                    state['snapshots'] += 1
                    audio_start = state.get('audio_start_monotonic_ns')
                    if audio_start is not None:
                        elapsed = (time.monotonic_ns() - audio_start) / 1e9
                        for fraction, name in ((.25, 'at-25-percent.png'), (.75, 'at-75-percent.png')):
                            if elapsed >= state['audio_seconds'] * fraction and name not in state['screenshots']:
                                page.screenshot(path=str(out.with_name(name)))
                                state['screenshots'].append(name)
                    if state.get('final_ready') and 'after-final.png' not in state['screenshots']:
                        page.evaluate('''id => document.dispatchEvent(new CustomEvent(
                          'moss:open-meeting', {detail:{meetingId:id}}))''', meeting)
                        page.wait_for_timeout(1500)
                        page.screenshot(path=str(out.with_name('after-final.png')))
                        state['screenshots'].append('after-final.png')
                    tick += 1
            finally:
                context.close()
                browser.close()
    except Exception as exc:
        state['error_type'] = type(exc).__name__
        ready.set()


def capture_arm(base: str, system_path: Path, mic_path: Path, seconds: float, out: Path) -> dict:
    client = Client(base, ssl._create_unverified_context())
    client.call('POST', '/api/workspace/bootstrap')
    descriptor = client.call('GET', '/api/live/descriptor')['descriptor']
    size, rate = descriptor['frame_samples'], descriptor['sample_rate']
    if rate != 16000:
        raise RuntimeError('unexpected live sample rate')
    created = client.call('POST', '/api/live/sessions', {'source_revision': descriptor['source_revision']})
    meeting = created.get('id') or created['session_id']
    system = read_wav(system_path)
    microphone = read_wav(mic_path)
    frame_bytes = size * 2
    total_frames = math.ceil(seconds * rate / size)
    tail_frames = math.ceil(6 * rate / size)
    drain_stop = threading.Event()
    drain_state = {'events': 0, 'snapshots': 0}
    drain = threading.Thread(target=event_drain,
                            args=(base, client._jar, meeting, out / 'events.jsonl',
                                  drain_stop, drain_state), daemon=True)
    drain.start()
    film_stop = threading.Event()
    film_ready = threading.Event()
    film_state = {'snapshots': 0, 'nonempty': 0, 'audio_seconds': seconds,
                  'screenshots': [], 'final_ready': False}
    film = threading.Thread(target=filmstrip_capture,
                           args=(base, client._jar, meeting, out / 'filmstrip.jsonl',
                                 film_stop, film_ready, film_state), daemon=True)
    film.start()
    max_pacing_lag = 0.0
    try:
        if not film_ready.wait(45) or film_state.get('error_type'):
            raise RuntimeError('headless frontend startup failed')
        epoch = time.time_ns()
        frame_seconds = size / rate
        start = time.monotonic()
        film_state['audio_start_monotonic_ns'] = time.monotonic_ns()
        (out / 'audio-start.json').write_text(json.dumps({
            'monotonic_ns': film_state['audio_start_monotonic_ns'],
            'audio_seconds': seconds}) + '\n')
        next_frame = 0
        with ThreadPoolExecutor(max_workers=2) as frame_pool:
          while next_frame < total_frames + tail_frames:
            scheduled_frame = start + next_frame * frame_seconds
            time.sleep(max(0, scheduled_frame - time.monotonic()))
            if next_frame < total_frames + tail_frames:
                sequence = next_frame
                health = dict(state='capturing', device_epoch=epoch, dropped_frames=0,
                              discontinuities=0, failure_code=None)
                client.call('POST', f'/api/live/sessions/{meeting}/heartbeat', {
                    'schema': 'moss-live-helper-health.v1', 'instance_id': 'dx-browser-replay',
                    'sequence': sequence, 'sent_monotonic_ns': time.monotonic_ns(),
                    'helper_version': 'dx-browser-replay', 'state': 'capturing',
                    'lanes': {'system': health, 'microphone': dict(health)}})
                payloads = []
                for lane, audio in (('system', system), ('microphone', microphone)):
                    chunk = (audio[sequence * frame_bytes:(sequence + 1) * frame_bytes]
                             if sequence < total_frames else b'')
                    chunk = chunk.ljust(frame_bytes, b'\0')
                    import array
                    values = array.array('h')
                    values.frombytes(chunk)
                    rms = math.sqrt(sum(v * v for v in values) / len(values)) / 32768
                    payloads.append({
                        'lane': lane, 'sequence': sequence,
                        'capture_timestamp_ns': round(sequence * frame_seconds * 1e9),
                        'capture_end_timestamp_ns': round((sequence + 1) * frame_seconds * 1e9),
                        'device_epoch': epoch, 'pcm_base64': base64.b64encode(chunk).decode(),
                        'sample_count': size, 'sample_rate': rate,
                        'silent': rms < SILENCE_RMS, 'discontinuity': False})
                futures = [frame_pool.submit(client.call, 'POST',
                    f'/api/live/sessions/{meeting}/frames', payload) for payload in payloads]
                for future in futures:
                    future.result()
                max_pacing_lag = max(max_pacing_lag, time.monotonic() - scheduled_frame)
                next_frame += 1
        before_stop = client.call('GET', f'/api/live/sessions/{meeting}/snapshot')
        (out / 'pre-stop-snapshot.json').write_text(json.dumps(before_stop, ensure_ascii=False))
        client.call('POST', f'/api/live/sessions/{meeting}/stop', {'deadline': 30})
        final = None
        for _ in range(600):
            final = client.call('GET', f'/api/live/sessions/{meeting}/snapshot')
            status = ((final.get('snapshot') or {}).get('session') or {}).get('finalization_status')
            if status in ('final', 'failed', 'unavailable'):
                break
            time.sleep(.5)
        (out / 'final-snapshot.json').write_text(json.dumps(final, ensure_ascii=False))
        saved = client.call('GET', f'/api/meetings/{meeting}')
        (out / 'saved-meeting.json').write_text(json.dumps(saved, ensure_ascii=False))
        film_state['final_ready'] = True
        for _ in range(40):
            if 'after-final.png' in film_state['screenshots'] or film_state.get('error_type'):
                break
            time.sleep(.25)
        if (not film_state['nonempty'] or film_state.get('error_type') or
                drain_state.get('error_type') or status != 'final' or saved.get('status') != 'completed' or
                len(film_state['screenshots']) != 3):
            raise RuntimeError('incomplete frontend, event, or final surface')
        result = {'seconds': seconds, 'frame_samples': size,
                'frames_per_lane': total_frames, 'tail_frames_per_lane': tail_frames,
                'filmstrip_snapshots': film_state['snapshots'],
                'filmstrip_nonempty_snapshots': film_state['nonempty'],
                'filmstrip_error_type': film_state.get('error_type'),
                'events': drain_state['events'], 'event_error_type': drain_state.get('error_type'),
                'service_snapshots': drain_state['snapshots'],
                'max_pacing_lag_s': round(max_pacing_lag, 3),
                'final_status': ((final.get('snapshot') or {}).get('session') or {}).get('finalization_status'),
                'saved_status': saved.get('status'), 'screenshots': film_state['screenshots']}
    finally:
        drain_stop.set()
        drain.join(timeout=10)
        film_stop.set()
        film.join(timeout=15)
    result['events'] = drain_state['events']
    result['service_snapshots'] = drain_state['snapshots']
    result['filmstrip_snapshots'] = film_state['snapshots']
    result['filmstrip_nonempty_snapshots'] = film_state['nonempty']
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--stub', action='store_true')
    mode.add_argument('--stack-url')
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--mic', type=Path, required=True, help='16 kHz mono PCM WAV, or silence')
    parser.add_argument('--seconds', type=float)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--budget', type=int, default=1050)
    parser.add_argument('--stack-port', type=int, default=18520)
    parser.add_argument('--proxy-port', type=int, default=18521)
    parser.add_argument('--stub-port', type=int, default=18522)
    args = parser.parse_args()
    out = args.out.resolve()
    if EVIDENCE not in out.parents or out.exists():
        parser.error('--out must be new and under evidence/P64')
    if args.stub and len({args.stack_port, args.proxy_port, args.stub_port}) != 3:
        parser.error('stub, proxy, and stack ports must differ')
    if args.stub and any(port < 18520 or port > 18529 for port in
                         (args.stack_port, args.proxy_port, args.stub_port)):
        parser.error('local ports must be in 18520-18529')
    with wave.open(str(args.system), 'rb') as source:
        seconds = min(args.seconds or source.getnframes() / source.getframerate(),
                      source.getnframes() / source.getframerate())
    if str(args.mic) != 'silence':
        with wave.open(str(args.mic), 'rb') as source:
            seconds = min(seconds, source.getnframes() / source.getframerate())
    out.mkdir(parents=True, mode=0o700)
    summary = {'mode': 'moss_loopback_stub' if args.stub else 'external_stack',
               'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'status': 'INCOMPLETE', 'provider_spend_usd': 0 if args.stub else 'UNMEASURED',
               'gemini_timing_anomalies': {'calls': 'UNMEASURED',
                                           'clamped': 'UNMEASURED',
                                           'dropped': 'UNMEASURED',
                                           'clamped_per_call': 'UNMEASURED',
                                           'dropped_per_call': 'UNMEASURED'}}
    app = stub = proxy = stack_log = None
    try:
        with tempfile.TemporaryDirectory(prefix='p64-', dir=os.environ.get('TMPDIR')) as scratch_name:
            scratch = Path(scratch_name)
            base = args.stack_url
            if args.stub:
                manifest = scratch / 'provider-manifest.json'
                summary['local_manifest_hash'] = candidate_manifest(manifest)
                cert, key = scratch / 'cert.pem', scratch / 'key.pem'
                subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                                '-keyout', str(key), '-out', str(cert), '-days', '1',
                                '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1'],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT),
                           MOSS_TEST_REAL_SQLITE='1')
                stub_log = (scratch / 'stub.log').open('wb')
                stub = subprocess.Popen([sys.executable, str(Path(__file__).with_name('loopback_vllm_stub.py')),
                                         '--port', str(args.stub_port), '--out', str(scratch / 'stub')],
                                        env=env, stdout=stub_log, stderr=subprocess.STDOUT,
                                        start_new_session=True)
                time.sleep(.5)
                if stub.poll() is not None:
                    raise RuntimeError('stub startup failed')
                proxy = TapProxy(port=args.proxy_port, upstream_port=args.stub_port,
                                 budget=args.budget, out=out / 'decoder-tap.jsonl')
                proxy.start()
                argv = [sys.executable, str(Path(__file__).with_name('local_stack.py')),
                        '--state', str(scratch / 'state'), '--cert', str(cert), '--key', str(key),
                        '--port', str(args.stack_port), '--manifest', str(manifest),
                        '--vllm-base-url', f'http://127.0.0.1:{args.proxy_port}/v1',
                        '--max-requests', str(args.budget), '--draft-lane-seconds', '1.0']
                stack_log = (scratch / 'stack.log').open('wb')
                app = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stack_log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
                base = f'https://127.0.0.1:{args.stack_port}'
                ready = False
                for _ in range(120):
                    if app.poll() is not None:
                        break
                    try:
                        client = Client(base, ssl._create_unverified_context())
                        ready = bool(client.call('POST', '/api/workspace/bootstrap'))
                        if ready:
                            break
                    except Exception:
                        time.sleep(1)
                if not ready:
                    raise RuntimeError('isolated stack startup failed: ' +
                                       (scratch / 'stack.log').read_text(errors='replace')[-1500:])
            summary.update(capture_arm(base, args.system, args.mic, seconds, out))
            summary['status'] = 'STUB_COMPLETE' if args.stub else 'EXTERNAL_COMPLETE'
    except Exception as exc:
        summary['error_type'] = type(exc).__name__
        summary['error'] = str(exc)[:500]
    finally:
        stop_process(app)
        if proxy is not None:
            summary['proxy'] = proxy.counters()
            proxy.close()
        stop_process(stub)
        if stack_log is not None:
            stack_log.close()
        if args.stub and 'stub_log' in locals():
            stub_log.close()
        if summary['status'].endswith('_COMPLETE'):
            summary['visual_metrics'] = compute_visual_metrics(out, seconds)
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps({k: v for k, v in summary.items() if k != 'visual_metrics'}, indent=2))
    return 0 if summary['status'].endswith('_COMPLETE') else 2


if __name__ == '__main__':
    raise SystemExit(main())
