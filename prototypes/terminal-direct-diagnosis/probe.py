import io,json,traceback,tempfile
from pathlib import Path
import soundfile as sf
from moss_transcribe_diarize.app.vllm_runner import VllmRunner
from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner
from moss_transcribe_diarize.app.runner_composition import build_terminal_finalizer
from moss_transcribe_diarize.app.live_transcript_convergence import TerminalDecodePlan,RollingStatus
from moss_transcribe_diarize.app.live_adapters import RunnerBoundedWavInference
from moss_transcribe_diarize.app.live_session import FrozenSpan
root=Path.home()/'.local/share/moss-transcribe-diarize/qualification-corpus/mono_javier_intro_50s'
paths=[root/'audio.wav'];assert len(paths)==1,paths
samples,sr=sf.read(paths[0],dtype='int16');assert sr==16000 and samples.ndim==1
current={}
class Probe(VllmRunner):
 def _build_fields(self,**kw):
  current['field_arguments']=kw
  return super()._build_fields(**kw)
 def _post_multipart(self,url,**kw):
  current['http_requests']=current.get('http_requests',0)+1
  current['request']={'url':url,'fields':kw['fields'],'wav_bytes':len(kw['file_bytes']),'sample_rate':16000,'timestamp_options':'absent','word_options':'absent'}
  return super()._post_multipart(url,**kw)
 def transcribe(self,path,**kw):
  current['runner_kwargs']=kw;current['source_wav_bytes']=Path(path).stat().st_size
  try:return super().transcribe(path,**kw)
  except Exception as e:
   current['exception_type']=type(e).__name__;current['exception_message']=str(e)
   current['traceback']=traceback.format_exc()
   chain=[];x=e
   while x is not None:
    chain.append({'type':type(x).__name__,'message':str(x),'http_status':getattr(x,'code',None)})
    x=x.__cause__
   current['exception_chain']=chain
   raise
runner=Probe(base_url='http://127.0.0.1:8000/v1',model='OpenMOSS-Team/MOSS-Transcribe-Diarize',timeout=1800)
finalizer=build_terminal_finalizer(runner=WindowedRunner(runner),prompt=None,max_length=16384,max_new_tokens=12000,decoding='greedy',temperature=1.0,max_length_cap=16384)
class Tape:
 def __init__(self,pcm):self.pcm=pcm
 def gaps(self,end):return ()
 def read(self,*,start_sample,end_sample):return self.pcm[start_sample*2:end_sample*2]
for duration in (50,2.5,10,30):
 current.clear();current.update(path='terminal',duration_seconds=duration,http_requests=0)
 pcm=samples[:int(duration*sr)].tobytes()
 plan=TerminalDecodePlan(epoch=0,end_sample=len(pcm)//2,rolling_through_sample=0,rolling_status=RollingStatus.ROLLING,windows_completed=0,windows_failed=0)
 result=finalizer.finalize(plan=plan,tape=Tape(pcm),base_text_revision_version=0)
 current['outcome']=str(result.outcome) if hasattr(result,'outcome') else str(result.accounting.outcome)
 print(json.dumps(current),flush=True)
current.clear();current.update(path='live',duration_seconds=2.5,http_requests=0)
span=FrozenSpan(id=1,epoch=0,start_sample=0,end_sample=40000,reason='direct-probe')
try:
 result=RunnerBoundedWavInference(runner,max_samples=40000).transcribe_pcm(span=span,pcm=samples[:40000].tobytes())
 current['outcome']='returned'
except Exception:current['outcome']='raised'
print(json.dumps(current),flush=True)
