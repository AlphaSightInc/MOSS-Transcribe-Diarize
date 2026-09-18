"""PROTOTYPE / retained measurement bench, never production.
Question: do identity, enrolment/abstention, rename and bank lifecycle survive supported stress?
Hypothesis: one ID per real voice, stable names, no unknown false name. Falsifier: any contrary
saved/snapshot state. No threshold tuning. Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python
prototypes/identity-stress/run.py <single|gap|alternating|recognition|rename|hygiene|lanes|all>
Uses isolated local stack :17867; public corpus only. Batch JSON state after each observed
identity version/action replaces the skill's interactive TUI to allow reproducible replay.
"""
import argparse, base64, importlib.util, json, ssl, sys, time, wave
from pathlib import Path
from collections import Counter, defaultdict
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tests.e2e.verify_demo_lanes import Client, snapshot_segments
from moss_transcribe_diarize.lane_word_oracle import normalize_segment, score_lanes
OUT=ROOT/'evidence/mvpfix/wp7'
SCRATCH=ROOT/'.wp7runtime'
CORPUS=ROOT/'evidence/live-policy-sweep-20260825/corpus'

def emit(kind, **data):
    row=dict(kind=kind, **data)
    print(json.dumps(row),flush=True)
    with (OUT/'stress-events.jsonl').open('a') as f: f.write(json.dumps(row)+'\n')
    return row

def audio(name,start,end):
    with wave.open(str(CORPUS/name/'audio.wav')) as w:
        assert (w.getframerate(),w.getnchannels(),w.getsampwidth())==(16000,1,2)
        w.setpos(round(start*16000));return w.readframes(round((end-start)*16000))

def speaker_score(rows,truth):
    rows=[normalize_segment(r) for r in rows]
    per=defaultdict(list);ambiguous=0
    for r in sorted(rows,key=lambda r:r['start']):
        overlaps=[(max(0,min(b,r['end'])-max(a,r['start'])),who) for a,b,who in truth]
        overlaps.sort(reverse=True)
        if not overlaps or overlaps[0][0]<=0: continue
        if sum(n>0 for n,_ in overlaps)>1: ambiguous+=1;continue
        per[overlaps[0][1]].append(r['speaker'])
    return dict(ids_by_truth={k:dict(Counter(v)) for k,v in per.items()},
        id_switches={k:sum(a!=b for a,b in zip(v,v[1:])) for k,v in per.items()},
        switch_straddling_segments=ambiguous,
        unresolved_segments=sum(not r['speaker'] or r['speaker']=='S00' for r in rows))

