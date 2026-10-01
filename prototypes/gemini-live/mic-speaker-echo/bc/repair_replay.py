"""Correct a harness placement: H holes use ungated cleanup so an intentionally gated word is never resurrected.
Re-run only cells whose candidate lists or earlier-restored label dependencies change; no threshold changes.
"""
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
import soundfile as sf
import compose
from compose import rule,S
from moss_transcribe_diarize.app.gemini_final_policy import WebRtcWordGate
import importlib.util
matrix_spec=importlib.util.spec_from_file_location('bc_matrix',Path(__file__).resolve().parent/'run.py')
matrix=importlib.util.module_from_spec(matrix_spec)
matrix_spec.loader.exec_module(matrix)

EV=matrix.EV
HERE=Path(__file__).resolve().parent


def candidates(cleanup,witness,skip):
    return [[(w.text,w.speaker,w.start_sample,w.end_sample) for w in run]
            for run,n in rule.uncovered_runs(cleanup,witness,skip=skip) if n>=rule.MIN_RUN_SAMPLES]


def run():
    inspected=[]
    for path in sorted((EV/'runs').glob('*/*/receipt.json')):
        receipt=json.loads(path.read_text())
        if receipt.get('single_terminal_observation'):continue
        folder=path.parent
        logs=json.loads((folder/'terminal.json').read_text())
        mic=logs.get('microphone')
        if mic is None or not receipt['args'].get('mic_wav'):continue
        args=receipt['args']
        prefix=round(args['prefix']*S)
        floor=(np.random.default_rng(7).normal(0,10**(-63/20),prefix)*32767).astype(np.int16)
        pcm=np.concatenate([floor,sf.read(args['mic_wav'],dtype='int16')[0]]).tobytes()
        raw=[compose.GeminiWord(*w) for w in mic['before_rule']]
        voiced=WebRtcWordGate().filter(pcm,raw)
        source=json.loads((folder/'witness.json').read_text())['microphone']
        witness=rule.one_owner([compose.GeminiWord(*w[:4]) for w in source],[w[4] for w in source])
        skip=mic['coverage_gaps']
        old,new=candidates(voiced,witness,skip),candidates(raw,witness,skip)
        # Multiple restored runs could accidentally borrow an earlier restored label: remeasure them too.
        restore_probes=json.loads((folder/'mic-restores.json').read_text())
        changed=old!=new or bool(restore_probes)
        row={'cell':str(folder.relative_to(EV/'runs')),'candidate_lists_changed':old!=new,
             'old_candidates':old,'correct_candidates':new,'rerun':changed}
        inspected.append(row)
        if changed:
            command=[sys.executable,str(HERE/'engine.py'),args['run'],args['system_wav'],args['mic_wav'],
                     '--prefix',str(args['prefix']),'--rule','.15','--quiet']
            for key in ('donor','terminal_from','shift','drop','chunk','overlap','inject'):
                if args.get(key) is not None:command+=['--'+key.replace('_','-'),str(args[key])]
            for key in ('w','f2'):
                if args.get(key):command+=['--'+key]
            with (folder/'repair-process.log').open('w') as log:
                result=subprocess.run(command,stdout=log,stderr=log)
            assert result.returncode==0,(folder/'repair-process.log').read_text()[-3000:]
            print('Corrected replay',row['cell'],flush=True)
        (EV/'placement-audit.json').write_text(json.dumps(inspected,ensure_ascii=False,indent=1)+'\n')
    print(json.dumps({'inspected':len(inspected),'rerun':sum(r['rerun'] for r in inspected)}),flush=True)

if __name__=='__main__':run()
