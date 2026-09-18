"""Offline evidence gate. Failures stop acceptance, never relax thresholds."""
import json
import sys
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv)>1 else 'evidence/mvpfix/wp26')
probe = json.loads((out/'prototype.json').read_text())
replay = json.loads((out/'production-replay.json').read_text())
survey = json.loads((out/'survey.json').read_text())
assert probe['verdict']=='PASS' and probe['decoder_calls']==0
assert [(p['start'],p['end'],p['assigned']) for p in probe['probes']]==[
    (149.61,153.75,'S01->speaker-0004'),(160.68,161.4,'S01->speaker-0004')]
assert replay['verdict']=='PASS' and replay['unassigned']==0
assert replay['segments']==56 and replay['unchanged_words_times_lanes']
assert len(replay['differences'])==len(replay['probes'])==2
assert all(p['lane']=='system' and p['reason']=='terminal_unassigned' for p in replay['probes'])
assert sum(p['bytes'] for p in replay['probes'])==155520
totals = {(r['package'],r['implementation']):r for r in survey['saved_store_totals']}
assert len(survey['databases'])==18
assert [(totals[key]['sessions'],totals[key]['segments'],totals[key]['unassigned_segments']) for key in
    [('wp12','accepted_overlap'),('wp17','accepted_overlap'),('wp12','historical_control')]]==[(3,127,2),(27,212,0),(19,476,64)]
print(json.dumps(dict(verdict='PASS', recovered_segments=2, recovered_words=16,
    cropped_audio_seconds=155520/32000, saved_census_sessions=49, decoder_calls=0)))
