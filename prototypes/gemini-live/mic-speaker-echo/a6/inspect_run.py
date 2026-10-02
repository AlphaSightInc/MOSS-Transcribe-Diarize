"""Throwaway offline diagnosis; reads public stress snapshots, never calls a provider."""
import difflib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from moss_transcribe_diarize.app import gemini_live_runtime as rt
BASE=Path.home()/'Documents/Codex/2026-09-28/moss-gemini/evidence/P73/r5b-stress'

def units(t):return [u for u,_,_ in rt._preview_units(t)]
def load(sub):
    solid=[];out=[]
    for line in (BASE/sub/'snapshots.jsonl').read_text().splitlines():
        x=json.loads(line)
        if x['effective'] is not None:solid=x['effective']
        x['solid']=solid
        out.append(x)
    return out

def probe(text,solid):
    raw=units(text);limit=max(60,len(raw)*5//4+8)
    tail=units(' '.join(r['text'] for r in solid if r.get('source_lane')=='system'))[-limit:]
    blocks=[b for b in difflib.SequenceMatcher(None,tail,raw,autojunk=False).get_matching_blocks() if b.size]
    return {'raw_units':len(raw),'solid_units':len(tail),'cut':rt._repeated_head(tail,raw),'head':raw[:30],
            'blocks':[dict(a=b.a,b=b.b,size=b.size,units=raw[b.b:b.b+min(b.size,8)]) for b in blocks],
            'gaps':[dict(shown=b.a-(a.a+a.size),preview=b.b-(a.b+a.size)) for a,b in zip(blocks,blocks[1:])]}

def main():
    out={}
    for sub in ['runs-recheck/c6s','runs/c6']:
        xs=load(sub);events=[];was=0
        for x in xs:
            if x['status']!='active':continue
            grey=[r for r in (x.get('provisional') or {}).get('segments',[]) if r['source_lane']=='system']
            text=' '.join(r['text'] for r in grey)
            repeat=sum(b.size for b in difflib.SequenceMatcher(None,units(' '.join(r['text'] for r in x['solid'] if r.get('source_lane')=='system')),units(text),autojunk=False).get_matching_blocks() if b.size>=5)
            if repeat>=100 and was<100:
                events.append(dict(e=x['e'],repeat=repeat,grey_units=len(units(text)),rows=[dict(start=r['start_sample'],end=r['end_sample'],head=r['text'][:90]) for r in grey]))
            was=repeat
        out[sub]={'long_repeat_onsets':events,'audio':json.loads((BASE/sub/'receipt.json').read_text())['audio']}
        if events:
            first=next(x for x in xs if x['e']==events[0]['e'])
            row=next(r for r in first['provisional']['segments'] if r['source_lane']=='system')
            out[sub]['first_exposed_head_probe']=probe(row['text'],first['solid'])
    xs=load('runs-recheck/c6s')
    before=next(x for x in xs if x['e']==254.45);after=next(x for x in xs if x['e']==255.1)
    exposed=after['provisional']['segments'][0]['text']
    out['jump']={'solid_identical':before['solid']==after['solid'],
       'before':{'e':before['e'],'preview':before['preview'],'shown':before['provisional']['segments']},
       'after':{'e':after['e'],'preview':after['preview'],'shown':after['provisional']['segments']},
       'probe_shown':probe(exposed,after['solid']),
       'probe_inferred_raw':probe('been '+exposed,after['solid'])}
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
