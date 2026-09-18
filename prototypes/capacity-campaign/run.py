"""PROTOTYPE: capacity/lifecycle baseline, metadata only. See NOTES.md.

One command: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python prototypes/capacity-campaign/run.py --sessions 1 --seconds 120
This command makes real decoder calls. --prepare-only performs no network I/O.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.e2e.verify_demo_lanes import Client
from moss_transcribe_diarize.phase2_acceptance import QUALITY_BOUNDS, canonical_lifecycle_fairness
from moss_transcribe_diarize.concurrency_evidence import prestop_inference_projection
spec = importlib.util.spec_from_file_location('wp6_latency', ROOT / 'prototypes/streaming-diarization/draft-lane/latency_probe.py')
latency = importlib.util.module_from_spec(spec)
spec.loader.exec_module(latency)
HOST = 'gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us'
CORPUS = ROOT / 'evidence/live-policy-sweep-20260825/corpus'
NAMES = ['interview_bill_ackman_60s', 'interview_keyu_jin_60s', 'mono_javier_intro_50s',
         'discussion_jamie_dimon_180s', 'interview_adam_frank_180s', 'discussion_rtfl_90s']


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    index = (len(values)-1)*p
    lo = math.floor(index)
    return values[lo] + (values[math.ceil(index)]-values[lo])*(index-lo)


def inputs(n):
    result = []
    for index in range(n):
        name = NAMES[index] if index < 6 else NAMES[index-3]
        directory = CORPUS / name
        with wave.open(str(directory / 'audio.wav')) as source:
            assert (source.getframerate(), source.getnchannels(), source.getsampwidth()) == (16000, 1, 2)
            pcm = source.readframes(source.getnframes())
        reference = [json.loads(line) for line in (directory / 'reference.jsonl').read_text().splitlines()]
        start, end = 0, len(pcm)//2
        # Eight-session overload uses distinct reference-aligned halves of the two long interviews.
        if n == 8 and index in (3, 4, 6, 7):
            split = round(reference[len(reference)//2]['start']*16000)
            start, end = (0, split) if index < 6 else (split, end)
        rows = [dict(row, start=row['start']-start/16000, end=row['end']-start/16000)
                for row in reference if row['start'] >= start/16000 and row['end'] <= end/16000]
        result.append((f'{name}:{start}:{end}', pcm[start*2:end*2], rows))
    return result


def metrics():
    with urllib.request.urlopen('http://127.0.0.1:18106/metrics', timeout=5) as response:
        body = response.read().decode()
    values = {}
    for name in ('num_requests_running', 'num_requests_waiting', 'kv_cache_usage_perc', 'gpu_cache_usage_perc', 'request_success_total'):
        matches = re.findall(r'^vllm:'+name+r'(?:\{[^\n]*\})?\s+([0-9.eE+-]+)', body, re.M)
        values[name] = sum(map(float, matches)) if matches else None
    if values['num_requests_running'] is None or values['num_requests_waiting'] is None:
        raise RuntimeError('missing_request_metrics')
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions', type=int, choices=(1, 2, 4, 8), required=True)
    parser.add_argument('--seconds', type=int, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--port', type=int, default=17866)
    parser.add_argument('--four-session-result', type=Path)
    args = parser.parse_args()
    if args.seconds <= 0 or args.port in (7861, 7862):
        parser.error('positive duration and private app port required')
    clips = inputs(args.sessions)
    if args.prepare_only:
        print(json.dumps({'prepared': True, 'sessions': args.sessions, 'seconds': args.seconds,
                          'clips': [{'clip': name, 'samples': len(pcm)//2, 'reference_rows': len(rows)} for name, pcm, rows in clips]}))
        return
    if args.sessions == 8:
        if not args.four_session_result:
            parser.error('eight-session step requires --four-session-result from clean 4x600')
        prior = json.loads(args.four_session_result.read_text())
        if (prior.get('sessions'), prior.get('seconds'), prior.get('clean')) != (4, 600, True):
            parser.error('4x600 did not pass cleanly')
    stamp = time.strftime('%Y%m%d-%H%M%S')
    out = ROOT / 'evidence/mvpfix/wp6' / f'{stamp}-{args.sessions}x{args.seconds}'
    out.mkdir()
    # Relative path keeps the Unix control socket below the macOS path limit.
    scratch = Path('.wp6-tmp') / stamp
    scratch.mkdir(parents=True)
    os.environ.update(TMPDIR=str(ROOT / scratch), PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT))
    processes = []
    stop_monitor = threading.Event()
    paused = threading.Event()
    contaminated = threading.Event()
    lock = threading.Lock()
    resources, failures, clients, ids, outputs = [], [], [], [], []
    result = dict(sessions=args.sessions, seconds=args.seconds, clean=False,
                  quality_bounds=QUALITY_BOUNDS, resources=resources, failures=failures, session_results=outputs)
    state = scratch / 'state'
    state.mkdir()

    def emit(row):
        with lock:
            with (out / 'actions.jsonl').open('a') as stream:
                stream.write(json.dumps(row) + '\n')
        print(json.dumps(row), flush=True)

    def own_requests():
        path = state / 'decoder.jsonl'
        rows = []
        if path.exists():
            for line in path.read_text().splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # Writer may currently be appending the last line.
        return rows

    def sample(pid):
        before = own_requests()
        metric = metrics()
        after = own_requests()
        active = max([r['active'] for r in before[-1:]+after[len(before):]] or [0])
        foreign = metric['num_requests_running'] + metric['num_requests_waiting'] > active
        if foreign:
            paused.set()
            contaminated.set()
            (state / 'PAUSE').touch()
        elif paused.is_set() and metric['num_requests_running'] + metric['num_requests_waiting'] == 0:
            (state / 'PAUSE').unlink(missing_ok=True)
            paused.clear()
        gpu = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', HOST,
                              'nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits'],
                             capture_output=True, text=True, timeout=10)
        rss = subprocess.check_output(['ps', '-o', 'rss=', '-p', str(pid)], text=True).strip()
        row = dict(kind='resource', time=time.monotonic(), app_rss_bytes=int(rss)*1024,
                   own_active=active, foreign_load_detected=foreign, metrics=metric,
                   gpu_memory_mib=gpu.stdout.strip() if gpu.returncode == 0 else None)
        resources.append(row)
        emit(row)

    def monitor(pid):
        while not stop_monitor.wait(30):
            try:
                sample(pid)
            except Exception as exc:
                failures.append('resource:'+type(exc).__name__)
                emit(dict(kind='resource_failure', error=type(exc).__name__))

    try:
        tunnel = subprocess.Popen(['ssh', '-N', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
                                   '-L', '127.0.0.1:18106:127.0.0.1:8000', HOST], stdout=subprocess.DEVNULL,
                                  stderr=(scratch / 'ssh.log').open('w'))
        processes.append(tunnel)
        for _ in range(30):
            if tunnel.poll() is not None:
                raise RuntimeError('private_tunnel_failed')
            try:
                initial = metrics()
                break
            except (OSError, RuntimeError):
                time.sleep(1)
        else:
            raise RuntimeError('metrics_unavailable')
        emit(dict(kind='preflight', metrics=initial))
        if initial['num_requests_running'] + initial['num_requests_waiting']:
            raise RuntimeError('foreign_load_before_campaign_pause_without_dispatch')
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(scratch/'key.pem'),
                        '-out', str(scratch/'cert.pem'), '-days', '2', '-subj', '/CN=127.0.0.1',
                        '-addext', 'subjectAltName=IP:127.0.0.1'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        app = subprocess.Popen([sys.executable, 'prototypes/capacity-campaign/stack.py', '--state', str(state),
                                '--cert', str(scratch/'cert.pem'), '--key', str(scratch/'key.pem'), '--port', str(args.port)],
                               stdout=(scratch/'app.log').open('w'), stderr=subprocess.STDOUT)
        processes.append(app)
        context = ssl.create_default_context(cafile=str(scratch/'cert.pem'))
        base = f'https://127.0.0.1:{args.port}'
        for _ in range(60):
            if app.poll() is not None:
                raise RuntimeError('local_stack_start_failed')
            try:
                with urllib.request.urlopen(base+'/api/workspace', context=context, timeout=2):
                    pass
                break
            except urllib.error.HTTPError:
                break  # An HTTP reply proves TLS/HTTP readiness; bootstrap below checks API.
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError('local_stack_timeout')
        sample(app.pid)
        watcher = threading.Thread(target=monitor, args=(app.pid,), daemon=True)
        watcher.start()
        for _ in clips:
            client = Client(base, context)
            client.call('POST', '/api/workspace/bootstrap')
            clients.append(client)
            descriptor = client.call('GET', '/api/live/descriptor')['descriptor']
            ids.append(client.call('POST', '/api/live/sessions', {'source_revision': descriptor['source_revision']})['id'])
        # Smoke still needs a distinct foreign owner.
        outsider = Client(base, context)
        outsider.call('POST', '/api/workspace/bootstrap')
        barrier = threading.Barrier(args.sessions)

        def worker(index):
            c, ident = clients[index], ids[index]
            name, pcm, reference = clips[index]
            row = dict(ordinal=index+1, clip=name, acknowledged_frames=0, retries=0,
                       foreign_probes=0, wrong_owner_failures=0, updates=[], coverage_lags=[], events=[])
            outputs.append(row)
            terminal = False
            event_seq = 0
            cadence = descriptor['frame_samples']/descriptor['sample_rate']
            assert cadence == .5, 'charter requires 0.5-second frames'
            fs, sr = descriptor['frame_samples'], descriptor['sample_rate']
            epoch = time.time_ns()
            health_sequence = 0
            seen = None
            coverage = set()
            started = None

            def heartbeat():
                nonlocal health_sequence
                h = dict(state='capturing', device_epoch=epoch, dropped_frames=0, discontinuities=0, failure_code=None)
                c.call('POST', f'/api/live/sessions/{ident}/heartbeat', dict(schema='moss-live-helper-health.v1',
                       instance_id='wp6-capacity', sequence=health_sequence, sent_monotonic_ns=time.monotonic_ns(),
                       helper_version='prototype', state='capturing', lanes=dict(system=h, microphone=h)))
                health_sequence += 1

            def observe():
                nonlocal seen, event_seq
                snap = c.call('GET', f'/api/live/sessions/{ident}/snapshot')['snapshot']
                now = time.monotonic()-started
                visible = latency.visible_segments(snap)
                text = tuple((s.get('start_sample'), s.get('end_sample'), s.get('text')) for s in visible)
                count = sum(len(latency.words(s.get('text',''))) for s in visible)
                if count and row.get('first_text_seconds') is None:
                    row['first_text_seconds'] = now
                if text != seen:
                    row['updates'].append(dict(at_seconds=now, words=count,
                          newest_audio_age_seconds=now-max([s.get('end_sample',0)/sr for s in visible] or [0])))
                    seen = text
                for bucket in range(min(int(now/cadence), int(args.seconds/cadence))):
                    end_sample = round((bucket+1)*cadence*sr)
                    if bucket not in coverage and any(s.get('start_sample',0) < end_sample and s.get('end_sample',0) >= end_sample for s in visible):
                        coverage.add(bucket)
                        row['coverage_lags'].append(max(0,now-(bucket+1)*cadence))
                events = c.call('GET', f'/api/live/sessions/{ident}/events?since_seq={event_seq}')['events']
                for event in events:
                    if event['seq'] != event_seq:
                        raise RuntimeError('event_sequence_gap')
                    event_seq += 1
                    p = event.get('payload',{})
                    row['events'].append(dict(kind=event['kind'], seq=event['seq'], session_id=ident,
                        payload={k:p[k] for k in ('runtime_monotonic_ns','item_id','submitted','admitted',
                        'committed_samples','canonical_decode_elapsed_sec','frozen_span_duration_sec',
                        'rolling_decode_elapsed_sec','windows_failed','stale_completions','outcome','reason','decode_failure') if k in p}))
                return snap

            try:
                barrier.wait(timeout=30)
                started = time.monotonic()
                for seq in range(int(args.seconds/cadence)):
                    heartbeat()
                    while paused.is_set():
                        heartbeat()
                        time.sleep(cadence)
                    fb = fs*2
                    offset = seq*fb % len(pcm)
                    chunk = (pcm+pcm)[offset:offset+fb]
                    for lane, data in (('system',chunk),('microphone',bytes(fb))):
                        frame = dict(lane=lane, sequence=seq, capture_timestamp_ns=epoch+round(seq*cadence*1e9),
                                     device_epoch=epoch, pcm_base64=base64.b64encode(data).decode(), sample_count=fs,
                                     sample_rate=sr, silent=data==bytes(fb), discontinuity=False)
                        retry_started = time.monotonic()
                        while True:
                            try:
                                c.call('POST', f'/api/live/sessions/{ident}/frames', frame)
                                row['acknowledged_frames'] += 1
                                break
                            except urllib.error.HTTPError as exc:
                                body = json.loads(exc.read())
                                if exc.code != 429:
                                    raise RuntimeError(f'frame_http_{exc.code}') from None
                                row['retries'] += 1
                                emit(dict(kind='backpressure', ordinal=index+1, sequence=seq, lane=lane, code=body.get('code') or body.get('failure',{}).get('code'), retryable=body.get('retryable')))
                                if time.monotonic()-retry_started > 30:
                                    raise RuntimeError('backpressure_no_progress_30s')
                                heartbeat()
                                time.sleep(cadence)
                    snap = observe()
                    probe = clients[(index+1)%len(clients)] if len(clients)>1 else outsider
                    for route in (f'/api/live/sessions/{ident}/snapshot', f'/api/meetings/{ident}'):
                        try:
                            probe.call('GET', route)
                            status = 200
                        except urllib.error.HTTPError as exc:
                            status = exc.code
                        row['foreign_probes'] += 1
                        row['wrong_owner_failures'] += status != 404
                    emit(dict(kind='frame', ordinal=index+1, sequence=seq, acknowledged_frames=row['acknowledged_frames'],
                              status=snap['session']['status'], words=row['updates'][-1]['words'] if row['updates'] else 0,
                              pending=snap.get('pending_work_items'), foreign_probes=row['foreign_probes']))
                    time.sleep(max(0, started+(seq+1)*cadence-time.monotonic()))
                stopped = time.monotonic()
                c.call('POST', f'/api/live/sessions/{ident}/stop', {'deadline':30})
                while True:
                    snap = observe()
                    ses = snap['session']
                    if ses['finalization_status'] in ('final','failed'):
                        break
                    if time.monotonic()-stopped > 90:
                        raise RuntimeError('finalization_timeout_90s')
                    time.sleep(.25)
                terminal = True
                words = latency.words(' '.join(s['text'] for s in latency.segments_of(snap)))
                ref = []
                clip_seconds = len(pcm)/2/sr
                partial_reference_rows = 0
                for loop in range(math.ceil(args.seconds/clip_seconds)):
                    for r in reference:
                        if loop*clip_seconds+r['end'] <= args.seconds:
                            ref.extend(latency.words(r['text']))
                        elif loop*clip_seconds+r['start'] < args.seconds:
                            partial_reference_rows += 1
                ref_set = set(ref)
                row.update(status=ses['status'], finalization_status=ses['finalization_status'],
                           stop_to_final_seconds=time.monotonic()-stopped,
                           accepted_samples=ses['accepted_samples'], accounted_samples=ses['accounted_samples'],
                           word_count=len(words), reference_word_count=len(ref), partial_reference_rows=partial_reference_rows,
                           words_per_minute=len(words)/(args.seconds/60),
                           unique_vocabulary_retention=len(set(words)&ref_set)/len(ref_set) if ref_set else None,
                           wer=latency.edit_wer(ref,words) if not partial_reference_rows else None,
                           speakers=len({s.get('canonical_speaker') for s in latency.segments_of(snap)}),
                           p95_coverage_lag=percentile(row['coverage_lags'], .95),
                           covered_buckets=len(coverage), expected_buckets=int(args.seconds/cadence))
                reopened = c.call('GET', f'/api/meetings/{ident}')
                row['reopened_status'] = reopened.get('status')
                canonical_lags = [max(0, (e['payload']['runtime_monotonic_ns']/1e9-started)-e['payload']['committed_samples']/sr)
                    for e in row['events'] if e['kind']=='canonical_processed' and e['payload'].get('submitted') is True
                    and 'committed_samples' in e['payload'] and 'runtime_monotonic_ns' in e['payload']]
                row['canonical_lags'] = canonical_lags
                row['p95_canonical_lag'] = percentile(canonical_lags,.95)
                row['final_wer_bound_comparison'] = None if row['wer'] is None else row['wer'] <= QUALITY_BOUNDS['final_wer'][1]
                row['first_text_api_comparison_4s'] = row.get('first_text_seconds',float('inf')) <= 4
                row['clean'] = (ses['status']=='closed' and ses['finalization_status']=='final'
                    and ses['accepted_samples']==ses['accounted_samples']==args.seconds*sr
                    and row['wrong_owner_failures']==0 and row['p95_canonical_lag'] is not None
                    and row['p95_canonical_lag']<=10 and row['reopened_status']=='completed')
            except Exception as exc:
                row['error'] = type(exc).__name__
                row['failure_code'] = str(exc) if isinstance(exc,RuntimeError) else None
                row['clean'] = False
                failures.append(f'session_{index+1}:{type(exc).__name__}')
            finally:
                if not terminal:
                    try:
                        c.call('POST', f'/api/live/sessions/{ident}/abort', {'reason':'WP6 campaign cleanup'})
                    except Exception as exc:
                        failures.append('abort:'+type(exc).__name__)
                emit(dict(kind='session_result', **row))

        with concurrent.futures.ThreadPoolExecutor(max_workers=args.sessions) as pool:
            list(pool.map(worker, range(args.sessions)))
        stop_monitor.set()
        watcher.join(timeout=15)
        sample(app.pid)
        all_events = [e for row in outputs for e in row['events']]
        lifecycle = sorted([e for e in all_events if e['kind'] in ('canonical_queued','canonical_started','canonical_processed')],
                           key=lambda e:e['payload'].get('runtime_monotonic_ns',0))
        result['fairness'] = canonical_lifecycle_fairness(lifecycle,set(ids),maximum_skew=1)
        rss = [r['app_rss_bytes'] for r in resources]
        result['app_rss_growth_bytes'] = max(rss)-rss[0]
        try:
            result['prestop_inference'] = prestop_inference_projection(all_events, accepted_audio_seconds=args.seconds*args.sessions)
        except ValueError as exc:
            failures.append('inference_evidence:'+str(exc))
        pending = {}
        depth = 0
        for e in sorted(all_events,key=lambda e:e['payload'].get('runtime_monotonic_ns',0)):
            p = e['payload']
            key = (e['session_id'],p.get('item_id'))
            if e['kind']=='rolling_decode_queued' and p.get('admitted') is True:
                pending[key] = True
                depth = max(depth,sum(k[0]==key[0] for k in pending))
            elif e['kind']=='rolling_decode_completed':
                pending.pop(key,None)
        result['maximum_refinement_queue_depth'] = depth
        cache = [r['metrics'].get('kv_cache_usage_perc') if r['metrics'].get('kv_cache_usage_perc') is not None else r['metrics'].get('gpu_cache_usage_perc') for r in resources]
        result['maximum_gpu_cache_use'] = max(cache) if all(v is not None for v in cache) else None
        result['foreign_load_detected'] = contaminated.is_set()
        result['decoder_calls'] = sum(r['kind']=='start' for r in own_requests())
        result['maximum_own_inflight'] = max([r['active'] for r in own_requests()] or [0])
        result['clean'] = (all(r.get('clean') for r in outputs) and len(outputs)==args.sessions and not failures
                           and not contaminated.is_set() and result['fairness'].get('passes') is True
                           and result['app_rss_growth_bytes']<=4*1024**3
                           and result.get('prestop_inference',{}).get('rtf',float('inf'))<1
                           and depth<=1 and result['maximum_gpu_cache_use'] is not None
                           and result['maximum_gpu_cache_use']<=.95)
        result['overload_backpressure_observed'] = any(r['retries'] for r in outputs)
        if args.sessions == 8 and not result['overload_backpressure_observed']:
            result['clean'] = False
        result['qualification'] = 'local baseline only; remote process-tree RSS, host journals and six-case quality corpus unmeasured'
    except Exception as exc:
        failures.append(type(exc).__name__+(':'+str(exc) if isinstance(exc,RuntimeError) else ''))
    finally:
        stop_monitor.set()
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        decoder = own_requests()
        (out/'decoder.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in decoder))
        result['decoder_calls'] = sum(r['kind']=='start' for r in decoder)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        emit(dict(kind='finished', clean=result['clean'], decoder_calls=result['decoder_calls'], failures=failures))
    raise SystemExit(0 if result['clean'] else 1)


if __name__ == '__main__':
    os.chdir(ROOT)
    main()
