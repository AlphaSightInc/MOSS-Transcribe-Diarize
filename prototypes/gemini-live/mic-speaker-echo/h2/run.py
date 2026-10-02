"""$0 candidate/product matrix, full state in H2 evidence. Never writes source receipts."""
import json
import sys
from pathlib import Path
from functools import partial
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path[:0]=[str(ROOT),str(HERE),str(HERE.parent/'f3')]
from moss_transcribe_diarize.app import gemini_coverage as coverage
from moss_transcribe_diarize.app.gemini_provider import GeminiWord as Word
import s2_witness as matrix
S=16000
EV=Path.home()/'Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-H2'
sys.path.insert(0,str(EV))
import candidate
PRODUCT=coverage.uncovered_runs
BASE=EV.parent/'R5B-C2/product'
F3EV=EV.parent/'P72/f3'

def w(text,a,b,label='live'):
    return Word(text,label,round(a*S),round(b*S))

def patterns():
    # RECONSTRUCTIONS: text is exported; per-word clocks and pre-H clean-up are injected.
    return {
      'c7-after':([w('Who',41,41.2),w('got',41.7,41.8),w('the',41.8,41.9),w('truth?',41.9,42.1)], [w('got',41.2,41.4),w('the',41.4,41.6)]),
      'c7-before':([w('Who',41,41.1),w('got',41.1,41.3),w('the',41.3,41.5),w('truth?',41.9,42.1)], [w('got',41.6,41.7),w('the',41.7,41.9)]),
      'c5b-grouped':([w('产品规划。',270,270.2),w('大家好',270.8,271)], [w('规',270.400375,270.6),w('划。',270.6,270.8)]),
      'distant-name':([w('Media',1,1.2),w('Lab',1.2,1.4),w('then',1.4,1.6),w('visited',2.2,2.4),w('today',3.2,3.4)], [w('Media',2.5,2.7),w('Lab',2.7,2.9)]),
      'repeat-yes':([w('yes',1,1.2),w('next',2.2,2.4)], [w('yes',1.4,1.7)]),
      'repeat-phrase':([w('thank',1,1.2),w('you',1.2,1.4),w('next',2.2,2.4)], [w('thank',1.6,1.8),w('you',1.8,2)]),
      'repeat-yes-yes':([w('yes yes',1,1.4),w('next',2.5,2.7)], [w('yes',1.6,1.8),w('yes',1.8,2)]),
      'repeat-chinese':([w('对对对',1,1.4),w('next',2.5,2.7)], [w('对',1.6,1.8),w('对',1.8,2),w('对',2,2.2)]),
      'stutter-live':([w('and',37.3,37.5),w('next',39,39.2)], [w('uh',37.5,37.5),w('I',38,38.2),w('I',38.2,38.2)]),
      'mixed-edge':([w('thank',1,1.2),w('you',1.2,1.4),w('next',2.5,2.7)], [w('thank',1.6,1.8),w('you',1.8,2),w('Cosette',2,2.3)]),
    }

def state(words):return [[w.text,w.speaker,w.start_sample,w.end_sample] for w in words]

