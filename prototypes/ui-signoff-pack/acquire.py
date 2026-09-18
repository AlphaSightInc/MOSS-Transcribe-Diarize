"""PROTOTYPE: acquire genuine public-corpus UI states on the isolated WP24 stack.
No production thresholds changed. Frame protocol and 30-second lease unchanged.
"""
import base64, json, ssl, sys, time, wave, threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tests.e2e.verify_demo_lanes import Client, reference_inputs
OUT=ROOT/'evidence/mvpfix/wp24';TMP=ROOT/'.wp24';BASE='https://127.0.0.1:17884'
def main():
    c=Client(BASE,ssl._create_unverified_context()); c.call('POST','/api/workspace/bootstrap')
    (TMP/'cookies.json').write_text(json.dumps(c._jar))
    d=c.call('GET','/api/live/descriptor')['descriptor'];size=d['frame_samples'];fb=size*2
    inp=reference_inputs(.03); total=max((len(x['pcm'])+fb-1)//fb for x in inp.values())
    ident=c.call('POST','/api/live/sessions',{'source_revision':d['source_revision']})['id']
    (TMP/'live-id').write_text(ident); epoch=time.time_ns(); start=time.monotonic(); snaps=[]
    for seq in range(total):
        health=dict(state='capturing',device_epoch=epoch,dropped_frames=0,discontinuities=0,failure_code=None)
        c.call('POST',f'/api/live/sessions/{ident}/heartbeat',dict(schema='moss-live-helper-health.v1',instance_id='wp24-public-corpus',sequence=seq,sent_monotonic_ns=time.monotonic_ns(),helper_version='wp24-pack',state='capturing',lanes={'system':health,'microphone':dict(health)}))
        for lane,row in inp.items():
            chunk=row['pcm'][seq*fb:(seq+1)*fb].ljust(fb,b'\0')
            c.call('POST',f'/api/live/sessions/{ident}/frames',dict(lane=lane,sequence=seq,capture_timestamp_ns=epoch+round(seq*size/16000*1e9),device_epoch=epoch,pcm_base64=base64.b64encode(chunk).decode(),sample_count=size,sample_rate=16000,silent=not any(chunk),discontinuity=False))
        snap=c.call('GET',f'/api/live/sessions/{ident}/snapshot')
        if not snaps or snap!=snaps[-1]:snaps.append(snap)
        time.sleep(max(0,(seq+1)*size/16000-(time.monotonic()-start)))
    pre=c.call('GET',f'/api/live/sessions/{ident}/snapshot')
    ids=pre['snapshot']['session']['identity_snapshot']['canonical_speakers']
    enrollment=None
    if ids:
        enrollment=c.call('PUT',f'/api/meetings/{ident}/speakers/{ids[0]}/name',dict(label='Public corpus speaker',save_voiceprint=True))
    stop=[]
    t=threading.Thread(target=lambda:stop.append(c.call('POST',f'/api/live/sessions/{ident}/stop',{'deadline':30})));t.start()
    while t.is_alive():
        snaps.append(c.call('GET',f'/api/live/sessions/{ident}/snapshot'));time.sleep(.2)
    t.join(); final=c.call('GET',f'/api/live/sessions/{ident}/snapshot');saved=c.call('GET',f'/api/meetings/{ident}')
    data=dict(provenance='Real vLLM, public Bill Ackman + Keyu Jin reference intervals, overlapping lanes, API-fed at real time; not physical devices.',seconds=round(time.monotonic()-start,3),pre=pre,final=final,saved=saved,snapshots=snaps,enrollment=enrollment,voiceprints=c.call('GET','/api/voiceprints'))
    (OUT/'live-source.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({'live_status':saved['status'],'snapshots':len(snaps),'seconds':data['seconds']}),flush=True)
    # Actual lease expiry, no shortened lease or injected terminal state.
    interrupted=c.call('POST','/api/live/sessions',{'source_revision':d['source_revision']})['id']
    for _ in range(80):
        obj=c.call('GET',f'/api/meetings/{interrupted}')
        if obj['status']!='active':break
        time.sleep(.5)
    data=dict(saved=obj,snapshot=c.call('GET',f'/api/live/sessions/{interrupted}/snapshot'),provenance='Real default 30-second helper lease expiry; no frames sent.')
    (OUT/'interrupted-source.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({'interrupted':obj['status']}),flush=True)
if __name__=='__main__':main()
