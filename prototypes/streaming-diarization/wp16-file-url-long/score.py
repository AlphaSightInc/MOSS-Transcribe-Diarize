"""Use existing ordered-word oracle against concatenated public references."""
import json,time
from pathlib import Path
from moss_transcribe_diarize.lane_word_oracle import words,distance
root=Path('.wp16runtime'); refs=[json.loads(s) for s in (root/'media/reference.jsonl').read_text().splitlines()]
reference=words(' '.join(r['text'] for r in refs)); cache=[]; rows=[]
for name in ['long.wav','long.mp3','long.m4a','concurrent-a','concurrent-b']:
 path=root/(name+'.meeting.json')
 if not path.exists(): continue
 meeting=json.loads(path.read_text()); segments=meeting['transcript']['segments']; observed=words(' '.join(s['text'] for s in segments)); start=time.monotonic()
 score=next((row.copy() for tokens,row in cache if tokens==observed),None)
 if score is None: score=distance(reference,observed); cache.append((observed,score.copy()))
 score.update(case=name,reference_segments=len(refs),saved_segments=len(segments),distinct_source_clips=2,reference_speakers=len({r['speaker'] for r in refs}),saved_speakers=len({s.get('speaker_entity_id') or s['speaker'] for s in segments}),oracle_seconds=time.monotonic()-start)
 print(json.dumps(score),flush=True); rows.append(score)
Path('evidence/mvpfix/wp16/word-scores.json').write_text(json.dumps(rows,indent=2)+'\n')
