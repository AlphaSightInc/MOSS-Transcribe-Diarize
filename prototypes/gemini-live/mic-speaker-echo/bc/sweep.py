"""All 63 frozen F2 level cells × W off/on, fresh whole-engine replay with the original donor answers."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import importlib.util
matrix_spec=importlib.util.spec_from_file_location('bc_matrix',Path(__file__).resolve().parent/'run.py')
matrix=importlib.util.module_from_spec(matrix_spec)
matrix_spec.loader.exec_module(matrix)

EV=matrix.EV
F2EV=matrix.F2EV
HERE=Path(__file__).resolve().parent


def run():
    population=[]
    for cell in json.loads((F2EV/'runs/sweep.json').read_text())['rows']:
        stem=f"{cell['kind']}-e{-int(cell['echo_db'])}-L{-int(cell['local_dbfs'])}--{cell['provider_words_from']}"
        original=json.loads((F2EV/'runs/sweep/cand'/stem/'receipt.json').read_text())
        for w_on in (False,True):
            out=f'sweep-w{int(w_on)}/{stem}'
            command=[sys.executable,str(HERE/'engine.py'),out,original['system_wav'],original['mic_wav'],
                     '--f2','--donor',cell['provider_words_from'],'--rule','.15','--quiet']
            if w_on:command.append('--w')
            population.append({'family':'f2','cell':stem,'w':w_on,'out':out,'command':command,
                               'prototype_scores':{key:{'recall':cell[proto],'outside_units':0,'echo_inside_units':0}
                                  for key,proto in [('live_solid','cand_live'),('saved_at_stop','cand_at_stop'),('saved','cand_saved')]},
                               'prefix':3.,'mic_wav':original['mic_wav']})
    results=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for job in pool.map(matrix.one,population):
            measured=job if 'error' in job else matrix.score(job)
            results.append(measured)
            print(json.dumps({k:v for k,v in measured.items() if k not in ('mic_admission','prototype_scores')},ensure_ascii=False),flush=True)
            (EV/'sweep-matrix.json').write_text(json.dumps(results,ensure_ascii=False,indent=1)+'\n')
    pairs={}
    for row in results:pairs.setdefault(row['cell'],{})[row['w']]=row
    summary={'cells':len(pairs),'replays':len(results),'errors':[r['out'] for r in results if 'error' in r],
             'regressions':[r['out'] for r in results if r.get('regressions')],
             'w_admission_differences':[k for k,p in pairs.items() if any('error' in r for r in p.values()) or p[False]['mic_admission']!=p[True]['mic_admission']]}
    (EV/'sweep-summary.json').write_text(json.dumps(summary,indent=1)+'\n')
    print(json.dumps(summary),flush=True)

if __name__=='__main__':run()
