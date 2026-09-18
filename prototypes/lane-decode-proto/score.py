"""Counts only. Ordered edit counts use supplied overlapping reference rows;
rows crossing capture boundaries are explicitly reported, never prorated by word count.
"""
import json,re,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CORPUS=Path('/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus')
OUT=ROOT/'evidence/mvpfix/wp1'
def words(s):return re.findall(r'[a-z0-9]+',s.lower())
def edits(ref,hyp):
    previous=[(j,0,0,j) for j in range(len(hyp)+1)]
    for i,r in enumerate(ref,1):
        row=[(i,0,i,0)]
        for j,h in enumerate(hyp,1):
            a,b,c=previous[j-1],previous[j],row[j-1]
            row.append(min((a[0]+(r!=h),a[1]+(r!=h),a[2],a[3]),(b[0]+1,b[1],b[2]+1,b[3]),(c[0]+1,c[1],c[2],c[3]+1)))
        previous=row
    total,sub,omit,add=previous[-1]
    return dict(reference_words=len(ref),hypothesis_words=len(hyp),substitutions=sub,omissions=omit,additions=add,wer=total/len(ref) if ref else None)
surfaces={p.name.removesuffix('-surfaces.json'):json.loads(p.read_text()) for p in (HERE/'scratch').glob('*-surfaces.json')}
rows=[]
for run_id,data in surfaces.items():
    meta=json.loads((OUT/f'{run_id}.json').read_text())
    case=meta['case']
    final=data['final']['effective_transcript'];pre=data['pre']['effective_transcript']
    saved=data['meeting']['transcript']['segments']
    owners={}
    for s in final:
        if s.get('canonical_speaker'):owners.setdefault(s['canonical_speaker'],set()).add(s.get('source_lane'))
    row={'case':case,'run_id':run_id,'prototype':meta.get('prototype','historical-v1-v2-v4'),'saved_words':sum(len(words(s['text'])) for s in saved),'saved_segments':len(saved),'saved_has_lane_tags':all('source_lane' in s for s in saved),'saved_matches_final_text_and_identity':[(s['text'],s.get('speaker_entity_id')) for s in saved]==[(s['text'],s.get('canonical_speaker')) for s in final],'lanes':{}}
    for lane,clip in [('system','interview_bill_ackman_60s'),('microphone','interview_bill_ackman_60s' if case=='same' else 'interview_keyu_jin_60s')]:
        reference=[json.loads(x) for x in (CORPUS/clip/'reference.jsonl').read_text().splitlines()]
        # Full reference text required by Fable; omissions include unplayed audio.
        if (case=='system_control' and lane=='microphone') or (case=='mic_control' and lane=='system') or (case in ('zero','noise') and lane=='microphone'):
            reference=[]
        ref=words(' '.join(r['text'] for r in reference))
        final_words=words(' '.join(s['text'] for s in final if s.get('source_lane')==lane))
        pre_words=words(' '.join(s['text'] for s in pre if s.get('source_lane')==lane))
        saved_words=words(' '.join(s['text'] for s,f in zip(saved,final,strict=True) if f.get('source_lane')==lane)) if row['saved_matches_final_text_and_identity'] else []
        control=surfaces.get('system_control' if lane=='system' or case=='same' else 'mic_control')
        vocab=set(words(' '.join(s['text'] for s in control['final']['effective_transcript'] if s.get('source_lane')==('system' if lane=='system' or case=='same' else 'microphone')))) if control else set()
        row['lanes'][lane]={'final_words':len(final_words),'saved_words_via_exact_surface_correspondence':len(saved_words),'attribution_method':'ordered saved/final text-and-identity equality permits positional lane correspondence; not persisted lane provenance','final_vs_full_reference':edits(ref,final_words),'pre_vs_full_reference':edits(ref,pre_words),'reference_boundary_crossing_rows':sum(r['end']>meta['seconds'] for r in reference),'wer_limitation':'full reference includes unplayed audio; omissions are not all decoder loss','saved_vs_full_reference':edits(ref,saved_words),'control_unique_vocabulary':len(vocab) if control else None,'retained_unique_vocabulary':len(vocab&set(final_words)) if control else None,'pre_retained_unique_vocabulary_vs_control':len(vocab&set(pre_words)) if control else None,'control_gain':1.0,'control_capture_seconds':24,'same_capture_extent':meta['seconds']==24,'pre_unique_vocabulary':len(set(pre_words)),'pre_vocabulary_retained_at_final':len(set(pre_words)&set(final_words)),'unattributed_words':sum(len(words(s['text'])) for s in final if s.get('source_lane')==lane and not s.get('canonical_speaker'))}
    rows.append(row)
lat=[json.loads(x) for x in (HERE/'scratch/latencies.jsonl').read_text().splitlines()]
queuepath=HERE/'scratch/queues.jsonl';queues=[json.loads(x) for x in queuepath.read_text().splitlines()] if queuepath.exists() else []
summary={'cases':rows,'requests':len(lat),'request_latency_seconds':{'min':min(x['seconds'] for x in lat),'median':statistics.median(x['seconds'] for x in lat),'max':max(x['seconds'] for x in lat)},'arbiter_max':{k:max((int(q.get(k,0)) for q in queues),default=0) for k in ('live_canonical','live_refinement','batch')},'pending_signals_max':max((q.get('pending_signals',0) for q in queues),default=0),'pending_signals_scope':'instrumented v4 only; unknown earlier','same_v1_terminal_identity':'time projection; superseded by voice evidence in v2','production_fix':'not implemented: full prototype verdict pending'}
sp=HERE/'scratch/spans.jsonl'
spans=[json.loads(x) for x in sp.read_text().splitlines()] if sp.exists() else []
summary['span_latency_by_samples']={}
for n in sorted({r['samples'] for r in spans}):
    times=[r['seconds'] for r in spans if r['samples']==n]
    summary['span_latency_by_samples'][str(n)]={'n':len(times),'min':min(times),'median':statistics.median(times),'max':max(times)}
summary['request_counts_by_case']={}
last=0
for name,count in [('same',26),('parity',26),('system_control',13),('mic_control',13),('mic-10',26),('mic-15',26),('system-10',26),('system-15',26),('stop_mid',14)]:
    if name not in surfaces:continue
    summary['request_counts_by_case'][name]={'first':last+1,'last':last+count,'count':count,'per_capture_minute':count*60/json.loads((OUT/f'{name}.json').read_text())['seconds'],'assignment':'serial case boundaries; checked against request log'}
    last+=count
for name,data in surfaces.items():
    meta=json.loads((OUT/f'{name}.json').read_text())
    if 'request_count' in meta:
        summary['request_counts_by_case'][name]={'first':meta['first_request'],'last':meta['last_request'],'count':meta['request_count'],'per_capture_minute':meta['request_count']*60/meta['seconds'],'assignment':'measured cumulative request counters before and after single meeting'}
        last+=meta['request_count']
summary['request_case_count_agrees']=last==len(lat)
(OUT/'requests.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in lat))
(OUT/'spans.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in spans))
(OUT/'scores.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({'cases':len(rows),'requests':len(lat),'saved_matches':[r['saved_matches_final_text_and_identity'] for r in rows],'arbiter_max':summary['arbiter_max']}))
