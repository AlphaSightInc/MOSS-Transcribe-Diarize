"""Discovery-only cost; fixed 36k-word two-hour lane,120 holes,5 paired samples."""
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path[:0]=[str(ROOT),str(HERE)]
from moss_transcribe_diarize.app.gemini_provider import GeminiWord as Word
from moss_transcribe_diarize.app import gemini_coverage as product
EV=Path.home()/'Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-H2'
sys.path.insert(0,str(EV))
import candidate
spec=importlib.util.spec_from_file_location('moss_transcribe_diarize.app._h2_baseline', EV/'coverage-before.py')
before=importlib.util.module_from_spec(spec);sys.modules[spec.name]=before;spec.loader.exec_module(before)
words=[Word(str(i),'kept',i*3200,i*3200+2400) for i in range(36000) if i%300!=150]
live=[Word(str(i),'live',i*3200,i*3200+2400) for i in range(36000)]
measure=product.uncovered_runs if '--product' in sys.argv else candidate.discovery
rows=[]
for i in range(5):
    start=time.perf_counter();a=before.uncovered_runs(words,live);old=time.perf_counter()-start
    start=time.perf_counter();b=measure(words,live);new=time.perf_counter()-start
    assert a==b
    rows.append({'before_s':old,'after_s':new,'added_s':new-old})
result={'mode':'product' if '--product' in sys.argv else 'prototype','words':36000,'hours':2,'holes':len(a),'paired_samples':rows,'median_added_s':statistics.median(r['added_s'] for r in rows),'provider_usd':0,'limit':'discovery CPU only; no microphone/encoder/full Stop latency claim'}
(EV/(result['mode']+'-cost.json')).write_text(json.dumps(result,indent=1)+'\n')
print(json.dumps(result,indent=1))
assert result['median_added_s']<.1