class Probe:
    def __init__(self):
        self.client=Client('https://127.0.0.1:17867',ssl._create_unverified_context())
        self.client.call('POST','/api/workspace/bootstrap')
        # Private scratch cookie lets the local browser inspect the same meeting; never evidence.
        (SCRATCH/'cookies.json').write_text(json.dumps(self.client._jar))
        self.results=[]
    def action(self,method,path,body=None):
        try:
            value=self.client.call(method,path,body);return dict(http=200,result=value)
        except HTTPError as exc:return dict(http=exc.code,error=json.loads(exc.read()))
    def name(self,ident,speaker,label,save=True):
        return self.action('PUT',f'/api/meetings/{ident}/speakers/{speaker}/name',dict(label=label,save_voiceprint=save))
    def bank(self):return self.client.call('GET','/api/voiceprints')['voiceprints']
    def meeting(self,case,pcm,truth,*,mic=None,actions=None,expected_name=None):
        d=self.client.call('GET','/api/live/descriptor')['descriptor'];size=d['frame_samples'];fb=size*2
        ident=self.client.call('POST','/api/live/sessions',{'source_revision':d['source_revision']})['id']
        epoch=time.time_ns();start=time.monotonic();last=-1;states=[];actions_done=[];recognition=None
        def observe():
            nonlocal last,recognition
            snap=self.client.call('GET',f'/api/live/sessions/{ident}/snapshot')
            s=snap['snapshot']['session'];identity=s['identity_snapshot'];labels=snap.get('speaker_labels',{})
            if expected_name and expected_name in labels.values() and recognition is None:recognition=time.monotonic()-start
            if identity['version']!=last:
                state=emit('snapshot',case=case,elapsed=round(time.monotonic()-start,3),
                    accepted_seconds=s['accepted_samples']/16000,identity=identity,labels=labels,
                    score=speaker_score(snapshot_segments(snap),truth))
                states.append(state);last=identity['version']
            if actions:
                actions(self,ident,identity['canonical_speakers'],time.monotonic()-start,actions_done)
            return snap
        failure=None
        try:
            for seq in range((len(pcm)+fb-1)//fb):
                health=dict(state='capturing',device_epoch=epoch,dropped_frames=0,discontinuities=0,failure_code=None)
                self.client.call('POST',f'/api/live/sessions/{ident}/heartbeat',dict(schema='moss-live-helper-health.v1',
                    instance_id='wp7-stress',sequence=seq,sent_monotonic_ns=time.monotonic_ns(),helper_version='stress',
                    state='capturing',lanes={'system':health,'microphone':dict(health)}))
                for lane,raw in [('system',pcm),('microphone',mic or b'')]:
                    chunk=raw[seq*fb:(seq+1)*fb].ljust(fb,b'\0')
                    self.client.call('POST',f'/api/live/sessions/{ident}/frames',dict(lane=lane,sequence=seq,
                        capture_timestamp_ns=epoch+round(seq*size/16000*1e9),device_epoch=epoch,
                        pcm_base64=base64.b64encode(chunk).decode(),sample_count=size,sample_rate=16000,
                        silent=not any(chunk),discontinuity=False))
                observe();time.sleep(max(0,(seq+1)*size/16000-(time.monotonic()-start)))
            # A 3-second input can finish before the first decoder response. Wait
            # for that response while still active so enrolment is actually attempted.
            if len(pcm) == 3*32000 and actions and not actions_done:
                deadline=time.monotonic()+5
                while not actions_done and time.monotonic()<deadline:
                    observe();time.sleep(.25)
            pre=observe()
        except Exception as exc:
            failure=type(exc).__name__+': '+str(exc);pre=None
        stopped=time.monotonic();stop=self.action('POST',f'/api/live/sessions/{ident}/stop',{'deadline':30})
        final=self.client.call('GET',f'/api/live/sessions/{ident}/snapshot')
        saved=self.client.call('GET',f'/api/meetings/{ident}')
        for _ in range(120):
            if saved['status']!='active':break
            time.sleep(.5);saved=self.client.call('GET',f'/api/meetings/{ident}')
        # Scratch retains public text for browser/export checking only, excluded from Git.
        (SCRATCH/f'{case}.json').write_text(json.dumps(dict(id=ident,final=final,saved=saved,pre=pre)))
        session=final['snapshot']['session'];rows=(saved.get('transcript') or {}).get('segments',[])
        result=emit('result',case=case,meeting=ident,status=saved['status'],failure=failure,
            finalization=session['finalization_status'],seconds=round(time.monotonic()-start,3),
            stop_seconds=round(time.monotonic()-stopped,3),identity=session['identity_snapshot'],
            saved_speakers=sorted({r.get('speaker','') for r in rows}),score=speaker_score(rows,truth),
            recognition_seconds=recognition,recognition_bar_seconds=4.0,actions=actions_done,
            bank=self.bank(),admissions='not exposed in snapshot; see album-events.jsonl')
        self.results.append(result);(OUT/'stress-results.json').write_text(json.dumps(self.results,indent=2)+'\n')
        return ident,result

    def run(self,case):
        adam=audio('interview_adam_frank_180s',49,109)
        bill=audio('interview_bill_ackman_60s',0,29)
        keyu=audio('interview_keyu_jin_60s',0,25)
        if case=='single':self.meeting(case,adam,[(0,60,'Adam')])
        elif case=='gap':self.meeting(case,adam[:25*32000]+bytes(10*32000)+adam[35*32000:],[(0,25,'Adam'),(35,60,'Adam')])
        elif case=='alternating':
            self.meeting(case,bill+keyu+bill[:6*32000],[(0,29,'Bill'),(29,54,'Keyu'),(54,60,'Bill')])
        elif case in ('recognition','rename','hygiene'):
            def enroll(p,ident,ids,elapsed,done):
                if ids and elapsed>=4 and not done:
                    done.append(emit('enroll',response=p.name(ident,ids[0],'WP7 Adam')))
                    done.append(emit('enroll_again',response=p.name(ident,ids[0],'WP7 Adam'),bank=p.bank()))
            ident,res=self.meeting('enroll',adam[:12*32000],[(0,12,'Adam')],actions=enroll)
            sid=res['identity']['canonical_speakers'][0] if res['identity']['canonical_speakers'] else ''
            emit('rename_after_stop',response=self.name(ident,sid,'WP7 stopped',False))
            emit('rename_after_reload',response=self.name(ident,sid,'WP7 reloaded',False))
            self.meeting('recognition',adam[12*32000:24*32000],[(0,12,'Adam')],expected_name='WP7 Adam')
            self.meeting('unknown',keyu[:12*32000],[(0,12,'Keyu')],expected_name='WP7 Adam')
            for profile in self.bank():emit('delete',response=self.action('DELETE',f"/api/voiceprints/{profile['id']}"))
            self.meeting('after_delete',adam[:6*32000],[(0,6,'Adam')],expected_name='WP7 Adam')
            def short(p,ident,ids,elapsed,done):
                if ids and not done:done.append(emit('three_second_enroll',response=p.name(ident,ids[0],'WP7 short')))
            self.meeting('three_seconds',adam[:3*32000],[(0,3,'Adam')],actions=short)
        elif case=='lanes':self.meeting(case,adam[:12*32000],[(0,12,'Adam')],mic=adam[:12*32000])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('case',choices=['all','single','gap','alternating','recognition','rename','hygiene','lanes']);args=parser.parse_args()
    p=Probe()
    for case in (['single','gap','alternating','recognition','lanes'] if args.case=='all' else [args.case]):p.run(case)

if __name__=='__main__':main()
