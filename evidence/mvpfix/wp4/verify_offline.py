"""Fresh-context WP4 verification. Offline only; no services, decoder or paid calls."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'evidence/mvpfix/wp4/fresh'
PYTHON=Path('/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python')
OUT.mkdir(parents=True,exist_ok=True)
(ROOT/'.wp4runtime/tmp').mkdir(parents=True,exist_ok=True)
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH='.',TMPDIR=str(ROOT/'.wp4runtime/tmp'),
         NPM_CONFIG_CACHE=str(ROOT/'evidence/mvpfix/wp4/.npm-cache'),NPM_CONFIG_UPDATE_NOTIFIER='false')


def run(name,args):
    result=subprocess.run(args,cwd=ROOT,env=env,capture_output=True,text=True)
    (OUT/(name+'.txt')).write_text(result.stdout+result.stderr)
    print(json.dumps(dict(check=name,exit_code=result.returncode)),flush=True)
    return result


def main():
    checks=[]
    imported=run('import',[str(PYTHON),'-c','import moss_transcribe_diarize as m; print(m.__file__)'])
    checks.append(Path(imported.stdout.strip()).resolve()==ROOT/'moss_transcribe_diarize/__init__.py')
    commands=[
        ('phase2',[str(PYTHON),'-m','pytest','-q','-p','no:cacheprovider','--basetemp=evidence/mvpfix/wp4/.pytest-fresh','tests/phase2']),
        ('f6',[str(PYTHON),'-m','pytest','-q','-p','no:cacheprovider','--basetemp=evidence/mvpfix/wp4/.pytest-fresh-f6','tests/phase2/test_voiceprint_latency_measurement.py']),
        ('frontend',['npm','--prefix','frontend','test','--','--run']),
        ('typecheck',['npm','--prefix','frontend','run','typecheck']),
        ('build',['npm','--prefix','frontend','run','build']),
    ]
    results={name:run(name,args) for name,args in commands}
    checks.extend(r.returncode==0 for r in results.values())
    checks.append(bool(re.search(r'\b805 passed\b',results['phase2'].stdout)))
    checks.append(bool(re.search(r'\b2 passed\b',results['f6'].stdout)))
    clean=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',results['frontend'].stdout)
    checks.append(bool(re.search(r'Tests\s+209 passed',clean)))
    measured=run('oracle',[str(PYTHON),'prototypes/streaming-diarization/wp4-oracle-falsifiers/measure_oracle.py'])
    rows={r['case']:r for r in map(json.loads,measured.stdout.splitlines())}
    checks.append(rows['valid_public_corpus_overlap']['passed'] and rows['valid_public_corpus_overlap']['duplication_count']==0)
    checks.append(not rows['duplicated_playback']['passed'] and rows['duplicated_playback']['duplication_count']==5)
    checks.append(not rows['production_counts_only_validator']['accepted'])
    measured_file=run('file-boundaries',[str(PYTHON),'prototypes/streaming-diarization/wp4-oracle-falsifiers/measure_file_boundaries.py'])
    file_rows=list(map(json.loads,measured_file.stdout.splitlines()))
    checks.append(len(file_rows)==8 and sum(r['status']=='failed' for r in file_rows)==7)
    checks.append(next(r for r in file_rows if r['case']=='no_speech')['notice']=='No speech detected.')
    browser=json.loads((ROOT/'evidence/mvpfix/wp4/browser-export-result.json').read_text())
    checks.append(browser['ok'] and len(browser['formats'])==5 and all(r['ok'] for r in browser['formats'].values()))
    live=json.loads((ROOT/'evidence/mvpfix/wp4/live-lane-results.json').read_text())
    checks.append(not live[0]['passed'] and live[0]['status']=='completed')
    checks.append(live[1]['status']=='interrupted' and live[1]['valid_semantic_negative_control'] is False)
    checks.append(len((ROOT/'evidence/mvpfix/wp4/decoder-requests.jsonl').read_text().splitlines())==40)
    (OUT/'checks.json').write_text(json.dumps(dict(passed=sum(checks),total=len(checks),checks=checks),indent=2)+'\n')
    print(json.dumps(dict(offline_checks_passed=sum(checks),offline_checks_total=len(checks),
                         live_acceptance='FAIL alternation; overlap INCONCLUSIVE due to request cap',
                         summary_live='BLOCKED on key')),flush=True)
    return int(not all(checks))

if __name__=='__main__': raise SystemExit(main())
