"""Hold observed words fixed; change only the source-supported reference correction."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tests.e2e.verify_demo_lanes import reference_inputs,snapshot_segments
from moss_transcribe_diarize.lane_word_oracle import score_lanes
from moss_transcribe_diarize.phase2_acceptance import QUALITY_BOUNDS
raw=[json.loads(line) for line in (ROOT/'runs/wp17/surfaces.jsonl').read_text().splitlines()]
refs={lane:row['reference'] for lane,row in reference_inputs(1).items()}
results=[]
for case in ('alternation','overlap'):
 before=json.loads((ROOT/f'evidence/mvpfix/wp17/before-{case}.json').read_text());ident=before['meeting']
 snaps=[r['result'] for r in raw if r['path']==f'/api/live/sessions/{ident}/snapshot']
 saved=[r['result'] for r in raw if r['path']==f'/api/meetings/{ident}'][-1]
 surfaces={}
 for name,segs in [('pre_terminal',snapshot_segments(snaps[0])),('final',snapshot_segments(snaps[-1])),('reopened',saved['transcript']['segments'])]:
  surfaces[name]=score_lanes(segs,refs,max_wer=QUALITY_BOUNDS['immediate_wer' if name=='pre_terminal' else 'final_wer'][1])
 results.append({'case':case,'measurement':'rescore identical retained output; no new decoder run','surfaces':surfaces})
(ROOT/'evidence/mvpfix/wp17/reference-only-after.json').write_text(json.dumps(results,indent=2)+'\n')
for r in results:print(r['case'],{k:{'wer':{l:v['wer'] for l,v in s['lanes'].items()},'attribution':s['attribution_errors'],'duplication':s['duplication_count']} for k,s in r['surfaces'].items()})
