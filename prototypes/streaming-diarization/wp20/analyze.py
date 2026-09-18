"""Counts-only audit of retained producer and shadow replay evidence. No new requests."""
import json,sys
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from moss_transcribe_diarize.transcript_parser import parse_transcript
from moss_transcribe_diarize.lane_word_oracle import words,distance
from tests.e2e.verify_demo_lanes import reference_inputs,snapshot_segments
S=ROOT/'runs/wp20';O=ROOT/'evidence/mvpfix/wp20'
trace=[json.loads(x) for x in (S/'trace.jsonl').read_text().splitlines()]
replay=[json.loads(x) for x in (S/'replay.jsonl').read_text().splitlines()]
surfaces=[json.loads(x) for x in (S/'surfaces.jsonl').read_text().splitlines()]
quality=[json.loads(p.read_text()) for p in sorted(O.glob('baseline-*.json'))]
durations=json.loads((O/'durations/stress-results.json').read_text())
refs={lane:row['reference'] for lane,row in reference_inputs(.03).items()}
def text(row):return ' '.join(s.text for s in parse_transcript(row['text']))
def score(ref,rows):return distance(words(ref),words(' '.join(text(r) for r in rows)))
def errors(s):return sum(s[k] for k in ('substitutions','omissions','additions'))
summary=[];details=[]
for case in quality+durations:
    sess=case['meeting'];is_quality='surfaces' in case
    snaps=[r['result']['snapshot'] for r in surfaces if sess in r['path'] and 'snapshot' in r['path']]
    pre=next((r for r in reversed(snaps) if r['session']['status']=='active'),None)
    pending=max((r['pending_work_items'] for r in snaps),default=0)
    for lane in ('system','microphone'):
        original=[r for r in trace if r['session']==sess and r['kind']=='canonical' and lane in r['lanes']]
        local=[r for r in replay if r['session']==sess and r['lane']==lane and r['arm']=='lane-local']
        same=[r for r in replay if r['session']==sess and r['lane']==lane and r['arm']=='same-boundary-alone']
        ownpcm=(S/f'{sess}-{lane}.pcm').read_bytes()
        active_local=[r for r in local if any(ownpcm[r['span']['start_sample']*2:r['span']['end_sample']*2])]
        mixed_edges=[(r['span']['start_sample'],r['span']['end_sample']) for r in original]
        local_edges=[(r['span']['start_sample'],r['span']['end_sample']) for r in active_local]
        result=dict(case=('reference-' if is_quality else '')+case['case'],meeting=sess,lane=lane,
            stop_seconds=case['stop_seconds'],max_observed_pending_work_items=pending,
            mixed_nonzero_spans=len(original),local_nonzero_spans=len(active_local),
            same_nonzero_boundaries=mixed_edges==local_edges,
            local_vs_mixed_text_difference=score(' '.join(text(r) for r in original),local),
            same_boundary_alone={stage:dict(windows=sum(r['stage']==stage for r in same),changed=sum(r['stage']==stage and errors(r['difference'])>0 for r in same),edits=sum(errors(r['difference']) for r in same if r['stage']==stage)) for stage in ('canonical','rolling','terminal')},
            per_span_ground_truth_wer='unmeasured: no word-level reference timestamps',
            local_runtime_latency='unmeasured: shadow replay is not a scheduling intervention')
        if is_quality:
            cutoff=pre['session']['committed_samples']
            result['pre_snapshot']={k:pre['session'][k] for k in ('accepted_samples','committed_samples','frozen_until_sample','canonical_through_sample')}
            result['wer']={
                'published_immediate':case['surfaces']['pre_terminal']['lanes'][lane],
                'published_final':case['surfaces']['final']['lanes'][lane],
                'canonical_all':score(refs[lane],original),
                'canonical_pre_committed':score(refs[lane],[r for r in original if r['span']['end_sample']<=cutoff]),
                'same_boundary_alone_canonical_all':score(refs[lane],[r for r in same if r['stage']=='canonical']),
                'local_canonical_all':score(refs[lane],local),
                'terminal_alone':score(refs[lane],[r for r in same if r['stage']=='terminal'])}
        summary.append(result)
        details.append(dict(case=result['case'],lane=lane,mixed=[dict(span=r['span'],words=len(words(text(r)))) for r in original],local=[dict(span=r['span'],words=len(words(text(r))),reused=r['reused_exact_pcm_and_reason']) for r in local],replay=[dict(stage=r['stage'],span=r['span'],difference=r['difference'],elapsed=r['elapsed']) for r in same]))
(O/'stage-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(O/'span-details.json').write_text(json.dumps(details,indent=2)+'\n')
for row in summary:print(json.dumps(row))
