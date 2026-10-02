"""Frozen product/prototype parity; includes actual publication-path stream replays."""
import json,sys,inspect,time,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent/'f1')]
import candidate,score,stream,degraded
from measure import ROOT,EV,load_stress,measure
rt=candidate.rt
PRODUCT=rt._trim_committed_preview

def factory(product):
    if not product:return candidate.RememberedTrim().trim
    state=[]
    return lambda segments,committed:PRODUCT(segments,committed,state)

def captured():
    files=sorted((ROOT/'P72/f1/runs').glob('*-base*/trim.jsonl'))+sorted((ROOT/'P72/f1/runs').glob('*-trim-base.jsonl'))
    report={};total=0
    for path in files:
        calls=[json.loads(x) for x in path.read_text().splitlines()];total+=len(calls)
        proto=factory(False);prod=factory(True);same=unchanged=0
        for c in calls:
            ss=tuple(score.seg(r) for r in c['segments']);cc=tuple(score.eff(r) for r in c['committed'])
            output=prod(ss,cc);assert output==proto(ss,cc)
            same+=1;unchanged+=output==PRODUCT(ss,cc)
        label=path.parent.name if path.name=='trim.jsonl' else path.stem
        stat={}
        for name in ('prototype','product'):
            score.arms.ARMS['a2']=factory(name=='product')
            stat[name]=score.offline(calls,['a2'])['a2']
        report[label]=dict(calls=len(calls),exact_parity=same,baseline_unchanged=unchanged,metrics=stat)
        print(label,len(calls),same,unchanged,flush=True)
    return dict(total=total,cells=report)

def streams():
    # Extend F1 replay's capture callback to receive product state; its publication
    # and audio/turn bookkeeping stay unchanged. No monkeypatched candidate copy.
    source=inspect.getsource(stream.replay).replace('def trim(segments, committed):','def trim(segments, committed, *args, **kwargs):').replace('kept = arm(segments, committed)','kept = arm(segments, committed, *args, **kwargs)')
    scope=dict(stream.__dict__);exec(source,scope);replay=scope['replay']
    result={}
    for name,loader in [('zh-188s',stream.load_zh),('en-302s',stream.load_e1),('r5d-cell',stream.load_cell)]:
        events,commits,total=loader();runs={}
        for mode in ('baseline','prototype','product'):
            proto=candidate.RememberedTrim()
            arm=(lambda s,c,*a,**k:PRODUCT(s,c)) if mode=='baseline' else ((lambda s,c,*a,**k:proto.trim(s,c)) if mode=='prototype' else PRODUCT)
            calls,snaps=replay(events,commits,total,arm)
            runs[mode]=(calls,score.snapshot_score(snaps))
            (EV/f'{name}-{mode}.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in calls))
        assert runs['prototype'][0]==runs['product'][0]
        assert runs['baseline'][0]==runs['product'][0]
        result[name]={mode:dict(calls=len(c),snapshots=stat) for mode,(c,stat) in runs.items()}
        print(name,{mode:stat['snapshots'] for mode,stat in result[name].items()},flush=True)
    rt._trim_committed_preview=PRODUCT
    return result

def main():
    report={'captured':captured(),'streams':streams(),'stress':{},'degraded':{}}
    for cell in ('c2','c4','c5b','c6'):
        calls=load_stress(cell);proto=factory(False);prod=factory(True)
        for c in calls:
            s=tuple(score.seg(r) for r in c['segments']);cc=tuple(score.eff(r) for r in c['committed']);assert proto(s,cc)==prod(s,cc)
        report['stress'][cell]={name:measure(calls,factory(name=='product'))[0] for name in ('prototype','product')}
        print(cell,report['stress'][cell],flush=True)
    for mode in ('baseline','prototype','product'):
        stat,states=degraded.run(product=mode=='product',baseline=mode=='baseline');report['degraded'][mode]=stat
        if mode=='product':(EV/'degraded-product.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in states))
    # The independently measured helper must reproduce the production commit placement.
    assert report['degraded']['prototype']==report['degraded']['product']
    (EV/'product-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('TOTAL',report['captured']['total'],'PARITY PASS',report['degraded'],flush=True)
if __name__=='__main__':main()
