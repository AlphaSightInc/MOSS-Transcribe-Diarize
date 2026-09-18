"""Verify WP20 retained counts against local raw measurements; no decoder calls."""
import json, subprocess, sys
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from moss_transcribe_diarize.lane_word_oracle import words,distance
from moss_transcribe_diarize.transcript_parser import parse_transcript
S=ROOT/'runs/wp20';O=ROOT/'evidence/mvpfix/wp20'
def read(p):return json.loads(p.read_text())
def lines(p):return [json.loads(x) for x in p.read_text().splitlines()]
def errors(d):return sum(d[k] for k in ('substitutions','omissions','additions'))
summary=read(O/'stage-summary.json');details=read(O/'span-details.json')
assert len(summary)==len(details)==12
# Re-derive aggregate files from original traces: stale/manually edited counts must fail.
subprocess.run([sys.executable,str(ROOT/'prototypes/streaming-diarization/wp20/analyze.py')],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
assert summary==read(O/'stage-summary.json') and details==read(O/'span-details.json')
raw=lines(S/'replay.jsonl');trace=lines(S/'trace.jsonl')
for r in raw:
    span=r['span'];assert 0<=span['start_sample']<span['end_sample']
    if r['stage']=='canonical':assert span['end_sample']-span['start_sample']<=40000
    if r['arm']=='same-boundary-alone':
        texts=[' '.join(s.text for s in parse_transcript(r[k])) for k in ('baseline_text','text')]
        assert r['difference']==distance(*map(words,texts))
for session in {r['session'] for r in raw}:
    for lane in ('system','microphone'):
        spans=[r['span'] for r in raw if r['arm']=='lane-local' and r['session']==session and r['lane']==lane]
        assert spans[0]['start_sample']==0
        assert all(a['end_sample']==b['start_sample'] for a,b in zip(spans,spans[1:]))
        assert spans[-1]['end_sample']*2==(S/f'{session}-{lane}.pcm').stat().st_size
same=[r for r in raw if r['arm']=='same-boundary-alone']
stages={stage:{'windows':sum(r['stage']==stage for r in same),'changed':sum(r['stage']==stage and errors(r['difference'])>0 for r in same)} for stage in ('canonical','rolling','terminal')}
assert stages=={'canonical':{'windows':137,'changed':0},'rolling':{'windows':30,'changed':0},'terminal':{'windows':12,'changed':1}}
for lane,n in [('system',18),('microphone',9)]:
    r=next(r for r in summary if r['case']=='reference-overlap' and r['lane']==lane)
    assert r['same_nonzero_boundaries']
    assert errors(r['wer']['canonical_all'])==errors(r['wer']['local_canonical_all'])==n
quality=[read(O/f'baseline-{c}.json') for c in ('alternation','overlap')]
durations=read(O/'durations/stress-results.json')
assert all(r['status']=='completed' for r in quality+durations)
assert all(r['finalization_status']=='final' and not r['passed'] for r in quality)
assert all(r['finalization']=='final' and r['failure'] is None for r in durations)
assert all(r['surfaces']['final']==r['surfaces']['reopened'] for r in quality)
padding=read(O/'padding-control.json')
a,b=[(S/f"{r['meeting']}-system.pcm").read_bytes() for r in quality]
assert a[:len(b)]==b and not any(a[len(b):])
assert padding['speech_prefix_equal_samples']==len(b)//2==464000
assert padding['alternation_extra_zero_samples']==(len(a)-len(b))//2==400000
assert [errors(r['score']) for r in padding['records']]==[9,13,11,13]
requests=sum(len(lines(O/f'{name}-requests.jsonl')) for name in ('stack','replay'))
assert requests==390<=500
# Evidence work must not silently become production or policy work.
assert not subprocess.check_output(['git','diff','de35ef365724caad47c407bd41c34e21182d20c7','--','moss_transcribe_diarize','tests','frontend'],cwd=ROOT)
print(json.dumps(dict(evidence_consistency='PASS',prototype_promotion='REJECTED_NO_OVERLAP_WIN',product_quality='FAIL',captures=6,lanes=12,standalone_replays=stages,requests=requests,request_budget=500,canonical_hard_cap_samples=40000,local_scheduling='UNMEASURED',per_span_ground_truth_wer='UNMEASURED'),indent=2))
