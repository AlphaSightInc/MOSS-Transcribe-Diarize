"""$0 recorded publication matrix; full state persisted beside summary."""
import json, sys, time, statistics, copy
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent/'f1')]
import candidate
import score
from moss_transcribe_diarize.app.live_session import EffectiveTranscriptSegment
rt=candidate.rt
ROOT=Path.home()/'Documents/Codex/2026-09-28/moss-gemini/evidence'
EV=ROOT/'P73/a2'

def load_stress(cell):
    eff=[]; calls=[]
    for line in (ROOT/f'P73/r5b-stress/runs/{cell}/snapshots.jsonl').read_text().splitlines():
        s=json.loads(line)
        if s.get('effective') is not None: eff=s['effective']
        if s['status']!='active' or not s.get('provisional'): continue
        calls.append(dict(at=round(s['e']*16000),frontier=s['committed'],segments=[
            [r['start_sample'],r['end_sample'],r['text'],r.get('source_lane')] for r in s['provisional']['segments']],
            committed=[[r['start_sample'],r['end_sample'],r['text'],r.get('source_lane')] for r in eff]))
    return calls

def measure(calls, arm, log=False):
    times=[]; totals={}; previous={}; detail=[]
    for c in calls:
        segments=tuple(score.seg(r) for r in c['segments']); committed=tuple(score.eff(r) for r in c['committed'])
        t=time.perf_counter(); out=arm(segments,committed); times.append((time.perf_counter()-t)*1000)
        for lane in ('system','microphone'):
            solid=score.units(' '.join(r.text for r in committed if r.source_lane==lane))
            grey=score.units(' '.join(r.text for r in out if r.source_lane==lane))
            repeated=score.repeated(grey,solid)
            stat=totals.setdefault(lane,dict(repeated=0,fresh=0,max_repeated=0,repeated_seconds=0,reshown=0))
            stat['repeated']+=repeated; stat['fresh']+=len(grey)-repeated; stat['max_repeated']=max(stat['max_repeated'],repeated)
            if lane in previous and previous[lane][1]>=5: stat['repeated_seconds']+=(c['at']-previous[lane][0])/16000
            previous[lane]=(c['at'],repeated)
        if log: detail.append(dict(**c,kept=[[r.start_sample,r.end_sample,r.text,r.source_lane] for r in out],state=copy.deepcopy(getattr(arm,'previous',[]))))
    return dict(lanes=totals,calls=len(calls),mean_ms=statistics.fmean(times),max_ms=max(times)),detail

def main():
    report={}
    for cell in ('c2','c4','c5b','c6'):
        calls=load_stress(cell); report[cell]={}
        for mode in ('base','split','progress'):
            arm=candidate.BASE if mode=='base' else candidate.Trim(mode)
            stat,detail=measure(calls,arm,log=mode=='progress'); report[cell][mode]=stat
            if detail: (EV/f'{cell}-progress.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in detail))
        print(cell,json.dumps(report[cell]),flush=True)
    (EV/'explore.json').write_text(json.dumps(report,indent=2))
if __name__=='__main__': main()
