"""PROTOTYPE — copied stores only; metadata output, private payloads under .wp31.
Question: do old durable records survive the integrated reader and restore?
Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <venv-python> prototypes/data-durability/probe.py
"""
import asyncio, json, shutil, sqlite3, time
from pathlib import Path
from fastapi.testclient import TestClient
from moss_transcribe_diarize.app import phase2

ROOT=Path(__file__).resolve().parents[2]
SCRATCH=ROOT/'.wp31'
OUT=ROOT/'evidence/mvpfix/wp31'
phase2.REQUIRED_SQLITE_RUNTIME=sqlite3.sqlite_version  # supplied local harness exception

def copy_state(source, dest):
    dest.mkdir(parents=True)
    for name in ('phase2.sqlite','phase2.sqlite-wal','phase2.sqlite-shm'):
        if (source/name).is_file(): shutil.copy2(source/name,dest/name)
    if (source/'meeting-audio').exists(): shutil.copytree(source/'meeting-audio',dest/'meeting-audio')

def rows(path):
    with sqlite3.connect(path) as db:
        db.row_factory=sqlite3.Row
        return {r[0]:[dict(x) for x in db.execute('SELECT * FROM '+r[0]+' ORDER BY rowid')] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}

def app(state):
    return phase2.create_phase2_app(database_path=state/'phase2.sqlite',file_work_root=state/'file-work',meeting_audio_root=state/'meeting-audio')

def inspect_store(name, source):
    state=SCRATCH/'stores'/name
    copy_state(source,state)
    before=rows(state/'phase2.sqlite')
    result={'source':str(source), 'tables':{k:len(v) for k,v in before.items()}}
    totals=dict(history=0,opened=0,transcripts_equal=0,rename=0,audio_truthful=0,voiceprints=0,tagged_segments=0,legacy_segments=0)
    with TestClient(app(state),base_url='https://moss.test') as client:
        for account in before['accounts']:
            aid=account['account_id']
            sessions=[s for s in before['sign_in_sessions'] if s['account_id']==aid]
            if not sessions or not account['enabled']: continue
            client.cookies.clear(); client.cookies.set(phase2.SESSION_COOKIE,sessions[0]['session_id'])
            history=client.get('/api/meetings'); history.raise_for_status()
            meetings=history.json()['meetings']; totals['history']+=len(meetings)
            expected=[m for m in before['meetings'] if m['account_id']==aid]
            assert {m['id'] for m in meetings}=={m['meeting_id'] for m in expected}
            bank=client.get('/api/voiceprints'); bank.raise_for_status()
            totals['voiceprints']+=len(bank.json()['voiceprints'])
            for m in meetings:
                mid=m['id']; opened=client.get('/api/meetings/'+mid); opened.raise_for_status(); m=opened.json(); totals['opened']+=1
                old=next((t for t in before['meeting_transcripts'] if t['meeting_id']==mid and t['account_id']==aid),None)
                totals['transcripts_equal']+=m['transcript']==(json.loads(old['document_json']) if old else None)
                for seg in (m.get('transcript') or {}).get('segments',[]): totals['tagged_segments' if seg.get('source_lane') else 'legacy_segments']+=1
                audio=m.get('audio') or {}; response=client.get('/api/meetings/'+mid+'/audio/download')
                totals['audio_truthful']+=response.status_code==(200 if audio.get('state') in ('available','partial') else 404)
                renamed=client.put('/api/meetings/'+mid+'/title',json={'title':'WP31 copied-store rename'})
                totals['rename']+=renamed.status_code==200 and client.get('/api/meetings/'+mid).json()['title']=='WP31 copied-store rename'
    after=rows(state/'phase2.sqlite')
    result.update(totals)
    result['bank_rows_unchanged']=all(before.get(t,[])==after.get(t,[]) for t in ('voiceprints','voiceprint_samples'))
    backup=SCRATCH/'idle-backups'/name
    copy_state(state,backup)
    result['idle_database_bytes_equal']=(state/'phase2.sqlite').read_bytes()==(backup/'phase2.sqlite').read_bytes()
    result['idle_rows_equal']=rows(state/'phase2.sqlite')==rows(backup/'phase2.sqlite')
    result['idle_audio_equal']=all((backup/'meeting-audio'/p.relative_to(state/'meeting-audio')).read_bytes()==p.read_bytes() for p in (state/'meeting-audio').rglob('*') if p.is_file())
    result['ok']=all(result[k]==result['tables']['meetings'] for k in ('history','opened','transcripts_equal','rename','audio_truthful')) and result['bank_rows_unchanged'] and result['idle_rows_equal'] and result['idle_audio_equal']
    print(json.dumps({'case':name,**result}),flush=True)
    return result

async def refusal():
    result={}
    for version in (1,3,999):
        path=SCRATCH/f'version-{version}.sqlite'
        with sqlite3.connect(path) as db: db.execute(f'PRAGMA user_version={version}')
        original=path.read_bytes()
        try:
            store=await phase2.Phase2Store.open(path); await store.close(); error=None
        except Exception as e: error={'type':type(e).__name__,'reason':str(e)}
        result[str(version)]={'refused':error is not None,'error':error,'bytes_unchanged':original==path.read_bytes()}
    path=SCRATCH/'corrupt.sqlite'; path.write_bytes(b'not a SQLite database\0'*100); original=path.read_bytes()
    try:
        store=await phase2.Phase2Store.open(path); await store.close(); error=None
    except Exception as e: error={'type':type(e).__name__,'reason':str(e)}
    result['corrupt']={'refused':error is not None,'error':error,'bytes_unchanged':original==path.read_bytes()}
    print(json.dumps({'case':'refusal',**result}),flush=True)
    return result

def main():
    sources={'codex-prelane':Path('/private/tmp/moss-review-runtime-20260917/state'),'lead-prelane':Path('/private/tmp/claude-501/ir/rt/state'),'lead-perlane':Path('/private/tmp/claude-501/ir/final/rt/state')}
    base=ROOT.parent
    for wp,suffix,pattern in [('wp6','capacity-baseline','.wp6-tmp/*/state/phase2.sqlite'),('wp15','stop-lease-longrun','.wp15/real-*/state/phase2.sqlite'),('wp22','memory-longrun','.wp22/real-*/state/phase2.sqlite')]:
        for i,p in enumerate(sorted((base/f'MOSS-Transcribe-Diarize-wt-{wp}-{suffix}').glob(pattern))): sources[f'{wp}-{i}']=p.parent
    result={'stores':{},'sqlite_runtime':sqlite3.sqlite_version}
    for name,source in sources.items(): result['stores'][name]=inspect_store(name,source)
    result['refusal']=asyncio.run(refusal())
    (OUT/'prototype.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
