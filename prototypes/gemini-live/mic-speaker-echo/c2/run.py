"""Frozen recorded matrices for S2; $0, full state in own evidence."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
EV = Path.home()/'Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-C2'
FIX3 = EV.parent/'R5B-FIX3'
F3EV = EV.parent/'P72/f3'
sys.path[:0] = [str(ROOT), str(HERE), str(HERE.parent/'f3')]
from moss_transcribe_diarize.app import gemini_coverage as candidate
import s2_witness as matrix
import f3lib
from moss_transcribe_diarize.app import gemini_coverage as production
from moss_transcribe_diarize.app.gemini_provider import GeminiWord as Word
S = 16000


def published(witness, rows):
    out = []
    for w in witness:
        row = max((r for r in rows if r['source_lane']=='system'), key=lambda r:
                  max(0,min(r['end']*S,w.end_sample)-max(r['start']*S,w.start_sample)), default=None)
        overlap = row and min(row['end']*S,w.end_sample)>max(row['start']*S,w.start_sample)
        label = row['speaker'] if overlap else f'unassigned-{w.speaker}'
        if label == 'Speaker TBD': label = f'unassigned-{w.speaker}'
        out.append(Word(w.text,label,w.start_sample,w.end_sample))
    return out


def compare(kept, live):
    before, runs1 = production.restore_witnessed_words(kept, live)
    after, runs2 = candidate.restore_system_witnessed_words(kept, live)
    assert [(w.text,w.start_sample,w.end_sample) for w in before]==[(w.text,w.start_sample,w.end_sample) for w in after]
    assert all(any(w is f for f in after) for w in kept)
    assert sum(len(r['text']) for r in runs1)==sum(len(r['text']) for r in runs2)
    new = [r for r in runs2 if any(s.startswith('witness-') for s in r['speakers'])]
    diffs = [{'text':a.text,'at':a.start_sample/S,'s1':a.speaker,'s2':b.speaker}
             for a,b in zip(before,after) if a.speaker!=b.speaker]
    return after, runs2, new, diffs


def main():
    EV.mkdir(parents=True,exist_ok=True)
    table=[]
    for prefix,name in matrix.LIVE.items():
        raw=json.loads((F3EV/'runs'/name/'witness.json').read_text())['system']
        live=production.one_owner([Word(*w[:4]) for w in raw],[w[4] for w in raw])
        rows=json.loads((F3EV/'runs'/name/'saved-meeting-live.json').read_text())['transcript']['segments']
        live=published(live,rows)
        for draw,other_prefix,path in matrix.draws():
            kept=[Word(w.text,w.speaker,w.start_sample,w.end_sample) for w in matrix.shifted(path,prefix-other_prefix)]
            after,runs,own,diffs=compare(kept,live)
            table.append({'live':name,'draw':draw,'own':own,'differences':diffs,'runs':runs})
    archived=[]
    truth_restores=[]
    truth=json.loads((F3EV/'fixtures/en-k3.truth.json').read_text())['turns']
    for folder in sorted((FIX3/'runs/f3-w0').iterdir()):
        if not (folder/'terminal.json').exists():continue
        log=json.loads((folder/'terminal.json').read_text()).get('system',{})
        if not log.get('before_rule'):continue
        raw=json.loads((folder/'witness.json').read_text())['system']
        live=production.one_owner([Word(*w[:4]) for w in raw],[w[4] for w in raw])
        rows=json.loads((folder/'saved-meeting-live.json').read_text())['transcript']['segments']
        live=published(live,rows)
        kept=[Word(*w) for w in log['before_rule']]
        after,runs,own,diffs=compare(kept,live)
        archived.append({'cell':folder.name,'own':own,'differences':diffs,'runs':runs})
        if folder.name.startswith('en-k3-'):
            prefix=json.loads((folder/'receipt.json').read_text())['args']['prefix']
            label_truth={}
            for w in kept:
                target=max(truth,key=lambda r:max(0,min(w.end_sample/S-prefix,r[1])-max(w.start_sample/S-prefix,r[0])))
                overlap=max(0,min(w.end_sample/S-prefix,target[1])-max(w.start_sample/S-prefix,target[0]))
                label_truth.setdefault(w.speaker,{}).setdefault(target[2],0)
                label_truth[w.speaker][target[2]]+=overlap
            label_truth={k:max(v,key=v.get) for k,v in label_truth.items()}
            before,_=production.restore_witnessed_words(kept,live)
            kept_ids={id(w) for w in kept}
            for a,b in zip(before,after):
                if id(a) in kept_ids:continue
                target=max(truth,key=lambda r:max(0,min(a.end_sample/S-prefix,r[1])-max(a.start_sample/S-prefix,r[0])))
                truth_restores.append({'cell':folder.name,'text':a.text,'truth':target[2],
                    's1':label_truth.get(a.speaker),'s2':label_truth.get(b.speaker),
                    's1_correct':label_truth.get(a.speaker)==target[2],'s2_correct':label_truth.get(b.speaker)==target[2]})
    # Live identity conflates two voices; nearest final word follows the clean-up split.
    kept=[Word('a','final-a',S,2*S),Word('b','final-b',10*S,11*S)]
    live=[Word('a','published-wrong',S,2*S),Word('reply','published-wrong',9*S,9*S+4000),Word('b','published-wrong',10*S,11*S)]
    wrong,_,own,_=compare(kept,live)
    assert [w.speaker for w in wrong if w.text=='reply']==['final-b'] and not own
    # A third speaker whose entire turn is omitted: own label, never neighbouring labels.
    injected=[Word('Welcome','published-ben',52*S,53*S),Word('Ben','published-ben',67*S,68*S)]
    kept=[Word('jingle','singer',50*S,51*S),Word('next','host',69*S,70*S)]
    output,runs,own,diffs=compare(kept,injected)
    assert {w.speaker for w in output if w.text in ('Welcome','Ben')}=={'witness-published-ben'}
    # Cost: production H plus bridge, two-hour word population.
    kept=[Word(str(i),'terminal-1',i*3200,i*3200+2400) for i in range(36000) if i%300!=150]
    live=[Word(str(i),'speaker-1',i*3200,i*3200+2400) for i in range(36000)]
    start=time.perf_counter();production.restore_witnessed_words(kept,live);s1=time.perf_counter()-start
    start=time.perf_counter();candidate.restore_system_witnessed_words(kept,live);s2=time.perf_counter()-start
    summary={'pairs':len(table),'pair_own_runs':sum(len(r['own']) for r in table),
        'archived_cells':len(archived),'archived_own_runs':sum(len(r['own']) for r in archived),
        'truth_restores':truth_restores,'cell2_shape':'PASS; see product-extended.json for recorded-answer injection',
        'wrong_live_split':'nearest kept final-b; no new label','cost_s':{'s1':s1,'s2':s2,'added':s2-s1},'provider_cost_usd':0}
    assert len(table)==100 and not any(r['s1_correct'] and not r['s2_correct'] for r in truth_restores)
    print("cost", s1, s2, s2-s1)
    assert s2-s1<1
    (EV/'product-matrix.json').write_text(json.dumps({'summary':summary,'pairs':table,'archived':archived},ensure_ascii=False,indent=1)+'\n')
    print(json.dumps({'summary':summary,'pairs':table,'archived':archived},ensure_ascii=False,indent=1))

if __name__=='__main__':
    main()
    from extended import run
    run()
