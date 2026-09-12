import os,sys,json,time,wave,subprocess
from pathlib import Path
ROOT=Path(os.environ['MOSS_DIFFERENTIAL_REPO']);sys.path.insert(0,str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rolling_projection import project
import httpx
from moss_transcribe_diarize.phase2_acceptance_external import _load_surface_harness,_quality_surface_observations
from moss_transcribe_diarize.phase2_acceptance_replay import AccountCookieLiveReplayService,SESSION_COOKIE
from moss_transcribe_diarize.live_service_replay import InMemoryLiveReplayService,run_service_replay,ServiceReplayRtfFailure
from moss_transcribe_diarize.app import phase2_web_cli
HERE=Path(os.environ['MOSS_DIFFERENTIAL_SCRATCH'])
CORPUS=ROOT/'evidence/live-policy-sweep-20260825/corpus'
CASES=['mono_javier_intro_50s','interview_bill_ackman_60s','interview_keyu_jin_60s','interview_adam_frank_180s','discussion_jamie_dimon_180s','discussion_rtfl_90s']
surface=_load_surface_harness(ROOT);os.environ['SSL_CERT_FILE']=str(HERE/'cert.pem')
ns={'__file__':str(HERE/'run_stack.py')};exec((HERE/'run_stack.py').read_text().replace('phase2_web_cli.main(argv)',''),ns)
args=phase2_web_cli.parse_args(ns['argv']);file_runner=phase2_web_cli._build_file_runner(args);factory=phase2_web_cli._build_live_runtime_factory(args,file_runner);runtime=factory()
class Mono(InMemoryLiveReplayService):
 async def stop(self,sid,deadline):return await self.runtime.stop(sid,300)
client=httpx.Client(verify=str(HERE/'cert.pem'),base_url='https://127.0.0.1:17862');client.post('/api/workspace/bootstrap').raise_for_status()
Path(os.environ['MOSS_TEXT_OUT']).mkdir(parents=True,exist_ok=True)
cookie=Path(os.environ['MOSS_TEXT_OUT'])/'measurement.cookie';cookie.touch(mode=0o600);cookie.write_text(client.cookies.get(SESSION_COOKIE));cookie.chmod(0o600)
account=AccountCookieLiveReplayService(base_url='https://127.0.0.1:17862',cookie_file=cookie,timeout_seconds=300)
result=json.loads((Path(os.environ['MOSS_TEXT_OUT'])/'results.json').read_text()) if (Path(os.environ['MOSS_TEXT_OUT'])/'results.json').exists() else {'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'identity_manifest':Path(args.live_provider_manifest).name,'paths':{'mono':'current shared LiveServiceRuntime, legacy mono adapter, no Account/v2','account':'own Phase-2 HTTPS stack17862, fresh workspace, speakers + silent microphone'},'rows':[]}
for case in CASES:
 for mode,service in [('mono',Mono(runtime)),('account',account)]:
  if any(x['case_id']==case and x['mode']==mode for x in result['rows']):continue
  started=time.monotonic();out=Path(os.environ['MOSS_TEXT_OUT'])/'runs'/mode/case
  captured=surface.SurfaceCaptureService(service,settle_timeout=30,poll_seconds=.25)
  desc=runtime.descriptor if mode=='mono' else account.descriptor()
  try:
   performance_failure=None
   try:
    run_service_replay(service=captured,audio_path=CORPUS/case/'audio.wav',out_dir=out,pace=1,max_pacing_lag=3,runs=1,expect_revision=desc.source_revision,expect_provider_hash=desc.provider_manifest_hash,expect_config_hash=desc.config_hashes.combined_config_hash)
   except ServiceReplayRtfFailure as e:
    performance_failure=type(e).__name__
    assert all(x in captured.captures for x in ['pre_stop_immediate','pre_stop_settled','post_stop_final'])
   (out/'captures.json').write_text(json.dumps(captured.captures))
   ref=CORPUS/case/'reference.jsonl'
   with wave.open(str(CORPUS/case/'audio.wav')) as wav:
    duration=wav.getnframes()/wav.getframerate()
   counts=_quality_surface_observations(captured.captures,reference_speaker_count=len({json.loads(x)['speaker'] for x in ref.read_text().splitlines()}))
   scores={name:surface.score_surface(surface.Case(case,CORPUS/case,ref),surface.transcript_rows(cap['snapshot'],duration)) for name,cap in captured.captures.items()}
   row={'case_id':case,'mode':mode,'performance_failure':performance_failure,'elapsed_seconds':time.monotonic()-started,'scores':scores,'surface_observations':counts}
   row['rolling_evidence']=project(out/'run-001'/'trace.jsonl',captured.captures)
   result['rows'].append(row);(Path(os.environ['MOSS_TEXT_OUT'])/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('CASE',case,mode,json.dumps(row),flush=True)
  except Exception as e:
   (out/'captures.json').write_text(json.dumps(captured.captures))
   if captured.captures:
    sid=next(iter(captured.captures.values()))['snapshot']['session_id']
    try:
     events=service.events(sid,since_seq=0)
     (out/'failure-events.jsonl').write_text(''.join(json.dumps({'kind':'service_event','event':event.to_dict()})+'\n' for event in events))
    except Exception as evidence_error:
     (out/'failure-evidence-error.txt').write_text(type(evidence_error).__name__)
   result['rows'].append({'case_id':case,'mode':mode,'error':type(e).__name__});(Path(os.environ['MOSS_TEXT_OUT'])/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('FAILED',case,mode,type(e).__name__,flush=True)
account.close();client.close()
