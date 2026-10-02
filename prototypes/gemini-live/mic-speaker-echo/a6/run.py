"""Absorbed offline A5 replay bench. One command; full state; no provider/product edits."""
import copy
import difflib
import inspect
import json
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path[:0]=[str(ROOT),str(HERE),str(HERE.parent/'a4'),str(HERE.parent/'f1')]
import product_pipeline as pipeline
import score
import stream
from inspect_run import load, probe, BASE
from moss_transcribe_diarize.app import gemini_live_runtime as rt

EV=BASE.parents[1]/'R5B-A5'
S=16000
HEAD=rt._repeated_head
scope=dict(rt.__dict__)
exec(inspect.getsource(HEAD).replace('shown_gap <= 16','shown_gap <= 24'),scope)
GAP24=scope['_repeated_head']


def units(t):return score.units(t,fold=False)
def cut(raw,shown):return len(units(raw))-len(units(shown))
def shown_after(raw,n):
    spans=rt._preview_units(raw)
    return raw[spans[n-1][2]:].lstrip(' \t\r\n,.;:!?，。；：！？、') if n else raw

def residue(text,solid,bounded=False):
    ref=score.units(' '.join(solid[-12:] if bounded else solid))
    grey=score.units(text)
    if bounded:ref=ref[-2*max(60,len(grey)*5//4+8):]
    return score.repeated(grey,ref)


class Floor:
    def __init__(self):self.state={}
    def apply(self,rows,frontiers,finished=()):
        active={r['key'] for r in rows if r['key'] is not None}
        self.state={k:v for k,v in self.state.items() if k in active}
        out=[]
        for row in rows:
            key=row['key'];n=row['base_cut'];f=frontiers.get(row['lane'],0)
            old=self.state.get(key) if key is not None else None
            if old and f>=old['frontier'] and row['raw_count']>=old['n']:
                n=max(n,old['n'])
            if key is not None:self.state[key]=dict(n=n,frontier=f)
            out.append(n)
        for key in finished:self.state.pop(tuple(key),None)
        return out


def capture(name,loader,head):
    trace=[]
    class Capture(rt.GeminiLiveRuntime):
        def publish_update(self,session_id,update):
            if isinstance(update,rt.GeminiPreview) and update.segments:
                before=self.snapshot(session_id).session.effective_transcript
                memory=copy.deepcopy(self._sessions[session_id].preview_cuts)
            result=super().publish_update(session_id,update)
            if isinstance(update,rt.GeminiPreview) and update.segments:
                state=self._sessions[session_id]
                out=self.snapshot(session_id).session.provisional.segments
                rows=[]
                for row in update.segments:
                    matching=[r for r in update.origins if r.source_lane==row.source_lane and r.text==row.text
                        and r.start_sample<=row.start_sample and r.end_sample>=row.end_sample]
                    key=(row.source_lane,matching[0].start_sample) if len(matching)==1 else None
                    kept=next((r['text'] for r in out if r['source_lane']==row.source_lane
                               and r['start_sample']==row.start_sample and r['end_sample']==row.end_sample),'')
                    rows.append(dict(lane=row.source_lane,key=key,start=row.start_sample,end=row.end_sample,
                                     raw=row.text,raw_count=len(units(row.text)),base_cut=cut(row.text,kept),shown=kept))
                trace.append(dict(at=max((c for _,c in update.lane_end_samples),default=update.end_sample)/S,
                    rows=rows,solid=[[r.start_sample,r.end_sample,r.text,r.source_lane] for r in before],
                    frontiers=dict(state.preview_snapshots.frontiers),memory_before=memory,
                    memory_after=copy.deepcopy(state.preview_cuts),finished=update.finished_turns,
                    snapshot=pipeline.snapshot_state(state.preview_snapshots)))
            return result
    rt._repeated_head=head
    try:pipeline.replay(name,loader,Capture)
    finally:rt._repeated_head=HEAD
    return trace


def aggregate(trace,outputs,truths,base_outputs):
    stat=dict(observations=len(trace),repeat_unit_seconds=0.,bounded_repeat_unit_seconds=0.,max_repeat=0,
       proxy_fresh_hidden_unit_observations=0,additional_proxy_fresh_hidden=0,proxy_fresh_rows=0,
       unmeasured_boundary_rows=0,changed_observations=0,changed_already_correct=0,
       hidden_after_confirmed_publication=0,known_publication_rows=0)
    episodes=[];opened=None;prev_at=None
    for i,(event,out) in enumerate(zip(trace,outputs)):
        dt=max(0,trace[i+1]['at']-event['at']) if i+1<len(trace) else 0
        repeat=bounded=0;allknown=True;fresh=0;basefresh=0
        for j,(r,n) in enumerate(zip(event['rows'],out)):
            text=shown_after(r['raw'],n)
            solid=[x[2] for x in event['solid'] if x[3]==r['lane']]
            repeat+=residue(text,solid);bounded+=residue(text,solid,True)
            t=truths[i][j]['boundary']
            if t is None:stat['unmeasured_boundary_rows']+=1;allknown=False
            else:
                loss=max(0,n-t);bloss=max(0,base_outputs[i][j]-t)
                fresh+=loss;basefresh+=bloss
                stat['proxy_fresh_hidden_unit_observations']+=loss
                stat['additional_proxy_fresh_hidden']+=max(0,loss-bloss)
                stat['proxy_fresh_rows']+=loss>0
            clocks=truths[i][j].get('publication_clocks')
            if clocks is not None:
                stat['known_publication_rows']+=1
                stat['hidden_after_confirmed_publication']+=sum(c is not None and c>event['frontiers'].get(r['lane'],0) for c in clocks[:n])
        stat['repeat_unit_seconds']+=repeat*dt
        stat['bounded_repeat_unit_seconds']+=bounded*dt
        stat['max_repeat']=max(stat['max_repeat'],repeat)
        changed=out!=base_outputs[i];stat['changed_observations']+=changed
        base_repeat=sum(residue(shown_after(r['raw'],n),[x[2] for x in event['solid'] if x[3]==r['lane']]) for r,n in zip(event['rows'],base_outputs[i]))
        stat['changed_already_correct']+=bool(changed and base_repeat==0 and basefresh==0 and allknown)
        # A long-repeat episode is continuous >=100 units, not each repeated poll.
        if bounded>=100 and opened is None:opened=event['at']
        if bounded<100 and opened is not None:
            episodes.append([opened,event['at']]);opened=None
    if opened is not None:episodes.append([opened,trace[-1]['at']])
    stat['large_repeat_episodes']=episodes
    for k in ['repeat_unit_seconds','bounded_repeat_unit_seconds']:stat[k]=round(stat[k],3)
    stat['verdict']='FAIL' if stat['additional_proxy_fresh_hidden'] else 'NO_MEASURED_ADDITIONAL_PROXY_LOSS; acoustic guarantee UNMEASURED'
    return stat


def recorded(name,loader):
    events,commits,total=loader()
    t0=capture(name,loader,HEAD);t2=capture(name,loader,GAP24)
    assert len(t0)==len(t2)
    final=stream.final_rows(commits)
    lineage={};indexed={}
    for text,start,end,_ in sorted(events,key=lambda e:e[2]):
        raw=units(text);prior,clocks=lineage.get(start,([],[]))
        prefix=next((i for i,(a,b) in enumerate(zip(prior,raw)) if a!=b),min(len(prior),len(raw)))
        clocks=clocks[:prefix]+([end]*(len(raw)-prefix) if prefix==len(prior) else [None]*(len(raw)-prefix))
        lineage[start]=(raw,clocks);indexed[(text.strip(),end)]=clocks
    truths=[]
    for e in t0:
        rows=[]
        for r in e['rows']:
            f=e['frontiers'].get(r['lane'],0)
            solid=[x[2] for x in e['solid'] if x[3]==r['lane']]
            t=score.true_cut(units(r['raw']),score.later_solid(final,r['lane'],f),score.units(' '.join(solid))[-r['raw_count']-40:])
            rows.append(dict(boundary=t,publication_clocks=indexed.get((r['raw'],r['end']))))
        truths.append(rows)
    floor=Floor();c0=[];c1=[];c2=[];full=[]
    for i,e in enumerate(t0):
        c0.append([r['base_cut'] for r in e['rows']])
        c1.append(floor.apply(e['rows'],e['frontiers'],e['finished']))
        assert [(r['raw'],r['key']) for r in e['rows']]==[(r['raw'],r['key']) for r in t2[i]['rows']]
        c2.append([r['base_cut'] for r in t2[i]['rows']])
        full.append(dict(**e,candidate_cuts=dict(C0=c0[-1],C1=c1[-1],C2=c2[-1]),
                         c1_state=copy.deepcopy(list(floor.state.items())),truth=truths[i],c2_snapshot=t2[i]['snapshot'],
                         c2_memory=t2[i]['memory_after']))
    (EV/f'{name}-full-state.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in full))
    for event in full:print(json.dumps(dict(population=name,full_state=event),ensure_ascii=False),flush=True)
    out={n:aggregate(t0,cuts,truths,c0) for n,cuts in [('C0',c0),('C1',c1),('C2',c2)]}
    out['audio_seconds']=total/S;out['scope']='complete production hybrid->lanes->runtime replay; later-solid proxy/first-publication lineage separately'
    return out


def stress(sub,name):
    xs=load(sub);trace=[];truths=[];previous=[];next_id=0
    # Only already published suffixes exist. Track overlapping observed rows as conditional keys.
    final=next(x['solid'] for x in reversed(xs) if x['status']=='active')
    final_rows=[[r['start_sample'],r['end_sample'],r['text'],r.get('source_lane')] for r in final]
    floor=Floor();c0=[];c1=[];c2=[];full=[]
    memory=[]
    for x in xs:
        if x['status']!='active':continue
        shown=(x.get('provisional') or {}).get('segments',[])
        rows=[];now=[];ts=[]
        fronts={lane:max((r['end_sample'] for r in x['solid'] if r.get('source_lane')==lane),default=0) for lane in ['system','microphone']}
        # Published-row C2 repair: exact raw prefixes already cut are unrecoverable.
        ss=tuple(rt.GeminiSegment(r['start_sample'],r['end_sample'],r['text'],source_lane=r['source_lane']) for r in shown)
        cc=tuple(score.eff([r['start_sample'],r['end_sample'],r['text'],r.get('source_lane')]) for r in x['solid'])
        rt._repeated_head=GAP24
        try:retrim=rt._trim_committed_preview(ss,cc,memory)
        finally:rt._repeated_head=HEAD
        cs2=[v[2] for v in score.cuts(ss,retrim)]
        for r in shown:
            lane=r['source_lane']; matches=[o for o in previous if o['lane']==lane and r['start_sample']<o['end'] and r['end_sample']>=o['end']]
            if len(matches)==1:key=matches[0]['key']
            else:next_id+=1;key=(lane,next_id)
            p=x.get('preview',{}).get(lane,{})
            only=sum(q['source_lane']==lane for q in shown)==1
            hidden=p.get('raw_units_last',0)-p.get('shown_units_last',0) if only and p else 0
            raw_count=len(units(r['text']))+hidden
            row=dict(lane=lane,key=key,start=r['start_sample'],end=r['end_sample'],raw=r['text'],raw_count=raw_count,base_cut=hidden,missing_prefix=hidden)
            rows.append(row);now.append(row)
            t=score.true_cut(units(r['text']),score.later_solid(final_rows,lane,fronts[lane]),score.units(' '.join(q['text'] for q in x['solid'] if q.get('source_lane')==lane))[-len(units(r['text']))-40:])
            ts.append(dict(boundary=t))
        counts=floor.apply(rows,fronts)
        baseline=[0]*len(rows)
        extra=[max(0,n-r['missing_prefix']) for r,n in zip(rows,counts)]
        # Below floor on hidden-prefix-only rows cannot be rendered/scored; subtract known missing count.
        assert all(n<=len(units(r['raw'])) for r,n in zip(rows,extra))
        event=dict(at=x['e'],rows=rows,solid=[[r['start_sample'],r['end_sample'],r['text'],r.get('source_lane')] for r in x['solid']],frontiers=fronts)
        trace.append(event);truths.append(ts);c0.append(baseline);c1.append(extra);c2.append(cs2)
        full.append(dict(**event,candidate_additional_cuts=dict(C0=baseline,C1=extra,C2=cs2),c1_state=copy.deepcopy(list(floor.state.items())),c2_memory=copy.deepcopy(memory),truth=ts))
        previous=now
    (EV/f'{name}-published-state.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in full))
    for event in full:print(json.dumps(dict(population=name,full_state=event),ensure_ascii=False),flush=True)
    out={n:aggregate(trace,cuts,truths,c0) for n,cuts in [('C0',c0),('C1',c1),('C2',c2)]}
    out['audio_seconds']=300 if name=='c6s' else 960
    out['scope']='published-row repair only; c6s count floors seeded from captured counters; row-overlap continuity CONDITIONAL; c6 missing raw cut history'
    return out


def main():
    EV.mkdir(parents=True,exist_ok=True)
    report={'base':'8f232636','provider_calls':0,'cost_usd':0,'candidates':{'C0':'current','C1':'same-turn count floor','C2':'asymmetric gap16->24'}}
    for name,loader in [('zh-188s',stream.load_zh),('en-302s',stream.load_e1),('r5d-cell',stream.load_cell)]:
        report[name]=recorded(name,loader);print(name,json.dumps(report[name]),flush=True)
    for sub,name in [('runs-recheck/c6s','c6s'),('runs/c6','c6')]:
        report[name]=stress(sub,name);print(name,json.dumps(report[name]),flush=True)
    (EV/'measurement.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    from inspect_run import main as diagnose
    from rewrite_control import main as rewrite
    diagnose()
    rewrite()
    print('Full state:',EV)
if __name__=='__main__':main()
