"""Known-clock counterfactual using recorded unit sequences, separate from real streams."""
import json
from pathlib import Path
from run import units, shown_after, Floor, GAP24, HEAD, rt, stream, EV, S

def main():
    en=units(max(stream.load_e1()[0],key=lambda e:len(units(e[0])))[0])
    zh=units(max(stream.load_zh()[0],key=lambda e:len(units(e[0])))[0])
    old=en[:60];fresh=zh[:20]
    assert not set(old)&set(fresh)
    state=rt._PreviewSnapshots();memory=[];floor=Floor()
    origin=rt.GeminiSegment(0,14*S,' '.join(old),source_lane='system')
    state.publication((origin,),(('system',14*S),))
    solid=(rt.EffectiveTranscriptSegment(0,15*S,' '.join(old),None,'rolling','system'),)
    state.advance(solid)
    row=rt.GeminiSegment(15*S,16*S,' '.join(old),source_lane='system')
    baseline=rt._trim_committed_preview((row,),solid,memory)
    priorcut=60-len(units(baseline[0].text)) if baseline else 60
    floor.apply([dict(key=('system',0),lane='system',raw_count=60,base_cut=priorcut)],{'system':15*S})
    raw=' '.join(old[15:]+fresh)
    origin=rt.GeminiSegment(0,20*S,raw,source_lane='system')
    row=rt.GeminiSegment(15*S,20*S,raw,source_lane='system')
    state.publication((origin,),(('system',20*S),))
    tc=state.cuts((row,),(origin,))
    report=dict(scope='known-clock rewrite composition, not a recorded meeting',old=old,deleted=old[:15],fresh=fresh,
                raw=raw,key=['system',0],frontier=15*S,clock=20*S,known_fresh_start_unit=45,time_cut=tc)
    for name,head in [('C0',HEAD),('C2',GAP24)]:
        rt._repeated_head=head
        try:shown=rt._apply_preview_time_cuts((row,),rt._trim_committed_preview((row,),solid,list(memory)),tc)
        finally:rt._repeated_head=HEAD
        n=65-len(units(shown[0].text)) if shown else 65
        report[name]=dict(cut=n,fresh_hidden=max(0,n-45),shown=[r.text for r in shown])
    n=floor.apply([dict(key=('system',0),lane='system',raw_count=65,base_cut=report['C0']['cut'])],{'system':15*S})[0]
    report['C1']=dict(cut=n,fresh_hidden=max(0,n-45),shown=shown_after(raw,n),state=list(floor.state.items()))
    (EV/'rewrite-control.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
