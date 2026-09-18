"""Current production Stop timings and terminal embedding work, no provider calls."""
import json
from pathlib import Path

out = Path('evidence/mvpfix/wp12')
trace = [json.loads(line) for line in (out/'trace.jsonl').read_text().splitlines()]
reports = []
for duration in (24, 60, 180):
    path = out/f'overlap-fixed-parity-{duration}.json'
    if not path.exists():
        continue
    run = json.loads(path.read_text())
    assert run['status']=='final' and run['saved_equal']
    rows = [x for x in trace if x['arm']==run['arm'] and run['start']<=x['time']<=run['stop']+run['stop_to_final']]
    events = {x['event']:x for x in rows if x['kind']=='event' and x['time']>=run['stop']}
    embeddings = [x for x in rows if x['kind']=='embedding' and x.get('reason') in ('terminal','terminal_uncovered')]
    reports.append(dict(seconds=duration, stop_to_final=run['stop_to_final'], requests=run['requests'],
        stop_to_terminal=events['terminal_finalization_started']['time']-run['stop'],
        terminal_to_publication=events['terminal_finalization_completed']['time']-events['terminal_finalization_started']['time'],
        terminal_embedding_calls=len(embeddings), terminal_encoder_intervals=sum(len(x['intervals']) for x in embeddings),
        terminal_embedding_audio_seconds=sum(x['audio_seconds'] for x in embeddings), saved_equal=run['saved_equal'], final=run['final']))
print(json.dumps(reports,indent=2))
