"""Offline saved-audio/content and birth-count evidence; no network or private words emitted."""
import importlib.util
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
run = Path(sys.argv[1])
result = json.loads((run/'result.json').read_text())
scratch = ROOT/'.wp6-tmp'/run.name[:15]
spec = importlib.util.spec_from_file_location('wp6_runner', ROOT/'prototypes/capacity-campaign/run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
clips = runner.inputs(result['sessions'])
database = scratch/'state/phase2.sqlite'
# Use only after the owned stack exits and SQLite checkpoints its WAL.
assert not database.with_name(database.name+'-wal').exists()
connection = sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1', uri=True)
rows = []
for row in sorted(result['session_results'], key=lambda r:r['ordinal']):
    ident = row['events'][0]['session_id']
    snapshot_path = scratch/f"snapshot-{row['ordinal']}.json"
    snap = json.loads(snapshot_path.read_text()) if snapshot_path.exists() else None
    status = connection.execute('SELECT status FROM meetings WHERE meeting_id=?',(ident,)).fetchone()[0]
    document = json.loads(connection.execute('SELECT document_json FROM meeting_transcripts WHERE meeting_id=?',(ident,)).fetchone()[0])
    segments = document['segments']
    words = runner.latency.words(' '.join(s['text'] for s in segments))
    snapshot_words = runner.latency.words(' '.join(s['text'] for s in runner.latency.segments_of(snap))) if snap else None
    audio = connection.execute('SELECT state,duration_ms,byte_count,relative_path FROM meeting_audio WHERE meeting_id=?',(ident,)).fetchone()
    audio_path = scratch/'state/meeting-audio'/audio[3]
    probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries',
        'format=duration,size:stream=codec_name,sample_rate,channels','-of','json',str(audio_path)],text=True))
    _, pcm, references = clips[row['ordinal']-1]
    seconds = len(pcm)/32000
    reference, partial = [], 0
    for loop in range(math.ceil(result['seconds']/seconds)):
        for r in references:
            if loop*seconds+r['end'] <= result['seconds']:
                reference.extend(runner.latency.words(r['text']))
            elif loop*seconds+r['start'] < result['seconds']:
                partial += 1
    terminal = [e for e in row['events'] if e['kind'].startswith('terminal_finalization')]
    canonical = [e for e in row['events'] if e['kind']=='canonical_processed'
                 and e['payload'].get('submitted') is True]
    canonical_lags = [max(0, e['payload']['runtime_monotonic_ns']/1e9-row['started_monotonic']
                         - e['payload']['committed_samples']/16000) for e in canonical]
    rows.append(dict(ordinal=row['ordinal'], saved_meeting_status=status,
        finalization_status=snap['session']['finalization_status'] if snap else 'not retained; interrupted meeting', terminal_events=terminal,
        stop_to_final_seconds=row.get('stop_to_final_seconds'),
        saved_audio_status=audio[0], saved_audio_duration_seconds=audio[1]/1000,
        saved_audio_bytes=audio[2], mp3_probe=probe, saved_matches_final_snapshot=words==snapshot_words if snap else None,
        word_count=len(words), reference_word_count=len(reference), partial_reference_rows=partial,
        p95_canonical_lag_seconds=runner.percentile(canonical_lags,.95),
        last_retained_canonical_samples=max(e['payload']['committed_samples'] for e in canonical),
        saved_transcript_end_seconds=max(s['end'] for s in segments),
        wer=None if partial else runner.latency.edit_wer(reference,words),
        identity_counts=snap['identity_counts'] if snap else None,
        named_speakers=len({s['speaker_entity_id'] for s in segments if s.get('speaker_entity_id')}),
        unassigned_segments=sum(not s.get('speaker_entity_id') for s in segments),
        reference_speakers=len({r['speaker'] for r in references}),
    ))
connection.close()
print(json.dumps(dict(source='read-only saved SQLite, final API snapshot and independent ffprobe',per_session=rows),indent=2))
