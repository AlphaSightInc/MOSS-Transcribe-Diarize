import sys,json,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tests.test_live_mixer import _Runtime
from moss_transcribe_diarize.app.live_lane_contract import LiveLane,LiveV2Frame
from moss_transcribe_diarize.app.live_v2_session import LiveV2Session
from moss_transcribe_diarize.app.live_mixer import LiveCompatibilityMixer

def run(early):
 source=LiveV2Session(max_retained_samples=960000);mix=LiveCompatibilityMixer(max_output_samples=8000);runtime=_Runtime();gaps=0
 def drain(final):
  nonlocal gaps
  while True:
   r=mix.admit_available('probe',source,runtime,final=final)
   if r is None:break
   gaps+=sum(r.diagnostics.gap_samples.values()) if hasattr(r.diagnostics,'gap_samples') else 0
 for seq,timestamp in enumerate([0,500000000,1000000000,1500000000,2000000000,2500500000]):
  values=[1000+(i%6000) for i in range(8000)]
  for lane in [LiveLane.SYSTEM,LiveLane.MICROPHONE]:
   silent=lane==LiveLane.MICROPHONE
   pcm=bytes(16000) if silent else struct.pack('<8000h',*values)
   source.accept(LiveV2Frame(lane=lane,sequence=seq,capture_timestamp_ns=timestamp,device_epoch=0,silent=silent,discontinuity=False,sample_rate=16000,sample_count=8000,pcm=pcm))
  drain(early and seq==4)
 drain(True)
 pcm=b''.join(x.pcm for x in runtime.frames)
 return list(struct.unpack('<'+'h'*(len(pcm)//2),pcm))
a=run(False);b=run(True)
result={'successor_timestamp_ns':2500500000,'nominal_frame_end_ns':2500000000,'timestamp_delta_samples':8,'normal_samples':len(a),'early_flush_samples':len(b),'changed_samples':sum(x!=y for x,y in zip(a,b)),'normal_zero_samples':a.count(0),'early_flush_zero_samples':b.count(0)}
print(json.dumps(result,indent=2))
