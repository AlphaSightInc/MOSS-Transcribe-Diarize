"""PROTOTYPE — falsify database-file-only hot backup at real store commit seam."""
import asyncio,json,shutil,sqlite3
from probe import phase2,SCRATCH,OUT
async def main():
    root=SCRATCH/'wal-control';root.mkdir()
    path=root/'phase2.sqlite';store=await phase2.Phase2Store.open(path)
    try:
        account,_=await store.bootstrap_browser(None);handle=await store.workspace(account).create_meeting('live')
        version=await handle.commit_transcript({'segments':[{'text':'Public synthetic durability marker'}]})
        shutil.copy2(path,root/'db-only.sqlite')
        def count(p):
            with sqlite3.connect(p) as db:
                try:return db.execute('SELECT count(*) FROM meeting_transcripts').fetchone()[0]
                except sqlite3.OperationalError:return 0
        with sqlite3.connect(path) as source,sqlite3.connect(root/'online.sqlite') as dest:source.backup(dest)
        r={'acknowledged_version':version,'source_transcripts':count(path),'database_only_transcripts':count(root/'db-only.sqlite'),'online_backup_transcripts':count(root/'online.sqlite'),'wal_bytes':Path(str(path)+'-wal').stat().st_size}
    finally:await store.close()
    (OUT/'wal-control.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
from pathlib import Path
asyncio.run(main())
