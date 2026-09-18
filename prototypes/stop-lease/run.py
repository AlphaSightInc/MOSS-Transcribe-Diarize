"""PROTOTYPE / retained regression bench: accepted Stop versus helper abandonment.

One command: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> prototypes/stop-lease/run.py
Production HTTP, runtime, lease coordinator and scratch SQLite; stub ASR only.
Virtual lease clock permits exact 30/35/45/90 s ordering without sleeping; it does
NOT measure decoder latency. --wall-clock uses real 30 s lease and 45/90 s work.
Question: does accepted Stop transfer outcome authority from capture to server?
Falsifier: loss of helper after runtime stop_requested interrupts committed words.
"""
import argparse
import asyncio
import concurrent.futures
import json
import sqlite3
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'tests' / 'phase2'))
from fastapi.testclient import TestClient
from tests.phase2 import test_owner_bound_live_meeting as f
from tests.test_live_helper_failure import FakeTimer
from moss_transcribe_diarize.app import phase2


def exercise(directory, case, delay=45, stage='drain', wall_clock=False, emit=print):
    directory.mkdir(parents=True, exist_ok=True)
    db = directory / 'meeting.sqlite'
    started, release = threading.Event(), threading.Event()
    request_tasks = []
    clock = [0.0]
    trace = []
    begin = time.monotonic()
    class Decoder(f.Decoder):
        calls = 0
        def transcribe_pcm(self, **kwargs):
            self.calls += 1
            if self.calls == 2 and stage == 'drain':
                started.set()
                if not release.wait(130):
                    raise RuntimeError('prototype release missing')
            return super().transcribe_pcm(**kwargs)
    original_terminal = f.WholeMeetingStub.transcribe
    def terminal(self, *args, **kwargs):
        if stage == 'terminal':
            started.set()
            if not release.wait(130):
                raise RuntimeError('prototype terminal release missing')
        if case == 'failure':
            raise RuntimeError('controlled terminal decoder failure')
        return original_terminal(self, *args, **kwargs)
    with patch.object(phase2, 'REQUIRED_SQLITE_RUNTIME', sqlite3.sqlite_version), patch.object(f.WholeMeetingStub, 'transcribe', terminal):
        sessions = asyncio.run(f.provision(db))
        app = f.make_app(db, speech=(True,False,True,False), decoder_factory=Decoder,
                         terminal_text='[0][S01]terminal owner words[0.00075]')
        with TestClient(app, base_url='https://moss.test') as client:
            timer = FakeTimer()
            original_stop = app.state.phase2_live.runtime.stop
            async def tracked_stop(*args, **kwargs):
                request_tasks.append(asyncio.current_task())
                return await original_stop(*args, **kwargs)
            app.state.phase2_live.runtime.stop = tracked_stop
            if not wall_clock:
                app.state.live_helper_failures._timer = timer
                app.state.live_helper_failures._monotonic_ns = lambda: int(clock[0]*1e9)
                app.state.live_helper_presence._monotonic_ns = lambda: int(clock[0]*1e9)
            f.session(client, sessions['a'])
            sid = client.post('/api/live/sessions').json()['id']
            url = f'/api/live/sessions/{sid}'
            sequence = 0
            def heartbeat():
                nonlocal sequence
                response = client.post(url+'/heartbeat', json=f.heartbeat(sequence))
                sequence += 1
                return response.status_code
            def record(action, **extra):
                raw = app.state.phase2_live.runtime.snapshot(sid)
                saved = client.get(f'/api/meetings/{sid}').json()
                row = dict(case=case, stage=stage, delay=delay, virtual_seconds=None if wall_clock else clock[0],
                           elapsed_seconds=time.monotonic()-begin, action=action,
                           status=raw.session.status, finalization=raw.session.finalization_status,
                           failure=None if raw.terminal_failure is None else raw.terminal_failure.code,
                           lease_armed=sid in app.state.live_helper_failures._sessions,
                           saved_status=saved['status'], saved_words=sum(len(s['text'].split()) for s in (saved.get('transcript') or {}).get('segments',[])),
                           accepted_samples=raw.session.accepted_samples, accounted_samples=raw.session.accounted_samples,
                           **extra)
                trace.append(row)
                emit(json.dumps(row))
                return row
            heartbeat()
            f.feed_two_lane_span(client,sid)
            f.wait_snapshot(client,sid,lambda r:r['meeting_transcript_version']>0)
            record('committed_prefix')
            if stage == 'drain':
                f.feed_two_lane_pairs(client,sid,range(3,5))
                assert started.wait(5)
            pool = concurrent.futures.ThreadPoolExecutor(1)
            try:
                stop = pool.submit(client.post,url+'/stop',json={'deadline':0 if case=='deadline' else 30})
                for _ in range(500):
                    if any(e.kind=='stop_requested' for e in app.state.phase2_live.runtime.events(sid)):
                        break
                    time.sleep(.002)
                else:
                    raise AssertionError('Stop was not accepted')
                if stage == 'terminal':
                    assert started.wait(5)
                record('accepted_stop')
                if case == 'disconnect':
                    client.portal.call(request_tasks[0].cancel)
                    record('request_task_cancelled')
                if case == 'deadline':
                    response = stop.result(5)
                    record('caller_wait_expired',http_status=response.status_code,code=response.json().get('code'))
                ticks = sorted(set(list(range(10,delay,10))+[30,35,delay]))
                for second in ticks:
                    if wall_clock:
                        time.sleep(max(0, second-(time.monotonic()-begin)))
                    clock[0]=second
                    if case=='continue' or (case=='outage' and second>=35):
                        code=heartbeat()
                        record('heartbeat',http_status=code)
                    if not wall_clock:
                        for due,handle in list(timer.scheduled):
                            if due <= int(second*1e9) and not handle.cancelled:
                                client.portal.call(handle.fire)
                        client.portal.call(asyncio.sleep,.01)
                    if second>=30:
                        record('clock_advanced')
                release.set()
                try:
                    response=stop.result(10)
                    record('stop_response',http_status=response.status_code,code=response.json().get('code'))
                except (concurrent.futures.CancelledError, RuntimeError) as exc:
                    if case != 'disconnect' or (isinstance(exc, RuntimeError) and str(exc) != 'No response returned.'):
                        raise
                    record('disconnected_response')
                f.wait_snapshot(client,sid,lambda r:r['snapshot']['session']['finalization_status'] in ('final','failed') or r['snapshot']['terminal_failure'] is not None)
                for _ in range(500):
                    saved=client.get(f'/api/meetings/{sid}').json()
                    if saved['status']!='active': break
                    time.sleep(.01)
                result=record('durable_outcome')
                result['case_pass']=result['saved_status']=='completed' and result['finalization']==('failed' if case=='failure' else 'final') and result['saved_words']>0
            finally:
                release.set()
                pool.shutdown(wait=True)
        # Reopen SQLite through the production API after server shutdown.
        async def reopen():
            store=await phase2.Phase2Store.open(db)
            try:
                owner=await store.account_for_session(sessions['a'])
                meeting=await store.workspace(owner).open_meeting(sid)
                snap=await meeting.snapshot()
                return dict(status=snap.status, document_equal=snap.transcript==saved['transcript'], words=sum(len(s['text'].split()) for s in snap.transcript['segments']))
            finally: await store.close()
        restarted=asyncio.run(reopen())
        result['restart_status']=restarted['status']
        result['restart_document_equal']=restarted['document_equal']
        result['restart_words']=restarted['words']
    return dict(result=result,trace=trace)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--wall-clock',action='store_true')
    p.add_argument('--case',choices=['continue','depart','deadline','outage','failure','disconnect'])
    p.add_argument('--stage',choices=['drain','terminal'])
    p.add_argument('--delay',type=int,default=45)
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    out=args.output or ROOT/'evidence/mvpfix/wp15'/f'semantics-{time.time_ns()}.json'
    cases=[args.case] if args.case else ['continue','depart','deadline','outage']
    stages=[args.stage] if args.stage else ['drain','terminal']
    results=[]
    for stage in stages:
        for case in cases:
            results.append(exercise(ROOT/'.wp15'/f'{time.time_ns()}',case,args.delay,stage,args.wall_clock))
    out.write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),passed=sum(r['result']['case_pass'] for r in results),total=len(results))))

if __name__=='__main__':main()
