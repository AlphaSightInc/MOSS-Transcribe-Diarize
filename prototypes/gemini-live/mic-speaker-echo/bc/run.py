"""One-command BC replay. No provider/key access; all source evidence read-only, own receipts only."""
from __future__ import annotations
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import compose
from compose import rule, S
import f3lib
import cells
import s2_witness as witness_matrix
import s6_patterns

HERE = Path(__file__).resolve().parent
EV = Path.home()/'Documents/Codex/2026-09-28/moss-gemini/evidence/P72/bc'
F2EV = EV.parent/'f2'
F3EV = EV.parent/'f3'
ENV = {**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'}
STATUS = EV.parents[2]/'status/R5B-C-STATUS.md'


def status(stage, text):
    STATUS.write_text(f'Stage: {stage}\n\nPhase 1 only; gemini/r5-f3. $0; production unchanged.\n{text}\n')


def rows_of(folder, name='saved-meeting.json'):
    return json.loads((folder/name).read_text())['transcript']['segments']


def microphone_score(rows, truth, prefix):
    mine=[r for r in rows if r['source_lane']=='microphone']
    tab=[r for r in rows if r['source_lane']=='system']
    matched=spoken=echo_inside=0
    claimed=set()
    for phrase in truth:
        lo,hi=phrase['start']+prefix-.7,phrase['end']+prefix+.7
        found=[r for r in mine if r['start']<hi and r['end']>lo]
        claimed.update(id(r) for r in found)
        want=cells.units(phrase['text'])
        heard=[u for r in found for u in cells.units(r['text'])]
        matched+=cells.lcs(want,heard)
        spoken+=len(want)
        tab_units={u for r in tab if r['start']<hi+2 and r['end']>lo-2 for u in cells.units(r['text'])}
        left=list(heard)
        for u in want:
            if u in left: left.remove(u)
        echo_inside+=sum(u in tab_units for u in left)
    return {'recall':f'{matched}/{spoken}', 'extra_units':max(0,sum(len(cells.units(r['text'])) for r in mine)-matched),
            'outside_units':sum(len(cells.units(r['text'])) for r in mine if id(r) not in claimed),
            'echo_inside_units':echo_inside}


def jobs():
    result=[]
    # Every original H engine cell, reconstructed from its own receipt (no cached evaluation).
    for path in sorted((F3EV/'runs').glob('*/receipt.json')):
        original=json.loads(path.read_text())
        if original['args'].get('rule') != .15: continue
        args=original['args']
        for w in (False,True):
            out=f'f3-w{int(w)}/{path.parent.name}'
            command=[sys.executable,str(HERE/'engine.py'),out,args['system_wav']]
            if args.get('mic_wav'): command.append(args['mic_wav'])
            if args['silent_mic']: command.append('--silent-mic')
            command+=['--prefix',str(args['prefix']),'--rule','.15','--quiet']
            for key in ('donor','terminal_from','shift','drop','chunk','overlap'):
                if args.get(key) is not None:
                    command+=['--'+key.replace('_','-'),str(args[key])]
            if w: command.append('--w')
            result.append({'family':'f3','cell':path.parent.name,'w':w,'out':out,'command':command,
                           'prototype':str(path.parent),'prefix':args['prefix']})
    matrix=json.loads((F2EV/'runs/matrix-final.json').read_text())
    for row in matrix['rows']:
        original=json.loads((F2EV/'runs/final'/row['cell']/'receipt.json').read_text())
        for w in (False,True):
            out=f'f2-w{int(w)}/{row["cell"]}'
            command=[sys.executable,str(HERE/'engine.py'),out,original['system_wav'],original['mic_wav'],
                     '--prefix',str(original['prefix_s']),'--rule','.15','--quiet']
            if original['answers'].startswith('rp-'): command+=['--donor',original['answers']]
            if w: command.append('--w')
            result.append({'family':'f2','cell':row['cell'],'w':w,'out':out,'command':command,
                           'prototype_scores':row['candidate'],'prefix':original['prefix_s'],
                           'mic_wav':original['mic_wav']})
    # F2 vlong is a recorded nineteenth engine cell, scored by returned words rather than unknown verbatim truth.
    original=json.loads((F2EV/'runs/final/vlong-e40-L37/receipt.json').read_text())
    for w in (False,True):
        out=f'f2-w{int(w)}/vlong-e40-L37'
        command=[sys.executable,str(HERE/'engine.py'),out,original['system_wav'],original['mic_wav'],'--rule','.15','--quiet']
        if w: command.append('--w')
        result.append({'family':'vlong','cell':'vlong-e40-L37','w':w,'out':out,'command':command,
                       'prefix':3.,'prototype':str(F2EV/'runs/final/vlong-e40-L37')})
    return result


def one(job):
    folder=EV/'runs'/job['out']
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/'process.log').open('w') as log:
        result=subprocess.run(job['command'],env=ENV,stdout=log,stderr=log)
    if result.returncode:
        return {**job,'error':(folder/'process.log').read_text()[-4000:]}
    receipt=json.loads((folder/'receipt.json').read_text())
    assert receipt['finalization_status']=='final' and all(c['replayed'] for c in receipt['batch_calls']), receipt
    return {k:v for k,v in job.items() if k!='command'}


