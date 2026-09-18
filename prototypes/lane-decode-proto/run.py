"""THROWAWAY real Live API probe. One command: python prototypes/lane-decode-proto/run.py same
Question: serial lane decode preserves lane words/speakers through Stop -> saved?
Falsifier: terminal removes a populated lane or same voice collapses into one identity.
Full relevant state (counts, queue, attribution, timing) printed after every frame.
"""
import sys,json,time,ssl,base64,re,array,math,random,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tests.e2e.verify_demo_lanes import Client,lane_pcm
CORPUS=Path('/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus')
HERE=Path(__file__).resolve().parent
OUT=ROOT/'evidence/mvpfix/wp1'
words=lambda s:re.findall(r'[a-z0-9]+',s.lower())
def surface_summary(segs):
    by={}
    for s in segs:
        lane=s.get('source_lane','unknown')
        entry=by.setdefault(lane,{'words':0,'speakers':set(),'unattributed_words':0})
        n=len(words(s.get('text','')));entry['words']+=n
        speaker=s.get('canonical_speaker') or s.get('speaker_entity_id')
        if speaker:entry['speakers'].add(speaker)
        else:entry['unattributed_words']+=n
    return {k:{**v,'speakers':sorted(v['speakers'])} for k,v in by.items()}
def wer(ref,hyp):
    # Edit alignment records substitutions, omissions, additions separately.
    previous=[(j,0,0,j) for j in range(len(hyp)+1)]
    for i,r in enumerate(ref,1):
        row=[(i,0,i,0)]
        for j,h in enumerate(hyp,1):
            a=previous[j-1];b=previous[j];c=row[j-1]
            row.append(min((a[0]+(r!=h),a[1]+(r!=h),a[2],a[3]),(b[0]+1,b[1],b[2]+1,b[3]),(c[0]+1,c[1],c[2],c[3]+1)))
        previous=row
    e,s,d,i=previous[-1]
    return {'reference_words':len(ref),'hypothesis_words':len(hyp),'substitutions':s,'omissions':d,'additions':i,'wer':e/len(ref) if ref else None}
case=sys.argv[1] if len(sys.argv)>1 else 'same'
run_id=os.environ.get('WP1_RUN_TAG','fixed-v1')+'-'+case
request_before=len((HERE/'scratch/latencies.jsonl').read_text().splitlines())
seconds=48 if case=='alternation' else 12 if case=='stop_mid' else 24
clips=['interview_bill_ackman_60s','interview_bill_ackman_60s' if case=='same' else 'interview_keyu_jin_60s']
audios=[lane_pcm(CORPUS/x/'audio.wav',seconds) for x in clips]
if case.startswith('mic-') or case.startswith('system-'):
    lane,db=case.split('-');i=0 if lane=='system' else 1
    audios[i]=lane_pcm(CORPUS/clips[i]/'audio.wav',seconds,10**(-float(db)/20))
