import os
import sys,json,wave
from pathlib import Path
from dataclasses import asdict
HERE=Path(os.environ["MOSS_DIFFERENTIAL_SCRATCH"])
ROOT=Path(os.environ["MOSS_DIFFERENTIAL_REPO"]);sys.path.insert(0,str(ROOT))
from moss_transcribe_diarize.app import phase2_web_cli
from moss_transcribe_diarize.app.live_coordinator import LiveCoordinator
from moss_transcribe_diarize.app.live_session import AudioFrame
ns={'__file__':str(HERE/'run_stack.py')}
exec((HERE/'run_stack.py').read_text().replace('phase2_web_cli.main(argv)',''),ns)
args=phase2_web_cli.parse_args(ns['argv'])
runtime=phase2_web_cli._build_live_runtime_factory(args,phase2_web_cli._build_file_runner(args))()
result=[]
for c in json.load(open(HERE/'mixing.json')):
 row={'case_id':c['case_id']}
 for mode,path in [('mono',ROOT/'evidence/live-policy-sweep-20260825/corpus'/c['case_id']/'audio.wav'),('mixed',HERE/'mixed'/c['case_id']/'audio.wav')]:
  with wave.open(str(path)) as w:pcm=w.readframes(w.getnframes())
  speech=runtime._speech_provider_factory(); endpoint=runtime._endpoint_policy_factory(); spans=[]; observations=[]
  for seq,start in enumerate(range(0,len(pcm),16000)):
   data=pcm[start:start+16000]; f=AudioFrame(sequence=seq,sample_count=len(data)//2,pcm=data)
   obs=speech.observe(frame=f,start_sample=start//2,end_sample=(start+len(data))//2)
   observations.extend([asdict(x) for x in obs])
   spans.extend(LiveCoordinator._observe_endpoint_with_policy(endpoint,obs,start//2,(start+len(data))//2))
  spans.extend(endpoint.stop())
  row[mode]={'spans':[asdict(x) for x in spans],'speech_observations':observations}
 a=row['mono'];b=row['mixed'];row['summary']={'mono_spans':len(a['spans']),'mixed_spans':len(b['spans']),'same_boundaries':a['spans']==b['spans'],'vad_decisions_changed':sum(x['speech_present']!=y['speech_present'] for x,y in zip(a['speech_observations'],b['speech_observations'])),'vad_observations':len(a['speech_observations'])}
 result.append(row);print(row['case_id'],row['summary'],flush=True)
(HERE/'endpoints.json').write_text(json.dumps(result,indent=2)+'\n')
