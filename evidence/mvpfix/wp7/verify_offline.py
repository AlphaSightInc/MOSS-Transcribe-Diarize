"""WP7 fresh-context verification: no decoder, provider, server or shared-tree writes."""
import json,os,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'evidence/mvpfix/wp7/fresh';OUT.mkdir(exist_ok=True)
PYTHON='/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python'
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH='.',TMPDIR=str(ROOT/'.wp7runtime/tmp'),
         NPM_CONFIG_CACHE=str(ROOT/'.wp7runtime/npm-cache'),NPM_CONFIG_UPDATE_NOTIFIER='false')
Path(env['TMPDIR']).mkdir(parents=True,exist_ok=True)
checks={}
def run(name,args):
    p=subprocess.run(args,cwd=ROOT,env=env,capture_output=True,text=True)
    (OUT/f'{name}.txt').write_text(p.stdout+p.stderr)
    checks[name+'_exit']=p.returncode==0
    print(json.dumps(dict(check=name,exit=p.returncode)),flush=True)
    return p.stdout

def main():
    imported=run('import',[PYTHON,'-c','import moss_transcribe_diarize as m; print(m.__file__)'])
    checks['own_import']=Path(imported.strip()).resolve()==ROOT/'moss_transcribe_diarize/__init__.py'
    suite=run('phase2',[PYTHON,'-m','pytest','-q','-p','no:cacheprovider','tests/phase2'])
    checks['phase2_811']=bool(re.search(r'\b811 passed\b',suite))
    ui=run('frontend',['npm','--prefix','frontend','test','--','--run','src/components/speakerRename.test.tsx','src/components/VoiceprintBank.test.tsx'])
    checks['frontend_5']=bool(re.search(r'Tests\s+5 passed',re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',ui)))
    protected=['moss_transcribe_diarize/phase2_acceptance.py','moss_transcribe_diarize/app/live_manifest_finalizer.py',
               'moss_transcribe_diarize/app/live_identity.py','moss_transcribe_diarize/app/live_identity_album.py',
               'moss_transcribe_diarize/app/live_session.py','moss_transcribe_diarize/app/phase2_speaker_identity.py',
               'moss_transcribe_diarize/app/phase2_voiceprint_match.py']
    unchanged=run('policy-diff',['git','diff','a7bb4201','--',*protected]);checks['policies_unchanged']=unchanged==''
    root=ROOT/'evidence/mvpfix/wp7'
    cases=json.loads((root/'stress-results.json').read_text());by={r['case']:r for r in cases}
    checks['13_completed']=len(cases)==13 and all(r['status']=='completed' and r['finalization']=='final' for r in cases)
    checks['149_identity_calls']=len((root/'stress-requests.jsonl').read_text().splitlines())==149
    checks['20_part0_calls']=len((root/'part0-requests.jsonl').read_text().splitlines())==20
    checks['single_one']=len(by['single']['identity']['canonical_speakers'])==1
    checks['gap_falsifier_retained']=len(by['gap']['identity']['canonical_speakers'])==2 and by['gap']['saved_speakers']==['S01']
    checks['two_voices_stable']=len(by['alternating']['identity']['canonical_speakers'])==2 and all(n==0 for n in by['alternating']['score']['id_switches'].values())
    checks['namespace_falsifier_retained']=len(by['lanes']['identity']['canonical_speakers'])==1
    checks['api_recognition_only']=0<by['recognition']['recognition_seconds']<4
    checks['unknown_abstains']=by['unknown']['recognition_seconds'] is None and by['unknown']['saved_speakers']==['S01']
    checks['deleted_profile_abstains']=by['after_delete']['recognition_seconds'] is None and not by['after_delete']['bank']
    checks['short_pending_not_falsely_enrolled']=not by['three_seconds_waited']['bank'] and by['three_seconds_waited']['actions'][0]['response']['result']['enrollment']=='pending'
    repeated=by['confirmed_replacement']['actions']
    checks['repeat_upserts_sample']=len(repeated)==2 and all(r['response']['result']['enrollment']=='enrolled' and r['bank'][0]['sample_count']==2 for r in repeated)
    checks['same_profile']=len({r['response']['result']['voiceprint_id'] for r in repeated})==1
    cpu=json.loads((root/'cpu-results.json').read_text())
    checks['cpu_4_matches']=len(cpu['matching'])==4 and all(r['expected']==r['observed'] for r in cpu['matching'])
    checks['cpu_floor']=cpu['enrollment_floor']==2 and [r['eligible'] for r in cpu['floors']]==[False,True,True]
    browser=json.loads((root/'browser-result.json').read_text())
    checks['saved_names_and_5_exports']=browser['name_persisted'] and len(browser['formats'])==5 and all(r['ok'] for r in browser['formats'].values())
    oracle=json.loads((root/'summary.json').read_text())['word_oracle']
    checks['interior_attribution_kept_failing']=not oracle['passed'] and oracle['attribution_errors']==2 and oracle['duplication_count']==2 and oracle['boundary_attribution_words']==0
    report=dict(passed=sum(checks.values()),total=len(checks),checks=checks,live_rerun=False)
    (OUT/'checks.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
    return int(not all(checks.values()))
if __name__=='__main__':raise SystemExit(main())
