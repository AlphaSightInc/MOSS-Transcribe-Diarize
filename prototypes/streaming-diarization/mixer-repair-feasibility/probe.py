import sys,json,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
import argparse,numpy as np
from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig,_identity_encoder,_identity_preparer
from moss_transcribe_diarize.app.live_session import FrozenSpan,LiveIdentitySnapshot
from moss_transcribe_diarize.app.live_identity_album import cosine_similarity
from moss_transcribe_diarize.app.live_mixer import _HEADROOM_GAIN
parser=argparse.ArgumentParser()
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--manifest',type=Path,default=Path.home()/'.local/share/moss-transcribe-diarize/live/live-provider-manifest.json')
args=parser.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
config=LiveProviderBundleConfig.from_manifest(args.manifest)
assert config.preflight().available
encoder=_identity_encoder(config)
case='interview_adam_frank_180s'
source=ROOT/'evidence/live-policy-sweep-20260825/corpus'/case/'audio.wav';mixed=out/'mixed.wav'
with wave.open(str(source)) as w: original_pcm=w.readframes(w.getnframes())
values=np.frombuffer(original_pcm,dtype='<i2').astype(float)
attenuated=np.trunc(values/32768*_HEADROOM_GAIN*32767).astype('<i2').tobytes()
with wave.open(str(mixed),'wb') as w:
 w.setparams((1,2,16000,0,'NONE',''));w.writeframes(attenuated)
observations=json.load(open(ROOT/'prototypes/streaming-diarization/account-path-differential/results/identity-windows.json'))
results=[]
for mode,audio,windows in [('baseline_mixed',mixed,'account'),('raw_same_windows',source,'account'),('mono_windows',source,'mono')]:
 preparer=_identity_preparer(config,encoder=encoder);provider=preparer.evidence_provider;state=LiveIdentitySnapshot();trace=[]
 with wave.open(str(audio)) as w:pcm=w.readframes(w.getnframes())
 rows=next(x['observations'] for x in observations if x['case_id']==case and x['mode']==windows)
 original=provider.score
 def score(**kw):
  value=original(**kw);provider.last_scores=value;return value
 provider.score=score
 for row in rows:
  if row['start_sample']>686240:break
  span=FrozenSpan(row['span_id'],0,row['start_sample'],row['end_sample'],'hard_cap' if row['end_sample']-row['start_sample']==40000 else 'endpoint')
  if not row['units']:continue
  text=''.join(f'[{start}][S{i+1:02}]observed interval[{end}]' for i,u in enumerate(row['units']) for start,end in u['intervals_seconds'])
  prepared=preparer.prepare(span=span,pcm=pcm[span.start_sample*2:span.end_sample*2],transcript=text,base_snapshot=state)
  trace.append({'span_id':span.id,'start_sample':span.start_sample,'end_sample':span.end_sample,'score':[e.score for e in provider.last_scores],'before':len(state.canonical_speakers),'after':len(prepared.proposed_snapshot.canonical_speakers),'status':prepared.status})
  state=prepared.proposed_snapshot
 results.append({'mode':mode,'trace':trace});(out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
 print(mode,[x for x in trace if x['start_sample']<686240 and x['end_sample']>640000],flush=True)
v1=encoder.embed(source,[(41.42,42.64)]);v2=encoder.embed(mixed,[(41.42,42.64)])
print('same short window raw-vs-mixed cosine',cosine_similarity(v1,v2),flush=True)
(out/'same-window.json').write_text(json.dumps({'raw_vs_mixed_cosine':cosine_similarity(v1,v2),'interval':[41.42,42.64]},indent=2)+'\n')
