"""Report the shadow falsifier; no decoder calls or transcript retention."""
import json
from pathlib import Path

out = Path('evidence/mvpfix/wp12')
trace = [json.loads(line) for line in (out/'trace.jsonl').read_text().splitlines()]
runs = []
for path in sorted(out.glob('overlap-shadow-*.json')):
    run = json.loads(path.read_text())
    rows = [x for x in trace if x['arm'] == run['arm'] and run['start'] <= x['time'] <= run['stop'] + run['stop_to_final']]
    comparisons = [x for x in rows if x['kind'] == 'overlap_comparison']
    embeddings = [x for x in rows if x['kind'] == 'embedding']
    changed = sum(len(x['differences']) for x in comparisons)
    cross_lane = sum(x['cross_lane_assignments'] for x in comparisons)
    runs.append(dict(arm=run['arm'], case=run['case'], seconds=run['seconds'], requests=run['requests'],
        control_saved_equal=run['saved_equal'], control_status=run['status'],
        control_segments=sum(x['acoustic_segments'] for x in comparisons),
        changed_segments=changed, cross_lane_assignments=cross_lane,
        acoustic_terminal_embedding_audio_seconds=sum(x['audio_seconds'] for x in embeddings if x.get('reason')=='terminal'),
        candidate_embedding_audio_seconds=sum(x['audio_seconds'] for x in embeddings if x.get('reason')=='terminal_uncovered'),
        verdict='PASS' if len(comparisons)==2 and changed==0 and cross_lane==0 and run['saved_equal'] else 'FALSIFIED',
        lanes=comparisons))
print(json.dumps(runs, indent=2))
