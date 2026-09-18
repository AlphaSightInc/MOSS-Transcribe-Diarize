"""THROWAWAY LOGIC action: fail one lane at a rolling boundary; print full surface.
One command: python prototypes/lane-decode-proto/failure_state.py
No provider requests. Real session/converger; deterministic decoder fault injection.
"""
from pathlib import Path
import sys,json
from dataclasses import asdict
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]))
import moss_transcribe_diarize.app

from moss_transcribe_diarize.app.live_session import AudioFrame,LiveSession,LiveIdentityPreparation,LiveIdentitySnapshot,CanonicalResult
from moss_transcribe_diarize.app.live_transcript_convergence import RollingTranscriptConverger
from moss_transcribe_diarize.app.live_adapters import InferenceTranscript,LiveProviderTransientError
from moss_transcribe_diarize.app.live_lane_decode import decode_refinement
session=LiveSession(max_retained_samples=320000)
session.accept_frame(AudioFrame(sequence=0,pcm=bytes(640000),sample_count=320000))
span=session.freeze_until(320000,reason='prototype')
text='[8][S01]system retained[12][8][S02]mic old[12]'
identity=LiveIdentitySnapshot(version=1,canonical_speakers=('speaker-0001','speaker-0002'))
prep=LiveIdentityPreparation(span_id=span.id,epoch=span.epoch,start_sample=0,end_sample=320000,base_snapshot_version=0,proposed_snapshot=identity,relabeled_transcript=text)
submitted=session.submit_prepared_canonical(CanonicalResult(span_id=span.id,epoch=span.epoch,start_sample=0,end_sample=320000,transcript=text,identity_preparation=prep,local_speakers=('S101','S201'),source_lanes=('system','microphone')))
converger=RollingTranscriptConverger(epoch=session.epoch)
converger.accept_pcm(0,bytes(640000))
class Tape:
    def __init__(self,byte):self.byte=byte
    def read(self,*,start_sample,end_sample):return self.byte*((end_sample-start_sample)*2)
class Decoder:
    def __init__(self):self.calls=[]
    def transcribe_pcm(self,*,span,pcm):
        self.calls.append('system' if pcm[0]==1 else 'microphone')
        if pcm[0]==1:raise LiveProviderTransientError('injected lane failure')
        return InferenceTranscript('[0][S01]healthy new words[1]')
decoder=Decoder()
c=SimpleNamespace(session=session,converger=converger,rolling_decoder=decoder,lane_tapes={'system':Tape(b'\x01'),'microphone':Tape(b'\x02')},_stopped_refinement_lanes=set(),_lane_preparers={})
states=[]
def show(action,**extra):
    snapshot=session.snapshot()
    row={'action':action,'surface':[asdict(s) for s in snapshot.effective_transcript],'lane_frontiers':session._lane_revision_frontiers,'global_frontier':snapshot.canonical_through_sample,'decoder_calls':list(decoder.calls),'stopped_lanes':sorted(c._stopped_refinement_lanes),**extra}
    states.append(row);print(json.dumps(row),flush=True)
show('committed',submitted=submitted.submitted)
for index in range(2):
    request=converger.observe_base(session.snapshot())[0]
    decoded=decode_refinement(c,request)
    proposal=converger.complete(request.id,decoded.outcome,segments=decoded.lane_segments,revision_lanes=decoded.revision_lanes)
    outcome=session.apply_text_revision(proposal)
    show('system failure, mic revision' if index==0 else 'next window: stopped system, mic continues',applied=outcome.applied,refusal=outcome.refusal)
final=session.snapshot().effective_transcript
verdict={'system_original_preserved':any(s.source_lane=='system' and s.start_sample==128000 and s.end_sample==192000 and s.text=='system retained' and s.canonical_speaker=='speaker-0001' for s in final),'mic_revised_windows':sum(s.source_lane=='microphone' and s.text=='healthy new words' for s in final),'calls':decoder.calls,'passed':all(s.get('applied',True) for s in states) and decoder.calls==['system','microphone','microphone']}
print(json.dumps(verdict))
Path('evidence/mvpfix/wp1/failure-state.json').write_text(json.dumps({'states':states,'verdict':verdict},indent=2))
