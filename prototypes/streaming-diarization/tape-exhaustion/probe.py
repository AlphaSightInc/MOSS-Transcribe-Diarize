"""WP29 PROTOTYPE / retained HTTP regression bench, derived from WP22 publication.
Question: does tape exhaustion preserve words, truthful audio, and cleanup?
One command: COMMON Python prototypes/streaming-diarization/tape-exhaustion/probe.py
Real public PCM, HTTP/SQLite/MP3/lifecycle; ASR and identity stubbed, audio accelerated.
"""
import argparse
import asyncio
import base64
import concurrent.futures
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'tests/phase2')]
from fastapi.testclient import TestClient
from tests.phase2 import test_owner_bound_live_meeting as f
from tests.test_live_helper_failure import FakeTimer
from moss_transcribe_diarize.app import phase2
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig
from moss_transcribe_diarize.app.live_service_runtime import _ManualTerminalScheduler

CASES = ['stop', 'depart', 'lease_expiry', 'silent_mic', 'system_only', 'microphone_only', 'mixed_only', 'concurrent']

def exercise(directory, case, emit=print, clips=None):
    directory.mkdir(parents=True, exist_ok=True)
    db = directory/'meeting.sqlite'
    original = f.make_runtime
    terminal = _ManualTerminalScheduler()
    class Decoder(f.Decoder):
        max_samples = 40000
    def runtime(**kwargs):
        r = original(**{**kwargs, 'decoder_factory': Decoder, 'speech': (True,)*400,
                         'max_tape_bytes': 60*32000})
        r.descriptor = replace(r.descriptor, frame_samples=8000, bounds=replace(
            r.descriptor.bounds, max_frame_samples=16000, max_retained_samples=320000,
            hard_cap_samples=40000, max_queue_depth=16))
        r._endpoint_policy_factory = lambda: EndpointPolicy(EndpointPolicyConfig(
            min_speech_samples=1, min_silence_samples=1, hard_cap_samples=40000))
        return r
    if clips is None:
        corpus = Path('/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus')
        clips = []
        for name in ['interview_bill_ackman_60s', 'interview_keyu_jin_60s']:
            with wave.open(str(corpus/name/'audio.wav')) as w:
                assert (w.getframerate(),w.getnchannels(),w.getsampwidth()) == (16000,1,2)
                clips.append(w.readframes(w.getnframes()))
    trace = []
    with patch.object(phase2, 'REQUIRED_SQLITE_RUNTIME', sqlite3.sqlite_version), patch.object(f, 'make_runtime', runtime):
        sessions = asyncio.run(f.provision(db))
        app = f.make_app(db, terminal_text='[0][S01]terminal owner words[2.5]', terminal_scheduler=terminal)
        with TestClient(app, base_url='https://moss.test') as client:
            f.session(client, sessions['a'])
            live = app.state.phase2_live
            clock = [0]
            timer = FakeTimer()
            app.state.live_helper_failures._timer = timer
            app.state.live_helper_failures._monotonic_ns = lambda: clock[0]
            app.state.live_helper_presence._monotonic_ns = lambda: clock[0]
            ids = [client.post('/api/live/sessions').json()['id'] for _ in range(2 if case == 'concurrent' else 1)]
            def record(sid, action):
                snap = live.runtime.snapshot(sid)
                c = live.runtime._sessions[sid].coordinator
                row = dict(case=case, session=ids.index(sid), action=action,
                           status=snap.session.status, finalization=snap.session.finalization_status,
                           accepted=snap.session.accepted_samples, accounted=snap.session.accounted_samples,
                           words=sum(len(s.text.split()) for s in snap.session.effective_transcript),
                           lease_armed=sid in app.state.live_helper_failures._sessions,
                           queue=live._bindings[sid].queue.qsize(),
                           tapes={k:v.accounting(through_sample=snap.session.accepted_samples).to_dict()
                                  for k,v in {'mixed':c.tape, **c.lane_tapes}.items()})
                trace.append(row); emit(json.dumps(row)); return row
            for seq in range(180):
                for sid in ids:
                    route=f'/api/live/sessions/{sid}'
                    assert client.post(route+'/heartbeat',json=f.heartbeat(seq)).status_code == 200
                    for i,lane in enumerate(['system','microphone']):
                        offset=seq*16000%len(clips[i]);pcm=(clips[i]*2)[offset:offset+16000]
                        if case=='silent_mic' and i==1: pcm=bytes(16000)
                        frame=dict(lane=lane,sequence=seq,capture_timestamp_ns=seq*500_000_000,
                            device_epoch=0,pcm_base64=base64.b64encode(pcm).decode(),sample_count=8000,
                            sample_rate=16000,silent=not any(pcm),discontinuity=False)
                        while True:
                            response=client.post(route+'/frames',json=frame)
                            if response.status_code!=429: break
                            time.sleep(.001)
                        assert response.status_code==200,response.text
                    if seq==2 and case.endswith('_only'):
                        # Isolated fault: digital zeros occupy bytes too, so silence cannot
                        # naturally exhaust just one tape. Keep the other two roomy.
                        c=live.runtime._sessions[sid].coordinator
                        target=case.removesuffix('_only')
                        for name,tape in {'mixed':c.tape,**c.lane_tapes}.items():
                            if name!=target:tape.capacity_bytes=120*32000
                    if seq in (2,119,121,179):record(sid,f'capture_{(seq+1)/2:g}s')
            prefixes={sid:live.runtime.snapshot(sid).session.effective_transcript for sid in ids}
            if case=='lease_expiry':
                clock[0]=31_000_000_000
                for due,handle in list(timer.scheduled):
                    if due<=clock[0] and not handle.cancelled:client.portal.call(handle.fire)
            else:
                pool=concurrent.futures.ThreadPoolExecutor(len(ids))
                requests=[pool.submit(client.post,f'/api/live/sessions/{sid}/stop',json={'deadline':30}) for sid in ids]
            for _ in range(1000):
                if all(live.runtime.snapshot(sid).session.status != 'active' for sid in ids):break
                time.sleep(.005)
            for sid in ids:record(sid,'closed_before_terminal')
            if case=='depart':
                clock[0]=90_000_000_000
                for due,handle in list(timer.scheduled):
                    if due<=clock[0] and not handle.cancelled:client.portal.call(handle.fire)
            terminal.drain()
            if case!='lease_expiry':
                responses=[request.result(35) for request in requests]
                pool.shutdown()
                assert all(r.status_code==200 for r in responses),[r.text for r in responses]
            results=[]
            documents={}
            for sid in ids:
                binding=live._bindings[sid]
                for _ in range(1000):
                    if binding.terminal_persisted and binding.queue.empty():break
                    time.sleep(.01)
                saved=client.get(f'/api/meetings/{sid}').json()
                snap=live.runtime.snapshot(sid)
                state=record(sid,'terminal')
                events=[e.to_dict() for e in live.runtime.events(sid) if e.kind.startswith('terminal_finalization')]
                audio=client.get(f'/api/meetings/{sid}/audio/download')
                path=directory/f'{ids.index(sid)}.mp3';path.write_bytes(audio.content)
                probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(path)],text=True)) if audio.status_code==200 else None
                decoded_pcm=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-f','s16le','-ac','1','-ar','16000','-']) if audio.status_code==200 else b''
                before=prefixes[sid]
                failed_lanes={'system','microphone'} if case not in ('system_only','microphone_only','mixed_only') else {case.removesuffix('_only')}
                preserved=all(s in snap.session.effective_transcript for s in before if s.source_lane in failed_lanes)
                result=dict(case=case,session=ids.index(sid),saved_status=saved['status'],finalization=snap.session.finalization_status,
                    terminal_failure=None if snap.terminal_failure is None else snap.terminal_failure.code,
                    saved_segments=len(saved['transcript']['segments']),prefix_preserved=preserved,
                    saved_equal=[s['text'] for s in saved['transcript']['segments']]==[s.text for s in snap.session.effective_transcript],
                    audio=saved['audio'],mp3=probe,decoded_samples=len(decoded_pcm)//2,notice=saved.get('notice'),events=events,state=state)
                documents[result['session']]=saved['transcript']
                results.append(result);emit(json.dumps(result))
            async def reopen():
                store=await phase2.Phase2Store.open(db)
                try:
                    owner=await store.account_for_session(sessions['a'])
                    return [(await (await store.workspace(owner).open_meeting(sid)).snapshot()).to_dict() for sid in ids]
                finally:await store.close()
            # Reopen through a second connection; no in-memory snapshot as persistence proof.
            reopened=asyncio.run(reopen())
            for r,saved in zip(results,reopened):
                r['reopened_status']=saved['status']
                r['reopened_segments']=len(saved['transcript']['segments'])
                r['reopened_document_equal']=saved['transcript']==documents[r['session']]
                r['reopened_notice']=saved.get('notice')
    return dict(case=case,results=results,trace=trace)

def main():
    p=argparse.ArgumentParser();p.add_argument('--case',choices=CASES);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    (ROOT/'.wp29/t').mkdir(parents=True,exist_ok=True);tempfile.tempdir=str(ROOT/'.wp29/t')
    results=[exercise(ROOT/'.wp29'/f'{case}-{time.time_ns()}',case) for case in ([a.case] if a.case else CASES)]
    a.output.write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__':main()
