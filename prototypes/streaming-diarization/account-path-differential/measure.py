import os
import os,sys,json,time,wave,math,asyncio
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(os.environ["MOSS_DIFFERENTIAL_REPO"]);sys.path.insert(0,str(ROOT))
import numpy as np,httpx
from moss_transcribe_diarize.phase2_acceptance_external import _load_surface_harness,_quality_surface_observations
from moss_transcribe_diarize.phase2_acceptance_replay import AccountCookieLiveReplayService,SESSION_COOKIE
from moss_transcribe_diarize.live_service_replay import InMemoryLiveReplayService,run_service_replay,ServiceReplayRtfFailure
from moss_transcribe_diarize.app.live_lane_contract import LiveLane,LiveV2Frame
from moss_transcribe_diarize.app.live_v2_session import LiveV2Session
from moss_transcribe_diarize.app.live_mixer import LiveCompatibilityMixer
from moss_transcribe_diarize.app import phase2_web_cli
HERE=Path(os.environ["MOSS_DIFFERENTIAL_SCRATCH"])
CORPUS=ROOT/'evidence/live-policy-sweep-20260825/corpus'
CASES=['mono_javier_intro_50s','interview_bill_ackman_60s','interview_keyu_jin_60s','interview_adam_frank_180s','discussion_jamie_dimon_180s','discussion_rtfl_90s']
surface=_load_surface_harness(ROOT);os.environ['SSL_CERT_FILE']=str(HERE/'cert.pem')
class Collector:
 def __init__(self):self.frames=[]
 def snapshot(self,sid):return SimpleNamespace(session=SimpleNamespace(next_frame_sequence=len(self.frames),version=len(self.frames)))
 def accept_frame(self,sid,frame,**kw):self.frames.append(frame);return SimpleNamespace(queued_item_ids=())
def mixed_audio(case):
 with wave.open(str(CORPUS/case/'audio.wav'),'rb') as w:pcm=w.readframes(w.getnframes())
 source=LiveV2Session(max_retained_samples=960000);mix=LiveCompatibilityMixer(max_output_samples=8000);out=Collector()
 for seq,start in enumerate(range(0,len(pcm),16000)):
  audio=pcm[start:start+16000];count=len(audio)//2
  for lane,blob,silent in [(LiveLane.SYSTEM,audio,False),(LiveLane.MICROPHONE,bytes(len(audio)),True)]:
   source.accept(LiveV2Frame(lane=lane,sequence=seq,capture_timestamp_ns=seq*500000000,device_epoch=0,silent=silent,discontinuity=False,sample_rate=16000,sample_count=count,pcm=blob))
  while mix.admit_available('probe',source,out) is not None:pass
 prestop=sum(f.sample_count for f in out.frames)
 while mix.admit_available('probe',source,out,final=True) is not None:pass
 mixed=b''.join(f.pcm for f in out.frames);assert len(pcm)==len(mixed)
 p=HERE/'mixed'/case;p.mkdir(parents=True,exist_ok=True)
 with wave.open(str(p/'audio.wav'),'wb') as w:w.setparams((1,2,16000,0,'NONE',''));w.writeframes(mixed)
 a=np.frombuffer(pcm,dtype='<i2').astype(float);b=np.frombuffer(mixed,dtype='<i2').astype(float)
 rms=lambda x:float(np.sqrt(np.mean(x*x)))
 expected=np.trunc(a/32768*(10**(-6/20))*32767).astype('<i2').tobytes()
 return {'case_id':case,'samples':len(a),'prestop_mixed_samples':prestop,'identical':pcm==mixed,'changed_samples':int(np.count_nonzero(a!=b)),'input_rms':rms(a),'mixed_rms':rms(b),'gain_db':20*math.log10(rms(b)/rms(a)),'exact_headroom_formula':expected==mixed}
mixing=[mixed_audio(c) for c in CASES];(HERE/'mixing.json').write_text(json.dumps(mixing,indent=2)+'\n');print('MIXING',json.dumps(mixing),flush=True)
ns={'__file__':str(HERE/'run_stack.py')};exec((HERE/'run_stack.py').read_text().replace('phase2_web_cli.main(argv)',''),ns)
args=phase2_web_cli.parse_args(ns['argv']);file_runner=phase2_web_cli._build_file_runner(args);factory=phase2_web_cli._build_live_runtime_factory(args,file_runner);runtime=factory()
class Mono(InMemoryLiveReplayService):
 async def stop(self,sid,deadline):return await self.runtime.stop(sid,300)
client=httpx.Client(verify=str(HERE/'cert.pem'),base_url='https://127.0.0.1:17862');client.post('/api/workspace/bootstrap').raise_for_status()
cookie=HERE/'measurement.cookie';cookie.write_text(client.cookies.get(SESSION_COOKIE));cookie.chmod(0o600)
account=AccountCookieLiveReplayService(base_url='https://127.0.0.1:17862',cookie_file=cookie,timeout_seconds=300)
result=json.loads((HERE/'results.json').read_text()) if (HERE/'results.json').exists() else {'source_revision':os.popen('git -C '+str(ROOT)+' rev-parse HEAD').read().strip(),'identity_manifest':str(args.live_provider_manifest),'paths':{'mono':'current shared LiveServiceRuntime, legacy mono adapter, no Account/v2','account':'own Phase-2 HTTPS stack17862, fresh workspace, speakers + silent microphone'},'rows':[]}
for case in CASES:
 for mode,service in [('mono',Mono(runtime)),('account',account)]:
  if any(x['case_id']==case and x['mode']==mode for x in result['rows']):continue
  started=time.monotonic();out=HERE/'runs'/mode/case
  captured=surface.SurfaceCaptureService(service,settle_timeout=30,poll_seconds=.25)
  desc=runtime.descriptor if mode=='mono' else account.descriptor()
  try:
   performance_failure=None
   try:
    run_service_replay(service=captured,audio_path=CORPUS/case/'audio.wav',out_dir=out,pace=1,max_pacing_lag=3,runs=1,expect_revision=desc.source_revision,expect_provider_hash=desc.provider_manifest_hash,expect_config_hash=desc.config_hashes.combined_config_hash)
   except ServiceReplayRtfFailure as e:
    performance_failure=str(e)
    assert all(x in captured.captures for x in ['pre_stop_immediate','pre_stop_settled','post_stop_final'])
   (out/'captures.json').write_text(json.dumps(captured.captures))
   ref=CORPUS/case/'reference.jsonl';duration=surface._wav_duration(CORPUS/case/'audio.wav') if hasattr(surface,'_wav_duration') else mixing[CASES.index(case)]['samples']/16000
   counts=_quality_surface_observations(captured.captures,reference_speaker_count=len({json.loads(x)['speaker'] for x in ref.read_text().splitlines()}))
   scores={name:surface.score_surface(surface.Case(case,CORPUS/case,ref),surface.transcript_rows(cap['snapshot'],duration)) for name,cap in captured.captures.items()}
   row={'case_id':case,'mode':mode,'performance_failure':performance_failure,'elapsed_seconds':time.monotonic()-started,'scores':scores,'surface_observations':counts}
   result['rows'].append(row);(HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('CASE',case,mode,json.dumps(row),flush=True)
  except Exception as e:
   (out/'captures.json').write_text(json.dumps(captured.captures))
   result['rows'].append({'case_id':case,'mode':mode,'error':str(e)});(HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('FAILED',case,mode,str(e),flush=True)
account.close();client.close()