def score(job):
    folder=EV/'runs'/job['out']
    terminal=json.loads((folder/'terminal.json').read_text())
    out={k:v for k,v in job.items() if k not in ('prototype_scores',)}
    out['lanes']={}
    if job['family']=='f3':
        original=Path(job['prototype'])
        before=json.loads((original/'terminal.json').read_text())
        for lane,log in terminal.items():
            text=' '.join(r['text'] for r in rows_of(folder) if r['source_lane']==lane)
            proto_text=' '.join(r['text'] for r in rows_of(original) if r['source_lane']==lane)
            words=log.get('final_words',[])
            old_words=before.get(lane,{}).get('final_words',[])
            own=[(w[0],w[2],w[3]) for w in words]
            proto=[(w[0],w[2],w[3]) for w in old_words]
            missing=[w for w in proto if w not in own]
            # C counts preserved text/times independent of W's intentional label changes.
            out['lanes'][lane]={'prototype_units':len(f3lib.units(proto_text)), 'bc_units':len(f3lib.units(text)),
                                'prototype_repeated':f3lib.repeated_units(proto_text), 'bc_repeated':f3lib.repeated_units(text),
                                'missing_prototype_words':missing, 'restored_words':log.get('restored_words',0)}
    elif job['family']=='f2':
        truth=cells.truth_of(job['mic_wav'])
        stages={'live_solid':'saved-meeting-before-stop.json','saved_at_stop':'saved-meeting-live.json','saved':'saved-meeting.json'}
        out['scores']={key:microphone_score(rows_of(folder,name),truth,job['prefix']) for key,name in stages.items()}
        out['prototype_scores']={key:job['prototype_scores'][key] for key in stages}
        out['regressions']=[]
        for key in stages:
            own,proto=out['scores'][key],job['prototype_scores'][key]
            if int(own['recall'].split('/')[0])<int(proto['recall'].split('/')[0]): out['regressions'].append(key+' recall')
            if own['outside_units']+own['echo_inside_units']>proto['outside_units']+proto['echo_inside_units']:
                out['regressions'].append(key+' invented/echo')
    else:
        out['words_on_page']={name:sum(len(r['text'].split()) for r in rows_of(folder,name) if r['source_lane']=='microphone')
                              for name in ('saved-meeting-before-stop.json','saved-meeting-live.json','saved-meeting.json')}
    out['mic_admission']=[(w[0],w[2],w[3]) for w in terminal.get('microphone',{}).get('final_words',[])]
    out['w_executed']='w_state' in terminal.get('system',{})
    return out