if case in ('zero','system_control'):audios[1]=bytes(len(audios[1]))
if case=='mic_control':audios[0]=bytes(len(audios[0]))
if case=='noise':
    rng=random.Random(1);x=array.array('h',(round(rng.gauss(0,32768*10**(-45/20))) for _ in range(len(audios[1])//2)));audios[1]=x.tobytes()
input_levels={}
for lane,pcm in zip(('system','microphone'),audios):
    samples=array.array('h');samples.frombytes(pcm)
    rms=math.sqrt(sum(v*v for v in samples)/len(samples))/32768
    input_levels[lane]={'dbfs':20*math.log10(rms) if rms else None,'all_zero':not any(pcm)}
c=Client('https://127.0.0.1:17871',ssl._create_unverified_context())
c.call('POST','/api/workspace/bootstrap')
d=c.call('GET','/api/live/descriptor')['descriptor']
ident=c.call('POST','/api/live/sessions',{'source_revision':d['source_revision']})['id']
fs=d['frame_samples'];sr=d['sample_rate'];fb=fs*2;n=seconds*sr//fs;zero=bytes(fb)
start=time.monotonic();epoch=time.time_ns();depth=[];pre={}
for seq in range(n):
    device_epoch=epoch+(1 if case=='reshare' and seq>=n//2 else 0)
    health={'state':'capturing','device_epoch':device_epoch,'dropped_frames':0,'discontinuities':0,'failure_code':None}
    c.call('POST',f'/api/live/sessions/{ident}/heartbeat',{'schema':'moss-live-helper-health.v1','instance_id':'wp1-prototype','sequence':seq,'sent_monotonic_ns':time.monotonic_ns(),'helper_version':'prototype','state':'capturing','lanes':{'system':health,'microphone':dict(health)}})
    for i,lane in enumerate(('system','microphone')):
        chunk=audios[i][seq*fb:(seq+1)*fb]
        if case=='alternation' and i!=(seq//(n//2)):chunk=zero
        c.call('POST',f'/api/live/sessions/{ident}/frames',{'lane':lane,'sequence':seq,'capture_timestamp_ns':epoch+seq*fs*1000000000//sr,'device_epoch':device_epoch,'pcm_base64':base64.b64encode(chunk).decode(),'sample_count':fs,'sample_rate':sr,'silent':chunk==zero,'discontinuity':case=='reshare' and seq==n//2})
    snap=c.call('GET',f'/api/live/sessions/{ident}/snapshot')['snapshot'];pre=snap['session']
    state={'case':case,'frame':seq,'accepted':pre['accepted_samples'],'committed':pre['committed_samples'],'pending':pre.get('pending_span_ids'), 'surface':surface_summary(pre.get('effective_transcript',[])),'arbiter':snap.get('arbiter'),'pending_signals':snap.get('pending_signals')}
    depth.append(state)
    print(json.dumps(state),flush=True)
    time.sleep(max(0,(seq+1)*fs/sr-(time.monotonic()-start)))
stop=time.monotonic();c.call('POST',f'/api/live/sessions/{ident}/stop',{'deadline':30})
while True:
    snap=c.call('GET',f'/api/live/sessions/{ident}/snapshot')['snapshot'];ses=snap['session']
    if ses.get('finalization_status') in ('final','failed','unavailable') or time.monotonic()-stop>90:break
    time.sleep(.25)
final_seconds=time.monotonic()-stop
meeting=c.call('GET',f'/api/meetings/{ident}')
# Save API shapes privately for scorer development, never commit transcripts.
(HERE/'scratch'/f'{run_id}-surfaces.json').write_text(json.dumps({'pre':pre,'final':ses,'meeting':meeting}))
request_after=len((HERE/'scratch/latencies.jsonl').read_text().splitlines())
result={'case':case,'run_id':run_id,'prototype':'production-v1','input_levels':input_levels,'first_request':request_before+1,'last_request':request_after,'request_count':request_after-request_before,'capture_start_monotonic':start,'capture_stop_monotonic':stop,'seconds':seconds,'pre':surface_summary(pre.get('effective_transcript',[])),'final':surface_summary(ses.get('effective_transcript',[])),'finalization':ses.get('finalization_status'),'stop_to_final_seconds':final_seconds,'meeting_top_keys':list(meeting),'queue_frames':depth}
(OUT/f'{run_id}.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='queue_frames'}),flush=True)

saved=meeting['transcript']['segments']
final=ses.get('effective_transcript',[])
failures=[]
if ses.get('finalization_status')!='final':failures.append('not_finalized')
if [(s['text'],s.get('speaker_entity_id')) for s in saved]!=[(s['text'],s.get('canonical_speaker')) for s in final]:failures.append('saved_final_mismatch')
summary=surface_summary(final)
for lane, earlier in surface_summary(pre.get('effective_transcript',[])).items():
    if earlier['words'] and not summary.get(lane,{}).get('words',0):failures.append(lane+'_words_erased_at_terminal')
    if earlier['speakers'] and not summary.get(lane,{}).get('speakers',[]):failures.append(lane+'_identity_erased_at_terminal')
if case=='same':
    system=set(summary.get('system',{}).get('speakers',[]))
    mic=set(summary.get('microphone',{}).get('speakers',[]))
    if len(system)!=1 or len(mic)!=1 or system&mic:failures.append('same_voice_not_two_lane_scoped_speakers')
if case in ('zero','noise'):
    mic=summary.get('microphone',{})
    if mic.get('words',0) or mic.get('speakers',[]):failures.append('non_speech_mic_produced_words_or_speakers')
    if any(row['surface'].get('microphone',{}).get('words',0) for row in depth):failures.append('non_speech_mic_produced_live_words')
result['falsifiers_failed']=failures
(OUT/f'{run_id}.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'run_id':run_id,'falsifiers_failed':failures,'request_count':request_after-request_before}),flush=True)
if failures:sys.exit(2)
