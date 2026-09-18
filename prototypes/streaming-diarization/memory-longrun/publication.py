"""WP22 supplemental HTTP/SQLite publication retention probe; ASR/identity stubbed.
Same 30-minute two-lane timestamps, accelerated. Counts publication queue and snapshots,
which are outside profile.py's production ONNX/runtime measurement. No GPU/network.
"""
import asyncio,base64,gc,json,os,sqlite3,subprocess,sys,tempfile,time,wave
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
ROOT=Path.cwd();sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'tests/phase2'),str(Path(__file__).parent)]
from fastapi.testclient import TestClient
from tests.phase2 import test_owner_bound_live_meeting as f
from moss_transcribe_diarize.app import phase2
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy,EndpointPolicyConfig
from memory_profile import size
scratch=ROOT/'.wp22/publication';scratch.mkdir(exist_ok=True);tempfile.tempdir=str(ROOT/'.wp22/t')
out=ROOT/'evidence/mvpfix/wp22/publication.jsonl'
original=f.make_runtime
class Decoder(f.Decoder):max_samples=40000

def runtime(**kwargs):
    r=original(**{**kwargs,'decoder_factory':Decoder,'speech':(True,)*4000,'max_tape_bytes':57_600_000})
    r.descriptor=replace(r.descriptor,frame_samples=8000,bounds=replace(r.descriptor.bounds,max_frame_samples=16000,max_retained_samples=320000,hard_cap_samples=40000,max_queue_depth=16))
    r._endpoint_policy_factory=lambda:EndpointPolicy(EndpointPolicyConfig(min_speech_samples=1,min_silence_samples=1,hard_cap_samples=40000))
    return r
with patch.object(phase2,'REQUIRED_SQLITE_RUNTIME',sqlite3.sqlite_version),patch.object(f,'make_runtime',runtime):
    sessions=asyncio.run(f.provision(scratch/'meeting.sqlite'))
    app=f.make_app(scratch/'meeting.sqlite')
    with TestClient(app,base_url='https://moss.test') as client:
        f.session(client,sessions['a']);sid=client.post('/api/live/sessions').json()['id'];route=f'/api/live/sessions/{sid}'
        live=app.state.phase2_live;binding=live._bindings[sid]
        start=time.monotonic();max_queue=0
        def record(second,phase):
            gc.collect()
            async def state():
                return dict(queue_count=binding.queue.qsize(),queue_bytes=size(binding.queue._queue),public_snapshot_bytes=size(binding.public_snapshot),public_events_bytes=size(binding.public_events),durable_document_bytes=size(binding.durable_document),terminal=binding.terminal_persisted)
            row=dict(seconds=second,phase=phase,wall_seconds=time.monotonic()-start,rss_bytes=int(subprocess.check_output(['ps','-o','rss=','-p',str(os.getpid())],text=True))*1024,max_queue_count=max_queue,**client.portal.call(state))
            with out.open('a') as stream:stream.write(json.dumps(row)+'\n')
            print(json.dumps(row),flush=True)
        record(0,'baseline')
        for seq in range(3600):
            assert client.post(route+'/heartbeat',json=f.heartbeat(seq)).status_code==200
            for lane in ['system','microphone']:
                frame=dict(lane=lane,sequence=seq,capture_timestamp_ns=seq*500_000_000,device_epoch=0,pcm_base64=base64.b64encode(b'\x01\x00'*8000).decode(),sample_count=8000,sample_rate=16000,silent=False,discontinuity=False)
                while True:
                    response=client.post(route+'/frames',json=frame)
                    if response.status_code!=429:break
                    time.sleep(.001)
                assert response.status_code==200,response.text
            max_queue=max(max_queue,binding.queue.qsize())
            if (seq+1)%60==0:record((seq+1)//2,'capture')
        response=client.post(route+'/stop',json={'deadline':30});assert response.status_code==200,response.text
        for _ in range(3000):
            if binding.terminal_persisted and binding.queue.empty():break
            time.sleep(.01)
        record(1800,'after_stop')
        saved=client.get(f'/api/meetings/{sid}').json()
        assert saved['status']=='completed',saved['status']
        assert binding.queue.empty()
