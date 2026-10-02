"""Apply H2 to explicit stress reconstructions; never infer unavailable word custody."""
import importlib.util
import json
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parents[3])]
from moss_transcribe_diarize.app import gemini_coverage as coverage
from run import patterns,state,EV,candidate,PRODUCT
SRC=EV.parent/'P73/r5b-stress/runs'
spec=importlib.util.spec_from_file_location('moss_transcribe_diarize.app._h2_before_stress', EV/'coverage-before.py')
before_rule=importlib.util.module_from_spec(spec);sys.modules[spec.name]=before_rule;spec.loader.exec_module(before_rule)
rows=[]
for cell in ['c5b','c7']:
    live=json.loads((SRC/cell/'saved-meeting-live.json').read_text())['transcript']['segments']
    saved=json.loads((SRC/cell/'saved-meeting.json').read_text())['transcript']['segments']
    if cell=='c7':
        before=next(r for r in live if r['source_lane']=='system' and r['start']==33.9)
        after=next(r for r in saved if r['source_lane']=='system' and 'got the got the' in r['text'])
        assert before['text'].endswith('Who got the truth?')
        names=['c7-after','c7-before']
    else:
        before=next(r for r in live if r['source_lane']=='system' and r['start']==270)
        a=next(r for r in saved if r['source_lane']=='system' and r['end']==270.400375)
        b=next(r for r in saved if r['source_lane']=='system' and r['start']==270.400375)
        assert a['text'].endswith('产品规划。') and b['text'].startswith('规划。大家好')
        after=[a,b];names=['c5b-grouped']
    for name in names:
        kept,witness=patterns()[name]
        baseline,old=before_rule.restore_witnessed_words(kept,witness)
        coverage.uncovered_runs=PRODUCT if '--product' in sys.argv else candidate.discovery
        output,new=coverage.restore_witnessed_words(kept,witness)
        rows.append({'cell':cell,'shape':name,'live_export':before,'saved_export':after,'provenance':'RECONSTRUCTION: exported text, injected per-word times/pre-H cleanup; exact real insertions unknown','cleanup':state(kept),'witness':state(witness),'before':state(baseline),'after':state(output),'before_restored':old,'after_restored':new})
        assert new==[] and output==tuple(kept)
flags={
 'F1':'c5b planning repetition: removed in grouped/character reconstruction; real insertion origin unobservable.',
 'F2':'c7 got-the repetition: removed in both before/after timing reconstructions; real insertion origin unobservable.',
 'F3':'c1 uh I I already live: preserved when clean-up omitted it; explicit clocked control restores3/3.',
 'F4':'c5a uh/I I/Who who who: no blanket stutter removal. If omitted and no adjacent equal whole run, restored. Actual pre-H clocks unavailable.',
 'F5':'c6 And uh And uh/together together/I I: same condition as F4; actual suppression UNKNOWN without pre-H words.',
 'F6':'c5b Chinese clauses repeat live at distinct times: no export rewrite; long clauses beyond12units are outside H2. Garbled mixed-script token unequal, unchanged.',
 'F7':'c6 collapsed rows/Yeah yeah: row spans cannot determine word clocks. H2 adds no projection fix; actual restore/suppression UNKNOWN.',
}
result={'audit_cells':8,'lanes':2,'original_system_restore_counter':205,'original_microphone_restore_counter':0,'flags':flags,'reconstructions':rows,'provider_usd':0,'limits':'No recalculated205 count or real stress pass claim: pre-H words/custody not retained.'}
mode='product' if '--product' in sys.argv else 'prototype'
(EV/(mode+'-stress.json')).write_text(json.dumps(result,ensure_ascii=False,indent=1)+'\n')
print(json.dumps({'mode':mode,'flags':flags,'reconstructed_shapes':len(rows)},ensure_ascii=False))
