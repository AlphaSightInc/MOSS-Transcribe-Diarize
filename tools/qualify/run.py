"""One-command local qualification ledger. Invoke existing benches; never fork their logic."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.qualify.decoder import Decoder
from tests.e2e.verify_workspace import retained_metadata, required_rows_verdict, verdict_exit_code
from tests.e2e.verify_demo_lanes import Client

PY = sys.executable
HOST = 'gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us'
LADDER = Path('/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/moss-mvp-review/evidence/independent-review/probes/ir_lane_ladder.py')
CASES = ['system@1', 'mic@1', 'overlap@1', 'overlap@0.316', 'overlap@0.1', 'overlapsysquiet@0.316']
BROWSER_CASES = tuple(range(1, 17))
MEASURED_REQUEST_RATE = .51
REQUEST_RATE_SOURCE = 'evidence/mvpfix/wp30/20260918-055122-1r-4x600/requests.jsonl'
REQUEST_HEADROOM = 1.25
LIVE_BENCH_SESSION_SECONDS = {
    # verify_workspace: primary capture, two controlled lane cases, recognition,
    # two bounded outage cases, then three eight-second repeat captures.
    'workspace': (18, 54, 29, 30, 70, 87, 8, 8, 8),
    'demo_lanes': (54, 29),
    # Six sessions: three four-frame captures, one empty capture, then two
    # one-frame concurrent captures. The production wire frame is 0.5 seconds.
    'lifecycle': (2, 2, 2, 0, .5, .5),
    'reshare': (20,),
    'identity_stress': (60, 60, 60),
    'level_ladder': (24, 24, 24, 24, 24, 24),
    # Cases 1-6, 11, 15 and 16 create these bounded live sessions. The other
    # browser cases are still represented by BROWSER_CASES below.
    'browser_stress_all': (8, 1, 1, 68, 19, 36, 16, 8, 50, 73, 45, 58),
}
WORKSPACE_FILE_SECONDS = (50, 50)
DEFAULT_FILE_SECONDS = (360, 180, 180, 180)
LONG_FILE_SECONDS = (1800,)


def write(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def counts(statuses):
    c = Counter(statuses)
    return dict(expected=len(statuses), executed=sum(v for k, v in c.items() if k not in ('UNRUNNABLE', 'SKIP')),
                passed=c['PASS'], failed=c['FAIL'], skipped=c['SKIP'], unrunnable=c['UNRUNNABLE'])


def request_plan(long):
    """Return the selected decoder population before any bundle work starts."""
    from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner, plan_windows

    live_benches = {
        name: dict(session_seconds=list(seconds), sessions=len(seconds), seconds=sum(seconds))
        for name, seconds in LIVE_BENCH_SESSION_SECONDS.items()
    }
    if long:
        live_benches['capacity_2x1800'] = dict(
            session_seconds=[1800, 1800], sessions=2, seconds=3600,
        )
    else:
        live_benches['capacity_2x300'] = dict(
            session_seconds=[300, 300], sessions=2, seconds=600,
        )
    live_sessions = sum(bench['sessions'] for bench in live_benches.values())
    live_session_seconds = sum(bench['seconds'] for bench in live_benches.values())
    file_seconds = [*WORKSPACE_FILE_SECONDS, *DEFAULT_FILE_SECONDS,
                    *(LONG_FILE_SECONDS if long else ())]
    file_windows = sum(len(plan_windows(
        seconds,
        window_seconds=WindowedRunner.window_seconds,
        stride_seconds=WindowedRunner.stride_seconds,
    )) for seconds in file_seconds)
    population = dict(
        live_benches=live_benches,
        live_sessions=live_sessions,
        live_session_seconds=live_session_seconds,
        file_seconds=file_seconds,
        file_windows=file_windows,
        window_seconds=WindowedRunner.window_seconds,
        stride_seconds=WindowedRunner.stride_seconds,
        browser_cases=list(BROWSER_CASES),
    )
    live_session_requests = live_session_seconds * MEASURED_REQUEST_RATE
    unadjusted = live_session_requests + file_windows + len(BROWSER_CASES)
    return dict(
        measured_rate=MEASURED_REQUEST_RATE,
        source_receipt=REQUEST_RATE_SOURCE,
        headroom=REQUEST_HEADROOM,
        planned_requests=math.ceil(unadjusted * REQUEST_HEADROOM),
        request_derivation=dict(
            live_session_requests=round(live_session_requests, 3),
            file_window_requests=file_windows,
            browser_case_requests=len(BROWSER_CASES),
            unadjusted_requests=round(unadjusted, 3),
            calculation='ceil(unadjusted_requests * headroom)',
        ),
        population=population,
    )


def ready_descriptor(base):
    client = Client(base, ssl._create_unverified_context())
    client.call('POST', '/api/workspace/bootstrap')
    return client.call('GET', '/api/live/descriptor')['descriptor']


def compare(first, second):
    a = {g['name']: g['status'] for g in first['gates']}
    b = {g['name']: g['status'] for g in second['gates']}
    return [dict(name=k, before=a.get(k), after=b.get(k)) for k in sorted(a.keys() | b.keys()) if a.get(k) != b.get(k)]


def bundle_verdict(gates):
    if any(g['status'] == 'FAIL' for g in gates):
        return 'FAIL'
    if any(g['status'] != 'PASS' and g.get('required', True) for g in gates):
        return 'INCOMPLETE'
    return 'PASS' if gates else 'INCOMPLETE'


class Bundle:
    def __init__(self, args, plan):
        self.args = args
        self.decoder_upstream_port = args.decoder_upstream_port or 18125
        self.started = time.monotonic()
        self.sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], text=True).splitlines()
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        self.out = (args.out or ROOT/'evidence/mvpfix/wp25').resolve()/f'{self.sha[:12]}-{stamp}'
        self.out.mkdir(parents=True)
        self.work = ROOT/'.wp25runtime'/stamp
        self.work.mkdir(parents=True)
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT))
        for key, subdir in [('TMPDIR','tmp'), ('XDG_CACHE_HOME','cache'), ('NUMBA_CACHE_DIR','numba'), ('npm_config_cache','npm')]:
            path = self.work/subdir
            path.mkdir()
            self.env[key] = str(path)
        # Prevent implicit relay dispatch without an explicit environment key.
        self.has_summary_key = any(os.environ.get(k) for k in ('GEMINI_API_KEY', 'GOOGLE_API_KEY', 'OPENAI_API_KEY', 'MOSS_LLM_UPSTREAM_API_KEY'))
        if not self.has_summary_key:
            self.env.pop('MOSS_LLM_UPSTREAMS', None)
        self.processes = []
        self.handles = []
        self.proxy = None
        self.monitor_stop = threading.Event()
        self.monitor = None
        self.data = dict(schema='moss-local-qualification.v2', scope='local measurement; not deployment or attended acceptance',
                         identity=dict(git_sha=self.sha, tree_clean=not dirty, dirty_files=dirty,
                                       python=sys.version.split()[0], node=subprocess.check_output(['node','--version'], text=True).strip(),
                                       decoder_tunnel_url=f'http://127.0.0.1:{self.decoder_upstream_port}', decoder_base_url='http://127.0.0.1:19125/v1'),
                         gates=[], request_budget=args.budget, long=args.long, integrated_candidate=self.sha,
                         measured_rate=plan['measured_rate'], source_receipt=plan['source_receipt'],
                         headroom=plan['headroom'], planned_requests=plan['planned_requests'],
                         request_derivation=plan['request_derivation'],
                         request_population=plan['population'])
        self.current = None
        self.gate('tree_clean', 'PASS' if not dirty else 'FAIL', measurements={'dirty_files':dirty})

    def flush(self):
        self.data['duration_seconds'] = round(time.monotonic()-self.started, 3)
        write(self.out/'summary.json', self.data)
        lines = ['# Local qualification', '', f"Candidate `{self.sha}`; clean at start: {self.data['identity']['tree_clean']}.",
                 f"Verdict: {self.data.get('verdict', 'INCOMPLETE')}.",
                 'Local measurement only; no deployment or attended-capture acceptance.', '',
                 '| Gate | Status | Counts | Seconds |', '|---|---|---|---|']
        reasons = []
        for g in self.data['gates']:
            lines.append(f"| {g['name']} | {g['status']} | {json.dumps(g['denominators'], separators=(',', ':'))} | {g['duration_seconds']} |")
            if g.get('reason'):
                reasons.append(f"{g['name']}: {g['reason']}")
        lines += ['', *reasons, '', f"Runtime: {self.data['duration_seconds']} s.", f"Decoder: {json.dumps(self.data.get('decoder', {}))}",
                  'Raw content-bearing stdout stays in ignored runtime scratch. Retained logs contain only status/count projections.']
        (self.out/'summary.md').write_text('\n'.join(lines)+'\n')

    def gate(self, name, status, denominators=None, duration=0, code=None, reason=None, measurements=None, required=True):
        row = dict(name=name, status=status, required=required, exit_code=code, denominators=denominators or counts([status]),
                   duration_seconds=round(duration, 3), artifacts=[name+'.log'])
        if self.proxy:
            row['decoder_requests_at_record'] = self.proxy.sent
            row['decoder_budget_exhausted_at_record'] = self.proxy.sent >= self.args.budget
        if reason:
            row['reason'] = reason
        if measurements is not None:
            row['measurements'] = measurements
        write(self.out/(name+'.log'), row)
        self.data['gates'].append(row)
        self.flush()
        print(f"{name}: {status} {json.dumps(row['denominators'])}", flush=True)
        return row

    def command(self, name, argv, timeout=1800, env=None):
        start = time.monotonic()
        target = self.work/(name+'.raw')
        with target.open('wb') as log:
            proc = subprocess.Popen(argv, cwd=ROOT, env=env or self.env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            self.processes.append(proc)
            self.current = proc
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.stop(proc)
                code = 124
            finally:
                self.stop(proc)
                self.processes.remove(proc)
                self.current = None
        return code, time.monotonic()-start, target

    def start(self, name, argv):
        log = (self.work/(name+'.raw')).open('wb')
        self.handles.append(log)
        proc = subprocess.Popen(argv, cwd=ROOT, env=self.env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self.processes.append(proc)
        return proc

    @staticmethod
    def stop(proc):
        # Signal the owned group even after the leader exits: browsers/helpers may remain.
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()

    def static(self):
        import moss_transcribe_diarize as package
        owned = Path(package.__file__).resolve().is_relative_to(ROOT)
        self.gate('python_import', 'PASS' if owned else 'FAIL', measurements={'path': package.__file__})
        if not owned:
            raise RuntimeError('wrong_checkout_import')
        assets = ROOT/'moss_transcribe_diarize/app/frontend_assets'
        backup = self.work/'assets'
        shutil.copytree(assets, backup)
        try:
            code, elapsed, _ = self.command('asset_build', ['npm','--prefix','frontend','run','build','--','--configLoader','native'])
            before = {str(p.relative_to(backup)): p.read_bytes() for p in backup.rglob('*') if p.is_file()}
            after = {str(p.relative_to(assets)): p.read_bytes() for p in assets.rglob('*') if p.is_file()}
            changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
            self.gate('asset_parity', 'PASS' if code == 0 and not changed else 'FAIL',
                      {'expected':len(before), 'compared':len(before.keys() | after.keys()), 'different':len(changed)},
                      elapsed, code, measurements={'different_files':changed})
        finally:
            shutil.rmtree(assets)
            shutil.copytree(backup, assets)
        pytest_counts = self.work/'pytest-counts.json'
        env = dict(self.env, MOSS_QUALIFY_COUNTS=str(pytest_counts))
        code, elapsed, _ = self.command('pytest', [PY,'-m','pytest','-q','-p','no:cacheprovider',
            '-p','tools.qualify.pytest_counts','-p','evidence.mvpfix.wp16.local_scratch',
            '--basetemp='+str(self.work/'pytest'), 'tests'], env=env)
        result = json.loads(pytest_counts.read_text()) if pytest_counts.exists() else {}
        self.gate('pytest', 'PASS' if code == 0 and result.get('collected',0)>0 else 'FAIL', result, elapsed, code)
        xml = self.work/'frontend.xml'
        code, elapsed, _ = self.command('frontend', ['npm','--prefix','frontend','test','--','--run',
            '--configLoader','native','--reporter=junit','--outputFile='+str(xml)])
        result = {}
        if xml.exists():
            tree = ET.parse(xml)
            cases = tree.findall('.//testcase')
            failed = [c for c in cases if c.find('failure') is not None or c.find('error') is not None]
            skipped = sum(c.find('skipped') is not None for c in cases)
            result = dict(collected=len(cases), executed=len(cases)-skipped, passed=len(cases)-len(failed)-skipped,
                          failed=len(failed), skipped=skipped,
                          failure_names=[c.get('classname','')+'::'+c.get('name','') for c in failed])
        self.gate('frontend', 'PASS' if code == 0 and result.get('collected',0)>0 else 'FAIL', result, elapsed, code)
        helper_counts = self.work/'helper-counts.json'
        code, elapsed, _ = self.command('bundle_helpers', [PY,'-m','pytest','-q','-p','no:cacheprovider',
            '-p','tools.qualify.pytest_counts','--basetemp='+str(self.work/'helpers'),'tools/qualify/test_bundle.py','tools/qualify/test_speaker_quality.py'],
            env=dict(self.env, MOSS_QUALIFY_COUNTS=str(helper_counts)))
        result = json.loads(helper_counts.read_text()) if helper_counts.exists() else {}
        self.gate('bundle_helpers', 'PASS' if code==0 and result.get('collected',0)>0 else 'FAIL', result, elapsed, code)
        for name, cmd in [('typecheck',['npm','--prefix','frontend','run','typecheck']),
                          ('verify_layout',['bash','scripts/check_verify_layout.sh'])]:
            code, elapsed, _ = self.command(name, cmd)
            self.gate(name, 'PASS' if code == 0 else 'FAIL', duration=elapsed, code=code)

    def metrics(self):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.decoder_upstream_port}/metrics', timeout=5) as r:
            source = r.read().decode()
        result = {}
        for key in ('num_requests_running','num_requests_waiting','request_success_total'):
            values = [float(line.rsplit(' ',1)[1]) for line in source.splitlines()
                      if re.match(r'vllm:'+key+r'(?:\{|\s)',line)]
            result[key] = sum(values) if values else None
        return result

    def sample(self):
        while not self.monitor_stop.is_set():
            try:
                row = dict(time=time.monotonic(), shared=self.metrics(), own_active=self.proxy.active, own_sent=self.proxy.sent)
            except Exception as exc:
                row = dict(time=time.monotonic(), error_type=type(exc).__name__)
            with (self.out/'contention.jsonl').open('a') as f:
                f.write(json.dumps(row)+'\n')
            self.monitor_stop.wait(2)

    def stack(self):
        start = time.monotonic()
        for port in (18125,19125,17825,17826,17827,17828,17829):
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1',port)) == 0:
                    self.gate('stack', 'UNRUNNABLE', reason=f'Own required port {port} already occupied; no reuse or termination')
                    return False
        tunnel = None
        if self.args.decoder_upstream_port is None:
            tunnel = self.start('tunnel', ['ssh','-N','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes',
                '-o','ControlMaster=no','-o','ControlPath=none','-o','UpdateHostKeys=no','-o','StrictHostKeyChecking=yes',
                '-L','127.0.0.1:18125:127.0.0.1:8000',HOST])
        initial = None
        for _ in range(30):
            if tunnel is not None and tunnel.poll() is not None:
                break
            try:
                initial = self.metrics()
                break
            except Exception:
                time.sleep(1)
        if initial is None or any(initial.get(k) is None for k in ('num_requests_running','num_requests_waiting')):
            self.gate('stack','UNRUNNABLE',duration=time.monotonic()-start, reason='Owned tunnel or required vLLM metrics unavailable')
            return False
        self.data['initial_contention'] = initial
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{self.decoder_upstream_port}/version', timeout=5) as r:
                value = json.load(r).get('version')
                self.data['identity']['vllm_version'] = value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9.+_-]{1,100}',value) else None
        except Exception:
            self.data['identity']['vllm_version'] = None
        # Authorized bounded run proceeds under sibling load; retain contention.
        code, _, _ = self.command('manifest', [PY,'prototypes/capacity-campaign/copy_manifest.py'])
        if code:
            self.gate('stack','UNRUNNABLE',duration=time.monotonic()-start,code=code,reason='Existing isolated manifest preparer failed; private log retained')
            return False
        manifest = self.work/'manifest-30m.json'
        shutil.copyfile(ROOT/'.wp6-tmp/manifest-30m.json',manifest)
        manifest.chmod(0o600)
        self.data['identity']['manifest'] = dict(name=manifest.name, sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
            max_tape_bytes=json.loads(manifest.read_text())['bounds_config']['max_tape_bytes'])
        cert, key = self.work/'cert.pem', self.work/'key.pem'
        code, _, _ = self.command('certificate', ['openssl','req','-x509','-newkey','rsa:2048','-nodes',
            '-keyout',str(key),'-out',str(cert),'-days','2','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1'])
        if code:
            self.gate('stack','UNRUNNABLE',duration=time.monotonic()-start,code=code,reason='Local certificate generation failed')
            return False
        import certifi
        ca=self.work/'ca.pem'
        ca.write_bytes(Path(certifi.where()).read_bytes()+b'\n'+cert.read_bytes())
        self.env['SSL_CERT_FILE']=str(ca)
        self.manifest,self.cert,self.key=manifest,cert,key
        self.proxy = Decoder(19125,self.decoder_upstream_port,self.args.budget,self.out/'decoder-requests.jsonl')
        self.proxy.start()
        self.monitor = threading.Thread(target=self.sample, daemon=True)
        self.monitor.start()
        state = (self.work/'state').relative_to(ROOT)
        app = self.start('stack', [PY,'prototypes/streaming-diarization/draft-lane/run_local_stack.py',
            '--state',str(state),'--cert',str(cert),'--key',str(key),'--port','17825',
            '--manifest',str(manifest),'--vllm-base-url','http://127.0.0.1:19125/v1', '--max-requests',str(self.args.budget)])
        ready = False
        for _ in range(120):
            if app.poll() is not None:
                break
            try:
                descriptor = ready_descriptor('https://127.0.0.1:17825')
                ready = bool(descriptor.get('source_revision'))
                if ready:
                    break
            except Exception:
                time.sleep(1)
        self.gate('stack','PASS' if ready else 'FAIL',duration=time.monotonic()-start,
                  reason='SQLite runtime pin bypassed by existing local recipe; not deployment parity',
                  measurements={'readiness':ready})
        return ready

    def extended(self, ready):
        specs=[('browser_stress_all',16),('file_6min',1),('file_3min_formats',3),('file_failures',5),('file_30min',1)]
        if not ready:
            for name,n in specs:
                status='SKIP' if name == 'file_30min' and not self.args.long else 'UNRUNNABLE'
                self.gate(name,status,counts([status]*n),reason='Requires --long' if status=='SKIP' else 'Isolated stack unavailable')
            self.capacity(ready=False)
            return
        output=self.work/'browser'
        state=(self.work/'browser-state').relative_to(ROOT)
        code,elapsed,_=self.command('browser_stress_all',[PY,'prototypes/browser-stress/run.py','all','--headed',
            '--base','https://127.0.0.1:17826','--stack-port','17826','--decoder-url','http://127.0.0.1:19125/v1',
            '--out',str(output),'--state',str(state),'--cert',str(self.cert),'--key',str(self.key),
            '--manifest',str(self.manifest)],timeout=3600)
        rows=json.loads((output/'campaign-results.json').read_text()) if (output/'campaign-results.json').exists() else {}
        statuses=[('UNRUNNABLE' if rows.get(str(i),{}).get('status')=='BLOCKED' else rows.get(str(i),{}).get('status','UNRUNNABLE')) for i in BROWSER_CASES]
        import ast
        module=ast.parse((ROOT/'prototypes/browser-stress/run.py').read_text())
        predicates=next(ast.literal_eval(node.value) for node in module.body if isinstance(node,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='PREDICATES' for t in node.targets))
        measurements={str(i):dict(status=statuses[i-1],predicate=predicates[i],
            observation=retained_metadata(rows.get(str(i),{}))) for i in BROWSER_CASES}
        self.gate('browser_stress_all',aggregate(statuses,code),counts(statuses),elapsed,code,
            reason='Native hidden-tab cases are UNRUNNABLE if Chromium never becomes hidden; missing rows mean bench could not execute',measurements=measurements)
        self.files()
        self.capacity(ready=True)

    def capacity(self, ready):
        if not ready:
            if self.args.long:
                self.gate('capacity_2x1800','UNRUNNABLE',counts(['UNRUNNABLE']*2),reason='Isolated stack unavailable')
            else:
                self.gate('capacity_2x300','UNRUNNABLE',counts(['UNRUNNABLE']*2),reason='Isolated stack unavailable')
                self.gate('capacity_2x1800','REQUIRED-NOT-RUN',counts(['SKIP']*2),reason='Requires --long and a sufficient explicit --budget')
            return
        name = 'capacity_2x1800' if self.args.long else 'capacity_2x300'
        seconds = 1800 if self.args.long else 300
        output=self.work/'capacity'
        scratch=(self.work/'capacity-runtime').relative_to(ROOT)
        code,elapsed,_=self.command(name,[PY,'prototypes/capacity-campaign/run.py',
            '--sessions','2','--seconds',str(seconds),'--clips','mono_javier_intro_50s','discussion_jamie_dimon_180s','--stack-port','17827','--decoder-url','http://127.0.0.1:19125/v1',
            '--out',str(output),'--scratch',str(scratch),'--manifest',str(self.manifest),'--allow-contention'],timeout=3600)
        result=json.loads((output/'result.json').read_text()) if (output/'result.json').exists() else {}
        rows=result.get('session_results',[])
        statuses=['PASS' if r.get('clean') else 'FAIL' for r in rows]+['UNRUNNABLE']*(2-len(rows))
        self.gate(name,'UNRUNNABLE' if not rows else 'PASS' if result.get('clean') and code==0 else 'FAIL',
            counts(statuses),elapsed,code,reason='Existing capacity clean bar includes no detected foreign load; contention is recorded without pausing',measurements=retained_metadata(result))
        if not self.args.long:
            self.gate('capacity_2x1800','REQUIRED-NOT-RUN',counts(['SKIP']*2),reason='Requires --long and a sufficient explicit --budget')

    def files(self):
        bench='prototypes/streaming-diarization/wp16-file-url-long/'
        scratch=self.work/'files'; output=self.work/'file-results'
        start=time.monotonic()
        code,_,_=self.command('file_prepare',[PY,bench+'prepare.py','--scratch',str(scratch),'--out',str(output)])
        if not code:
            code,_,_=self.command('file_six_minute',['ffmpeg','-v','error','-y','-i',str(scratch/'media/long.wav'),'-t','360',str(scratch/'media/six.wav')])
        for name,codec in [('three.wav',[]),('three.mp3',['-c:a','libmp3lame','-b:a','64k']),('three.m4a',['-c:a','aac','-b:a','64k'])]:
            if not code:
                code,_,_=self.command('file_prepare_'+name,['ffmpeg','-v','error','-y','-i',str(scratch/'media/long.wav'),'-t','180',*codec,str(scratch/'media'/name)])
        specs=[('file_6min',['six.wav']),('file_3min_formats',['three.wav','three.mp3','three.m4a']),('file_failures',['empty.wav','text.mp3','missing','html','hang'])]
        if self.args.long:specs.append(('file_30min',['long.wav']))
        else:self.gate('file_30min','SKIP',counts(['SKIP']*1),reason='Requires --long')
        if code:
            for name,cases in specs:self.gate(name,'UNRUNNABLE',counts(['UNRUNNABLE']*len(cases)),time.monotonic()-start,code,reason='Public media preparation failed')
            return
        origin=self.start('file_origins',[PY,bench+'sources.py','--scratch',str(scratch),'--out',str(output),
            '--source-port','17828','--hang-port','17829','--cert',str(self.cert),'--key',str(self.key)])
        try:
            for _ in range(50):
                if origin.poll() is not None:break
                with socket.socket() as sock:
                    if sock.connect_ex(('127.0.0.1',17828))==0:break
                time.sleep(.1)
            for name,cases in specs:
                codes=[];elapsed=0
                for case in cases:
                    c,d,_=self.command(name+'_'+case,[PY,bench+'probe.py',case,'--base','https://127.0.0.1:17825',
                        '--decoder-url','http://127.0.0.1:19125','--out',str(output),'--scratch',str(scratch),
                        '--source-base','https://127.0.0.1:17828','--hang-base','http://127.0.0.1:17829','--allow-contention'],timeout=7200)
                    codes.append(c);elapsed+=d
                code=next((c for c in codes if c),0)
                statuses=[]; rows=[]
                for case in cases:
                    path=output/(case+'.json')
                    row=json.loads(path.read_text()) if path.exists() else {}
                    status='PASS' if file_passed(row,case) else 'FAIL' if row else 'UNRUNNABLE'
                    statuses.append(status)
                    projection=dict(case=case,status=status,measurements=retained_metadata(row))
                    projection['expected_failure_code']=FILE_FAILURES.get(case)
                    value=row.get('failure_code')
                    projection['observed_failure_code']=value if isinstance(value,str) and re.fullmatch(r'[a-z0-9_]+',value) else None
                    if row and case not in FILE_FAILURES:
                        from moss_transcribe_diarize.lane_word_oracle import words,distance
                        seconds=360 if case=='six.wav' else 180 if case.startswith('three.') else 1800
                        refs=[json.loads(line) for line in (scratch/'media/reference.jsonl').read_text().splitlines()]
                        reference=words(' '.join(r['text'] for r in refs if r['end']<=seconds))
                        meeting=json.loads((scratch/(case+'.meeting.json')).read_text())
                        observed=words(' '.join(r['text'] for r in meeting['transcript']['segments']))
                        projection['ordered_word_score']=distance(reference,observed)
                        from tools.qualify.speaker_quality import score_speakers
                        projection['speaker_quality']=score_speakers(
                            [r for r in refs if r['end']<=seconds], meeting['transcript']['segments'])
                    rows.append(projection)
                self.gate(name,aggregate(statuses,code),counts(statuses),elapsed,code,
                    reason='Existing WP16 bars: durable outcome, five exact exports for speech, audio download, foreign read 404; failures typed and visible after reload',measurements=rows)
        finally:
            self.stop(origin);self.processes.remove(origin)

    def benches(self, ready):
        base = 'https://127.0.0.1:17825'
        expected = [('workspace',14),('demo_lanes',2),('lifecycle',7),('reshare',6),('level_ladder',6),('identity_stress',3)]
        if not ready:
            for name,n in expected:
                self.gate(name,'UNRUNNABLE',counts(['UNRUNNABLE']*n),reason='Isolated stack unavailable')
            return
        workspace = self.work/'workspace'
        selected = [i for i in range(1,15) if i != 9 or self.has_summary_key]
        code, elapsed, _ = self.command('workspace', [PY,'tests/e2e/verify_workspace.py','--base',base,
            '--allow-local-self-signed','--corpus',str(ROOT/'evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s'),
            '--output',str(workspace),'--rows',','.join(map(str,selected))],timeout=3600)
        result = json.loads((workspace/'results.json').read_text()) if (workspace/'results.json').exists() else {'rows':{}}
        rows = result['rows']
        for n in range(1,15):
            if n == 9 and not self.has_summary_key:
                rows['9'] = dict(status='SKIP', reason_code='no_key_in_environment')
            elif str(n) not in rows:
                rows[str(n)] = dict(status='UNRUNNABLE', reason_code='bench_produced_no_row')
        status = ('FAIL' if code not in (0,2,77) or any(v['status']=='FAIL' for v in rows.values())
                  else 'UNRUNNABLE' if code==77 or any(v['status']=='UNRUNNABLE' for v in rows.values())
                  else 'INCOMPLETE' if code==2 else required_rows_verdict(rows))
        self.gate('workspace',status,counts([v['status'] for v in rows.values()]),elapsed,code,measurements=rows)
        for row, value in sorted(rows.items(), key=lambda kv:int(kv[0])):
            self.gate('workspace_row_'+row,value['status'],duration=value.get('seconds',0),reason=value.get('reason_code'),measurements=value)
        demo = self.work/'demo.json'
        code, elapsed, _ = self.command('demo_lanes',[PY,'tests/e2e/verify_demo_lanes.py','--base',base,
            '--allow-local-self-signed','--case','both','--output',str(demo)])
        rows = json.loads(demo.read_text()) if demo.exists() else []
        statuses = ['PASS' if r['passed'] else 'FAIL' for r in rows]+['UNRUNNABLE']*(2-len(rows))
        self.gate('demo_lanes','PASS' if code==0 and statuses==['PASS','PASS'] else 'FAIL',counts(statuses),elapsed,code,measurements=[dict(retained_metadata(row),case=case) for case,row in zip(('alternation','overlap'),rows)])
        for name,n in [('lifecycle',7),('reshare',6)]:
            code, elapsed, log = self.command(name,[PY,'tests/e2e/stress_'+name+'.py'],env=dict(self.env,MOSS_BASE=base))
            matches = re.findall(r'^\s*(PASS|FAIL)\s+',log.read_text(),re.M)
            statuses = matches+['UNRUNNABLE']*max(0,n-len(matches))
            self.gate(name,'PASS' if code==0 and matches==['PASS']*n else 'FAIL',counts(statuses),elapsed,code)
        self.identity()
        if not LADDER.is_file():
            self.gate('level_ladder','UNRUNNABLE',counts(['UNRUNNABLE']*6),reason='Lead ladder script absent; supply --ladder path')
            return
        output = self.work/'ladder.json'
        code, elapsed, _ = self.command('level_ladder',[PY,str(LADDER),str(output),base,','.join(CASES)])
        raw = json.loads(output.read_text())['cases'] if output.exists() else []
        scores = score_ladder(raw)
        for row in scores:
            expected={'system':37,'microphone':32}
            active={'system'} if row['case']=='system@1' else {'microphone'} if row['case']=='mic@1' else set(expected)
            row['lead_reference_retained']={lane:expected[lane] if lane in active else 0 for lane in expected}
            row['reproduces_lead']=all(row['retention_vs_alone'][lane]['alone_unique']==expected[lane]
                and row['retention_vs_alone'][lane]['retained']==row['lead_reference_retained'][lane] for lane in expected)
        statuses = ['PASS' if r.get('finalization')=='final' else 'FAIL' for r in raw]+['UNRUNNABLE']*(6-len(raw))
        self.gate('level_ladder','PASS' if code==0 and statuses==['PASS']*6 else 'FAIL',counts(statuses),elapsed,code,
                  reason='PASS means six finalized measurements; retention has no supplied acceptance threshold. Unique vocabulary is not transcript accuracy.',measurements=scores)

    def identity(self):
        output=self.work/'identity'
        output.mkdir()
        target=output/'stress-results.json'
        statuses,results,codes=[],[],[]
        started=time.monotonic()
        for case in ('single','gap','alternating'):
            target.unlink(missing_ok=True)
            code,elapsed,_=self.command('identity_'+case,[PY,'prototypes/identity-stress/run.py',case,
                '--base','https://127.0.0.1:17825','--out',str(output),'--scratch',str(self.work/'identity-scratch')])
            rows=json.loads(target.read_text()) if target.exists() else []
            row=rows[-1] if rows else {}
            passed=code==0 and identity_passed(row,expected_voices=2 if case=='alternating' else 1)
            statuses.append('PASS' if passed else 'FAIL' if row else 'UNRUNNABLE')
            codes.append(code)
            results.append(dict(case=case,status=statuses[-1],exit_code=code,seconds=elapsed,measurements=retained_metadata(row)))
        self.gate('identity_stress','PASS' if statuses == ['PASS']*3 else 'FAIL',counts(statuses),
                  time.monotonic()-started, 0 if all(code==0 for code in codes) else 1,
                  reason='One saved identity per reference voice, distinct across voices, zero within-voice switches/unresolved segments; unused births reported separately',
                  measurements=results)

    def cleanup(self):
        for proc in reversed(self.processes):
            self.stop(proc)
        self.monitor_stop.set()
        if self.monitor:
            self.monitor.join(timeout=7)
        if self.proxy:
            self.proxy.close()
        for handle in self.handles:
            handle.close()
        self.data['decoder'] = dict(accepted_requests=self.proxy.sent if self.proxy else 0,
                                    completed_requests=self.proxy.completed if self.proxy else 0,
                                    peak_in_flight=self.proxy.peak if self.proxy else 0,
                                    rejected_by_budget=self.proxy.rejected if self.proxy else 0,
                                    active_at_teardown=self.proxy.active if self.proxy else 0,
                                    budget_exhausted=(self.proxy.sent >= self.args.budget) if self.proxy else False,
                                    shared_metrics='sampled every 2 seconds; not own request attribution')
        alive = []
        for proc in self.processes:
            try:
                os.killpg(proc.pid,0)
                alive.append(proc.pid)
            except ProcessLookupError:
                pass
        self.gate('teardown','FAIL' if alive else 'PASS',measurements={'owned_process_groups_remaining':alive})
        self.data['gate_counts'] = dict(Counter(g['status'] for g in self.data['gates']))
        self.data['budget_censored'] = self.data['decoder']['rejected_by_budget'] > 0
        self.data['verdict'] = ('INCOMPLETE' if self.data['budget_censored']
                                else bundle_verdict(self.data['gates']))
        if self.data['budget_censored']:
            self.data['verdict_reason'] = 'budget_censored'
        self.data['qualified'] = self.data['verdict'] == 'PASS'
        if self.args.compare:
            baseline = json.loads(self.args.compare.read_text())
            deltas = compare(baseline,self.data)
            omitted=[d for d in deltas if not self.args.long and d['name'] in ('file_30min','capacity_2x1800')
                     and d['after'] in ('SKIP','REQUIRED-NOT-RUN')]
            deltas=[d for d in deltas if d not in omitted]
            self.data['determinism'] = dict(baseline=str(self.args.compare),status='PASS' if not deltas else 'FAIL',deltas=deltas,
                                           same_candidate=baseline['identity']['git_sha']==self.sha, intentionally_omitted_long_gates=omitted)
        self.flush()
        print('BUNDLE '+str(self.out),flush=True)


FILE_FAILURES={'empty.wav':'transcode_failed','text.mp3':'transcode_failed','missing':'acquisition_http_404',
               'html':'acquisition_failed','hang':'acquisition_timeout'}


def aggregate(statuses,code):
    if 'FAIL' in statuses:return 'FAIL'
    if 'UNRUNNABLE' in statuses:return 'UNRUNNABLE'
    return 'PASS' if code==0 else 'FAIL'


def file_passed(row,case):
    if not row:return False
    common=(row.get('foreign_read_status')==404 and row.get('history_reason') and row.get('header_reason')
        and row.get('reason_content_free') and row.get('status')==row.get('reload_status'))
    if case in FILE_FAILURES:
        return bool(common and row.get('status')=='failed' and row.get('failure_code')==FILE_FAILURES[case])
    exports=row.get('exports',{})
    return bool(common and row.get('status')=='completed' and row.get('mp3_link') and row.get('mp3_bytes',0)>0
        and set(exports)=={'md','txt','json','srt','vtt'} and all(e['ok'] for e in exports.values()))


def identity_passed(row, expected_voices=2):
    score = row.get('score', {})
    identities = score.get('ids_by_truth', {})
    return (row.get('status') == 'completed' and row.get('finalization') == 'final'
            and row.get('failure') is None and len(identities) == expected_voices
            and all(len(ids) == 1 for ids in identities.values())
            and len({speaker for ids in identities.values() for speaker in ids}) == len(identities)
            and not any(score.get('id_switches', {}).values())
            and score.get('unresolved_segments') == 0)


def score_ladder(rows):
    vocab = {row['case']: set().union(*(set(v) for v in row.get('_tokens_by_speaker',{}).values())) for row in rows}
    controls = {lane: vocab.get(case,set())-vocab.get(other,set()) for lane,case,other in
                [('system','system@1','mic@1'),('microphone','mic@1','system@1')]}
    result=[]
    for row in rows:
        safe = {k:v for k,v in row.items() if k != '_tokens_by_speaker'}
        safe['retention_vs_alone'] = {lane: dict(retained=len(words & vocab[row['case']]), alone_unique=len(words),
                                      fraction=len(words & vocab[row['case']])/len(words) if words else None)
                                     for lane,words in controls.items()}
        result.append(safe)
    return result


def main(argv=None):
    global LADDER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--long',action='store_true')
    parser.add_argument('--budget',type=int,default=request_plan(False)['planned_requests'])
    parser.add_argument('--decoder-upstream-port',type=int,help='Use an existing owned loopback decoder/proxy instead of opening another SSH tunnel')
    parser.add_argument('--out',type=Path)
    parser.add_argument('--compare',type=Path)
    parser.add_argument('--ladder',type=Path,default=LADDER)
    args = parser.parse_args(argv)
    if args.budget < 1:
        parser.error('budget must be positive')
    plan = request_plan(args.long)
    if plan['planned_requests'] > args.budget:
        shortfall = plan['planned_requests'] - args.budget
        print(f"REQUEST BUDGET INSUFFICIENT: planned_requests={plan['planned_requests']} "
              f"budget={args.budget} shortfall={shortfall}", file=sys.stderr)
        return 2
    LADDER = args.ladder
    bundle = Bundle(args, plan)
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    try:
        bundle.static()
        ready = bundle.stack()
        bundle.benches(ready)
        bundle.extended(ready)
    except (Exception,KeyboardInterrupt) as exc:
        bundle.gate('runner','FAIL',reason=type(exc).__name__+'; inspect private runtime log')
        # Preserve details privately, never copy exception strings into the bundle.
        import traceback
        (bundle.work/'runner-error.raw').write_text(traceback.format_exc())
    finally:
        recorded = {gate['name'] for gate in bundle.data['gates']}
        if not args.long and 'capacity_2x1800' not in recorded:
            bundle.gate('capacity_2x1800','REQUIRED-NOT-RUN',counts(['SKIP']*2),
                        reason='Requires --long and a sufficient explicit --budget')
            recorded.add('capacity_2x1800')
        required = dict(python_import=1, asset_parity=17, pytest=0, frontend=0,
                        bundle_helpers=0, typecheck=1, verify_layout=1, stack=1,
                        browser_stress_all=16,file_6min=1,file_3min_formats=3,file_failures=5,file_30min=1,capacity_2x1800=2,
                        workspace=14, demo_lanes=2, lifecycle=7, reshare=6, level_ladder=6, identity_stress=3)
        if not args.long:
            required['capacity_2x300'] = 2
        required.update({'workspace_row_'+str(n):1 for n in range(1,15)})
        for name, expected in required.items():
            if name not in recorded:
                bundle.gate(name, 'UNRUNNABLE', counts(['UNRUNNABLE']*expected),
                            reason='Prerequisite failed or runner interrupted; no observation')
        bundle.cleanup()
    if bundle.data.get('determinism',{}).get('status','PASS') != 'PASS':
        return 1
    return verdict_exit_code(bundle.data['verdict'])


if __name__ == '__main__':
    raise SystemExit(main())
