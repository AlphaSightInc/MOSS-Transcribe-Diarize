"""Counts only from retained stress evidence; never infer hidden abstentions."""
import json,sys
from pathlib import Path
from collections import Counter,defaultdict
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from moss_transcribe_diarize.lane_word_oracle import score_lanes,normalize_segment
OUT=ROOT/'evidence/mvpfix/wp7';scratch=ROOT/'.wp7runtime'
results=json.loads((OUT/'stress-results.json').read_text())
events=[json.loads(x) for x in (OUT/'stress-events.jsonl').read_text().splitlines()]
albums=defaultdict(list)
for line in (OUT/'album-events.jsonl').read_text().splitlines():
 r=json.loads(line);albums[r['album']].append(r)
summary=[]
assert len(albums)==len(results),(len(albums),len(results))
# Every sequential meeting creates exactly one causal album in this harness;
# cardinality and span-id restart checked here, not assumed for arbitrary runs.
for result,(album,observations) in zip(results,albums.items()):
 assert observations[0]['span_id']==0
 states=[r for r in events if r['kind']=='snapshot' and r.get('case')==result['case']]
 deferred={dict(r['identity']['diagnostics']).get('span_id') for r in states if dict(r['identity']['diagnostics']).get('deferred_births')}
 summary.append(dict(case=result['case'],status=result['status'],births=len(result['identity']['canonical_speakers']),
   final_used_ids=sorted({k for v in result['score']['ids_by_truth'].values() for k in v if k}),
   final_switches=result['score']['id_switches'],album=album,album_dispositions=dict(Counter(r['disposition'] for r in observations)),
   observed_deferred_spans=len(deferred),abstentions='not inferable from published identity snapshots',
   recognition_seconds=result['recognition_seconds'],stop_seconds=result['stop_seconds']))
# The initial two complete utterances have full references. Later repeated six
# seconds has no word timestamps, so is excluded rather than inventing its text.
raw=json.loads((scratch/'alternating.json').read_text());rows=raw['saved']['transcript']['segments']
selected=[r for r in rows if normalize_segment(r)['end']<=54]
refs={k:json.loads((ROOT/'evidence/live-policy-sweep-20260825/corpus'/name/'reference.jsonl').read_text().splitlines()[0])['text'] for k,name in [('system','interview_bill_ackman_60s'),('microphone','interview_keyu_jin_60s')]}
oracle=score_lanes(selected,refs,max_wer=.15,lane_switches=(29,))
report=dict(cases=summary,word_oracle=oracle,word_oracle_scope='First 54 s complete-reference input; output selected by segment end <=54. Boundary words may be omitted by this selection. Voice grouping via lexical inference; both voices actually supplied on system lane.',
 request_count=len((scratch/'stress/requests.jsonl').read_text().splitlines()))
(OUT/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