def pure_matrix():
    rows=[]
    for name,expect,fn in s6_patterns.CASES:
        text,restored,words=fn()
        assert text==expect,(name,text,expect)
        rows.append({'case':name,'expected':expect,'actual':text,'restored':restored})
    (EV/'h-patterns.json').write_text(json.dumps(rows,ensure_ascii=False,indent=1)+'\n')
    table=[]
    for prefix,name in witness_matrix.LIVE.items():
        raw=json.loads((F3EV/'runs'/name/'witness.json').read_text())['system']
        witness=rule.one_owner([rule.Word(*w[:4]) for w in raw],[w[4] for w in raw])
        live_units=witness_matrix.zh_units(witness,prefix)
        for draw,other_prefix,path in witness_matrix.draws():
            words=witness_matrix.shifted(path,prefix-other_prefix)
            before=witness_matrix.zh_units(words,prefix)
            need={t:min(witness_matrix.NAMES.count(t),max(live_units.count(t),before.count(t))) for t in set(witness_matrix.NAMES)}
            for w in (False,True):
                # Pure omission selection is label-independent: execute frozen W output separately in the engine matrix.
                filled,restored=rule.fill_holes(words,witness)
                after=witness_matrix.zh_units(sorted(filled,key=lambda x:(x.start_sample,x.end_sample)),prefix)
                table.append({'live':name,'draw':draw,'w':w,'lost':sum(max(0,c-after.count(t)) for t,c in need.items()),
                              'missing_extra':witness_matrix.against_truth(after),'stutters':witness_matrix.stutters(after),
                              'restored':restored})
    (EV/'h-pairs.json').write_text(json.dumps(table,ensure_ascii=False,indent=1)+'\n')
    for w in (False,True):
        mine=[r for r in table if r['w']==w]
        assert len(mine)==100 and sum(r['lost'] for r in mine)==4
        assert sum(r['stutters'] for r in mine)==0
    print('H patterns:',len(rows),'H pairs:',len(table),'lost names: 4/100 per W state',flush=True)


def main():
    EV.mkdir(parents=True,exist_ok=True)
    status('BC PROBES','Contract dc64c7d7; naive 6/31 eligible 0, isolated 6/6 at -10/-20 dB. Measuring B and recorded matrices.')
    result=subprocess.run([sys.executable,str(HERE/'probes.py')],env=ENV,stdout=(EV/'probes.log').open('w'),stderr=subprocess.STDOUT)
    assert result.returncode==0,(EV/'probes.log').read_text()[-4000:]
    pure_matrix()
    work=jobs()
    (EV/'population.json').write_text(json.dumps(work,ensure_ascii=False,indent=1)+'\n')
    status('BC RECORDED MATRIX',f'A/B probes pass; frozen population {len(work)} fresh engine replays, W off/on. H 100 pairs: 4 lost names, 0 doubled, 15 patterns pass. All receipts own evidence/P72/bc.')
    results=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for job in pool.map(one,work):
            if 'error' in job:
                print('ERROR',job['out'],job['error'],flush=True)
                results.append(job)
            else:
                measured=score(job)
                results.append(measured)
                print(json.dumps({k:v for k,v in measured.items() if k not in ('mic_admission','prototype_scores')},ensure_ascii=False),flush=True)
            (EV/'engine-matrix.json').write_text(json.dumps(results,ensure_ascii=False,indent=1)+'\n')
            if len(results)%6==0:
                status('BC RECORDED MATRIX',f'{len(results)}/{len(work)} engine replays scored; errors {sum("error" in r for r in results)}. A/B probes pass; receipts evidence/P72/bc. Phase 2 not started.')
    pairs={}
    for row in results:
        pairs.setdefault((row['family'],row['cell']),{})[row['w']]=row
    differences=[str(key) for key,p in pairs.items() if any('error' in r for r in p.values()) or p[False]['mic_admission']!=p[True]['mic_admission']]
    regressions=[r['out'] for r in results if r.get('regressions') or any(v['missing_prototype_words'] or v['bc_repeated']>v['prototype_repeated'] for v in r.get('lanes',{}).values())]
    summary={'engine_replays':len(results),'errors':sum('error' in r for r in results),
             'w_admission_differences':differences,'regressions':regressions,
             'w_system_executions':sum(r.get('w_executed',False) for r in results),'cost_usd':0}
    (EV/'summary.json').write_text(json.dumps(summary,indent=1)+'\n')
    print(json.dumps(summary),flush=True)

if __name__=='__main__':
    main()
    for script in ('negative.py','injected_engine.py','sweep.py','repair_replay.py','validate.py'):
        print('BC step:',script,flush=True)
        subprocess.run([sys.executable,str(HERE/script)],env=ENV,check=True)
    verdict=json.loads((EV/'verdict.json').read_text())
    assert verdict['verdict']=='PASS',verdict
    status('BC MEASURED', 'All required measurements exercised; verdict PASS. See evidence/P72/bc/verdict.json. Phase 2 requires lead GO. Prototype-only; full report in bc/NOTES.md.')
