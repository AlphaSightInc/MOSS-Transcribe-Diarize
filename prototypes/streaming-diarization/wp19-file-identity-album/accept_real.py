"""WP19 real decoder acceptance. Serial, own tunnel 18119, 18 requests total.
Per-segment truth is maximum temporal reference overlap; canonical-to-truth mapping
is ONE global one-to-one maximum overlap assignment, never per-window remapping.
Silence/uncovered time excluded from duration accuracy, reported separately.
Words remain only in ignored scratch. Identity accuracy is not transcript accuracy.
"""
from collections import defaultdict
from dataclasses import asdict
import argparse
import json
from pathlib import Path
import time
import urllib.request
import wave
import numpy as np
from scipy.optimize import linear_sum_assignment
from moss_transcribe_diarize.app.file_identity_album import AlbumIdentityResolver
from moss_transcribe_diarize.app.runner_composition import build_file_runner
from moss_transcribe_diarize.app.windowed_transcription import plan_windows, extract_window_wav, _stitch_segments
from moss_transcribe_diarize.transcript_parser import parse_transcript

ROOT=Path('.wp19runtime'); OUT=Path('evidence/mvpfix/wp19')
CORPUS=Path('/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus')
NAMES=['interview_bill_ackman_60s','interview_keyu_jin_60s']

def score(segments,minutes):
    refs=[]
    for i in range(minutes):
        for line in (CORPUS/NAMES[i%2]/'reference.jsonl').read_text().splitlines():
            r=json.loads(line); refs.append(dict(start=r['start']+i*60,end=r['end']+i*60,speaker=r['speaker']))
    truth=sorted({r['speaker'] for r in refs}); pred=sorted({s.speaker for s in segments if s.speaker != 'S00'})
    rows=[]; matrix=np.zeros((len(pred),len(truth)))
    for index,s in enumerate(segments):
        overlaps=defaultdict(float)
        for r in refs:
            overlap=max(0.,min(s.end,r['end'])-max(s.start,r['start']))
            overlaps[r['speaker']]+=overlap
        overlaps={k:v for k,v in overlaps.items() if v>0}
        if s.speaker in pred:
            for t,amount in overlaps.items(): matrix[pred.index(s.speaker),truth.index(t)]+=amount
        rows.append(dict(index=index,start=s.start,end=s.end,predicted=s.speaker,overlaps=overlaps,truth=max(overlaps,key=overlaps.get) if overlaps else None))
    a,b=linear_sum_assignment(-matrix)
    mapping={pred[i]:truth[j] for i,j in zip(a,b)}
    for r in rows: r['correct']=r['truth'] is not None and mapping.get(r['predicted'])==r['truth']
    denominator=sum(r['truth'] is not None for r in rows)
    total=sum(sum(r['overlaps'].values()) for r in rows)
    correct=sum(r['overlaps'].get(mapping.get(r['predicted']),0) for r in rows)
    return dict(truth_voices=len(truth),identities=len(pred),mapping=mapping,segments=len(rows),scored_segments=denominator,correct_segments=sum(r['correct'] for r in rows),segment_accuracy=sum(r['correct'] for r in rows)/denominator,truth_overlap_seconds=total,correct_seconds=correct,duration_accuracy=correct/total,unattributed_segments=sum(s.speaker=='S00' for s in segments),unscored_segments=len(rows)-denominator,rows=rows)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--decode',action='store_true'); p.add_argument('--minutes',type=int,nargs='+',choices=[6,30],default=[6,30]); p.add_argument('--output',type=Path,default=OUT); args=p.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    runner=build_file_runner(model_path='unused',device='cpu',dtype='bf16',backend='vllm',vllm_base_url='http://127.0.0.1:18119/v1',vllm_model='OpenMOSS-Team/MOSS-Transcribe-Diarize',vllm_api_key='EMPTY',vllm_timeout=1800)
    resolver=AlbumIdentityResolver()
    requests=0
    for minutes in args.minutes:
        folder=ROOT/f'real-{minutes}'; folder.mkdir(exist_ok=True)
        source=ROOT/'media/long.wav'
        windows=plan_windows(minutes*60,window_seconds=150,stride_seconds=120)
        paths=[]; groups=[]; decodes=[]
        for w in windows:
            path=folder/f'window-{w.index}.wav'; paths.append(path)
            extract_window_wav(source,path,start_seconds=w.start,duration_seconds=w.duration)
            cache=folder/f'decode-{w.index}.json'
            if args.decode:
                metrics=urllib.request.urlopen('http://127.0.0.1:18119/metrics').read().decode()
                queue=[s for s in metrics.splitlines() if s.startswith(('vllm:num_requests_running{','vllm:num_requests_waiting{'))]
                t=time.monotonic(); result=runner._decode_window(path,w,dict(max_length=16384,max_new_tokens=12000,decoding='greedy')); requests+=1
                cache.write_text(json.dumps(result.to_dict()))
                info=dict(window=asdict(w),queue_before=queue,elapsed=time.monotonic()-t,tokens=result.generated_tokens,requests=requests)
                decodes.append(info); print(json.dumps({'minutes':minutes,**info}),flush=True)
            groups.append(parse_transcript(json.loads(cache.read_text())['text']))
        t=time.monotonic(); result=resolver.resolve(windows,groups,window_audio_paths=paths); elapsed=time.monotonic()-t
        stitched=_stitch_segments(windows,result.relabeled_results)
        scored=score(stitched,minutes)
        scored.update(resolver_seconds=elapsed,window_count=len(windows),decodes=decodes,summary=result.summary,diagnostics=result.diagnostics,text_time_unchanged=all((a.start,a.end,a.text)==(b.start,b.end,b.text) for ga,gb in zip(groups,result.relabeled_results) for a,b in zip(ga,gb)))
        (args.output/f'accept-real-{minutes}.json').write_text(json.dumps(scored,indent=2)+'\n')
        (folder/'segments.json').write_text(json.dumps([asdict(s) for s in stitched]))
        print(json.dumps({k:v for k,v in scored.items() if k not in ('diagnostics','rows','decodes')}),flush=True)
if __name__=='__main__': main()
