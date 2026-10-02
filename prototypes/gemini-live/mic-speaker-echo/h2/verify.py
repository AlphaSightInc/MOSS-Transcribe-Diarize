"""Compare frozen engine surfaces to C2 and H2 prototype; failures block completion."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
EV=Path.home()/'Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-H2'
mode='product' if '--product' in sys.argv else 'prototype'
current=EV/mode
baselines={'C2':EV.parent/'R5B-C2/product'}
if mode=='product':baselines['H2prototype']=EV/'prototype'
jobs=json.loads((current/'engine-matrix.json').read_text())
results=[]
for tag,base in baselines.items():
    differences=[];restore_changes=[]
    for job in jobs:
        own=current/'runs'/job['out'];prior=base/'runs'/job['out']
        receipt=json.loads((own/'receipt.json').read_text())
        assert receipt['cost_usd']==0 and all(c['replayed'] for c in receipt['batch_calls'])
        a=json.loads((own/'terminal.json').read_text());b=json.loads((prior/'terminal.json').read_text())
        for lane in set(a)|set(b):
            for key in ['final_words','restored','restored_words']:
                if a.get(lane,{}).get(key)!=b.get(lane,{}).get(key):
                    difference={'cell':job['out'],'lane':lane,'surface':key,'before':b.get(lane,{}).get(key),'after':a.get(lane,{}).get(key)}
                    differences.append(difference)
                    if key=='restored':restore_changes.append(difference)
        for name in ['saved-meeting-before-stop.json','saved-meeting-live.json','saved-meeting.json']:
            fields=['text','start','end','speaker','speaker_entity_id','source_lane']
            def surface(p):return [{k:r.get(k) for k in fields} for r in json.loads((p/name).read_text())['transcript']['segments']]
            if surface(own)!=surface(prior):differences.append({'cell':job['out'],'surface':name,'before':surface(prior),'after':surface(own)})
        for lane in set(a)|set(b):
            if a.get(lane,{}).get('before_rule')!=b.get(lane,{}).get('before_rule'):differences.append({'cell':job['out'],'lane':lane,'surface':'kept clean-up changed'})
    results.append({'baseline':tag,'cells':len(jobs),'differences':differences,'restored_words_changes':restore_changes})
result={'mode':mode,'comparisons':results,'provider_usd':0}
(EV/(mode+'-parity.json')).write_text(json.dumps(result,ensure_ascii=False,indent=1)+'\n')
print(json.dumps({'mode':mode,'comparisons':[{k:v for k,v in r.items() if k not in ('differences','restored_words_changes')}|{'difference_count':len(r['differences']),'changed_restore_count':len(r['restored_words_changes'])} for r in results]}))
assert len(jobs)==127 and not any(r['differences'] for r in results)
