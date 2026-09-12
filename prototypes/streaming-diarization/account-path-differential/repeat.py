import os
import sys,json,time,os
from pathlib import Path
HERE=Path(os.environ["MOSS_DIFFERENTIAL_SCRATCH"]);ROOT=Path(os.environ["MOSS_DIFFERENTIAL_REPO"]);sys.path.insert(0,str(ROOT))
from moss_transcribe_diarize.app import phase2_web_cli
from moss_transcribe_diarize.app.live_session import FrameAck
from moss_transcribe_diarize.app.live_service_runtime import LiveServiceFrameResult
from moss_transcribe_diarize.phase2_acceptance_replay import AccountCookieLiveReplayService
from moss_transcribe_diarize.live_service_replay import InMemoryLiveReplayService,run_service_replay,ServiceReplayRtfFailure
from moss_transcribe_diarize.phase2_acceptance_external import _load_surface_harness,_quality_surface_observations
surface=_load_surface_harness(ROOT);os.environ['SSL_CERT_FILE']=str(HERE/'cert.pem')
ns={'__file__':str(HERE/'run_stack.py')};exec((HERE/'run_stack.py').read_text().replace('phase2_web_cli.main(argv)',''),ns)
args=phase2_web_cli.parse_args(ns['argv']);runtime=phase2_web_cli._build_live_runtime_factory(args,phase2_web_cli._build_file_runner(args))()
class Mono(InMemoryLiveReplayService):
 async def stop(self,sid,deadline):return await self.runtime.stop(sid,300)
class Hold(Mono):
 def create(self):
  self.held=None;self.offset=0;return super().create()
 def accept_frame(self,sid,frame):
  previous=self.held;self.held=frame
  queued=() if previous is None else self.runtime.accept_frame(sid,previous).queued_item_ids
  start=self.offset;self.offset+=frame.sample_count
  return LiveServiceFrameResult(FrameAck(frame.sequence,start,self.offset,self.offset,frame.sample_count,()),queued,self.runtime.snapshot(sid))
 async def stop(self,sid,deadline):
  if self.held is not None:self.runtime.accept_frame(sid,self.held);self.held=None
  return await super().stop(sid,deadline)
account=AccountCookieLiveReplayService(base_url='https://127.0.0.1:17862',cookie_file=HERE/'measurement.cookie',timeout_seconds=300)
corpus=ROOT/'evidence/live-policy-sweep-20260825/corpus'
plans=[('mono_javier_intro_50s','account_repeat',account,corpus)]
results=[]
for case,mode,service,audio_root in plans:
 out=HERE/'controls'/mode/case;out.mkdir(parents=True,exist_ok=True);started=time.monotonic()
 captured=surface.SurfaceCaptureService(service,settle_timeout=30,poll_seconds=.25)
 desc=account.descriptor() if mode.startswith('account') else runtime.descriptor
 record={'case_id':case,'mode':mode}
 try:
  try:
   run_service_replay(service=captured,audio_path=audio_root/case/'audio.wav',out_dir=out,pace=1,max_pacing_lag=3,runs=1,expect_revision=desc.source_revision,expect_provider_hash=desc.provider_manifest_hash,expect_config_hash=desc.config_hashes.combined_config_hash)
   record['performance_failure']=None
  except ServiceReplayRtfFailure as e:
   record['performance_failure']=str(e)
   assert all(k in captured.captures for k in ['pre_stop_immediate','pre_stop_settled','post_stop_final'])
  ref=corpus/case/'reference.jsonl';duration=next(x['samples']/16000 for x in json.load(open(HERE/'mixing.json')) if x['case_id']==case)
  record['scores']={k:surface.score_surface(surface.Case(case,corpus/case,ref),surface.transcript_rows(v['snapshot'],duration)) for k,v in captured.captures.items()}
  record['surface_observations']=_quality_surface_observations(captured.captures,reference_speaker_count=len({json.loads(x)['speaker'] for x in ref.read_text().splitlines()}))
 except Exception as e:record['error']=str(e)
 finally:
  (out/'captures.json').write_text(json.dumps(captured.captures))
  record['elapsed_seconds']=time.monotonic()-started;results.append(record)
  (HERE/'repeat.json').write_text(json.dumps(results,indent=2)+'\n')
  print(mode,case,json.dumps(record),flush=True)
account.close()
