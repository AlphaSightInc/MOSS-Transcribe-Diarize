"""Read-only retained WP12 timing/evidence audit; no decoder calls."""
import json, sqlite3, re
from pathlib import Path
ROOT=Path.cwd();OUT=ROOT/'evidence/mvpfix/wp12'
rows=[json.loads(s) for s in (OUT/'trace.jsonl').read_text().splitlines()]
requests=[json.loads(s) for s in (OUT/'requests.jsonl').read_text().splitlines()]
assert len(requests)<=1200
assert [r['request'] for r in requests]==list(range(1,len(requests)+1))
intervals=[]
for r in rows:
    if r['kind']=='request':intervals.extend([(r['start'],1),(r['start']+r['seconds'],-1)])
active=peak=0
for _,delta in sorted(intervals):active+=delta;peak=max(peak,active)
assert peak<=2 and active==0
assert len(intervals)//2 == len(requests)
result={'requests':len(requests),'request_cap':1200,'peak_decoder_concurrency':peak,'runs':[]}
paths = sorted(path for case in ('parity','alternation','mic-minus10','same-voice') for path in OUT.glob(f'*-{case}-*.json'))
for path in paths:
    r=json.loads(path.read_text());assert r['status']=='final' and r['saved_equal']
    subset=[x for x in rows if x['arm']==r['arm'] and r['stop']<=x['time']<=r['stop']+r['stop_to_final']+.1]
    events={x['event']:x for x in subset if x['kind']=='event'}
    terminals=[x for x in subset if x['kind']=='terminal_end']
    identity=[x for x in subset if x['kind']=='identity' and x['reason']=='terminal']
    start=events['terminal_finalization_started']['time'];end=events['terminal_finalization_completed']['time']
    result['runs'].append({'file':path.name,'seconds':r['seconds'],'stop_to_final':r['stop_to_final'],'requests':r['requests'],'drain_seconds':start-r['stop'],'terminal_wall_seconds':end-start,'terminal_decoder_job_seconds':[x['seconds'] for x in terminals],'terminal_identity_seconds':[x['seconds'] for x in identity],'terminal_windows':sum(x['accounting']['window_count'] for x in terminals),'terminal_decoded_audio_seconds':sum(x['accounting']['decoded_audio_samples'] for x in terminals)/16000,'stop_pending':events['stop_requested']['queues'],'final':r['final']})
# Compare actual persisted segment dictionaries, retaining only counts/verdicts.
for duration,index in ((24,0),(60,-1)):
    docs={}
    for arm in ('lane','parallel'):
        c=sqlite3.connect(f'file:{ROOT}/.wp12/state-{arm}/phase2.sqlite?mode=ro',uri=True)
        docs[arm]=[json.loads(x[0])['segments'] for x in c.execute('SELECT document_json FROM meeting_transcripts ORDER BY updated_at_ms')][index]
        c.close()
    byspeaker={}
    for speaker in sorted({s['speaker_entity_id'] for s in docs['lane']}):
        def words(arm):return [w for s in docs[arm] if s['speaker_entity_id']==speaker for w in re.findall(r'[a-z0-9]+',s['text'].lower())]
        a,b=words('lane'),words('parallel');assert a==b
        byspeaker[speaker]={'ordered_words_equal':True,'words':len(a)}
    result[f'equivalence_{duration}']={'exact_saved_segments_equal':docs['lane']==docs['parallel'],'speakers':byspeaker}
assert result['equivalence_24']['exact_saved_segments_equal']
c=sqlite3.connect(f'file:{ROOT}/.wp12/state-fixed/phase2.sqlite?mode=ro',uri=True)
a=json.loads(c.execute('SELECT document_json FROM meeting_transcripts ORDER BY updated_at_ms DESC LIMIT 1').fetchone()[0])['segments']
c.close()
c=sqlite3.connect(f'file:{ROOT}/.wp12/state-lane/phase2.sqlite?mode=ro',uri=True)
b=json.loads(c.execute('SELECT document_json FROM meeting_transcripts ORDER BY updated_at_ms LIMIT 1').fetchone()[0])['segments']
c.close()
assert a==b
result['fixed_24_exact_saved_segments_equal']=True
# Current matched instrumentation arms: compare retained dictionaries, not counts.
matched={}
for arm in ('serial-traced','concurrent-traced'):
    c=sqlite3.connect(f'file:{ROOT}/.wp12/state-{arm}/phase2.sqlite?mode=ro',uri=True)
    matched[arm]=json.loads(c.execute('SELECT document_json FROM meeting_transcripts ORDER BY updated_at_ms DESC LIMIT 1').fetchone()[0])['segments']
    c.close()
assert matched['serial-traced']==matched['concurrent-traced']
result['matched_24_exact_saved_segments_equal']=True
result['matched_24_saved_segment_count']=len(matched['serial-traced'])
c=sqlite3.connect(f'file:{ROOT}/.wp12/state-overlap-fixed/phase2.sqlite?mode=ro',uri=True)
fixed=[json.loads(x[0])['segments'] for x in c.execute('SELECT document_json FROM meeting_transcripts ORDER BY updated_at_ms')]
c.close()
for index,duration in enumerate((24,60)):
    c=sqlite3.connect(f'file:{ROOT}/.wp12/state-overlap-shadow-p{duration}/phase2.sqlite?mode=ro',uri=True)
    control=json.loads(c.execute('SELECT document_json FROM meeting_transcripts ORDER BY updated_at_ms LIMIT 1').fetchone()[0])['segments']
    c.close()
    actual=fixed[index]
    assert [(s['text'],s['speaker_entity_id']) for s in actual] == [(s['text'],s['speaker_entity_id']) for s in control]
    differences=[{'row':i,'fields':[key for key in a if a[key]!=b[key]]} for i,(a,b) in enumerate(zip(control,actual,strict=True)) if a!=b]
    if duration==24:assert not differences
    result[f'overlap_saved_{duration}']={'segments':len(actual),'exact_text_and_speaker_equal':True,'exact_dictionaries_equal':not differences,'differences':differences}
invalidated=json.loads((OUT/'overlap-invalidated-180-control.json').read_text())
result['completed_run_requests']=sum(r['requests'] for r in result['runs'])
result['invalidated_control_requests']=invalidated['completed_requests']
assert result['completed_run_requests']+result['invalidated_control_requests']==len(requests)
print(json.dumps(result,indent=2))
