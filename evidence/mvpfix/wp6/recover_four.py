"""Offline recovery of the four-session saved surface; original failed result stays intact.

Reads only this campaign's ignored local SQLite artifact. Never emits transcript words.
The original collector omitted unavailable outcomes and precise start/Stop anchors;
all recovered clock quantities are explicitly upper bounds, not exact replacements.
"""
import importlib.util
import json
import math
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / 'evidence/mvpfix/wp6/20260918-000221-4x600'
spec = importlib.util.spec_from_file_location('wp6_recovery_runner', ROOT/'prototypes/capacity-campaign/run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
original = json.loads((RUN/'result.json').read_text())
database = ROOT/'.wp6-tmp/20260918-000221/state/phase2.sqlite'
connection = sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True)
clips = runner.inputs(4)
rows = []
anchor = original['resources'][0]['time']  # Before all workspace creation and replay.
for row in sorted(original['session_results'], key=lambda r:r['ordinal']):
    ident = row['events'][0]['session_id']
    status = connection.execute('SELECT status FROM meetings WHERE meeting_id=?',(ident,)).fetchone()[0]
    version, document = connection.execute('SELECT version,document_json FROM meeting_transcripts WHERE meeting_id=?',(ident,)).fetchone()
    segments = json.loads(document)['segments']
    audio = connection.execute('SELECT state,duration_ms,byte_count FROM meeting_audio WHERE meeting_id=?',(ident,)).fetchone()
    words = runner.latency.words(' '.join(s['text'] for s in segments))
    _, pcm, references = clips[row['ordinal']-1]
    seconds = len(pcm)/32000
    ref, partial = [], 0
    for loop in range(math.ceil(600/seconds)):
        for r in references:
            if loop*seconds+r['end'] <= 600:
                ref.extend(runner.latency.words(r['text']))
            elif loop*seconds+r['start'] < 600:
                partial += 1
    terminal = [e for e in row['events'] if e['kind']=='terminal_finalization_failed']
    assert len(terminal)==1 and terminal[0]['payload']['outcome']=='tape_unavailable'
    canonical = [e for e in row['events'] if e['kind']=='canonical_processed' and e['payload'].get('submitted') is True]
    lags = [max(0,e['payload']['runtime_monotonic_ns']/1e9-anchor-e['payload']['committed_samples']/16000) for e in canonical]
    rows.append(dict(
        ordinal=row['ordinal'], saved_meeting_status=status,
        observed_session_closed_events=sum(e['kind']=='session_closed' for e in row['events']),
        finalization_status_from_recorded_outcome='unavailable',
        terminal_reason=terminal[0]['payload']['reason'], stop_to_final_seconds=None,
        stop_to_unavailable_upper_bound_seconds=terminal[0]['payload']['runtime_monotonic_ns']/1e9-anchor-600,
        p95_canonical_lag_upper_bound_seconds=runner.percentile(lags,.95),
        canonical_events=len(canonical),
        acknowledged_frames=row['acknowledged_frames'],
        acknowledged_audio_samples_derived=row['acknowledged_frames']//2*8000,
        last_committed_samples_from_events=max(e['payload']['committed_samples'] for e in canonical),
        accepted_accounted_api_counters='not retained by original collector',
        transcript_version=version, word_count=len(words), reference_word_count=len(ref),
        words_per_minute=len(words)/10, partial_reference_rows=partial,
        wer=None if partial else runner.latency.edit_wer(ref,words),
        unique_vocabulary_retention=len(set(words)&set(ref))/len(set(ref)),
        speakers=len({s.get('speaker_entity_id') or s.get('speaker') for s in segments}),
        last_api_visible_word_count=row['updates'][-1]['words'],
        saved_audio_status=audio[0], saved_audio_duration_seconds=audio[1]/1000,
        saved_audio_bytes=audio[2],
    ))
connection.close()
print(json.dumps(dict(source='read-only retained local SQLite plus original event/ack records',
    clocks='Upper bounds use the resource sample before client bootstrap; exact replay/Stop anchors were not retained.',
    per_session=rows),indent=2))
