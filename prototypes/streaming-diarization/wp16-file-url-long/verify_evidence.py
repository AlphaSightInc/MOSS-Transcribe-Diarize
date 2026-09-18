"""Offline assertions over retained browser evidence; never dispatches a decoder."""
import json
from pathlib import Path
root=Path('evidence/mvpfix/wp16')
load=lambda name:json.loads((root/name).read_text())
summary=load('summary.json'); rows={r['case']:r for r in summary['cases']}
assert len(rows)==16
failures={'empty.wav':'transcode_failed','text.mp3':'transcode_failed','missing':'acquisition_http_404','html':'acquisition_failed','hang':'acquisition_timeout'}
for name,row in rows.items():
 assert row['foreign_read_status']==404, name
 assert row['history_reason'] and row['header_reason'] and row['reason_content_free'],name
 assert row['status']==row['reload_status'],name
 if name in failures:
  assert row['status']=='failed' and row['failure_code']==failures[name],name
 else:
  assert row['status']=='completed' and row['mp3_link'] and row['mp3_bytes']>0,name
 assert all(e['ok'] for e in row['exports'].values()),name
assert summary['exports_passed']==summary['exports_total']==50
assert rows['silence.wav']['saved_words']==0 and rows['silence.wav']['notice']=='No speech detected.'
assert load('silence-before.json')['saved_words']==32
oversize=load('oversize.json')
assert oversize['status']==507 and oversize['meetings']==0 and oversize['post_routes']==['admission']
assert 'Not accepted: Insufficient storage for upload.' in oversize['ui']
assert 0<summary['requests']<=200
windows=[json.loads(line) for line in (root/'windows.jsonl').read_text().splitlines()]
for name in ('long.wav','long.mp3','long.m4a'):
 row=rows[name]; decoded=[w for w in windows if row['started_monotonic']<=w['started']<row['started_monotonic']+row['elapsed_seconds']]
 assert [w['index'] for w in decoded]==list(range(15)),name
 assert all(w['end']-w['start']<=150 for w in decoded)
 assert row['saved_audio_seconds']==1800 and row['rss_samples']>=2
pair=[rows['concurrent-a'],rows['concurrent-b']]
start=min(r['started_monotonic'] for r in pair);end=max(r['started_monotonic']+r['elapsed_seconds'] for r in pair)
decoded=[w for w in windows if start<=w['started']<end]; threads={w['thread'] for w in decoded}
assert len(threads)==2 and len(decoded)==30
assert all(sorted(w['index'] for w in decoded if w['thread']==t)==list(range(15)) for t in threads)
scores=load('word-scores.json');assert len(scores)==5
for score in scores:
 assert score['reference_words']==4725 and score['reference_speakers']==3 and score['saved_speakers']==31
 assert score['observed_words']==rows[score['case']]['saved_words']
 assert abs(score['wer']-(score['substitutions']+score['omissions']+score['additions'])/4725)<1e-12
print(json.dumps(dict(cases=16,typed_failures=5,exports='50/50',long_cases=5,capacity_refusal=True,silence_fixed=True,requests=summary['requests'],status='PASS')))

# Compare actual retained browser downloads to actual saved API snapshots again.
from tests.e2e.export_oracle import compare_export
from moss_transcribe_diarize.lane_word_oracle import words
count=0
for name,row in rows.items():
    snapshot=json.loads((Path('.wp16runtime')/(name+'.meeting.json')).read_text())
    assert snapshot['id']==row['meeting_id']
    segments=(snapshot.get('transcript') or {}).get('segments',[])
    assert sum(len(words(s['text'])) for s in segments)==row['saved_words']
    for fmt in row['exports']:
        actual=(Path('.wp16runtime')/(name+'.'+fmt)).read_text()
        assert compare_export(fmt,actual,snapshot)['ok'],(name,fmt)
        count+=1
assert count==50
print(json.dumps(dict(retained_downloads_checked=count,status='PASS')))
