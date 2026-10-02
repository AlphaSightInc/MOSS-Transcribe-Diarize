"""A4 amended-gate replay: one command; full state receipts; no provider calls."""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE), str(HERE.parent/'f1')]
import candidate
import score
import stream
from moss_transcribe_diarize.app import gemini_live_runtime as rt

S = 16000
EV = Path.home()/'Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-A4'
F1 = EV.parent/'P72/f1/runs'
G = rt.GeminiSegment


def units(text):
    return score.units(text, fold=False)


def snapshot_state(state):
    return dict(clocks=dict(state.clocks),frontiers=dict(state.frontiers),max_pending=state.max_pending,
                overflows=state.overflows,turns=[dict(lane=k[0],start=k[1],snapshot=v.snapshot,
                pending=list(v.pending),lost_through=v.lost_through) for k,v in state.turns.items()])


def run_stream(name, loader, filename, reducer, apply):
    events, commits, total = loader()
    calls = [json.loads(l) for l in (F1/filename).read_text().splitlines()]
    indexed = {(t.strip(),e):(t.strip(),b,e,f) for t,b,e,f in events}
    state, cuts, trace, times = reducer(), [], [], []
    changed = additions = unmatched = safety = parity = 0
    rewrite_rows = rewrite_residue = normal_residue = 0
    residue_seconds = 0.0
    previous = {}
    for index, call in enumerate(calls):
        ss = tuple(score.seg(r) for r in call['segments'])
        cc = tuple(score.eff(r) for r in call['committed'])
        baseline = rt._trim_committed_preview(ss,cc,cuts)
        origins, clocks, finals = [], {}, []
        for row in ss:
            event = indexed.get((row.text,row.end_sample))
            if event is None:
                unmatched += 1
                continue
            t,b,e,f = event
            origins.append(G(b,e,t,source_lane=row.source_lane))
            clocks[row.source_lane] = max(clocks.get(row.source_lane,0),e)
            if f:
                finals.append((row.source_lane,b))
        before = time.perf_counter()
        state.advance(cc)
        state.publication(origins, tuple(clocks.items()), finals)
        tc = state.cuts(ss,origins)
        output = apply(ss,baseline,tc)
        state.finish(finals)
        times.append((time.perf_counter()-before)*1000)
        changed += output != baseline
        rows = []
        for row,(_,raw,bc),(_,_,chosen),time_cut in zip(ss,score.cuts(ss,baseline),score.cuts(ss,output),tc):
            origin = indexed.get((row.text,row.end_sample))
            frontier = state.frontiers.get(row.source_lane,0)
            eligible = [e for e in events if origin and e[1]==origin[1] and e[2]<=frontier]
            snap = max(eligible,key=lambda e:e[2]) if eligible else None
            expected = next((i for i,(a,b) in enumerate(zip(units(snap[0]),raw)) if a!=b),
                            min(len(units(snap[0])),len(raw))) if snap else 0
            # Finals clear after their publication; a new final with no active history
            # and uncertain merged rows abstain rather than borrowing an oracle key.
            safety += max(0,time_cut-expected)
            if time_cut <= bc:
                parity += chosen != bc
            additions += chosen-bc
            later = score.later_solid(stream.final_rows(commits),row.source_lane,frontier)
            truth = score.true_cut(raw,later,score.units(' '.join(r.text for r in cc))[-len(raw)-40:])
            residue = max(0,truth-chosen) if truth is not None else 0
            key = (row.source_lane,origin[1]) if origin else None
            old = previous.get(key,[])
            rewritten = bool(old and raw[:len(old)]!=old)
            previous[key] = raw
            if rewritten:
                rewrite_rows += 1
                rewrite_residue = max(rewrite_residue,residue)
            else:
                normal_residue = max(normal_residue,residue)
            if residue and index+1<len(calls):
                residue_seconds += (calls[index+1]['at']-call['at'])/S
            rows.append(dict(lane=row.source_lane,raw=row.text,baseline_cut=bc,snapshot_cut=time_cut,
                             oracle_snapshot_cut=expected,chosen_cut=chosen,proxy_residue=residue,
                             rewrite=rewritten,shown=[r.text for r in output]))
        trace.append(dict(call=index,rows=rows,state=snapshot_state(state)))
    (EV/f'{name}-{MODE}-trace.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2)+'\n')
    return dict(calls=len(calls),changed_calls=changed,additional_removed_unit_publications=additions,
                time_additions_outside_snapshot= safety, same_gate_mismatches=parity,unmatched_rows=unmatched,
                max_pending=state.max_pending,overflows=state.overflows,
                added_mean_ms=statistics.fmean(times),added_max_ms=max(times),
                max_nonrewrite_residue_later_solid_proxy=normal_residue,
                rewritten_publications=rewrite_rows,max_rewrite_residue_later_solid_proxy=rewrite_residue,
                residue_publication_seconds=round(residue_seconds,3))


def controls(reducer,apply):
    state = reducer()
    old = 'one settled introduction with several words before the frontier'
    fresh = 'Zebras gallop quietly while fresh speakers discuss entirely novel matters today'
    report = []
    def publish(name,origin_start,clock,text,frontier=15,lane='system',finished=(),solid=None,expect=None):
        cc = solid if solid is not None else (score.eff([0,frontier*S,'unrelated solid content',lane]),)
        origin = G(origin_start*S,clock*S,text,source_lane=lane)
        row = G(max(origin_start,frontier)*S,clock*S,text,source_lane=lane)
        state.advance(cc)
        state.publication((origin,),((lane,clock*S),),finished)
        tc=state.cuts((row,),(origin,))[0]
        baseline=rt._trim_committed_preview((row,),cc)
        output=apply((row,),baseline,[tc])
        state.finish(finished)
        if expect is not None:
            assert tc==expect,(name,tc,expect)
        report.append(dict(case=name,snapshot_cut=tc,raw=text,baseline=[r.text for r in baseline],
                           shown=[r.text for r in output],state=snapshot_state(state)))
    publish('pre-frontier',0,14,old,frontier=0,expect=0)
    publish('unchanged-prefix',0,20,old+' '+fresh,expect=len(units(old)))
    publish('partial-rewrite',0,21,'one changed '+fresh,expect=1)
    publish('complete-rewrite',0,22,'rewritten '+fresh,expect=0)
    publish('new-turn-chorus',16,23,old+' '+fresh,expect=0)
    publish('split-turn',17,24,old+' '+fresh,expect=0)
    publish('merge-new-start',5,25,old+' '+fresh,expect=0)
    publish('other-lane',0,26,old+' '+fresh,lane='microphone',expect=0)
    state.clear()
    publish('old-source',0,14,old,frontier=0)
    state.advance((score.eff([0,15*S,'solid','system']),))
    state.reset('system')
    publish('replacement-restart-same-key',0,20,old+' '+fresh,expect=0)
    state.clear()
    publish('no-new-publication-old',0,14,old,frontier=0)
    state.advance((score.eff([0,30*S,'solid','system']),))
    publish('frontier-with-no-publication',0,35,old+' '+fresh,frontier=30,expect=len(units(old)))
    state.clear()
    publish('degraded-old-publication',0,55,old,frontier=15,expect=0)
    publish('rolling-replaces-degraded',0,60,old+' '+fresh,frontier=30,expect=0)
    state.clear()
    publish('eligible-before-final',0,14,old,frontier=0)
    publish('final-ends-turn',0,20,old+' '+fresh,finished=(('system',0),),expect=len(units(old)))
    assert not state.turns
    publish('restated-final-next-interim',20,21,old+' '+fresh,expect=0)
    state.clear()
    publish('stale-lane-original',0,14,old,frontier=0)
    # The other lane advances; stale system clock14 cannot date newly supplied text at20.
    state.publication((G(0,14*S,old+' '+fresh,source_lane='system'),),
                      (('system',14*S),('microphone',20*S)))
    state.advance((score.eff([0,15*S,'solid','system']),))
    assert state.cuts((G(15*S,20*S,old+' '+fresh,source_lane='system'),),
                      (G(0,20*S,old+' '+fresh,source_lane='system'),))==[len(units(old))]
    state.clear()
    publish('before-ambiguous-source',0,14,old,frontier=0)
    state.advance((score.eff([0,15*S,'solid','system']),))
    mixed=(G(0,20*S,old+' '+fresh,source_lane='system'),
           G(0,20*S,'another source turn',source_lane='system'))
    state.publication(mixed,(('system',20*S),))
    assert state.cuts((G(15*S,20*S,old+' '+fresh,source_lane='system'),),mixed)==[0]
    report.append(dict(case='ambiguous-source-key',state=snapshot_state(state)))
    state.clear()
    for clock in range(1,10001):
        state.publication((G(0,clock,old,source_lane='system'),),(('system',clock),))
    assert len(state.turns[('system',0)].pending)==64
    state.advance((score.eff([0,100,'solid','system']),))
    assert state.cuts((G(0,10001,old+' '+fresh,source_lane='system'),),
                      (G(0,10001,old+' '+fresh,source_lane='system'),))==[0]
    report.append(dict(case='10000-publication-stall',state=snapshot_state(state)))
    state.advance((score.eff([0,9999,'solid','system']),))
    assert state.cuts((G(0,10001,old+' '+fresh,source_lane='system'),),
                      (G(0,10001,old+' '+fresh,source_lane='system'),))==[len(units(old))]
    state.clear()
    assert not state.turns and not state.clocks and not state.frontiers
    (EV/f'controls-{MODE}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return dict(printed_cases=len(report),fresh_time_loss=0,stall_publications=10000,pending_bound=64)


def injections(reducer,apply):
    en = units(max(stream.load_e1()[0],key=lambda e:len(units(e[0])))[0])
    zh = units(max(stream.load_zh()[0],key=lambda e:len(units(e[0])))[0])
    insertion='these eleven injected unheard words belong exclusively to this omitted passage'
    han=''.join(u for u in zh if len(u)==1)[:169]
    cases=[('solid-omits22',' '.join(en),' '.join(en[:40]+en[62:])),
           ('preview-inserts11',' '.join(en[:40])+' '+insertion+' '+' '.join(en[40:]),' '.join(en)),
           ('preview-inserts169',''.join(zh[:40])+han+''.join(zh[40:]),''.join(zh))]
    report=[]
    for name,old,solid in cases:
        for lane in ('system','microphone'):
            state=reducer(); cuts=[]
            state.publication((G(0,14*S,old,source_lane=lane),),((lane,14*S),))
            cc=(score.eff([0,15*S,solid,lane]),)
            state.advance(cc)
            fresh='Zebras gallop quietly while fresh speakers discuss entirely novel matters today'
            raw=old+' '+fresh;origin=G(0,20*S,raw,source_lane=lane);row=G(15*S,20*S,raw,source_lane=lane)
            state.publication((origin,),((lane,20*S),))
            tc=state.cuts((row,),(origin,));baseline=rt._trim_committed_preview((row,),cc,cuts)
            shown=apply((row,),baseline,tc)
            assert ' '.join(r.text for r in shown)==fresh
            report.append(dict(case=name,lane=lane,snapshot_cut=tc[0],repeated_residue_units=0,
                               repeated_residue_seconds=0,fresh_time_loss=0,shown=[r.text for r in shown],
                               state=snapshot_state(state)))
    (EV/f'injections-{MODE}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return [{k:v for k,v in r.items() if k not in ('state','shown')} for r in report]


def main():
    global MODE
    parser=argparse.ArgumentParser();parser.add_argument('--product',action='store_true');args=parser.parse_args()
    MODE='product' if args.product else 'prototype'
    reducer=rt._PreviewSnapshots if args.product else candidate.PreviewSnapshots
    apply=rt._apply_preview_time_cuts if args.product else candidate.apply_time_cuts
    EV.mkdir(parents=True,exist_ok=True)
    report=dict(controls=controls(reducer,apply),injections=injections(reducer,apply),streams={
        'zh-188s':run_stream('zh-188s',stream.load_zh,'zh-long-trim-base.jsonl',reducer,apply),
        'en-302s':run_stream('en-302s',stream.load_e1,'e1-en-trim-base.jsonl',reducer,apply)})
    assert all(r['time_additions_outside_snapshot']==0 and r['same_gate_mismatches']==0 and
               r['overflows']==0 and r['added_mean_ms']<=1 for r in report['streams'].values())
    (EV/f'core-{MODE}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
