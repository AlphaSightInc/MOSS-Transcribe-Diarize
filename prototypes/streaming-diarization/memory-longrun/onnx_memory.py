"""WP22 throwaway intervention: same ONNX inputs, CPU arena on versus off.
One command: COMMON Python <this-file> --arena on|off --output <json>
Falsifier: arena off fails to reduce retained RSS, changes vectors, or is too slow.
No production policy values changed. Public interview audio; vectors stay in scratch.
"""
import argparse,gc,json,os,subprocess,time
from pathlib import Path
import numpy as np
import onnxruntime as ort
from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig,_identity_encoder
from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder
p=argparse.ArgumentParser();p.add_argument('--arena',choices=['on','off','shrink','no-pattern','production'],required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--varying',action='store_true');a=p.parse_args()
config=LiveProviderBundleConfig.from_manifest(Path.home()/'.local/share/moss-transcribe-diarize/live/live-provider-manifest.json')
adapter=_identity_encoder(config)
def factory(*args,**kw):
    kw['sess_options'].enable_cpu_mem_arena=a.arena!='off'
    kw['sess_options'].enable_mem_pattern=a.arena!='no-pattern'
    session=ort.InferenceSession(*args,**kw)
    if a.arena=='shrink':
        original=session.run
        opts=ort.RunOptions();opts.add_run_config_entry('memory.enable_memory_arena_shrinkage','cpu:0')
        session.run=lambda outputs,inputs:original(outputs,inputs,opts)
    return session
encoder=_OnnxWeSpeakerEmbedder(adapter.state_path,device='cpu',session_factory=None if a.arena=='production' else factory)
clip=Path('/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/interview_bill_ackman_60s/audio.wav')
rows=[];vectors=[]
def record(action,**kw):
    gc.collect();r=dict(action=action,arena=a.arena,rss_bytes=int(subprocess.check_output(['ps','-o','rss=','-p',str(os.getpid())],text=True))*1024,**kw);rows.append(r);print(json.dumps(r),flush=True);a.output.write_text(json.dumps(rows,indent=2)+'\n')
encoder.load();record('loaded')
for cycle in range(2 if a.varying else 3):
    for seconds in ([.5+i*.237 for i in range(40)] if a.varying else [2.5,10,2.5,30,2.5,10]):
        start=time.monotonic();vectors.append(encoder.embed(clip,[(0,seconds)]));record('embedded',cycle=cycle,seconds=seconds,elapsed=time.monotonic()-start)
np.save(Path('.wp22')/('vectors-'+a.arena+('-varying' if a.varying else '')+'.npy'),np.asarray(vectors))
encoder._session=None;record('session_destroyed')
