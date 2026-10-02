"""Qualify remembered cuts against F1 frozen captured inputs and adverse sequences."""
import json,sys,time,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent/'f1')]
import candidate,score,trim
from measure import ROOT,EV,load_stress,measure
rt=candidate.rt
G=rt.GeminiSegment

def adverse():
    # Frozen known boundaries: only old prefixes may disappear. Every test prints state.
    solid='one settled introduction about the previous meeting'
    tail='this next clause contains new speech and must remain'
    rows=(G(0,100,solid,source_lane='system'),)
    cases=[]
    for mode in ('local','latest','progress','remembered'):
        arm=candidate.RememberedTrim() if mode=='remembered' else candidate.Trim(mode)
        apply=arm.trim if mode=='remembered' else arm
        base=apply((G(100,150,solid+' '+tail,source_lane='system'),),rows)
        # Gap after a proven prefix: not previously cut tail must stay, including novel intervening words.
        rewritten=solid+' rewritten unheard clause with entirely different words '+tail
        out=apply((G(100,170,rewritten,source_lane='system'),),rows)
        cases.append(dict(mode=mode,case='grown-prefix',shown=[r.text for r in out],state=str(getattr(arm,'cuts',getattr(arm,'previous',[])))))
        # Fresh turn beginning exactly like old speech: nonoverlap resets remembered evidence.
        out=apply((G(180,220,solid+' '+tail,source_lane='system'),),())
        cases.append(dict(mode=mode,case='restart-no-solid',shown=[r.text for r in out],fresh_preserved=out[0].text==solid+' '+tail))
    # Anchor middle matches would swallow fresh intervening words/chorus even with a matching head.
    committed=solid+' older overlapping words returned only by the rolling model while other people speak an entirely different topic for this long window then finish with a chorus now'
    fresh='fresh unrevised speech has never been committed and this completely different lengthy passage belongs to the new chorus occurrence today'
    raw=solid+' '+fresh+' then finish with a chorus now'
    for mode in ('local','latest','split','progress','remembered'):
        arm=candidate.RememberedTrim() if mode=='remembered' else candidate.Trim(mode)
        out=(arm.trim if mode=='remembered' else arm)((G(100,180,raw,source_lane='system'),),(G(0,100,committed,source_lane='system'),))
        cases.append(dict(mode=mode,case='fresh-middle-before-repeated-chorus',shown=[r.text for r in out],fresh_preserved=bool(out and fresh in out[0].text)))
    # Time proportion can cut new speech: most duration before frontier but omitted prefix is tiny.
    cases.append(dict(mode='proportional',case='untimed-text',raw='old '+fresh,frontier_fraction=.9,cut_units=int(.9*len(score.units('old '+fresh))),fresh_units_hidden=max(0,int(.9*len(score.units('old '+fresh)))-1)))
    return cases

def main():
    report={'adversarial':adverse(),'f1':{},'stress':{}}
    files=sorted((ROOT/'P72/f1/runs').glob('*-base*/trim.jsonl'))+sorted((ROOT/'P72/f1/runs').glob('*-trim-base.jsonl'))
    for path in files:
        calls=[json.loads(x) for x in path.read_text().splitlines()]
        arm=candidate.RememberedTrim()
        name=path.parent.name if path.name=='trim.jsonl' else path.stem
        score.arms.ARMS['remembered']=arm.trim
        score.arms.ARMS['current']=candidate.BASE
        report['f1'][name]=score.offline(calls,['current','remembered'])
        print(name,{k:{x:v[x] for x in ('repeated_unit_polls','reshown_units','calls_differ_from_base','us_mean')} for k,v in report['f1'][name].items()},flush=True)
    for cell in ('c2','c4','c5b','c6'):
        calls=load_stress(cell);arm=candidate.RememberedTrim()
        report['stress'][cell]={'baseline':measure(calls,candidate.BASE)[0],'remembered':measure(calls,arm.trim)[0]}
    (EV/'qualification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report['adversarial'],ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
