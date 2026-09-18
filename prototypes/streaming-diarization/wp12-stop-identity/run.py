"""WP12 real API probe, adapted from WP1. Public corpus only; no transcripts retained."""
import os,sys,json,time,ssl,base64,re
from pathlib import Path
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
from tests.e2e.verify_demo_lanes import Client,lane_pcm,CORPUS
seconds=int(sys.argv[1]);case=sys.argv[2];arm=os.environ.get('WP12_ARM','lane')
OUT=ROOT/'evidence/mvpfix/wp12'
def count():return len((OUT/'requests.jsonl').read_text().splitlines()) if (OUT/'requests.jsonl').exists() else 0
def summary(segs):
    result={}
    for s in segs:
        row=result.setdefault(s.get('source_lane','mono'),dict(words=0,speakers=[]))
        row['words']+=len(re.findall(r"[a-z0-9]+",s['text'].lower()))
        speaker=s.get('canonical_speaker')
        if speaker and speaker not in row['speakers']:row['speakers'].append(speaker)
    return result
pcm=[lane_pcm(CORPUS/x/'audio.wav',60) for x in ('interview_bill_ackman_60s','interview_keyu_jin_60s')]
pcm=[(p*((seconds*32000+len(p)-1)//len(p)))[:seconds*32000] for p in pcm]
c=Client('https://127.0.0.1:17872',ssl._create_unverified_context());c.call('POST','/api/workspace/bootstrap')
d=c.call('GET','/api/live/descriptor')['descriptor'];ident=c.call('POST','/api/live/sessions',{'source_revision':d['source_revision']})['id']
fs=d['frame_samples'];sr=d['sample_rate'];fb=fs*2;n=seconds*sr//fs;zero=bytes(fb);before=count();start=time.monotonic();epoch=time.time_ns()
for seq in range(n):
    health={'state':'capturing','device_epoch':epoch,'dropped_frames':0,'discontinuities':0,'failure_code':None}
    c.call('POST',f'/api/live/sessions/{ident}/heartbeat',{'schema':'moss-live-helper-health.v1','instance_id':'wp12-prototype','sequence':seq,'sent_monotonic_ns':time.monotonic_ns(),'helper_version':'prototype','state':'capturing','lanes':{'system':health,'microphone':dict(health)}})
    for i,lane in enumerate(('system','microphone')):
        chunk=pcm[i][seq*fb:(seq+1)*fb]
        if case=='alternation' and i!=seq//(n//2):chunk=zero
        c.call('POST',f'/api/live/sessions/{ident}/frames',{'lane':lane,'sequence':seq,'capture_timestamp_ns':epoch+seq*fs*1000000000//sr,'device_epoch':epoch,'pcm_base64':base64.b64encode(chunk).decode(),'sample_count':fs,'sample_rate':sr,'silent':chunk==zero,'discontinuity':False})
    snap=c.call('GET',f'/api/live/sessions/{ident}/snapshot')['snapshot']['session']
    print(json.dumps(dict(arm=arm,case=case,frame=seq,accepted=snap['accepted_samples'],committed=snap['committed_samples'],surface=summary(snap.get('effective_transcript',[])))),flush=True)
    time.sleep(max(0,(seq+1)*fs/sr-(time.monotonic()-start)))
pre=snap;stop=time.monotonic();c.call('POST',f'/api/live/sessions/{ident}/stop',{'deadline':30})
while True:
    final=c.call('GET',f'/api/live/sessions/{ident}/snapshot')['snapshot']['session']
    if final.get('finalization_status') in ('final','failed','unavailable') or time.monotonic()-stop>180:break
    time.sleep(.1)
elapsed=time.monotonic()-stop
saved=c.call('GET',f'/api/meetings/{ident}')['transcript']['segments']
surface=final.get('effective_transcript',[])
(ROOT/'.wp12'/f'{arm}-{case}-{seconds}-surface.json').write_text(json.dumps(surface))
result=dict(arm=arm,case=case,seconds=seconds,start=start,stop=stop,stop_to_final=elapsed,status=final.get('finalization_status'),requests=count()-before,pre=summary(pre.get('effective_transcript',[])),final=summary(surface),saved_equal=[(s['text'],s.get('speaker_entity_id')) for s in saved]==[(s['text'],s.get('canonical_speaker')) for s in surface])
(OUT/f'{arm}-{case}-{seconds}.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
