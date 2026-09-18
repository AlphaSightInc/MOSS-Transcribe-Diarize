"""Provider-free verification of retained evidence and all extended private stores.

Exits nonzero if successful claims or explicit known limitations no longer match.
It does not rerun a decoder, assume recordings are reproducible, or open originals.
"""
import json
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient
from probe import ROOT,SCRATCH,OUT,app,copy_state,rows


def main():
    baseline=json.loads((OUT/'prototype.json').read_text())
    journeys=json.loads((OUT/'journeys.json').read_text())['stores']
    recovery=json.loads((OUT/'recovery.json').read_text())
    rollback=json.loads((OUT/'rollback.json').read_text())
    assert len(baseline['stores'])==len(journeys)==13
    assert sum(r['tables']['meetings'] for r in baseline['stores'].values())==47
    assert all(r['ok'] for r in baseline['stores'].values())
    assert all(r['ok'] for r in journeys.values())
    assert sum(r['exports_passed'] for r in journeys.values())==235
    assert all(v['refused'] and v['bytes_unchanged'] for v in baseline['refusal'].values())
    assert recovery['restart']['status']=='interrupted'
    assert recovery['restart']['committed_before']==recovery['restart']['committed_after']==2
    assert recovery['restart']['acknowledged_segments_preserved']
    assert recovery['restart']['audio_state']=='partial' and recovery['restart']['audio_decodable']
    assert recovery['client']['new_status']=='completed' and recovery['client']['new_segments']>0
    assert recovery['client']['same_document'] and recovery['client']['same_document_after_new']
    assert recovery['active_backup']['restored_interrupted'] and recovery['active_backup']['transcript_rows_preserved'] and recovery['active_backup']['audio_resolves']
    assert recovery['cold_boot']['descriptor_status']==200
    assert all(r['all_rows_unchanged'] for r in rollback.values())
    assert rollback['base_37979e53']['lanes']==0 and rollback['base_37979e53']['exports_passed']==32
    assert rollback['integrated_after']['lanes']==8 and rollback['integrated_after']['exports_passed']==40
    wal=json.loads((OUT/'wal-control.json').read_text())
    assert (wal['source_transcripts'],wal['database_only_transcripts'],wal['online_backup_transcripts'])==(1,0,1)
    # Actual rerun on independent copies after the live-extension process has exited.
    verification=SCRATCH/'verify-extended'
    verification.mkdir(exist_ok=True)
    counts={'stores':0,'meetings':0,'preserved_old_transcripts':0,'new_meetings':0,'audio_files':0}
    for name,old in baseline['stores'].items():
        dest=verification/name
        # Single execution only, so fresh verification cannot silently reuse a stale copy.
        copy_state(SCRATCH/'stores'/name,dest)
        before=rows(dest/'phase2.sqlite'); originals=rows(SCRATCH/'idle-backups'/name/'phase2.sqlite')
        old_docs={(r['account_id'],r['meeting_id']):r['document_json'] for r in originals['meeting_transcripts']}
        assert len(before['meetings'])==old['tables']['meetings']+1
        with TestClient(app(dest),base_url='https://moss.test'):
            after=rows(dest/'phase2.sqlite')
            assert before==after
            found={(r['account_id'],r['meeting_id']):r['document_json'] for r in after['meeting_transcripts']}
            assert all(found[k]==v for k,v in old_docs.items())
            audio=[a for a in after['meeting_audio'] if a['state'] in ('available','partial')]
            assert all((dest/'meeting-audio'/a['relative_path']).stat().st_size==a['byte_count'] for a in audio)
        counts['stores']+=1;counts['meetings']+=len(after['meetings']);counts['preserved_old_transcripts']+=len(old_docs);counts['new_meetings']+=1;counts['audio_files']+=len(audio)
    assert counts['meetings']==60 and counts['preserved_old_transcripts']==47
    print(json.dumps({'pass':True,'retained_evidence_claims_checked':True,'extended_stores_reopened':counts},sort_keys=True))

if __name__=='__main__':main()