def evaluate(discover):
    coverage.uncovered_runs=discover
    pairs=[]
    for prefix,name in matrix.LIVE.items():
        raw=json.loads((F3EV/'runs'/name/'witness.json').read_text())['system']
        live=coverage.one_owner([Word(*w[:4]) for w in raw],[w[4] for w in raw])
        live_units=matrix.zh_units(live,prefix)
        for draw,other_prefix,path in matrix.draws():
            kept=[Word(w.text,w.speaker,w.start_sample,w.end_sample) for w in matrix.shifted(path,prefix-other_prefix)]
            before=matrix.zh_units(kept,prefix)
            need={t:min(matrix.NAMES.count(t),max(live_units.count(t),before.count(t))) for t in set(matrix.NAMES)}
            filled,restored=coverage.restore_system_witnessed_words(kept,live)
            after=matrix.zh_units(sorted(filled,key=lambda w:(w.start_sample,w.end_sample)),prefix)
            pairs.append({'live':name,'draw':draw,'lost':sum(max(0,c-after.count(t)) for t,c in need.items()),'missing_extra':matrix.against_truth(after),'stutters':matrix.stutters(after),'restored':restored,'output':state(filled)})
    archived=[]
    for job in json.loads((BASE/'engine-matrix.json').read_text()):
        folder=BASE/'runs'/job['out']
        logs=json.loads((folder/'terminal.json').read_text())
        witnesses=json.loads((folder/'witness.json').read_text())
        for lane,log in logs.items():
            kept=[Word(*w[:4]) for w in log.get('before_rule',[])]
            # Engine witness export records live custody; inspect schema before interpreting.
            raw=witnesses.get(lane,[])
            live=coverage.one_owner([Word(*w[:4]) for w in raw],[w[4] for w in raw])
            runs=discover(kept,live,skip=log.get('coverage_gaps',[]))
            archived.append({'cell':job['out'],'lane':lane,'runs':[{'words':state(run),'samples':samples} for run,samples in runs]})
    synthetic=[]
    for name,(kept,live) in patterns().items():
        out,restored=coverage.restore_witnessed_words(kept,live)
        synthetic.append({'name':name,'cleanup':state(kept),'witness':state(live),'output':state(out),'restored':restored})
    summary={'pairs':len(pairs),'lost_names':sum(r['lost'] for r in pairs),'doubled':sum(r['stutters'] for r in pairs),'missing_mean':sum(r['missing_extra'][0] for r in pairs)/100,'extra_mean':sum(r['missing_extra'][1] for r in pairs)/100,'archived_cells':127}
    return {'summary':summary,'pairs':pairs,'archived':archived,'synthetic':synthetic}


def main():
    EV.mkdir(exist_ok=True)
    if '--prototype' not in sys.argv:
        baseline=json.loads((EV/'baseline.json').read_text())
    else:
        baseline=evaluate(candidate.ORIGINAL)
        (EV/'baseline.json').write_text(json.dumps(baseline,ensure_ascii=False,indent=1)+'\n')
    modes=['a','b','c'] if '--prototype' in sys.argv else ['product']
    for mode in modes:
        discover=PRODUCT if mode=='product' else partial(candidate.discovery,mode=mode)
        measured=evaluate(discover)
        changes=[{'before':a,'after':b} for a,b in zip(baseline['archived'],measured['archived']) if a!=b]
        measured['changes']=changes
        if mode=='product':
            reference=json.loads((EV/'a.json').read_text())
            recorded=json.loads(json.dumps(measured))
            assert all(recorded[key]==reference[key] for key in ['summary','pairs','archived','synthetic']), 'Product differs from frozen H2a prototype'
        (EV/(mode+'.json')).write_text(json.dumps(measured,ensure_ascii=False,indent=1)+'\n')
        print(mode,json.dumps(measured['summary']), 'changed archived lanes',len(changes),flush=True)
        print('Full state:',EV/(mode+'.json'),flush=True)
        print('synthetic',[(r['name'],[w[0] for w in r['output']],sum(len(x['text']) for x in r['restored'])) for r in measured['synthetic']],flush=True)
    if '--prototype' in sys.argv:
        margin=[]
        for seconds in [.1,.25,.5,1,2]:
            for limit in [2,4,8,12]:
                coverage.uncovered_runs=partial(candidate.discovery,mode='a',seconds=seconds,limit=limit)
                row={'seconds':seconds,'limit':limit,'restored':{}}
                for name,(kept,live) in patterns().items():
                    row['restored'][name]=sum(len(r['text']) for r in coverage.restore_witnessed_words(kept,live)[1])
                margin.append(row)
        (EV/'margin.json').write_text(json.dumps(margin,indent=1)+'\n')
        print('margin',json.dumps(margin),flush=True)
    coverage.uncovered_runs=candidate.ORIGINAL

if __name__=='__main__':main()
