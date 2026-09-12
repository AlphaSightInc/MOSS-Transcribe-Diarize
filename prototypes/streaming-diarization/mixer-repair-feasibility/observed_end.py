import sys,struct,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tests.test_live_mixer import _Runtime
from moss_transcribe_diarize.app.live_lane_contract import LiveLane,LiveV2Frame
from moss_transcribe_diarize.app.live_v2_session import LiveV2Session
from moss_transcribe_diarize.app.live_mixer import LiveCompatibilityMixer,_LaneInterval
# Producer knows each frame's observed end when it emits the completed frame.
starts=[0,500000000,1000000000,1500000000,2000000000,2500500000]
ends=starts[1:]+[3000500000]
class Explicit(LiveCompatibilityMixer):
 def _sealed_intervals(self,retained,*,final):
  return tuple(_LaneInterval(retained=x,start_ns=x.frame.capture_timestamp_ns,end_ns=ends[x.frame.sequence]) for x in retained)
 def _sealed_frontier_ns(self,retained):return self._sealed_intervals(retained,final=False)[-1].end_ns

def run(cls):
 source=LiveV2Session(max_retained_samples=960000);mix=cls(max_output_samples=8000);runtime=_Runtime();accepted=[]
 for seq,ts in enumerate(starts):
  for lane in LiveLane:
   # Genuine overlap, different waveforms. No silence shortcut.
   values=[1000+(i%6000) if lane==LiveLane.SYSTEM else -700+(i%1200) for i in range(8000)]
   source.accept(LiveV2Frame(lane,seq,ts,0,False,False,16000,8000,struct.pack('<8000h',*values)))
  while mix.admit_available('test',source,runtime) is not None:pass
  accepted.append(sum(x.sample_count for x in runtime.frames))
 while mix.admit_available('test',source,runtime,final=True) is not None:pass
 return b''.join(x.pcm for x in runtime.frames),accepted
a,old=run(LiveCompatibilityMixer);b,new=run(Explicit)
r={'changed_bytes':sum(x!=y for x,y in zip(a,b)),'same_length':len(a)==len(b),'legacy_accepted_samples':old,'explicit_end_accepted_samples':new,'two_active_lanes':True}
assert a==b
assert new[4]==40008 and old[4]==32000
print(json.dumps(r,indent=2))
