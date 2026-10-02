"""Throwaway FK experiment on the real product schema. No network/model/key access."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from moss_transcribe_diarize.app.phase2 import Phase2Store

async def main():
    with tempfile.TemporaryDirectory() as tmp:
        store = await Phase2Store.open(Path(tmp) / 'probe.sqlite3')
        account, _ = await store.bootstrap_browser(None)
        handle = await store.workspace(account).create_meeting('file')
        await handle.finish('completed')
        db = store._connection
        async with store._mutation():
            await db.execute("INSERT INTO voiceprints VALUES (?, 'v', 'Alex', 'fake', 2, 1, 1, 1)", (account.account_id,))
            await db.execute("INSERT INTO voiceprint_samples VALUES (?, 'v', 's', ?, ?, 1)", (account.account_id, b'vector', handle.meeting_id))
        blocked = False
        try:
            async with store._mutation():
                await db.execute('DELETE FROM meetings WHERE meeting_id=?', (handle.meeting_id,))
        except Exception as exc:
            blocked = type(exc).__name__ == 'IntegrityError'
        async with store._mutation():
            await db.execute('UPDATE voiceprint_samples SET source_meeting_id=NULL WHERE source_meeting_id=?', (handle.meeting_id,))
            await db.execute('DELETE FROM meetings WHERE meeting_id=?', (handle.meeting_id,))
        cursor = await db.execute('SELECT vector, source_meeting_id FROM voiceprint_samples')
        row = await cursor.fetchone()
        state = dict(direct_delete_fk_blocked=blocked, remaining_meetings=len(await store.workspace(account).list_meetings()), saved_vector_unchanged=row['vector'] == b'vector', source_detached=row['source_meeting_id'] is None)
        print(json.dumps(state, indent=2))
        assert blocked and state['remaining_meetings'] == 0 and state['saved_vector_unchanged'] and state['source_detached']
        await store.close()
asyncio.run(main())
