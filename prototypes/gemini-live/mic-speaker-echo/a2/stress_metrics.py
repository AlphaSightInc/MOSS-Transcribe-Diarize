"""Stress receipt's bounded-tail metric, without reclassifying old genuine repetitions."""
import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent/'f1')]
from measure import load_stress,EV,ROOT
import candidate,score
rt=candidate.rt

def calculate(calls,arm):
    samples=[]
    for c in calls:
        segments=tuple(score.seg(r) for r in c['segments']);committed=tuple(score.eff(r) for r in c['committed'])
        kept=arm(segments,committed);sample=dict(e=c['at']/16000)
        for lane in ('system','microphone'):
            grey=score.units(''.join(r.text for r in kept if r.source_lane==lane))
            tail=score.units(''.join(r.text for r in [r for r in committed if r.source_lane==lane][-12:]))[-2*max(60,len(grey)*5//4+8):]
            sample[lane]=dict(repeated=score.repeated(grey,tail),fresh=len(grey)-score.repeated(grey,tail))
        samples.append(sample)
    return {lane:dict(repeated_unit_polls=sum(s[lane]['repeated'] for s in samples),max_repeated=max(s[lane]['repeated'] for s in samples),seconds_ge10=round(sum(b['e']-a['e'] for a,b in zip(samples,samples[1:]) if a[lane]['repeated']>=10),1),fresh_unit_polls=sum(s[lane]['fresh'] for s in samples)) for lane in ('system','microphone')}

def main():
    report={}
    for cell in ('c2','c4','c5b','c6'):
        calls=load_stress(cell);cuts=[]
        report[cell]={}
        for name,arm in [('published',lambda s,c:s),('baseline-retrim',rt._trim_committed_preview),('prototype-retrim',candidate.RememberedTrim().trim),('product-retrim',lambda s,c:rt._trim_committed_preview(s,c,cuts))]:
            report[cell][name]=calculate(calls,arm)
        receipt=json.loads((ROOT/f'P73/r5b-stress/runs/{cell}/analysis.json').read_text())['F1_grey_vs_solid']['server_snapshots']
        for lane in ('system','microphone'):
            observed=report[cell]['published'][lane]
            assert observed['max_repeated']==receipt[lane]['worst_repeated_units']
            assert observed['repeated_unit_polls']==receipt[lane]['repeated_unit_polls']
        assert report[cell]['prototype-retrim']==report[cell]['product-retrim']
    (EV/'stress-metrics.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
